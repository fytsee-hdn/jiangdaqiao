"""
wecom_compliance_bridge.py — WeCom Adapter Integration for Compliance Upload Intake.

Connects WeCom messages to the D0 interaction bridge for compliance windows.
Feature-flagged: COMPLIANCE_UPLOAD_INTAKE_ENABLED must be "true".

Flow: WeCom event → normalize → handle_interaction → reply to user.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  Feature flag
# ══════════════════════════════════════════════════════════════════

def is_enabled() -> bool:
    return os.environ.get("COMPLIANCE_UPLOAD_INTAKE_ENABLED", "false").lower() == "true"

# ══════════════════════════════════════════════════════════════════
#  Window binding config
# ══════════════════════════════════════════════════════════════════

_BINDING_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
    "config", "agent_windows", "wecom_window_binding.json",
)
_binding_cache: Optional[dict] = None


def _load_binding() -> dict:
    global _binding_cache
    if _binding_cache is not None:
        return _binding_cache
    path = os.path.abspath(_BINDING_PATH)
    try:
        with open(path, "r", encoding="utf-8") as f:
            _binding_cache = json.load(f)
    except Exception:
        _binding_cache = {"default_window": "common_window", "bindings": []}
    return _binding_cache


def _resolve_window(wecom_entry: str, bot_name: str = "") -> str:
    """Resolve WeCom entry identifier → internal window_id."""
    binding = _load_binding()
    # Match by wecom_entry first
    for b in binding.get("bindings", []):
        if b.get("wecom_entry") == wecom_entry:
            return b["window_id"]
    # Match by bot_name
    if bot_name:
        for b in binding.get("bindings", []):
            if b.get("bot_name", "").lower() == bot_name.lower():
                return b["window_id"]
    # Fallback
    return binding.get("default_window", "common_window")


# ══════════════════════════════════════════════════════════════════
#  WeCom event normalizer
# ══════════════════════════════════════════════════════════════════

def normalize_wecom_event(wecom_event: dict) -> dict:
    """Convert a WeCom event dict into normalized interaction input.

    Expected WeCom event fields (flexible):
      - wecom_entry or bot_name
      - user_id or enterprise_wechat_id or FromUserName
      - content or text or MsgType + Content
      - message_type: text / image / file
      - file_path (if downloaded)
      - original_filename
    """
    # Window
    wecom_entry = wecom_event.get("wecom_entry", "")
    bot_name = wecom_event.get("bot_name", "")
    window_id = _resolve_window(wecom_entry, bot_name)

    # User
    user_id = (
        wecom_event.get("user_id")
        or wecom_event.get("enterprise_wechat_id")
        or wecom_event.get("FromUserName")
        or "unknown_user"
    )

    # Message
    content = wecom_event.get("content") or wecom_event.get("text") or wecom_event.get("Content") or ""
    msg_type = wecom_event.get("message_type") or wecom_event.get("MsgType") or "text"

    # File
    file_path = wecom_event.get("file_path") or wecom_event.get("local_path") or ""
    original_filename = wecom_event.get("original_filename") or wecom_event.get("filename") or ""

    return {
        "window_id": window_id,
        "user_id": user_id,
        "content": content,
        "message_type": msg_type,
        "file_path": file_path,
        "original_filename": original_filename,
        "wecom_entry": wecom_entry,
        "bot_name": bot_name,
        "timestamp": wecom_event.get("timestamp") or wecom_event.get("CreateTime") or "",
    }


# ══════════════════════════════════════════════════════════════════
#  Main entry point
# ══════════════════════════════════════════════════════════════════

def handle_wecom_compliance_event(wecom_event: dict) -> dict:
    """Process a WeCom event through the D0 interaction bridge.

    Only active when COMPLIANCE_UPLOAD_INTAKE_ENABLED=true.
    Otherwise returns feature_disabled response.
    """
    from hermes.gsp_compliance_agent.runtime.compliance_audit import log_event

    if not is_enabled():
        return {
            "ok": True,
            "reply_text": "",
            "status": "feature_disabled",
            "note": "COMPLIANCE_UPLOAD_INTAKE_ENABLED is false. Event not processed by compliance bridge.",
        }

    # ── 1. Normalize ─────────────────────────────────────
    norm = normalize_wecom_event(wecom_event)
    log_event("wecom_message_received", {
        "user_id": norm["user_id"], "window_id": norm["window_id"],
        "message_type": norm["message_type"], "has_file": bool(norm["file_path"]),
        "bot_name": norm["bot_name"],
    })

    # ── 2. Call D0 interaction bridge ────────────────────
    from hermes.gsp_compliance_agent.runtime.interaction_bridge import handle_interaction

    result = handle_interaction(
        window_id=norm["window_id"],
        user_id=norm["user_id"],
        content=norm["content"],
        message_type=norm["message_type"],
        file_path=norm["file_path"],
        original_filename=norm["original_filename"],
    )

    # ── 3. Track pending upload if staged ────────────────
    upload_meta = result.get("upload_meta")
    if upload_meta and result.get("status") == "staged_pending_user_confirmation":
        from hermes.gsp_compliance_agent.runtime.pending_upload_tracker import add_pending_upload
        add_pending_upload(
            upload_id=upload_meta["upload_id"],
            user_id=norm["user_id"],
            window_id=norm["window_id"],
            staged_path=upload_meta.get("staged_path", ""),
            file_hash=upload_meta.get("file_hash", ""),
            detected_intent="compliance_source_file_upload",
        )

    # ── 4. Audit ─────────────────────────────────────────
    event_type = "upload_staged" if upload_meta else "interaction_created"
    if not result["ok"]:
        event_type = "permission_denied" if "permission" in result.get("status", "") else "error"
    log_event(event_type, {
        "user_id": norm["user_id"], "window_id": norm["window_id"],
        "status": result.get("status"), "ok": result["ok"],
        "upload_id": (upload_meta or {}).get("upload_id", ""),
    })

    return result


# ══════════════════════════════════════════════════════════════════
#  Confirmation / rejection handlers
# ══════════════════════════════════════════════════════════════════

def handle_confirm_upload(user_id: str, upload_id: str,
                          intended_source_type: str = "customer_requirement",
                          intended_customer: str = "",
                          intended_standard_family: str = "") -> dict:
    """User confirms a pending staged upload for import review.

    Only the upload owner can confirm. Creates import_request only.
    """
    from hermes.gsp_compliance_agent.runtime.compliance_audit import log_event
    from hermes.gsp_compliance_agent.runtime.pending_upload_tracker import confirm_upload, get_pending_upload

    pending = get_pending_upload(upload_id)
    if pending is None:
        log_event("error", {"user_id": user_id, "upload_id": upload_id, "error": "not_found"})
        return {"ok": False, "reply_text": "Upload not found or already processed."}

    confirmed = confirm_upload(upload_id, user_id)
    if not confirmed["ok"]:
        log_event("permission_denied", {"user_id": user_id, "upload_id": upload_id,
                     "error": confirmed["error"]})
        return {"ok": False, "reply_text": f"Cannot confirm: {confirmed['error']}"}

    from hermes.gsp_compliance_agent.runtime.interaction_bridge import handle_confirm_import_review

    upload_meta = {
        "upload_id": upload_id,
        "staged_path": pending["staged_file_path"],
        "file_hash": pending["file_hash"],
    }
    result = handle_confirm_import_review(
        upload_meta=upload_meta, user_id=user_id,
        window_id=pending["window_id"],
        intended_source_type=intended_source_type,
        intended_customer=intended_customer,
        intended_standard_family=intended_standard_family,
    )

    log_event("upload_confirmed", {
        "user_id": user_id, "upload_id": upload_id, "ok": result["ok"],
    })
    return result


def handle_reject_upload(user_id: str, upload_id: str, reason: str = "") -> dict:
    """User rejects a pending staged upload."""
    from hermes.gsp_compliance_agent.runtime.compliance_audit import log_event
    from hermes.gsp_compliance_agent.runtime.pending_upload_tracker import reject_upload, get_pending_upload
    from hermes.gsp_compliance_agent.runtime.upload_intake import move_to_rejected

    pending = get_pending_upload(upload_id)
    if pending is None:
        return {"ok": False, "reply_text": "Upload not found or already processed."}

    rejected = reject_upload(upload_id, user_id, reason)
    if not rejected["ok"]:
        return {"ok": False, "reply_text": f"Cannot reject: {rejected['error']}"}

    move_to_rejected(pending["staged_file_path"], reason)
    log_event("upload_rejected", {"user_id": user_id, "upload_id": upload_id, "reason": reason})

    return {"ok": True, "reply_text": "Upload rejected. File moved to rejected staging."}


def handle_confirm_action(user_id: str, action: str, upload_id: str, **kwargs) -> dict:
    """Route user confirmation action to the correct handler."""
    if action == "confirm_submit_for_import_review":
        return handle_confirm_upload(user_id, upload_id, **kwargs)
    if action == "reject_upload":
        return handle_reject_upload(user_id, upload_id, kwargs.get("reason", ""))
    if action in ("classify_as_internal_reference", "classify_as_legal_source", "ask_for_summary"):
        return {
            "ok": True,
            "reply_text": f"Action '{action}' acknowledged. File remains in staging for manual classification.",
        }
    return {"ok": False, "reply_text": f"Unknown action: {action}"}
