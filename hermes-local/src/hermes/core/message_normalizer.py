"""
message_normalizer.py

Multi-entry source_window recognizer.
Normalizes raw messages from different frontends into a unified
Hermes internal format. The "source_window" field routes each
message to the correct business module downstream.

Supported source_windows:
  - reimbursement_assistant (报销助手)
  - general_assistant     (通用助手, default)
"""

from datetime import datetime, timezone
from typing import Any


def normalize_message(raw_message: dict) -> dict:
    """
    Normalize a raw incoming message into a unified Hermes internal format.

    Parameters
    ----------
    raw_message : dict
        Raw message from any frontend (WeCom, Telegram, CLI, etc.).
        Must contain at minimum a "content" key.
        Optional keys: source, source_window, user_id, message_type,
                       attachments, conversation_id, timestamp.

    Returns
    -------
    dict
        Standardized message dict with these guaranteed fields:
          - source          : str  — original frontend identifier
          - source_window   : str  — business routing tag
          - user_id         : str  — sender identifier
          - message_type    : str  — "text", "image", "voice", "file", etc.
          - content         : str  — message body text
          - attachments     : list — list of attachment dicts
          - timestamp       : str  — ISO-8601 UTC
          - conversation_id : str  — conversation / chat thread ID
    """
    raw_message = raw_message or {}

    # ---- source ----
    source = _safe_str(raw_message.get("source"), "unknown")

    # ---- source_window (核心路由) ----
    raw_sw = raw_message.get("source_window")
    if raw_sw is not None and isinstance(raw_sw, str) and raw_sw.strip():
        source_window = raw_sw.strip()
    else:
        source_window = "general_assistant"

    # ---- user_id ----
    user_id = _safe_str(raw_message.get("user_id"), "unknown_user")

    # ---- message_type ----
    message_type = _safe_str(raw_message.get("message_type"), "text")

    # ---- content ----
    content = _safe_str(raw_message.get("content"), "")

    # ---- attachments ----
    attachments = raw_message.get("attachments", [])
    if not isinstance(attachments, list):
        attachments = []

    # ---- timestamp (ISO-8601 UTC) ----
    ts = raw_message.get("timestamp")
    if ts:
        # If it's a numeric Unix timestamp, convert to ISO string
        if isinstance(ts, (int, float)):
            timestamp = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        else:
            timestamp = str(ts)
    else:
        timestamp = datetime.now(timezone.utc).isoformat()

    # ---- conversation_id ----
    conversation_id = _safe_str(raw_message.get("conversation_id"), "default")

    return {
        "source": source,
        "source_window": source_window,
        "user_id": user_id,
        "message_type": message_type,
        "content": content,
        "attachments": attachments,
        "timestamp": timestamp,
        "conversation_id": conversation_id,
    }


def _safe_str(value: Any, default: str = "") -> str:
    """Safely convert a value to string, returning *default* on failure."""
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default
