"""
gsp_wechat_entry_router.py — GSP WeChat Multi-Entry Router.

Routes incoming WeChat messages to the correct GSP Agent based on:
  1. bot_name → wechat_entries.json lookup
  2. source_window → wechat_entries.json lookup
  3. Fallback: gsp_service (never gsp_admin)

Enforces:
  - Admin entry: owner/admin only. Others get permission denied.
  - Service entry: routes to Service Agent for dispatch.
  - Reimbursement entry: optional direct access (disabled by default).
  - Never falls back to Admin entry.

Logs all routing decisions; never logs secrets.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from hermes.core.message import normalised_message_factory

# ══════════════════════════════════════════════════════════════════
#  Paths
# ══════════════════════════════════════════════════════════════════

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "config", "wechat_entries.json"
)

_logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  Config loader (with cache)
# ══════════════════════════════════════════════════════════════════

_entries_cache: Optional[List[dict]] = None
_fallback_cache: Optional[dict] = None
_security_cache: Optional[dict] = None


def _load_config() -> dict:
    """Load wechat_entries.json. Returns empty dict on failure."""
    path = os.path.abspath(_CONFIG_PATH)
    if not os.path.isfile(path):
        _logger.warning("wechat_entries.json not found at %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as exc:
        _logger.error("Failed to load wechat_entries.json: %s", exc)
        return {}


def _get_entries() -> List[dict]:
    """Return the list of entry definitions."""
    global _entries_cache
    if _entries_cache is None:
        cfg = _load_config()
        _entries_cache = cfg.get("entries", [])
    return _entries_cache


def _get_fallback() -> dict:
    """Return the fallback entry definition."""
    global _fallback_cache
    if _fallback_cache is None:
        cfg = _load_config()
        fb = cfg.get("fallback", {})
        _fallback_cache = {
            "entry_id": fb.get("entry_id", "gsp_service"),
            "target_agent": "gsp_service_agent",
            "reason": fb.get("reason", "Unrecognised entry — falling back to GSP Service Agent."),
        }
    return _fallback_cache


def _get_security() -> dict:
    """Return the security policy dict."""
    global _security_cache
    if _security_cache is None:
        cfg = _load_config()
        _security_cache = cfg.get("security", {})
    return _security_cache


# ══════════════════════════════════════════════════════════════════
#  Entry matching
# ══════════════════════════════════════════════════════════════════


def _match_bot_name(bot_name: str) -> Optional[dict]:
    """Match a bot_name to an entry definition. Case-insensitive."""
    if not bot_name:
        return None
    bn = bot_name.strip().lower()
    for entry in _get_entries():
        for name in entry.get("bot_names", []):
            if name.strip().lower() == bn:
                return entry
    return None


def _match_source_window(source_window: str) -> Optional[dict]:
    """Match a source_window to an entry definition."""
    if not source_window:
        return None
    sw = source_window.strip().lower()
    for entry in _get_entries():
        for win in entry.get("source_windows", []):
            if win.strip().lower() == sw:
                return entry
    return None


# ══════════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════════


def resolve_entry(
    *,
    bot_name: str = "",
    source_window: str = "",
    user_id: str = "",
    user_role: str = "employee",
) -> dict:
    """Resolve the correct GSP entry and target agent for a WeChat message.

    Resolution priority:
      1. Match by bot_name (from wechat_entries.json.bot_names)
      2. Match by source_window (from wechat_entries.json.source_windows)
      3. Fallback to gsp_service (NEVER admin)

    Admin entry enforcement:
      If the resolved entry is gsp_admin and user_role is NOT in
      allowed_roles, the entry is blocked and a permission-denied
      response is returned.

    Parameters
    ----------
    bot_name : str
        The bot name from the WeChat platform.
    source_window : str
        The source_window tag from the message normaliser.
    user_id : str
        The user's unique identifier.
    user_role : str
        The user's role (owner, admin, finance, manager, employee).

    Returns
    -------
    dict
        {
            "ok": bool,
            "entry_id": str,
            "target_agent": str,
            "source": "wechat",
            "user_id": str,
            "user_role": str,
            "route_reason": str,
            "blocked": bool,
            "block_reason": str,
            "reply_text": str,  # only set if blocked
        }
    """
    result = {
        "ok": True,
        "entry_id": "",
        "target_agent": "",
        "source": "wechat",
        "user_id": user_id,
        "user_role": user_role,
        "route_reason": "",
        "blocked": False,
        "block_reason": "",
        "reply_text": "",
    }

    # ── 1. Try bot_name match ─────────────────────────────────
    entry = _match_bot_name(bot_name)
    if entry:
        result["route_reason"] = f"matched bot_name '{bot_name}'"

    # ── 2. Try source_window match ────────────────────────────
    if not entry:
        entry = _match_source_window(source_window)
        if entry:
            result["route_reason"] = f"matched source_window '{source_window}'"

    # ── 3. Fallback ───────────────────────────────────────────
    if not entry:
        fb = _get_fallback()
        result["entry_id"] = fb["entry_id"]
        result["target_agent"] = fb["target_agent"]
        result["route_reason"] = fb.get("reason", "Fallback — unrecognised entry.")
        _logger.info(
            "WeChat entry fallback: bot_name=%r source_window=%r user=%r → %s",
            _safe_str(bot_name), _safe_str(source_window), _safe_str(user_id),
            result["target_agent"],
        )
        return result

    # ── 4. Resolve target agent ───────────────────────────────
    result["entry_id"] = entry["entry_id"]
    result["target_agent"] = entry.get("target_agent", "gsp_service_agent")

    # ── 5. Admin entry permission check ───────────────────────
    if entry["type"] == "admin_entry":
        allowed = entry.get("allowed_roles", [])
        if user_role not in allowed:
            sec = _get_security()
            result["ok"] = False
            result["blocked"] = True
            result["block_reason"] = "permission_denied_admin_entry"
            result["reply_text"] = sec.get(
                "block_message_for_unauthorized",
                "你当前没有 GSP Admin Agent 的权限。请使用 GSP Service Agent 入口提交业务请求。",
            )
            _logger.warning(
                "Admin entry blocked: user=%r role=%r entry=%s",
                _safe_str(user_id), user_role, entry["entry_id"],
            )

    return result


def route_wechat_message(
    *,
    bot_name: str = "",
    source_window: str = "",
    user_id: str = "",
    user_role: str = "employee",
    content: str = "",
    message_type: str = "text",
    attachments: Optional[List[dict]] = None,
    conversation_id: str = "",
) -> dict:
    """Full pipeline: resolve entry → build normalised message → return.

    This is the main entry point called by wechat_chatbot_adapter.
    """
    entry = resolve_entry(
        bot_name=bot_name,
        source_window=source_window,
        user_id=user_id,
        user_role=user_role,
    )

    # If blocked, return immediately
    if entry["blocked"]:
        return {
            "ok": False,
            "entry_id": entry["entry_id"],
            "target_agent": entry["target_agent"],
            "source": "wechat",
            "user_id": user_id,
            "user_role": user_role,
            "reply_text": entry["reply_text"],
            "route_reason": entry["route_reason"],
            "blocked": True,
            "block_reason": entry["block_reason"],
            "normalised_message": None,
        }

    # Build normalised message
    msg = normalised_message_factory(
        content=content,
        message_type=message_type,
        source="wechat",
        user_id=user_id,
        conversation_id=conversation_id,
        attachments=attachments or [],
    )

    return {
        "ok": True,
        "entry_id": entry["entry_id"],
        "target_agent": entry["target_agent"],
        "source": "wechat",
        "user_id": user_id,
        "user_role": user_role,
        "reply_text": "",
        "route_reason": entry["route_reason"],
        "blocked": False,
        "block_reason": "",
        "normalised_message": msg,
    }


def list_entries() -> List[dict]:
    """Return all configured entries (for status/debugging)."""
    return [
        {
            "entry_id": e["entry_id"],
            "display_name": e["display_name"],
            "type": e["type"],
            "target_agent": e["target_agent"],
            "default_enabled": e.get("default_enabled", True),
        }
        for e in _get_entries()
    ]


# ══════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════


def _safe_str(s: Any, max_len: int = 40) -> str:
    """Truncate a string for safe logging."""
    if not isinstance(s, str):
        return str(s)[:max_len]
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s
