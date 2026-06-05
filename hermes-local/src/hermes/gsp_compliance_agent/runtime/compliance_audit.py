"""
compliance_audit.py — GSP Compliance Agent: Audit logging for WeCom upload intake.

Writes JSONL audit log for every adapter-level action.
Never logs sensitive file contents — only metadata and hashes.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Bangkok")
except ImportError:
    _TZ = timezone(timedelta(hours=7))

_logger = logging.getLogger(__name__)

_AUDIT_PATH = os.path.join(
    os.environ.get(
        "GSP_COMPLIANCE_DATA_ROOT",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
            "data", "knowledge", "compliance",
        ),
    ),
    "upload_staging", "logs", "wecom_upload_audit.jsonl",
)


def log_event(event_type: str, data: Dict[str, Any]) -> None:
    """Write one JSONL audit entry.

    Parameters
    ----------
    event_type : str
        One of: wecom_message_received, interaction_created, upload_staged,
        upload_confirmed, upload_rejected, permission_denied, error.
    data : dict
        Event data. Sensitive fields (file contents) MUST NOT be included.
    """
    entry = {
        "timestamp": datetime.now(_TZ).isoformat(),
        "event_type": event_type,
        "data": _sanitize(data),
    }
    try:
        path = os.path.abspath(_AUDIT_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        _logger.warning("Audit log write failed: %s", exc)


def _sanitize(data: dict) -> dict:
    """Remove potentially sensitive fields from audit data."""
    safe = {}
    sensitive_keys = {"content", "file_content", "body", "raw_body", "token", "secret", "password"}
    for k, v in data.items():
        if k.lower() in sensitive_keys:
            safe[k] = "[REDACTED]"
        elif isinstance(v, dict):
            safe[k] = _sanitize(v)
        elif isinstance(v, str) and len(v) > 500:
            safe[k] = v[:500] + "..."
        else:
            safe[k] = v
    return safe


def read_audit_log(limit: int = 50) -> list:
    """Read the last N audit entries."""
    path = os.path.abspath(_AUDIT_PATH)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entries = []
        for line in lines[-limit:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries
    except Exception:
        return []


def clear_audit_log() -> None:
    """Clear the audit log (for test isolation)."""
    path = os.path.abspath(_AUDIT_PATH)
    if os.path.isfile(path):
        os.remove(path)
