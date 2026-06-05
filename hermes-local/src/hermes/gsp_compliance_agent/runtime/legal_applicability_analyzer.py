"""
legal_applicability_analyzer.py — GSP Compliance Agent: LLM-first legal applicability analysis.

Provides functions to build LLM input from legal text/index records,
call the LLM (or mock), normalize output, and draft applicable_legal_requirement
records.

Key principles:
- mock_llm=True by default in tests
- dry_run=True by default
- execute=False by default
- All outputs have review_status=applicability_pending_review
- All outputs have approval_status=not_approved
- No final legal judgment
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from hermes.gsp_compliance_agent.runtime.compliance_data_paths import (
    resolve_compliance_path,
    ensure_empty_jsonl,
)
from hermes.gsp_compliance_agent.runtime.legal_workflow_guard import (
    applicable_legal_requirements_path,
)


# ══════════════════════════════════════════════════════════════════
#  Default LLM prompt path
# ══════════════════════════════════════════════════════════════════


def get_legal_applicability_prompt_path() -> str:
    """Return the path to the legal applicability analysis prompt."""
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    return os.path.join(
        project_root,
        "hermes",
        "gsp_compliance_agent",
        "prompts",
        "legal_applicability_analysis_prompt.md",
    )


# ══════════════════════════════════════════════════════════════════
#  Build LLM input
# ══════════════════════════════════════════════════════════════════


def build_legal_applicability_input(
    legal_text_or_index_record: Dict[str, Any],
    gsp_context: Optional[List[Dict[str, str]]] = None,
    customer_context: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Build the input structure for LLM legal applicability analysis.

    Detects whether the record is from legal_text_archive or legal_curated_index.

    Args:
        legal_text_or_index_record: Record from legal_text_archive or legal_curated_index.
        gsp_context: Optional list of GSP standard context entries.
        customer_context: Optional list of IWAY/customer requirement context entries.

    Returns:
        Input dict for LLM analysis.
    """
    input_data = {}

    # Detect type by ID prefix
    record_id = legal_text_or_index_record.get("legal_text_id", "")
    if not record_id:
        record_id = legal_text_or_index_record.get("legal_index_id", "")

    if record_id.startswith("LT-"):
        # legal_text_archive record
        input_data["legal_text_id"] = legal_text_or_index_record.get("legal_text_id", "")
        input_data["legal_source_id"] = legal_text_or_index_record.get("legal_source_id", "")
        input_data["country_code"] = legal_text_or_index_record.get("country_code", "")
        input_data["law_number"] = legal_text_or_index_record.get("law_number", "")
        input_data["article_reference"] = legal_text_or_index_record.get("article_reference", "")
        input_data["original_text"] = legal_text_or_index_record.get("original_text", "")
        input_data["original_language"] = legal_text_or_index_record.get("original_language", "")
        input_data["_source_type"] = "legal_text_archive"
    elif record_id.startswith("LI-"):
        # legal_curated_index record
        input_data["legal_index_id"] = legal_text_or_index_record.get("legal_index_id", "")
        input_data["legal_source_id"] = legal_text_or_index_record.get("legal_source_id", "")
        input_data["country_code"] = legal_text_or_index_record.get("country_code", "")
        input_data["topic"] = legal_text_or_index_record.get("topic", "")
        input_data["subtopic"] = legal_text_or_index_record.get("subtopic", "")
        input_data["law_number"] = legal_text_or_index_record.get("law_number", "")
        input_data["article_reference"] = legal_text_or_index_record.get("article_reference", "")
        input_data["original_text_or_summary"] = legal_text_or_index_record.get(
            "original_text_or_summary", ""
        )
        input_data["applicability_hint"] = legal_text_or_index_record.get("applicability_hint", "")
        input_data["function_hint"] = legal_text_or_index_record.get("function_hint", "")
        input_data["risk_area_hint"] = legal_text_or_index_record.get("risk_area_hint", "")
        input_data["_source_type"] = "legal_curated_index"
    else:
        # Generic fallback
        input_data["_source_type"] = "unknown"
        for k, v in legal_text_or_index_record.items():
            if k not in ("created_at", "updated_at", "review_status", "approval_status"):
                input_data[k] = v

    # Add optional context
    if gsp_context:
        input_data["_gsp_standards_context"] = gsp_context

    if customer_context:
        input_data["_iway_context"] = customer_context

    return input_data


