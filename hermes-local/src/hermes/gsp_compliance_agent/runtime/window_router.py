"""
window_router.py — GSP Compliance Agent: Window Routing Runtime.

Reads config/agent_windows/window_agent_map.json and routes incoming
interactions to the correct target agent based on window_id.

Rules:
  - Professional windows → direct_to_agent
  - common_window → through_service_agent (gsp_service_agent)
  - Unknown window → fallback to common_window
  - All routing decisions are logged.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
    "config", "agent_windows", "window_agent_map.json",
)

_cache: Optional[dict] = None


def _load_window_map() -> dict:
    """Load the window-agent map. Cached after first load."""
    global _cache
    if _cache is not None:
        return _cache

    path = os.path.abspath(_CONFIG_PATH)
    try:
        with open(path, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        _logger.error("Failed to load window_agent_map.json: %s", exc)
        _cache = {"windows": []}
    return _cache


def get_window(window_id: str) -> Optional[dict]:
    """Look up a single window by window_id."""
    for w in _load_window_map().get("windows", []):
        if w.get("window_id") == window_id:
            return dict(w)
    return None


def route_window(window_id: str) -> dict:
    """Route a window_id to a target agent + routing rule.

    Returns
    -------
    dict
        {
            "ok": bool,
            "window_id": str,
            "target_agent": str,
            "routing_rule": str,
            "window_type": str,
            "fallback": bool,
            "reason": str,
        }
    """
    window = get_window(window_id)

    if window is None:
        # Fallback to common_window
        fallback = get_window("common_window") or {}
        _logger.warning(
            "Unknown window '%s' — falling back to common_window → %s",
            window_id, fallback.get("target_agent", "gsp_service_agent"),
        )
        return {
            "ok": True,
            "window_id": window_id,
            "target_agent": fallback.get("target_agent", "gsp_service_agent"),
            "routing_rule": "through_service_agent",
            "window_type": "common_window",
            "fallback": True,
            "display_name": fallback.get("display_name", "GSP Service Window"),
            "reason": f"Unknown window '{window_id}' — fallback to common_window.",
        }

    return {
        "ok": True,
        "window_id": window["window_id"],
        "target_agent": window["target_agent"],
        "routing_rule": window.get("routing_rule", "direct_to_agent"),
        "window_type": window.get("window_type", "professional_window"),
        "fallback": False,
        "display_name": window.get("display_name", ""),
        "reason": f"Window '{window_id}' routed to {window['target_agent']}.",
    }


def check_window_access(window_id: str, user_role: str) -> dict:
    """Check if a user role can access a given window.

    Returns
    -------
    dict
        {"allowed": bool, "reason": str}
    """
    window = get_window(window_id)
    if window is None:
        return {"allowed": False, "reason": f"Window '{window_id}' not found."}

    allowed_roles = window.get("allowed_roles", [])
    denied_roles = window.get("denied_roles", [])

    if denied_roles and user_role in denied_roles:
        return {
            "allowed": False,
            "reason": f"Role '{user_role}' is explicitly denied for window '{window_id}'.",
        }

    if allowed_roles and user_role not in allowed_roles:
        return {
            "allowed": False,
            "reason": f"Role '{user_role}' not in allowed_roles for window '{window_id}'. Allowed: {allowed_roles}",
        }

    return {"allowed": True, "reason": f"Role '{user_role}' has access to window '{window_id}'."}


def list_windows() -> List[dict]:
    """Return all configured windows."""
    return [
        {
            "window_id": w["window_id"],
            "display_name": w.get("display_name", ""),
            "target_agent": w["target_agent"],
            "window_type": w.get("window_type", ""),
            "routing_rule": w.get("routing_rule", ""),
        }
        for w in _load_window_map().get("windows", [])
    ]
