"""
interaction_bridge.py — GSP Compliance Agent: Interaction Runtime Bridge.

The main entry point for all compliance-window interactions.
Ties together: window routing → user lookup → code prefilter
→ LLM intent → permission check → interaction_record → action.

PURE HARD-CODED FLOWS ARE NOT ALLOWED.
Code does deterministic prefilter + safety check only.
Intent is always LLM-classified (mock or real).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# ── Timezone ─────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Bangkok")
except ImportError:
    _TZ = timezone(timedelta(hours=7))

_logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  Imports (lazy to avoid circular)
# ══════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(_TZ).isoformat()


# ══════════════════════════════════════════════════════════════════
#  Mock User Registry (for runtime testing)
# ══════════════════════════════════════════════════════════════════

_MOCK_USERS: Dict[str, dict] = {
    "usr-owner-001": {
        "user_id": "usr-owner-001", "display_name": "System Owner",
        "primary_role": "owner", "status": "active",
        "permissions": ["*"],
        "accessible_windows": ["common_window", "admin_window", "compliance_owner_window", "department_compliance", "reimbursement_window"],
        "task_scopes": ["compliance_ikea", "compliance_vietnam_law"],
    },
    "usr-compliance-001": {
        "user_id": "usr-compliance-001", "display_name": "Compliance Owner",
        "primary_role": "compliance_owner", "status": "active",
        "permissions": ["upload_compliance_source_file", "confirm_source_text", "approve_customer_requirement"],
        "accessible_windows": ["common_window", "compliance_owner_window"],
        "task_scopes": ["compliance_ikea"],
    },
    "usr-dept-001": {
        "user_id": "usr-dept-001", "display_name": "Department Owner (PROD)",
        "primary_role": "department_owner", "status": "active",
        "permissions": ["upload_evidence_file", "submit_daily_report"],
        "accessible_windows": ["common_window", "department_compliance"],
        "task_scopes": ["compliance_ikea_prod"],
    },
    "usr-emp-001": {
        "user_id": "usr-emp-001", "display_name": "Employee",
        "primary_role": "employee", "status": "active",
        "permissions": [],
        "accessible_windows": ["common_window"],
        "task_scopes": [],
    },
    "usr-inactive-001": {
        "user_id": "usr-inactive-001", "display_name": "Inactive User",
        "primary_role": "employee", "status": "inactive",
        "permissions": [], "accessible_windows": [], "task_scopes": [],
    },
}


def lookup_user(user_id: str) -> Optional[dict]:
    """Look up a user in the mock registry."""
    return _MOCK_USERS.get(user_id)


# ══════════════════════════════════════════════════════════════════
#  Code Prefilter (deterministic only)
# ══════════════════════════════════════════════════════════════════

def code_prefilter(message: dict, user: dict, window: dict) -> dict:
    """Deterministic prefilter. Does NOT decide final intent.

    Returns candidate agent/intent for LLM to refine.
    """
    content = (message.get("content") or "").strip()
    msg_type = message.get("message_type", "text")
    has_file = bool(message.get("attachments") or message.get("file_path"))
    window_type = window.get("window_type", "")

    # Safety: block dangerous content
    blocked_patterns = ["rm -rf", "DROP TABLE", "DELETE FROM", "eval(", "exec("]
    for bp in blocked_patterns:
        if bp.lower() in content.lower():
            return {
                "candidate_agent": None, "candidate_intent": "blocked_dangerous",
                "confidence": 1.0, "risk_level": "critical",
                "requires_llm_analysis": False,
                "blocked": True, "block_reason": f"dangerous_pattern: {bp}",
                "notes": "Blocked by code prefilter — dangerous content detected.",
            }

    # Professional windows → direct to their agent
    if window_type == "professional_window":
        target = window["target_agent"]
        return {
            "candidate_agent": target, "candidate_intent": "professional_window_direct",
            "confidence": 0.85, "risk_level": "low",
            "requires_llm_analysis": True,
            "blocked": False, "block_reason": "",
            "notes": f"Professional window '{window['window_id']}' → direct to {target}. LLM refines intent.",
        }

    # Common window → through service agent, LLM classifies
    if has_file:
        return {
            "candidate_agent": "gsp_service_agent",
            "candidate_intent": "file_upload_pending_classification",
            "confidence": 0.65, "risk_level": "medium",
            "requires_llm_analysis": True,
            "blocked": False, "block_reason": "",
            "notes": "File upload in common_window — LLM must classify intent.",
        }

    return {
        "candidate_agent": "gsp_service_agent",
        "candidate_intent": "text_message_pending_classification",
        "confidence": 0.50, "risk_level": "low",
        "requires_llm_analysis": True,
        "blocked": False, "block_reason": "",
        "notes": "Text in common_window — LLM must classify intent.",
    }


# ══════════════════════════════════════════════════════════════════
#  Mock LLM Intent Classifier
# ══════════════════════════════════════════════════════════════════

def mock_llm_classify(prefilter: dict, user: dict, window: dict) -> dict:
    """Mock LLM intent classifier for testing.

    In production, this is replaced by real LLM call.
    """
    candidate = prefilter.get("candidate_agent", "")
    intent = prefilter.get("candidate_intent", "")
    has_file = "file" in intent or "upload" in intent

    if prefilter.get("blocked"):
        return {
            "intent_id": f"li-{uuid.uuid4().hex[:8]}",
            "selected_agent": None, "confidence": 1.0,
            "intent_summary": "Blocked by prefilter", "reason": prefilter["block_reason"],
            "requires_permission": False, "risk_flags": ["blocked"],
            "needs_clarification": False,
            "llm_mode": "mock",
        }

    # Professional window: refine intent based on file presence
    if candidate == "gsp_compliance_agent":
        if has_file:
            return {
                "intent_id": f"li-{uuid.uuid4().hex[:8]}",
                "selected_agent": "gsp_compliance_agent",
                "confidence": 0.82, "intent_summary": "用户上传文件到合规窗口",
                "reason": "合规窗口文件上传 — 可能是客户要求源文件",
                "requires_permission": True,
                "required_permission": "upload_compliance_source_file",
                "risk_flags": [], "risk_level": "medium",
                "needs_clarification": True,
                "clarification_question": "请确认这是客户合规要求源文件、内部参考文件、法律源文件还是证据文件？",
                "llm_mode": "mock",
            }
        return {
            "intent_id": f"li-{uuid.uuid4().hex[:8]}",
            "selected_agent": "gsp_compliance_agent",
            "confidence": 0.78, "intent_summary": "合规相关文本查询",
            "reason": "合规窗口文本消息", "requires_permission": False,
            "risk_flags": [], "llm_mode": "mock",
        }

    # Common window
    return {
        "intent_id": f"li-{uuid.uuid4().hex[:8]}",
        "selected_agent": "gsp_service_agent",
        "confidence": 0.5, "intent_summary": "需要通过Service Agent路由",
        "reason": "common_window — LLM路由到Service Agent",
        "requires_permission": False, "risk_flags": [], "llm_mode": "mock",
    }


# ══════════════════════════════════════════════════════════════════
#  Permission Check
# ══════════════════════════════════════════════════════════════════

def check_permission(llm_result: dict, user: dict, window: dict) -> dict:
    """Code-level permission check. LLM output is advisory only."""
    required_perm = llm_result.get("required_permission", "")
    user_perms = user.get("permissions", [])
    role = user.get("primary_role", "employee")

    # Owner bypass (but still logged)
    if role == "owner":
        return {
            "check_id": f"pc-{uuid.uuid4().hex[:8]}",
            "user_id": user["user_id"], "allowed": True,
            "reason": "Owner has unrestricted access.", "is_high_risk": False,
            "requires_confirmation": False,
        }

    # Admin limited — can view, cannot approve compliance
    if role == "admin" and required_perm in ("approve_customer_requirement", "maintain_gsp_standard"):
        return {
            "check_id": f"pc-{uuid.uuid4().hex[:8]}",
            "user_id": user["user_id"], "allowed": False,
            "reason": "Admin cannot approve compliance requirements in Phase D0.",
            "is_high_risk": True, "requires_confirmation": False,
        }

    # Employee: no upload permissions
    if role == "employee" and required_perm and "upload" in required_perm:
        return {
            "check_id": f"pc-{uuid.uuid4().hex[:8]}",
            "user_id": user["user_id"], "allowed": False,
            "reason": "Employee role does not have upload permissions.",
            "is_high_risk": False, "requires_confirmation": False,
        }

    # Department owner: can upload evidence, not source files
    if role == "department_owner":
        if required_perm == "upload_compliance_source_file":
            return {
                "check_id": f"pc-{uuid.uuid4().hex[:8]}",
                "user_id": user["user_id"], "allowed": False,
                "reason": "Department owner cannot upload compliance source files.",
                "is_high_risk": False, "requires_confirmation": False,
            }
        if required_perm in ("upload_evidence_file", "submit_daily_report"):
            return {
                "check_id": f"pc-{uuid.uuid4().hex[:8]}",
                "user_id": user["user_id"], "allowed": True,
                "reason": f"Department owner can {required_perm}.",
                "is_high_risk": False, "requires_confirmation": False,
            }

    # Check user permissions
    if required_perm and required_perm not in user_perms:
        return {
            "check_id": f"pc-{uuid.uuid4().hex[:8]}",
            "user_id": user["user_id"], "allowed": False,
            "reason": f"Missing required permission: {required_perm}.",
            "is_high_risk": False, "requires_confirmation": False,
        }

    return {
        "check_id": f"pc-{uuid.uuid4().hex[:8]}",
        "user_id": user["user_id"], "allowed": True,
        "reason": "Permission check passed.", "is_high_risk": False,
        "requires_confirmation": False,
    }


# ══════════════════════════════════════════════════════════════════
#  Interaction Record Builder
# ══════════════════════════════════════════════════════════════════

def build_interaction_record(
    message: dict,
    window: dict,
    user: dict,
    prefilter: dict,
    llm_result: dict,
    permission: dict,
    *,
    upload_meta: Optional[dict] = None,
) -> dict:
    """Build a complete interaction_record dict."""
    ir_id = f"ir-{uuid.uuid4().hex[:12]}"
    now = _now()

    rec = {
        "interaction_id": ir_id,
        "user_id": user["user_id"],
        "window_id": window["window_id"],
        "user_message": (message.get("content") or "")[:500],
        "message_type": message.get("message_type", "text"),
        "timestamp": now,
        "status": _derive_status(prefilter, permission, llm_result),
        "routed_to_agent": llm_result.get("selected_agent", ""),
        "prefilter_result": {
            "prefilter_id": f"pf-{uuid.uuid4().hex[:8]}",
            "matched": prefilter.get("blocked", False),
            "suggested_window": window["window_id"],
            "confidence": prefilter.get("confidence", 0),
        },
        "llm_intent_result": {
            "intent_id": llm_result.get("intent_id", ""),
            "selected_agent": llm_result.get("selected_agent", ""),
            "confidence": llm_result.get("confidence", 0),
        },
        "permission_result": {
            "check_id": permission.get("check_id", ""),
            "allowed": permission.get("allowed", False),
            "reason": permission.get("reason", ""),
        },
        "agent_response": "",
        "response_time_ms": 0,
        "version": 1, "created_at": now, "updated_at": now,
    }

    if upload_meta:
        rec["upload_metadata"] = {
            "upload_id": upload_meta.get("upload_id", ""),
            "original_filename": upload_meta.get("original_filename", ""),
            "staged_file_path": upload_meta.get("staged_path", ""),
            "file_sha256": upload_meta.get("file_hash", ""),
            "file_extension": upload_meta.get("extension", ""),
            "file_size": upload_meta.get("size", 0),
            "staging_status": "staged_pending_user_confirmation",
        }

    return rec


def _derive_status(prefilter: dict, permission: dict, llm_result: dict) -> str:
    if prefilter.get("blocked"):
        return "blocked"
    if not permission.get("allowed"):
        return "denied_by_permission"
    if llm_result.get("needs_clarification"):
        return "staged_pending_user_confirmation"
    return "routed_to_agent"


# ══════════════════════════════════════════════════════════════════
#  Full Pipeline: handle_interaction()
# ══════════════════════════════════════════════════════════════════

def handle_interaction(
    window_id: str,
    user_id: str,
    content: str = "",
    message_type: str = "text",
    file_path: str = "",
    original_filename: str = "",
) -> dict:
    """Full interaction pipeline: window → user → prefilter → LLM → permission → record.

    Returns a complete result dict with reply_text for the user.
    """
    from hermes.gsp_compliance_agent.runtime.window_router import route_window, check_window_access
    from hermes.gsp_compliance_agent.runtime.upload_intake import stage_upload, create_import_request

    start_time = time.time()
    message = {"content": content, "message_type": message_type}
    if file_path:
        message["file_path"] = file_path
        message["attachments"] = [{"file_type": os.path.splitext(file_path)[1], "file_path": file_path}]

    # ── 1. Window routing ────────────────────────────
    window = route_window(window_id)

    # ── 2. User lookup ──────────────────────────────
    user = lookup_user(user_id)
    if user is None:
        return {
            "ok": False,
            "reply_text": "User not registered. Please contact system administrator.",
            "interaction_id": f"ir-{uuid.uuid4().hex[:12]}",
            "status": "denied_unregistered_user",
            "window_id": window_id,
            "target_agent": "",
        }

    if user.get("status") != "active":
        return {
            "ok": False,
            "reply_text": "Your account is inactive. Please contact system administrator.",
            "interaction_id": f"ir-{uuid.uuid4().hex[:12]}",
            "status": "denied_inactive_user",
            "window_id": window_id,
            "target_agent": "",
        }

    user_role = user["primary_role"]

    # ── 3. Window access check ──────────────────────
    access = check_window_access(window_id, user_role)
    if not access["allowed"]:
        return {
            "ok": False,
            "reply_text": f"You do not have access to this window. {access['reason']}",
            "interaction_id": f"ir-{uuid.uuid4().hex[:12]}",
            "status": "denied_window_access",
            "window_id": window_id,
            "target_agent": window["target_agent"],
        }

    # ── 4. Code prefilter ───────────────────────────
    prefilter = code_prefilter(message, user, window)
    if prefilter.get("blocked"):
        return {
            "ok": False,
            "reply_text": f"Message blocked: {prefilter['block_reason']}",
            "interaction_id": f"ir-{uuid.uuid4().hex[:12]}",
            "status": "blocked",
            "window_id": window_id,
            "target_agent": "",
        }

    # ── 5. File upload staging (if applicable) ───────
    upload_meta = None
    if file_path and os.path.isfile(file_path):
        upload_meta = stage_upload(file_path, user_id, original_filename)
        if not upload_meta["ok"]:
            return {
                "ok": False,
                "reply_text": f"File upload failed: {upload_meta['error']}",
                "interaction_id": f"ir-{uuid.uuid4().hex[:12]}",
                "status": "upload_failed",
                "window_id": window_id,
            }

    # ── 6. LLM intent classification (mock) ──────────
    llm_result = mock_llm_classify(prefilter, user, window)

    # ── 7. Permission check ──────────────────────────
    permission = check_permission(llm_result, user, window)

    # ── 8. Build interaction record ──────────────────
    ir = build_interaction_record(message, window, user, prefilter, llm_result, permission, upload_meta=upload_meta)
    elapsed_ms = int((time.time() - start_time) * 1000)
    ir["response_time_ms"] = elapsed_ms

    # ── 9. Generate response ─────────────────────────
    target = llm_result.get("selected_agent", window["target_agent"])
    display = window.get("display_name", "GSP Agent")

    if not permission["allowed"]:
        reply = f"You do not have permission for this action. {permission['reason']}"
        return {
            "ok": False, "reply_text": reply,
            "interaction_id": ir["interaction_id"],
            "status": "denied_by_permission",
            "window_id": window_id, "target_agent": target,
            "interaction_record": ir, "upload_meta": upload_meta,
        }

    if upload_meta:
        reply = (
            f"I received the file '{upload_meta['original_filename']}' and saved it to staging.\n"
            f"Detected intent: compliance source file upload.\n"
            f"Target agent: {display}.\n"
            f"Current status: staged_pending_user_confirmation.\n"
            f"File hash: {upload_meta['file_hash'][:16]}...\n"
            f"This file has NOT been imported into the controlled source library yet.\n"
            f"Please confirm whether this file should be submitted for controlled source import review."
        )
        return {
            "ok": True, "reply_text": reply,
            "interaction_id": ir["interaction_id"],
            "status": "staged_pending_user_confirmation",
            "window_id": window_id, "target_agent": target,
            "interaction_record": ir, "upload_meta": upload_meta,
            "allowed_next_actions": [
                "confirm_submit_for_import_review",
                "classify_as_internal_reference",
                "classify_as_legal_source",
                "reject_upload",
                "ask_for_summary",
            ],
        }

    return {
        "ok": True,
        "reply_text": f"Message received. Routed to {display}.",
        "interaction_id": ir["interaction_id"],
        "status": "routed_to_agent",
        "window_id": window_id, "target_agent": target,
        "interaction_record": ir,
    }


# ══════════════════════════════════════════════════════════════════
#  Action handler: confirm_submit_for_import_review
# ══════════════════════════════════════════════════════════════════

def handle_confirm_import_review(
    upload_meta: dict, user_id: str, window_id: str,
    intended_source_type: str = "customer_requirement",
    intended_customer: str = "",
    intended_standard_family: str = "",
) -> dict:
    """Handle user confirmation: move to accepted and create import request.

    Does NOT perform actual import. Creates dry-run import_request.
    """
    from hermes.gsp_compliance_agent.runtime.upload_intake import move_to_accepted, create_import_request

    upload_id = upload_meta.get("upload_id", "")
    staged_path = upload_meta.get("staged_path", "")

    moved = move_to_accepted(upload_id, staged_path)
    if not moved["ok"]:
        return {"ok": False, "reply_text": f"Failed to accept file: {moved['error']}"}

    irq = create_import_request(
        upload_id=upload_id,
        user_id=user_id,
        window_id=window_id,
        staged_path=moved["new_path"],
        file_hash=upload_meta.get("file_hash", ""),
        intended_source_type=intended_source_type,
        intended_customer=intended_customer,
        intended_standard_family=intended_standard_family,
    )

    return {
        "ok": True,
        "reply_text": (
            f"File accepted for import review.\n"
            f"Import request ID: {irq['import_request_id']}\n"
            f"Status: pending_c3_import\n"
            f"The file has been moved to accepted_for_import_review.\n"
            f"Actual controlled import will be performed in Phase C3.1 or C4."
        ),
        "import_request": irq,
    }
