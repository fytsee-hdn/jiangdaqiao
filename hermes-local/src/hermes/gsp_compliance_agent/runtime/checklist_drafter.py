"""
checklist_drafter.py — GSP Compliance Agent: C6B Department Checklist Draft Generation.

LLM-first semantic analysis of GSP Standard candidates (+ linked evidence records)
to propose department checklist items for verification.

Key principles:
- mock_llm=True by default in tests
- dry_run=True by default; execute=False by default
- No write unless execute=True
- LLM output validated against department_checklist.schema.json
- Invalid LLM output creates needs_human_review record, not crash
- No hard-coded checklist generation rules based on domain/principle
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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
_CRM_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "customer_requirements", "customer_requirement_master.jsonl")
_EVIDENCE_PATH = os.path.join(_ROOT, "data", "knowledge", "compliance", "evidence_matrix", "evidence_matrix.jsonl")
_CHECKLIST_DIR = os.path.join(_ROOT, "data", "knowledge", "compliance", "checklists")
_CHECKLIST_PATH = os.path.join(_CHECKLIST_DIR, "department_checklist.jsonl")
_DRY_RUN_DIR = os.path.join(_CHECKLIST_DIR, "dry_runs")
_REPORT_DIR = os.path.join(_CHECKLIST_DIR, "reports")

# ══════════════════════════════════════════════════════════════════
#  Valid value sets (code normalizes labels, does not decide content)
# ══════════════════════════════════════════════════════════════════

VALID_CHECKLIST_TYPES = {
    "document_check", "record_check", "site_observation", "interview_check",
    "system_data_check", "permit_or_license_check", "training_check",
    "equipment_or_facility_check", "supplier_check",
    "emergency_preparedness_check", "other", "unknown",
}

VALID_FREQUENCIES = {
    "once", "daily", "weekly", "monthly", "quarterly", "annually",
    "per_shift", "per_batch", "as_needed", "upon_request", "ongoing", "unknown",
}

VALID_RISK_LEVELS = {"critical", "high", "medium", "low", "unknown"}

# ══════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════


def _now() -> str:
    return datetime.now(_TZ).isoformat()


def _load_jsonl(path: str) -> List[dict]:
    records = []
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def load_crm_by_id(crm_id: str) -> Optional[dict]:
    for rec in _load_jsonl(_CRM_PATH):
        if rec.get("id") == crm_id:
            return rec
    sample_path = os.path.join(_ROOT, "data", "knowledge", "compliance",
                               "sample_records", "c5a_sample_crm_fixtures.jsonl")
    if os.path.isfile(sample_path):
        for rec in _load_jsonl(sample_path):
            if rec.get("id") == crm_id:
                return rec
    return None


def load_linked_crm(links: List[dict]) -> List[dict]:
    results = []
    for link in (links or []):
        crm_id = link.get("crm_id", "")
        if crm_id:
            rec = load_crm_by_id(crm_id)
            if rec:
                results.append(rec)
    return results


def load_evidence_for_gsp(gsp_standard_id: str) -> List[dict]:
    """Load evidence drafts linked to a specific GSP standard."""
    return [r for r in _load_jsonl(_EVIDENCE_PATH)
            if r.get("gsp_standard_id") == gsp_standard_id]


def normalize_checklist_type(raw: str) -> str:
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in VALID_CHECKLIST_TYPES:
        return normalized
    for valid in VALID_CHECKLIST_TYPES:
        if valid.startswith(normalized) or normalized.startswith(valid):
            return valid
    return "other"


def normalize_frequency(raw: str) -> str:
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in VALID_FREQUENCIES:
        return normalized
    return "unknown"


def normalize_risk_level(raw: str) -> str:
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in VALID_RISK_LEVELS:
        return normalized
    return "unknown"


def normalize_function(raw: str) -> str:
    mapping = {
        "ehs": "EHS", "environmental": "EHS", "health_safety": "EHS", "safety": "EHS",
        "human_resources": "HR", "hr": "HR",
        "production": "Production", "manufacturing": "Production",
        "quality": "QA", "qa": "QA", "quality_assurance": "QA",
        "maintenance": "Maintenance", "engineering": "Maintenance",
        "logistics": "Logistics", "warehouse": "Logistics",
        "training": "Training",
        "legal": "Legal",
        "compliance": "Compliance",
        "administration": "Administration", "admin": "Administration",
        "management": "Management",
    }
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return mapping.get(key, raw.strip().title())


# ══════════════════════════════════════════════════════════════════
#  Build LLM input
# ══════════════════════════════════════════════════════════════════


def build_checklist_generation_input(
    gsp_candidate: dict,
    linked_requirements: Optional[List[dict]] = None,
    linked_evidence: Optional[List[dict]] = None,
) -> dict:
    """Build the input dict for LLM checklist generation.

    Structures GSP candidate + linked CRM + linked evidence for LLM.
    """
    if linked_requirements is None:
        links = gsp_candidate.get("source_customer_requirement_links", [])
        linked_requirements = load_linked_crm(links)

    if linked_evidence is None:
        linked_evidence = load_evidence_for_gsp(
            gsp_candidate.get("gsp_standard_id", "")
        )

    customer_reqs = []
    for crm in linked_requirements:
        customer_reqs.append({
            "crm_id": crm.get("id", ""),
            "customer": crm.get("customer", crm.get("customer_code", "IKEA")),
            "standard_family": crm.get("standard_family", "IWAY"),
            "standard_version": crm.get("standard_version", ""),
            "clause_ref": crm.get("clause_ref", ""),
            "original_text_excerpt": crm.get("original_text_en", "") or crm.get("requirement_text", ""),
        })
    if not customer_reqs:
        for link in gsp_candidate.get("source_customer_requirement_links", []):
            customer_reqs.append({
                "crm_id": link.get("crm_id", ""),
                "customer": link.get("customer", "IKEA"),
                "standard_family": link.get("standard_family", "IWAY"),
                "standard_version": link.get("standard_version", ""),
                "clause_ref": link.get("clause_ref", ""),
                "original_text_excerpt": link.get("original_text_excerpt", ""),
            })

    evidence_recs = []
    for ev in linked_evidence:
        evidence_recs.append({
            "evidence_id": ev.get("evidence_id", ""),
            "evidence_title": ev.get("evidence_title", ""),
            "evidence_type": ev.get("evidence_type", ""),
            "evidence_owner_function": ev.get("evidence_owner_function", ""),
            "evidence_frequency": ev.get("evidence_frequency", ""),
        })

    principle = gsp_candidate.get("gsp_principle", "PXX")
    domain = gsp_candidate.get("gsp_domain", "REV")
    principle_labels = {
        "P01": "Legal Compliance", "P02": "Forced Labour",
        "P03": "Child Labour & Young Workers", "P04": "Health & Safety",
        "P05": "Working Hours", "P06": "Wages & Benefits",
        "P07": "Freedom of Association", "P08": "Fire Safety & Emergency Preparedness",
        "P09": "Chemical Safety & Hazardous Substances", "P10": "Environmental Management",
        "PXX": "General / Other",
    }
    domain_labels = {
        "WH": "Working Hours", "WB": "Wages & Benefits",
        "SWM": "Safe Working Methods", "OHS": "Occupational Health & Safety",
        "FIRE": "Fire Safety", "CHEM": "Chemical Safety",
        "WASTE": "Waste Management", "CL": "Child Labour",
        "LR": "Labour Rights", "LEG": "Legal Compliance",
        "GOV": "Governance", "ENV": "Environmental", "REV": "Review / General",
    }

    return {
        "gsp_standard": {
            "gsp_standard_id": gsp_candidate.get("gsp_standard_id", ""),
            "title": gsp_candidate.get("title", ""),
            "gsp_principle": principle,
            "gsp_domain": domain,
            "requirement_statement": gsp_candidate.get("requirement_statement", ""),
            "normative_force": gsp_candidate.get("normative_force", "shall"),
            "is_critical": gsp_candidate.get("is_critical", False),
            "gsp_applicability": gsp_candidate.get("gsp_applicability", "all_facilities"),
            "legal_dependency": gsp_candidate.get("legal_dependency", "needs_legal_review"),
        },
        "linked_customer_requirements": customer_reqs,
        "linked_evidence_records": evidence_recs,
        "principle_label": f"{principle} - {principle_labels.get(principle, 'Unknown')}",
        "domain_label": f"{domain} - {domain_labels.get(domain, 'General')}",
    }


# ══════════════════════════════════════════════════════════════════
#  Mock LLM (for testing only)
# ══════════════════════════════════════════════════════════════════

_MOCK_RESPONSES = {
    "SWM": [
        {
            "checklist_question": "Is there a documented risk assessment covering all routine and non-routine tasks?",
            "check_purpose": "To verify that the facility has systematically identified all occupational health and safety risks through documented risk assessment.",
            "check_method": "Review the risk assessment register and verify it covers all identified work tasks. Check that assessments are reviewed at least annually and updated when processes change.",
            "expected_result": "Risk assessment register covering all facility tasks with identified hazards, risk ratings, control measures, and review dates. Signed off by EHS manager.",
            "required_evidence": "Risk assessment register, task inventory list, annual review records, process change documentation.",
            "responsible_function": "EHS",
            "responsible_department": "EHS Department",
            "suggested_frequency": "annually",
            "risk_level": "critical",
            "checklist_type": "document_check",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "FIRE": [
        {
            "checklist_question": "Are fire extinguishers available, accessible, and inspected monthly?",
            "check_purpose": "To verify that fire extinguishers are maintained and readily accessible throughout the facility.",
            "check_method": "Walk through the facility and inspect fire extinguisher locations, check monthly inspection tags, verify accessibility and unobstructed access.",
            "expected_result": "Fire extinguishers visible and accessible at required locations. Monthly inspection tags complete and current. No obstructions blocking access.",
            "required_evidence": "Monthly fire extinguisher inspection logs, facility floor plan showing extinguisher locations, purchase/refill records.",
            "responsible_function": "EHS",
            "responsible_department": "EHS Department",
            "suggested_frequency": "monthly",
            "risk_level": "critical",
            "checklist_type": "equipment_or_facility_check",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
        {
            "checklist_question": "Are emergency exits clearly marked, unobstructed, and unlocked during working hours?",
            "check_purpose": "To verify emergency egress paths are safe and accessible at all times workers are present.",
            "check_method": "Walk through the facility and inspect all emergency exits and egress paths. Verify exit signs are visible, paths are unobstructed, and doors are unlocked from the inside.",
            "expected_result": "All emergency exits clearly marked with illuminated signs. Exit paths free of obstructions. Doors open easily from inside without special knowledge or tools.",
            "required_evidence": "Emergency exit inspection logs, facility evacuation plan, photographs of exit conditions, maintenance records for exit hardware.",
            "responsible_function": "EHS",
            "responsible_department": "EHS Department",
            "suggested_frequency": "monthly",
            "risk_level": "critical",
            "checklist_type": "site_observation",
            "uncertainty_notes": "Local building codes may have specific requirements for exit signage and door hardware.",
            "needs_human_review": True,
        },
        {
            "checklist_question": "Are emergency evacuation drills conducted at least annually with records maintained?",
            "check_purpose": "To verify that workers are prepared to evacuate the facility in an emergency.",
            "check_method": "Review drill records including dates, attendance, evacuation time, observations, and corrective actions. Interview workers on evacuation procedures.",
            "expected_result": "At least one drill per year with complete records including date, duration, participant count, observations, and corrective actions. Workers can describe evacuation procedures.",
            "required_evidence": "Evacuation drill reports, drill attendance sheets, evacuation time measurements, corrective action records.",
            "responsible_function": "EHS",
            "responsible_department": "EHS Department",
            "suggested_frequency": "annually",
            "risk_level": "high",
            "checklist_type": "training_check",
            "uncertainty_notes": "Some jurisdictions may require semi-annual drills. Check local regulations.",
            "needs_human_review": True,
        },
    ],
    "WH": [
        {
            "checklist_question": "Do actual working hours comply with the 60-hour weekly maximum including overtime?",
            "check_purpose": "To verify that working hours do not exceed the IWAY standard limit of 60 hours per week including overtime.",
            "check_method": "Review time records for a sample of workers across different departments. Calculate weekly totals including overtime for at least the last 3 months.",
            "expected_result": "No worker exceeds 60 hours per week including overtime. Weekly records are complete and accurate. Overtime is clearly identified in records.",
            "required_evidence": "Timekeeping records, attendance reports, payroll records, HR system export showing daily and weekly hours.",
            "responsible_function": "HR",
            "responsible_department": "HR Department",
            "suggested_frequency": "monthly",
            "risk_level": "high",
            "checklist_type": "record_check",
            "uncertainty_notes": "National law may have stricter limits. Verify maximum weekly hours against local regulations.",
            "needs_human_review": True,
        },
        {
            "checklist_question": "Are workers provided at least one day off in every seven-day period?",
            "check_purpose": "To verify that every worker receives a minimum of one rest day per week.",
            "check_method": "Review work schedules and attendance records for a sample of workers. Verify that each worker has at least one full calendar day off in each seven-day period.",
            "expected_result": "Every worker has at least one full rest day per seven-day period. Rest days are recorded and verifiable in attendance records.",
            "required_evidence": "Work schedules, attendance records, rest day schedules, HR records.",
            "responsible_function": "HR",
            "responsible_department": "HR Department",
            "suggested_frequency": "monthly",
            "risk_level": "high",
            "checklist_type": "record_check",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "CHEM": [
        {
            "checklist_question": "Is there a complete chemical inventory with Safety Data Sheets available in the local language?",
            "check_purpose": "To verify that all chemicals are identified and their safety information is accessible to workers.",
            "check_method": "Review the chemical inventory for completeness. Check that an SDS is available at each point of use in the local language.",
            "expected_result": "Complete chemical inventory listing all substances. SDS available in local language at each storage and use location. Inventory updated when chemicals are added or removed.",
            "required_evidence": "Chemical inventory register, Safety Data Sheets (SDS) in local language, SDS binders or digital access at use points.",
            "responsible_function": "EHS",
            "responsible_department": "EHS Department",
            "suggested_frequency": "quarterly",
            "risk_level": "critical",
            "checklist_type": "document_check",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "CL": [
        {
            "checklist_question": "Does the facility have verified age documentation for all workers demonstrating minimum age compliance?",
            "check_purpose": "To verify that no person below the minimum employment age is employed at the facility.",
            "check_method": "Review personnel files for a sample of workers, verifying that government-issued ID or equivalent age documentation is on file. Check that the youngest workers have especially thorough documentation.",
            "expected_result": "Valid age verification documentation for all workers. No worker below the minimum age is employed. Age verification is conducted before employment.",
            "required_evidence": "Copies of worker IDs or passports, age verification records, new hire documentation.",
            "responsible_function": "HR",
            "responsible_department": "HR Department",
            "suggested_frequency": "quarterly",
            "risk_level": "critical",
            "checklist_type": "record_check",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "WB": [
        {
            "checklist_question": "Are wages paid on time and at or above the legal minimum wage or industry benchmark?",
            "check_purpose": "To verify that wage rates comply with minimum wage requirements and are paid on schedule.",
            "check_method": "Review payroll records and payslips for a sample of workers across wage grades. Compare wage rates to legal minimum wage and industry benchmarks. Verify payment dates against scheduled pay days.",
            "expected_result": "All workers paid at or above minimum wage (or industry benchmark if higher). Payslips provided in a language workers understand. No late or missed payments.",
            "required_evidence": "Payroll records, payslips, minimum wage documentation, employee wage rate schedules.",
            "responsible_function": "HR",
            "responsible_department": "HR Department",
            "suggested_frequency": "monthly",
            "risk_level": "high",
            "checklist_type": "record_check",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "LR": [
        {
            "checklist_question": "Is there evidence of worker representation or alternative dialogue mechanisms?",
            "check_purpose": "To verify that workers have access to representation or collective dialogue mechanisms.",
            "check_method": "Review documentation of worker committees, union registrations, or alternative representation structures. Interview worker representatives or committee members.",
            "expected_result": "Documented worker representation structure with meeting records. Workers can describe how to raise collective concerns. Management demonstrates engagement with worker representatives.",
            "required_evidence": "Trade union registration, collective bargaining agreements, worker committee records, meeting minutes, alternative representation documentation.",
            "responsible_function": "HR",
            "responsible_department": "HR Department",
            "suggested_frequency": "annually",
            "risk_level": "high",
            "checklist_type": "interview_check",
            "uncertainty_notes": "Trade union rights vary by jurisdiction. Verify applicable local law.",
            "needs_human_review": True,
        },
    ],
    "OHS": [
        {
            "checklist_question": "Is PPE provided free of charge and are workers trained in its proper use?",
            "check_purpose": "To verify that PPE is available at no cost to workers and they are competent in its use.",
            "check_method": "Review PPE issue records and training records. Inspect PPE availability at workstations. Interview workers on PPE use and comfort.",
            "expected_result": "PPE provided free of charge appropriate to each task. Training records show workers received instruction on proper use, fitting, and maintenance. PPE is in good condition and used correctly.",
            "required_evidence": "PPE issue records, training attendance records, PPE inspection logs, worker interviews.",
            "responsible_function": "EHS",
            "responsible_department": "EHS Department",
            "suggested_frequency": "annually",
            "risk_level": "high",
            "checklist_type": "equipment_or_facility_check",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "LEG": [
        {
            "checklist_question": "Are all required permits, licences, and registrations valid and available for inspection?",
            "check_purpose": "To verify that the facility maintains current legal authorisations for all regulated activities.",
            "check_method": "Review the legal register or permit tracker. Verify each permit/licence is current. Check renewal dates and ensure renewals are initiated before expiry.",
            "expected_result": "Complete register of all required permits, licences, and registrations. All documents are current and available for inspection. Renewal process is established and tracked.",
            "required_evidence": "Permit/licence register, copies of current permits, licence renewal tracking system, inspection records.",
            "responsible_function": "Legal",
            "responsible_department": "Compliance Department",
            "suggested_frequency": "quarterly",
            "risk_level": "critical",
            "checklist_type": "permit_or_license_check",
            "uncertainty_notes": "Permit requirements vary by jurisdiction. Legal review recommended.",
            "needs_human_review": True,
        },
    ],
    "ENV": [
        {
            "checklist_question": "Is there a documented environmental policy and aspect/impact register?",
            "check_purpose": "To verify that the facility has established its environmental management framework.",
            "check_method": "Review the environmental policy for management commitment and scope. Verify the aspect/impact register covers all operational activities.",
            "expected_result": "Signed environmental policy from management. Aspect/impact register identifying significant environmental aspects with significance criteria.",
            "required_evidence": "Environmental policy document, aspect/impact register, review/update records.",
            "responsible_function": "EHS",
            "responsible_department": "EHS Department",
            "suggested_frequency": "annually",
            "risk_level": "medium",
            "checklist_type": "document_check",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "WASTE": [
        {
            "checklist_question": "Is waste segregated by type, stored appropriately, and disposed of through licensed contractors?",
            "check_purpose": "To verify that waste management practices prevent environmental harm and comply with legal requirements.",
            "check_method": "Inspect waste storage areas for proper segregation and containment. Review waste disposal records and contractor licences.",
            "expected_result": "Waste segregated into appropriate categories. Storage areas are well-maintained with proper containment. Waste disposal records and licensed contractor agreements are current.",
            "required_evidence": "Waste segregation records, storage area inspection reports, contractor licences, waste manifests.",
            "responsible_function": "EHS",
            "responsible_department": "EHS Department",
            "suggested_frequency": "monthly",
            "risk_level": "medium",
            "checklist_type": "site_observation",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "REV": [
        {
            "checklist_question": "Is there documentation demonstrating implementation of this general requirement?",
            "check_purpose": "To verify compliance with a general or unclassified requirement.",
            "check_method": "Review available documentation and interview responsible personnel to determine what evidence exists.",
            "expected_result": "Documentation demonstrating implementation is available and current.",
            "required_evidence": "To be determined during review.",
            "responsible_function": "Compliance",
            "responsible_department": "Compliance Department",
            "suggested_frequency": "unknown",
            "risk_level": "medium",
            "checklist_type": "other",
            "uncertainty_notes": "General domain — checklist requirement needs human interpretation.",
            "needs_human_review": True,
        },
    ],
}


def call_mock_llm(generation_input: dict) -> dict:
    """Deterministic mock LLM for testing.

    Returns structured checklist proposals based on GSP domain.
    MOCK ONLY — does NOT perform real semantic analysis.
    """
    domain = generation_input.get("gsp_standard", {}).get("gsp_domain", "REV")
    gsp_id = generation_input.get("gsp_standard", {}).get("gsp_standard_id", "unknown")

    proposed = _MOCK_RESPONSES.get(domain, _MOCK_RESPONSES["REV"])

    result = {
        "gsp_standard_id": gsp_id,
        "analysis_summary": f"Mock checklist generation for {domain} domain: "
                            f"Based on GSP standard and linked evidence records, "
                            f"the following checklist items verify implementation.",
        "proposed_items": proposed,
        "_mock": True,
    }
    return result


# ══════════════════════════════════════════════════════════════════
#  Normalize and validate
# ══════════════════════════════════════════════════════════════════


def normalize_checklist_draft(
    llm_output: dict,
    gsp_candidate: dict,
    linked_evidence: Optional[List[dict]] = None,
) -> List[dict]:
    """Normalize LLM output into valid checklist draft records.

    Code validates structure and normalizes fields.
    Does NOT change semantic content.
    """
    gsp_id = gsp_candidate.get("gsp_standard_id", "")
    samples = gsp_candidate.get("derivation_batch_id", "") or ""
    is_sample = "sample" in samples.lower()

    proposed = llm_output.get("proposed_items", [])
    if not proposed:
        proposed = [{
            "checklist_question": "Checklist Item (Human Review Required)",
            "check_purpose": f"LLM did not produce specific checklist items for {gsp_id}. Human review required.",
            "check_method": "To be determined during review.",
            "expected_result": "To be determined during review.",
            "required_evidence": "To be determined during review.",
            "responsible_function": "Compliance",
            "responsible_department": "Compliance Department",
            "suggested_frequency": "unknown",
            "risk_level": "unknown",
            "checklist_type": "other",
            "uncertainty_notes": "No checklist items generated by LLM.",
            "needs_human_review": True,
        }]

    # Collect linked evidence IDs
    linked_ev_ids = [ev.get("evidence_id", "") for ev in (linked_evidence or []) if ev.get("evidence_id")]
    # Also try from the candidate's evidence matrix
    if not linked_ev_ids:
        linked_ev_ids = [ev.get("evidence_id", "") for ev in load_evidence_for_gsp(gsp_id) if ev.get("evidence_id")]

    records = []
    now = _now()

    # Extract CRM IDs from GSP candidate
    crm_ids = []
    for link in gsp_candidate.get("source_customer_requirement_links", []):
        cid = link.get("crm_id", "")
        if cid:
            crm_ids.append(cid)

    for i, item in enumerate(proposed):
        seq = i + 1
        item_id = generate_checklist_item_id(gsp_id, seq)
        cl_type = normalize_checklist_type(item.get("checklist_type", "other") or "other")
        freq = normalize_frequency(item.get("suggested_frequency", "unknown") or "unknown")
        risk = normalize_risk_level(item.get("risk_level", "unknown") or "unknown")
        func = normalize_function(item.get("responsible_function", "") or "")

        record = {
            "checklist_item_id": item_id,
            "checklist_set_id": "",
            "linked_gsp_standard_id": gsp_id,
            "linked_customer_requirement_ids": crm_ids,
            "linked_evidence_ids": linked_ev_ids,
            "source_original_text_refs": [],
            "checklist_question": str(item.get("checklist_question", f"Checklist {seq}"))[:500],
            "check_purpose": str(item.get("check_purpose", ""))[:1000],
            "check_method": str(item.get("check_method", ""))[:1000],
            "expected_result": str(item.get("expected_result", ""))[:1000],
            "required_evidence": str(item.get("required_evidence", ""))[:1000],
            "responsible_function": func,
            "responsible_department": str(item.get("responsible_department", ""))[:100],
            "suggested_frequency": freq,
            "risk_level": risk,
            "checklist_type": cl_type,
            "site_scope": gsp_candidate.get("gsp_applicability", "all_facilities"),
            "applicability": "",
            "llm_reasoning_summary": str(llm_output.get("analysis_summary", ""))[:500],
            "uncertainty_notes": str(item.get("uncertainty_notes", ""))[:500],
            "needs_human_review": bool(item.get("needs_human_review", False)),
            "generation_method": "llm_semantic_analysis_mock" if llm_output.get("_mock") else "llm_semantic_analysis",
            "review_status": "draft_pending_review",
            "approval_status": "not_approved",
            "generated_by": "gsp_compliance_agent",
            "batch_id": "",
            "sample_only": is_sample,
            "created_by": "c6b_checklist_drafter",
            "created_at": now,
            "updated_at": now,
            "notes": f"Checklist item {seq} for {gsp_id}. Generated by LLM semantic analysis.",
        }
        records.append(record)

    return records


def validate_checklist_draft(checklist_record: dict) -> dict:
    """Validate a checklist draft record against required fields."""
    errors = []
    warnings = []

    required = ["checklist_item_id", "linked_gsp_standard_id", "checklist_question",
                "checklist_type", "review_status", "approval_status"]
    for field in required:
        if not checklist_record.get(field):
            errors.append(f"Missing required field: {field}")

    if checklist_record.get("checklist_item_id") and not re.match(
            r'^CL-GSP-COM-', checklist_record["checklist_item_id"]):
        warnings.append(f"Checklist ID format may be non-standard: {checklist_record['checklist_item_id']}")

    cl_type = checklist_record.get("checklist_type", "")
    if cl_type and cl_type not in VALID_CHECKLIST_TYPES:
        warnings.append(f"Invalid checklist_type '{cl_type}'")

    freq = checklist_record.get("suggested_frequency", "")
    if freq and freq not in VALID_FREQUENCIES:
        warnings.append(f"Invalid suggested_frequency '{freq}'")

    risk = checklist_record.get("risk_level", "")
    if risk and risk not in VALID_RISK_LEVELS:
        warnings.append(f"Invalid risk_level '{risk}'")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def generate_checklist_item_id(gsp_standard_id: str, sequence: int) -> str:
    """Generate deterministic checklist item ID.

    Format: CL-<gsp_standard_id>-<seq>
    Example: CL-GSP-COM-P04-SWM-001-001
    """
    return f"CL-{gsp_standard_id}-{sequence:03d}"


def generate_checklist_set_id(batch_id: str, gsp_standard_id: Optional[str] = None) -> str:
    """Generate a checklist set ID for grouping items."""
    if gsp_standard_id:
        return f"CL-SET-{batch_id}-{gsp_standard_id}"
    return f"CL-SET-{batch_id}"


def _load_existing_checklist_ids(path: str) -> set:
    """Load existing checklist item IDs for duplicate detection."""
    existing = set()
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    eid = rec.get("checklist_item_id", "")
                    if eid:
                        existing.add(eid)
                except json.JSONDecodeError:
                    pass
    return existing


# ══════════════════════════════════════════════════════════════════
#  Core drafting functions
# ══════════════════════════════════════════════════════════════════


def draft_checklist_for_gsp_candidate(
    gsp_candidate: dict,
    options: Optional[dict] = None,
) -> dict:
    """Generate checklist drafts for a single GSP standard candidate.

    Calls mock LLM to propose checklist items.
    Code validates structure and normalizes fields.

    Args:
        gsp_candidate: Single GSP standard candidate dict.
        options: Dict with keys: mock_llm, include_needs_legal_review,
                 include_evidence_context.

    Returns:
        Dict with keys: ok, records, warnings, errors.
    """
    if options is None:
        options = {}

    mock_llm = options.get("mock_llm", True)
    include_legal = options.get("include_needs_legal_review", False)
    include_evidence = options.get("include_evidence_context", True)

    warnings = []
    errors = []

    # Check review_status eligibility
    status = gsp_candidate.get("review_status", "")
    if status == "rejected":
        return {"ok": True, "records": [], "warnings": ["Skipped rejected candidate."], "errors": []}
    if status == "correction_required":
        return {"ok": True, "records": [], "warnings": ["Skipped correction_required candidate."], "errors": []}
    if status == "needs_legal_review" and not include_legal:
        return {"ok": True, "records": [], "warnings": ["Skipped needs_legal_review candidate."], "errors": []}
    if status not in ("confirmed_for_internal_standard", "draft_pending_review", "needs_legal_review"):
        if status == "needs_legal_review" and include_legal:
            pass
        elif status in ("draft_pending_review", "confirmed_for_internal_standard"):
            pass
        else:
            warnings.append(f"Unexpected review_status '{status}'. Proceeding with caution.")

    gsp_id = gsp_candidate.get("gsp_standard_id", "")

    # Load linked evidence if requested
    linked_evidence = None
    if include_evidence:
        linked_evidence = load_evidence_for_gsp(gsp_id)
        if linked_evidence:
            warnings.append(f"Linked {len(linked_evidence)} evidence records for {gsp_id}.")

    # Build input
    generation_input = build_checklist_generation_input(
        gsp_candidate, linked_evidence=linked_evidence,
    )

    # Call LLM
    if mock_llm:
        try:
            llm_output = call_mock_llm(generation_input)
        except Exception as e:
            errors.append(f"Mock LLM error: {e}")
            llm_output = {
                "gsp_standard_id": gsp_id,
                "analysis_summary": f"Mock LLM error: {e}",
                "proposed_items": [],
                "_mock": True,
            }
    else:
        errors.append("Real LLM not implemented in C6B-Lite. Use --mock-llm.")
        return {"ok": False, "records": [], "warnings": warnings, "errors": errors}

    # Normalize
    try:
        records = normalize_checklist_draft(llm_output, gsp_candidate, linked_evidence)
    except Exception as e:
        errors.append(f"Normalization error: {e}")
        return {"ok": False, "records": [], "warnings": warnings, "errors": errors}

    # Validate
    for rec in records:
        validation = validate_checklist_draft(rec)
        if not validation["valid"]:
            warnings.append(f"Validation warning for {rec.get('checklist_item_id', '?')}: {validation['errors']}")
        warnings.extend(validation["warnings"])

    return {
        "ok": True,
        "records": records,
        "warnings": warnings,
        "errors": errors,
    }


def draft_checklist_batch(
    candidates: List[dict],
    batch_id: Optional[str] = None,
    dry_run: bool = True,
    mock_llm: bool = True,
    include_needs_legal_review: bool = False,
    include_evidence_context: bool = True,
) -> dict:
    """Generate checklist drafts for a batch of GSP candidates.

    Returns dict with counts, by-type breakdown, and warnings.
    """
    now = _now()
    ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")
    if batch_id is None:
        batch_id = f"C6B-{ts}"

    set_id = generate_checklist_set_id(batch_id)

    result: Dict[str, Any] = {
        "ok": False,
        "status": "initialising",
        "records": [],
        "input_count": len(candidates),
        "skipped_count": 0,
        "draft_count": 0,
        "by_type": {},
        "by_function": {},
        "by_department": {},
        "needs_review_count": 0,
        "linked_evidence_count": 0,
        "warnings": [],
        "errors": [],
        "dry_run": dry_run,
        "batch_id": batch_id,
        "mock_llm": mock_llm,
        "include_evidence_context": include_evidence_context,
        "write_path": None,
    }

    for candidate in candidates:
        gsp_id = candidate.get("gsp_standard_id", "?")
        dri = draft_checklist_for_gsp_candidate(candidate, options={
            "mock_llm": mock_llm,
            "include_needs_legal_review": include_needs_legal_review,
            "include_evidence_context": include_evidence_context,
        })

        if not dri["ok"]:
            result["errors"].append(f"Checklist error for {gsp_id}: {dri.get('errors', [])}")
            result["skipped_count"] += 1
            continue

        if not dri["records"]:
            result["skipped_count"] += 1
            if dri["warnings"]:
                result["warnings"].append(f"{gsp_id}: {dri['warnings'][0]}")
            continue

        for rec in dri["records"]:
            rec["batch_id"] = batch_id
            rec["checklist_set_id"] = set_id

        # Count linked evidence
        for rec in dri["records"]:
            if rec.get("linked_evidence_ids"):
                result["linked_evidence_count"] += len(rec["linked_evidence_ids"])

        result["records"].extend(dri["records"])
        result["draft_count"] += len(dri["records"])
        result["warnings"].extend(dri["warnings"])
        result["errors"].extend(dri["errors"])

        for rec in dri["records"]:
            cl_type = rec.get("checklist_type", "other")
            result["by_type"][cl_type] = result["by_type"].get(cl_type, 0) + 1
            func = rec.get("responsible_function", "Unknown")
            result["by_function"][func] = result["by_function"].get(func, 0) + 1
            dept = rec.get("responsible_department", "Unknown")
            result["by_department"][dept] = result["by_department"].get(dept, 0) + 1
            if rec.get("needs_human_review"):
                result["needs_review_count"] += 1

    # Duplicate detection
    if not dry_run and result["records"]:
        existing_ids = _load_existing_checklist_ids(_CHECKLIST_PATH)
        deduped = []
        for rec in result["records"]:
            eid = rec.get("checklist_item_id", "")
            if eid in existing_ids:
                result["warnings"].append(f"Duplicate checklist_item_id '{eid}' skipped.")
                continue
            deduped.append(rec)
        result["records"] = deduped
        result["draft_count"] = len(deduped)

    result["status"] = "ready" if dry_run else "written"
    result["write_path"] = None if dry_run else _CHECKLIST_PATH

    if not dry_run:
        ok = write_checklist_drafts(result["records"], execute=True)
        result["ok"] = ok
    else:
        result["ok"] = True

    return result


def write_checklist_drafts(records: List[dict], execute: bool = False) -> bool:
    """Write checklist drafts to department_checklist.jsonl. Only if execute=True."""
    if not execute:
        return False
    if not records:
        return True
    try:
        os.makedirs(os.path.dirname(_CHECKLIST_PATH), exist_ok=True)
        existing_ids = _load_existing_checklist_ids(_CHECKLIST_PATH)
        for rec in records:
            eid = rec.get("checklist_item_id", "")
            if eid in existing_ids:
                _logger.warning("Duplicate checklist_item_id '%s' skipped.", eid)
                continue
            with open(_CHECKLIST_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            existing_ids.add(eid)
        return True
    except Exception as e:
        _logger.error("Failed to write checklist drafts: %s", e)
        return False


# ══════════════════════════════════════════════════════════════════
#  Dry-run and report
# ══════════════════════════════════════════════════════════════════


def write_dry_run_output(result: dict) -> str:
    ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")
    os.makedirs(_DRY_RUN_DIR, exist_ok=True)
    path = os.path.join(_DRY_RUN_DIR, f"c6b_checklist_draft_dry_run_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


def generate_checklist_draft_report(result: dict, batch_id: str = "") -> str:
    ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")
    os.makedirs(_REPORT_DIR, exist_ok=True)
    path = os.path.join(_REPORT_DIR, f"c6b_department_checklist_draft_report_{ts}.md")

    if not batch_id:
        batch_id = result.get("batch_id", f"C6B-{ts}")

    lines = [
        "# C6B Department Checklist Draft Report",
        "",
        f"**Batch ID:** {batch_id}",
        f"**Generated:** {_now()}",
        f"**Mode:** {'DRY-RUN' if result['dry_run'] else 'EXECUTE'}",
        f"**Mock LLM:** {result.get('mock_llm', True)}",
        f"**Evidence context:** {result.get('include_evidence_context', True)}",
        "",
        "---",
        "",
        "## Overview",
        "",
        f"- **Input candidates:** {result['input_count']}",
        f"- **Skipped candidates:** {result['skipped_count']}",
        f"- **Checklist drafts generated:** {result['draft_count']}",
        f"- **Needs human review:** {result['needs_review_count']}",
        f"- **Linked evidence records:** {result['linked_evidence_count']}",
        "",
        "## Checklist by Type",
        "",
    ]
    for cl_type in sorted(result["by_type"].keys()):
        lines.append(f"- **{cl_type}:** {result['by_type'][cl_type]}")
    lines.append("")
    lines.append("## Checklist by Responsible Function")
    lines.append("")
    for func in sorted(result["by_function"].keys()):
        lines.append(f"- **{func}:** {result['by_function'][func]}")
    lines.append("")
    lines.append("## Checklist by Department")
    lines.append("")
    for dept in sorted(result["by_department"].keys()):
        lines.append(f"- **{dept}:** {result['by_department'][dept]}")
    lines.append("")

    if result.get("warnings"):
        lines.extend(["---", "", "## Warnings", ""])
        for w in result["warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    if result.get("errors"):
        lines.extend(["---", "", "## Errors", ""])
        for e in result["errors"]:
            lines.append(f"- {e}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## Source Traceability",
        "",
    ])
    for rec in result.get("records", [])[:10]:
        cl_id = rec.get("checklist_item_id", "?")
        gsp_id = rec.get("linked_gsp_standard_id", "?")
        crm_ids = rec.get("linked_customer_requirement_ids", [])
        ev_ids = rec.get("linked_evidence_ids", [])
        lines.append(
            f"- {cl_id} → {gsp_id} → CRM: {', '.join(crm_ids[:3]) if crm_ids else 'none'}"
            f"{' | Evidence: ' + ', '.join(ev_ids[:2]) if ev_ids else ''}"
        )
    if len(result.get("records", [])) > 10:
        lines.append(f"- ... and {len(result['records']) - 10} more")

    lines.extend([
        "",
        "---",
        "",
        "## ⚠️ IMPORTANT WARNING",
        "",
        "These checklist items are draft records generated by LLM semantic analysis.",
        "They do NOT approve compliance, SOPs, training, legal interpretation,",
        "customer overlay, or department todo.",
        "",
        "All checklist records are draft_pending_review and not_approved.",
        "Human review is required before checklists can be considered reliable.",
    ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path
