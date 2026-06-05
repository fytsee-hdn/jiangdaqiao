"""
controlled_import.py — GSP Compliance Agent: Controlled Source Import Pipeline.

Imports accepted files from D1 confirmation into:
  1. source_register
  2. source_text_archive
  3. customer_requirement_master candidates
  4. controlled_terms candidates
  5. import log
  6. human review packet

Rules:
  - Only imports from accepted import_requests with status=pending_c3_import.
  - Does NOT mark anything as approved.
  - Does NOT generate GSP standards, SOPs, or training.
  - All records remain pending human confirmation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
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
from hermes.gsp_compliance_agent.runtime.compliance_data_paths import (
    get_compliance_data_root, resolve_compliance_path,
)

_logger = logging.getLogger(__name__)

# Paths (resolved via compliance_data_paths for profile isolation)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

_IMPORT_LOGS_DIR = os.path.join(get_compliance_data_root(), "source_files", "customer_requirements", "IKEA_IWAY", "import_logs")
_REVIEW_PACKETS_DIR = os.path.join(get_compliance_data_root(), "source_files", "customer_requirements", "IKEA_IWAY", "review_packets")
_UPLOAD_LOGS = os.path.join(get_compliance_data_root(), "upload_staging", "logs")

_SOURCE_REGISTER_PATH = resolve_compliance_path("source_register/source_register.jsonl")
_SOURCE_TEXT_ARCHIVE_PATH = resolve_compliance_path("source_text_archive/source_text_archive.jsonl")
_CRM_PATH = resolve_compliance_path("customer_requirements/customer_requirement_master.jsonl")
_CONTROLLED_TERMS_PATH = resolve_compliance_path("controlled_terms/controlled_terms.jsonl")


def _now() -> str:
    return datetime.now(_TZ).isoformat()

def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _append_jsonl(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ══════════════════════════════════════════════════════════════════
#  Step 1: Find pending import_request
# ══════════════════════════════════════════════════════════════════

def find_pending_import_request(specific_id: Optional[str] = None) -> Optional[dict]:
    """Find the newest pending import_request, or a specific one by ID."""
    import glob
    pending = []
    for f in glob.glob(os.path.join(_UPLOAD_LOGS, "import_request_*.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
            if data.get("status") == "pending_c3_import":
                pending.append((f, data))
        except Exception:
            pass

    if not pending:
        return None

    if specific_id:
        for path, data in pending:
            if data.get("import_request_id") == specific_id:
                data["_log_path"] = path
                return data
        return None

    # Newest first (by requested_at)
    pending.sort(key=lambda x: x[1].get("requested_at", ""), reverse=True)
    newest = pending[0][1]
    newest["_log_path"] = pending[0][0]
    return newest


# ══════════════════════════════════════════════════════════════════
#  Step 2: Validate import_request
# ══════════════════════════════════════════════════════════════════

def validate_import_request(irq: dict) -> dict:
    """Validate an import_request for the pilot.

    Returns {"valid": bool, "reason": str, "warnings": list}
    """
    warnings = []
    src_path = irq.get("source_file_path", "")

    # File exists
    if not src_path or not os.path.isfile(src_path):
        return {"valid": False, "reason": "source_file_missing", "warnings": warnings}

    # SHA256 match
    expected_hash = irq.get("file_hash", "")
    actual_hash = _sha256_file(src_path)
    if expected_hash and actual_hash != expected_hash:
        return {"valid": False, "reason": "hash_mismatch",
                "warnings": [f"Expected {expected_hash[:16]}..., got {actual_hash[:16]}..."]}

    # Metadata checks (warnings only — do not block)
    if irq.get("intended_customer", "").upper() != "IKEA":
        warnings.append("intended_customer not IKEA")
    if irq.get("intended_standard_family", "").upper() != "IWAY":
        warnings.append("intended_standard_family not IWAY")

    ext = os.path.splitext(src_path)[1].lower()
    if ext != ".pdf":
        warnings.append(f"Not a PDF: {ext}")

    return {"valid": True, "reason": "ok", "warnings": warnings, "actual_hash": actual_hash}


# ══════════════════════════════════════════════════════════════════
#  Step 3: Source registration
# ══════════════════════════════════════════════════════════════════

def register_source(irq: dict, actual_hash: str) -> dict:
    """Register the source file in source_register. Returns the source record."""
    now = _now()
    src_path = irq.get("source_file_path", "")

    # Check for duplicate hash
    if os.path.isfile(_SOURCE_REGISTER_PATH):
        for line in open(_SOURCE_REGISTER_PATH, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                existing = json.loads(line)
                if existing.get("file_hash") == actual_hash:
                    _logger.info("Duplicate hash found — skipping source_register: %s", actual_hash[:16])
                    return existing
            except Exception:
                pass

    src_id = f"SR-IWAY6-{uuid.uuid4().hex[:8].upper()}"
    record = {
        "id": src_id,
        "source_type": "customer_requirement",
        "document_title": "IWAY Standard 6.0",
        "status": "approved" if False else "draft",
        "review_status": "registered_pending_text_confirmation",
        "version": 1,
        "created_at": now, "updated_at": now,
        "document_code": "IWAY 6.0",
        "issuing_body": "IKEA of Sweden",
        "standard_version": "6.0",
        "storage_path": src_path,
        "original_filename": os.path.basename(src_path),
        "file_hash": actual_hash,
        "language": "en",
        "priority": "critical",
        "scope_tags": ["environment", "labour", "health_safety", "chemical", "social"],
        "applies_to_countries": ["VN"],
        "upload_id": irq.get("upload_id", ""),
        "import_request_id": irq.get("import_request_id", ""),
        "review": {"reviewed_by": irq.get("requested_by", ""), "reviewed_at": now},
        "notes": "Phase C3.1 controlled import. Pending human text confirmation.",
    }
    _append_jsonl(_SOURCE_REGISTER_PATH, record)
    _logger.info("source_register: %s (hash=%s)", src_id, actual_hash[:16])
    return record


# ══════════════════════════════════════════════════════════════════
#  Step 4: Source text extraction
# ══════════════════════════════════════════════════════════════════

def extract_text_to_archive(src_path: str, source_id: str, file_hash: str) -> List[dict]:
    """Extract text from PDF into source_text_archive records.

    Returns list of archive records created.
    """
    now = _now()
    records = []

    try:
        # Try PyPDF2 / pikepdf for text extraction
        text_by_page = _extract_pdf_text(src_path)
    except Exception as e:
        _logger.warning("PDF text extraction failed: %s", e)
        # Create a single fallback record
        rec = _make_archive_record(source_id, file_hash, 1, "[PDF extraction failed]", "failed", 0.0, now)
        records.append(rec)
        return records

    if not text_by_page:
        rec = _make_archive_record(source_id, file_hash, 1, "[No extractable text]", "empty", 0.0, now)
        records.append(rec)
        return records

    for page_num, text in text_by_page.items():
        confidence = 0.8 if len(text) > 50 else 0.3
        rec = _make_archive_record(source_id, file_hash, page_num, text, "pdf_text_extraction", confidence, now)
        records.append(rec)
        _append_jsonl(_SOURCE_TEXT_ARCHIVE_PATH, rec)

    _logger.info("source_text_archive: %d records for %s", len(records), source_id)
    return records


def _make_archive_record(source_id: str, file_hash: str, page: int, text: str,
                         method: str, confidence: float, now: str) -> dict:
    return {
        "id": f"STA-{source_id}-P{page:03d}",
        "source_id": source_id,
        "source_file_hash": file_hash,
        "page_number": page,
        "original_text": text,
        "extraction_method": method,
        "extraction_confidence": confidence,
        "immutable": True,
        "confirmation_status": "extracted_pending_confirmation",
        "review_status": "extracted_pending_confirmation",
        "original_language": "en",
        "document_title": "IWAY Standard 6.0",
        "ingested_by": "c3.1_controlled_import",
        "ingested_at": now,
        "version": 1, "created_at": now,
    }


def _extract_pdf_text(src_path: str) -> dict:
    """Try to extract text per page from a PDF. Returns {page_num: text}."""
    result = {}
    # Try PyPDF2
    try:
        import PyPDF2
        with open(src_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for i, page in enumerate(reader.pages, 1):
                text = page.extract_text()
                if text and text.strip():
                    result[i] = text.strip()
        if result:
            return result
    except ImportError:
        pass
    except Exception as e:
        _logger.warning("PyPDF2 failed: %s", e)

    # Try pikepdf
    try:
        import pikepdf
        pdf = pikepdf.open(src_path)
        for i, page in enumerate(pdf.pages, 1):
            # pikepdf doesn't have text extraction built in; skip
            pass
    except ImportError:
        pass

    # Fallback: read raw bytes and try to find text
    try:
        raw = open(src_path, "rb").read()
        text = raw.decode("latin-1", errors="ignore")
        # Extract text between stream/endstream or BT/ET markers
        import re
        bt_blocks = re.findall(r'BT(.*?)ET', text, re.DOTALL)
        if bt_blocks:
            combined = " ".join(b.strip() for b in bt_blocks)
            # Clean PDF operators
            combined = re.sub(r'\\([0-9]{3})', lambda m: chr(int(m.group(1))), combined)
            combined = re.sub(r'\(([^)]*)\)', r'\1', combined)
            combined = re.sub(r'Tj|TJ|Td|TD|Tm|Tf|Tc|Tw|Tz|TL|Ts|Tr|T\*', ' ', combined)
            combined = re.sub(r'\s+', ' ', combined).strip()
            if combined:
                result[1] = combined
    except Exception as e:
        _logger.warning("Raw text fallback failed: %s", e)

    return result


# ══════════════════════════════════════════════════════════════════
#  Step 5: Customer requirement candidate extraction
# ══════════════════════════════════════════════════════════════════

def extract_requirement_candidates(archive_records: List[dict], source_id: str,
                                    file_hash: str) -> List[dict]:
    """Parse archive text for IWAY requirement-like items.

    Returns list of customer_requirement_master candidates.
    Does NOT generate GSP core standard records.
    """
    now = _now()
    candidates = []

    for rec in archive_records:
        text = rec.get("original_text", "")
        page = rec.get("page_number", 1)
        sta_id = rec["id"]

        # Skip empty/minimal pages
        if len(text) < 30:
            continue

        # Skip non-requirement pages
        lower = text.lower()
        skip_markers = ["table of contents", "copyright", "all rights reserved",
                        "introduction", "purpose of this", "how to use",
                        "glossary", "definitions", "appendix"]
        if any(m in lower for m in skip_markers):
            continue

        # Look for IWAY requirement patterns
        import re
        # Pattern: G 1.1, G 2.2, G 6.4, or standalone requirement codes
        req_pattern = re.findall(r'([A-Z]\s*\d+\.\d+)', text)
        if not req_pattern:
            req_pattern = re.findall(r'(IWAY\s*\d+\.\d+)', text, re.IGNORECASE)

        if req_pattern:
            for code in req_pattern:
                clean_code = re.sub(r'\s+', ' ', code).strip()
                cid = f"CRM-IWAY-{clean_code.replace(' ', '-')}"
                candidate = {
                    "id": cid,
                    "source_id": source_id,
                    "source_text_archive_id": sta_id,
                    "source_file_hash": file_hash,
                    "customer": "IKEA",
                    "standard_family": "IWAY",
                    "standard_version": "6.0",
                    "customer_code": "IKEA",
                    "customer_name": "IKEA Supply AG",
                    "standard_name": "IWAY Standard",
                    "clause_ref": clean_code,
                    "iway_requirement_code": clean_code,
                    "customer_requirement_level": "unknown",
                    "source_section_type": "unknown",
                    "original_text_en": text[:2000],
                    "official_language": "EN",
                    "translation_for_reference_only": True,
                    "domain_tags": [],
                    "normative_force": "shall",
                    "is_critical": False,
                    "source_document_id": source_id,
                    "mapped_to_gsp_core": False,
                    "core_requirement_ids": [],
                    "review_status": "source_text_extracted_pending_confirmation",
                    "approval_status": "not_approved",
                    "level_review_required": True,
                    "upload_id": "",
                    "import_request_id": "",
                    "page_number": page,
                    "status": "draft",
                    "version": 1, "created_at": now, "updated_at": now,
                    "review": {"reviewed_by": "c3.1_import", "reviewed_at": now},
                    "notes": "Phase C3.1 auto-extracted candidate. Requires human confirmation.",
                }
                candidates.append(candidate)
                _append_jsonl(_CRM_PATH, candidate)

    _logger.info("customer_requirement_master: %d candidates", len(candidates))
    return candidates


# ══════════════════════════════════════════════════════════════════
#  Step 6: Controlled term extraction
# ══════════════════════════════════════════════════════════════════

def extract_controlled_terms(archive_records: List[dict], source_id: str) -> List[dict]:
    """Extract glossary-style terms. Only picks up pages that look like glossaries."""
    now = _now()
    terms = []

    for rec in archive_records:
        text = rec.get("original_text", "").lower()
        if "glossary" not in text and "definition" not in text:
            continue
def find_pending_import_request(specific_id: Optional[str] = None,
                                allow_test: bool = False) -> Optional[dict]:
    """Find pending import_request(s). Requires explicit ID for actual import.

    - If specific_id given: return that request or None.
    - If no specific_id: return ALL pending, but mark as needing explicit selection.
    - Excludes test_only/created_by_test unless allow_test=True.

    Returns dict with '_log_path' and '_needs_explicit_id' markers.
    """
    import glob
    pending = []
    for f in glob.glob(os.path.join(_UPLOAD_LOGS, "import_request_*.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
            if data.get("status") == "pending_c3_import":
                if not allow_test:
                    if data.get("test_only") or data.get("created_by_test"):
                        continue
                pending.append((f, data))
        except Exception:
            pass

    if not pending:
        return None

    if specific_id:
        for path, data in pending:
            if data.get("import_request_id") == specific_id:
                data["_log_path"] = path
                return data
        return None

    # No specific ID: return the FIRST but mark as needing explicit ID
    pending.sort(key=lambda x: x[1].get("requested_at", ""), reverse=True)
    newest = pending[0][1]
    newest["_log_path"] = pending[0][0]
    newest["_needs_explicit_id"] = True
    newest["_candidate_count"] = len(pending)
    return newest


def validate_iway_pdf(src_path: str) -> dict:
    """Validate that a file appears to be a genuine IWAY PDF.

    Returns {"valid": bool, "confidence": float, "signatures": list, "reason": str}
    """
    if not src_path or not os.path.isfile(src_path):
        return {"valid": False, "confidence": 0.0, "signatures": [], "reason": "File not found."}

    ext = os.path.splitext(src_path)[1].lower()
    if ext != ".pdf":
        return {"valid": False, "confidence": 0.0, "signatures": [], "reason": f"Not a PDF: {ext}"}

    sigs = ["iway standard", "the ikea way", "inter ikea systems", "iway standard - edition"]
    try:
        import PyPDF2
        with open(src_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            pages = min(len(reader.pages), 3)
            text = ""
            for i in range(pages):
                t = reader.pages[i].extract_text()
                if t:
                    text += t.lower() + " "
            found = [s for s in sigs if s in text]
            if found:
                return {"valid": True, "confidence": 0.9, "signatures": found, "reason": f"IWAY signatures found: {found}"}
            return {"valid": False, "confidence": 0.3, "signatures": [], "reason": "No IWAY signature detected in first 3 pages."}
    except ImportError:
        pass

    # Fallback: raw bytes check
    try:
        raw = open(src_path, "rb").read(10000).decode("latin-1", errors="ignore").lower()
        found = [s for s in sigs if s in raw]
        if found:
            return {"valid": True, "confidence": 0.7, "signatures": found, "reason": f"IWAY signatures found (raw): {found}"}
    except Exception:
        pass

    return {"valid": False, "confidence": 0.1, "signatures": [], "reason": "No IWAY signature detected in raw bytes."}


# ══════════════════════════════════════════════════════════════════
#  Step 7: Full import pipeline (HARDENED)
# ══════════════════════════════════════════════════════════════════

def run_controlled_import(
    import_request_id: Optional[str] = None,
    *,
    dry_run: bool = False,
    allow_test: bool = False,
    require_iway_validation: bool = False,
) -> dict:
    """Execute the C3.1 controlled import pipeline (hardened version).

    Parameters
    ----------
    import_request_id : str, optional
        REQUIRED for actual import. If None, returns error listing candidates.
    dry_run : bool
        If True, validates and reports but does NOT write anything.
    allow_test : bool
        If True, includes test_only/created_by_test requests.
    require_iway_validation : bool
        If True, validates file contains IWAY signatures.

    Returns
    -------
    dict with: ok, status, import_request, source_record, archive_count,
              requirement_count, term_count, warnings, errors, dry_run_report.
    """
    run_id = f"c3_1-{datetime.now(_TZ).strftime('%Y%m%d-%H%M%S')}"
    start_time = _now()
    result = {
        "ok": False, "import_run_id": run_id, "status": "", "dry_run": dry_run,
        "import_request": None, "source_record": None,
        "archive_count": 0, "requirement_count": 0, "term_count": 0,
        "warnings": [], "errors": [], "dry_run_report": None,
    }

    # ── 1. Find pending ─────────────────────────────────
    irq = find_pending_import_request(import_request_id, allow_test=allow_test)
    if irq is None:
        result["status"] = "skipped_no_pending_request"
        result["errors"].append("No pending import_request found.")
        _log_import(run_id, result, start_time, irq=None)
        return result

    # ── 1a. Require explicit ID ─────────────────────────
    if not import_request_id:
        count = irq.get("_candidate_count", 1)
        result["status"] = "requires_explicit_import_request_id"
        result["errors"].append(
            f"Explicit --import-request-id required. {count} pending request(s) found. "
            "Run scripts/compliance/diagnose_import_requests.py to list candidates."
        )
        _log_import(run_id, result, start_time, irq)
        return result

    result["import_request"] = irq

    # ── 2. Validate import_request ──────────────────────
    validation = validate_import_request(irq)
    if not validation["valid"]:
        result["status"] = f"failed_{validation['reason']}"
        result["errors"].append(validation["reason"])
        if not dry_run:
            _update_irq_status(irq, result["status"])
        _log_import(run_id, result, start_time, irq)
        return result
    result["warnings"].extend(validation.get("warnings", []))
    actual_hash = validation["actual_hash"]

    # ── 2a. IWAY validation (optional) ──────────────────
    if require_iway_validation:
        iway_val = validate_iway_pdf(irq["source_file_path"])
        if not iway_val["valid"]:
            result["status"] = "failed_validation_not_iway"
            result["errors"].append(iway_val["reason"])
            if not dry_run:
                _update_irq_status(irq, result["status"])
            _log_import(run_id, result, start_time, irq)
            return result
        result["warnings"].append(f"IWAY validation: confidence={iway_val['confidence']}")

    # ── 3. Dry-run: report only ─────────────────────────
    if dry_run:
        page_est = _estimate_pages(irq["source_file_path"])
        result["dry_run_report"] = {
            "import_request_id": irq.get("import_request_id"),
            "source_file": irq.get("source_file_path"),
            "file_hash": actual_hash,
            "estimated_pages": page_est,
            "would_register_source": True,
            "would_extract_text": True,
            "targets": [
                "source_register.jsonl",
                "source_text_archive.jsonl",
                "customer_requirement_master.jsonl",
                "controlled_terms.jsonl",
            ],
        }
        result["status"] = "dry_run_completed"
        result["ok"] = True
        _log_import(run_id, result, start_time, irq)
        return result

    # ── 4. Register source ──────────────────────────────
    src_rec = register_source(irq, actual_hash)
    result["source_record"] = src_rec
    source_id = src_rec["id"]

    # ── 5. Extract text ─────────────────────────────────
    archive_records = extract_text_to_archive(irq["source_file_path"], source_id, actual_hash)
    result["archive_count"] = len(archive_records)

    # ── 6. Extract requirements ─────────────────────────
    req_candidates = extract_requirement_candidates(archive_records, source_id, actual_hash)
    result["requirement_count"] = len(req_candidates)

    # ── 7. Extract terms ────────────────────────────────
    term_candidates = extract_controlled_terms(archive_records, source_id)
    result["term_count"] = len(term_candidates)

    # ── 8. Review packet ────────────────────────────────
    packet_path = _create_review_packet(run_id, irq, src_rec, result, archive_records,
                                         req_candidates, term_candidates)
    result["review_packet_path"] = packet_path

    # ── 9. Update status ────────────────────────────────
    final_status = "imported_pending_human_confirmation"
    if result["warnings"]:
        final_status = "imported_with_warnings_pending_human_confirmation"
    result["status"] = final_status
    _update_irq_status(irq, final_status, source_id=source_id, run_id=run_id)

    # ── 10. Log ─────────────────────────────────────────
    result["ok"] = True
    _log_import(run_id, result, start_time, irq)
    result["import_log_path"] = os.path.join(_IMPORT_LOGS_DIR, f"{run_id}.json")
    return result


def _estimate_pages(src_path: str) -> int:
    try:
        import PyPDF2
        with open(src_path, "rb") as f:
            return len(PyPDF2.PdfReader(f).pages)
    except Exception:
        return -1


# ══════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════

def _update_irq_status(irq: dict, status: str, **extra) -> None:
    log_path = irq.get("_log_path", "")
    if not log_path or not os.path.isfile(log_path):
        return
    try:
        data = json.load(open(log_path, encoding="utf-8"))
        data["status"] = status
        data["updated_at"] = _now()
        data.update(extra)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        _logger.warning("Failed to update import_request status: %s", e)


def _log_import(run_id: str, result: dict, start_time: str, irq: Optional[dict]) -> None:
    os.makedirs(_IMPORT_LOGS_DIR, exist_ok=True)
    log = {
        "import_run_id": run_id,
        "import_request_id": (irq or {}).get("import_request_id", ""),
        "upload_id": (irq or {}).get("upload_id", ""),
        "source_file_path": (irq or {}).get("source_file_path", ""),
        "source_id": (result.get("source_record") or {}).get("id", ""),
        "file_hash": (irq or {}).get("file_hash", ""),
        "archive_count": result["archive_count"],
        "requirement_count": result["requirement_count"],
        "term_count": result["term_count"],
        "warnings": result["warnings"],
        "errors": result["errors"],
        "status": result["status"],
        "started_at": start_time,
        "ended_at": _now(),
    }
    path = os.path.join(_IMPORT_LOGS_DIR, f"{run_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def _create_review_packet(run_id: str, irq: dict, src_rec: dict, result: dict,
                          archive_records: List[dict], req_candidates: List[dict],
                          term_candidates: List[dict]) -> str:
    os.makedirs(_REVIEW_PACKETS_DIR, exist_ok=True)
    path = os.path.join(_REVIEW_PACKETS_DIR, f"iway_6_0_import_review_packet_{run_id}.md")

    lines = [
        f"# IWAY 6.0 Import Review Packet",
        f"",
        f"**Import Run ID:** {run_id}",
        f"**Import Request ID:** {irq.get('import_request_id', '')}",
        f"**Upload ID:** {irq.get('upload_id', '')}",
        f"**Source ID:** {src_rec.get('id', '')}",
        f"**SHA256:** {irq.get('file_hash', '')[:20]}...",
        f"**Status:** {result['status']}",
        f"",
        f"## Extraction Summary",
        f"",
        f"| Metric | Count |",
        f"|---|---|",
        f"| Pages archived | {result['archive_count']} |",
        f"| Requirement candidates | {result['requirement_count']} |",
        f"| Controlled term candidates | {result['term_count']} |",
        f"| Warnings | {len(result['warnings'])} |",
        f"",
    ]
    if result["warnings"]:
        lines.append("## Warnings")
        for w in result["warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    lines.extend([
        "## Requirement Candidates",
        "",
        f"Total: {len(req_candidates)} candidates extracted.",
        "",
    ])
    for r in req_candidates[:20]:
        lines.append(f"- **{r.get('iway_requirement_code', '?')}**: {r.get('original_text_en', '')[:120]}...")
    if len(req_candidates) > 20:
        lines.append(f"- ... and {len(req_candidates) - 20} more")

    lines.extend([
        "",
        "## ⚠️ IMPORTANT",
        "",
        "**Confirming extracted source text only confirms extraction accuracy.**",
        "It does NOT approve GSP standards, SOPs, checklists, training content,",
        "department work packages, or legal interpretation.",
        "",
        "All candidates have `review_status = source_text_extracted_pending_confirmation`",
        "and `approval_status = not_approved`.",
    ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path
