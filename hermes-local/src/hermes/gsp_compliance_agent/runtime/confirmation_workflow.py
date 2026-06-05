"""
confirmation_workflow.py — GSP Compliance Agent: Human Confirmation Workflow.

Handles source text, customer requirement, and controlled term confirmation,
correction, rejection, split, and merge decisions.

All decisions:
  - Require permission checks
  - Write immutable review_decision records  
  - Update target record status
  - Write audit log entries
  - NEVER generate GSP standards or approve SOP/checklist/training
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
_DECISIONS_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "review_decisions", "review_decisions.jsonl")
_AUDIT_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "review_decisions", "review_audit.jsonl")
_CRM_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "customer_requirements", "customer_requirement_master.jsonl")
_STA_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "source_text_archive", "source_text_archive.jsonl")
_CT_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "controlled_terms", "controlled_terms.jsonl")

# ══════════════════════════════════════════════════════════════════
#  Permission model
# ══════════════════════════════════════════════════════════════════

_REQUIRED_PERMISSIONS = {
    "confirm_source_text": ["confirm_source_text"],
    "correct_source_text": ["correct_source_text"],
    "reject_source_text": ["reject_source_text"],
    "confirm_customer_requirement": ["confirm_customer_requirement"],
    "reject_customer_requirement": ["reject_customer_requirement"],
    "confirm_controlled_term": ["confirm_controlled_term"],
    "reject_controlled_term": ["reject_controlled_term"],
}

_ROLE_PERMISSIONS = {
    "compliance_owner": [
        "confirm_source_text", "correct_source_text", "reject_source_text",
        "confirm_customer_requirement", "reject_customer_requirement",
        "confirm_controlled_term", "reject_controlled_term",
    ],
    "owner": ["confirm_source_text", "confirm_customer_requirement", "confirm_controlled_term",
              "correct_source_text", "reject_source_text", "reject_customer_requirement", "reject_controlled_term"],
    "admin": [],
    "department_owner": [],
    "employee": [],
}


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
    if not os.path.isfile(path):
        return None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("id") == record_id:
                return rec
        except Exception:
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
            if rec.get("id") == record_id:
                rec.update(updates)
                rec["updated_at"] = _now()
                found = True
            lines.append(json.dumps(rec, ensure_ascii=False))
        except Exception:
            lines.append(line)
    if found:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return found


# ══════════════════════════════════════════════════════════════════
#  Permission check
# ══════════════════════════════════════════════════════════════════

def check_permission(action: str, user_role: str) -> dict:
    allowed = action in _ROLE_PERMISSIONS.get(user_role, [])
    return {"allowed": allowed, "action": action, "user_role": user_role,
            "reason": "OK" if allowed else f"Role '{user_role}' lacks permission '{action}'."}


# ══════════════════════════════════════════════════════════════════
#  Core confirmation functions
# ══════════════════════════════════════════════════════════════════

def _record_decision(
    target_type: str, target_id: str, decision_type: str,
    decision_result: str, user_id: str, user_role: str,
    previous_status: str, new_status: str,
    comment: str = "", correction_text: str = "", correction_reason: str = "",
    split_ids: Optional[List[str]] = None, merge_id: str = "",
) -> dict:
    """Write a review_decision record and audit entry."""
    dec_id = _uid("RD")
    audit_id = _uid("AUDIT")
    now = _now()

    decision = {
        "review_decision_id": dec_id,
        "version": 1,
        "target_record_type": target_type,
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
        "split_target_ids": split_ids or [],
        "merge_target_id": merge_id,
        "audit_log_id": audit_id,
        "created_at": now,
    }
    _append_jsonl(_DECISIONS_PATH, decision)

    audit = {
        "audit_log_id": audit_id,
        "timestamp": now,
        "user_id_hash": _hash(user_id),
        "action": decision_type,
        "target_record_type": target_type,
        "target_record_id": target_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "result": decision_result,
        "comment_present": bool(comment),
        "created_at": now,
    }
    _append_jsonl(_AUDIT_PATH, audit)

    _logger.info("Review decision %s: %s %s → %s by %s", dec_id, target_type, previous_status, new_status, _hash(user_id))
    return decision


# ── Source Text ──────────────────────────────────────────

def confirm_source_text(record_id: str, user_id: str, user_role: str, comment: str = "") -> dict:
    perm = check_permission("confirm_source_text", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_STA_PATH, record_id)
    if rec is None:
        return {"ok": False, "error": f"Source text record '{record_id}' not found."}

    prev = rec.get("confirmation_status", rec.get("review_status", "unknown"))
    _update_record(_STA_PATH, record_id, {"confirmation_status": "confirmed_by_user", "review_status": "confirmed_by_user"})
    decision = _record_decision("source_text_archive", record_id, "confirm_source_text", "confirmed", user_id, user_role, prev, "confirmed_by_user", comment)
    return {"ok": True, "decision": decision, "message": "Source text confirmed (extraction accuracy only — NOT GSP standard approval)."}


def correct_source_text(record_id: str, user_id: str, user_role: str, corrected_text: str, reason: str) -> dict:
    perm = check_permission("correct_source_text", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_STA_PATH, record_id)
    if rec is None:
        return {"ok": False, "error": f"Source text record '{record_id}' not found."}

    prev = rec.get("confirmation_status", rec.get("review_status", "unknown"))
    _update_record(_STA_PATH, record_id, {"original_text": corrected_text, "confirmation_status": "corrected_pending_confirmation", "review_status": "corrected_pending_confirmation"})
    decision = _record_decision("source_text_archive", record_id, "correct_source_text", "corrected", user_id, user_role, prev, "corrected_pending_confirmation", correction_text=corrected_text, correction_reason=reason)
    return {"ok": True, "decision": decision, "message": "Source text corrected. Re-review required."}


def reject_source_text(record_id: str, user_id: str, user_role: str, reason: str) -> dict:
    perm = check_permission("reject_source_text", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_STA_PATH, record_id)
    if rec is None:
        return {"ok": False, "error": f"Source text record '{record_id}' not found."}

    prev = rec.get("confirmation_status", rec.get("review_status", "unknown"))
    _update_record(_STA_PATH, record_id, {"confirmation_status": "rejected_by_user", "review_status": "rejected_by_user"})
    decision = _record_decision("source_text_archive", record_id, "reject_source_text", "rejected", user_id, user_role, prev, "rejected_by_user", comment=reason)
    return {"ok": True, "decision": decision, "message": "Source text rejected."}


# ── Customer Requirement ─────────────────────────────────

def confirm_customer_requirement(record_id: str, user_id: str, user_role: str, comment: str = "") -> dict:
    perm = check_permission("confirm_customer_requirement", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CRM_PATH, record_id)
    if rec is None:
        return {"ok": False, "error": f"Customer requirement '{record_id}' not found."}

    prev = rec.get("review_status", "unknown")
    _update_record(_CRM_PATH, record_id, {"review_status": "requirement_confirmed", "approval_status": "not_approved"})
    decision = _record_decision("customer_requirement_master", record_id, "confirm_customer_requirement", "confirmed", user_id, user_role, prev, "requirement_confirmed", comment)
    return {"ok": True, "decision": decision, "message": "Customer requirement confirmed (as valid customer requirement only — NOT GSP standard approval)."}


def reject_customer_requirement(record_id: str, user_id: str, user_role: str, reason: str) -> dict:
    perm = check_permission("reject_customer_requirement", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CRM_PATH, record_id)
    if rec is None:
        return {"ok": False, "error": f"Customer requirement '{record_id}' not found."}

    prev = rec.get("review_status", "unknown")
    _update_record(_CRM_PATH, record_id, {"review_status": "rejected_not_requirement", "approval_status": "not_approved"})
    decision = _record_decision("customer_requirement_master", record_id, "reject_not_requirement", "rejected", user_id, user_role, prev, "rejected_not_requirement", comment=reason)
    return {"ok": True, "decision": decision, "message": "Customer requirement rejected."}


def mark_requirement_split(record_id: str, user_id: str, user_role: str, reason: str) -> dict:
    perm = check_permission("confirm_customer_requirement", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CRM_PATH, record_id)
    if rec is None:
        return {"ok": False, "error": f"Customer requirement '{record_id}' not found."}

    prev = rec.get("review_status", "unknown")
    _update_record(_CRM_PATH, record_id, {"review_status": "split_required"})
    decision = _record_decision("customer_requirement_master", record_id, "split_requirement", "split_required", user_id, user_role, prev, "split_required", comment=reason)
    return {"ok": True, "decision": decision, "message": "Requirement marked as needing split."}


# ── Controlled Term ──────────────────────────────────────

def confirm_controlled_term(term_id: str, user_id: str, user_role: str, comment: str = "") -> dict:
    perm = check_permission("confirm_controlled_term", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CT_PATH, term_id)
    if rec is None:
        return {"ok": False, "error": f"Controlled term '{term_id}' not found."}

    prev = rec.get("review_status", "unknown")
    _update_record(_CT_PATH, term_id, {"review_status": "term_confirmed"})
    decision = _record_decision("controlled_term", term_id, "confirm_controlled_term", "confirmed", user_id, user_role, prev, "term_confirmed", comment)
    return {"ok": True, "decision": decision, "message": "Controlled term confirmed."}


def reject_controlled_term(term_id: str, user_id: str, user_role: str, reason: str) -> dict:
    perm = check_permission("reject_controlled_term", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_record(_CT_PATH, term_id)
    if rec is None:
        return {"ok": False, "error": f"Controlled term '{term_id}' not found."}

    prev = rec.get("review_status", "unknown")
    _update_record(_CT_PATH, term_id, {"review_status": "rejected_not_term"})
    decision = _record_decision("controlled_term", term_id, "reject_not_term", "rejected", user_id, user_role, prev, "rejected_not_term", comment=reason)
    return {"ok": True, "decision": decision, "message": "Controlled term rejected."}


# ══════════════════════════════════════════════════════════════════
#  List pending records
# ══════════════════════════════════════════════════════════════════

def list_pending(record_type: str, limit: int = 50) -> List[dict]:
    path_map = {
        "source_text": (_STA_PATH, ["extracted_pending_confirmation", "corrected_pending_confirmation"]),
        "customer_requirement": (_CRM_PATH, ["source_text_extracted_pending_confirmation", "source_text_confirmed_pending_requirement_review"]),
        "controlled_term": (_CT_PATH, ["extracted_pending_confirmation"]),
    }
    if record_type not in path_map:
        return []

    path, pending_statuses = path_map[record_type]
    if not os.path.isfile(path):
        return []

    results = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            status = rec.get("review_status", rec.get("confirmation_status", ""))
            if status in pending_statuses:
                results.append({
                    "id": rec.get("id", "?"),
                    "type": record_type,
                    "status": status,
                    "source_id": rec.get("source_id", ""),
                    "page": rec.get("page_number", ""),
                    "preview": str(rec.get("original_text", rec.get("requirement_text", rec.get("term", ""))))[:120],
                })
        except Exception:
            pass

    return results[-limit:]
