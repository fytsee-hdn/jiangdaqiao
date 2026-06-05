"""
checklist_review_workflow.py — GSP Compliance Agent: C6C Checklist Review Flow.

Supports structured review of department checklist draft records generated via C6B.

Review actions:
- confirm_checklist_item
- correct_checklist_item
- reject_checklist_item
- mark_checklist_needs_human_review
- mark_checklist_needs_legal_review
- archive_checklist_item

Key rules:
- Confirming does NOT publish SOP/training/todo/legal interpretation
- Confirming does NOT approve customer overlay
- All actions require permission checks
- All actions write review_decision + audit log
- No action generates downstream content
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Bangkok")
except ImportError:
    _TZ = timezone(timedelta(hours=7))

_logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  Paths
# ══════════════════════════════════════════════════════════════════

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_CHECKLIST_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "checklists", "department_checklist.jsonl")
_DECISIONS_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "review_decisions", "review_decisions.jsonl")
_AUDIT_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "review_decisions", "review_audit.jsonl")
_PACKETS_DIR = os.path.join(_ROOT, "data", "knowledge", "compliance", "review_packets")

# ══════════════════════════════════════════════════════════════════
#  Valid status values
# ══════════════════════════════════════════════════════════════════

_VALID_REVIEW_STATUSES = {
    "draft_pending_review",
    "review_in_progress",
    "confirmed_for_internal_use",
    "correction_required",
    "rejected",
    "needs_human_review",
    "needs_legal_review",
    "archived",
    "superseded",
}

# ══════════════════════════════════════════════════════════════════
#  Permission model
# ══════════════════════════════════════════════════════════════════

_ROLE_PERMISSIONS = {
    "compliance_owner": [
        "list_checklist_items", "review_checklist_item", "correct_checklist_item",
        "reject_checklist_item", "mark_checklist_needs_review",
    ],
    "owner": [
        "list_checklist_items", "review_checklist_item", "correct_checklist_item",
        "reject_checklist_item", "mark_checklist_needs_review",
    ],
    "admin_developer": [
        "list_checklist_items", "review_checklist_item", "correct_checklist_item",
        "reject_checklist_item", "mark_checklist_needs_review",
    ],
    "admin": [],
    "department_owner": [],
    "employee": [],
}


def check_checklist_review_permission(action: str, user_role: str) -> dict:
    allowed = action in _ROLE_PERMISSIONS.get(user_role, [])
    return {
        "allowed": allowed,
        "action": action,
        "user_role": user_role,
        "reason": "OK" if allowed else f"Role '{user_role}' lacks permission '{action}'.",
    }


# ══════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════


def _now() -> str:
    return datetime.now(_TZ).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16] if s else ""


def _append_jsonl(path: str, record: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _find_record(path: str, record_id: str) -> Optional[dict]:
    """Find a record by its primary ID field."""
    if not os.path.isfile(path):
        return None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("checklist_item_id") == record_id:
                return rec
        except json.JSONDecodeError:
            pass
    return None


def _update_record(path: str, record_id: str, updates: dict) -> bool:
    """Update a record in a JSONL file. Rewrites entire file."""
    if not os.path.isfile(path):
        return False
    lines = []
    found = False
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            lines.append("")
            continue
        try:
            rec = json.loads(line)
            if rec.get("checklist_item_id") == record_id:
                rec.update(updates)
                rec["updated_at"] = _now()
                found = True
            lines.append(json.dumps(rec, ensure_ascii=False))
        except json.JSONDecodeError:
            lines.append(line)
    if found:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return found


def _record_decision(
    target_id: str,
    decision_type: str,
    decision_result: str,
    user_id: str,
    user_role: str,
    previous_status: str,
    new_status: str,
    comment: str = "",
    correction_text: str = "",
    correction_reason: str = "",
) -> dict:
    """Write a review_decision record and audit entry for checklist items."""
    dec_id = _uid("RD")
    audit_id = _uid("AUDIT")
    now = _now()

    decision = {
        "review_decision_id": dec_id,
        "version": 1,
        "target_record_type": "department_checklist",
        "target_record_id": target_id,
        "decision_type": decision_type,
        "decision_result": decision_result,
        "reviewer_user_id": user_id,
        "reviewer_role": user_role,
        "review_timestamp": now,
        "previous_status": previous_status,
        "new_status": new_status,
        "comment": comment,
        "correction_text": correction_text,
        "correction_reason": correction_reason,
        "audit_log_id": audit_id,
        "created_at": now,
    }
    _append_jsonl(_DECISIONS_PATH, decision)

    audit = {
        "audit_log_id": audit_id,
        "timestamp": now,
        "user_id_hash": _hash(user_id),
        "action": decision_type,
        "target_record_type": "department_checklist",
        "target_record_id": target_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "result": decision_result,
        "comment_present": bool(comment),
        "created_at": now,
    }
    _append_jsonl(_AUDIT_PATH, audit)

    _logger.info(
        "Checklist review decision %s: %s %s -> %s by %s",
        dec_id, target_id, previous_status, new_status, _hash(user_id),
    )
    return decision


# ══════════════════════════════════════════════════════════════════
#  Core review functions
# ══════════════════════════════════════════════════════════════════


def list_checklist_items(
    status: str = "draft_pending_review",
    limit: int = 20,
    user_role: str = "compliance_owner",
) -> dict:
    """List checklist items with a given review status."""
    perm = check_checklist_review_permission("list_checklist_items", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    if not os.path.isfile(_CHECKLIST_PATH):
        return {"ok": True, "count": 0, "items": [], "warning": "No checklist file found."}

    results = []
    for line in open(_CHECKLIST_PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            rs = rec.get("review_status", "")
            if rs == status or status == "all":
                results.append({
                    "checklist_item_id": rec.get("checklist_item_id", ""),
                    "linked_gsp_standard_id": rec.get("linked_gsp_standard_id", ""),
                    "checklist_question": str(rec.get("checklist_question", ""))[:120],
                    "checklist_type": rec.get("checklist_type", ""),
                    "responsible_function": rec.get("responsible_function", ""),
                    "review_status": rs,
                    "approval_status": rec.get("approval_status", "not_approved"),
                    "risk_level": rec.get("risk_level", ""),
                    "needs_human_review": rec.get("needs_human_review", False),
                })
        except json.JSONDecodeError:
            pass

    results = results[-limit:]
    return {
        "ok": True,
        "count": len(results),
        "items": results,
        "warning": "Confirming a checklist draft does NOT publish SOP, training, department todo, legal interpretation, or customer overlay.",
    }


def get_checklist_item(
    checklist_item_id: str,
    user_role: str = "compliance_owner",
) -> dict:
    """Get a single checklist item by ID."""
    perm = check_checklist_review_permission("list_checklist_items", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CHECKLIST_PATH, checklist_item_id)
    if rec is None:
        return {"ok": False, "error": f"Checklist item '{checklist_item_id}' not found."}

    return {"ok": True, "item": rec}


def confirm_checklist_item(
    checklist_item_id: str,
    user_id: str,
    user_role: str = "compliance_owner",
    comment: Optional[str] = None,
) -> dict:
    """Confirm a checklist item for internal use.

    Confirming means the checklist question and method are accepted for internal use.
    Does NOT publish SOP/training/todo/legal interpretation/customer overlay.
    """
    perm = check_checklist_review_permission("review_checklist_item", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CHECKLIST_PATH, checklist_item_id)
    if rec is None:
        return {"ok": False, "error": f"Checklist item '{checklist_item_id}' not found."}

    prev = rec.get("review_status", "unknown")
    if prev == "confirmed_for_internal_use":
        return {"ok": False, "error": f"Checklist item '{checklist_item_id}' is already confirmed."}

    new_status = "confirmed_for_internal_use"
    updated = _update_record(_CHECKLIST_PATH, checklist_item_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{checklist_item_id}'."}

    decision = _record_decision(
        checklist_item_id, "confirm_checklist_item", "confirmed",
        user_id, user_role, prev, new_status,
        comment=comment or "",
    )
    return {
        "ok": True,
        "decision": decision,
        "message": (
            f"Checklist item '{checklist_item_id}' confirmed for internal use. "
            "This does NOT publish SOP, training, department todo, legal interpretation, "
            "customer overlay, or final approval."
        ),
    }


def correct_checklist_item(
    checklist_item_id: str,
    user_id: str,
    user_role: str,
    corrections: dict,
    reason: str,
) -> dict:
    """Correct checklist item text/metadata.

    corrections dict can include: checklist_question, check_purpose, check_method,
    expected_result, required_evidence, responsible_function, etc.
    """
    perm = check_checklist_review_permission("correct_checklist_item", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CHECKLIST_PATH, checklist_item_id)
    if rec is None:
        return {"ok": False, "error": f"Checklist item '{checklist_item_id}' not found."}

    prev = rec.get("review_status", "unknown")

    corrections_to_apply = {}
    allowed_fields = {
        "checklist_question", "check_purpose", "check_method", "expected_result",
        "required_evidence", "responsible_function", "responsible_department",
        "suggested_frequency", "risk_level", "checklist_type", "site_scope",
        "applicability",
    }
    for field in allowed_fields:
        if field in corrections:
            corrections_to_apply[field] = corrections[field]

    corrections_to_apply["review_status"] = "correction_required"
    corrections_to_apply["approval_status"] = "not_approved"

    updated = _update_record(_CHECKLIST_PATH, checklist_item_id, corrections_to_apply)
    if not updated:
        return {"ok": False, "error": f"Failed to update '{checklist_item_id}'."}

    decision = _record_decision(
        checklist_item_id, "correct_checklist_item", "corrected",
        user_id, user_role, prev, "correction_required",
        correction_text=json.dumps(corrections_to_apply, ensure_ascii=False),
        correction_reason=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"Checklist item '{checklist_item_id}' corrected. Status set to correction_required.",
    }


def reject_checklist_item(
    checklist_item_id: str,
    user_id: str,
    user_role: str,
    reason: str,
) -> dict:
    """Reject a checklist item."""
    perm = check_checklist_review_permission("reject_checklist_item", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CHECKLIST_PATH, checklist_item_id)
    if rec is None:
        return {"ok": False, "error": f"Checklist item '{checklist_item_id}' not found."}

    prev = rec.get("review_status", "unknown")
    new_status = "rejected"

    updated = _update_record(_CHECKLIST_PATH, checklist_item_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{checklist_item_id}'."}

    decision = _record_decision(
        checklist_item_id, "reject_checklist_item", "rejected",
        user_id, user_role, prev, new_status,
        comment=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"Checklist item '{checklist_item_id}' rejected.",
    }


def mark_checklist_needs_human_review(
    checklist_item_id: str,
    user_id: str,
    user_role: str,
    reason: str,
) -> dict:
    """Mark a checklist item as needing human review."""
    perm = check_checklist_review_permission("mark_checklist_needs_review", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CHECKLIST_PATH, checklist_item_id)
    if rec is None:
        return {"ok": False, "error": f"Checklist item '{checklist_item_id}' not found."}

    prev = rec.get("review_status", "unknown")
    new_status = "needs_human_review"

    updated = _update_record(_CHECKLIST_PATH, checklist_item_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{checklist_item_id}'."}

    decision = _record_decision(
        checklist_item_id, "mark_checklist_needs_human_review", "needs_human_review",
        user_id, user_role, prev, new_status,
        comment=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"Checklist item '{checklist_item_id}' marked as needs_human_review.",
    }


def mark_checklist_needs_legal_review(
    checklist_item_id: str,
    user_id: str,
    user_role: str,
    reason: str,
) -> dict:
    """Mark a checklist item as needing legal review."""
    perm = check_checklist_review_permission("review_checklist_item", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CHECKLIST_PATH, checklist_item_id)
    if rec is None:
        return {"ok": False, "error": f"Checklist item '{checklist_item_id}' not found."}

    prev = rec.get("review_status", "unknown")
    new_status = "needs_legal_review"

    updated = _update_record(_CHECKLIST_PATH, checklist_item_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{checklist_item_id}'."}

    decision = _record_decision(
        checklist_item_id, "mark_checklist_needs_legal_review", "needs_legal_review",
        user_id, user_role, prev, new_status,
        comment=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"Checklist item '{checklist_item_id}' marked as needs_legal_review.",
    }


def archive_checklist_item(
    checklist_item_id: str,
    user_id: str,
    user_role: str,
    reason: str,
) -> dict:
    """Archive a checklist item."""
    perm = check_checklist_review_permission("review_checklist_item", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CHECKLIST_PATH, checklist_item_id)
    if rec is None:
        return {"ok": False, "error": f"Checklist item '{checklist_item_id}' not found."}

    prev = rec.get("review_status", "unknown")
    new_status = "archived"

    updated = _update_record(_CHECKLIST_PATH, checklist_item_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{checklist_item_id}'."}

    decision = _record_decision(
        checklist_item_id, "archive_checklist_item", "archived",
        user_id, user_role, prev, new_status,
        comment=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"Checklist item '{checklist_item_id}' archived.",
    }


# ══════════════════════════════════════════════════════════════════
#  Review packet generation
# ══════════════════════════════════════════════════════════════════


def generate_checklist_review_packet(
    batch_id: Optional[str] = None,
    user_role: str = "compliance_owner",
) -> dict:
    """Generate a checklist review packet as markdown."""
    perm = check_checklist_review_permission("list_checklist_items", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    if not os.path.isfile(_CHECKLIST_PATH):
        return {"ok": True, "count": 0, "path": None, "warning": "No checklist file."}

    all_items: List[dict] = []
    for line in open(_CHECKLIST_PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if batch_id:
                if rec.get("batch_id") != batch_id:
                    continue
            all_items.append(rec)
        except json.JSONDecodeError:
            pass

    status_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    func_counts: Dict[str, int] = {}
    dept_counts: Dict[str, int] = {}
    h_review = 0
    l_review = 0
    for rec in all_items:
        rs = rec.get("review_status", "unknown")
        status_counts[rs] = status_counts.get(rs, 0) + 1
        ct = rec.get("checklist_type", "other")
        type_counts[ct] = type_counts.get(ct, 0) + 1
        rf = rec.get("responsible_function", "Unknown")
        func_counts[rf] = func_counts.get(rf, 0) + 1
        rd = rec.get("responsible_department", "Unknown")
        dept_counts[rd] = dept_counts.get(rd, 0) + 1
        if rec.get("needs_human_review"):
            h_review += 1
        if rec.get("review_status") == "needs_legal_review":
            l_review += 1

    os.makedirs(_PACKETS_DIR, exist_ok=True)
    ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")
    run_id = _uid("C6C")
    path = os.path.join(_PACKETS_DIR, f"c6c_checklist_review_packet_{ts}.md")

    def _allowed_actions(status: str) -> list:
        base = {
            "draft_pending_review": ["confirm", "correct", "reject", "needs_human_review", "needs_legal_review", "archive"],
            "review_in_progress": ["confirm", "correct", "reject", "needs_human_review", "needs_legal_review", "archive"],
            "confirmed_for_internal_use": ["correct", "reject", "archive"],
            "correction_required": ["confirm", "correct", "reject", "archive"],
            "rejected": ["archive"],
            "needs_human_review": ["confirm", "correct", "reject", "needs_legal_review", "archive"],
            "needs_legal_review": ["confirm", "correct", "reject", "archive"],
            "archived": [],
            "superseded": [],
        }
        return base.get(status, [])

    lines = [
        "# C6C Checklist Review Packet",
        "",
        f"**Packet ID:** {run_id}",
        f"**Generated:** {_now()}",
        f"**Batch ID:** {batch_id or 'all'}",
        "",
        "---",
        "",
        "## Overview",
        "",
        f"- **Total items:** {len(all_items)}",
        f"- **Needs human review:** {h_review}",
        f"- **Needs legal review:** {l_review}",
        "",
        "### By Status",
    ]
    for s in sorted(status_counts.keys()):
        lines.append(f"- {s}: {status_counts[s]}")
    lines.append("")
    lines.append("### By Checklist Type")
    for t in sorted(type_counts.keys()):
        lines.append(f"- {t}: {type_counts[t]}")
    lines.append("")
    lines.append("### By Responsible Function")
    for f in sorted(func_counts.keys()):
        lines.append(f"- {f}: {func_counts[f]}")
    lines.append("")
    lines.append("### By Department")
    for d in sorted(dept_counts.keys()):
        lines.append(f"- {d}: {dept_counts[d]}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Item Details")
    lines.append("")

    for rec in all_items:
        cid = rec.get("checklist_item_id", "?")
        gsp_id = rec.get("linked_gsp_standard_id", "?")
        crm_ids = rec.get("linked_customer_requirement_ids", [])
        ev_ids = rec.get("linked_evidence_ids", [])
        question = str(rec.get("checklist_question", ""))[:200]
        method = str(rec.get("check_method", ""))[:150]
        result = str(rec.get("expected_result", ""))[:150]
        rs = rec.get("review_status", "unknown")
        aps = rec.get("approval_status", "not_approved")
        allowed = ", ".join(_allowed_actions(rs))

        lines.append(f"### {cid}")
        lines.append(f"- **GSP Standard:** {gsp_id}")
        lines.append(f"- **CRM IDs:** {', '.join(crm_ids[:3]) if crm_ids else 'none'}")
        lines.append(f"- **Evidence IDs:** {', '.join(ev_ids[:3]) if ev_ids else 'none'}")
        lines.append(f"- **Review Status:** {rs}")
        lines.append(f"- **Approval Status:** {aps}")
        lines.append(f"- **Question:** {question}")
        lines.append(f"- **Check Method:** {method}")
        lines.append(f"- **Expected Result:** {result}")
        lines.append(f"- **Allowed Actions:** {allowed}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## ⚠️ IMPORTANT WARNING",
        "",
        "Confirming a checklist draft does NOT publish SOP, training, department todo,",
        "legal interpretation, customer overlay, or final business approval.",
        "",
        "All checklist items remain draft or confirmed_internal only.",
        "They are NOT published checklists.",
    ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return {
        "ok": True,
        "packet_id": run_id,
        "path": path,
        "total_items": len(all_items),
        "by_status": status_counts,
        "by_type": type_counts,
        "by_function": func_counts,
        "by_department": dept_counts,
        "warning": "Confirming does NOT publish SOP, training, department todo, legal interpretation.",
    }
