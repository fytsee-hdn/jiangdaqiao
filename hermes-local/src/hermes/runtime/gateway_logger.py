"""
gateway_logger.py

Local file logger for the HTTP Gateway.

Logs Gateway events (request_received, response_sent, error) as JSONL
to logs/gateway.log.

Features:
  - Automatic request_id generation (gw-YYYYMMDD-HHMMSS-XXXXXX)
  - Asia/Bangkok timestamps
  - Sensitive field redaction (token, api_key, secret, password)
  - Content length truncation (content: 200, ocr_text: 300)
  - Fail-safe: logging errors never crash the caller
"""

import json
import os
import random
import string
import warnings
from datetime import datetime
from typing import Any, Optional

try:
    from zoneinfo import ZoneInfo
    _TZ_BKK = ZoneInfo("Asia/Bangkok")
except (ImportError, KeyError):
    from datetime import timezone, timedelta
    _TZ_BKK = timezone(timedelta(hours=7))

# ══════════════════════════════════════════════════════════════════
#  Paths
# ══════════════════════════════════════════════════════════════════

_log_path = None  # lazy-initialised on first write


def _ensure_log_path() -> str:
    """Return the absolute log file path, creating directory if needed."""
    global _log_path
    if _log_path is None:
        # Relative to project root: ~/hermes-local/logs/gateway.log
        base = os.path.dirname(os.path.abspath(__file__))  # hermes/runtime
        base = os.path.dirname(base)  # hermes
        base = os.path.dirname(base)  # ~/hermes-local
        _log_path = os.path.join(base, "logs", "gateway.log")
    return _log_path


# ══════════════════════════════════════════════════════════════════
#  Request ID generation
# ══════════════════════════════════════════════════════════════════


def generate_request_id() -> str:
    """
    Generate a unique request ID.

    Format: gw-YYYYMMDD-HHMMSS-XXXXXX
    where XXXXXX is 6 random hex digits.
    """
    now = datetime.now(_TZ_BKK)
    date_part = now.strftime("%Y%m%d-%H%M%S")
    rand_part = "".join(random.choices(string.hexdigits.upper(), k=6))
    return f"gw-{date_part}-{rand_part}"


# ══════════════════════════════════════════════════════════════════
#  Sensitive field redaction
# ══════════════════════════════════════════════════════════════════

_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {"token", "api_key", "secret", "password", "authorization"}
_SENSITIVE_SUFFIXES = {"token", "api_key", "secret", "password"}


def _redact_value(key: str, value: Any) -> Any:
    """
    Redact a single value if the key is sensitive.

    Checks:
      - Exact match in _SENSITIVE_KEYS
      - Key ends with any _SENSITIVE_SUFFIXES
    """
    kl = key.lower().strip()
    if kl in _SENSITIVE_KEYS:
        return _REDACTED
    for suffix in _SENSITIVE_SUFFIXES:
        if kl.endswith(suffix):
            return _REDACTED
    return value


def _redact_dict(data: dict) -> dict:
    """Recursively redact sensitive values from a dict."""
    redacted = {}
    for k, v in data.items():
        rv = _redact_value(k, v)
        if rv is _REDACTED:
            redacted[k] = _REDACTED
        elif isinstance(v, dict):
            redacted[k] = _redact_dict(v)
        elif isinstance(v, list):
            redacted[k] = [
                _redact_dict(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            redacted[k] = v
    return redacted


# ══════════════════════════════════════════════════════════════════
#  Content truncation
# ══════════════════════════════════════════════════════════════════


def _truncate(text: Any, max_len: int = 200) -> str:
    """Truncate text to max_len characters, appending '...' if cut."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _truncate_data(data: dict) -> dict:
    """Apply content length limits to known long fields."""
    truncated = dict(data)
    # content -> 200 chars
    if "content" in truncated and isinstance(truncated["content"], str):
        truncated["content"] = _truncate(truncated["content"], 200)
    # ocr_text -> 300 chars
    for key in ("ocr_text", "ocrText", "ocr_text_raw"):
        if key in truncated:
            truncated[key] = _truncate(truncated[key], 300)
    # error -> 300 chars
    if "error" in truncated and isinstance(truncated["error"], str):
        truncated["error"] = _truncate(truncated["error"], 300)
    return truncated


# ══════════════════════════════════════════════════════════════════
#  Main log function
# ══════════════════════════════════════════════════════════════════


def log_gateway_event(event_type: str, data: dict) -> None:
    """
    Log a gateway event to logs/gateway.log as a single JSONL line.

    Parameters
    ----------
    event_type : str
        One of: "request_received", "response_sent", "error"
    data : dict
        Event payload. Will be redacted for sensitive fields and
        truncated for long content fields.

    Logging failures (permission error, disk full, etc.) are caught
    and reported via warnings.warn — they never raise.
    """
    try:
        log_path = _ensure_log_path()

        # Build log entry
        now = datetime.now(_TZ_BKK)
        entry = {
            "timestamp": now.isoformat(timespec="seconds"),
            "event_type": event_type,
        }

        # Copy core fields from data
        for key in ("request_id", "conversation_id", "source", "source_window",
                     "message_type", "summary"):
            if key in data:
                entry[key] = data[key]

        # Build the inner data dict (redacted + truncated)
        inner = dict(data)
        # Remove top-level fields already in entry to avoid duplication
        for key in ("request_id", "conversation_id", "source", "source_window",
                     "message_type", "summary", "event_type", "timestamp"):
            inner.pop(key, None)

        # Redact sensitive values
        inner = _redact_dict(inner)

        # Truncate long content fields
        inner = _truncate_data(inner)

        entry["data"] = inner

        # ── Ensure directory exists ─────────────────────────────
        log_dir = os.path.dirname(log_path)
        os.makedirs(log_dir, exist_ok=True)

        # ── Write JSONL ─────────────────────────────────────────
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    except Exception as exc:
        warnings.warn(
            f"Gateway logger failed to write event '{event_type}': {exc}",
            stacklevel=2,
        )


# ══════════════════════════════════════════════════════════════════
#  Test helper
# ══════════════════════════════════════════════════════════════════


def get_log_path() -> str:
    """Return the absolute log file path (for test assertions)."""
    return _ensure_log_path()


def clear_log() -> None:
    """Delete the log file (for test isolation)."""
    path = _ensure_log_path()
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def read_log() -> list:
    """Read all log entries from gateway.log as a list of dicts."""
    path = _ensure_log_path()
    if not os.path.isfile(path):
        return []
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return entries
