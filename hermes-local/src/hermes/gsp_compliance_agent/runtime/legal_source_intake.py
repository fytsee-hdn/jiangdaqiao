"""
legal_source_intake.py — GSP Compliance Agent: legal source and legal index intake.

Responsibilities:
- Register legal source documents (law, decree, circular, etc.)
- Parse Excel/CSV/TXT legal index files into legal_curated_index candidates
- Archive original file metadata
- Normalize law numbers, country codes, jurisdiction, language, topic labels
- Write JSONL records under compliance data root

Do NOT perform final applicability judgment in code.
"""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from hashlib import sha256

from hermes.gsp_compliance_agent.runtime.compliance_data_paths import (
    resolve_compliance_path,
    ensure_empty_jsonl,
)
from hermes.gsp_compliance_agent.runtime.legal_workflow_guard import (
    legal_source_register_path,
    legal_text_archive_path,
    legal_curated_index_path,
)


# ══════════════════════════════════════════════════════════════════
#  Normalization helpers
# ══════════════════════════════════════════════════════════════════


_COUNTRY_CODE_ALIASES = {
    "vietnam": "VN",
    "vn": "VN",
    "china": "CN",
    "cn": "CN",
    "viet nam": "VN",
}


def normalize_country_code(raw: str) -> str:
    """Normalize country code to ISO 3166-1 alpha-2."""
    cleaned = raw.strip().lower()
    if cleaned in _COUNTRY_CODE_ALIASES:
        return _COUNTRY_CODE_ALIASES[cleaned]
    # Already uppercase ISO code
    if re.match(r"^[A-Z]{2}$", cleaned.upper()):
        return cleaned.upper()
    return cleaned.upper()


_VALID_SOURCE_TYPES = {
    "law", "decree", "circular", "technical_regulation",
    "standard", "official_guidance", "legal_index",
    "curated_excel_index", "other",
}


def normalize_source_type(raw: str) -> str:
    """Normalize source type to valid enum value."""
    cleaned = raw.strip().lower().replace(" ", "_")
    # Handle common variations
    type_map = {
        "law": "law",
        "decree": "decree",
        "circular": "circular",
        "technical_regulation": "technical_regulation",
        "standard": "standard",
        "official_guidance": "official_guidance",
        "legal_index": "legal_index",
        "curated_excel": "curated_excel_index",
        "curated_excel_index": "curated_excel_index",
        "excel_index": "curated_excel_index",
    }
    if cleaned in type_map:
        return type_map[cleaned]
    return cleaned if cleaned in _VALID_SOURCE_TYPES else "other"


def normalize_law_number(raw: str) -> str:
    """Normalize law number (e.g., '45/2019/QH14' or '45/2019/QH14')."""
    return raw.strip()


def normalize_topic_label(raw: str) -> str:
    """Normalize topic label (preserve original, just strip)."""
    return raw.strip()


def generate_id(prefix: str, index: int, country_code: str = "XX") -> str:
    """Generate a unique legal record ID.

    Format: <prefix>-<country_code>-<index>
    e.g., LS-VN-001, LT-VN-001, ALR-VN-001
    """
    return f"{prefix}-{country_code}-{index:04d}"


# ══════════════════════════════════════════════════════════════════
#  Source Registration
# ══════════════════════════════════════════════════════════════════


