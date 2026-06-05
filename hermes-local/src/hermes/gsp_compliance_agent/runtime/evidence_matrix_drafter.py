"""
evidence_matrix_drafter.py — GSP Compliance Agent: C6A Evidence Matrix Draft Generation.

LLM-first semantic analysis of GSP Standard candidates to propose evidence requirements.
Code performs structure/validation only — LLM performs business reasoning.

Key principles:
- mock_llm=True by default in tests (deterministic output)
- dry_run=True by default; execute=False by default
- No write unless execute=True
- LLM output validated against evidence_matrix.schema.json
- Invalid LLM output creates needs_human_review record, not crash
- No hard-coded evidence mapping rules based on domain/principle
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
_EVIDENCE_DIR = os.path.join(_ROOT, "data", "knowledge", "compliance", "evidence_matrix")
_EVIDENCE_PATH = os.path.join(_EVIDENCE_DIR, "evidence_matrix.jsonl")
_DRY_RUN_DIR = os.path.join(_EVIDENCE_DIR, "dry_runs")
_REPORT_DIR = os.path.join(_EVIDENCE_DIR, "reports")

# ══════════════════════════════════════════════════════════════════
#  Valid evidence types (code may normalize labels, not decide content)
# ══════════════════════════════════════════════════════════════════

VALID_EVIDENCE_TYPES = {
    "policy_or_procedure", "work_instruction", "training_record",
    "attendance_or_system_export", "inspection_record", "maintenance_record",
    "risk_assessment", "permit_or_license", "monitoring_record",
    "incident_or_near_miss_record", "audit_record", "photo_or_visual_evidence",
    "supplier_or_subcontractor_record", "communication_record",
    "corrective_action_record", "other", "unknown",
}

VALID_FREQUENCIES = {
    "once", "daily", "weekly", "monthly", "quarterly", "annually",
    "per_shift", "per_batch", "as_needed", "upon_request", "ongoing", "unknown",
}

VALID_FORMATS = {
    "document", "spreadsheet", "photograph", "video", "system_export",
    "signed_form", "certificate", "log_book", "database_record",
    "email", "physical_sample", "other", "unknown",
}

VALID_RISK_LEVELS = {"critical", "high", "medium", "low", "unknown"}

# ══════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════


def _now() -> str:
    return datetime.now(_TZ).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _append_jsonl(path: str, record: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_jsonl(path: str) -> List[dict]:
    """Load all records from a JSONL file."""
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


def _find_record(path: str, record_id: str) -> Optional[dict]:
    """Find a record by ID field."""
    records = _load_jsonl(path)
    for rec in records:
        if rec.get("id") == record_id or rec.get("evidence_id") == record_id or rec.get("gsp_standard_id") == record_id:
            return rec
    return None


def load_crm_records(path: str = "") -> List[dict]:
    """Load CRM records from path or default location including sample fixtures."""
    if path and os.path.isfile(path):
        return _load_jsonl(path)
    return _load_jsonl(_CRM_PATH)


def load_crm_by_id(crm_id: str) -> Optional[dict]:
    """Find a CRM record by ID across all sources."""
    # Check main CRM file
    for rec in _load_jsonl(_CRM_PATH):
        if rec.get("id") == crm_id:
            return rec
    # Check sample fixtures
    sample_path = os.path.join(_ROOT, "data", "knowledge", "compliance",
                               "sample_records", "c5a_sample_crm_fixtures.jsonl")
    if os.path.isfile(sample_path):
        for rec in _load_jsonl(sample_path):
            if rec.get("id") == crm_id:
                return rec
    return None


def load_linked_crm(links: List[dict]) -> List[dict]:
    """Load CRM records referenced by source_customer_requirement_links."""
    results = []
    for link in (links or []):
        crm_id = link.get("crm_id", "")
        if crm_id:
            rec = load_crm_by_id(crm_id)
            if rec:
                results.append(rec)
    return results


def normalize_evidence_type(raw: str) -> str:
    """Normalize evidence type to a valid value. Returns 'other' if unrecognized."""
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in VALID_EVIDENCE_TYPES:
        return normalized
    # Try partial match
    for valid in VALID_EVIDENCE_TYPES:
        if valid.startswith(normalized) or normalized.startswith(valid):
            return valid
    return "other"


def normalize_frequency(raw: str) -> str:
    """Normalize frequency to a valid value."""
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in VALID_FREQUENCIES:
        return normalized
    return "unknown"


def normalize_format(raw: str) -> str:
    """Normalize format to a valid value."""
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in VALID_FORMATS:
        return normalized
    return "other"


def normalize_risk_level(raw: str) -> str:
    """Normalize risk level to a valid value."""
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in VALID_RISK_LEVELS:
        return normalized
    return "unknown"


def normalize_owner_function(raw: str) -> str:
    """Normalize owner function name."""
    mapping = {
        "ehs": "EHS",
        "environmental": "EHS",
        "health_safety": "EHS",
        "safety": "EHS",
        "human_resources": "HR",
        "hr": "HR",
        "production": "Production",
        "manufacturing": "Production",
        "quality": "QA",
        "qa": "QA",
        "quality_assurance": "QA",
        "maintenance": "Maintenance",
        "engineering": "Maintenance",
        "logistics": "Logistics",
        "warehouse": "Logistics",
        "training": "Training",
        "legal": "Legal",
        "compliance": "Compliance",
        "administration": "Administration",
        "admin": "Administration",
        "management": "Management",
    }
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return mapping.get(key, raw.strip().title())


# ══════════════════════════════════════════════════════════════════
#  Build LLM analysis input
# ══════════════════════════════════════════════════════════════════


def build_evidence_analysis_input(
    gsp_candidate: dict,
    linked_requirements: Optional[List[dict]] = None,
) -> dict:
    """Build the input dict for LLM evidence analysis.

    Extracts relevant fields from the GSP candidate and linked CRM records.
    Code only structures the data — LLM performs the semantic interpretation.
    """
    if linked_requirements is None:
        links = gsp_candidate.get("source_customer_requirement_links", [])
        linked_requirements = load_linked_crm(links)

    # Build CRM info for prompt
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

    # If no CRM records loaded from external sources, use links embedded in GSP candidate
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

    principle = gsp_candidate.get("gsp_principle", "PXX")
    domain = gsp_candidate.get("gsp_domain", "REV")

    principle_labels = {
        "P01": "Legal Compliance",
        "P02": "Forced Labour",
        "P03": "Child Labour & Young Workers",
        "P04": "Health & Safety",
        "P05": "Working Hours",
        "P06": "Wages & Benefits",
        "P07": "Freedom of Association",
        "P08": "Fire Safety & Emergency Preparedness",
        "P09": "Chemical Safety & Hazardous Substances",
        "P10": "Environmental Management",
        "PXX": "General / Other",
    }

    domain_labels = {
        "WH": "Working Hours", "WB": "Wages & Benefits",
        "SWM": "Safe Working Methods", "OHS": "Occupational Health & Safety",
        "FIRE": "Fire Safety", "CHEM": "Chemical Safety",
        "WASTE": "Waste Management", "CL": "Child Labour",
        "LR": "Labour Rights", "LEG": "Legal Compliance",
        "GOV": "Governance", "ENV": "Environmental",
        "REV": "Review / General",
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
            "gsp_owner_function": gsp_candidate.get("gsp_owner_function", ""),
            "gsp_responsible_departments": gsp_candidate.get("gsp_responsible_departments", []),
            "legal_dependency": gsp_candidate.get("legal_dependency", "needs_legal_review"),
            "notes": gsp_candidate.get("notes", ""),
        },
        "linked_customer_requirements": customer_reqs,
        "principle_label": f"{principle} - {principle_labels.get(principle, 'Unknown')}",
        "domain_label": f"{domain} - {domain_labels.get(domain, 'General')}",
    }


# ══════════════════════════════════════════════════════════════════
#  Mock LLM (for testing only)
# ══════════════════════════════════════════════════════════════════

_MOCK_RESPONSES = {
    "SWM": [
        {
            "evidence_title": "Risk Assessment Register",
            "evidence_requirement_statement": "A documented risk assessment covering all routine and non-routine tasks that can pose a health or safety risk, reviewed at least annually and updated when processes change.",
            "evidence_type": "risk_assessment",
            "evidence_owner_function": "EHS",
            "evidence_responsible_department": "EHS Department",
            "evidence_frequency": "annually",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Risk assessment document with identified hazards, risk ratings, control measures, review dates, and authorised signatures. Must cover all identified tasks in the facility.",
            "evidence_retention_requirement": "Minimum 3 years or until next IWAY audit",
            "risk_level": "critical",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "FIRE": [
        {
            "evidence_title": "Fire Extinguisher Inspection Log",
            "evidence_requirement_statement": "Monthly inspection records for all fire extinguishers in the facility, documenting location, condition, pressure gauge reading, and any maintenance actions taken.",
            "evidence_type": "inspection_record",
            "evidence_owner_function": "EHS",
            "evidence_responsible_department": "EHS Department",
            "evidence_frequency": "monthly",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Inspection log with dated entries for each extinguisher, signature of inspector, and documented follow-up for any deficiencies found.",
            "evidence_retention_requirement": "Minimum 12 months",
            "risk_level": "critical",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
        {
            "evidence_title": "Emergency Evacuation Drill Records",
            "evidence_requirement_statement": "Records of annual emergency evacuation drills including date, time, duration, participant count, observations, and corrective actions for any issues identified.",
            "evidence_type": "training_record",
            "evidence_owner_function": "EHS",
            "evidence_responsible_department": "EHS Department",
            "evidence_frequency": "annually",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Drill report with photographs, headcount records, evacuation time measurement, and sign-off by EHS manager. Corrective action plan for any issues found.",
            "evidence_retention_requirement": "Minimum 3 years",
            "risk_level": "critical",
            "uncertainty_notes": "Drill frequency may need to be higher for high-risk facilities. Check local regulations.",
            "needs_human_review": True,
        },
    ],
    "WH": [
        {
            "evidence_title": "Working Hours Records",
            "evidence_requirement_statement": "Complete and accurate records of actual working hours for all workers including regular hours, overtime hours, and rest days, demonstrating compliance with the 60-hour weekly maximum and one day off in seven.",
            "evidence_type": "attendance_or_system_export",
            "evidence_owner_function": "HR",
            "evidence_responsible_department": "HR Department",
            "evidence_frequency": "monthly",
            "evidence_format": "spreadsheet",
            "evidence_acceptance_criteria": "Time records showing daily and weekly totals for each worker, with overtime clearly identified. Weekly totals must not exceed 60 hours. At least one rest day per seven-day period must be evident.",
            "evidence_retention_requirement": "Minimum 2 years",
            "risk_level": "high",
            "uncertainty_notes": "National law may have stricter limits. Verify against local regulations.",
            "needs_human_review": True,
        },
        {
            "evidence_title": "Rest Day Schedule",
            "evidence_requirement_statement": "Published work schedule showing assigned rest days for all workers, demonstrating compliance with the requirement for at least one day off in every seven-day period.",
            "evidence_type": "policy_or_procedure",
            "evidence_owner_function": "HR",
            "evidence_responsible_department": "HR Department",
            "evidence_frequency": "weekly",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Schedule posted or available showing each worker's assigned rest days. Actual attendance records must match the schedule. Any deviations must be documented with justification.",
            "evidence_retention_requirement": "Minimum 1 year",
            "risk_level": "high",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "CL": [
        {
            "evidence_title": "Age Verification Records",
            "evidence_requirement_statement": "Copies of valid identity documents or equivalent age verification for all workers, demonstrating that no person below the minimum age of 15 (or 14 in ILO Convention 138 exception countries) is employed.",
            "evidence_type": "policy_or_procedure",
            "evidence_owner_function": "HR",
            "evidence_responsible_department": "HR Department",
            "evidence_frequency": "once",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Copy of each worker's government-issued ID or equivalent documented age verification. Must be maintained throughout employment and available for inspection.",
            "evidence_retention_requirement": "Duration of employment plus 2 years",
            "risk_level": "critical",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "WB": [
        {
            "evidence_title": "Wage Records and Payslips",
            "evidence_requirement_statement": "Records of wages paid to all workers including payslips showing gross pay, deductions, net pay, and hours worked, demonstrating compliance with minimum wage requirements.",
            "evidence_type": "attendance_or_system_export",
            "evidence_owner_function": "HR",
            "evidence_responsible_department": "HR Department",
            "evidence_frequency": "monthly",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Payslips provided to each worker in a language they understand. Records show wage rates equal to or above legal minimum wage or industry benchmark. Timely payment demonstrated.",
            "evidence_retention_requirement": "Minimum 3 years",
            "risk_level": "high",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "LR": [
        {
            "evidence_title": "Worker Representation Records",
            "evidence_requirement_statement": "Evidence of worker representation mechanisms such as trade union membership records, collective bargaining agreements, or alternative worker representation structures where trade union rights are restricted by law.",
            "evidence_type": "communication_record",
            "evidence_owner_function": "HR",
            "evidence_responsible_department": "HR Department",
            "evidence_frequency": "as_needed",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Documentation of worker committee elections, meeting minutes, collective bargaining agreements, or alternative representation structures. Must demonstrate worker access to representation without interference.",
            "evidence_retention_requirement": "Minimum 3 years",
            "risk_level": "high",
            "uncertainty_notes": "Legal restrictions on trade unions vary by country. Verify local law applicability.",
            "needs_human_review": True,
        },
    ],
    "CHEM": [
        {
            "evidence_title": "Chemical Inventory and SDS Register",
            "evidence_requirement_statement": "Complete inventory of all chemicals used, stored, or handled in the facility with corresponding Safety Data Sheets (SDS) available in the local language at each point of use.",
            "evidence_type": "monitoring_record",
            "evidence_owner_function": "EHS",
            "evidence_responsible_department": "EHS Department",
            "evidence_frequency": "quarterly",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Chemical inventory listing all substances with quantities and locations. SDS maintained for each chemical and available in local language at the point of use. Inventory updated when chemicals are added or removed.",
            "evidence_retention_requirement": "Minimum 5 years",
            "risk_level": "critical",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
        {
            "evidence_title": "Chemical Storage Inspection Records",
            "evidence_requirement_statement": "Records of regular inspections of chemical storage areas confirming proper labelling, secondary containment, segregation of incompatible substances, and restricted access.",
            "evidence_type": "inspection_record",
            "evidence_owner_function": "EHS",
            "evidence_responsible_department": "EHS Department",
            "evidence_frequency": "monthly",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Inspection checklist covering labelling completeness, containment integrity, segregation compliance, access control, and spill kit availability. Signed by inspector with corrective actions tracked.",
            "evidence_retention_requirement": "Minimum 2 years",
            "risk_level": "high",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "LEG": [
        {
            "evidence_title": "Legal Register / Permit Register",
            "evidence_requirement_statement": "A register of all applicable national and local laws, regulations, permits, licences, and registrations relevant to the facility's operations, with evidence of current validity.",
            "evidence_type": "permit_or_license",
            "evidence_owner_function": "Legal",
            "evidence_responsible_department": "Compliance Department",
            "evidence_frequency": "quarterly",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Register listing all applicable legal requirements with current validity status. Copies of all required permits, licences, and registrations available. Renewal dates tracked and upcoming renewals identified.",
            "evidence_retention_requirement": "Minimum 5 years",
            "risk_level": "critical",
            "uncertainty_notes": "Applicable laws vary by jurisdiction. Legal review recommended to confirm completeness of legal register.",
            "needs_human_review": True,
        },
    ],
    "OHS": [
        {
            "evidence_title": "PPE Issue and Training Records",
            "evidence_requirement_statement": "Records demonstrating that personal protective equipment (PPE) is provided free of charge, appropriate for identified hazards, and that workers are trained in proper use and maintenance.",
            "evidence_type": "training_record",
            "evidence_owner_function": "EHS",
            "evidence_responsible_department": "EHS Department",
            "evidence_frequency": "annually",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "PPE issue records showing each worker received appropriate PPE at no cost. Training records demonstrating competency in proper use, fitting, and maintenance of each PPE type. Refresher training at least annually.",
            "evidence_retention_requirement": "Minimum 3 years",
            "risk_level": "high",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "ENV": [
        {
            "evidence_title": "Environmental Policy and Aspect Register",
            "evidence_requirement_statement": "A documented environmental policy and register of significant environmental aspects and impacts identified for the facility's operations.",
            "evidence_type": "policy_or_procedure",
            "evidence_owner_function": "EHS",
            "evidence_responsible_department": "EHS Department",
            "evidence_frequency": "annually",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Environmental policy signed by management. Aspect and impact register covering all operational activities with significance ratings. Review and update records demonstrating annual review.",
            "evidence_retention_requirement": "Minimum 3 years",
            "risk_level": "medium",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
        {
            "evidence_title": "Waste Management Records",
            "evidence_requirement_statement": "Records demonstrating that waste is segregated by type, stored appropriately in designated areas, and disposed of through licensed contractors with proper waste manifests.",
            "evidence_type": "monitoring_record",
            "evidence_owner_function": "EHS",
            "evidence_responsible_department": "EHS Department",
            "evidence_frequency": "monthly",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Waste segregation records, storage area inspection reports, licensed contractor agreements, and waste disposal manifests or transfer notes for each waste shipment.",
            "evidence_retention_requirement": "Minimum 5 years",
            "risk_level": "medium",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "WASTE": [
        {
            "evidence_title": "Waste Management Records",
            "evidence_requirement_statement": "Records demonstrating that waste is segregated by type, stored appropriately, and disposed of through licensed contractors.",
            "evidence_type": "monitoring_record",
            "evidence_owner_function": "EHS",
            "evidence_responsible_department": "EHS Department",
            "evidence_frequency": "monthly",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Waste segregation records, storage area inspections, contractor licences, and disposal manifests.",
            "evidence_retention_requirement": "Minimum 5 years",
            "risk_level": "medium",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "GOV": [
        {
            "evidence_title": "Management Review Records",
            "evidence_requirement_statement": "Records of periodic management reviews covering compliance performance, audit results, corrective actions, and policy effectiveness.",
            "evidence_type": "audit_record",
            "evidence_owner_function": "Management",
            "evidence_responsible_department": "Management",
            "evidence_frequency": "annually",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "Meeting minutes, attendance records, agenda covering compliance topics, action items with assigned owners and deadlines.",
            "evidence_retention_requirement": "Minimum 3 years",
            "risk_level": "medium",
            "uncertainty_notes": "",
            "needs_human_review": False,
        },
    ],
    "REV": [
        {
            "evidence_title": "Supporting Documentation",
            "evidence_requirement_statement": "Documentation demonstrating implementation of this general requirement. Specific evidence type and format depend on the nature of the requirement and should be determined during review.",
            "evidence_type": "other",
            "evidence_owner_function": "Compliance",
            "evidence_responsible_department": "Compliance Department",
            "evidence_frequency": "unknown",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "To be determined during human review based on the specific requirement.",
            "evidence_retention_requirement": "To be determined",
            "risk_level": "medium",
            "uncertainty_notes": "This candidate maps to a general domain (REV). Evidence requirements require human interpretation.",
            "needs_human_review": True,
        },
    ],
}


def call_mock_llm(analysis_input: dict) -> dict:
    """Deterministic mock LLM for testing.

    Returns structured evidence proposals based on the GSP domain.
    This is a MOCK — it does NOT perform real semantic analysis.
    It exists only to test that the code structure works correctly.
    """
    domain = analysis_input.get("gsp_standard", {}).get("gsp_domain", "REV")
    gsp_id = analysis_input.get("gsp_standard", {}).get("gsp_standard_id", "unknown")

    proposed = _MOCK_RESPONSES.get(domain, _MOCK_RESPONSES["REV"])

    result = {
        "gsp_standard_id": gsp_id,
        "analysis_summary": f"Mock analysis for {domain} domain: "
                            f"Based on the GSP standard statement and linked customer requirements, "
                            f"the following evidence would demonstrate implementation.",
        "proposed_evidence": proposed,
        "_mock": True,
    }
    return result


# ══════════════════════════════════════════════════════════════════
#  Validate and normalize LLM output
# ══════════════════════════════════════════════════════════════════


def normalize_evidence_draft(llm_output: dict, gsp_candidate: dict) -> List[dict]:
    """Normalize LLM output into valid evidence draft records.

    Code validates structure and normalizes fields.
    Does NOT change semantic content — only formats and validates.
    """
    gsp_id = gsp_candidate.get("gsp_standard_id", "")
    samples = gsp_candidate.get("derivation_batch_id", "") or ""
    is_sample = "sample" in samples.lower()

    proposed = llm_output.get("proposed_evidence", [])
    if not proposed:
        # Create a needs_human_review placeholder
        proposed = [{
            "evidence_title": "Evidence Requirement (Human Review Required)",
            "evidence_requirement_statement": (
                f"LLM analysis did not produce specific evidence proposals for "
                f"{gsp_id}. Human review is required to determine appropriate evidence."
            ),
            "evidence_type": "other",
            "evidence_owner_function": "Compliance",
            "evidence_responsible_department": "Compliance Department",
            "evidence_frequency": "unknown",
            "evidence_format": "document",
            "evidence_acceptance_criteria": "To be determined during human review",
            "evidence_retention_requirement": "To be determined",
            "risk_level": "unknown",
            "uncertainty_notes": "No evidence proposals generated by LLM.",
            "needs_human_review": True,
        }]

    records = []
    now = _now()

    for i, ev in enumerate(proposed):
        seq = i + 1
        evidence_id = generate_evidence_id(gsp_id, seq)

        # Normalize values
        ev_type = normalize_evidence_type(ev.get("evidence_type", "other") or "other")
        freq = normalize_frequency(ev.get("evidence_frequency", "unknown") or "unknown")
        fmt = normalize_format(ev.get("evidence_format", "other") or "other")
        risk = normalize_risk_level(ev.get("risk_level", "unknown") or "unknown")
        owner = normalize_owner_function(ev.get("evidence_owner_function", "") or "")

        record = {
            "evidence_id": evidence_id,
            "version": 1,
            "gsp_standard_id": gsp_id,
            "gsp_standard_title": gsp_candidate.get("title", ""),
            "source_customer_requirement_links": gsp_candidate.get("source_customer_requirement_links", []),
            "source_original_text_refs": [],
            "evidence_title": str(ev.get("evidence_title", f"Evidence {seq}"))[:200],
            "evidence_requirement_statement": str(ev.get("evidence_requirement_statement", ""))[:2000],
            "evidence_type": ev_type,
            "evidence_owner_function": owner,
            "evidence_responsible_department": str(ev.get("evidence_responsible_department", ""))[:100],
            "evidence_frequency": freq,
            "evidence_format": fmt,
            "evidence_acceptance_criteria": str(ev.get("evidence_acceptance_criteria", ""))[:1000],
            "evidence_retention_requirement": str(ev.get("evidence_retention_requirement", ""))[:200],
            "risk_level": risk,
            "llm_reasoning_summary": str(llm_output.get("analysis_summary", ""))[:500],
            "uncertainty_notes": str(ev.get("uncertainty_notes", ""))[:500],
            "needs_human_review": bool(ev.get("needs_human_review", False)),
            "review_status": "draft_pending_review",
            "approval_status": "not_approved",
            "evidence_generation_method": "llm_semantic_analysis_mock" if llm_output.get("_mock") else "llm_semantic_analysis",
            "generated_by": "gsp_compliance_agent",
            "batch_id": "",
            "sample_only": is_sample,
            "created_by": "c6a_evidence_drafter",
            "created_at": now,
            "updated_at": now,
            "notes": f"Evidence draft {seq} for {gsp_id}. Generated by LLM semantic analysis.",
            # Legacy fields
            "id": evidence_id,
            "core_requirement_id": gsp_id,
            "status": "draft",
            "evidence_description": str(ev.get("evidence_requirement_statement", ""))[:2000],
        }

        records.append(record)

    return records


def validate_evidence_draft(evidence_record: dict) -> dict:
    """Validate an evidence draft record against required fields and valid values.

    Returns dict with: valid (bool), errors (list), warnings (list).
    """
    errors = []
    warnings = []

    required = ["evidence_id", "gsp_standard_id", "evidence_title", "evidence_type",
                "review_status", "approval_status"]
    for field in required:
        if not evidence_record.get(field):
            errors.append(f"Missing required field: {field}")

    if evidence_record.get("evidence_id") and not re.match(r'^EV-GSP-COM-', evidence_record["evidence_id"]):
        warnings.append(f"Evidence ID format may be non-standard: {evidence_record['evidence_id']}")

    ev_type = evidence_record.get("evidence_type", "")
    if ev_type and ev_type not in VALID_EVIDENCE_TYPES:
        warnings.append(f"Invalid evidence_type '{ev_type}', normalized to 'other'")

    freq = evidence_record.get("evidence_frequency", "")
    if freq and freq not in VALID_FREQUENCIES:
        warnings.append(f"Invalid evidence_frequency '{freq}'")

    fmt = evidence_record.get("evidence_format", "")
    if fmt and fmt not in VALID_FORMATS:
        warnings.append(f"Invalid evidence_format '{fmt}'")

    risk = evidence_record.get("risk_level", "")
    if risk and risk not in VALID_RISK_LEVELS:
        warnings.append(f"Invalid risk_level '{risk}'")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def generate_evidence_id(gsp_standard_id: str, sequence: int) -> str:
    """Generate a deterministic evidence ID from GSP standard ID and sequence.

    Format: EV-<gsp_standard_id>-<seq>
    Example: EV-GSP-COM-P04-SWM-001-001
    """
    return f"EV-{gsp_standard_id}-{sequence:03d}"


def _load_existing_evidence_ids(path: str) -> set:
    """Load existing evidence IDs for duplicate detection."""
    existing = set()
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    eid = rec.get("evidence_id", "") or rec.get("id", "")
                    if eid:
                        existing.add(eid)
                except json.JSONDecodeError:
                    pass
    return existing


# ══════════════════════════════════════════════════════════════════
#  Core drafting functions
# ══════════════════════════════════════════════════════════════════


def draft_evidence_for_gsp_candidate(
    gsp_candidate: dict,
    options: Optional[dict] = None,
) -> dict:
    """Generate evidence drafts for a single GSP standard candidate.

    Calls mock LLM (or real LLM if configured) to propose evidence requirements.
    Code validates structure, normalizes fields, and generates IDs.

    Args:
        gsp_candidate: A single GSP standard candidate dict from JSONL.
        options: Dict with keys:
            - mock_llm (bool): Use mock LLM (default: True)
            - llm_client (callable): Real LLM client function
            - include_needs_legal_review (bool): Include needs_legal_review candidates

    Returns:
        Dict with keys: ok, records, warnings, errors.
    """
    if options is None:
        options = {}

    mock_llm = options.get("mock_llm", True)
    include_legal = options.get("include_needs_legal_review", False)

    warnings = []
    errors = []

    # Check review_status eligibility
    status = gsp_candidate.get("review_status", "")
    if status == "rejected":
        return {"ok": True, "records": [], "warnings": ["Skipped rejected candidate."], "errors": []}
    if status == "correction_required":
        return {"ok": True, "records": [], "warnings": ["Skipped correction_required candidate."], "errors": []}
    if status == "needs_legal_review" and not include_legal:
        return {"ok": True, "records": [], "warnings": ["Skipped needs_legal_review candidate (use include_needs_legal_review=True)."], "errors": []}
    if status not in ("confirmed_for_internal_standard", "draft_pending_review", "needs_legal_review"):
        if status == "needs_legal_review" and include_legal:
            pass  # OK
        elif status == "draft_pending_review":
            pass  # OK (for source=sample_only)
        elif status == "confirmed_for_internal_standard":
            pass  # OK
        else:
            warnings.append(f"Unexpected review_status '{status}'. Proceeding with caution.")

    # Build analysis input
    analysis_input = build_evidence_analysis_input(gsp_candidate)

    # Call LLM (mock or real)
    if mock_llm:
        try:
            llm_output = call_mock_llm(analysis_input)
        except Exception as e:
            errors.append(f"Mock LLM error: {e}")
            llm_output = {
                "gsp_standard_id": gsp_candidate.get("gsp_standard_id", ""),
                "analysis_summary": "LLM analysis failed. Error: " + str(e),
                "proposed_evidence": [],
                "_mock": True,
            }
    else:
        # Real LLM — not yet implemented in this phase
        errors.append("Real LLM not implemented in C6A-Lite. Use --mock-llm.")
        return {"ok": False, "records": [], "warnings": warnings, "errors": errors}

    # Normalize LLM output into valid records
    try:
        records = normalize_evidence_draft(llm_output, gsp_candidate)
    except Exception as e:
        errors.append(f"Normalization error: {e}")
        return {"ok": False, "records": [], "warnings": warnings, "errors": errors}

    # Validate each record
    for record in records:
        validation = validate_evidence_draft(record)
        if not validation["valid"]:
            warnings.append(f"Validation warning for {record.get('evidence_id', '?')}: {validation['errors']}")
        warnings.extend(validation["warnings"])

    return {
        "ok": True,
        "records": records,
        "warnings": warnings,
        "errors": errors,
    }


def draft_evidence_batch(
    candidates: List[dict],
    batch_id: Optional[str] = None,
    dry_run: bool = True,
    mock_llm: bool = True,
    include_needs_legal_review: bool = False,
) -> dict:
    """Generate evidence drafts for a batch of GSP standard candidates.

    Args:
        candidates: List of GSP standard candidate dicts.
        batch_id: Optional batch identifier.
        dry_run: If True, only generate in memory, do not write.
        mock_llm: If True, use mock LLM for testing.
        include_needs_legal_review: If True, include needs_legal_review candidates.

    Returns:
        Dict with keys: ok, status, records, input_count, skipped_count,
        draft_count, by_type, by_owner, needs_review_count, warnings, errors,
        dry_run, batch_id, write_path.
    """
    now = _now()
    ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")

    if batch_id is None:
        batch_id = f"C6A-{ts}"

    result: Dict[str, Any] = {
        "ok": False,
        "status": "initialising",
        "records": [],
        "input_count": len(candidates),
        "skipped_count": 0,
        "draft_count": 0,
        "by_type": {},
        "by_owner": {},
        "needs_review_count": 0,
        "warnings": [],
        "errors": [],
        "dry_run": dry_run,
        "batch_id": batch_id,
        "mock_llm": mock_llm,
        "write_path": None,
    }

    for candidate in candidates:
        gsp_id = candidate.get("gsp_standard_id", "?")
        dri = draft_evidence_for_gsp_candidate(candidate, options={
            "mock_llm": mock_llm,
            "include_needs_legal_review": include_needs_legal_review,
        })

        if not dri["ok"]:
            result["errors"].append(f"Evidence draft error for {gsp_id}: {dri.get('errors', [])}")
            result["skipped_count"] += 1
            continue

        if not dri["records"]:
            # Candidate was skipped (rejected, correction_required, etc.)
            result["skipped_count"] += 1
            if dri["warnings"]:
                result["warnings"].append(f"{gsp_id}: {dri['warnings'][0]}")
            continue

        # Add batch_id to each record
        for rec in dri["records"]:
            rec["batch_id"] = batch_id

        result["records"].extend(dri["records"])
        result["draft_count"] += len(dri["records"])
        result["warnings"].extend(dri["warnings"])
        result["errors"].extend(dri["errors"])

        # Count by type and owner
        for rec in dri["records"]:
            ev_type = rec.get("evidence_type", "other")
            result["by_type"][ev_type] = result["by_type"].get(ev_type, 0) + 1

            owner = rec.get("evidence_owner_function", "Unknown")
            result["by_owner"][owner] = result["by_owner"].get(owner, 0) + 1

            if rec.get("needs_human_review"):
                result["needs_review_count"] += 1

    # Detect duplicates against existing evidence_matrix.jsonl
    if not dry_run and result["records"]:
        existing_ids = _load_existing_evidence_ids(_EVIDENCE_PATH)
        deduped = []
        for rec in result["records"]:
            eid = rec.get("evidence_id", "")
            if eid in existing_ids:
                result["warnings"].append(f"Duplicate evidence_id '{eid}' skipped.")
                continue
            deduped.append(rec)
        result["records"] = deduped
        result["draft_count"] = len(deduped)

    result["status"] = "ready" if dry_run else "written"
    result["write_path"] = None if dry_run else _EVIDENCE_PATH

    if not dry_run:
        ok = write_evidence_drafts(result["records"], execute=True)
        result["ok"] = ok
    else:
        result["ok"] = True

    return result


def write_evidence_drafts(records: List[dict], execute: bool = False) -> bool:
    """Write evidence draft records to evidence_matrix.jsonl.

    Only writes if execute=True.
    Returns True if write was performed and successful.
    """
    if not execute:
        return False

    if not records:
        return True

    try:
        os.makedirs(os.path.dirname(_EVIDENCE_PATH), exist_ok=True)
        existing_ids = _load_existing_evidence_ids(_EVIDENCE_PATH)

        for rec in records:
            eid = rec.get("evidence_id", "")
            if eid in existing_ids:
                _logger.warning("Duplicate evidence_id '%s' skipped during write.", eid)
                continue
            _append_jsonl(_EVIDENCE_PATH, rec)
            existing_ids.add(eid)

        return True
    except Exception as e:
        _logger.error("Failed to write evidence drafts: %s", e)
        return False


# ══════════════════════════════════════════════════════════════════
#  Dry-run and report generation
# ══════════════════════════════════════════════════════════════════


def write_dry_run_output(result: dict) -> str:
    """Write dry-run JSON output."""
    ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")
    os.makedirs(_DRY_RUN_DIR, exist_ok=True)
    path = os.path.join(_DRY_RUN_DIR, f"c6a_evidence_draft_dry_run_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


def generate_evidence_draft_report(result: dict, batch_id: str = "") -> str:
    """Generate a markdown report for the evidence draft run."""
    ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")
    os.makedirs(_REPORT_DIR, exist_ok=True)
    path = os.path.join(_REPORT_DIR, f"c6a_evidence_matrix_draft_report_{ts}.md")

    if not batch_id:
        batch_id = result.get("batch_id", f"C6A-{ts}")

    lines = [
        "# C6A Evidence Matrix Draft Report",
        "",
        f"**Batch ID:** {batch_id}",
        f"**Generated:** {_now()}",
        f"**Mode:** {'DRY-RUN' if result['dry_run'] else 'EXECUTE'}",
        f"**Mock LLM:** {result.get('mock_llm', True)}",
        "",
        "---",
        "",
        "## Overview",
        "",
        f"- **Input candidates:** {result['input_count']}",
        f"- **Skipped candidates:** {result['skipped_count']}",
        f"- **Evidence drafts generated:** {result['draft_count']}",
        f"- **Needs human review:** {result['needs_review_count']}",
        "",
        "## Evidence by Type",
        "",
    ]
    for ev_type in sorted(result["by_type"].keys()):
        lines.append(f"- **{ev_type}:** {result['by_type'][ev_type]}")
    lines.append("")
    lines.append("## Evidence by Owner Function")
    lines.append("")
    for owner in sorted(result["by_owner"].keys()):
        lines.append(f"- **{owner}:** {result['by_owner'][owner]}")
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

    # Traceability summary
    lines.extend([
        "---",
        "",
        "## Source Traceability",
        "",
    ])
    for rec in result.get("records", [])[:10]:
        gsp_id = rec.get("gsp_standard_id", "?")
        ev_id = rec.get("evidence_id", "?")
        links = rec.get("source_customer_requirement_links", [])
        crm_ids = [l.get("crm_id", "?") for l in links]
        lines.append(f"- {ev_id} → {gsp_id} → CRM: {', '.join(crm_ids) if crm_ids else 'none'}")
    if len(result.get("records", [])) > 10:
        lines.append(f"- ... and {len(result['records']) - 10} more")

    lines.extend([
        "",
        "---",
        "",
        "## ⚠️ IMPORTANT WARNING",
        "",
        "These evidence requirements are draft records generated by LLM semantic analysis.",
        "They do NOT approve compliance, SOPs, checklists, training, legal interpretation,",
        "or customer overlay.",
        "",
        "All evidence records are draft_pending_review and not_approved.",
        "Human review is required before evidence can be considered reliable.",
    ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return path
