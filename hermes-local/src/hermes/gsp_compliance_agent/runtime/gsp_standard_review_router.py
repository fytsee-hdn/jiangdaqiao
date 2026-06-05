"""
gsp_standard_review_router.py — GSP Compliance Agent: C5B GSP Standard Review Router.

Routes structured review commands to gsp_standard_review_workflow functions.
Only allows admin_development_window (no business user exposure).
All actions include "NOT published GSP Standard" warning.
"""

from __future__ import annotations

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

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# ══════════════════════════════════════════════════════════════════
#  Safety: only allowed source windows
# ══════════════════════════════════════════════════════════════════

_ALLOWED_SOURCE_WINDOWS = {"admin_development_window"}
_BUSINESS_WINDOWS_RESERVED = {"compliance_owner_window", "department_compliance_window"}

_STANDARD_WARNING = (
    "⚠️  Confirming a GSP Standard candidate does NOT publish SOP, checklist, "
    "training, legal interpretation, customer overlay, or final business approval."
)


def route_gsp_standard_review_command(
    source_window: str,
    user_id: str,
    user_role: str,
    action: str,
    gsp_standard_id: str = "",
    comment: str = "",
    reason: str = "",
    corrections: Optional[dict] = None,
    merge_target_id: str = "",
    batch_id: str = "",
    status: str = "draft_pending_review",
    limit: int = 20,
) -> dict:
    """Route a GSP standard review command to the workflow.

    Parameters
    ----------
    source_window : must be admin_development_window
    user_id, user_role : from user registry
    action : list_gsp_candidates, confirm_gsp_candidate, correct_gsp_candidate,
             reject_gsp_candidate, mark_gsp_split_required, mark_gsp_merged,
             mark_gsp_needs_legal_review, generate_gsp_review_packet
    gsp_standard_id : target GSP standard candidate ID
    comment, reason, corrections, merge_target_id, batch_id, status, limit : optional
    """
    # ── Safety gate ─────────────────────────────────
    if source_window not in _ALLOWED_SOURCE_WINDOWS:
        if source_window in _BUSINESS_WINDOWS_RESERVED:
            return {
                "ok": False,
                "error": f"Source window '{source_window}' is reserved for future business use. Not active yet.",
                "warning": _STANDARD_WARNING,
            }
        return {
            "ok": False,
            "error": f"Source window '{source_window}' not allowed for GSP standard review workflow.",
        }

    # ── Import workflow ──────────────────────────────
    from hermes.gsp_compliance_agent.runtime.gsp_standard_review_workflow import (
        list_gsp_standard_candidates,
        get_gsp_standard_candidate,
        confirm_gsp_standard_candidate,
        correct_gsp_standard_candidate,
        reject_gsp_standard_candidate,
        mark_gsp_standard_split_required,
        mark_gsp_standard_merged,
        mark_gsp_standard_needs_legal_review,
        archive_gsp_standard_candidate,
        generate_gsp_standard_review_packet,
        check_gsp_review_permission,
    )

    # ── Route actions ─────────────────────────────────

    if action == "list_gsp_candidates":
        result = list_gsp_standard_candidates(
            status=status, limit=limit, user_role=user_role
        )
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "show_gsp_candidate":
        if not gsp_standard_id:
            return {"ok": False, "error": "gsp_standard_id is required."}
        result = get_gsp_standard_candidate(gsp_standard_id, user_role)
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "confirm_gsp_candidate":
        if not gsp_standard_id:
            return {"ok": False, "error": "gsp_standard_id is required."}
        result = confirm_gsp_standard_candidate(
            gsp_standard_id, user_id, user_role, comment=comment or None
        )
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "correct_gsp_candidate":
        if not gsp_standard_id:
            return {"ok": False, "error": "gsp_standard_id is required."}
        if not corrections:
            return {"ok": False, "error": "corrections dict is required for correct action."}
        result = correct_gsp_standard_candidate(
            gsp_standard_id, user_id, user_role, corrections, reason or "No reason provided"
        )
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "reject_gsp_candidate":
        if not gsp_standard_id:
            return {"ok": False, "error": "gsp_standard_id is required."}
        if not reason:
            return {"ok": False, "error": "reason is required for reject."}
        result = reject_gsp_standard_candidate(
            gsp_standard_id, user_id, user_role, reason
        )
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "mark_gsp_split_required":
        if not gsp_standard_id:
            return {"ok": False, "error": "gsp_standard_id is required."}
        if not reason:
            return {"ok": False, "error": "reason is required."}
        result = mark_gsp_standard_split_required(
            gsp_standard_id, user_id, user_role, reason
        )
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "mark_gsp_merged":
        if not gsp_standard_id:
            return {"ok": False, "error": "gsp_standard_id is required."}
        if not merge_target_id:
            return {"ok": False, "error": "merge_target_id is required."}
        if not reason:
            return {"ok": False, "error": "reason is required."}
        result = mark_gsp_standard_merged(
            gsp_standard_id, user_id, user_role, merge_target_id, reason
        )
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "mark_gsp_needs_legal_review":
        if not gsp_standard_id:
            return {"ok": False, "error": "gsp_standard_id is required."}
        if not reason:
            return {"ok": False, "error": "reason is required."}
        result = mark_gsp_standard_needs_legal_review(
            gsp_standard_id, user_id, user_role, reason
        )
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "archive_gsp_candidate":
        if not gsp_standard_id:
            return {"ok": False, "error": "gsp_standard_id is required."}
        if not reason:
            return {"ok": False, "error": "reason is required."}
        result = archive_gsp_standard_candidate(
            gsp_standard_id, user_id, user_role, reason
        )
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "generate_gsp_review_packet":
        result = generate_gsp_standard_review_packet(
            batch_id=batch_id or None, user_role=user_role
        )
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    return {"ok": False, "error": f"Unsupported action '{action}'."}
