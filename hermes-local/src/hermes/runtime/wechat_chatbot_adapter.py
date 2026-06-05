"""
wechat_chatbot_adapter.py

WeChat chatbot adapter for the Hermes local Gateway.

Converts WeChat chatbot messages into gateway-compatible payloads,
processes them through the full pipeline, and extracts reply text
suitable for sending back to the WeChat chatbot.

This is designed to be used by a WeChat chatbot handler BEFORE migrating
to the WeCom (企业微信) smart bot. Once the business flow is verified,
the same gateway payload format can be reused by the WeCom bot.

Supported bot_names:
  - "报销助手" → expense / reimbursement_assistant
  - "Hermes助手" → general / general_assistant
  - unknown → general / general_assistant
"""

import json
import os
import sys
from typing import Any, Optional

# Ensure we can import sibling modules
_src = os.path.dirname(os.path.abspath(__file__))
_src_parent = os.path.dirname(_src)
if _src_parent not in sys.path:
    sys.path.insert(0, _src_parent)

# ── Runtime safety import ───────────────────────────────────
from hermes.runtime.runtime_safety import detect_forbidden_runtime_command

from hermes.runtime.gateway import handle_gateway_message

# ══════════════════════════════════════════════════════════════════
#  Bot name -> frontend_entry / source_window mapping
# ══════════════════════════════════════════════════════════════════

_BOT_MAPPING = {
    "报销助手": {
        "frontend_entry": "expense",
        "source_window": "reimbursement_assistant",
    },
    "hermes助手": {
        "frontend_entry": "general",
        "source_window": "general_assistant",
    },
}

_DEFAULT_BOT = {
    "frontend_entry": "general",
    "source_window": "general_assistant",
}


def _resolve_bot(bot_name: Optional[str]) -> dict:
    """Resolve bot_name to frontend_entry and source_window."""
    if not bot_name or not isinstance(bot_name, str):
        return dict(_DEFAULT_BOT)
    key = bot_name.strip().lower()
    return _BOT_MAPPING.get(key, dict(_DEFAULT_BOT))


# ══════════════════════════════════════════════════════════════════
#  Conversion: WeChat chatbot message -> Gateway payload
# ══════════════════════════════════════════════════════════════════


def convert_wechat_chatbot_message_to_gateway_payload(message: dict) -> dict:
    """
    Convert a WeChat chatbot message dict to a gateway-compatible payload.

    Parameters
    ----------
    message : dict
        Expected keys:
          - source (str, default "wechat_chatbot")
          - bot_name (str, optional): "报销助手" or "Hermes助手"
          - user_id (str): WeChat user ID
          - message_type (str): "text" or "image"
          - content (str): message text
          - attachments (list, optional): list of attachment dicts
          - conversation_id (str, optional): if empty, auto-generated

    Returns
    -------
    dict — gateway-compatible payload
    """
    if not isinstance(message, dict):
        message = {}

    source = str(message.get("source", "wechat_chatbot"))
    bot_name = message.get("bot_name")
    user_id = str(message.get("user_id", "unknown_user"))
    message_type = str(message.get("message_type", "text"))
    content = str(message.get("content", ""))
    attachments = message.get("attachments", [])
    if not isinstance(attachments, list):
        attachments = []

    # ── Resolve bot -> entry ────────────────────────────────────
    bot_cfg = _resolve_bot(bot_name)
    frontend_entry = bot_cfg["frontend_entry"]
    source_window = bot_cfg["source_window"]

    # ── Conversation ID ─────────────────────────────────────────
    conversation_id = str(message.get("conversation_id", "") or "")
    if not conversation_id:
        conversation_id = f"wechat:{frontend_entry}:{user_id}"

    # ── Build payload ───────────────────────────────────────────
    payload = {
        "source": source,
        "frontend_entry": frontend_entry,
        "source_window": source_window,
        "user_id": user_id,
        "message_type": message_type,
        "content": content,
        "attachments": attachments,
        "conversation_id": conversation_id,
        "timestamp": "",
        "raw": dict(message),
    }

    return payload


# ══════════════════════════════════════════════════════════════════
#  Full pipeline: convert → dispatch → reply text
# ══════════════════════════════════════════════════════════════════


def handle_wechat_chatbot_message(message: dict) -> dict:
    """
    Full pipeline for a WeChat chatbot message.

      1. Convert to gateway payload
      2. Dispatch through handle_gateway_message()
      3. Extract reply text

    Parameters
    ----------
    message : dict
        WeChat chatbot message dict.

    Returns
    -------
    dict with keys: success, reply_text, gateway_response
    """
    payload = convert_wechat_chatbot_message_to_gateway_payload(message)

    # ── Runtime safety check ──────────────────────────────────
    content = str(message.get("content", ""))
    safety = detect_forbidden_runtime_command(content)
    if safety.get("blocked"):
        return {
            "success": True,
            "reply_text": safety.get("user_message",
                "当前微信入口仅用于业务处理，不能执行系统维护、代码修改或敏感配置操作。"),
            "gateway_response": {
                "success": True,
                "content": safety.get("user_message", ""),
                "result": {"next_action": "manual_review", "module": "unknown"},
                "safety_blocked": True,
                "safety_category": safety.get("category", ""),
            },
        }

    try:
        gateway_response = handle_gateway_message(payload)
    except Exception as exc:
        return {
            "success": False,
            "reply_text": f"处理消息时出错，请稍后重试。",
            "gateway_response": None,
        }

    # ── Extract reply text ──────────────────────────────────────
    reply_text = ""
    if isinstance(gateway_response, dict):
        reply_text = gateway_response.get("content", "")
        if not reply_text:
            reply_text = gateway_response.get("user_message", "")
        if not reply_text:
            # Try nested in result
            result = gateway_response.get("result", {})
            if isinstance(result, dict):
                reply_text = result.get("content", "") or result.get("user_message", "")

    if not reply_text:
        reply_text = "已收到消息，但暂无可返回内容。"

    return {
        "success": True,
        "reply_text": reply_text,
        "gateway_response": gateway_response,
    }
