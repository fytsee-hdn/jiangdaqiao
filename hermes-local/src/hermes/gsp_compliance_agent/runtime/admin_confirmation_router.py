"""
admin_confirmation_router.py — GSP Compliance Agent: Admin Confirmation Command Router.

Routes structured admin/development commands to confirmation_workflow functions.
Only allows admin_development_window (no business user exposure).
All confirmations include "NOT GSP standard approval" warning.
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
_REVIEW_PACKETS_DIR = os.path.join(_ROOT, "data", "knowledge", "compliance", "review_packets")

# ══════════════════════════════════════════════════════════════════
#  Safety: only allowed source windows
# ══════════════════════════════════════════════════════════════════

_ALLOWED_SOURCE_WINDOWS = {"admin_development_window"}
_BUSINESS_WINDOWS_RESERVED = {"compliance_owner_window", "department_compliance_window"}

_STANDARD_WARNING = (
    "⚠️  This confirmation does NOT approve GSP Standard, SOP, checklist, "
    "training, customer overlay, or legal interpretation."
)


def _now() -> str:
    return datetime.now(_TZ).isoformat()


def _uid(pref: str) -> str:
    return f"{pref}-{uuid.uuid4().hex[:8].upper()}"


# ══════════════════════════════════════════════════════════════════
#  Router
# ══════════════════════════════════════════════════════════════════

def route_confirmation_command(
    source_window: str,
    user_id: str,
    user_role: str,
    action: str,
    record_type: str = "",
    record_id: str = "",
    comment: str = "",
    reason: str = "",
    correction_text: str = "",
    merge_target_id: str = "",
) -> dict:
    """Route a structured admin confirmation command to the workflow.

    Parameters
    ----------
    source_window : must be admin_development_window
    user_id, user_role : from user registry
    action : list_pending, confirm, correct, reject, split, merge, generate_packet
    record_type : source_text, customer_requirement, controlled_term
    record_id : target record ID
    comment, reason, correction_text, merge_target_id : optional
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
            "error": f"Source window '{source_window}' not allowed for confirmation workflow.",
        }

    # ── Route ───────────────────────────────────────
    from hermes.gsp_compliance_agent.runtime.confirmation_workflow import (
        list_pending, confirm_source_text, correct_source_text, reject_source_text,
        confirm_customer_requirement, reject_customer_requirement,
        confirm_controlled_term, reject_controlled_term,
        mark_requirement_split, check_permission,
    )

    # List pending
    if action == "list_pending":
        if record_type not in ("source_text", "customer_requirement", "controlled_term"):
            return {"ok": False, "error": f"Invalid record_type '{record_type}'."}
        records = list_pending(record_type)
        return {
            "ok": True,
            "action": "list_pending",
            "record_type": record_type,
            "count": len(records),
            "records": records,
            "allowed_actions": _allowed_actions_for_type(record_type),
            "warning": _STANDARD_WARNING,
        }

    # Generate review packet
    if action == "generate_packet":
        return _generate_review_packet(record_type)

    # Confirmation/correction/rejection actions
    if not record_id:
        return {"ok": False, "error": "record_id is required for this action."}

    action_map = _build_action_map(record_type, record_id, user_id, user_role, comment, reason, correction_text, merge_target_id)
    fn = action_map.get((record_type, action))
    if fn is None:
        return {"ok": False, "error": f"Unsupported action '{action}' for type '{record_type}'."}

    result = fn()
    if result.get("ok"):
        result["warning"] = _STANDARD_WARNING
    return result


def _build_action_map(record_type, record_id, user_id, user_role, comment, reason, correction_text, merge_target_id):
    from hermes.gsp_compliance_agent.runtime.confirmation_workflow import (
        confirm_source_text as cst, correct_source_text as corst, reject_source_text as rst,
        confirm_customer_requirement as ccr, reject_customer_requirement as rcr,
        confirm_controlled_term as cct, reject_controlled_term as rct,
        mark_requirement_split as mrs,
    )
    return {
        ("source_text", "confirm"): lambda: cst(record_id, user_id, user_role, comment),
        ("source_text", "correct"): lambda: corst(record_id, user_id, user_role, correction_text, reason),
        ("source_text", "reject"): lambda: rst(record_id, user_id, user_role, reason),
        ("customer_requirement", "confirm"): lambda: ccr(record_id, user_id, user_role, comment),
        ("customer_requirement", "reject"): lambda: rcr(record_id, user_id, user_role, reason),
        ("customer_requirement", "split"): lambda: mrs(record_id, user_id, user_role, reason),
        ("controlled_term", "confirm"): lambda: cct(record_id, user_id, user_role, comment),
        ("controlled_term", "reject"): lambda: rct(record_id, user_id, user_role, reason),
    }


