"""
legal_original_text_acquirer.py — GSP Compliance Agent: legal original text acquisition pipeline.

Responsibilities:
- Load law list records from legal_curated_index or legal_source_register
- Normalize law identifiers (law_number, country_code, law_name)
- Build search queries for official legal sources
- Search for official legal source candidates (with mock mode for testing)
- Rank source candidates by confidence (high > medium > low)
- Fetch original legal text from source candidates (with mock mode)
- Compute SHA256 text hash for integrity
- Create legal original acquisition records
- Archive original legal text to legal_text_archive JSONL
- Generate acquisition reports in markdown format

Key rules:
- dry_run=True by default, execute=False by default
- Mock modes for testing
- All records: approval_status=not_approved, review_status=acquisition_pending
- No final legal judgment
- No applicability analysis
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, List, Optional, Tuple

from hermes.gsp_compliance_agent.runtime.compliance_data_paths import (
    resolve_compliance_path,
    ensure_empty_jsonl,
)
from hermes.gsp_compliance_agent.runtime.legal_workflow_guard import (
    legal_source_register_path,
    legal_text_archive_path,
    legal_curated_index_path,
    legal_original_acquisitions_path,
    legal_article_candidates_path,
)


# ══════════════════════════════════════════════════════════════════
#  Internal helpers
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


def _generate_acquisition_id(country_code: str, index: int) -> str:
    """Generate a legal original acquisition record ID.

    Format: LA-<country_code>-<index>
    """
    return f"LA-{country_code}-{index:04d}"


# ══════════════════════════════════════════════════════════════════
#  1. load_law_list_records
# ══════════════════════════════════════════════════════════════════


def load_law_list_records(
    source: str = "legal_curated_index",
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Load law list/index records from the specified source.

    Args:
        source: One of 'legal_curated_index' (default) or 'legal_source_register'.
        filters: Optional dict of field:value pairs to filter records by.
            Only records where record[field] == value are returned.

    Returns:
        List of matching records. Empty list if source is unknown or no match.
    """
    if source == "legal_curated_index":
        path = legal_curated_index_path()
    elif source == "legal_source_register":
        path = legal_source_register_path()
    else:
        return []

    records = _load_jsonl(path)

    if filters:
        filtered = []
        for r in records:
            match = True
            for key, value in filters.items():
                if r.get(key) != value:
                    match = False
                    break
            if match:
                filtered.append(r)
        return filtered

    return records


# ══════════════════════════════════════════════════════════════════
#  2. normalize_law_identifier
# ══════════════════════════════════════════════════════════════════


def normalize_law_identifier(record: Dict[str, Any]) -> Dict[str, str]:
    """Extract and normalize law identifiers from a record.

    Handles records from either legal_curated_index or legal_source_register.

    Args:
        record: A record dict from legal_curated_index or legal_source_register.

    Returns:
        Dict with keys: 'law_number', 'country_code', 'law_name'.
        Missing fields default to empty string.
    """
    law_number = record.get("law_number", record.get("normalized_law_number", ""))
    if isinstance(law_number, str):
        law_number = law_number.strip()
    else:
        law_number = str(law_number) if law_number else ""

    country_code = record.get("country_code", "")
    if isinstance(country_code, str):
        country_code = country_code.strip().upper()
    else:
        country_code = str(country_code).strip().upper() if country_code else ""

    law_name = record.get(
        "law_name",
        record.get("law_name_original", record.get("law_name_en", "")),
    )
    if isinstance(law_name, str):
        law_name = law_name.strip()
    else:
        law_name = str(law_name) if law_name else ""

    return {
        "law_number": law_number,
        "country_code": country_code,
        "law_name": law_name,
    }


# ══════════════════════════════════════════════════════════════════
#  3. build_official_source_search_query
# ══════════════════════════════════════════════════════════════════


def build_official_source_search_query(law_record: Dict[str, Any]) -> str:
    """Build a search query string for locating the official legal text.

    Constructs a human-readable search query from the law record fields,
    tailored for searching official government gazettes, legal databases,
    or other authoritative sources.

    Args:
        law_record: A record dict containing law identifiers.

    Returns:
        A search query string.
    """
    identifiers = normalize_law_identifier(law_record)
    parts = []

    if identifiers["country_code"]:
        parts.append(f"[{identifiers['country_code']}]")

    if identifiers["law_number"]:
        parts.append(identifiers["law_number"])

    if identifiers["law_name"]:
        parts.append(identifiers["law_name"])

    if not parts:
        return ""

    return " ".join(parts) + " — official legal text"