def register_legal_source(
    country_code: str,
    source_type: str,
    law_name_original: str,
    jurisdiction: Optional[str] = None,
    law_number: Optional[str] = None,
    law_name_en: Optional[str] = None,
    issuing_authority: Optional[str] = None,
    issue_date: Optional[str] = None,
    effective_date: Optional[str] = None,
    language: Optional[str] = None,
    source_file_id: Optional[str] = None,
    source_file_hash: Optional[str] = None,
    source_url: Optional[str] = None,
    source_origin: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Register a legal source document.

    Returns the registered source record.
    """
    country_code = normalize_country_code(country_code)
    source_type = normalize_source_type(source_type)

    # Load existing sources to find next index
    path = legal_source_register_path()
    existing = _load_jsonl(path)
    next_index = len(existing) + 1

    source_id = generate_id("LS", next_index, country_code)

    record = {
        "legal_source_id": source_id,
        "country_code": country_code,
        "jurisdiction": jurisdiction or "national",
        "source_type": source_type,
        "law_number": normalize_law_number(law_number) if law_number else "",
        "law_name_original": law_name_original.strip(),
        "law_name_en": law_name_en.strip() if law_name_en else "",
        "issuing_authority": issuing_authority or "",
        "issue_date": issue_date or "",
        "effective_date": effective_date or "",
        "status": "current",
        "language": language or "unknown",
        "source_file_id": source_file_id or "",
        "source_file_hash": source_file_hash or "",
        "source_url": source_url or "",
        "source_origin": source_origin or "manual_registration",
        "replaces": "",
        "amended_by": [],
        "related_sources": [],
        "review_status": "registered",
        "approval_status": "not_approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if notes:
        record["notes"] = notes

    return record


def write_legal_source_registration(record: Dict[str, Any], execute: bool = False) -> Tuple[bool, str]:
    """Write a legal source registration record to JSONL.

    Args:
        record: The source registration record.
        execute: If True, writes to file. If False, dry-run.

    Returns:
        (success: bool, message: str)
    """
    path = legal_source_register_path()
    if not execute:
        return True, f"[DRY RUN] Would write legal source '{record.get('legal_source_id')}' to {path}"

    ensure_empty_jsonl(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return True, f"Legal source '{record['legal_source_id']}' registered."


# ══════════════════════════════════════════════════════════════════
#  Text Archive
# ══════════════════════════════════════════════════════════════════


def archive_legal_text(
    legal_source_id: str,
    country_code: str,
    original_text: str,
    original_language: str,
    article_reference: Optional[str] = None,
    section_reference: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    law_number: Optional[str] = None,
    page_number: Optional[int] = None,
    row_number: Optional[int] = None,
    sheet_name: Optional[str] = None,
    extraction_method: Optional[str] = None,
    translated_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Archive legal text as an immutable record.

    Args:
        legal_source_id: FK to legal_source_register.
        country_code: ISO 3166-1 alpha-2.
        original_text: Verbatim legal text (IMMUTABLE).
        original_language: Language code.
        article_reference: Article/clause/section reference.
        section_reference: More specific section reference.
        jurisdiction: e.g., 'national'.
        law_number: Official law number.
        page_number: Source page.
        row_number: Source row (for Excel index).
        sheet_name: Source sheet (for Excel index).
        extraction_method: How text was extracted.
        translated_text: REFERENCE ONLY translation.

    Returns:
        The text archive record.
    """
    country_code = normalize_country_code(country_code)

    path = legal_text_archive_path()
    existing = _load_jsonl(path)
    next_index = len(existing) + 1

    text_id = generate_id("LT", next_index, country_code)

    text_hash = sha256(original_text.encode("utf-8")).hexdigest()

    record = {
        "legal_text_id": text_id,
        "legal_source_id": legal_source_id,
        "country_code": country_code,
        "jurisdiction": jurisdiction or "national",
        "law_number": normalize_law_number(law_number) if law_number else "",
        "article_reference": article_reference or "",
        "section_reference": section_reference or "",
        "original_text": original_text,
        "original_language": original_language,
        "translated_text_reference_only": translated_text or "",
        "page_number": page_number,
        "row_number": row_number,
        "sheet_name": sheet_name or "",
        "text_hash": text_hash,
        "immutable": True,
        "extraction_method": extraction_method or "manual_input",
        "review_status": "archived",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    return record


def write_legal_text_archive(record: Dict[str, Any], execute: bool = False) -> Tuple[bool, str]:
    """Write a legal text archive record to JSONL."""
    path = legal_text_archive_path()
    if not execute:
        return True, f"[DRY RUN] Would archive legal text '{record.get('legal_text_id')}' to {path}"

    ensure_empty_jsonl(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return True, f"Legal text '{record['legal_text_id']}' archived."


# ══════════════════════════════════════════════════════════════════
#  Curated Index Intake (parse Excel/CSV/TXT)
# ══════════════════════════════════════════════════════════════════


def parse_csv_legal_index(
    file_path: str,
    legal_source_id: str,
    country_code: str,
    sheet_name: Optional[str] = None,
    uploaded_filename: Optional[str] = None,
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """Parse a CSV file as a legal curated index.

    Expected columns (flexible matching):
    - topic / 主题
    - subtopic / 子主题
    - law_number / 法律编号 / 法律号
    - law_name / 法律名称
    - article_reference / 条款 / 文章
    - original_text / 原文 / 原文内容 / 原文或摘要
    - applicability_hint / 适用范围提示
    - function_hint / 职能提示
    - risk_area_hint / 风险领域提示

    Returns:
        (success: bool, message: str, records: List[Dict])
    """
    if not os.path.isfile(file_path):
        return False, f"File not found: {file_path}", []

    country_code = normalize_country_code(country_code)

    # Column name normalization map
    col_map = {
        "topic": "topic",
        "主题": "topic",
        "subtopic": "subtopic",
        "子主题": "subtopic",
        "law_number": "law_number",
        "法律编号": "law_number",
        "法律号": "law_number",
        "law_name": "law_name",
        "法律名称": "law_name",
        "article_reference": "article_reference",
        "条款": "article_reference",
        "文章": "article_reference",
        "original_text": "original_text_or_summary",
        "原文": "original_text_or_summary",
        "原文内容": "original_text_or_summary",
        "原文或摘要": "original_text_or_summary",
        "applicability_hint": "applicability_hint",
        "适用范围提示": "applicability_hint",
        "function_hint": "function_hint",
        "职能提示": "function_hint",
        "risk_area_hint": "risk_area_hint",
        "风险领域提示": "risk_area_hint",
    }

    records = []
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return False, "CSV has no headers", []

            # Map headers
            mapped_headers = {}
            for header in reader.fieldnames:
                h = header.strip()
                if h in col_map:
                    mapped_headers[h] = col_map[h]
                else:
                    # Skip unmapped columns gracefully
                    pass

            if "topic" not in mapped_headers.values():
                return False, "CSV must have a 'topic' column", []

            # Load existing index
            path = legal_curated_index_path()
            existing = _load_jsonl(path)
            next_index = len(existing) + 1

            for row_num, row in enumerate(reader, start=1):
                record = {
                    "legal_index_id": generate_id("LI", next_index, country_code),
                    "legal_source_id": legal_source_id,
                    "country_code": country_code,
                    "index_source_type": "csv",
                    "uploaded_file_id": "",
                    "uploaded_filename": uploaded_filename or os.path.basename(file_path),
                    "sheet_name": sheet_name or "",
                    "row_number": row_num,
                    "topic": "",
                    "subtopic": "",
                    "law_number": "",
                    "law_name": "",
                    "article_reference": "",
                    "original_text_or_summary": "",
                    "applicability_hint": "",
                    "function_hint": "",
                    "risk_area_hint": "",
                    "review_status": "indexed_pending_analysis",
                    "approval_status": "not_approved",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

                for raw_col, mapped_field in mapped_headers.items():
                    value = row.get(raw_col, "").strip() if row.get(raw_col) else ""
                    if mapped_field in record:
                        record[mapped_field] = value

                record["topic"] = normalize_topic_label(record["topic"])
                record["law_number"] = normalize_law_number(record["law_number"])

                records.append(record)
                next_index += 1

        return True, f"Parsed {len(records)} records from CSV.", records

    except Exception as e:
        return False, f"Error parsing CSV: {e}", []


def parse_txt_legal_index(
    file_path: str,
    legal_source_id: str,
    country_code: str,
    uploaded_filename: Optional[str] = None,
    topic_delimiter: str = "---",
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """Parse a TXT file as a legal curated index.

    Expected format (one entry per block, separated by delimiter):
    ---
    Topic: <topic>
    Subtopic: <subtopic>
    Law Number: <law_number>
    Law Name: <law_name>
    Article: <article_reference>
    Summary: <text>
    ---

    Returns:
        (success: bool, message: str, records: List[Dict])
    """
    if not os.path.isfile(file_path):
        return False, f"File not found: {file_path}", []

    country_code = normalize_country_code(country_code)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        blocks = content.split(topic_delimiter)
        blocks = [b.strip() for b in blocks if b.strip()]

        path = legal_curated_index_path()
        existing = _load_jsonl(path)
        next_index = len(existing) + 1
        records = []

        for block in blocks:
            record = {
                "legal_index_id": generate_id("LI", next_index, country_code),
                "legal_source_id": legal_source_id,
                "country_code": country_code,
                "index_source_type": "txt",
                "uploaded_file_id": "",
                "uploaded_filename": uploaded_filename or os.path.basename(file_path),
                "sheet_name": "",
                "row_number": next_index,
                "topic": "",
                "subtopic": "",
                "law_number": "",
                "law_name": "",
                "article_reference": "",
                "original_text_or_summary": "",
                "applicability_hint": "",
                "function_hint": "",
                "risk_area_hint": "",
                "review_status": "indexed_pending_analysis",
                "approval_status": "not_approved",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            for line in block.split("\n"):
                line = line.strip()
                if line.startswith("Topic:"):
                    record["topic"] = normalize_topic_label(line[6:].strip())
                elif line.startswith("Subtopic:"):
                    record["subtopic"] = line[9:].strip()
                elif line.startswith("Law Number:"):
                    record["law_number"] = normalize_law_number(line[11:].strip())
                elif line.startswith("Law Name:"):
                    record["law_name"] = line[9:].strip()
                elif line.startswith("Article:"):
                    record["article_reference"] = line[8:].strip()
                elif line.startswith("Summary:"):
                    record["original_text_or_summary"] = line[8:].strip()

            records.append(record)
            next_index += 1

        return True, f"Parsed {len(records)} records from TXT.", records

    except Exception as e:
        return False, f"Error parsing TXT: {e}", []


def write_legal_curated_index(
    records: List[Dict[str, Any]], execute: bool = False
) -> Tuple[bool, str]:
    """Write legal curated index records to JSONL.

    Args:
        records: List of curated index records.
        execute: If True, writes to file.

    Returns:
        (success: bool, message: str)
    """
    path = legal_curated_index_path()
    if not execute:
        return True, f"[DRY RUN] Would write {len(records)} curated index records to {path}"

    ensure_empty_jsonl(path)
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return True, f"Wrote {len(records)} curated index records."


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