def _allowed_actions_for_type(record_type: str) -> List[str]:
    base = {
        "source_text": ["confirm_source_text", "correct_source_text", "reject_source_text"],
        "customer_requirement": ["confirm_customer_requirement", "reject_customer_requirement", "mark_requirement_split_required"],
        "controlled_term": ["confirm_controlled_term", "reject_controlled_term"],
    }
    return base.get(record_type, []) + ["generate_review_packet"]


# ══════════════════════════════════════════════════════════════════
#  Review packet generator
# ══════════════════════════════════════════════════════════════════

def _generate_review_packet(record_type: str = "combined") -> dict:
    from hermes.gsp_compliance_agent.runtime.confirmation_workflow import list_pending

    types_to_include = ["source_text", "customer_requirement", "controlled_term"] if record_type == "combined" else [record_type]
    os.makedirs(_REVIEW_PACKETS_DIR, exist_ok=True)

    run_id = _uid("PKT")
    lines = [
        "# Compliance Review Packet",
        f"",
        f"**Packet ID:** {run_id}",
        f"**Generated:** {_now()}",
    ]

    total = 0
    for rt in types_to_include:
        pending = list_pending(rt)
        total += len(pending)
        lines.append(f"")
        lines.append(f"## {rt.replace('_', ' ').title()} ({len(pending)} pending)")
        lines.append(f"")
        for r in pending[:30]:
            lines.append(f"- **{r['id']}** [{r['status']}] — {r.get('preview', '')[:100]}")
        if len(pending) > 30:
            lines.append(f"- ... and {len(pending) - 30} more")

    lines.extend([
        "",
        "## ⚠️ IMPORTANT",
        "",
        _STANDARD_WARNING,
    ])

    path = os.path.join(_REVIEW_PACKETS_DIR, f"review_packet_{run_id}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {
        "ok": True,
        "action": "generate_packet",
        "packet_id": run_id,
        "path": path,
        "total_pending": total,
        "by_type": {rt: len(list_pending(rt)) for rt in types_to_include},
        "warning": _STANDARD_WARNING,
    }


# ══════════════════════════════════════════════════════════════════
#  LLM intent contract (sample intents for future LLM integration)
# ══════════════════════════════════════════════════════════════════

LLM_INTENT_CONTRACT = {
    "description": "Admin confirmation intents for LLM-assisted interpretation.",
    "active": False,  # Not connected to live LLM yet
    "intents": [
        {
            "intent": "list_pending_source_text",
            "action": "list_pending", "record_type": "source_text",
            "example_phrases": ["列出待确认的source text", "哪些原文还没确认", "show pending source texts"],
        },
        {
            "intent": "list_pending_customer_requirements",
            "action": "list_pending", "record_type": "customer_requirement",
            "example_phrases": ["列出待确认的IWAY条款", "哪些条款还没审核", "list pending requirements"],
        },
        {
            "intent": "list_pending_controlled_terms",
            "action": "list_pending", "record_type": "controlled_term",
            "example_phrases": ["列出待确认的术语", "show pending terms"],
        },
        {
            "intent": "confirm_source_text",
            "action": "confirm", "record_type": "source_text",
            "example_phrases": ["确认这条source text", "这条原文没问题", "confirm this source text"],
        },
        {
            "intent": "reject_customer_requirement",
            "action": "reject", "record_type": "customer_requirement",
            "example_phrases": ["驳回这条条款", "这条不是IWAY条款", "reject this requirement"],
        },
        {
            "intent": "generate_review_packet",
            "action": "generate_packet", "record_type": "combined",
            "example_phrases": ["生成review packet", "生成审核报告", "generate review packet"],
        },
    ],
}
