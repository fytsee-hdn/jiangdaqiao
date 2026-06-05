"""
wecom_client.py

WeCom (企业微信) client — access_token management and message sending.

Modes (controlled by WECOM_API_MODE env var):
  - "mock" (default): Returns fake tokens, does NOT call WeCom API
  - "real": Calls real WeCom API (requires configured secrets)

Auto-reply controlled by WECOM_AUTO_REPLY env var:
  - "0" (default): No auto-reply
  - "1": Automatically send text reply after processing
"""

import json
import os
import time
from typing import Optional

# Ensure we can import sibling modules
import sys as _sys
_src = os.path.dirname(os.path.abspath(__file__))
_src_parent = os.path.dirname(_src)
if _src_parent not in _sys.path:
    _sys.path.insert(0, _src_parent)

from hermes.runtime.wecom_config import load_wecom_config
from hermes.runtime.gateway_logger import log_gateway_event, generate_request_id

# ══════════════════════════════════════════════════════════════════
#  Mode detection
# ══════════════════════════════════════════════════════════════════

_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
_SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"


def is_mock_mode() -> bool:
    """Return True if WECOM_API_MODE=mock."""
    mode = os.environ.get("WECOM_API_MODE", "mock").strip().lower()
    return mode != "real"


def is_auto_reply_enabled() -> bool:
    """Return True if WECOM_AUTO_REPLY=1."""
    return os.environ.get("WECOM_AUTO_REPLY", "0").strip() == "1"


# ══════════════════════════════════════════════════════════════════
#  Token cache (in-memory)
# ══════════════════════════════════════════════════════════════════

_token_cache = {}  # agent_key -> {"token": str, "expires_at": int}


# ══════════════════════════════════════════════════════════════════
#  Access token API
# ══════════════════════════════════════════════════════════════════


def get_wecom_access_token(
    agent_key: str = "expense",
    force_refresh: bool = False,
) -> dict:
    """
    Get a WeCom access_token for the given agent.

    Parameters
    ----------
    agent_key : str
        "expense" or "general"
    force_refresh : bool
        If True, bypass cache and fetch fresh token.

    Returns
    -------
    dict with keys: success, agent_key, access_token, expires_at,
                    from_cache, error
    """
    rid = generate_request_id()
    now = time.time()

    # ── Check cache ────────────────────────────────────────────
    if not force_refresh and agent_key in _token_cache:
        cached = _token_cache[agent_key]
        if cached["expires_at"] > now + 300:  # 5 min buffer
            log_gateway_event("wecom_access_token_cached", {
                "request_id": rid,
                "agent_key": agent_key,
                "summary": f"token_cached_agent={agent_key}",
            })
            return {
                "success": True,
                "agent_key": agent_key,
                "access_token": cached["token"],
                "expires_at": cached["expires_at"],
                "from_cache": True,
                "error": "",
            }

    # ── Load config ─────────────────────────────────────────────
    config = load_wecom_config(mask_secrets=False)
    corp_id = config.get("corp_id", "")
    agent_cfg = config.get("agents", {}).get(agent_key, {})
    agent_secret = agent_cfg.get("secret", "")

    # ── Mock mode ──────────────────────────────────────────────
    if is_mock_mode():
        mock_token = f"mock_access_token_{agent_key}"
        expires_at = int(now + 7200)
        _token_cache[agent_key] = {"token": mock_token, "expires_at": expires_at}
        return {
            "success": True,
            "agent_key": agent_key,
            "access_token": mock_token,
            "expires_at": expires_at,
            "from_cache": False,
            "error": "",
        }

    # ── Real mode ──────────────────────────────────────────────
    if not corp_id or not agent_secret:
        return {
            "success": False,
            "agent_key": agent_key,
            "access_token": "",
            "expires_at": 0,
            "from_cache": False,
            "error": f"Missing config: corp_id={'yes' if corp_id else 'no'}, "
                     f"secret={'yes' if agent_secret else 'no'}",
        }

    log_gateway_event("wecom_access_token_requested", {
        "request_id": rid,
        "agent_key": agent_key,
        "summary": f"requesting_token_agent={agent_key}",
    })

    try:
        import urllib.request
        url = f"{_TOKEN_URL}?corpid={corp_id}&corpsecret={agent_secret}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {
            "success": False,
            "agent_key": agent_key,
            "access_token": "",
            "expires_at": 0,
            "from_cache": False,
            "error": f"HTTP error: {exc}",
        }

    if data.get("errcode", -1) != 0:
        return {
            "success": False,
            "agent_key": agent_key,
            "access_token": "",
            "expires_at": 0,
            "from_cache": False,
            "error": f"WeCom error {data.get('errcode')}: {data.get('errmsg', '')}",
        }

    token = data.get("access_token", "")
    expires_in = data.get("expires_in", 7200)
    expires_at = int(now + expires_in)
    _token_cache[agent_key] = {"token": token, "expires_at": expires_at}

    return {
        "success": True,
        "agent_key": agent_key,
        "access_token": token,
        "expires_at": expires_at,
        "from_cache": False,
        "error": "",
    }


