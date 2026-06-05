"""
wechat_chatbot_bridge.py

Bridge between the Hermes Weixin platform adapter and the local
WeChat chatbot adapter.

Converts Hermes MessageEvent-style objects into the format expected
by handle_wechat_chatbot_message(), then dispatches and returns the reply.

This is a PURE BRIDGE — it does NOT modify any Hermes本体 files,
does NOT register callbacks, and does NOT restart the gateway.

Phase 32: When event has media_urls but no local media_paths,
automatically downloads images to uploads/wechat/YYYYMMDD/ for
subsequent real OCR processing.

Usage (sync):
    from hermes.runtime.wechat_chatbot_bridge import handle_weixin_event_sync
    result = handle_weixin_event_sync(event)
    reply = extract_reply_text(result)

Usage (async):
    from hermes.runtime.wechat_chatbot_bridge import handle_weixin_event_async
    result = await handle_weixin_event_async(event)
"""

import asyncio
from typing import Any, Optional

from hermes.runtime.wechat_chatbot_adapter import (
    handle_wechat_chatbot_message,
)
from hermes.runtime.wechat_media_downloader import (
    download_wechat_media_url,
)

# ══════════════════════════════════════════════════════════════════
#  Safe attribute/dict access
# ══════════════════════════════════════════════════════════════════


def _get_attr(obj: Any, attr: str, default: Any = "") -> Any:
    """Safely read an attribute or dict key from an object."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _get_str(obj: Any, attr: str, default: str = "") -> str:
    """Get a string value from attribute or dict key."""
    val = _get_attr(obj, attr, default)
    if val is None:
        return default
    return str(val)


# ══════════════════════════════════════════════════════════════════
#  Conversion
# ══════════════════════════════════════════════════════════════════


def convert_message_event_to_chatbot_input(event: Any) -> dict:
    """
    Convert a Hermes MessageEvent (object or dict) to the format
    expected by handle_wechat_chatbot_message().

    Compatible with both:
      - MessageEvent object with .text, .source, .media_urls, etc.
      - Plain dict with 'text', 'source', 'media_urls', etc.
      - Minimal dict with only 'text' (graceful fallback)
    """
    # ── Extract user_id ────────────────────────────────────────
    sender_id = _get_str(event, "sender_id")
    user_id = _get_str(event, "user_id")
    source = _get_attr(event, "source")
    source_user_id = _get_str(source, "user_id")

    resolved_user_id = sender_id or user_id or source_user_id or "unknown_user"

    # ── Extract chat_id ────────────────────────────────────────
    chat_id = _get_str(event, "chat_id")
    source_chat_id = _get_str(source, "chat_id")
    source_room_id = _get_str(source, "room_id")

    resolved_chat_id = chat_id or source_chat_id or source_room_id or resolved_user_id

    # ── Extract text content ───────────────────────────────────
    text = _get_str(event, "text")

    # ── Determine message_type and attachments ─────────────────
    message_type = "text"
    attachments = []

    # Support both media_paths and media_urls — keep them separate
    raw_media_paths = _get_attr(event, "media_paths")
    media_paths = raw_media_paths if isinstance(raw_media_paths, list) else []

    raw_media_urls = _get_attr(event, "media_urls")
    media_urls = raw_media_urls if isinstance(raw_media_urls, list) else []

    if media_paths:
        message_type = "image"
        for path in media_paths:
            if path and isinstance(path, str):
                attachments.append({
                    "file_type": "image",
                    "file_path": path,
                })

    # ── Determine bot_name ─────────────────────────────────────
    # Move bot_name resolution BEFORE download so entry is available
    bot_name = _get_str(event, "bot_name")
    if not bot_name:
        metadata = _get_attr(event, "metadata")
        if isinstance(metadata, dict):
            bot_name = _get_str(metadata, "bot_name", "报销助手")
        else:
            bot_name = "报销助手"

    # Map bot_name to frontend_entry shorthand
    bot_to_entry = {
        "报销助手": "expense",
        "Hermes助手": "general",
    }
    entry = bot_to_entry.get(bot_name, "general")

    if media_urls and not attachments:
        message_type = "image"
        downloaded_count = 0
        download_failed_count = 0

        for url in media_urls:
            if url and isinstance(url, str):
                # Download the media URL to a local file
                dl_result = download_wechat_media_url(
                    url=url,
                    user_id=resolved_user_id,
                    conversation_id=f"{entry}:{resolved_chat_id}",
                    media_type="image",
                )

                if dl_result.get("success"):
                    downloaded_count += 1
                    attachments.append({
                        "file_type": "image",
                        "file_path": dl_result["file_path"],
                        "url": url,
                    })
                else:
                    download_failed_count += 1
                    attachments.append({
                        "file_type": "image",
                        "url": url,
                        "file_path": "",
                        "download_error": dl_result.get("error", "Download failed"),
                    })

        # Add debug info to the raw message
        raw_debug = {
            "media_url_count": len(media_urls),
            "downloaded_count": downloaded_count,
            "download_failed_count": download_failed_count,
        }
        # We'll attach this as metadata on the input message
        # so downstream code can inspect it

    # ── Build conversation_id ─────────────────────────────────
    # (bot_name and entry already resolved above)
    conversation_id = f"wechat:{entry}:{resolved_chat_id}"

    # ── Build input message ────────────────────────────────────
    input_msg = {
        "source": "wechat_chatbot",
        "bot_name": bot_name,
        "user_id": resolved_user_id,
        "message_type": message_type,
        "content": text,
        "attachments": attachments,
        "conversation_id": conversation_id,
    }

    # Attach download debug info if available
    if media_urls and not raw_media_paths:
        try:
            input_msg["_media_download_info"] = raw_debug
        except NameError:
            pass  # No download was attempted (shouldn't happen)

    return input_msg


# ══════════════════════════════════════════════════════════════════
#  Sync handler
# ══════════════════════════════════════════════════════════════════


def handle_weixin_event_sync(event: Any) -> dict:
    """
    Process a Weixin MessageEvent-style object synchronously.

    Returns
    -------
    dict with keys: success, reply_text, chat_id, gateway_response
    """
    # Convert
    input_msg = convert_message_event_to_chatbot_input(event)

    # Resolve chat_id for return
    chat_id = input_msg.get("conversation_id", "")

    # Dispatch
    result = handle_wechat_chatbot_message(input_msg)

    return {
        "success": result.get("success", False),
        "reply_text": result.get("reply_text", ""),
        "chat_id": chat_id,
        "gateway_response": result.get("gateway_response", {}),
    }


# ══════════════════════════════════════════════════════════════════
#  Async wrapper
# ══════════════════════════════════════════════════════════════════


async def handle_weixin_event_async(event: Any) -> dict:
    """
    Process a Weixin MessageEvent-style object asynchronously.

    The actual work runs in a thread pool via asyncio.to_thread
    since handle_wechat_chatbot_message() is synchronous.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, handle_weixin_event_sync, event,
    )


# ══════════════════════════════════════════════════════════════════
#  Reply text extraction
# ══════════════════════════════════════════════════════════════════


def extract_reply_text(result: dict) -> str:
    """
    Extract a human-readable reply string from a bridge result.

    Parameters
    ----------
    result : dict
        Output from handle_weixin_event_sync() or handle_weixin_event_async().

    Returns
    -------
    str — reply text, or a fallback message on error.
    """
    if result.get("success"):
        return result.get("reply_text", "")
    return "处理消息时出现错误，请稍后再试。"
