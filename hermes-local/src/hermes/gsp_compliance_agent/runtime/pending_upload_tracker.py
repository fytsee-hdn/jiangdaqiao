"""
pending_upload_tracker.py — Multi-file upload queue for compliance chatbot.

Tracks staged uploads pending user confirmation with batch support.
Multiple pending uploads per user are allowed.
Supports confirm-one, confirm-all, reject-one, reject-all.

Uses GSP_COMPLIANCE_DATA_ROOT to resolve storage path.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Bangkok")
except ImportError:
    _TZ = timezone(timedelta(hours=7))

_logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  Path resolution via compliance_data_paths
# ══════════════════════════════════════════════════════════════════

try:
    from hermes.gsp_compliance_agent.runtime.compliance_data_paths import get_compliance_data_root
    _STORE_PATH = os.path.join(get_compliance_data_root(), "upload_staging", "logs", "pending_uploads.json")
except ImportError:
    _STORE_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
        "data", "knowledge", "compliance", "upload_staging", "logs",
        "pending_uploads.json",
    )

# Pending uploads expire after 7 days
_EXPIRE_SECONDS = 7 * 24 * 3600


# ══════════════════════════════════════════════════════════════════
#  Allowed upload statuses
# ══════════════════════════════════════════════════════════════════

_VALID_STATUSES = frozenset({
    "pending_user_confirmation",
    "accepted_for_import_review",
    "rejected_by_user",
    "expired",
    "cancelled",
    "import_request_created",
})


# ══════════════════════════════════════════════════════════════════
#  Store helpers
# ══════════════════════════════════════════════════════════════════


def _load_store() -> dict:
    path = os.path.abspath(_STORE_PATH)
    if not os.path.isfile(path):
        return {"pending_uploads": {}, "batches": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"pending_uploads": {}, "batches": {}}


def _save_store(store: dict) -> None:
    path = os.path.abspath(_STORE_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def _now() -> str:
    return datetime.now(_TZ).isoformat()


def _uid(prefix: str = "UP") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


# ══════════════════════════════════════════════════════════════════
#  Upload management
# ══════════════════════════════════════════════════════════════════


def add_pending_upload(
    user_id: str,
    original_filename: str,
    staged_path: str,
    file_hash: str,
    source_window: str = "compliance_owner_window",
    batch_id: Optional[str] = None,
    suggested_source_type: str = "",
    suggested_customer: str = "",
    suggested_standard_family: str = "",
    metadata: Optional[dict] = None,
) -> dict:
    """Register a pending upload awaiting user confirmation.

    Supports multiple concurrent uploads per user.
    If batch_id is not provided, a new batch_id is generated.
    """
    now = datetime.now(_TZ)
    store = _load_store()
    upload_id = _uid()

    if not batch_id:
        batch_id = _uid("BATCH")

    record = {
        "upload_id": upload_id,
        "batch_id": batch_id,
        "user_id": user_id,
        "source_window": source_window,
        "original_filename": original_filename,
        "staged_file_path": staged_path,
        "file_hash": file_hash,
        "suggested_source_type": suggested_source_type,
        "suggested_customer": suggested_customer,
        "suggested_standard_family": suggested_standard_family,
        "status": "pending_user_confirmation",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=_EXPIRE_SECONDS)).isoformat(),
        "metadata": metadata or {},
    }
    store["pending_uploads"][upload_id] = record

    # Track batch
    if batch_id not in store["batches"]:
        store["batches"][batch_id] = {
            "batch_id": batch_id,
            "user_id": user_id,
            "upload_ids": [],
            "created_at": now.isoformat(),
        }
    store["batches"][batch_id]["upload_ids"].append(upload_id)

    _save_store(store)
    _logger.info("Pending upload %s for %s (batch %s): %s", upload_id, user_id, batch_id, original_filename)
    return record


def list_pending_uploads(
    user_id: str,
    status: str = "pending_user_confirmation",
) -> List[dict]:
    """List all non-expired pending uploads for a user with the given status."""
    store = _load_store()
    now_iso = _now()
    result = []
    for uid, rec in store["pending_uploads"].items():
        if rec["user_id"] != user_id:
            continue
        if rec["status"] != status:
            continue
        if rec["expires_at"] < now_iso:
            continue
        result.append(rec)
    return result


def get_pending_upload(upload_id: str) -> Optional[dict]:
    """Get a pending upload by ID."""
    store = _load_store()
    return store["pending_uploads"].get(upload_id)


def confirm_pending_upload(upload_id: str, user_id: str) -> dict:
    """Confirm a single pending upload.

    Returns dict with ok, upload, error.
    """
    store = _load_store()
    rec = store["pending_uploads"].get(upload_id)

    if rec is None:
        return {"ok": False, "upload": None, "error": "Upload not found."}
    if rec["user_id"] != user_id:
        return {"ok": False, "upload": rec, "error": "Upload belongs to another user."}
    if rec["expires_at"] < _now():
        return {"ok": False, "upload": rec, "error": "Upload confirmation window has expired."}
    if rec["status"] != "pending_user_confirmation":
        return {"ok": False, "upload": rec, "error": f"Upload status is '{rec['status']}', not pending."}

    rec["status"] = "accepted_for_import_review"
    rec["confirmed_at"] = _now()
    store["pending_uploads"][upload_id] = rec
    _save_store(store)
    return {"ok": True, "upload": rec, "error": ""}


def reject_pending_upload(upload_id: str, user_id: str, reason: str = "") -> dict:
    """Reject a pending upload."""
    store = _load_store()
    rec = store["pending_uploads"].get(upload_id)

    if rec is None:
        return {"ok": False, "upload": None, "error": "Upload not found."}
    if rec["user_id"] != user_id:
        return {"ok": False, "upload": rec, "error": "Upload belongs to another user."}
    if rec["status"] != "pending_user_confirmation":
        return {"ok": False, "upload": rec, "error": f"Upload status is '{rec['status']}', can't reject."}

    rec["status"] = "rejected_by_user"
    rec["rejected_at"] = _now()
    rec["rejection_reason"] = reason
    store["pending_uploads"][upload_id] = rec
    _save_store(store)
    return {"ok": True, "upload": rec, "error": ""}


def confirm_all_pending_uploads(user_id: str, batch_id: Optional[str] = None) -> dict:
    """Confirm all pending uploads for a user.

    If batch_id is provided, only confirms uploads in that batch.
    Returns dict with ok, confirmed (list), errors (list).
    """
    pending = list_pending_uploads(user_id)
    if batch_id:
        pending = [u for u in pending if u.get("batch_id") == batch_id]

    if not pending:
        return {"ok": True, "confirmed": [], "errors": ["No pending uploads found."]}

    confirmed = []
    errors = []
    for upload in pending:
        result = confirm_pending_upload(upload["upload_id"], user_id)
        if result["ok"]:
            confirmed.append(result["upload"])
        else:
            errors.append({"upload_id": upload["upload_id"], "error": result["error"]})

    return {
        "ok": len(confirmed) > 0,
        "confirmed": confirmed,
        "errors": errors,
        "count": len(confirmed),
    }


def reject_all_pending_uploads(user_id: str, batch_id: Optional[str] = None) -> dict:
    """Reject all pending uploads for a user."""
    pending = list_pending_uploads(user_id)
    if batch_id:
        pending = [u for u in pending if u.get("batch_id") == batch_id]

    if not pending:
        return {"ok": True, "rejected": [], "errors": ["No pending uploads found."]}

    rejected = []
    errors = []
    for upload in pending:
        result = reject_pending_upload(upload["upload_id"], user_id)
        if result["ok"]:
            rejected.append(result["upload"])
        else:
            errors.append({"upload_id": upload["upload_id"], "error": result["error"]})

    return {
        "ok": True,
        "rejected": rejected,
        "errors": errors,
        "count": len(rejected),
    }


def expire_old_uploads() -> int:
    """Mark expired uploads. Returns count expired."""
    store = _load_store()
    now_iso = _now()
    expired = []
    for uid, rec in store["pending_uploads"].items():
        if rec["status"] == "pending_user_confirmation" and rec["expires_at"] < now_iso:
            rec["status"] = "expired"
            store["pending_uploads"][uid] = rec
            expired.append(uid)
    if expired:
        _save_store(store)
    _logger.info("Expired %d pending uploads", len(expired))
    return len(expired)


def cleanup_expired() -> int:
    """Alias for expire_old_uploads for backward compatibility."""
    return expire_old_uploads()


# ══════════════════════════════════════════════════════════════════
#  Batch helpers
# ══════════════════════════════════════════════════════════════════


def get_batch(batch_id: str) -> Optional[dict]:
    """Get batch info including upload_ids."""
    store = _load_store()
    return store["batches"].get(batch_id)


def get_batches_for_user(user_id: str) -> List[dict]:
    """Get all batches for a user."""
    store = _load_store()
    return [b for b in store["batches"].values() if b["user_id"] == user_id]


def format_upload_list(uploads: List[dict]) -> str:
    """Format a list of pending uploads for chatbot display."""
    if not uploads:
        return "没有待确认的文件。 / No pending uploads."

    lines = [f"待确认文件 ({len(uploads)} 个):"]
    for u in uploads:
        fid = u.get("upload_id", "?")
        fname = u.get("original_filename", "unknown")
        fhash = u.get("file_hash", "")[:12]
        batch = u.get("batch_id", "")[:12]
        lines.append(f"  [{fid}] {fname} (SHA256: {fhash}...)")
    lines.append("")
    lines.append("请回复:")
    lines.append("  确认文件 <upload_id>  — 确认单个文件")
    lines.append("  确认全部上传文件     — 确认所有文件")
    lines.append("  拒绝文件 <upload_id>  — 拒绝单个文件")
    return "\n".join(lines)
