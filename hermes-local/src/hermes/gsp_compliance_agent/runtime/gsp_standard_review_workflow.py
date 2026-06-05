"""
gsp_standard_review_workflow.py — GSP Compliance Agent: C5B GSP Standard Candidate Review.

Supports structured review of GSP Standard candidates derived via C5A.

Review actions:
- confirm_gsp_standard_candidate
- correct_gsp_standard_candidate
- reject_gsp_standard_candidate
- mark_gsp_standard_split_required
- mark_gsp_standard_merged
- mark_gsp_standard_needs_legal_review
- archive_gsp_standard_candidate

Key rules:
- Confirming does NOT publish SOP/checklist/training/legal interpretation
- Confirming does NOT approve customer overlay
- All actions require permission checks
- All actions write review_decision + audit log
- No action generates downstream content (SOP/checklist/training/mapping)
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
_GSP_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "gsp_standards", "gsp_core_standard.jsonl")
_DECISIONS_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "review_decisions", "review_decisions.jsonl")
_AUDIT_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "review_decisions", "review_audit.jsonl")
_PACKETS_DIR = os.path.join(_ROOT, "data", "knowledge", "compliance", "review_packets")

# ══════════════════════════════════════════════════════════════════
#  Valid status values
# ══════════════════════════════════════════════════════════════════

_VALID_REVIEW_STATUSES = {
    "draft_pending_review",
    "review_in_progress",
    "confirmed_for_internal_standard",
    "correction_required",
    "rejected",
    "split_required",
    "merged_with_other_standard",
    "needs_legal_review",
    "archived",
    "superseded",
}

# ══════════════════════════════════════════════════════════════════
#  Permission model
# ══════════════════════════════════════════════════════════════════

_REQUIRED_PERMISSIONS = {
    "list_gsp_standard_candidates": ["list_gsp_standard_candidates"],
    "review_gsp_standard_candidate": ["review_gsp_standard_candidate"],
    "correct_gsp_standard_candidate": ["correct_gsp_standard_candidate"],
    "reject_gsp_standard_candidate": ["reject_gsp_standard_candidate"],
    "mark_gsp_standard_needs_legal_review": ["mark_gsp_standard_needs_legal_review"],
    "archive_gsp_standard_candidate": ["archive_gsp_standard_candidate"],
}

_ROLE_PERMISSIONS = {
    "compliance_owner": [
        "list_gsp_standard_candidates",
        "review_gsp_standard_candidate",
        "correct_gsp_standard_candidate",
        "reject_gsp_standard_candidate",
        "mark_gsp_standard_needs_legal_review",
        "archive_gsp_standard_candidate",
    ],
    "owner": [
        "list_gsp_standard_candidates",
        "review_gsp_standard_candidate",
        "correct_gsp_standard_candidate",
        "reject_gsp_standard_candidate",
        "mark_gsp_standard_needs_legal_review",
        "archive_gsp_standard_candidate",
    ],
    "admin_developer": [
        "list_gsp_standard_candidates",
        "review_gsp_standard_candidate",
        "correct_gsp_standard_candidate",
        "reject_gsp_standard_candidate",
        "mark_gsp_standard_needs_legal_review",
        "archive_gsp_standard_candidate",
    ],
    "admin": [],
    "department_owner": [],
    "employee": [],
}


def check_gsp_review_permission(action: str, user_role: str) -> dict:
    """Check if a role has the required permission."""
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


def _find_gsp_record(gsp_standard_id: str) -> Optional[dict]:
    """Find a GSP standard candidate by its gsp_standard_id or id field."""
    if not os.path.isfile(_GSP_PATH):
        return None
    for line in open(_GSP_PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("gsp_standard_id") == gsp_standard_id or rec.get("id") == gsp_standard_id:
                return rec
        except json.JSONDecodeError:
            pass
    return None


def _update_gsp_record(gsp_standard_id: str, updates: dict) -> bool:
    """Update a GSP standard candidate record. Rewrites entire file."""
    if not os.path.isfile(_GSP_PATH):
        return False
    lines = []
    found = False
    for line in open(_GSP_PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            lines.append("")
            continue
        try:
            rec = json.loads(line)
            if rec.get("gsp_standard_id") == gsp_standard_id or rec.get("id") == gsp_standard_id:
                rec.update(updates)
                rec["updated_at"] = _now()
                found = True
            lines.append(json.dumps(rec, ensure_ascii=False))
        except json.JSONDecodeError:
            lines.append(line)
    if found:
        with open(_GSP_PATH, "w", encoding="utf-8") as f:
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
    split_reason: str = "",
    merge_target_id: str = "",
    archive_reason: str = "",
) -> dict:
    """Write a review_decision record and audit entry for GSP standard candidates."""
    dec_id = _uid("RD")
    audit_id = _uid("AUDIT")
    now = _now()

    decision = {
        "review_decision_id": dec_id,
        "version": 1,
        "target_record_type": "gsp_core_standard",
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
        "split_reason": split_reason,
        "merge_target_id": merge_target_id,
        "archive_reason": archive_reason,
        "audit_log_id": audit_id,
        "created_at": now,
    }
    _append_jsonl(_DECISIONS_PATH, decision)

    audit = {
        "audit_log_id": audit_id,
        "timestamp": now,
        "user_id_hash": _hash(user_id),
        "action": decision_type,
        "target_record_type": "gsp_core_standard",
        "target_record_id": target_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "result": decision_result,
        "comment_present": bool(comment),
        "created_at": now,
    }
    _append_jsonl(_AUDIT_PATH, audit)

    _logger.info(
        "GSP review decision %s: %s %s -> %s by %s",
        dec_id, target_id, previous_status, new_status, _hash(user_id),
    )
    return decision


# ══════════════════════════════════════════════════════════════════
#  Core review functions
# ══════════════════════════════════════════════════════════════════


def list_gsp_standard_candidates(
    status: str = "draft_pending_review",
    limit: int = 20,
    user_role: str = "compliance_owner",
) -> dict:
    """List GSP standard candidates with a given review status.

    Returns dict with: ok, count, candidates, warning.
    """
    perm = check_gsp_review_permission("list_gsp_standard_candidates", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    if not os.path.isfile(_GSP_PATH):
        return {"ok": True, "count": 0, "candidates": [], "warning": "No GSP standard candidates file found."}

    results = []
    for line in open(_GSP_PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            rs = rec.get("review_status", "")
            if rs == status or status == "all":
                results.append({
                    "gsp_standard_id": rec.get("gsp_standard_id", ""),
                    "id": rec.get("id", ""),
                    "title": rec.get("title", ""),
                    "gsp_principle": rec.get("gsp_principle", ""),
                    "gsp_domain": rec.get("gsp_domain", ""),
                    "review_status": rs,
                    "approval_status": rec.get("approval_status", "not_approved"),
                    "statement_preview": str(rec.get("requirement_statement", ""))[:120],
                    "source_customer_requirement_links": rec.get("source_customer_requirement_links", []),
                    "derivation_batch_id": rec.get("derivation_batch_id", ""),
                    "sample_only": rec.get("notes", "").startswith("Derived from CRM"),
                })
        except json.JSONDecodeError:
            pass

    results = results[-limit:]
    return {
        "ok": True,
        "count": len(results),
        "candidates": results,
        "warning": "Confirmation does NOT publish SOP/checklist/training/legal interpretation.",
    }


def get_gsp_standard_candidate(
    gsp_standard_id: str,
    user_role: str = "compliance_owner",
) -> dict:
    """Get a single GSP standard candidate by ID."""
    perm = check_gsp_review_permission("list_gsp_standard_candidates", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_gsp_record(gsp_standard_id)
    if rec is None:
        return {"ok": False, "error": f"GSP standard candidate '{gsp_standard_id}' not found."}

    return {"ok": True, "candidate": rec}


def confirm_gsp_standard_candidate(
    gsp_standard_id: str,
    user_id: str,
    user_role: str = "compliance_owner",
    comment: Optional[str] = None,
) -> dict:
    """Confirm a GSP standard candidate for internal standard layer review.

    Confirming means internal acceptance as a correctly drafted GSP standard.
    Does NOT publish SOP/checklist/training/legal interpretation/customer overlay.
    """
    perm = check_gsp_review_permission("review_gsp_standard_candidate", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_gsp_record(gsp_standard_id)
    if rec is None:
        return {"ok": False, "error": f"GSP standard candidate '{gsp_standard_id}' not found."}

    prev = rec.get("review_status", "unknown")
    if prev == "confirmed_for_internal_standard":
        return {"ok": False, "error": f"GSP standard candidate '{gsp_standard_id}' is already confirmed."}

    new_status = "confirmed_for_internal_standard"
    updated = _update_gsp_record(gsp_standard_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{gsp_standard_id}'."}

    decision = _record_decision(
        gsp_standard_id,
        "confirm_gsp_standard_candidate",
        "confirmed",
        user_id, user_role, prev, new_status,
        comment=comment or "",
    )
    return {
        "ok": True,
        "decision": decision,
        "message": (
            f"GSP standard candidate '{gsp_standard_id}' confirmed for internal standard review. "
            "This does NOT publish SOP, checklist, training, legal interpretation, "
            "customer overlay, or final business approval."
        ),
    }


def correct_gsp_standard_candidate(
    gsp_standard_id: str,
    user_id: str,
    user_role: str,
    corrections: dict,
    reason: str,
) -> dict:
    """Correct text/metadata of a GSP standard candidate.

    corrections dict can include:
    - requirement_statement (new statement text)
    - title (new title)
    - gsp_principle (new principle code)
    - gsp_domain (new domain code)
    """
    perm = check_gsp_review_permission("correct_gsp_standard_candidate", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_gsp_record(gsp_standard_id)
    if rec is None:
        return {"ok": False, "error": f"GSP standard candidate '{gsp_standard_id}' not found."}

    prev = rec.get("review_status", "unknown")

    # Apply corrections to fields
    corrections_to_apply = {}
    for field in ("requirement_statement", "title", "gsp_principle", "gsp_domain",
                  "normative_force", "is_critical", "gsp_applicability"):
        if field in corrections:
            corrections_to_apply[field] = corrections[field]

    corrections_to_apply["review_status"] = "correction_required"
    corrections_to_apply["approval_status"] = "not_approved"

    updated = _update_gsp_record(gsp_standard_id, corrections_to_apply)
    if not updated:
        return {"ok": False, "error": f"Failed to update '{gsp_standard_id}'."}

    decision = _record_decision(
        gsp_standard_id,
        "correct_gsp_standard_candidate",
        "corrected",
        user_id, user_role, prev, "correction_required",
        correction_text=json.dumps(corrections_to_apply, ensure_ascii=False),
        correction_reason=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"GSP standard candidate '{gsp_standard_id}' corrected. Status set to correction_required.",
    }


def reject_gsp_standard_candidate(
    gsp_standard_id: str,
    user_id: str,
    user_role: str,
    reason: str,
) -> dict:
    """Reject a GSP standard candidate."""
    perm = check_gsp_review_permission("reject_gsp_standard_candidate", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_gsp_record(gsp_standard_id)
    if rec is None:
        return {"ok": False, "error": f"GSP standard candidate '{gsp_standard_id}' not found."}

    prev = rec.get("review_status", "unknown")
    new_status = "rejected"

    updated = _update_gsp_record(gsp_standard_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{gsp_standard_id}'."}

    decision = _record_decision(
        gsp_standard_id,
        "reject_gsp_standard_candidate",
        "rejected",
        user_id, user_role, prev, new_status,
        comment=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"GSP standard candidate '{gsp_standard_id}' rejected.",
    }


def mark_gsp_standard_split_required(
    gsp_standard_id: str,
    user_id: str,
    user_role: str,
    reason: str,
) -> dict:
    """Mark a GSP standard candidate as needing to be split into multiple records."""
    perm = check_gsp_review_permission("review_gsp_standard_candidate", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_gsp_record(gsp_standard_id)
    if rec is None:
        return {"ok": False, "error": f"GSP standard candidate '{gsp_standard_id}' not found."}

    prev = rec.get("review_status", "unknown")
    new_status = "split_required"

    updated = _update_gsp_record(gsp_standard_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{gsp_standard_id}'."}

    decision = _record_decision(
        gsp_standard_id,
        "mark_gsp_standard_split_required",
        "split_required",
        user_id, user_role, prev, new_status,
        split_reason=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"GSP standard candidate '{gsp_standard_id}' marked as split_required.",
    }


def mark_gsp_standard_merged(
    gsp_standard_id: str,
    user_id: str,
    user_role: str,
    merge_target_id: str,
    reason: str,
) -> dict:
    """Mark a GSP standard candidate as merged with another standard."""
    perm = check_gsp_review_permission("review_gsp_standard_candidate", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_gsp_record(gsp_standard_id)
    if rec is None:
        return {"ok": False, "error": f"GSP standard candidate '{gsp_standard_id}' not found."}

    # Verify merge target exists
    target = _find_gsp_record(merge_target_id)
    if target is None:
        return {"ok": False, "error": f"Merge target '{merge_target_id}' not found."}

    prev = rec.get("review_status", "unknown")
    new_status = "merged_with_other_standard"

    updated = _update_gsp_record(gsp_standard_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{gsp_standard_id}'."}

    decision = _record_decision(
        gsp_standard_id,
        "mark_gsp_standard_merged",
        "merged",
        user_id, user_role, prev, new_status,
        merge_target_id=merge_target_id,
        correction_reason=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"GSP standard candidate '{gsp_standard_id}' marked as merged with '{merge_target_id}'.",
    }


def mark_gsp_standard_needs_legal_review(
    gsp_standard_id: str,
    user_id: str,
    user_role: str,
    reason: str,
) -> dict:
    """Mark a GSP standard candidate as needing legal review."""
    perm = check_gsp_review_permission("mark_gsp_standard_needs_legal_review", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_gsp_record(gsp_standard_id)
    if rec is None:
        return {"ok": False, "error": f"GSP standard candidate '{gsp_standard_id}' not found."}

    prev = rec.get("review_status", "unknown")
    new_status = "needs_legal_review"

    updated = _update_gsp_record(gsp_standard_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{gsp_standard_id}'."}

    decision = _record_decision(
        gsp_standard_id,
        "mark_gsp_standard_needs_legal_review",
        "needs_legal_review",
        user_id, user_role, prev, new_status,
        comment=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"GSP standard candidate '{gsp_standard_id}' marked as needs_legal_review.",
    }


def archive_gsp_standard_candidate(
    gsp_standard_id: str,
    user_id: str,
    user_role: str,
    reason: str,
) -> dict:
    """Archive a GSP standard candidate."""
    perm = check_gsp_review_permission("archive_gsp_standard_candidate", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    rec = _find_gsp_record(gsp_standard_id)
    if rec is None:
        return {"ok": False, "error": f"GSP standard candidate '{gsp_standard_id}' not found."}

    prev = rec.get("review_status", "unknown")
    new_status = "archived"

    updated = _update_gsp_record(gsp_standard_id, {
        "review_status": new_status,
        "approval_status": "not_approved",
    })
    if not updated:
        return {"ok": False, "error": f"Failed to update '{gsp_standard_id}'."}

    decision = _record_decision(
        gsp_standard_id,
        "archive_gsp_standard_candidate",
        "archived",
        user_id, user_role, prev, new_status,
        archive_reason=reason,
    )
    return {
        "ok": True,
        "decision": decision,
        "message": f"GSP standard candidate '{gsp_standard_id}' archived.",
    }


# ══════════════════════════════════════════════════════════════════
#  Review packet generation
# ══════════════════════════════════════════════════════════════════


def generate_gsp_standard_review_packet(
    batch_id: Optional[str] = None,
    user_role: str = "compliance_owner",
) -> dict:
    """Generate a GSP standard review packet as a markdown report.

    Lists all GSP standard candidates grouped by status with a
    no-downstream-approval warning.
    """
    perm = check_gsp_review_permission("list_gsp_standard_candidates", user_role)
    if not perm["allowed"]:
        return {"ok": False, "error": perm["reason"]}

    if not os.path.isfile(_GSP_PATH):
        return {"ok": True, "count": 0, "path": None, "warning": "No GSP candidates file."}

    # Load all candidates
    all_candidates: List[dict] = []
    for line in open(_GSP_PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            # Filter by derivation_batch_id if specified
            if batch_id:
                if rec.get("derivation_batch_id") != batch_id:
                    continue
            all_candidates.append(rec)
        except json.JSONDecodeError:
            pass

    # Build counts
    status_counts: Dict[str, int] = {}
    principle_counts: Dict[str, int] = {}
    domain_counts: Dict[str, int] = {}
    for rec in all_candidates:
        rs = rec.get("review_status", "unknown")
        status_counts[rs] = status_counts.get(rs, 0) + 1
        p = rec.get("gsp_principle", "PXX")
        principle_counts[p] = principle_counts.get(p, 0) + 1
        d = rec.get("gsp_domain", "REV")
        domain_counts[d] = domain_counts.get(d, 0) + 1

    os.makedirs(_PACKETS_DIR, exist_ok=True)
    ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")
    run_id = _uid("C5B")
    path = os.path.join(_PACKETS_DIR, f"c5b_gsp_standard_review_packet_{ts}.md")

    lines = [
        "# C5B GSP Standard Review Packet",
        "",
        f"**Packet ID:** {run_id}",
        f"**Generated:** {_now()}",
        f"**Batch ID:** {batch_id or 'all'}",
        "",
        "---",
        "",
        "## Overview",
        "",
        f"- **Total candidates:** {len(all_candidates)}",
        f"- **Status breakdown:**",
    ]
    for s in sorted(status_counts.keys()):
        lines.append(f"  - {s}: {status_counts[s]}")
    lines.append("")
    lines.append(f"- **By Principle:**")
    for p in sorted(principle_counts.keys()):
        lines.append(f"  - {p}: {principle_counts[p]}")
    lines.append("")
    lines.append(f"- **By Domain:**")
    for d in sorted(domain_counts.keys()):
        lines.append(f"  - {d}: {domain_counts[d]}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Candidate Details")
    lines.append("")

    for rec in all_candidates:
        gsp_id = rec.get("gsp_standard_id", "?")
        principle = rec.get("gsp_principle", "?")
        domain = rec.get("gsp_domain", "?")
        statement = str(rec.get("requirement_statement", ""))[:200]
        review_status = rec.get("review_status", "unknown")
        approval_status = rec.get("approval_status", "not_approved")
        links = rec.get("source_customer_requirement_links", [])
        crm_ids = [l.get("crm_id", "?") for l in links]

        # Determine allowed actions based on current status
        allowed = _allowed_actions_for_status(review_status)

        lines.append(f"### {gsp_id}")
        lines.append(f"")
        lines.append(f"- **Principle:** {principle}")
        lines.append(f"- **Domain:** {domain}")
        lines.append(f"- **Review Status:** {review_status}")
        lines.append(f"- **Approval Status:** {approval_status}")
        lines.append(f"- **Statement:** {statement}")
        lines.append(f"- **Source CRM IDs:** {', '.join(crm_ids) if crm_ids else 'none'}")
        lines.append(f"- **Allowed Actions:** {', '.join(allowed) if allowed else 'none'}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## ⚠️ IMPORTANT WARNING",
        "",
        "Confirming a GSP Standard candidate does NOT publish SOP, ",
        "checklist, training, legal interpretation, customer overlay, ",
        "or final business approval.",
        "",
        "All candidates remain draft or confirmed_internal only.",
        "They are NOT approved/published GSP Standards.",
    ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return {
        "ok": True,
        "packet_id": run_id,
        "path": path,
        "total_candidates": len(all_candidates),
        "by_status": status_counts,
        "by_principle": principle_counts,
        "by_domain": domain_counts,
        "warning": "Confirming does NOT publish SOP, checklist, training, legal interpretation.",
    }


def _allowed_actions_for_status(status: str) -> List[str]:
    """Return allowed actions based on current review status."""
    base = {
        "draft_pending_review": [
            "confirm_gsp_standard_candidate",
            "correct_gsp_standard_candidate",
            "reject_gsp_standard_candidate",
            "mark_gsp_standard_split_required",
            "mark_gsp_standard_merged",
            "mark_gsp_standard_needs_legal_review",
            "archive_gsp_standard_candidate",
        ],
        "review_in_progress": [
            "confirm_gsp_standard_candidate",
            "correct_gsp_standard_candidate",
            "reject_gsp_standard_candidate",
            "mark_gsp_standard_split_required",
            "mark_gsp_standard_merged",
            "mark_gsp_standard_needs_legal_review",
            "archive_gsp_standard_candidate",
        ],
        "confirmed_for_internal_standard": [
            "correct_gsp_standard_candidate",
            "reject_gsp_standard_candidate",
            "archive_gsp_standard_candidate",
        ],
        "correction_required": [
            "confirm_gsp_standard_candidate",
            "correct_gsp_standard_candidate",
            "reject_gsp_standard_candidate",
            "archive_gsp_standard_candidate",
        ],
        "rejected": ["archive_gsp_standard_candidate"],
        "split_required": ["archive_gsp_standard_candidate"],
        "merged_with_other_standard": ["archive_gsp_standard_candidate"],
        "needs_legal_review": [
            "confirm_gsp_standard_candidate",
            "correct_gsp_standard_candidate",
            "reject_gsp_standard_candidate",
            "archive_gsp_standard_candidate",
        ],
        "archived": [],
        "superseded": [],
    }
    return base.get(status, [])
