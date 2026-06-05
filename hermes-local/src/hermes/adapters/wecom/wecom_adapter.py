"""
wecom_adapter.py

WeCom (企业微信) message adapter for the Hermes local Gateway.

Converts mock WeCom message dicts into gateway-compatible payloads
that can be passed to handle_gateway_message().

This is a PURE DATA TRANSFORMATION layer:

  - Does NOT connect to real WeCom backend
  - Does NOT handle AES encryption/decryption
  - Does NOT download media files (MediaId is kept as metadata)
  - Does NOT verify WeCom signatures
  - Does NOT make any HTTP requests

Supported MsgTypes:
  - text
  - image
  - voice, video, file, location → "unsupported" (passthrough)

AgentID -> frontend_entry mapping:
  - 1000002 → expense / reimbursement_assistant (报销助手)
  - 1000003 → general / general_assistant (Hermes助手)
  - unknown → general / general_assistant
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

# Ensure we can import sibling modules
_src = os.path.dirname(os.path.abspath(__file__))
_src_parent = os.path.dirname(_src)  # hermes/
if _src_parent not in sys.path:
    sys.path.insert(0, _src_parent)

from hermes.runtime.gateway import handle_gateway_message
from hermes.runtime.wecom_config import get_agent_mapping_from_config


# ══════════════════════════════════════════════════════════════════
#  AgentID -> frontend_entry / source_window mapping
#  Dynamically loaded from config (env vars), with fallback
# ══════════════════════════════════════════════════════════════════

_DEFAULT_AGENT_MAPPING = {
    "1000002": {
        "name": "报销助手",
        "frontend_entry": "expense",
        "source_window": "reimbursement_assistant",
    },
    "1000003": {
        "name": "Hermes助手",
        "frontend_entry": "general",
        "source_window": "general_assistant",
    },
}


def _get_agent_mapping() -> dict:
    """Return the current AgentID mapping, dynamic from config with fallback."""
    dynamic = get_agent_mapping_from_config()
    if dynamic:
        return dynamic
    return _DEFAULT_AGENT_MAPPING

_DEFAULT_AGENT = {
    "name": "默认助手",
    "frontend_entry": "general",
    "source_window": "general_assistant",
}


def _lookup_agent(agent_id: Any) -> dict:
    """Look up agent config by ID. Returns default if not found."""
    key = str(agent_id).strip() if agent_id is not None else ""
    mapping = _get_agent_mapping()
    return mapping.get(key, _DEFAULT_AGENT)


# ══════════════════════════════════════════════════════════════════
#  Conversion: WeCom message -> Gateway payload
# ══════════════════════════════════════════════════════════════════


def convert_wecom_message_to_gateway_payload(wecom_message: dict) -> dict:
    """
    Convert a mock WeCom message dict to a gateway-compatible payload.

    Parameters
    ----------
    wecom_message : dict
        Mock WeCom callback message dict. Expected keys:
          - ToUserName, FromUserName, CreateTime, MsgType, MsgId, AgentID
          - Content (for text)
          - PicUrl, MediaId (for image)

    Returns
    -------
    dict — gateway-compatible payload with keys:
        source, frontend_entry, source_window, user_id,
        message_type, content, attachments, conversation_id, raw
    """
    if not isinstance(wecom_message, dict):
        wecom_message = {}

    # ── Extract core WeCom fields ───────────────────────────────
    msg_type = str(wecom_message.get("MsgType", "")).strip().lower()
    from_user = str(wecom_message.get("FromUserName", "unknown_user"))
    agent_id = str(wecom_message.get("AgentID", ""))
    content = str(wecom_message.get("Content", ""))

    # ── Agent mapping ───────────────────────────────────────────
    agent_cfg = _lookup_agent(agent_id)
    source_window = agent_cfg["source_window"]
    frontend_entry = agent_cfg["frontend_entry"]

    # ── conversation_id ────────────────────────────────────────
    conversation_id = f"wecom:{agent_id}:{from_user}"

    # ── Message-type-specific conversion ────────────────────────
    gwy_message_type = msg_type
    gwy_content = content
    attachments = []

    if msg_type == "text":
        gwy_message_type = "text"
        gwy_content = content
        attachments = []

    elif msg_type == "image":
        gwy_message_type = "image"
        gwy_content = ""
        attachments = [
            {
                "file_type": "image",
                "media_id": str(wecom_message.get("MediaId", "")),
                "url": str(wecom_message.get("PicUrl", "")),
                "file_path": "",
            }
        ]

    else:
        # Unsupported MsgType: voice, video, file, location, etc.
        gwy_message_type = "unsupported"
        gwy_content = ""
        attachments = []

    # ── Build gateway payload ───────────────────────────────────
    payload = {
        "source": "wecom",
        "frontend_entry": frontend_entry,
        "source_window": source_window,
        "user_id": from_user,
        "message_type": gwy_message_type,
        "content": gwy_content,
        "attachments": attachments,
        "conversation_id": conversation_id,
        "raw": dict(wecom_message),
    }

    return payload


# ══════════════════════════════════════════════════════════════════
#  Mock handler: convert + dispatch
# ══════════════════════════════════════════════════════════════════


def handle_wecom_mock_message(wecom_message: dict) -> dict:
    """
    Full mock WeCom message handling pipeline:

      1. convert_wecom_message_to_gateway_payload()
      2. handle_gateway_message()
      3. Return gateway response

    Parameters
    ----------
    wecom_message : dict
        Mock WeCom callback message.

    Returns
    -------
    dict — gateway response with keys: success, source_window,
           conversation_id, result
    """
    payload = convert_wecom_message_to_gateway_payload(wecom_message)
    return handle_gateway_message(payload)
