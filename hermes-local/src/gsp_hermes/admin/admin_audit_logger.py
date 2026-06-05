"""Admin Audit Logger

Logs admin actions to logs/admin_agent.log in JSONL format.
Handles redaction of sensitive fields and timezone-aware timestamps.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADMIN_LOG_PATH: Optional[str] = None
_LOG_DIR = "logs/"
_SENSITIVE_KEYS: set = {
    "token",
    "api_key",
    "secret",
    "password",
    "authorization",
    ".env",
    "raw_text",
    "summary",
}
_SENSITIVE_SUFFIXES: set = {
    "token",
    "api_key",
    "secret",
    "password",
}

_SENSITIVE_TEXT_RE = re.compile(
    r"(\.env|api[_ -]?key|token|secret|password|auth\.json|authorization|"
    r"credential|credentials|密钥|密码|令牌|凭证)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Timezone helper
# ---------------------------------------------------------------------------

try:
    from zoneinfo import ZoneInfo

    _TZ = ZoneInfo("Asia/Bangkok")
except (ImportError, KeyError):
    _TZ = timezone(timedelta(hours=7))

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_log_path() -> str:
    """Find the project root and return the absolute path to the admin log.

    Walks up from this file's directory (hermes/admin_agent/) to discover
    ~/hermes-local/ (or wherever the project root is), creates the logs/
    directory if needed, and returns the absolute path to admin_agent.log.
    """
    global _ADMIN_LOG_PATH
    if _ADMIN_LOG_PATH is not None:
        return _ADMIN_LOG_PATH

    override = os.environ.get("HERMES_ADMIN_LOG_PATH", "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        _ADMIN_LOG_PATH = str(path)
        return _ADMIN_LOG_PATH

    # This file is at: <project_root>/src/gsp_hermes/admin/admin_audit_logger.py
    current = Path(__file__).resolve().parent
    project_root = current.parents[2].resolve()

    log_dir = project_root / "var" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    _ADMIN_LOG_PATH = str(log_dir / "admin_agent.log")
    return _ADMIN_LOG_PATH


def _redact_value(key: str, value: Any) -> Any:
    """Redact a single value if its key or text contains sensitive content."""
    key_lower = key.lower()
    if key_lower in _SENSITIVE_KEYS:
        return "[REDACTED]"
    for suffix in _SENSITIVE_SUFFIXES:
        if key_lower.endswith(suffix.lower()):
            return "[REDACTED]"
    if isinstance(value, str) and _SENSITIVE_TEXT_RE.search(value):
        return "[REDACTED]"
    return value


def _redact_dict(data: dict) -> dict:
    """Recursively redact sensitive values from a dictionary.

    - For nested dicts, recurse.
    - For lists, iterate and recurse if items are dicts.
    - Leaves non-dict/non-list values untouched (redaction handled
      at the key level).
    """
    redacted: dict = {}
    for key, value in data.items():
        redacted_key = key
        if isinstance(value, dict):
            redacted[redacted_key] = _redact_dict(value)
        elif isinstance(value, list):
            redacted_list = []
            for item in value:
                if isinstance(item, dict):
                    redacted_list.append(_redact_dict(item))
                else:
                    redacted_list.append(item)
            redacted[redacted_key] = redacted_list
        else:
            redacted[redacted_key] = _redact_value(redacted_key, value)
    return redacted


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def log_admin_action(action: dict) -> None:
    """Log an admin action to the admin audit log.

    Parameters
    ----------
    action : dict
        Expected keys: actor, entrypoint, user_id, intent, risk_level,
        requires_confirmation, allowed, summary, data.

    The 'data' field is redacted before writing.
    Timestamps use Asia/Bangkok timezone with ISO-8601 format.
    Never crashes on write failure.
    """
    try:
        now = datetime.now(_TZ)
        entry = {
            "timestamp": now.isoformat(),
            "event_type": "admin_action",
            "actor": action.get("actor"),
            "entrypoint": action.get("entrypoint"),
            "user_id": action.get("user_id"),
            "intent": action.get("intent"),
            "risk_level": action.get("risk_level"),
            "requires_confirmation": action.get("requires_confirmation"),
            "allowed": action.get("allowed"),
            "summary": _redact_value("summary", action.get("summary", "")),
        }

        # Redact the 'data' field before including it
        raw_data = action.get("data")
        if isinstance(raw_data, dict):
            entry["data"] = _redact_dict(raw_data)
        else:
            entry["data"] = raw_data

        log_path = _ensure_log_path()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Never crash on write failure
        pass


def read_admin_log(limit: int = 20) -> list:
    """Read the last *limit* entries from the admin audit log.

    Parameters
    ----------
    limit : int
        Maximum number of entries to return (reading from the end).

    Returns
    -------
    list[dict]
        Parsed JSON entries. Empty list if the log file does not exist.
    """
    log_path = _ensure_log_path()
    if not os.path.isfile(log_path):
        return []

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []

    # Take the last N lines
    tail = lines[-limit:]

    entries: list = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return entries


def clear_admin_log() -> None:
    """Delete the admin log file.

    Primarily used for test isolation.
    """
    global _ADMIN_LOG_PATH
    _ADMIN_LOG_PATH = None
    log_path = _ensure_log_path()
    try:
        if os.path.isfile(log_path):
            os.remove(log_path)
    except Exception:
        pass
