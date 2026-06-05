"""
legal_article_extractor.py — GSP Compliance Agent: legal article extraction pipeline.

Responsible for:
- Loading archived legal text by ID
- Segmenting legal text into individual articles
- Building LLM extraction inputs
- Calling LLM (or mock) for article summary/categorisation
- Normalising LLM output into legal_article_candidate records
- Validating candidate records
- Writing candidates to JSONL
- Generating extraction batch reports

Status conventions:
- review_status defaults to 'article_extracted_pending_review'
- approval_status defaults to 'not_approved'

Do NOT perform final legal judgment or applicability analysis here.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from hermes.gsp_compliance_agent.runtime.compliance_data_paths import (
    resolve_compliance_path,
    ensure_empty_jsonl,
)
from hermes.gsp_compliance_agent.runtime.legal_workflow_guard import (
    legal_article_candidates_path,
    legal_text_archive_path,
    legal_source_register_path,
)


# ══════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════


def _load_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load JSONL records from path."""
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


def generate_id(prefix: str, index: int, country_code: str = "XX") -> str:
    """Generate a unique legal article candidate ID.

    Format: <prefix>-<country_code>-<index>
    e.g., LAC-VN-0001

    Args:
        prefix: ID prefix (use 'LAC' for legal article candidates).
        index: Sequential number.
        country_code: ISO 3166-1 alpha-2 country code.

    Returns:
        Formatted ID string.
    """
    return f"{prefix}-{country_code}-{index:04d}"


# ══════════════════════════════════════════════════════════════════
#  1. load_archived_legal_text
# ══════════════════════════════════════════════════════════════════


def load_archived_legal_text(legal_text_id: str) -> Optional[Dict[str, Any]]:
    """Load an archived legal text record by its legal_text_id.

    Searches legal_text_archive JSONL for a record whose ``legal_text_id``
    field matches the given ID and whose ``review_status`` is ``"archived"``.

    Args:
        legal_text_id: The unique ID of the legal text record to load.

    Returns:
        The matching legal text record dict, or None if not found or not archived.
    """
    path = legal_text_archive_path()
    records = _load_jsonl(path)
    for record in records:
        if record.get("legal_text_id") == legal_text_id:
            if record.get("review_status") == "archived":
                return record
            return None
    return None


# ══════════════════════════════════════════════════════════════════
#  2. segment_legal_text_into_articles
# ══════════════════════════════════════════════════════════════════


# Regex patterns for common article/section markers across jurisdictions.
_ARTICLE_PATTERNS = [
    # Vietnamese: Điều 1., Điều 1:, Điều 1
    re.compile(r"(Điều\s+\d+(?:\s*[\.:])?)", re.UNICODE),
    # English: Article 1., Article 1:, Article 1
    re.compile(r"(Article\s+\d+(?:\s*[\.:])?)", re.IGNORECASE),
    # Section markers: Section 1., § 1, §1
    re.compile(r"(Section\s+\d+(?:\s*[\.:])?)", re.IGNORECASE),
    re.compile(r"(§\s*\d+)"),
    # Clause markers: Clause 1.
    re.compile(r"(Clause\s+\d+(?:\s*[\.:])?)", re.IGNORECASE),
    # Chapter-level (used as fallback delimiter): Chương, Chapter
    re.compile(r"(Chương\s+\d+)", re.UNICODE),
    re.compile(r"(Chapter\s+\d+)", re.IGNORECASE),
]


