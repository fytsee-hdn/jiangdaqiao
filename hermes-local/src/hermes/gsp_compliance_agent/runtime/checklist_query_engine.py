"""
checklist_query_engine.py — GSP Compliance Agent: C6D Checklist Query and Traceability.

Read-only query functions for department checklist items, linked GSP standards,
customer requirements, and evidence records. No writes, no status changes.

Uses compliance_data_paths for data root resolution (supports GSP_COMPLIANCE_DATA_ROOT env var).
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from hermes.gsp_compliance_agent.runtime.compliance_data_paths import (
    gsp_standards_path,
    evidence_matrix_path,
    checklists_path,
    crm_path,
)

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Bangkok")
except ImportError:
    _TZ = timezone(timedelta(hours=7))

_logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  Paths (resolved via compliance_data_paths for profile isolation)
# ══════════════════════════════════════════════════════════════════

_CHECKLIST_PATH = checklists_path()
_GSP_PATH = gsp_standards_path()
_EVIDENCE_PATH = evidence_matrix_path()
_CRM_PATH = crm_path()
_SAMPLE_CRM_PATH = os.path.join(
    os.path.dirname(os.path.dirname(crm_path())),
    "sample_records", "c5a_sample_crm_fixtures.jsonl"
)


# ══════════════════════════════════════════════════════════════════
#  Data loaders
# ══════════════════════════════════════════════════════════════════


def _load_jsonl(path: str) -> List[dict]:
    if not os.path.isfile(path):
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def load_checklist_records() -> List[dict]:
    return _load_jsonl(_CHECKLIST_PATH)


def load_gsp_standard_records() -> List[dict]:
    return _load_jsonl(_GSP_PATH)


def load_customer_requirement_records() -> List[dict]:
    records = _load_jsonl(_CRM_PATH)
    records.extend(_load_jsonl(_SAMPLE_CRM_PATH))
    return records


def load_evidence_records() -> List[dict]:
    return _load_jsonl(_EVIDENCE_PATH)


# ══════════════════════════════════════════════════════════════════
#  Query by GSP standard, CRM, department, function
# ══════════════════════════════════════════════════════════════════


def query_checklist_by_gsp_standard(gsp_standard_id: str) -> dict:
    all_items = load_checklist_records()
    matched = [i for i in all_items
               if i.get("linked_gsp_standard_id") == gsp_standard_id]

    if not matched:
        return {
            "ok": True, "count": 0, "items": [],
            "warning": f"No checklist items found for GSP standard '{gsp_standard_id}'.",
        }

    gsp_records = load_gsp_standard_records()
    gsp = next((g for g in gsp_records
                if g.get("gsp_standard_id") == gsp_standard_id), None)

    return {
        "ok": True,
        "count": len(matched),
        "items": [_format_item(i) for i in matched],
        "linked_gsp_standard": {
            "gsp_standard_id": gsp_standard_id,
            "requirement_statement": (gsp.get("requirement_statement", "")[:300] if gsp else ""),
            "gsp_principle": gsp.get("gsp_principle", "") if gsp else "",
            "gsp_domain": gsp.get("gsp_domain", "") if gsp else "",
        } if gsp else None,
        "warning": "These are draft checklist items and do NOT publish SOP, training, or legal interpretation.",
    }


def query_checklist_by_customer_requirement(customer_requirement_id: str) -> dict:
    all_items = load_checklist_records()
    matched = [i for i in all_items
               if customer_requirement_id in i.get("linked_customer_requirement_ids", [])]

    if not matched:
        return {
            "ok": True, "count": 0, "items": [],
            "warning": f"No checklist items found for CRM '{customer_requirement_id}'.",
        }

    crm_records = load_customer_requirement_records()
    crm = next((c for c in crm_records if c.get("id") == customer_requirement_id), None)

    return {
        "ok": True,
        "count": len(matched),
        "items": [_format_item(i) for i in matched],
        "linked_customer_requirement": {
            "id": customer_requirement_id,
            "original_text_en": (crm.get("original_text_en", "") or crm.get("requirement_text", ""))[:300] if crm else "",
            "clause_ref": crm.get("clause_ref", "") if crm else "",
            "customer": crm.get("customer", crm.get("customer_code", "")) if crm else "",
        } if crm else None,
        "warning": "Draft checklist items — not approved.",
    }


def query_checklist_by_department(department: str) -> dict:
    dept_lower = department.strip().lower()
    all_items = load_checklist_records()
    matched = [i for i in all_items
               if dept_lower in i.get("responsible_department", "").lower()]

    if not matched:
        return {
            "ok": True, "count": 0, "items": [],
            "warning": f"No checklist items found for department '{department}'.",
        }

    return {
        "ok": True,
        "count": len(matched),
        "items": [_format_item(i) for i in matched],
        "warning": "Draft checklist items — not approved.",
    }


def query_checklist_by_function(function: str) -> dict:
    func_lower = function.strip().lower()
    all_items = load_checklist_records()
    matched = [i for i in all_items
               if func_lower == i.get("responsible_function", "").lower()
               or func_lower in i.get("responsible_function", "").lower()]

    if not matched:
        return {
            "ok": True, "count": 0, "items": [],
            "warning": f"No checklist items found for function '{function}'.",
        }

    return {
        "ok": True,
        "count": len(matched),
        "items": [_format_item(i) for i in matched],
        "warning": "Draft checklist items — not approved.",
    }


# ══════════════════════════════════════════════════════════════════
#  Traceability and evidence
# ══════════════════════════════════════════════════════════════════


def get_checklist_item_traceability(checklist_item_id: str) -> dict:
    all_items = load_checklist_records()
    item = next((i for i in all_items
                 if i.get("checklist_item_id") == checklist_item_id), None)

    if item is None:
        return {"ok": False, "error": f"Checklist item '{checklist_item_id}' not found."}

    result: Dict[str, Any] = {
        "ok": True,
        "checklist_item": {
            "checklist_item_id": item.get("checklist_item_id", ""),
            "checklist_question": item.get("checklist_question", ""),
            "check_method": item.get("check_method", ""),
            "checklist_type": item.get("checklist_type", ""),
            "responsible_function": item.get("responsible_function", ""),
            "responsible_department": item.get("responsible_department", ""),
            "review_status": item.get("review_status", ""),
            "approval_status": item.get("approval_status", ""),
        },
        "linked_gsp_standard": None,
        "linked_customer_requirements": [],
        "linked_evidence": [],
        "warnings": [],
    }

    gsp_id = item.get("linked_gsp_standard_id", "")
    if gsp_id:
        gsp_records = load_gsp_standard_records()
        gsp = next((g for g in gsp_records if g.get("gsp_standard_id") == gsp_id), None)
        if gsp:
            result["linked_gsp_standard"] = {
                "gsp_standard_id": gsp.get("gsp_standard_id", ""),
                "requirement_statement": gsp.get("requirement_statement", "")[:500],
                "gsp_principle": gsp.get("gsp_principle", ""),
                "gsp_domain": gsp.get("gsp_domain", ""),
                "review_status": gsp.get("review_status", ""),
            }
        else:
            result["warnings"].append(f"Linked GSP standard '{gsp_id}' not found.")

    crm_ids = item.get("linked_customer_requirement_ids", [])
    if crm_ids:
        crm_records = load_customer_requirement_records()
        for cid in crm_ids:
            crm = next((c for c in crm_records if c.get("id") == cid), None)
            if crm:
                result["linked_customer_requirements"].append({
                    "id": cid,
                    "original_text_en": (crm.get("original_text_en", "") or crm.get("requirement_text", ""))[:300],
                    "clause_ref": crm.get("clause_ref", ""),
                    "customer": crm.get("customer", crm.get("customer_code", "")),
                })
            else:
                result["warnings"].append(f"Linked CRM record '{cid}' not found.")

    ev_ids = item.get("linked_evidence_ids", [])
    if ev_ids:
        ev_records = load_evidence_records()
        for eid in ev_ids:
            ev = next((e for e in ev_records if e.get("evidence_id") == eid), None)
            if ev:
                result["linked_evidence"].append({
                    "evidence_id": eid,
                    "evidence_title": ev.get("evidence_title", ""),
                    "evidence_requirement_statement": (ev.get("evidence_requirement_statement", "") or "")[:300],
                    "evidence_type": ev.get("evidence_type", ""),
                })
            else:
                result["warnings"].append(f"Linked evidence record '{eid}' not found.")

    result["warnings"].append("Draft records — not approved. Do not use as SOP, training, or legal judgment.")
    return result


def get_checklist_item_evidence(checklist_item_id: str) -> dict:
    trace = get_checklist_item_traceability(checklist_item_id)
    if not trace["ok"]:
        return trace

    return {
        "ok": True,
        "checklist_item_id": checklist_item_id,
        "checklist_question": trace["checklist_item"]["checklist_question"],
        "linked_evidence": trace["linked_evidence"],
        "count": len(trace["linked_evidence"]),
        "warnings": trace["warnings"],
    }


# ══════════════════════════════════════════════════════════════════
#  Summary
# ══════════════════════════════════════════════════════════════════


def summarize_checklist_results(records: Optional[List[dict]] = None, max_items: int = 10) -> dict:
    if records is None:
        records = load_checklist_records()

    total = len(records)
    by_status: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    by_function: Dict[str, int] = {}
    by_department: Dict[str, int] = {}
    needs_review = 0

    for rec in records:
        rs = rec.get("review_status", "unknown")
        by_status[rs] = by_status.get(rs, 0) + 1
        ct = rec.get("checklist_type", "other")
        by_type[ct] = by_type.get(ct, 0) + 1
        rf = rec.get("responsible_function", "Unknown")
        by_function[rf] = by_function.get(rf, 0) + 1
        rd = rec.get("responsible_department", "Unknown")
        by_department[rd] = by_department.get(rd, 0) + 1
        if rec.get("needs_human_review"):
            needs_review += 1

    return {
        "ok": True,
        "total": total,
        "by_status": dict(sorted(by_status.items())),
        "by_type": dict(sorted(by_type.items())),
        "by_function": dict(sorted(by_function.items())),
        "by_department": dict(sorted(by_department.items())),
        "needs_human_review": needs_review,
        "max_items": max_items,
        "warning": "Draft records — not approved.",
    }


# ══════════════════════════════════════════════════════════════════
#  Mock LLM intent parser
# ══════════════════════════════════════════════════════════════════


def parse_checklist_query_intent(user_message: str, mock: bool = True) -> dict:
    if not mock:
        return {
            "ok": False, "error": "Real LLM not implemented in C6D-Lite.",
            "query_intent": "unknown", "filters": {}, "confidence": 0,
            "needs_clarification": True,
            "clarification_question": "Real LLM not available for intent parsing.",
        }

    msg_lower = user_message.lower().strip()
    filters: Dict[str, str] = {}
    intent = "checklist_summary"
    confidence = 0.6
    needs_clarification = False
    clarification = ""

    gsp_match = re.search(r'(GSP-COM-P\d{2,3}-[A-Z]{2,4}-\d{3})', user_message)
    crm_match = re.search(r'(CRM-[\w-]+)', user_message)
    cl_match = re.search(r'(CL-GSP-COM-[\w-]+)', user_message)

    if cl_match:
        intent = "checklist_item_traceability"
        filters["checklist_item_id"] = cl_match.group(1)
        confidence = 0.95
    elif gsp_match and ("checklist" in msg_lower or "standard" in msg_lower):
        intent = "checklist_by_gsp_standard"
        filters["gsp_standard_id"] = gsp_match.group(1)
        confidence = 0.95
    elif crm_match:
        intent = "checklist_by_customer_requirement"
        filters["customer_requirement_id"] = crm_match.group(1)
        confidence = 0.90
    elif "evidence" in msg_lower and cl_match:
        intent = "checklist_item_evidence"
        filters["checklist_item_id"] = cl_match.group(1)
        confidence = 0.90
    elif "evidence" in msg_lower and gsp_match:
        intent = "checklist_by_gsp_standard"
        filters["gsp_standard_id"] = gsp_match.group(1)
        confidence = 0.85

    dept_keywords = {
        "ehs": ("function", "EHS"), "environmental": ("function", "EHS"),
        "hr": ("function", "HR"), "human resources": ("function", "HR"),
        "production": ("function", "Production"),
        "legal": ("function", "Legal"),
        "qa": ("function", "QA"), "quality": ("function", "QA"),
        "compliance": ("function", "Compliance"),
    }
    for keyword, (filter_type, value) in dept_keywords.items():
        if keyword in msg_lower:
            filters[filter_type] = value
            if "checklist" in msg_lower or intent == "checklist_summary":
                if filter_type == "function":
                    intent = "checklist_by_function"
                else:
                    intent = "checklist_by_department"
            confidence = max(confidence, 0.85)

    if any(w in msg_lower for w in ["summary", "overview", "count", "how many", "all checklist"]):
        intent = "checklist_summary"
        confidence = max(confidence, 0.80)

    if intent == "checklist_summary" and not any(kw in msg_lower for kw in
                                                  ["summary", "overview", "count", "how many", "all"]):
        if msg_lower in ("", "checklist", "show checklist", "list"):
            needs_clarification = True
            clarification = "Filter by GSP standard ID, department (EHS, HR), or show all."
            confidence = 0.4

    return {
        "ok": True,
        "query_intent": intent,
        "filters": filters,
        "requested_output": "list" if intent != "checklist_summary" else "summary",
        "confidence": confidence,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification,
        "risk_level": "low" if confidence >= 0.85 else "medium" if confidence >= 0.6 else "high",
    }


# ══════════════════════════════════════════════════════════════════
#  Formatting
# ══════════════════════════════════════════════════════════════════


def _format_item(item: dict) -> dict:
    return {
        "checklist_item_id": item.get("checklist_item_id", ""),
        "checklist_question": item.get("checklist_question", ""),
        "check_method": item.get("check_method", ""),
        "expected_result": item.get("expected_result", ""),
        "required_evidence": item.get("required_evidence", ""),
        "responsible_function": item.get("responsible_function", ""),
        "responsible_department": item.get("responsible_department", ""),
        "checklist_type": item.get("checklist_type", ""),
        "suggested_frequency": item.get("suggested_frequency", ""),
        "risk_level": item.get("risk_level", ""),
        "review_status": item.get("review_status", ""),
        "approval_status": item.get("approval_status", ""),
        "needs_human_review": item.get("needs_human_review", False),
        "linked_gsp_standard_id": item.get("linked_gsp_standard_id", ""),
        "linked_customer_requirement_ids": item.get("linked_customer_requirement_ids", []),
        "linked_evidence_ids": item.get("linked_evidence_ids", []),
    }


def format_checklist_response(query_result: dict, response_mode: str = "chat") -> str:
    if not query_result.get("ok"):
        return f"Error: {query_result.get('error', 'Unknown error')}"

    lines = []

    count = query_result.get("count", query_result.get("total", 0))
    if isinstance(count, int):
        lines.append(f"Found {count} checklist item(s).")

    if "by_status" in query_result:
        lines.append("")
        lines.append("By Status:")
        for s, c in query_result.get("by_status", {}).items():
            lines.append(f"  {s}: {c}")
        lines.append("")
        lines.append("By Type:")
        for t, c in query_result.get("by_type", {}).items():
            lines.append(f"  {t}: {c}")
        lines.append("")
        lines.append("By Function:")
        for f, c in query_result.get("by_function", {}).items():
            lines.append(f"  {f}: {c}")
        lines.append("")
        lines.append(f"Needs human review: {query_result.get('needs_human_review', 0)}")
        return "\n".join(lines)

    if query_result.get("linked_gsp_standard"):
        gsp = query_result["linked_gsp_standard"]
        lines.append(f"GSP Standard: {gsp.get('gsp_standard_id', '')} "
                     f"[{gsp.get('gsp_principle', '')}|{gsp.get('gsp_domain', '')}]")

    if query_result.get("linked_customer_requirement"):
        crm = query_result["linked_customer_requirement"]
        lines.append(f"Customer Requirement: {crm.get('clause_ref', '')} ({crm.get('customer', '')})")

    if query_result.get("items"):
        for item in query_result["items"][:10]:
            lines.append("")
            lines.append(f"  [{item['checklist_item_id']}]")
            lines.append(f"  Q: {item.get('checklist_question', '')[:150]}")
            if response_mode == "detail":
                lines.append(f"  Method: {item.get('check_method', '')[:150]}")
                lines.append(f"  Expected: {item.get('expected_result', '')[:150]}")
            lines.append(f"  Function: {item.get('responsible_function', '')} | "
                         f"Dept: {item.get('responsible_department', '')} | "
                         f"Type: {item.get('checklist_type', '')}")
            lines.append(f"  Status: {item.get('review_status', '')} | "
                         f"Approval: {item.get('approval_status', '')}")
        if count > 10:
            lines.append(f"\n  ... and {count - 10} more")

    if "linked_evidence" in query_result:
        ev = query_result["linked_evidence"]
        if ev:
            lines.append(f"\nLinked Evidence ({len(ev)}):")
            for e in ev[:5]:
                lines.append(f"  - {e.get('evidence_id', '')}: {e.get('evidence_title', '')[:100]}")

    if query_result.get("linked_gsp_standard") and "linked_customer_requirements" in query_result:
        lines.append("\nTraceability:")
        for crm in query_result.get("linked_customer_requirements", [])[:3]:
            lines.append(f"  => CRM: {crm.get('id', '')} ({crm.get('clause_ref', '')})")

    for w in (query_result.get("warnings", []) if isinstance(query_result.get("warnings", []), list)
              else [query_result.get("warning", "")]):
        if w:
            lines.append(f"\n⚠️  {w}")

    lines.append("\n⚠️  These are draft checklist items. They do NOT publish SOP, training, "
                 "legal interpretation, or customer overlay.")

    return "\n".join(lines)
