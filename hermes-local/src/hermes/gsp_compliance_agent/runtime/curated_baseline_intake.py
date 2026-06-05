"""
curated_baseline_intake.py — P8B: import user-provided curated baselines.

Accepts Excel/CSV/Text baseline records, parses them, normalizes fields,
and writes to curated_baseline.jsonl. No automatic confirmation.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Bangkok")
except ImportError:
    _TZ = timezone(timedelta(hours=7))

_logger = logging.getLogger(__name__)

from hermes.gsp_compliance_agent.runtime.compliance_data_paths import resolve_compliance_path

_BASELINE_DIR = os.path.dirname(resolve_compliance_path("curated_baselines/curated_baseline.jsonl"))
_BASELINE_PATH = resolve_compliance_path("curated_baselines/curated_baseline.jsonl")


def _now() -> str:
    return datetime.now(_TZ).isoformat()


def _uid(prefix: str = "CB") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _append_jsonl(path: str, record: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def normalize_requirement_code(raw: str) -> str:
    """Normalize a requirement code (e.g., 'LT 6.1', 'G 4.1', 'N 6.0')."""
    raw = raw.strip()
    # Remove leading zeros
    raw = re.sub(r'\b0+(\d)', r'\1', raw)
    return raw


def parse_txt_baseline(
    text: str,
    source_id: str = "",
    customer: str = "IKEA",
    source_family: str = "IWAY",
    baseline_type: str = "text",
    batch_id: str = "",
    created_by: str = "p8b_baseline_intake",
) -> List[dict]:
    """Parse plain text or pasted baseline into records.
    
    Expects one requirement per line or tab/comma-separated:
    code<tab>text or code,text or code|text
    """
    records = []
    now = _now()
    lines = text.strip().split("\n")

    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        # Try to split code from text
        code = ""
        req_text = line

        for sep in ["\t", "|", ",", "  "]:
            parts = line.split(sep, 1)
            if len(parts) == 2 and len(parts[0]) < 30:
                # Heuristic: first part looks like a code
                first = parts[0].strip()
                if re.match(r'^[A-Z]+\s*[\d.]+', first) or re.match(r'^[A-Z]\s+\d', first):
                    code = normalize_requirement_code(first)
                    req_text = parts[1].strip()
                    break

        record = {
            "curated_baseline_id": _uid(),
            "source_id": source_id,
            "source_family": source_family,
            "source_version": "",
            "customer": customer,
            "uploaded_file_id": "",
            "uploaded_filename": "",
            "baseline_type": baseline_type,
            "baseline_language": "en",
            "section_name": "",
            "requirement_code": code,
            "requirement_level": "",
            "requirement_text": req_text,
            "original_row_number": i + 1,
            "original_sheet_name": "",
            "source_reference": "",
            "sample_only": batch_id and "sample" in batch_id.lower(),
            "review_status": "baseline_imported_pending_comparison",
            "approval_status": "not_approved",
            "batch_id": batch_id,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        records.append(record)

    return records


def parse_csv_baseline(
    csv_content: str,
    source_id: str = "",
    customer: str = "IKEA",
    source_family: str = "IWAY",
    batch_id: str = "",
    created_by: str = "p8b_baseline_intake",
) -> List[dict]:
    """Parse CSV baseline content.
    
    Expected columns: requirement_code, requirement_text (or similar names).
    """
    records = []
    now = _now()
    reader = csv.DictReader(io.StringIO(csv_content))

    code_col = None
    text_col = None
    section_col = None
    level_col = None

    for r in reader.fieldnames or []:
        rl = r.lower()
        if "code" in rl or "clause" in rl or "ref" in rl:
            code_col = r
        if "text" in rl or "requirement" in rl or "description" in rl:
            text_col = r
        if "section" in rl or "chapter" in rl:
            section_col = r
        if "level" in rl or "force" in rl:
            level_col = r

    for i, row in enumerate(reader):
        if text_col is None:
            continue
        code = normalize_requirement_code(row.get(code_col or "", ""))
        req_text = row.get(text_col or "", "").strip()
        if not req_text:
            continue

        record = {
            "curated_baseline_id": _uid(),
            "source_id": source_id,
            "source_family": source_family,
            "source_version": "",
            "customer": customer,
            "uploaded_file_id": "",
            "uploaded_filename": "",
            "baseline_type": "csv",
            "baseline_language": "en",
            "section_name": row.get(section_col or "", ""),
            "requirement_code": code,
            "requirement_level": row.get(level_col or "", ""),
            "requirement_text": req_text,
            "original_row_number": i + 1,
            "original_sheet_name": "",
            "source_reference": "",
            "sample_only": batch_id and "sample" in batch_id.lower(),
            "review_status": "baseline_imported_pending_comparison",
            "approval_status": "not_approved",
            "batch_id": batch_id,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        records.append(record)

    return records


def write_baseline_records(
    records: List[dict],
    execute: bool = False,
) -> bool:
    """Write baseline records to JSONL. Only if execute=True."""
    if not execute:
        return False
    if not records:
        return True
    try:
        os.makedirs(_BASELINE_DIR, exist_ok=True)
        for rec in records:
            _append_jsonl(_BASELINE_PATH, rec)
        _logger.info("Wrote %d curated baseline records", len(records))
        return True
    except Exception as e:
        _logger.error("Failed to write baseline records: %s", e)
        return False