# ══════════════════════════════════════════════════════════════════
#  4. search_official_legal_sources
# ══════════════════════════════════════════════════════════════════


def search_official_legal_sources(
    law_record: Dict[str, Any],
    country_code: Optional[str] = None,
    mock: bool = False,
) -> List[Dict[str, Any]]:
    """Search for official legal source candidates for a given law record.

    In mock mode, returns a single simulated source candidate.
    In real mode, returns an empty list with a note explaining that
    official source search is not yet implemented.

    Args:
        law_record: The law/index record to search for.
        country_code: Override country code. If None, extracted from record.
        mock: If True, return a mock source candidate for testing.

    Returns:
        List of source candidate dicts. Each candidate contains:
        - source_title: str
        - source_url: str
        - source_type: str
        - confidence: str ('high', 'medium', 'low')
        - note: str
    """
    identifiers = normalize_law_identifier(law_record)
    cc = (country_code or identifiers["country_code"]).upper()

    if mock:
        law_number = identifiers["law_number"] or "unknown"
        law_name = identifiers["law_name"] or "Unknown Law"
        query = build_official_source_search_query(law_record)

        mock_candidate = {
            "source_title": f"Official Gazette — {law_name} ({law_number})",
            "source_url": f"https://example.gov/{cc.lower()}/official-gazette/{law_number}",
            "source_type": "official_gazette",
            "confidence": "high",
            "note": (
                f"[MOCK] Simulated source candidate for '{law_name}'. "
                "Replace with real official source search in production."
            ),
            "search_query": query,
            "country_code": cc,
            "law_number": law_number,
        }
        return [mock_candidate]

    return []


# ══════════════════════════════════════════════════════════════════
#  5. rank_source_candidates
# ══════════════════════════════════════════════════════════════════


