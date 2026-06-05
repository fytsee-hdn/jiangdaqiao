"""
checklist_query_router.py — GSP Compliance Agent: C6D Checklist Query Router.

Routes read-only checklist query commands to the query engine.
Only allows admin_development_window.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)

_ALLOWED_SOURCE_WINDOWS = {"admin_development_window"}
_BUSINESS_WINDOWS_RESERVED = {"compliance_owner_window", "department_compliance_window"}

_STANDARD_WARNING = (
    "⚠️  These are draft checklist items. They do NOT publish SOP, training, "
    "legal interpretation, or customer overlay."
)


def route_checklist_query(
    source_window: str,
    action: str,
    gsp_standard_id: str = "",
    customer_requirement_id: str = "",
    checklist_item_id: str = "",
    department: str = "",
    function: str = "",
    message: str = "",
    user_role: str = "compliance_owner",
) -> dict:
    """Route a read-only checklist query to the query engine.

    Parameters
    ----------
    source_window : must be admin_development_window
    action : query_checklist, query_checklist_by_gsp_standard,
             query_checklist_by_customer_requirement, query_checklist_by_department,
             query_checklist_traceability, query_checklist_evidence,
             summarize_checklists, ask_checklist_query
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
            "error": f"Source window '{source_window}' not allowed.",
        }

    from hermes.gsp_compliance_agent.runtime.checklist_query_engine import (
        query_checklist_by_gsp_standard,
        query_checklist_by_customer_requirement,
        query_checklist_by_department,
        query_checklist_by_function,
        get_checklist_item_traceability,
        get_checklist_item_evidence,
        summarize_checklist_results,
        parse_checklist_query_intent,
        format_checklist_response,
    )

    if action == "query_checklist_by_gsp_standard":
        if not gsp_standard_id:
            return {"ok": False, "error": "gsp_standard_id is required."}
        result = query_checklist_by_gsp_standard(gsp_standard_id)
    elif action == "query_checklist_by_customer_requirement":
        if not customer_requirement_id:
            return {"ok": False, "error": "customer_requirement_id is required."}
        result = query_checklist_by_customer_requirement(customer_requirement_id)
    elif action == "query_checklist_by_department":
        if not department:
            return {"ok": False, "error": "department is required."}
        result = query_checklist_by_department(department)
    elif action == "query_checklist_by_function":
        if not function:
            return {"ok": False, "error": "function is required."}
        result = query_checklist_by_function(function)
    elif action == "query_checklist_traceability":
        if not checklist_item_id:
            return {"ok": False, "error": "checklist_item_id is required."}
        result = get_checklist_item_traceability(checklist_item_id)
    elif action == "query_checklist_evidence":
        if not checklist_item_id:
            return {"ok": False, "error": "checklist_item_id is required."}
        result = get_checklist_item_evidence(checklist_item_id)
    elif action == "summarize_checklists":
        result = summarize_checklist_results()
    elif action == "ask_checklist_query":
        if not message:
            return {"ok": False, "error": "message is required."}
        intent = parse_checklist_query_intent(message, mock=True)
        if intent["needs_clarification"]:
            return {
                "ok": True,
                "needs_clarification": True,
                "clarification_question": intent["clarification_question"],
                "intent": intent,
            }
        return _route_by_intent(intent, result_formatter=format_checklist_response)
    else:
        return {"ok": False, "error": f"Unsupported action '{action}'."}

    if result.get("ok"):
        result["warning"] = _STANDARD_WARNING
    return result


def _route_by_intent(intent: dict, result_formatter=None) -> dict:
    """Route based on parsed intent."""
    filters = intent.get("filters", {})
    qtype = intent.get("query_intent", "")

    from hermes.gsp_compliance_agent.runtime.checklist_query_engine import (
        query_checklist_by_gsp_standard,
        query_checklist_by_customer_requirement,
        query_checklist_by_department,
        query_checklist_by_function,
        get_checklist_item_traceability,
        get_checklist_item_evidence,
        summarize_checklist_results,
        format_checklist_response,
    )

    if qtype == "checklist_by_gsp_standard" and filters.get("gsp_standard_id"):
        result = query_checklist_by_gsp_standard(filters["gsp_standard_id"])
    elif qtype == "checklist_by_customer_requirement" and filters.get("customer_requirement_id"):
        result = query_checklist_by_customer_requirement(filters["customer_requirement_id"])
    elif qtype == "checklist_by_department" and filters.get("department"):
        result = query_checklist_by_department(filters["department"])
    elif qtype == "checklist_by_function" and filters.get("function"):
        result = query_checklist_by_function(filters["function"])
    elif qtype == "checklist_item_traceability" and filters.get("checklist_item_id"):
        result = get_checklist_item_traceability(filters["checklist_item_id"])
    elif qtype == "checklist_item_evidence" and filters.get("checklist_item_id"):
        result = get_checklist_item_evidence(filters["checklist_item_id"])
    elif qtype == "checklist_summary":
        result = summarize_checklist_results()
    else:
        result = summarize_checklist_results()
        result["warning"] = "Showing all checklist summaries. Use a more specific query to filter."

    if result.get("ok"):
        result["warning"] = _STANDARD_WARNING
        result["chat_response"] = format_checklist_response(result)
    return result
