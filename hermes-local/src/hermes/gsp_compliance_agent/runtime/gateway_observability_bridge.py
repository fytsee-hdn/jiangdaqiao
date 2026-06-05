"""
gateway_observability_bridge.py — GSP Compliance Agent: Gateway Observability Hook.

Metadata-only bridge that normalizes source_window for incoming Hermes gateway
events and writes observability records. Does NOT modify message content,
routing, or business logic.

Used for: tracing WeCom/WeChat messages before GSP business workflow is activated.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Bangkok")
except ImportError:
    _TZ = timezone(timedelta(hours=7))

_logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  Paths
# ══════════════════════════════════════════════════════════════════

_NORMALIZATION_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
    "config", "agent_windows", "source_window_normalization.json",
)

_OBSERVABILITY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
    "data", "knowledge", "compliance", "gateway_observability", "gateway_events.jsonl",
)

# ══════════════════════════════════════════════════════════════════
#  Config loading
# ══════════════════════════════════════════════════════════════════

_norm_cache: Optional[dict] = None


def _load_normalization() -> dict:
    global _norm_cache
    if _norm_cache is not None:
        return _norm_cache
    path = os.path.abspath(_NORMALIZATION_PATH)
    try:
        with open(path, "r", encoding="utf-8") as f:
            _norm_cache = json.load(f)
    except Exception:
        _norm_cache = {"mappings": {}, "fallback": {"source_window": "unknown", "target_agent": "gsp_service_agent", "requires_review": True}}
    return _norm_cache


# ══════════════════════════════════════════════════════════════════
#  Logic
# ══════════════════════════════════════════════════════════════════

def resolve_source_window(
    platform: str,
    profile: str = "default",
) -> dict:
    """Resolve source_window and target_agent for a platform/profile pair.

    Returns
    -------
    dict with: source_window, target_agent, is_business_user_entry, requires_review, mapping_source
    """
    cfg = _load_normalization()
    profile_map = cfg.get("mappings", {}).get(profile, {})
    platform_map = profile_map.get(platform, {})

    if platform_map and platform_map.get("status") != "reserved_not_active":
        return {
            "source_window": platform_map.get("source_window", "unknown"),
            "target_agent": platform_map.get("target_agent", "gsp_service_agent"),
            "is_business_user_entry": platform_map.get("is_business_user_entry", False),
            "requires_review": False,
            "mapping_source": f"profile={profile}, platform={platform}",
        }

    if platform_map and platform_map.get("status") == "reserved_not_active":
        return {
            "source_window": "unknown",
            "target_agent": "gsp_service_agent",
            "is_business_user_entry": False,
            "requires_review": True,
            "mapping_source": f"reserved_not_active: profile={profile}, platform={platform}",
        }

    fb = cfg.get("fallback", {})
    return {
        "source_window": fb.get("source_window", "unknown"),
        "target_agent": fb.get("target_agent", "gsp_service_agent"),
        "is_business_user_entry": False,
        "requires_review": fb.get("requires_review", True),
        "mapping_source": "fallback",
    }


def record_gateway_event(
    *,
    platform: str,
    profile: str = "default",
    user_id: str = "",
    chat_id: str = "",
    message_type: str = "text",
    native_log_ref: str = "",
) -> dict:
    """Record a metadata-only gateway observability event.

    Does NOT log message content, file content, or secrets.
    """
    resolved = resolve_source_window(platform, profile)
    now = datetime.now(_TZ).isoformat()

    record = {
        "event_id": f"gw-obs-{uuid.uuid4().hex[:12]}",
        "timestamp": now,
        "profile": profile,
        "platform": platform,
        "source_window": resolved["source_window"],
        "target_agent": resolved["target_agent"],
        "user_id_hash": _hash(user_id) if user_id else "",
        "chat_id_hash": _hash(chat_id) if chat_id else "",
        "message_type": message_type,
        "routing_stage": "gateway_observed",
        "is_business_user_entry": resolved["is_business_user_entry"],
        "requires_review": resolved["requires_review"],
        "mapping_source": resolved["mapping_source"],
        "native_log_ref": native_log_ref,
        "created_at": now,
    }

    try:
        path = os.path.abspath(_OBSERVABILITY_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        _logger.warning("Failed to write observability event: %s", exc)

    return record


def _hash(s: str) -> str:
    """One-way hash for user/chat identifiers."""
    if not s:
        return ""
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def read_observability_log(limit: int = 50) -> list:
    """Read recent observability events."""
    path = os.path.abspath(_OBSERVABILITY_PATH)
    if not os.path.isfile(path):
        return []
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-limit:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return entries


def count_by_source_window() -> dict:
    """Count observability events by source_window."""
    from collections import Counter
    entries = read_observability_log(1000)
    return dict(Counter(e.get("source_window", "unknown") for e in entries))


def count_by_platform() -> dict:
    """Count observability events by platform."""
    from collections import Counter
    entries = read_observability_log(1000)
    return dict(Counter(e.get("platform", "unknown") for e in entries))
