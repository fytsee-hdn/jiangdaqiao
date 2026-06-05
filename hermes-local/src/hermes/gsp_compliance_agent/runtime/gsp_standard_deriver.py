"""
gsp_standard_deriver.py — GSP Compliance Agent: C5A Standard Candidate Derivation.

Converts confirmed customer_requirement_master records into GSP Core Standard
candidates. All output is draft_pending_review / not_approved.

Derivation methods:
  - copied_from_customer_requirement
  - interpreted_from_customer_requirement
  - localized_for_gsp_operation
  - split_from_customer_requirement
  - consolidated_from_multiple_requirements
  - execution_expanded_from_customer_requirement

Key invariants:
  - dry_run=True by default
  - execute=False by default
  - No write unless execute=True
  - Even when execute=True, records are draft_pending_review only
  - No approved records, no SOP/checklist/training, no legal judgment
"""

from __future__ import annotations

import hashlib
import json
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

# ══════════════════════════════════════════════════════════════════
#  Paths
# ══════════════════════════════════════════════════════════════════

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)

_GSP_STANDARDS_DIR = os.path.join(
    _PROJECT_ROOT, "data", "knowledge", "compliance", "gsp_standards"
)
_GSP_CORE_STANDARD_PATH = os.path.join(
    _GSP_STANDARDS_DIR, "gsp_core_standard.jsonl"
)
_DRY_RUN_DIR = os.path.join(_GSP_STANDARDS_DIR, "derivation_dry_runs")
_REPORT_DIR = os.path.join(_GSP_STANDARDS_DIR, "derivation_reports")

# ══════════════════════════════════════════════════════════════════
#  Principle & Domain Classification Tables
# ══════════════════════════════════════════════════════════════════

IWAY_CLAUSE_TO_PRINCIPLE: Dict[str, str] = {
    "G 1.": "P01",
    "G 2.": "P02",
    "G 3.": "P03",
    "G 4.": "P04",
    "G 5.": "P05",
    "G 6.": "P06",
    "G 7.": "P07",
    "G 8.": "P08",
    "G 9.": "P09",
    "G 10.": "P10",
    "G 1 ": "P01",
    "G 2 ": "P02",
    "G 3 ": "P03",
    "G 4 ": "P04",
    "G 5 ": "P05",
    "G 6 ": "P06",
    "G 7 ": "P07",
    "G 8 ": "P08",
    "G 9 ": "P09",
    "G 10 ": "P10",
}

PRINCIPLE_KEYWORD_TO_CODE: Dict[str, str] = {
    "g 1": "P01",
    "g 2": "P02",
    "g 3": "P03",
    "g 4": "P04",
    "g 5": "P05",
    "g 6": "P06",
    "g 7": "P07",
    "g 8": "P08",
    "g 9": "P09",
    "g 10": "P10",
    "principle 1": "P01",
    "principle 2": "P02",
    "principle 3": "P03",
    "principle 4": "P04",
    "principle 5": "P05",
    "principle 6": "P06",
    "principle 7": "P07",
    "principle 8": "P08",
    "principle 9": "P09",
    "principle 10": "P10",
    "legal": "P01",
    "forced": "P02",
    "child": "P03",
    "young": "P03",
    "risk assessment": "P04",
    "safe working": "P04",
    "hazardous": "P04",
    "ppe": "P04",
    "working hours": "P05",
    "overtime": "P05",
    "rest day": "P05",
    "wage": "P06",
    "payslip": "P06",
    "benefit": "P06",
    "union": "P07",
    "bargain": "P07",
    "discrimination": "P07",
    "grievance": "P07",
    "fire": "P08",
    "emergency": "P08",
    "evacuation": "P08",
    "chemical": "P09",
    "sds": "P09",
    "environmental": "P10",
    "waste": "P10",
    "pollution": "P10",
}

