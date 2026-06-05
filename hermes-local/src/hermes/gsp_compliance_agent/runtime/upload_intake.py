"""
upload_intake.py — GSP Compliance Agent: File Upload Intake & Staging.

Handles file uploads from compliance windows:
  - Saves to staging (NOT directly to controlled source folders)
  - Calculates SHA256
  - Records upload metadata
  - Supports: accept_for_import_review, reject, classify_as_*

Key: No automatic import. No source_register/source_text_archive writes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from hermes.gsp_compliance_agent.runtime.compliance_data_paths import get_compliance_data_root

_logger = logging.getLogger(__name__)

_STAGING_BASE = os.path.join(get_compliance_data_root(), "upload_staging")

# Allowed extensions for compliance upload
_ALLOWED_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp",
})

# Max file size: 50 MB
_MAX_FILE_SIZE = 50 * 1024 * 1024


def _resolve_staging_path(subdir: str = "pending_classification") -> str:
    """Resolve absolute staging path."""
    path = os.path.join(os.path.abspath(_STAGING_BASE), subdir)
    os.makedirs(path, exist_ok=True)
    return path


def _sha256(file_path: str) -> str:
    """Calculate SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_upload(file_path: str) -> dict:
    """Validate a file before staging.

    Returns
    -------
    dict
        {"valid": bool, "reason": str, "extension": str, "size": int}
    """
    if not os.path.isfile(file_path):
        return {"valid": False, "reason": "File not found.", "extension": "", "size": 0}

    ext = os.path.splitext(file_path)[1].lower()
    size = os.path.getsize(file_path)

    if ext not in _ALLOWED_EXTENSIONS:
        return {
            "valid": False,
            "reason": f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
            "extension": ext, "size": size,
        }

    if size > _MAX_FILE_SIZE:
        return {
            "valid": False,
            "reason": f"File too large ({size} bytes). Maximum: {_MAX_FILE_SIZE} bytes.",
            "extension": ext, "size": size,
        }

    return {"valid": True, "reason": "OK", "extension": ext, "size": size}


def stage_upload(
    file_path: str,
    user_id: str,
    original_filename: Optional[str] = None,
) -> dict:
    """Stage a file upload to pending_classification.

    Does NOT write to source_register, source_text_archive, or
    customer_requirement_master.

    Returns
    -------
    dict
        {
            "ok": bool,
            "upload_id": str,
            "staged_path": str,
            "file_hash": str,
            "extension": str,
            "size": int,
            "original_filename": str,
            "error": str,
        }
    """
    fname = original_filename or os.path.basename(file_path)

    # Validate
    validation = validate_upload(file_path)
    if not validation["valid"]:
        return {
            "ok": False, "upload_id": "", "staged_path": "",
            "file_hash": "", "extension": validation["extension"],
            "size": validation["size"], "original_filename": fname,
            "error": validation["reason"],
        }

    # Generate upload_id and staged path
    uid = uuid.uuid4().hex[:12]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    staged_name = f"{ts}_{user_id}_{uid}{validation['extension']}"
    dest_dir = _resolve_staging_path("pending_classification")
    dest_path = os.path.join(dest_dir, staged_name)

    # Copy file to staging
    shutil.copy2(file_path, dest_path)

    # Calculate hash
    file_hash = _sha256(dest_path)

    _logger.info(
        "Staged upload %s from %s: %s (%d bytes, sha256=%s)",
        uid, user_id, fname, validation["size"], file_hash[:12],
    )

    return {
        "ok": True,
        "upload_id": uid,
        "staged_path": dest_path,
        "file_hash": file_hash,
        "extension": validation["extension"],
        "size": validation["size"],
        "original_filename": fname,
        "error": "",
    }


def move_to_accepted(upload_id: str, staged_path: str) -> dict:
    """Move a staged file from pending_classification to accepted_for_import_review."""
    dest_dir = _resolve_staging_path("accepted_for_import_review")
    fname = os.path.basename(staged_path)
    dest_path = os.path.join(dest_dir, fname)

    if not os.path.isfile(staged_path):
        return {"ok": False, "error": "Staged file not found."}

    shutil.move(staged_path, dest_path)
    _logger.info("Accepted for import review: %s → %s", upload_id, dest_path)

    return {"ok": True, "new_path": dest_path, "upload_id": upload_id}


def move_to_rejected(staged_path: str, reason: str = "") -> dict:
    """Move a staged file to rejected."""
    dest_dir = _resolve_staging_path("rejected")
    fname = os.path.basename(staged_path)
    dest_path = os.path.join(dest_dir, fname)

    if not os.path.isfile(staged_path):
        return {"ok": False, "error": "Staged file not found."}

    shutil.move(staged_path, dest_path)
    _logger.info("Rejected upload: %s (reason: %s)", fname, reason)

    return {"ok": True, "new_path": dest_path}


def create_import_request(
    upload_id: str,
    user_id: str,
    window_id: str,
    staged_path: str,
    file_hash: str,
    intended_source_type: str = "customer_requirement",
    intended_customer: str = "",
    intended_standard_family: str = "",
) -> dict:
    """Create an import_request log for dry-run handoff.

    Does NOT perform actual import. Prepares for Phase C3.1 / C4.
    """
    logs_dir = _resolve_staging_path("logs")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(logs_dir, f"import_request_{ts}_{upload_id}.json")

    record = {
        "import_request_id": f"irq-{upload_id}",
        "upload_id": upload_id,
        "user_id": user_id,
        "window_id": window_id,
        "source_file_path": staged_path,
        "file_hash": file_hash,
        "intended_source_type": intended_source_type,
        "intended_customer": intended_customer,
        "intended_standard_family": intended_standard_family,
        "requested_by": user_id,
        "requested_at": datetime.now().isoformat(),
        "status": "pending_c3_import",
        "notes": "Dry-run import request. Actual import not performed. Requires Phase C3.1 or C4.",
    }

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    _logger.info("Import request created: %s", log_path)
    return record
