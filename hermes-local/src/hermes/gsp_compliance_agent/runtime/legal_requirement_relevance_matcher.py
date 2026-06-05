"""
legal_requirement_relevance_matcher.py — GSP Compliance Agent: legal-to-GSP/IWAY relevance matching.

Matches legal article candidates against GSP standards and IWAY customer requirements
using LLM-assisted relevance analysis.

Key principles:
- mock_llm=True by default
- dry_run=True by default
- execute=False by default
- All outputs have review_status=applicability_pending_review
- All outputs have approval_status=not_approved
- No final legal judgment — outputs are candidates only
- Do NOT conclude final applicability
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
    legal_article_candidates_path,
)


# ══════════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════════


def _load_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load JSONL records from a file path.

    Args:
        path: Absolute path to the JSONL file.

    Returns:
        List of parsed dict records. Empty list if file missing or empty.
    """
    records = []
    if not os.path.isfile(path):
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


# ══════════════════════════════════════════════════════════════════
#  1. Load legal article candidates
# ══════════════════════════════════════════════════════════════════


def load_legal_article_candidates(
    status_filter: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Load legal article candidates from the legal_article_candidates JSONL.

    Args:
        status_filter: If provided, filter records by review_status field.
            e.g., 'extracted', 'ready_for_relevance_matching'.
            If None, all records are returned.
        limit: Maximum number of records to return. If None, all matching records.

    Returns:
        List of legal article candidate dicts.
    """
    path = legal_article_candidates_path()
    records = _load_jsonl(path)

    if status_filter is not None:
        records = [r for r in records if r.get("review_status") == status_filter]

    if limit is not None and limit > 0:
        records = records[:limit]

    return records


# ══════════════════════════════════════════════════════════════════
#  2. Load GSP standard candidates
# ══════════════════════════════════════════════════════════════════


def load_gsp_standard_candidates(
    status_filter: str = "confirmed_for_internal_standard",
) -> List[Dict[str, Any]]:
    """Load GSP standard records from gsp_core_standard JSONL.

    GSP standards are the internal compliance baselines against which
    legal articles are compared for potential relevance.

    Args:
        status_filter: Filter by status field. Default is
            'confirmed_for_internal_standard' which means the standard
            has been reviewed and confirmed for internal use.
            If None, all records are returned.

    Returns:
        List of GSP standard dicts with at minimum 'id' and 'statement' keys.
    """
    path = resolve_compliance_path("gsp_standards/gsp_core_standard.jsonl")
    records = _load_jsonl(path)

    if status_filter is not None:
        records = [r for r in records if r.get("status") == status_filter]

    return records


# ══════════════════════════════════════════════════════════════════
#  3. Load IWAY customer requirements
# ══════════════════════════════════════════════════════════════════


def load_iway_customer_requirements(
    status_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load IWAY/customer requirements from customer_requirement_master JSONL.

    IWAY requirements represent customer-specific compliance requirements
    that legal articles may overlap with or be stricter than.

    Args:
        status_filter: If provided, filter records by status field.
            e.g., 'active', 'confirmed'.
            If None, all records are returned.

    Returns:
        List of customer requirement dicts with at minimum
        'id' and 'requirement' keys.
    """
    path = resolve_compliance_path(
        "customer_requirements/customer_requirement_master.jsonl"
    )
    records = _load_jsonl(path)

    if status_filter is not None:
        records = [r for r in records if r.get("status") == status_filter]

    return records


# ══════════════════════════════════════════════════════════════════
#  4. Build LLM relevance input
# ══════════════════════════════════════════════════════════════════


def build_llm_relevance_input(
    legal_article: Dict[str, Any],
    gsp_context: Optional[List[Dict[str, str]]] = None,
    iway_context: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Build the input structure for LLM legal requirement relevance analysis.

    Constructs a dict matching the prompt template's expected input schema.

    Args:
        legal_article: A legal article candidate record (from
            legal_article_candidates JSONL). Expected keys:
            legal_article_candidate_id, article_reference, llm_summary,
            article_topic, etc.
        gsp_context: Optional list of GSP standard context entries.
            Each entry should have 'id' and 'statement' keys.
        iway_context: Optional list of IWAY/customer requirement entries.
            Each entry should have 'id' and 'requirement' keys.

    Returns:
        Input dict suitable for call_llm_for_relevance_analysis().
    """
    input_data: Dict[str, Any] = {}

    # Legal article section
    input_data["legal_article"] = {
        "legal_article_candidate_id": legal_article.get(
            "legal_article_candidate_id", ""
        ),
        "article_reference": legal_article.get("article_reference", ""),
        "llm_summary": legal_article.get("llm_summary", ""),
        "article_topic": legal_article.get("article_topic", ""),
    }

    # Also carry forward any other keys that may be useful
    for key in (
        "legal_source_id",
        "country_code",
        "law_number",
        "law_name",
        "original_text",
        "article_text",
    ):
        if key in legal_article:
            input_data["legal_article"][key] = legal_article[key]

    # GSP standards context
    if gsp_context:
        normalized_gsp = []
        for entry in gsp_context:
            gsp_entry = {
                "id": entry.get("id", entry.get("gsp_standard_id", "")),
                "statement": entry.get(
                    "statement",
                    entry.get("standard_statement", entry.get("description", "")),
                ),
            }
            normalized_gsp.append(gsp_entry)
        input_data["gsp_standards_context"] = normalized_gsp
    else:
        input_data["gsp_standards_context"] = []

    # IWAY/customer requirements context
    if iway_context:
        normalized_iway = []
        for entry in iway_context:
            iway_entry = {
                "id": entry.get("id", entry.get("requirement_id", "")),
                "requirement": entry.get(
                    "requirement",
                    entry.get("customer_requirement", entry.get("description", "")),
                ),
            }
            normalized_iway.append(iway_entry)
        input_data["iway_context"] = normalized_iway
    else:
        input_data["iway_context"] = []

    return input_data


# ══════════════════════════════════════════════════════════════════
#  5. Call LLM for relevance analysis (mock or real)
# ══════════════════════════════════════════════════════════════════


def _mock_relevance_output(
    input_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate mock LLM relevance analysis output for testing.

    Produces deterministic output based on the input legal article
    fields. Always marks needs_legal_review=True as a conservative default.

    Args:
        input_data: Input dict from build_llm_relevance_input().

    Returns:
        Mock LLM output matching the prompt's expected response schema.
    """
    legal_article = input_data.get("legal_article", {})
    article_id = legal_article.get("legal_article_candidate_id", "LAC-UNKNOWN")
    article_topic = legal_article.get("article_topic", "")
    article_summary = legal_article.get("llm_summary", "")[:200]

    gsp_context = input_data.get("gsp_standards_context", [])
    iway_context = input_data.get("iway_context", [])

    # Deterministic relevance assessment based on topic keywords
    topic_lower = article_topic.lower() if article_topic else ""
    summary_lower = article_summary.lower() if article_summary else ""

    # Check for common compliance-relevant keywords
    relevant_keywords = [
        "environment",
        "safety",
        "health",
        "labour",
        "labor",
        "waste",
        "emission",
        "chemical",
        "fire",
        "worker",
        "employee",
        "occupational",
        "hygiene",
        "hazard",
        "risk",
        " protective ",
        "personal protective",
        "training",
        "social",
        "human rights",
        "discrimination",
        "working hours",
        "wage",
        "child labour",
        "forced labour",
        "environmental",
    ]

    potentially_relevant = any(
        kw in topic_lower or kw in summary_lower for kw in relevant_keywords
    )

    # Determine relevant GSP IDs (mock — pick from context if relevant)
    relevant_gsp_ids = []
    if potentially_relevant and gsp_context:
        for gsp in gsp_context[:2]:  # Mock: pick at most 2
            gsp_statement = (gsp.get("statement") or "").lower()
            if any(kw in gsp_statement for kw in relevant_keywords):
                relevant_gsp_ids.append(gsp.get("id", ""))

    # Determine relevant IWAY IDs
    relevant_iway_ids = []
    if potentially_relevant and iway_context:
        for iway in iway_context[:2]:
            iway_req = (iway.get("requirement") or "").lower()
            if any(kw in iway_req for kw in relevant_keywords):
                relevant_iway_ids.append(iway.get("id", ""))

    # Relationship type heuristic
    if "environment" in topic_lower:
        relationship_type = "equivalent"
    elif "safety" in topic_lower or "health" in topic_lower:
        relationship_type = "stricter"
    elif "labour" in topic_lower or "labor" in topic_lower:
        relationship_type = "additional"
    else:
        relationship_type = "unknown"

    return {
        "legal_article_candidate_id": article_id,
        "potentially_relevant_to_gsp": potentially_relevant,
        "potentially_relevant_to_iway": potentially_relevant,
        "relevant_gsp_standard_ids": relevant_gsp_ids,
        "relevant_iway_requirement_ids": relevant_iway_ids,
        "relationship_type": relationship_type,
        "overlap_description": (
            f"Mock assessment: Article topic '{article_topic}' "
            f"{'shows' if potentially_relevant else 'does not show'} "
            f"potential overlap with GSP/IWAY compliance requirements. "
            f"Relationship type: {relationship_type}."
        ),
        "stricter_than_customer_requirement": (
            "uncertain" if relationship_type == "unknown" else (
                True if relationship_type == "stricter" else False
            )
        ),
        "needs_legal_review": True,
        "needs_human_confirmation": True,
        "llm_reasoning_summary": (
            f"Mock relevance assessment for {article_id}. "
            f"Topic: '{article_topic}'. "
            f"Summary excerpt: '{article_summary}...'."
        ),
        "uncertainty_notes": (
            "Mock LLM: conservative defaults applied. "
            "Real LLM analysis required for actual relevance determination. "
            "All outputs are candidates — no final legal applicability is concluded."
        ),
    }


def get_legal_relevance_prompt_path() -> str:
    """Return the path to the legal requirement relevance LLM prompt.

    Returns:
        Absolute path to the prompt markdown file.
    """
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    return os.path.join(
        project_root,
        "hermes",
        "gsp_compliance_agent",
        "prompts",
        "legal_requirement_relevance_prompt.md",
    )


def call_llm_for_relevance_analysis(
    input_data: Dict[str, Any],
    llm_client: Any = None,
    mock: bool = True,
) -> Dict[str, Any]:
    """Call LLM for legal requirement relevance analysis.

    Args:
        input_data: Built input from build_llm_relevance_input().
        llm_client: Optional LLM client for real analysis. If None
            and mock is False, falls back to mock output.
        mock: If True, use mock output (default). Set to False to
            use real LLM inference.

    Returns:
        LLM output dict with relevance assessment.
    """
    if mock:
        return _mock_relevance_output(input_data)

    # Real LLM path
    if llm_client is not None:
        prompt_path = get_legal_relevance_prompt_path()
        if os.path.isfile(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()

        # Build the full prompt with input JSON
        full_prompt = (
            prompt_template
            + "\n\n## Input\n\n```json\n"
            + json.dumps(input_data, indent=2, ensure_ascii=False)
            + "\n```"
        )

        try:
            result = llm_client.complete(full_prompt)
            # Parse JSON from result
            output = json.loads(result)
            return output
        except Exception:
            # Fallback to mock on parse failure
            return _mock_relevance_output(input_data)

    return _mock_relevance_output(input_data)


# ══════════════════════════════════════════════════════════════════
#  6. Normalize relevance result
# ══════════════════════════════════════════════════════════════════


def normalize_relevance_result(
    llm_output: Dict[str, Any],
    legal_article: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalize LLM relevance output into a valid applicable_legal_requirement record.

    Maps the LLM relevance analysis fields into the standard
    applicable_legal_requirement schema. All outputs are candidates
    with review_status='applicability_pending_review' and
    approval_status='not_approved'.

    Args:
        llm_output: Raw output from call_llm_for_relevance_analysis().
        legal_article: Original legal article candidate record used as input.

    Returns:
        Normalized applicable_legal_requirement candidate dict.
    """
    country_code = legal_article.get("country_code", "XX")
    legal_source_id = legal_article.get("legal_source_id", "")

    # Build requirement summary from LLM output
    overlap_desc = llm_output.get("overlap_description", "")
    llm_reasoning = llm_output.get("llm_reasoning_summary", "")
    uncertainty = llm_output.get("uncertainty_notes", "")
    relationship_type = llm_output.get("relationship_type", "unknown")

    requirement_summary_parts = [
        f"Legal Article: {legal_article.get('article_reference', '')}",
        f"Topic: {legal_article.get('article_topic', '')}",
    ]
    if overlap_desc:
        requirement_summary_parts.append(f"Overlap: {overlap_desc}")
    requirement_summary = " | ".join(requirement_summary_parts)

    record = {
        "legal_requirement_id": "",  # Assigned by create function
        "legal_source_id": legal_source_id,
        "legal_article_candidate_id": llm_output.get(
            "legal_article_candidate_id",
            legal_article.get("legal_article_candidate_id", ""),
        ),
        "country_code": country_code,
        "jurisdiction": legal_article.get("jurisdiction", "national"),
        "law_number": legal_article.get("law_number", ""),
        "law_name": legal_article.get("law_name", ""),
        "article_reference": legal_article.get("article_reference", ""),
        "original_text_link": legal_article.get("legal_article_candidate_id", ""),
        "requirement_summary": requirement_summary,
        "applicability_scope": "All facilities under GSP scope",
        # Relevance-specific fields
        "potentially_relevant_to_gsp": llm_output.get(
            "potentially_relevant_to_gsp", False
        ),
        "potentially_relevant_to_iway": llm_output.get(
            "potentially_relevant_to_iway", False
        ),
        "relevant_gsp_standard_ids": llm_output.get(
            "relevant_gsp_standard_ids", []
        ),
        "relevant_iway_requirement_ids": llm_output.get(
            "relevant_iway_requirement_ids", []
        ),
        "relationship_type": relationship_type,
        "overlap_description": overlap_desc,
        "stricter_than_customer_requirement": llm_output.get(
            "stricter_than_customer_requirement", False
        ),
        # Applicability fields (from LLM or defaults)
        "applicable_to_gsp_candidate": llm_output.get(
            "potentially_relevant_to_gsp", False
        ),
        "applicable_function": legal_article.get("article_topic", ""),
        "applicable_department": "",
        "risk_area": "regulatory_compliance",
        "obligation_type": "mandatory_requirement",
        "compliance_obligation_candidate": llm_output.get(
            "llm_reasoning_summary", ""
        ),
        "linked_gsp_standard_ids": llm_output.get("relevant_gsp_standard_ids", []),
        "linked_iway_requirement_ids": llm_output.get(
            "relevant_iway_requirement_ids", []
        ),
        # Review and legal flags
        "needs_legal_review": llm_output.get("needs_legal_review", True),
        "needs_human_confirmation": llm_output.get("needs_human_confirmation", True),
        "llm_reasoning_summary": llm_reasoning,
        "uncertainty_notes": uncertainty,
        # Status — all outputs are candidates
        "review_status": "applicability_pending_review",
        "approval_status": "not_approved",
        "created_by": "legal_requirement_relevance_matcher",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    return record


# ══════════════════════════════════════════════════════════════════
#  7. Create applicable legal requirement candidate
# ══════════════════════════════════════════════════════════════════


_legal_requirement_counter = 0


def create_applicable_legal_requirement_candidate(
    relevance_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Assign a legal_requirement_id to a normalized relevance result.

    Generates a unique ID with the 'ALR' (Applicable Legal Requirement)
    prefix. Sets review_status='applicability_pending_review' and
    approval_status='not_approved'.

    Args:
        relevance_result: Normalized record from
            normalize_relevance_result().

    Returns:
        Completed candidate record with assigned ID.
    """
    global _legal_requirement_counter
    _legal_requirement_counter += 1

    country_code = relevance_result.get("country_code", "XX")
    req_id = f"ALR-{country_code}-{_legal_requirement_counter:04d}"

    relevance_result["legal_requirement_id"] = req_id
    relevance_result["review_status"] = "applicability_pending_review"
    relevance_result["approval_status"] = "not_approved"

    return relevance_result


# ══════════════════════════════════════════════════════════════════
#  8. Generate legal relevance report
# ══════════════════════════════════════════════════════════════════


def generate_legal_relevance_report(
    records: List[Dict[str, Any]],
    batch_id: Optional[str] = None,
) -> str:
    """Generate a human-readable Markdown report for legal relevance analysis.

    Produces a summary of the relevance matching results including
    candidate counts, potential applicability flags, and warnings
    about the candidate-only nature of the analysis.

    Args:
        records: List of applicable_legal_requirement candidate records
            produced by the relevance matching pipeline.
        batch_id: Optional batch/run identifier for traceability.

    Returns:
        Markdown report string.
    """
    lines = []
    lines.append("# Legal Requirement Relevance Analysis Report")
    lines.append("")

    if batch_id:
        lines.append(f"**Batch ID:** {batch_id}")
        lines.append("")

    total = len(records)
    relevant_to_gsp = sum(
        1 for r in records if r.get("potentially_relevant_to_gsp")
    )
    relevant_to_iway = sum(
        1 for r in records if r.get("potentially_relevant_to_iway")
    )
    needs_legal_review = sum(
        1 for r in records if r.get("needs_legal_review", True)
    )
    needs_confirmation = sum(
        1 for r in records if r.get("needs_human_confirmation", True)
    )
    stricter = sum(
        1
        for r in records
        if r.get("stricter_than_customer_requirement") is True
    )
    stricter_uncertain = sum(
        1
        for r in records
        if r.get("stricter_than_customer_requirement") == "uncertain"
    )

    lines.append(f"**Total legal articles analysed:** {total}")
    lines.append(f"**Potentially relevant to GSP:** {relevant_to_gsp}")
    lines.append(f"**Potentially relevant to IWAY:** {relevant_to_iway}")
    lines.append(f"**Needs legal review:** {needs_legal_review}")
    lines.append(f"**Needs human confirmation:** {needs_confirmation}")
    lines.append(
        f"**Potentially stricter than customer req.:** "
        f"{stricter} (uncertain: {stricter_uncertain})"
    )
    lines.append("")

    # Relationship type distribution
    rel_types: Dict[str, int] = {}
    for r in records:
        rt = r.get("relationship_type", "unknown")
        rel_types[rt] = rel_types.get(rt, 0) + 1

    if rel_types:
        lines.append("**Relationship type distribution:**")
        for rt, count in sorted(rel_types.items()):
            lines.append(f"- {rt}: {count}")
        lines.append("")

    # Detail table
    lines.append("## Relevance Candidates")
    lines.append("")
    lines.append(
        "| ID | Article Ref | Country | Relevant to GSP | "
        "Relevant to IWAY | Relationship | Needs Review |"
    )
    lines.append(
        "|----|-------------|---------|-----------------|"
        "-----------------|--------------|--------------|"
    )
    for r in records:
        lines.append(
            f"| {r.get('legal_requirement_id', '')} "
            f"| {r.get('article_reference', '')} "
            f"| {r.get('country_code', '')} "
            f"| {r.get('potentially_relevant_to_gsp', False)} "
            f"| {r.get('potentially_relevant_to_iway', False)} "
            f"| {r.get('relationship_type', 'unknown')} "
            f"| {r.get('needs_legal_review', True)} |"
        )

    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    lines.append(
        "- All requirements are draft candidates — "
        "`applicability_pending_review`."
    )
    lines.append("- All requirements are `not_approved`.")
    lines.append("- **No final legal opinion has been made.**")
    lines.append(
        "- No legal applicability has been confirmed. "
        "These are relevance candidates only."
    )
    lines.append(
        "- All LLM analysis is candidate only — "
        "subject to human/legal review."
    )
    lines.append(
        "- Relevance to GSP/IWAY does not constitute "
        "a finding of legal applicability."
    )
    lines.append(
        "- Local legal counsel must be consulted before "
        "any compliance action is taken."
    )

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  9. Write applicable legal requirement candidates
# ══════════════════════════════════════════════════════════════════


def write_applicable_legal_requirement_candidates(
    records: List[Dict[str, Any]],
    execute: bool = False,
) -> Tuple[bool, str]:
    """Write applicable legal requirement candidate records to JSONL.

    Args:
        records: List of candidate records produced by
            create_applicable_legal_requirement_candidate().
        execute: If True, actually writes to the JSONL file.
            If False (default), returns a dry-run message.

    Returns:
        (success: bool, message: str)
    """
    path = applicable_legal_requirements_path()

    if not execute:
        return True, (
            f"[DRY RUN] Would write {len(records)} applicable legal "
            f"requirement candidates to {path}"
        )

    ensure_empty_jsonl(path)
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return True, (
        f"Wrote {len(records)} applicable legal requirement candidates "
        f"to {path}"
    )