def segment_legal_text_into_articles(
    legal_text_record: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Split a legal text record into individual article segments.

    Uses regex patterns for Vietnamese and English article/section markers
    (Điều, Article, Section, §, Clause, Chương, Chapter). The entire
    ``original_text`` field is scanned and split at each marker boundary.

    Args:
        legal_text_record: A legal text archive record containing at minimum
            an ``original_text`` field. Other fields (``legal_source_id``,
            ``law_number``, ``country_code``, ``original_language``) may be
            present and are carried through to each segment's context.

    Returns:
        A list of segment dicts, each with:
            - ``article_reference`` (str): the matched marker text
            - ``text`` (str): the segment body
            - ``index`` (int): segment position (1-based)
        Returns an empty list if the text cannot be segmented.
    """
    original_text = legal_text_record.get("original_text", "")
    if not original_text:
        return []

    # Build a combined pattern that matches any of the article markers.
    # Capture the marker text as group 1.
    combined_pattern_parts = []
    for pat in _ARTICLE_PATTERNS:
        combined_pattern_parts.append(pat.pattern)
    combined_pattern = re.compile(
        "(" + "|".join(combined_pattern_parts) + ")",
        re.IGNORECASE | re.UNICODE,
    )

    # Find all marker positions
    matches = list(combined_pattern.finditer(original_text))
    if not matches:
        # No markers found — return entire text as a single segment
        return [
            {
                "article_reference": "full_text",
                "text": original_text.strip(),
                "index": 1,
            }
        ]

    segments = []
    for i, match in enumerate(matches):
        marker = match.group(0).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(original_text)
        segment_text = original_text[start:end].strip()
        segments.append(
            {
                "article_reference": marker,
                "text": segment_text,
                "index": i + 1,
            }
        )

    return segments


# ══════════════════════════════════════════════════════════════════
#  3. build_llm_article_extraction_input
# ══════════════════════════════════════════════════════════════════


def build_llm_article_extraction_input(
    article_text: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the structured input dict for LLM article extraction.

    The input dict conforms to the prompt template expected by
    ``legal_article_extraction_prompt.md``.

    Args:
        article_text: The raw text of a single legal article segment.
        context: Optional dict providing additional context fields:
            - ``article_reference`` (str): e.g. "Điều 1"
            - ``original_language`` (str): e.g. "vi"
            - ``law_number`` (str): e.g. "45/2019/QH14"
            - ``law_name`` (str): e.g. "Bộ luật Lao động 2019"

    Returns:
        A dict with keys: ``article_reference``, ``original_text``,
        ``original_language``, ``law_number``, ``law_name``.
    """
    context = context or {}
    return {
        "article_reference": context.get("article_reference", ""),
        "original_text": article_text,
        "original_language": context.get("original_language", "unknown"),
        "law_number": context.get("law_number", ""),
        "law_name": context.get("law_name", ""),
    }


# ══════════════════════════════════════════════════════════════════
#  4. call_llm_for_article_summary
# ══════════════════════════════════════════════════════════════════


_MOCK_LLM_OUTPUT = {
    "article_reference": "",
    "llm_summary": (
        "This article requires the employer to ensure occupational safety "
        "for workers, covering hazard identification, risk assessment, and "
        "implementation of protective measures."
    ),
    "translated_summary_reference_only": (
        "Điều này yêu cầu người sử dụng lao động phải bảo đảm an toàn lao động "
        "cho người lao động."
    ),
    "article_topic": "labour",
    "article_keywords": [
        "occupational safety",
        "employer obligation",
        "risk assessment",
    ],
    "possible_gsp_domains": ["labour", "safety"],
    "needs_legal_review": False,
    "needs_human_confirmation": True,
    "uncertainty_notes": "",
}


def call_llm_for_article_summary(
    input_data: Dict[str, Any],
    llm_client: Optional[Any] = None,
    mock: bool = True,
) -> Dict[str, Any]:
    """Call the LLM to analyse a legal article and produce a structured summary.

    When ``mock=True`` (the default), returns a pre-defined mock output with
    the ``article_reference`` copied from the input for traceability. This
    allows development and testing without an active LLM connection.

    When ``mock=False``, the function would call the actual LLM using the
    prompt template from ``legal_article_extraction_prompt.md``. The caller
    must provide a compatible ``llm_client`` with a ``generate`` or ``chat``
    method.

    Args:
        input_data: The input dict produced by ``build_llm_article_extraction_input``.
        llm_client: An optional LLM client instance. Required if ``mock=False``.
        mock: If True, returns mock structured output. Default is True.

    Returns:
        A dict with keys matching the LLM output schema:
            - ``article_reference`` (str)
            - ``llm_summary`` (str)
            - ``translated_summary_reference_only`` (str)
            - ``article_topic`` (str)
            - ``article_keywords`` (list[str])
            - ``possible_gsp_domains`` (list[str])
            - ``needs_legal_review`` (bool)
            - ``needs_human_confirmation`` (bool)
            - ``uncertainty_notes`` (str)

    Note:
        This function does NOT perform final legal judgment. The output is
        a draft candidate that must be reviewed.
    """
    if mock:
        output = dict(_MOCK_LLM_OUTPUT)
        output["article_reference"] = input_data.get("article_reference", "")
        return output

    # In production, the real LLM call would be implemented here:
    #   prompt = _build_prompt(input_data)
    #   response = llm_client.generate(prompt)
    #   output = json.loads(response)
    #
    # For now, raise a clear error when mock is disabled but no client.
    if llm_client is None:
        raise ValueError(
            "llm_client is required when mock=False. "
            "Pass a valid LLM client or set mock=True for development."
        )

    # Placeholder for real LLM integration
    raise NotImplementedError(
        "Real LLM integration is not yet implemented. "
        "Use mock=True for development and testing."
    )


# ══════════════════════════════════════════════════════════════════
#  5. normalize_legal_article_candidate
# ══════════════════════════════════════════════════════════════════


def normalize_legal_article_candidate(
    llm_output: Dict[str, Any],
    article_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalise LLM output into a legal_article_candidate record.

    Combines the LLM analysis output with its context (legal source metadata,
    segment info) to produce a structured candidate record ready for validation
    and persistence.

    Args:
        llm_output: The structured output from ``call_llm_for_article_summary``.
        article_context: Dict with context fields including:
            - ``legal_source_id`` (str, required)
            - ``legal_text_id`` (str, required)
            - ``country_code`` (str, required)
            - ``article_reference`` (str, required)
            - ``law_number`` (str, optional)
            - ``law_name`` (str, optional)
            - ``original_language`` (str, optional)

    Returns:
        A legal article candidate record dict with the following structure:

        .. code-block:: python

            {
                "legal_article_candidate_id": str,       # e.g. "LAC-VN-0001"
                "legal_source_id": str,
                "legal_text_id": str,
                "country_code": str,
                "article_reference": str,
                "original_language": str,
                "law_number": str,
                "law_name": str,
                "llm_summary": str,
                "translated_summary_reference_only": str,
                "article_topic": str,
                "article_keywords": list[str],
                "possible_gsp_domains": list[str],
                "needs_legal_review": bool,
                "needs_human_confirmation": bool,
                "uncertainty_notes": str,
                "review_status": "article_extracted_pending_review",
                "approval_status": "not_approved",
                "created_at": str,                        # ISO 8601
                "updated_at": str,                        # ISO 8601
                "pipeline_stage": "article_extraction",
            }

    Note:
        The ``legal_article_candidate_id`` is generated using ``generate_id``
        with the prefix ``LAC``. The caller is responsible for setting the
        correct index or the next sequential ID will be computed from existing
        records.
    """
    country_code = article_context.get("country_code", "XX")

    # Determine next index from existing candidates
    candidates_path = legal_article_candidates_path()
    existing = _load_jsonl(candidates_path)
    next_index = len(existing) + 1

    candidate_id = generate_id("LAC", next_index, country_code)

    now = datetime.now(timezone.utc).isoformat()

    # Default article_reference from context if LLM output is empty
    article_ref = llm_output.get("article_reference") or article_context.get(
        "article_reference", ""
    )

    record = {
        "legal_article_candidate_id": candidate_id,
        "legal_source_id": article_context.get("legal_source_id", ""),
        "legal_text_id": article_context.get("legal_text_id", ""),
        "country_code": country_code,
        "article_reference": article_ref,
        "original_language": article_context.get("original_language", "unknown"),
        "law_number": article_context.get("law_number", ""),
        "law_name": article_context.get("law_name", ""),
        "llm_summary": llm_output.get("llm_summary", ""),
        "translated_summary_reference_only": llm_output.get(
            "translated_summary_reference_only", ""
        ),
        "article_topic": llm_output.get("article_topic", "other"),
        "article_keywords": llm_output.get("article_keywords", []),
        "possible_gsp_domains": llm_output.get("possible_gsp_domains", []),
        "needs_legal_review": llm_output.get("needs_legal_review", False),
        "needs_human_confirmation": llm_output.get("needs_human_confirmation", True),
        "uncertainty_notes": llm_output.get("uncertainty_notes", ""),
        "review_status": "article_extracted_pending_review",
        "approval_status": "not_approved",
        "created_at": now,
        "updated_at": now,
        "pipeline_stage": "article_extraction",
    }

    return record


# ══════════════════════════════════════════════════════════════════
#  6. validate_legal_article_candidate
# ══════════════════════════════════════════════════════════════════


_REQUIRED_CANDIDATE_FIELDS = [
    "legal_article_candidate_id",
    "legal_source_id",
    "legal_text_id",
    "country_code",
    "article_reference",
    "llm_summary",
    "article_topic",
    "review_status",
    "approval_status",
]

_EXPECTED_TYPES = {
    "legal_article_candidate_id": str,
    "legal_source_id": str,
    "legal_text_id": str,
    "country_code": str,
    "article_reference": str,
    "llm_summary": str,
    "article_topic": str,
    "article_keywords": list,
    "possible_gsp_domains": list,
    "needs_legal_review": bool,
    "needs_human_confirmation": bool,
    "review_status": str,
    "approval_status": str,
}


def validate_legal_article_candidate(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a legal article candidate record.

    Checks:
    - All required fields are present and non-empty (strings have content,
      lists are non-empty for required list fields).
    - Fields have the correct type.
    - ``review_status`` is ``"article_extracted_pending_review"``.
    - ``approval_status`` is ``"not_approved"``.

    Args:
        record: The candidate record to validate.

    Returns:
        A tuple of ``(is_valid: bool, errors: List[str])``. If valid, errors
        is an empty list.
    """
    errors: List[str] = []

    # Check required fields exist
    for field in _REQUIRED_CANDIDATE_FIELDS:
        if field not in record:
            errors.append(f"Missing required field: '{field}'")
            continue

        value = record[field]

        # Check type
        expected_type = _EXPECTED_TYPES.get(field)
        if expected_type and not isinstance(value, expected_type):
            errors.append(
                f"Field '{field}' should be {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
            continue

        # Check non-empty for string fields
        if expected_type is str and not value.strip():
            errors.append(f"Required string field '{field}' is empty")
            continue

        # Check non-empty for list fields
        if expected_type is list and len(value) == 0:
            errors.append(f"Required list field '{field}' is empty")

    # Validate review_status
    if record.get("review_status") != "article_extracted_pending_review":
        errors.append(
            f"review_status must be 'article_extracted_pending_review', "
            f"got '{record.get('review_status')}'"
        )

    # Validate approval_status
    if record.get("approval_status") != "not_approved":
        errors.append(
            f"approval_status must be 'not_approved', "
            f"got '{record.get('approval_status')}'"
        )

    return len(errors) == 0, errors


# ══════════════════════════════════════════════════════════════════
#  7. write_legal_article_candidates
# ══════════════════════════════════════════════════════════════════


def write_legal_article_candidates(
    records: List[Dict[str, Any]],
    execute: bool = False,
) -> Tuple[bool, str]:
    """Write legal article candidate records to JSONL.

    Args:
        records: List of candidate records to write.
        execute: If True, writes to the JSONL file. If False (default),
            performs a dry-run and reports what would be written.

    Returns:
        A tuple of ``(success: bool, message: str)``.

    Note:
        Each record is validated via ``validate_legal_article_candidate``
        before writing. If any record fails validation, the entire batch
        is rejected.
    """
    path = legal_article_candidates_path()

    # Validate all records first
    for i, record in enumerate(records):
        is_valid, errors = validate_legal_article_candidate(record)
        if not is_valid:
            err_msg = "; ".join(errors)
            return False, (
                f"Validation failed for record {i} "
                f"('{record.get('legal_article_candidate_id', 'unknown')}'): "
                f"{err_msg}"
            )

    if not execute:
        return True, (
            f"[DRY RUN] Would write {len(records)} legal article candidate "
            f"records to {path}"
        )

    ensure_empty_jsonl(path)
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return True, (
        f"Wrote {len(records)} legal article candidate records to {path}"
    )


# ══════════════════════════════════════════════════════════════════
#  8. generate_legal_article_extraction_report
# ══════════════════════════════════════════════════════════════════


def generate_legal_article_extraction_report(
    records: List[Dict[str, Any]],
    batch_id: str,
) -> str:
    """Generate a Markdown report for a batch of extracted legal articles.

    The report includes a summary header, per-article sections with
    analysis details, and topic/domain aggregations.

    Args:
        records: List of legal article candidate records to include in report.
        batch_id: A batch identifier string (e.g., ``"BATCH-20260518-001"``)
            that appears in the report header.

    Returns:
        A Markdown-formatted report string suitable for saving to disk or
        displaying in a review interface.

    Note:
        The report does NOT contain final legal judgment. It is a review
        aid for human reviewers.
    """
    now = datetime.now(timezone.utc).isoformat()
    total = len(records)

    # Count topics
    topic_counts: Dict[str, int] = {}
    for r in records:
        topic = r.get("article_topic", "other")
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    # Count domains
    domain_counts: Dict[str, int] = {}
    for r in records:
        domains = r.get("possible_gsp_domains", [])
        for d in domains:
            domain_counts[d] = domain_counts.get(d, 0) + 1

    # Count flagged for review
    flagged_for_review = sum(
        1 for r in records if r.get("needs_legal_review", False)
    )
    needs_confirmation = sum(
        1 for r in records if r.get("needs_human_confirmation", True)
    )

    lines: List[str] = []
    lines.append(f"# Legal Article Extraction Report")
    lines.append("")
    lines.append(f"**Batch ID:** {batch_id}")
    lines.append(f"**Generated:** {now}")
    lines.append(f"**Total Articles Extracted:** {total}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Total articles | {total} |")
    lines.append(f"| Flagged for legal review | {flagged_for_review} |")
    lines.append(f"| Needs human confirmation | {needs_confirmation} |")
    lines.append("")
    lines.append("### Topic Distribution")
    lines.append("")
    lines.append(f"| Topic | Count |")
    lines.append(f"|---|---|")
    for topic in sorted(topic_counts.keys()):
        lines.append(f"| {topic} | {topic_counts[topic]} |")
    lines.append("")
    lines.append("### GSP Domain Distribution")
    lines.append("")
    lines.append(f"| Domain | Mentions |")
    lines.append(f"|---|---|")
    for domain in sorted(domain_counts.keys()):
        lines.append(f"| {domain} | {domain_counts[domain]} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Per-article details
    lines.append("## Article Details")
    lines.append("")

    for i, record in enumerate(records, start=1):
        candidate_id = record.get("legal_article_candidate_id", "N/A")
        article_ref = record.get("article_reference", "N/A")
        topic = record.get("article_topic", "N/A")
        summary = record.get("llm_summary", "")
        keywords = ", ".join(record.get("article_keywords", []))
        domains = ", ".join(record.get("possible_gsp_domains", []))
        needs_review = "⚠️ Yes" if record.get("needs_legal_review") else "No"
        needs_confirm = "Yes" if record.get("needs_human_confirmation") else "No"
        uncertainty = record.get("uncertainty_notes", "") or "None"

        lines.append(f"### {i}. {article_ref}")
        lines.append("")
        lines.append(f"**Candidate ID:** `{candidate_id}`")
        lines.append("")
        lines.append(f"**Topic:** {topic}")
        lines.append(f"**Keywords:** {keywords}")
        lines.append(f"**GSP Domains:** {domains}")
        lines.append(f"**Needs Legal Review:** {needs_review}")
        lines.append(f"**Needs Human Confirmation:** {needs_confirm}")
        lines.append(f"**Uncertainty Notes:** {uncertainty}")
        lines.append("")
        lines.append("**Summary:**")
        lines.append("")
        lines.append(f"> {summary}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Disclaimer")
    lines.append("")
    lines.append(
        "This report is an **AI-generated draft** for review purposes only. "
        "It does not constitute legal advice or a final determination of "
        "compliance. All article candidates require human review and "
        "confirmation before use in compliance assessments."
    )
    lines.append("")

    return "\n".join(lines)