# ══════════════════════════════════════════════════════════════════
#  Send text message
# ══════════════════════════════════════════════════════════════════

_MAX_CONTENT_LEN = 1900

_AGENT_KEY_TO_ID = {
    "expense": None,  # resolved dynamically from config
    "general": None,
}


def _resolve_agent_id(agent_key: str) -> Optional[str]:
    """Get the numeric agent_id for a given agent_key."""
    config = load_wecom_config(mask_secrets=False)
    return config.get("agents", {}).get(agent_key, {}).get("agent_id", "")


def send_wecom_text_message(
    touser: str,
    content: str,
    agent_key: str = "expense",
) -> dict:
    """
    Send a text message to a WeCom user.

    Parameters
    ----------
    touser : str
        WeCom user ID (FromUserName).
    content : str
        Text content. Truncated at 1900 chars.
    agent_key : str
        "expense" or "general"

    Returns
    -------
    dict with keys: success, agent_key, touser, errcode, errmsg, mode
    """
    rid = generate_request_id()

    if not content:
        content = "已收到消息。"

    # Truncate content
    if len(content) > _MAX_CONTENT_LEN:
        content = content[:_MAX_CONTENT_LEN] + "..."

    # ── Token ───────────────────────────────────────────────────
    token_result = get_wecom_access_token(agent_key)
    if not token_result.get("success"):
        log_gateway_event("wecom_message_send_failed", {
            "request_id": rid,
            "agent_key": agent_key,
            "touser": touser,
            "error": token_result.get("error", ""),
            "summary": f"send_failed_token_error",
        })
        return {
            "success": False,
            "agent_key": agent_key,
            "touser": touser,
            "errcode": -1,
            "errmsg": token_result.get("error", ""),
            "mode": "mock" if is_mock_mode() else "real",
        }

    access_token = token_result.get("access_token", "")

    # ── Resolve agent_id ────────────────────────────────────────
    agent_id_str = _resolve_agent_id(agent_key)
    try:
        agent_id = int(agent_id_str) if agent_id_str else 0
    except (ValueError, TypeError):
        agent_id = 0

    log_gateway_event("wecom_message_send_attempt", {
        "request_id": rid,
        "agent_key": agent_key,
        "touser": touser,
        "summary": f"sending_text_to_{touser}",
    })

    # ── Mock mode ──────────────────────────────────────────────
    if is_mock_mode():
        log_gateway_event("wecom_message_send_success", {
            "request_id": rid,
            "agent_key": agent_key,
            "touser": touser,
            "mode": "mock",
            "summary": f"mock_send_text_to_{touser}",
        })
        return {
            "success": True,
            "agent_key": agent_key,
            "touser": touser,
            "errcode": 0,
            "errmsg": "mock send ok",
            "mode": "mock",
        }

    # ── Real mode ──────────────────────────────────────────────
    try:
        import urllib.request

        send_url = f"{_SEND_URL}?access_token={access_token}"
        payload = json.dumps({
            "touser": touser,
            "msgtype": "text",
            "agentid": agent_id,
            "text": {"content": content},
            "safe": 0,
        }).encode("utf-8")

        req = urllib.request.Request(
            send_url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log_gateway_event("wecom_message_send_failed", {
            "request_id": rid,
            "agent_key": agent_key,
            "error": str(exc),
            "summary": "send_http_error",
        })
        return {
            "success": False,
            "agent_key": agent_key,
            "touser": touser,
            "errcode": -1,
            "errmsg": f"HTTP error: {exc}",
            "mode": "real",
        }

    if data.get("errcode", -1) != 0:
        log_gateway_event("wecom_message_send_failed", {
            "request_id": rid,
            "agent_key": agent_key,
            "errcode": data.get("errcode"),
            "summary": f"wecom_api_error_{data.get('errcode')}",
        })
        return {
            "success": False,
            "agent_key": agent_key,
            "touser": touser,
            "errcode": data.get("errcode"),
            "errmsg": data.get("errmsg", ""),
            "mode": "real",
        }

    log_gateway_event("wecom_message_send_success", {
        "request_id": rid,
        "agent_key": agent_key,
        "touser": touser,
        "mode": "real",
        "summary": f"real_send_text_to_{touser}",
    })
    return {
        "success": True,
        "agent_key": agent_key,
        "touser": touser,
        "errcode": 0,
        "errmsg": "ok",
        "mode": "real",
    }


# ══════════════════════════════════════════════════════════════════
#  Reply builder
# ══════════════════════════════════════════════════════════════════


def _resolve_agent_key_from_agent_id(agent_id: str) -> str:
    """Map a WeCom AgentID string to an agent_key."""
    from hermes.runtime.wecom_adapter import _get_agent_mapping
    mapping = _get_agent_mapping()
    for key, cfg in mapping.items():
        if str(key) == str(agent_id):
            fe = cfg.get("frontend_entry", "")
            if fe == "expense":
                return "expense"
            if fe == "general":
                return "general"
    return "general"


def send_wecom_reply_for_gateway_response(
    wecom_message: dict,
    gateway_response: dict,
) -> dict:
    """
    Extract user + content from a WeCom callback and gateway response,
    then send a text reply.

    Parameters
    ----------
    wecom_message : dict
        Original WeCom message dict (needs FromUserName, AgentID).
    gateway_response : dict
        Response from handle_wecom_mock_message() or handle_gateway_message().

    Returns
    -------
    dict — result from send_wecom_text_message()
    """
    # ── Determine recipient ────────────────────────────────────
    touser = str(wecom_message.get("FromUserName", ""))
    if not touser:
        return {
            "success": False,
            "error": "No FromUserName in wecom_message",
        }

    # ── Determine agent_key ────────────────────────────────────
    agent_id = str(wecom_message.get("AgentID", ""))
    agent_key = _resolve_agent_key_from_agent_id(agent_id)

    # ── Extract content ────────────────────────────────────────
    content = ""
    # Try direct result
    if isinstance(gateway_response, dict):
        content = gateway_response.get("result", {}).get("content", "")
        if not content:
            content = gateway_response.get("gateway_response", {}).get(
                "result", {}).get("content", "")
        if not content:
            content = gateway_response.get("content", "")
        if not content:
            content = gateway_response.get("gateway_response", {}).get(
                "content", "")

    if not content:
        content = "已收到消息，但暂无可返回内容。"

    # ── Send ───────────────────────────────────────────────────
    return send_wecom_text_message(touser, content, agent_key)