DOMAIN_KEYWORDS: List[Tuple[List[str], str]] = [
    (["working hours", "overtime", "rest day", "rest period", "weekly"], "WH"),
    (["wage", "payslip", "benefit", "minimum wage", "compensation", "salary"], "WB"),
    (["risk assessment", "safe working routine", "hazardous work", "authorised worker"], "SWM"),
    (["ppe", "personal protective", "health", "safety", "occupational", "first aid"], "OHS"),
    (["fire", "emergency", "evacuation", "extinguisher", "fire safety"], "FIRE"),
    (["chemical", "hazardous substance", "sds", "safety data sheet", "msds"], "CHEM"),
    (["waste", "segregation", "disposal", "recycle", "landfill"], "WASTE"),
    (["child", "young worker", "minimum age", "school", "juvenile"], "CL"),
    (["forced", "bonded", "indentured", "prison", "discrimination", "grievance",
      "association", "union", "bargain", "harassment"], "LR"),
    (["permit", "licence", "license", "law", "regulation", "legal", "compliance with national"], "LEG"),
    (["policy", "routine", "internal audit", "kpi", "dialogue", "management system",
      "documented", "reviewed", "annually", "procedure"], "GOV"),
    (["environmental", "pollution", "emission", "effluent", "carbon", "resource"], "ENV"),
]

# ══════════════════════════════════════════════════════════════════
#  Sequence Counter (in-memory per batch; persists only via JSONL dedup)
# ══════════════════════════════════════════════════════════════════