# ══════════════════════════════════════════════════════════════════
#  LLM call (mock or real)
# ══════════════════════════════════════════════════════════════════


def _mock_llm_output(
    input_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate mock LLM output for testing.

    Produces realistic but deterministic output based on input fields.
    """
    country_code = input_data.get("country_code", "VN")
    source_type = input_data.get("_source_type", "unknown")

    topic = ""
    text = ""
    if source_type == "legal_text_archive":
        topic = input_data.get("law_number", "Unknown Law")
        text = input_data.get("original_text", "")[:200]
    elif source_type == "legal_curated_index":
        topic = input_data.get("topic", "Unknown Topic")
        text = input_data.get("original_text_or_summary", "")[:200]
    else:
        topic = input_data.get("topic", input_data.get("law_number", "Unknown"))

    # Deterministic but realistic output
    needs_legal_review = True  # Always true in mock (conservative default)
    applicable_to_gsp = "环境" in topic or "安全" in topic or "labor" in topic.lower() or "labour" in topic.lower()

    return {
        "legal_requirement_id": None,  # Will be generated
        "requirement_summary": f"Mock analysis: Legal requirement from {topic} in {country_code}. "
        f"Text excerpt: {text}...",
        "applicability_scope": "All facilities under GSP scope",
        "applicable_to_gsp_candidate": applicable_to_gsp,
        "applicable_function": "environment" if "环境" in topic else "labour" if "labour" in topic.lower() or "labor" in topic.lower() else "safety",
        "applicable_department": "EHS",
        "risk_area": "regulatory_compliance",
        "obligation_type": "mandatory_requirement",
        "compliance_obligation_candidate": f"[MOCK] Facility shall comply with {topic} requirements.",
        "linked_gsp_standard_ids": [],
        "linked_iway_requirement_ids": [],
        "stricter_than_customer_requirement": False,
        "needs_legal_review": needs_legal_review,
        "llm_reasoning_summary": f"Mock assessment based on topic '{topic}'.",
        "uncertainty_notes": "Mock LLM: always mark uncertain. Real LLM analysis required.",
    }


def call_llm_for_legal_applicability(
    input_data: Dict[str, Any],
    llm_client: Any = None,
    mock: bool = True,
) -> Dict[str, Any]:
    """Call LLM for legal applicability analysis.

    Args:
        input_data: Built input from build_legal_applicability_input().
        llm_client: Optional LLM client for real analysis.
        mock: If True, use mock output (default).

    Returns:
        LLM output dict.
    """
    if mock:
        return _mock_llm_output(input_data)

    # Real LLM path (future)
    if llm_client is not None:
        prompt_path = get_legal_applicability_prompt_path()
        if os.path.isfile(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()

        # Build the full prompt
        full_prompt = prompt_template + "\n\n## Input\n\n```json\n" + json.dumps(input_data, indent=2, ensure_ascii=False) + "\n```"

        try:
            result = llm_client.complete(full_prompt)
            # Parse JSON from result
            output = json.loads(result)
            return output
        except Exception:
            return _mock_llm_output(input_data)

    return _mock_llm_output(input_data)


# ══════════════════════════════════════════════════════════════════
#  Output normalization and validation
# ══════════════════════════════════════════════════════════════════


def normalize_legal_applicability_output(
    llm_output: Dict[str, Any],
    source_record: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalize LLM output into a valid applicable_legal_requirement record.

    Args:
        llm_output: Raw output from call_llm_for_legal_applicability().
        source_record: Original legal text or index record.

    Returns:
        Normalized applicable_legal_requirement record.
    """
    country_code = source_record.get("country_code", "XX")
    source_id = source_record.get("legal_source_id", "")
    text_id = source_record.get("legal_text_id", "")
    index_id = source_record.get("legal_index_id", "")

    return {
        "legal_requirement_id": "",  # Set by draft function
        "legal_source_id": source_id,
        "legal_text_id": text_id,
        "legal_index_id": index_id,
        "country_code": country_code,
        "jurisdiction": source_record.get("jurisdiction", "national"),
        "law_number": source_record.get("law_number", ""),
        "law_name": source_record.get("law_name", ""),
        "article_reference": source_record.get("article_reference", ""),
        "original_text_link": text_id or index_id,
        "requirement_summary": llm_output.get("requirement_summary", ""),
        "applicability_scope": llm_output.get("applicability_scope", ""),
        "applicable_to_gsp_candidate": llm_output.get("applicable_to_gsp_candidate", False),
        "applicable_function": llm_output.get("applicable_function", ""),
        "applicable_department": llm_output.get("applicable_department", ""),
        "risk_area": llm_output.get("risk_area", ""),
        "obligation_type": llm_output.get("obligation_type", "mandatory_requirement"),
        "compliance_obligation_candidate": llm_output.get("compliance_obligation_candidate", ""),
        "linked_gsp_standard_ids": llm_output.get("linked_gsp_standard_ids", []),
        "linked_iway_requirement_ids": llm_output.get("linked_iway_requirement_ids", []),
        "stricter_than_customer_requirement": llm_output.get("stricter_than_customer_requirement", False),
        "needs_legal_review": llm_output.get("needs_legal_review", True),
        "llm_reasoning_summary": llm_output.get("llm_reasoning_summary", ""),
        "uncertainty_notes": llm_output.get("uncertainty_notes", ""),
        "review_status": "applicability_pending_review",
        "approval_status": "not_approved",
        "created_by": "legal_applicability_analyzer",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_applicable_legal_requirement(
    record: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """Validate an applicable_legal_requirement record.

    Checks:
    - Required fields present
    - review_status is valid
    - approval_status is not_approved
    - needs_legal_review is set if uncertain

    Returns:
        (valid: bool, errors: List[str])
    """
    errors = []

    if not record.get("legal_requirement_id"):
        errors.append("Missing legal_requirement_id.")

    if not record.get("country_code"):
        errors.append("Missing country_code.")

    if not record.get("requirement_summary"):
        errors.append("Missing requirement_summary.")

    review_status = record.get("review_status", "")
    valid_statuses = {
        "applicability_pending_review", "applicable_pending_legal_review",
        "not_applicable", "confirmed_applicable", "rejected",
        "needs_legal_review", "superseded",
    }
    if review_status not in valid_statuses:
        errors.append(f"Invalid review_status: '{review_status}'")

    approval_status = record.get("approval_status", "")
    valid_approvals = {"not_approved", "legal_review_pending", "legal_confirmed_reference_only"}
    if approval_status not in valid_approvals:
        errors.append(f"Invalid approval_status: '{approval_status}'")

    if record.get("needs_legal_review") and review_status not in ("needs_legal_review", "applicability_pending_review"):
        errors.append(
            f"needs_legal_review is True but review_status is '{review_status}'. "
            "Should be 'needs_legal_review' or 'applicability_pending_review'."
        )

    return len(errors) == 0, errors


# ══════════════════════════════════════════════════════════════════
#  Draft applicable legal requirement
# ══════════════════════════════════════════════════════════════════


_legal_requirement_counter = 0


def draft_applicable_legal_requirement(
    record: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Draft an applicable legal requirement with ID assigned.

    Args:
        record: Normalized record from normalize_legal_applicability_output().
        options: Optional dict with keys:
            - counter: int (for test reproducibility)
            - batch_id: str

    Returns:
        Completed draft record with ID.
    """
    global _legal_requirement_counter
    opts = options or {}

    counter = opts.get("counter")
    if counter is None:
        _legal_requirement_counter += 1
        counter = _legal_requirement_counter

    country_code = record.get("country_code", "XX")
    req_id = f"ALR-{country_code}-{counter:04d}"

    record["legal_requirement_id"] = req_id

    return record


def draft_applicable_legal_requirement_batch(
    records: List[Dict[str, Any]],
    batch_id: Optional[str] = None,
    dry_run: bool = True,
    mock_llm: bool = True,
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """Draft applicable legal requirements for a batch of source records.

    For each source record:
    1. Build LLM input
    2. Call LLM (or mock)
    3. Normalize output
    4. Assign ID
    5. Validate

    Args:
        records: List of source records (legal_text_archive or legal_curated_index).
        batch_id: Optional batch identifier.
        dry_run: If True, do not write (just return drafted records).
        mock_llm: If True, use mock LLM.

    Returns:
        (success: bool, message: str, drafted_records: List[Dict])
    """
    drafted = []
    errors = []

    for i, source_record in enumerate(records):
        try:
            llm_input = build_legal_applicability_input(source_record)
            llm_output = call_llm_for_legal_applicability(llm_input, mock=mock_llm)
            normalized = normalize_legal_applicability_output(llm_output, source_record)
            completed = draft_applicable_legal_requirement(
                normalized,
                options={"counter": i + 1, "batch_id": batch_id},
            )
            valid, validation_errors = validate_applicable_legal_requirement(completed)
            if not valid:
                errors.append(f"Row {i + 1}: {', '.join(validation_errors)}")
            drafted.append(completed)
        except Exception as e:
            errors.append(f"Row {i + 1}: {e}")

    if errors:
        return False, f"Draft completed with {len(errors)} error(s): {'; '.join(errors)}", drafted

    return True, f"Drafted {len(drafted)} applicable legal requirements.", drafted


# ══════════════════════════════════════════════════════════════════
#  Write to JSONL
# ══════════════════════════════════════════════════════════════════


def write_applicable_legal_requirements(
    records: List[Dict[str, Any]],
    execute: bool = False,
) -> Tuple[bool, str]:
    """Write applicable legal requirement records to JSONL.

    Args:
        records: List of drafted applicable_legal_requirement records.
        execute: If True, writes to file.

    Returns:
        (success: bool, message: str)
    """
    path = applicable_legal_requirements_path()
    if not execute:
        return True, f"[DRY RUN] Would write {len(records)} applicable legal requirements to {path}"

    ensure_empty_jsonl(path)
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return True, f"Wrote {len(records)} applicable legal requirements."


# ══════════════════════════════════════════════════════════════════
#  Report generation
# ══════════════════════════════════════════════════════════════════


def generate_legal_applicability_report(
    records: List[Dict[str, Any]],
    batch_id: Optional[str] = None,
) -> str:
    """Generate a human-readable report for a batch of legal applicability analysis.

    Args:
        records: List of drafted applicable_legal_requirement records.
        batch_id: Optional batch ID.

    Returns:
        Markdown report string.
    """
    lines = []
    lines.append("# Legal Applicability Analysis Report")
    lines.append("")

    if batch_id:
        lines.append(f"**Batch ID:** {batch_id}")
        lines.append("")

    total = len(records)
    applicable = sum(1 for r in records if r.get("applicable_to_gsp_candidate"))
    needs_review = sum(1 for r in records if r.get("needs_legal_review"))
    stricter = sum(1 for r in records if r.get("stricter_than_customer_requirement"))

    lines.append(f"**Total records analysed:** {total}")
    lines.append(f"**Potentially applicable to GSP:** {applicable}")
    lines.append(f"**Needs legal review:** {needs_review}")
    lines.append(f"**Potentially stricter than customer requirement:** {stricter}")
    lines.append("")

    lines.append("## Candidates")
    lines.append("")
    lines.append("| ID | Country | Law | Function | Applicable | Needs Review |")
    lines.append("|----|---------|-----|----------|------------|--------------|")
    for r in records:
        lines.append(
            f"| {r.get('legal_requirement_id', '')} "
            f"| {r.get('country_code', '')} "
            f"| {r.get('law_number', '')} "
            f"| {r.get('applicable_function', '')} "
            f"| {r.get('applicable_to_gsp_candidate', False)} "
            f"| {r.get('needs_legal_review', True)} |"
        )

    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    lines.append("- All requirements are draft candidates — `applicability_pending_review`.")
    lines.append("- All requirements are `not_approved`.")
    lines.append("- No final legal opinion has been made.")
    lines.append("- No SOP, checklist, training, or department todo has been generated.")
    lines.append("- All LLM analysis is candidate only — subject to human/legal review.")

    return "\n".join(lines)
