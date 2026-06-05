"""
legal_workflow_guard.py — GSP Compliance Agent: legal standard workflow guard.

Provides guard functions for the multi-country legal standard workflow.
Ensures legal text cannot bypass applicability analysis, review, and legal confirmation.

All guard functions follow the pattern:
- Return True if the action is allowed.
- Return a blocking reason (string) if blocked.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple, Optional

from hermes.gsp_compliance_agent.runtime.compliance_data_paths import (
    resolve_compliance_path,
    get_compliance_data_root,
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


def _get_record(path: str, record_id: str, id_field: str) -> Optional[Dict[str, Any]]:
    """Find a record by its ID field."""
    records = _load_jsonl(path)
    for r in records:
        if r.get(id_field) == record_id:
            return r
    return None


# ══════════════════════════════════════════════════════════════════
#  Legal source paths
# ══════════════════════════════════════════════════════════════════


def legal_source_register_path() -> str:
    return resolve_compliance_path("legal/legal_source_register/legal_source_register.jsonl")


def legal_text_archive_path() -> str:
    return resolve_compliance_path("legal/legal_text_archive/legal_text_archive.jsonl")


def legal_curated_index_path() -> str:
    return resolve_compliance_path("legal/legal_curated_index/legal_curated_index.jsonl")


def applicable_legal_requirements_path() -> str:
    return resolve_compliance_path(
        "legal/applicable_legal_requirements/applicable_legal_requirements.jsonl"
    )


def legal_interpretations_path() -> str:
    return resolve_compliance_path("legal/legal_interpretations/legal_interpretations.jsonl")


def legal_gsp_mappings_path() -> str:
    return resolve_compliance_path("legal/legal_gsp_mappings/legal_gsp_mappings.jsonl")


# ══════════════════════════════════════════════════════════════════
#  Guard functions
# ══════════════════════════════════════════════════════════════════


def is_legal_source(source_record: Dict[str, Any]) -> bool:
    """Check if a source record is a legal source.

    Checks source_type or domain markers. Returns True if legal.
    """
    source_type = source_record.get("source_type", "")
    legal_types = {
        "law", "decree", "circular", "technical_regulation",
        "standard", "official_guidance", "legal_index",
        "curated_excel_index", "other_legal",
    }
    if source_type in legal_types:
        return True
    domain = source_record.get("domain", "")
    if domain == "legal":
        return True
    return False


def requires_legal_review(record: Dict[str, Any]) -> bool:
    """Check if a record requires legal review.

    Returns True if the record originated from a legal source
    or has legal implications.
    """
    if is_legal_source(record):
        return True
    needs_legal = record.get("needs_legal_review", False)
    if needs_legal:
        return True
    legal_dependency = record.get("legal_dependency", "")
    if legal_dependency == "needs_legal_review":
        return True
    return False


def can_create_applicable_legal_candidate(legal_source_id: str) -> Tuple[bool, str]:
    """Check if an applicable legal requirement candidate can be created from a legal source.

    Allowed if:
    - legal source is registered and archived.

    Returns (allowed: bool, reason: str).
    """
    path = legal_source_register_path()
    source = _get_record(path, legal_source_id, "legal_source_id")
    if not source:
        return False, f"Legal source '{legal_source_id}' not found."

    review_status = source.get("review_status", "")
    if review_status not in ("registered", "archived", "verified"):
        return False, (
            f"Legal source '{legal_source_id}' has status '{review_status}'. "
            "Candidate creation requires 'registered', 'archived', or 'verified'."
        )

    return True, "ok"


def can_confirm_applicable_legal_requirement(
    legal_requirement_id: str,
) -> Tuple[bool, str]:
    """Check if an applicable legal requirement can be confirmed.

    BLOCKED in P9A unless the guard is bypassed for testing.
    Legal requirements always require review before confirmation.

    Returns (allowed: bool, reason: str).
    """
    path = applicable_legal_requirements_path()
    req = _get_record(path, legal_requirement_id, "legal_requirement_id")
    if not req:
        return False, f"Legal requirement '{legal_requirement_id}' not found."

    review_status = req.get("review_status", "")
    # Block direct confirmation — legal review must happen first
    if review_status == "applicability_pending_review":
        return False, (
            f"Legal requirement '{legal_requirement_id}' is '{review_status}'. "
            "Must pass legal review before confirmation."
        )

    # If already needs_legal_review, still blocked
    if review_status == "needs_legal_review":
        return False, (
            f"Legal requirement '{legal_requirement_id}' is '{review_status}'. "
            "Legal review must be completed before confirmation."
        )

    return False, (
        "No legal requirement can be approved/finalised in P9A. "
        "All remain candidates until legal review workflow is active."
    )


def can_link_legal_requirement_to_gsp(
    legal_requirement_id: str,
    gsp_standard_id: str,
) -> Tuple[bool, str]:
    """Check if a legal requirement can be linked to a GSP Standard.

    Allowed only if the legal requirement is confirmed_applicable
    or explicitly allowed as draft mapping.

    Returns (allowed: bool, reason: str).
    """
    req_path = applicable_legal_requirements_path()
    req = _get_record(req_path, legal_requirement_id, "legal_requirement_id")
    if not req:
        return False, f"Legal requirement '{legal_requirement_id}' not found."

    review_status = req.get("review_status", "")
    if review_status not in ("confirmed_applicable", "applicable_pending_legal_review"):
        return False, (
            f"Legal requirement '{legal_requirement_id}' has status '{review_status}'. "
            "Must be 'confirmed_applicable' or 'applicable_pending_legal_review' for mapping."
        )

    # Draft mapping is allowed for confirmed_applicable requirements
    return True, "ok"


def can_generate_legal_checklist(
    legal_requirement_id: str,
) -> Tuple[bool, str]:
    """Check if a legal checklist can be generated from a legal requirement.

    ALWAYS blocked in P9A. Checklist generation from legal sources
    is deferred to a later phase.

    Returns (allowed: bool, reason: str).
    """
    return False, (
        "Legal checklist generation is blocked in P9A. "
        "This will be enabled in a future phase after legal review workflow is complete."
    )


def can_mark_legal_requirement_approved(
    legal_requirement_id: str,
) -> Tuple[bool, str]:
    """Check if a legal requirement can be marked as approved.

    ALWAYS blocked in P9A. No legal requirement can reach
    final approved status.

    Returns (allowed: bool, reason: str).
    """
    return False, (
        "No legal requirement can be marked approved in P9A. "
        "All legal requirements remain candidates until legal review is active."
    )


def get_legal_blocking_reasons(record_id: str) -> List[str]:
    """Get all legal blocking reasons for a record.

    Args:
        record_id: Either a legal_source_id or legal_requirement_id.

    Returns:
        List of blocking reason strings. Empty list if no blocks.
    """
    reasons = []

    # Try as legal source first
    src_path = legal_source_register_path()
    source = _get_record(src_path, record_id, "legal_source_id")
    if source:
        allowed, reason = can_create_applicable_legal_candidate(record_id)
        if not allowed:
            reasons.append(reason)

    # Try as legal requirement
    req_path = applicable_legal_requirements_path()
    req = _get_record(req_path, record_id, "legal_requirement_id")
    if req:
        allowed, reason = can_confirm_applicable_legal_requirement(record_id)
        if not allowed:
            reasons.append(reason)

        allowed, reason = can_mark_legal_requirement_approved(record_id)
        if not allowed:
            reasons.append(reason)

    if not reasons:
        reasons.append(f"Record '{record_id}' not found in legal source register or requirements.")

    return reasons


# ══════════════════════════════════════════════════════════════════
#  P9C: Legal original text acquisition guard functions
# ══════════════════════════════════════════════════════════════════


def legal_original_acquisitions_path() -> str:
    return resolve_compliance_path(
        "legal/legal_original_acquisitions/legal_original_acquisition.jsonl"
    )


def legal_article_candidates_path() -> str:
    return resolve_compliance_path(
        "legal/legal_article_candidates/legal_article_candidates.jsonl"
    )


def can_run_legal_applicability_analysis(legal_source_id: str) -> Tuple[bool, str]:
    """Check if legal applicability analysis can be run for a legal source.

    Requires original text to be archived.
    If only a law list/index exists, blocks analysis unless
    user explicitly accepts index-only draft mode.

    Returns (allowed: bool, reason: str).
    """
    # Check if legal source exists
    src_path = legal_source_register_path()
    source = _get_record(src_path, legal_source_id, "legal_source_id")
    if not source:
        return False, f"Legal source '{legal_source_id}' not found."

    # Check if original text is archived
    text_path = legal_text_archive_path()
    text_records = _load_jsonl(text_path)
    has_text = any(
        r.get("legal_source_id") == legal_source_id
        and r.get("review_status") == "archived"
        for r in text_records
    )

    if not has_text:
        return False, (
            f"Legal source '{legal_source_id}' has no archived original text. "
            "Applicability analysis based solely on law title/index is not allowed. "
            "Use index_only_draft_mode only with user acceptance and mandatory flags."
        )

    return True, "ok"


def has_original_text_archive(legal_source_id: str) -> Tuple[bool, str]:
    """Check if original legal text is archived for a source.

    Returns (has_text: bool, message: str).
    """
    text_path = legal_text_archive_path()
    text_records = _load_jsonl(text_path)
    has_text = any(
        r.get("legal_source_id") == legal_source_id
        and r.get("review_status") == "archived"
        for r in text_records
    )

    if not has_text:
        return False, (
            f"Legal source '{legal_source_id}' has no archived legal text. "
            "Acquire and archive original text before proceeding."
        )

    return True, f"Original text archived for '{legal_source_id}'."


def has_article_candidates(legal_source_id: str) -> Tuple[bool, str, List[str]]:
    """Check if legal article candidates exist for a source.

    Returns (has_articles: bool, message: str, article_ids: List[str]).
    """
    ac_path = legal_article_candidates_path()
    records = _load_jsonl(ac_path)
    articles = [
        r.get("legal_article_candidate_id", "")
        for r in records
        if r.get("legal_source_id") == legal_source_id
    ]

    if not articles:
        return False, (
            f"No article candidates for legal source '{legal_source_id}'. "
            "Extract articles from archived text first."
        ), []

    return True, f"{len(articles)} article candidates found.", articles


def can_create_legal_gsp_mapping(legal_requirement_id: str) -> Tuple[bool, str]:
    """Check if a legal GSP mapping can be created.

    Requires the legal requirement to be confirmed_applicable.
    This is ALWAYS blocked in P9X — legal overlay requires
    confirmed applicable legal requirements.

    Returns (allowed: bool, reason: str).
    """
    return False, (
        "Legal GSP mapping is blocked. "
        "Requires confirmed_applicable legal requirements, "
        "which are not available in the current phase. "
        "All legal requirements remain candidates."
    )


def can_start_legal_overlay(country_code: str) -> Tuple[bool, str]:
    """Check if legal overlay can be started for a country.

    ALWAYS blocked in P9X. Legal overlay requires:
    - Confirmed applicable legal requirements
    - Human/legal review
    - Approved legal interpretations

    Returns (allowed: bool, reason: str).
    """
    return False, (
        f"Legal overlay for '{country_code}' is blocked. "
        "Requires confirmed_applicable legal requirements with "
        "human/legal review. Not available in current phase."
    )


def get_acquisition_blocking_reasons(legal_source_id: str) -> List[str]:
    """Get all blocking reasons for legal text acquisition pipeline.

    Args:
        legal_source_id: ID of the legal source.

    Returns:
        List of blocking reason strings.
    """
    reasons = []

    # 1. Can we run applicability analysis?
    allowed, reason = can_run_legal_applicability_analysis(legal_source_id)
    if not allowed:
        reasons.append(reason)

    # 2. Has original text?
    has_text, msg = has_original_text_archive(legal_source_id)
    if not has_text:
        reasons.append(msg)

    # 3. Has article candidates?
    has_articles, msg, _ = has_article_candidates(legal_source_id)
    if not has_articles:
        reasons.append(msg)

    # 4. Can create GSP mapping?
    allowed, reason = can_create_legal_gsp_mapping(legal_source_id)
    if not allowed:
        reasons.append(reason)

    return reasons