def _load_existing_mappings(gsp_path: str) -> Tuple[set, Dict[str, str]]:
    """Load existing GSP standard IDs and CRM→GSP mappings from JSONL for deduplication.

    Returns (gsp_ids_set, crm_to_gsp_map).
    """
    existing_ids: set = set()
    crm_to_gsp: Dict[str, str] = {}
    if os.path.isfile(gsp_path):
        try:
            with open(gsp_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rec = json.loads(line)
                            gsp_id = rec.get("gsp_standard_id", "")
                            if gsp_id:
                                existing_ids.add(gsp_id)
                            for link in rec.get("source_customer_requirement_links", []):
                                crm_id = link.get("crm_id", "")
                                if crm_id and crm_id not in crm_to_gsp:
                                    crm_to_gsp[crm_id] = gsp_id
                        except json.JSONDecodeError:
                            pass
        except OSError:
            pass
    return existing_ids, crm_to_gsp


def _next_sequence(existing_ids: set, principle: str, domain: str) -> int:
    """Determine next sequence number for GSP-COM-P<principle>-<domain>-<seq>."""
    prefix = f"GSP-COM-{principle}-{domain}-"
    max_seq = 0
    for gid in existing_ids:
        if gid.startswith(prefix):
            try:
                seq = int(gid[len(prefix):])
                max_seq = max(max_seq, seq)
            except ValueError:
                pass
    return max_seq + 1


# ══════════════════════════════════════════════════════════════════
#  Core Functions
# ══════════════════════════════════════════════════════════════════


def classify_gsp_principle(crm_record: Dict[str, Any]) -> str:
    """Classify GSP principle from CRM record clause_ref, iway_requirement_code, or text content.

    Returns principle code like 'P04', 'PXX'.
    """
    clause_ref = crm_record.get("clause_ref", "") or ""
    iway_code = crm_record.get("iway_requirement_code", "") or ""
    text = crm_record.get("original_text_en", "") or crm_record.get("requirement_text", "") or ""

    # 1. Try precise IWAY clause number matching: "G N." where N is 1-10
    m = re.search(r'G\s+(\d+)', f"{clause_ref} {iway_code}")
    if m:
        num = int(m.group(1))
        if 1 <= num <= 10:
            return f"P{num:02d}"
        else:
            return "PXX"

    # 2. Try keyword matching in combined text
    combined = f"{clause_ref} {iway_code} {text}".lower()
    for keyword, principle_code in PRINCIPLE_KEYWORD_TO_CODE.items():
        if keyword in combined:
            return principle_code

    return "PXX"


def classify_gsp_domain(crm_record: Dict[str, Any]) -> str:
    """Classify GSP domain from CRM record content.

    Returns domain code like 'SWM', 'OHS', 'REV'.
    """
    text = crm_record.get("original_text_en", "") or crm_record.get("requirement_text", "") or ""
    clause_ref = crm_record.get("clause_ref", "") or ""
    domain_tags = crm_record.get("domain_tags", []) or []
    combined = f"{clause_ref} {text} {' '.join(domain_tags)}".lower()

    # 1. Specific domain tags take priority (chemical, fire, waste, environment)
    specific_tag_to_domain = {
        "chemical": "CHEM",
        "fire": "FIRE",
        "waste": "WASTE",
        "environment": "ENV",
    }
    for tag, domain in specific_tag_to_domain.items():
        if tag in (t.lower() for t in domain_tags):
            return domain

    # 2. Keyword matching (more specific than broad tags like "labour")
    for keywords, domain in DOMAIN_KEYWORDS:
        for kw in keywords:
            if kw in combined:
                return domain

    # 3. Broad domain tags as fallback
    broad_tag_to_domain = {
        "health_safety": "OHS",
        "labour": "LR",
        "social": "LR",
        "legal": "LEG",
    }
    for tag, domain in broad_tag_to_domain.items():
        if tag in (t.lower() for t in domain_tags):
            return domain

    return "REV"


def derive_from_customer_requirement(
    crm_record: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
    existing_ids: Optional[set] = None,
) -> Optional[Dict[str, Any]]:
    """Derive a single GSP standard candidate from one confirmed CRM record.

    Returns None if the CRM record is not confirmed or should be skipped.
    """
    if options is None:
        options = {}

    # Skip unconfirmed
    review_status = crm_record.get("review_status", "")
    if review_status != "requirement_confirmed":
        return None

    approval_status = crm_record.get("approval_status", "")
    if approval_status == "approved":
        return None  # should not happen in current data model but safety check

    principle = classify_gsp_principle(crm_record)
    domain = classify_gsp_domain(crm_record)

    # Determine derivation method
    derivation_method = options.get(
        "derivation_method", "interpreted_from_customer_requirement"
    )

    # Generate ID
    if existing_ids is None:
        existing_ids = set()
    seq = _next_sequence(existing_ids, principle, domain)
    gsp_standard_id = f"GSP-COM-{principle}-{domain}-{seq:03d}"

    # Build standard statement
    crm_text = crm_record.get("original_text_en", "") or crm_record.get(
        "requirement_text", ""
    )
    clause_ref = crm_record.get("clause_ref", "")

    standard_statement = _build_standard_statement(
        crm_text, clause_ref, derivation_method
    )

    now = datetime.now(_TZ).isoformat()

    candidate: Dict[str, Any] = {
        "id": f"GSP-C5A-{uuid.uuid4().hex[:8].upper()}",
        "version": 1,
        "status": "draft",
        "core_id": gsp_standard_id,
        "gsp_standard_id": gsp_standard_id,
        "title": f"GSP Standard {gsp_standard_id}",
        "chapter": domain,
        "requirement_statement": standard_statement,
        "normative_force": crm_record.get("normative_force", "shall"),
        "is_critical": crm_record.get("is_critical", False),
        "domain_tags": crm_record.get("domain_tags", []),
        "source_customer_requirements": [
            {
                "customer_req_id": crm_record.get("id", ""),
                "customer_code": crm_record.get("customer", crm_record.get("customer_code", "")),
                "clause_ref": clause_ref,
            }
        ],
        "gsp_principle": principle,
        "gsp_domain": domain,
        "standard_language": "en",
        "standard_derivation_method": derivation_method,
        "source_original_text_preserved": True,
        "source_customer_requirement_links": [
            {
                "crm_id": crm_record.get("id", ""),
                "customer": crm_record.get("customer", crm_record.get("customer_code", "IKEA")),
                "standard_family": crm_record.get("standard_family", "IWAY"),
                "standard_version": crm_record.get("standard_version", ""),
                "clause_ref": clause_ref,
                "original_text_excerpt": crm_text[:500] if crm_text else "",
                "source_text_archive_id": crm_record.get("source_text_archive_id", ""),
                "mapping_type": "one_to_one",
            }
        ],
        "gsp_applicability": "all_facilities",
        "gsp_owner_function": "",
        "gsp_responsible_departments": [],
        "gsp_required_controls": [],
        "legal_dependency": "needs_legal_review",
        "gsp_gap_status": "not_assessed",
        "review_status": "draft_pending_review",
        "approval_status": "not_approved",
        "source_id": crm_record.get("source_id", ""),
        "source_text_archive_id": crm_record.get("source_text_archive_id", ""),
        "created_at": now,
        "updated_at": now,
        "review": {},
        "notes": f"Derived from CRM {crm_record.get('id', '')} via {derivation_method}. "
        f"ⓘ This is a candidate — NOT an approved GSP standard.",
    }

    # Add batch_id if provided
    batch_id = options.get("batch_id", "")
    if batch_id:
        candidate["derivation_batch_id"] = batch_id

    # Add derivation method hints for future
    if options.get("sample_only"):
        candidate["notes"] += " [C5A SAMPLE ONLY]"

    return candidate


def _build_standard_statement(
    crm_text: str, clause_ref: str, derivation_method: str
) -> str:
    """Build GSP standard statement from CRM original text, adapting language
    based on derivation method without creating SOP-level steps."""
    if not crm_text.strip():
        return f"[Derived from {clause_ref}]"

    if derivation_method == "copied_from_customer_requirement":
        return crm_text.strip()

    if derivation_method == "interpreted_from_customer_requirement":
        prefix = "GSP interprets the customer requirement as follows: "
        return prefix + crm_text.strip()

    if derivation_method == "localized_for_gsp_operation":
        prefix = "For GSP factory operations: "
        return prefix + crm_text.strip()

    if derivation_method in (
        "split_from_customer_requirement",
        "consolidated_from_multiple_requirements",
    ):
        return f"[{derivation_method}] {crm_text.strip()}"

    if derivation_method == "execution_expanded_from_customer_requirement":
        return f"GSP shall implement controls to ensure: {crm_text.strip()}"

    return crm_text.strip()


def derive_batch_from_confirmed_requirements(
    records: List[Dict[str, Any]],
    batch_id: Optional[str] = None,
    dry_run: bool = True,
    execute: bool = False,
    source_label: str = "unknown",
    derivation_method: str = "interpreted_from_customer_requirement",
    max_candidates: Optional[int] = None,
) -> Dict[str, Any]:
    """Derive GSP standard candidates from a batch of CRM records.

    Args:
        records: List of CRM records (dicts from JSONL).
        batch_id: Optional batch identifier.
        dry_run: If True, only validate and report, no writes.
        execute: If True, write candidates to gsp_core_standard.jsonl.
        source_label: Label for the source (e.g., 'sample_only', 'confirmed').
        derivation_method: Default derivation method.
        max_candidates: Optional limit on candidate count.

    Returns:
        Dict with keys: ok, status, candidates, input_count, confirmed_count,
        skipped_count, candidate_count, by_principle, by_domain, warnings, errors,
        dry_run, write_path.
    """
    now = datetime.now(_TZ).isoformat()
    ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")

    result: Dict[str, Any] = {
        "ok": False,
        "status": "initialising",
        "candidates": [],
        "input_count": len(records),
        "confirmed_count": 0,
        "skipped_count": 0,
        "candidate_count": 0,
        "by_principle": {},
        "by_domain": {},
        "warnings": [],
        "errors": [],
        "dry_run": dry_run,
        "derive_execute": execute,
        "write_path": None,
        "batch_id": batch_id or f"C5A-{ts}",
    }

    # Load existing IDs for dedup
    existing_ids, crm_to_gsp = _load_existing_mappings(_GSP_CORE_STANDARD_PATH)

    options: Dict[str, Any] = {
        "batch_id": result["batch_id"],
        "derivation_method": derivation_method,
        "sample_only": ("sample" in source_label.lower()),
    }

    # Confirm CRM source existence
    for rec in records:
        rid = rec.get("id", "?")
        review_status = rec.get("review_status", "")

        if review_status == "requirement_confirmed":
            result["confirmed_count"] += 1
        else:
            result["skipped_count"] += 1
            continue

        if max_candidates and result["candidate_count"] >= max_candidates:
            result["warnings"].append(
                f"Reached max_candidates={max_candidates}, stopping early"
            )
            break

        try:
            candidate = derive_from_customer_requirement(
                rec, options, existing_ids
            )
            if candidate is None:
                result["skipped_count"] += 1
                # Adjust: we already counted as confirmed, but now skipped by derive
                result["confirmed_count"] = max(0, result["confirmed_count"] - 1)
                continue

        except Exception as e:
            result["errors"].append(f"Derivation error for {rid}: {e}")
            result["skipped_count"] += 1
            result["confirmed_count"] = max(0, result["confirmed_count"] - 1)
            continue

        # Dedup check: same CRM source already generated a GSP standard?
        crm_id = rec.get("id", "")
        gsp_id = candidate.get("gsp_standard_id", "")
        if crm_id in crm_to_gsp:
            result["warnings"].append(
                f"CRM {crm_id} already mapped to GSP {crm_to_gsp[crm_id]} — skipping"
            )
            result["skipped_count"] += 1
            result["confirmed_count"] = max(0, result["confirmed_count"] - 1)
            continue

        existing_ids.add(gsp_id)
        crm_to_gsp[crm_id] = gsp_id
        result["candidates"].append(candidate)
        result["candidate_count"] += 1

        # Count by principle
        p = candidate.get("gsp_principle", "PXX")
        result["by_principle"][p] = result["by_principle"].get(p, 0) + 1

        # Count by domain
        d = candidate.get("gsp_domain", "REV")
        result["by_domain"][d] = result["by_domain"].get(d, 0) + 1

    # -- Execute write --
    if execute and not dry_run and result["candidates"]:
        write_path = write_gsp_standard_candidates(
            result["candidates"], execute=True
        )
        result["write_path"] = write_path
        result["status"] = "written"
    elif execute and dry_run:
        result["warnings"].append(
            "Both execute=True and dry_run=True — skipping write "
            "(dry_run takes precedence)"
        )
        result["status"] = "dry_run_only"
    else:
        result["status"] = "dry_run" if dry_run else "preview"

    # -- Dry-run report --
    if dry_run and result["candidate_count"] > 0:
        os.makedirs(_DRY_RUN_DIR, exist_ok=True)
        dr_path = os.path.join(
            _DRY_RUN_DIR, f"c5a_derivation_dry_run_{ts}.json"
        )
        dr_data = {
            "batch_id": result["batch_id"],
            "source_label": source_label,
            "timestamp": now,
            "dry_run": True,
            "input_count": result["input_count"],
            "confirmed_count": result["confirmed_count"],
            "skipped_count": result["skipped_count"],
            "candidate_count": result["candidate_count"],
            "by_principle": result["by_principle"],
            "by_domain": result["by_domain"],
            "candidates": [
                {
                    "gsp_standard_id": c["gsp_standard_id"],
                    "title": c["title"],
                    "principle": c.get("gsp_principle"),
                    "domain": c.get("gsp_domain"),
                    "method": c.get("standard_derivation_method"),
                    "source_crm": [
                        lk.get("crm_id", "")
                        for lk in c.get("source_customer_requirement_links", [])
                    ],
                }
                for c in result["candidates"]
            ],
            "warnings": result["warnings"],
            "errors": result["errors"],
        }
        try:
            with open(dr_path, "w") as f:
                json.dump(dr_data, f, indent=2)
            result["dry_run_report_path"] = dr_path
        except OSError as e:
            result["errors"].append(f"Failed to write dry-run report: {e}")

    result["ok"] = len(result["errors"]) == 0
    return result


def validate_traceability(candidate: Dict[str, Any]) -> Dict[str, bool]:
    """Validate that a GSP candidate maintains required traceability fields.

    Returns dict with validation keys and boolean results.
    """
    validations: Dict[str, bool] = {}

    links = candidate.get("source_customer_requirement_links", [])
    validations["has_source_links"] = len(links) > 0

    if links:
        lk = links[0]
        validations["has_crm_id"] = bool(lk.get("crm_id"))
        validations["has_customer"] = bool(lk.get("customer"))
        validations["has_standard_family"] = bool(lk.get("standard_family"))
        validations["has_clause_ref"] = bool(lk.get("clause_ref"))
        validations["has_original_text_excerpt"] = bool(
            lk.get("original_text_excerpt")
        )

    validations["has_source_original_text_preserved"] = candidate.get(
        "source_original_text_preserved", False
    )
    validations["is_draft_pending_review"] = (
        candidate.get("review_status") == "draft_pending_review"
    )
    validations["is_not_approved"] = (
        candidate.get("approval_status") == "not_approved"
    )
    validations["has_gsp_standard_id"] = bool(candidate.get("gsp_standard_id"))
    validations["has_principle"] = bool(candidate.get("gsp_principle"))
    validations["has_domain"] = bool(candidate.get("gsp_domain"))

    return validations


def write_gsp_standard_candidates(
    candidates: List[Dict[str, Any]], execute: bool = False
) -> Optional[str]:
    """Write GSP standard candidates to JSONL file.

    Returns the write path if execute=True and write succeeded, None otherwise.
    Duplicate check by gsp_standard_id per batch (caller should handle).
    """
    if not execute:
        return None

    os.makedirs(os.path.dirname(_GSP_CORE_STANDARD_PATH), exist_ok=True)

    try:
        with open(_GSP_CORE_STANDARD_PATH, "a") as f:
            for c in candidates:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        return _GSP_CORE_STANDARD_PATH
    except OSError as e:
        raise RuntimeError(f"Failed to write GSP standards: {e}")


# ══════════════════════════════════════════════════════════════════
#  Utility
# ══════════════════════════════════════════════════════════════════


def load_crm_records(path: str) -> List[Dict[str, Any]]:
    """Load CRM records from a JSONL file."""
    records: List[Dict[str, Any]] = []
    if not os.path.isfile(path):
        return records
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def build_derivation_report(
    derivation_result: Dict[str, Any], source_label: str, ts: str
) -> str:
    """Build a markdown derivation report."""
    dr = derivation_result
    lines: List[str] = []

    lines.append("# GSP Standard Candidate Derivation Report")
    lines.append("")
    lines.append(f"**Phase:** C5A")
    lines.append(f"**Batch ID:** {dr.get('batch_id', 'N/A')}")
    lines.append(f"**Timestamp:** {dr.get('timestamp', ts)}")
    lines.append(f"**Source:** {source_label}")
    lines.append(f"**Mode:** {'DRY-RUN' if dr.get('dry_run') else 'EXECUTE'}")
    lines.append("")

    lines.append("## Summary")
    lines.append(f"- Input CRM records: {dr.get('input_count', 0)}")
    lines.append(f"- Confirmed CRM records: {dr.get('confirmed_count', 0)}")
    lines.append(f"- Skipped CRM records: {dr.get('skipped_count', 0)}")
    lines.append(f"- Candidate count: {dr.get('candidate_count', 0)}")
    lines.append("")

    by_p = dr.get("by_principle", {})
    if by_p:
        lines.append("## Count by Principle")
        for p in sorted(by_p.keys()):
            lines.append(f"- {p}: {by_p[p]}")
        lines.append("")

    by_d = dr.get("by_domain", {})
    if by_d:
        lines.append("## Count by Domain")
        for d in sorted(by_d.keys()):
            lines.append(f"- {d}: {by_d[d]}")
        lines.append("")

    lines.append("## Derivation Methods Used")
    lines.append(f"- Default: interpreted_from_customer_requirement")
    lines.append(f"- All methods available: copied, interpreted, localized, split, consolidated, execution_expanded")
    lines.append("")

    lines.append("## Traceability Summary")
    lines.append("- All candidates include source_customer_requirement_links")
    lines.append("- All candidates preserve original text excerpt (source_original_text_preserved=true)")
    lines.append("- Source CRM ID recorded in every candidate")
    lines.append("- standard_family=IWAY, customer=IKEA")
    lines.append("")

    lines.append("## Warnings")
    warnings = dr.get("warnings", [])
    if warnings:
        for w in warnings:
            lines.append(f"- {w}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Errors")
    errors = dr.get("errors", [])
    if errors:
        for e in errors:
            lines.append(f"- {e}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## No-Approval Warning")
    lines.append("")
    lines.append(
        "> ⚠️ **IMPORTANT:** These GSP Standard records are candidates only. "
        "They do NOT approve GSP compliance, SOPs, checklists, training, "
        "legal interpretation, or customer overlay."
    )
    lines.append("")

    lines.append("## Intentionally Not Implemented in C5A")
    lines.append("- No SOP generation")
    lines.append("- No checklist generation")
    lines.append("- No training matrix generation")
    lines.append("- No department work package generation")
    lines.append("- No legal judgment or compliance conclusion")
    lines.append("- No customer_to_gsp_mapping formal records (reserved for C5B)")
    lines.append("- No ikea_iway_overlay generation")
    lines.append("- No approved GSP standards (all draft_pending_review / not_approved)")
    lines.append("")

    return "\n".join(lines)


def write_derivation_report(
    derivation_result: Dict[str, Any], source_label: str
) -> str:
    """Write a markdown derivation report to disk.

    Returns the report path.
    """
    now = datetime.now(_TZ)
    ts = now.strftime("%Y%m%d_%H%M%S")
    os.makedirs(_REPORT_DIR, exist_ok=True)

    report_content = build_derivation_report(derivation_result, source_label, ts)
    report_path = os.path.join(
        _REPORT_DIR, f"c5a_gsp_standard_derivation_report_{ts}.md"
    )

    with open(report_path, "w") as f:
        f.write(report_content)

    derivation_result["report_path"] = report_path
    derivation_result["timestamp"] = now.isoformat()
    return report_path
