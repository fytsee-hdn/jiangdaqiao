"""
checklist_review_router.py — GSP Compliance Agent: C6C Checklist Review Router.

Routes structured review commands to checklist_review_workflow functions.
Only allows admin_development_window (no business user exposure).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Bangkok")
except ImportError:
    pass

_logger = logging.getLogger(__name__)

_ALLOWED_SOURCE_WINDOWS = {"admin_development_window"}
_BUSINESS_WINDOWS_RESERVED = {"compliance_owner_window", "department_compliance_window"}

_STANDARD_WARNING = (
    "⚠️  Confirming a checklist draft does NOT publish SOP, training, department todo, "
    "legal interpretation, customer overlay, or final business approval."
)


def route_checklist_review_command(
    source_window: str,
    user_id: str,
    user_role: str,
    action: str,
    checklist_item_id: str = "",
    comment: str = "",
    reason: str = "",
    corrections: Optional[dict] = None,
    batch_id: str = "",
    status: str = "draft_pending_review",
    limit: int = 20,
) -> dict:
    """Route a checklist review command to the workflow.

    Parameters
    ----------
    source_window : must be admin_development_window
    action : list_checklist_items, show_checklist_item, confirm_checklist_item,
             correct_checklist_item, reject_checklist_item,
             mark_checklist_needs_human_review, mark_checklist_needs_legal_review,
             archive_checklist_item, generate_checklist_review_packet
    """
    if source_window not in _ALLOWED_SOURCE_WINDOWS:
        if source_window in _BUSINESS_WINDOWS_RESERVED:
            return {
                "ok": False,
                "error": f"Source window '{source_window}' is reserved for future business use. Not active yet.",
                "warning": _STANDARD_WARNING,
            }
        return {
            "ok": False,
            "error": f"Source window '{source_window}' not allowed for checklist review workflow.",
        }

    from hermes.gsp_compliance_agent.runtime.checklist_review_workflow import (
        list_checklist_items, get_checklist_item,
        confirm_checklist_item, correct_checklist_item, reject_checklist_item,
        mark_checklist_needs_human_review, mark_checklist_needs_legal_review,
        archive_checklist_item, generate_checklist_review_packet,
    )

    if action == "list_checklist_items":
        result = list_checklist_items(status=status, limit=limit, user_role=user_role)
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "show_checklist_item":
        if not checklist_item_id:
            return {"ok": False, "error": "checklist_item_id is required."}
        result = get_checklist_item(checklist_item_id, user_role)
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "confirm_checklist_item":
        if not checklist_item_id:
            return {"ok": False, "error": "checklist_item_id is required."}
        result = confirm_checklist_item(checklist_item_id, user_id, user_role, comment=comment or None)
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "correct_checklist_item":
        if not checklist_item_id:
            return {"ok": False, "error": "checklist_item_id is required."}
        if not corrections:
            return {"ok": False, "error": "corrections dict is required."}
        result = correct_checklist_item(checklist_item_id, user_id, user_role, corrections, reason or "No reason")
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "reject_checklist_item":
        if not checklist_item_id:
            return {"ok": False, "error": "checklist_item_id is required."}
        if not reason:
            return {"ok": False, "error": "reason is required."}
        result = reject_checklist_item(checklist_item_id, user_id, user_role, reason)
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "mark_checklist_needs_human_review":
        if not checklist_item_id:
            return {"ok": False, "error": "checklist_item_id is required."}
        if not reason:
            return {"ok": False, "error": "reason is required."}
        result = mark_checklist_needs_human_review(checklist_item_id, user_id, user_role, reason)
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "mark_checklist_needs_legal_review":
        if not checklist_item_id:
            return {"ok": False, "error": "checklist_item_id is required."}
        if not reason:
            return {"ok": False, "error": "reason is required."}
        result = mark_checklist_needs_legal_review(checklist_item_id, user_id, user_role, reason)
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "archive_checklist_item":
        if not checklist_item_id:
            return {"ok": False, "error": "checklist_item_id is required."}
        if not reason:
            return {"ok": False, "error": "reason is required."}
        result = archive_checklist_item(checklist_item_id, user_id, user_role, reason)
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    if action == "generate_checklist_review_packet":
        result = generate_checklist_review_packet(batch_id=batch_id or None, user_role=user_role)
        if result.get("ok"):
            result["warning"] = _STANDARD_WARNING
        return result

    return {"ok": False, "error": f"Unsupported action '{action}'."}
