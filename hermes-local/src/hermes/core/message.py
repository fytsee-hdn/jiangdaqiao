"""
message.py — Standard message / result data structures for the GSP architecture.

Defines the canonical shape of messages flowing between agents.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ══════════════════════════════════════════════════════════════════
#  Normalised Message (input to agents)
# ══════════════════════════════════════════════════════════════════

def normalised_message_factory(
    *,
    content: str = "",
    message_type: str = "text",
    source: str = "unknown",
    user_id: str = "unknown_user",
    conversation_id: str = "",
    attachments: Optional[List[dict]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> dict:
    """Build a normalised message dict consumed by all agents."""
    return {
        "content": content,
        "message_type": message_type,
        "source": source,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "attachments": attachments or [],
        "metadata": metadata or {},
    }


# ══════════════════════════════════════════════════════════════════
#  Agent Result (output from agents)
# ══════════════════════════════════════════════════════════════════

def agent_result_factory(
    *,
    ok: bool = True,
    agent_id: str = "",
    reply_text: str = "",
    data: Optional[Dict[str, Any]] = None,
    audit_event: Optional[dict] = None,
    next_state: Optional[dict] = None,
    error: str = "",
) -> dict:
    """Build a standard agent result dict."""
    return {
        "ok": ok,
        "agent_id": agent_id,
        "reply_text": reply_text,
        "data": data or {},
        "audit_event": audit_event,
        "next_state": next_state,
        "error": error,
    }