def rank_source_candidates(
    candidates: List[Dict[str, Any]],
    source_priority_rules: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Rank source candidates by confidence level.

    Ranking order: high > medium > low.
    Within the same confidence tier, original order is preserved.

    Args:
        candidates: List of source candidate dicts, each with a 'confidence' key.
        source_priority_rules: Optional list of source_type values to prioritize.
            If provided, candidates matching a priority source_type are boosted
            one tier within their confidence group.

    Returns:
        Ranked list of source candidates.
    """
    if not candidates:
        return []

    confidence_order = {"high": 0, "medium": 1, "low": 2}

    def _rank_key(c: Dict[str, Any]) -> Tuple[int, int, str]:
        conf = c.get("confidence", "low")
        base_rank = confidence_order.get(conf, 2)

        # Apply priority boost if source_type matches
        if source_priority_rules:
            source_type = c.get("source_type", "")
            if source_type in source_priority_rules:
                base_rank = max(0, base_rank - 1)  # Boost one tier

        title = c.get("source_title", "")
        return (base_rank, 0, title)

    return sorted(candidates, key=_rank_key)


# ══════════════════════════════════════════════════════════════════
#  6. fetch_official_legal_text
# ══════════════════════════════════════════════════════════════════


def fetch_official_legal_text(
    source_candidate: Dict[str, Any],
    mock: bool = False,
) -> Dict[str, Any]:
    """Fetch the original legal text from a source candidate.

    In mock mode, returns a simulated legal text block with metadata.
    In real mode, returns a result indicating the user must upload the text.

    Args:
        source_candidate: A source candidate dict from search_official_legal_sources.
        mock: If True, return mock original text for testing.

    Returns:
        Dict with keys:
        - success: bool
        - original_text: str (the fetched text, empty if needs_user_upload)
        - text_source: str ('mock', 'needs_user_upload', or 'fetched')
        - fetch_method: str
        - note: str
    """
    if mock:
        law_number = source_candidate.get("law_number", source_candidate.get("search_query", "unknown"))
        source_title = source_candidate.get("source_title", "Unknown Source")

        mock_text = (
            f"MOCK ORIGINAL LEGAL TEXT — {source_title}\n\n"
            f"Law Number: {law_number}\n\n"
            "This is a simulated original legal text block for testing and development purposes. "
            "It contains placeholder content that mirrors the structure of an official gazette entry. "
            "In production, this would contain the actual verbatim legal text from the official source.\n\n"
            "Article 1 — Scope\n"
            "This Law provides for the regulation of compliance standards "
            "applicable to organizations operating within the jurisdiction.\n\n"
            "Article 2 — Definitions\n"
            "For the purposes of this Law, the following terms shall have the meanings assigned to them...\n\n"
            "Article 3 — General Provisions\n"
            "All organizations shall comply with the requirements set forth in this Law "
            "and any subordinate regulations issued thereunder.\n\n"
            "[END OF MOCK TEXT]"
        )

        text_hash = compute_text_hash(mock_text)

        return {
            "success": True,
            "original_text": mock_text,
            "text_hash": text_hash,
            "text_source": "mock",
            "fetch_method": "mock_generation",
            "note": (
                f"[MOCK] Generated mock legal text for '{source_title}'. "
                "Replace with real text fetch from official source in production."
            ),
            "character_count": len(mock_text),
        }

    return {
        "success": False,
        "original_text": "",
        "text_hash": "",
        "text_source": "needs_user_upload",
        "fetch_method": "user_upload_required",
        "note": (
            "Official legal text could not be fetched automatically. "
            "User must upload the original legal text document. "
            "Automatic fetch from official sources is not yet implemented."
        ),
        "character_count": 0,
    }


# ══════════════════════════════════════════════════════════════════
#  7. compute_text_hash
# ══════════════════════════════════════════════════════════════════


def compute_text_hash(text: str) -> str:
    """Compute the SHA-256 hex digest of text for integrity verification.

    Args:
        text: The text content to hash.

    Returns:
        SHA-256 hex digest string.
    """
    return sha256(text.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════
#  8. create_legal_original_acquisition_record
# ══════════════════════════════════════════════════════════════════


def create_legal_original_acquisition_record(
    law_record: Dict[str, Any],
    source_candidate: Dict[str, Any],
    fetch_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Create a full legal original acquisition record.

    Combines data from the law record, source candidate, and fetch result
    into a comprehensive acquisition record ready for JSONL storage.

    Args:
        law_record: The original law/index record being acquired.
        source_candidate: The source candidate used for the fetch.
        fetch_result: The result from fetch_official_legal_text.

    Returns:
        Acquisition record dict with all metadata.
    """
    identifiers = normalize_law_identifier(law_record)
    cc = identifiers["country_code"]

    # Load existing acquisitions to determine next index
    acq_path = legal_original_acquisitions_path()
    existing = _load_jsonl(acq_path)
    next_index = len(existing) + 1

    acquisition_id = _generate_acquisition_id(cc, next_index)

    record = {
        "legal_acquisition_id": acquisition_id,
        "legal_source_id": law_record.get("legal_source_id", ""),
        "legal_index_id": law_record.get("legal_index_id", ""),
        "country_code": cc,
        "law_number": identifiers["law_number"],
        "law_name": identifiers["law_name"],
        "source_candidate": {
            "source_title": source_candidate.get("source_title", ""),
            "source_url": source_candidate.get("source_url", ""),
            "source_type": source_candidate.get("source_type", ""),
            "confidence": source_candidate.get("confidence", "low"),
            "search_query": source_candidate.get("search_query", ""),
        },
        "fetch_result": {
            "success": fetch_result.get("success", False),
            "text_source": fetch_result.get("text_source", ""),
            "fetch_method": fetch_result.get("fetch_method", ""),
            "character_count": fetch_result.get("character_count", 0),
            "note": fetch_result.get("note", ""),
        },
        "text_hash": fetch_result.get("text_hash", ""),
        "review_status": "acquisition_pending",
        "approval_status": "not_approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    return record


# ══════════════════════════════════════════════════════════════════
#  9. archive_legal_text
# ══════════════════════════════════════════════════════════════════


def archive_legal_text(
    acquisition_record: Dict[str, Any],
    original_text: str,
    execute: bool = False,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Archive original legal text to the legal_text_archive JSONL.

    Creates a legal text archive record from the acquisition record's metadata
    and the original text content. The text is marked immutable and archived.

    Args:
        acquisition_record: The acquisition record from create_legal_original_acquisition_record.
        original_text: The verbatim original legal text to archive.
        execute: If True, writes to file. If False, dry-run.

    Returns:
        (success: bool, message: str, text_archive_record: Optional[Dict])
        On dry-run, returns the record without writing.
        On error, returns (False, error_msg, None).
    """
    text_hash = compute_text_hash(original_text)
    cc = acquisition_record.get("country_code", "XX")

    # Load existing archive records to determine next index
    archive_path = legal_text_archive_path()
    existing = _load_jsonl(archive_path)
    next_index = len(existing) + 1

    text_id = f"LT-{cc}-{next_index:04d}"

    text_archive_record = {
        "legal_text_id": text_id,
        "legal_acquisition_id": acquisition_record.get("legal_acquisition_id", ""),
        "legal_source_id": acquisition_record.get("legal_source_id", ""),
        "legal_index_id": acquisition_record.get("legal_index_id", ""),
        "country_code": cc,
        "law_number": acquisition_record.get("law_number", ""),
        "law_name": acquisition_record.get("law_name", ""),
        "original_text": original_text,
        "text_hash": text_hash,
        "immutable": True,
        "acquisition_source": acquisition_record.get("fetch_result", {}).get("text_source", ""),
        "acquisition_method": acquisition_record.get("fetch_result", {}).get("fetch_method", ""),
        "source_candidate_title": acquisition_record.get("source_candidate", {}).get("source_title", ""),
        "source_candidate_url": acquisition_record.get("source_candidate", {}).get("source_url", ""),
        "review_status": "archived",
        "approval_status": "not_approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if not execute:
        return True, (
            f"[DRY RUN] Would archive legal text '{text_id}' "
            f"({len(original_text)} chars, hash={text_hash[:12]}...) "
            f"to {archive_path}"
        ), text_archive_record

    try:
        ensure_empty_jsonl(archive_path)
        with open(archive_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(text_archive_record, ensure_ascii=False) + "\n")

        return True, (
            f"Legal text '{text_id}' archived successfully "
            f"({len(original_text)} chars, hash={text_hash[:12]}...)."
        ), text_archive_record

    except Exception as e:
        return False, f"Error archiving legal text: {e}", None


# ══════════════════════════════════════════════════════════════════
#  10. generate_acquisition_report
# ══════════════════════════════════════════════════════════════════


def generate_acquisition_report(
    records: List[Dict[str, Any]],
    batch_id: str,
) -> str:
    """Generate a markdown report summarizing legal text acquisitions.

    Produces a human-readable report with per-record details and
    aggregate statistics.

    Args:
        records: List of acquisition record dicts.
        batch_id: Identifier for this acquisition batch (e.g., timestamp or UUID).

    Returns:
        Markdown-formatted report string.
    """
    now = datetime.now(timezone.utc).isoformat()
    total = len(records)

    successful = [r for r in records if r.get("fetch_result", {}).get("success", False)]
    pending = [r for r in records if not r.get("fetch_result", {}).get("success", False)]
    mock_sources = [r for r in records if r.get("fetch_result", {}).get("text_source") == "mock"]
    needs_upload = [r for r in records if r.get("fetch_result", {}).get("text_source") == "needs_user_upload"]

    lines = []
    lines.append(f"# Legal Original Text Acquisition Report")
    lines.append(f"")
    lines.append(f"**Batch ID:** {batch_id}")
    lines.append(f"**Generated:** {now}")
    lines.append(f"**Total Records:** {total}")
    lines.append(f"")
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Law Records Processed | {total} |")
    lines.append(f"| Successful Acquisitions | {len(successful)} |")
    lines.append(f"| Pending User Upload | {len(needs_upload)} |")
    lines.append(f"| Mock (Test) Acquisitions | {len(mock_sources)} |")
    lines.append(f"| Pending Review | {total} |")
    lines.append(f"")
    lines.append(f"## Per-Record Details")
    lines.append(f"")
    lines.append(f"| # | Acquisition ID | Country | Law Number | Law Name | Source | Success | Text Source |")
    lines.append(f"|---|----------------|---------|------------|----------|--------|---------|-------------|")

    for idx, rec in enumerate(records, start=1):
        acq_id = rec.get("legal_acquisition_id", "N/A")
        cc = rec.get("country_code", "??")
        law_num = rec.get("law_number", "")
        law_name = rec.get("law_name", "")[:60] if rec.get("law_name") else ""
        source_title = rec.get("source_candidate", {}).get("source_title", "N/A")[:40]
        success = "Yes" if rec.get("fetch_result", {}).get("success", False) else "No"
        text_source = rec.get("fetch_result", {}).get("text_source", "N/A")
        lines.append(
            f"| {idx} | {acq_id} | {cc} | {law_num} | {law_name} | {source_title} | {success} | {text_source} |"
        )

    lines.append(f"")
    lines.append(f"## Notes")
    lines.append(f"")
    lines.append(f"- All records have `approval_status: not_approved` and `review_status: acquisition_pending`.")
    lines.append(f"- Records where text_source is `needs_user_upload` require manual upload of official legal text.")
    lines.append(f"- Mock records are for testing only and must be replaced with real official source text.")
    lines.append(f"- No final legal judgment or applicability analysis has been performed.")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"*Report auto-generated by legal_original_text_acquirer.py*")

    return "\n".join(lines)
