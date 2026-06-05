"""
gateway.py

Local HTTP Gateway for Hermes local system.

Provides a pure function handle_gateway_message(payload) that:

  1. Resolves frontend_entry -> source_window mapping
  2. Converts payload to Hermes internal raw_message
  3. Calls dispatcher's handle_incoming_message()
  4. Returns a unified response dict

If FastAPI is installed, also exposes an optional FastAPI app with:
  - GET  /health  (no auth required)
  - POST /api/message  (optional Bearer token auth)
  - GET  /wecom/callback  (WeCom verify, returns echostr)
  - POST /wecom/callback  (WeCom message, JSON or XML)

Authentication:
  Set env var HERMES_GATEWAY_TOKEN to enable Bearer token protection.
  If unset or empty, POST /api/message has no auth (but prints a warning).

This gateway does NOT connect to real WeCom, does NOT handle
WeCom encryption, and does NOT start any long-lived server.
"""

import json
import os
import sys
from typing import Any, Optional

# Ensure we can import from the project root
_src = os.path.dirname(os.path.abspath(__file__))
_src_parent = os.path.dirname(_src)  # hermes/
if _src_parent not in sys.path:
    sys.path.insert(0, _src_parent)

from hermes.runtime.dispatcher import handle_incoming_message
from hermes.runtime.gateway_logger import (
    generate_request_id,
    log_gateway_event,
)


# ══════════════════════════════════════════════════════════════════
#  Frontend entry -> source_window mapping
# ══════════════════════════════════════════════════════════════════

_FRONTEND_MAP = {
    "expense": "reimbursement_assistant",
    "reimbursement": "reimbursement_assistant",
    "general": "general_assistant",
    "default": "general_assistant",
}


def _resolve_source_window(payload: dict) -> str:
    """
    Resolve source_window from payload.

    Priority:
      1. payload['source_window'] if present and non-empty
      2. payload['frontend_entry'] -> lookup in _FRONTEND_MAP
      3. fallback -> "general_assistant"
    """
    # Priority 1: explicit source_window
    sw = payload.get("source_window")
    if sw and isinstance(sw, str) and sw.strip():
        return sw.strip()

    # Priority 2: frontend_entry
    fe = payload.get("frontend_entry")
    if fe and isinstance(fe, str) and fe.strip():
        mapped = _FRONTEND_MAP.get(fe.strip().lower())
        if mapped:
            return mapped

    # Priority 3: fallback
    return "general_assistant"


# ══════════════════════════════════════════════════════════════════
#  Token-based authentication
# ══════════════════════════════════════════════════════════════════

_GATEWAY_TOKEN_ENV = "HERMES_GATEWAY_TOKEN"
_GATEWAY_TOKEN = os.environ.get(_GATEWAY_TOKEN_ENV, "").strip()
_AUTH_ENABLED = bool(_GATEWAY_TOKEN)


def _load_gateway_token() -> str:
    """Return the configured gateway token or empty string."""
    return _GATEWAY_TOKEN


def is_auth_enabled() -> bool:
    """
    Return True if HERMES_GATEWAY_TOKEN is set and non-empty.

    When True, FastAPI POST /api/message requires
        Authorization: Bearer <token>
    """
    return _AUTH_ENABLED


def _verify_bearer_token(authorization: Optional[str]) -> bool:
    """
    Verify a Bearer token against the configured gateway token.

    Parameters
    ----------
    authorization : str or None
        The raw Authorization header value (e.g. "Bearer my-token").

    Returns
    -------
    bool
        True if auth is not configured, or if the token matches.
        False if auth is configured and the token is wrong/missing.
    """
    if not _AUTH_ENABLED:
        return True  # no auth configured -> always allowed

    if not authorization:
        return False

    parts = authorization.strip().split(None, 1)
    if len(parts) != 2:
        return False

    scheme, token = parts
    if scheme.lower() != "bearer":
        return False

    return token == _GATEWAY_TOKEN


# ══════════════════════════════════════════════════════════════════
#  Main entry point
# ══════════════════════════════════════════════════════════════════


def handle_gateway_message(payload: Any) -> dict:
    """
    Accept an external payload, convert to Hermes raw_message,
    dispatch through the pipeline, and return a unified response.

    Parameters
    ----------
    payload : any
        Expected to be a dict. Non-dict payloads return success=False.

    Returns
    -------
    dict with keys: success, source_window, conversation_id, result, error
    """
    # ── Validate payload ────────────────────────────────────────
    if payload is None:
        log_gateway_event("error", {
            "request_id": generate_request_id(),
            "conversation_id": "",
            "source_window": "",
            "error": "Payload is None",
            "summary": "error=PayloadIsNone",
        })
        return {
            "success": False,
            "source_window": "",
            "conversation_id": "",
            "result": None,
            "error": "Payload is None. Expected a JSON object with "
                     "'content' and optional 'source_window'/'frontend_entry'.",
        }

    if not isinstance(payload, dict):
        log_gateway_event("error", {
            "request_id": generate_request_id(),
            "conversation_id": "",
            "source_window": "",
            "error": f"Payload must be a dict, got {type(payload).__name__}",
            "summary": f"error=InvalidPayloadType({type(payload).__name__})",
        })
        return {
            "success": False,
            "source_window": "",
            "conversation_id": "",
            "result": None,
            "error": f"Payload must be a dict, got {type(payload).__name__}.",
        }

    # ── Resolve source_window ───────────────────────────────────
    source_window = _resolve_source_window(payload)
    conversation_id = str(payload.get("conversation_id", "gateway_default"))
    request_id = generate_request_id()

    # ── Build raw_message ──────────────────────────────────────
    raw_message = dict(payload)
    raw_message["source_window"] = source_window

    # ── Remove gateway-only fields before passing to dispatcher ─
    raw_message.pop("frontend_entry", None)

    # ── Log request_received ────────────────────────────────────
    content = payload.get("content", "")
    attachments = payload.get("attachments", [])
    att_count = len(attachments) if isinstance(attachments, list) else 0
    log_gateway_event("request_received", {
        "request_id": request_id,
        "source": payload.get("source", ""),
        "source_window": source_window,
        "user_id": payload.get("user_id", ""),
        "message_type": payload.get("message_type", ""),
        "conversation_id": conversation_id,
        "frontend_entry": payload.get("frontend_entry", ""),
        "content": content,
        "attachment_count": att_count,
        "summary": f"source_window={source_window}, type={payload.get('message_type', '')}, "
                   f"attachments={att_count}",
    })

    # ── Dispatch ────────────────────────────────────────────────
    try:
        result = handle_incoming_message(raw_message)
    except Exception as exc:
        log_gateway_event("error", {
            "request_id": request_id,
            "conversation_id": conversation_id,
            "source_window": source_window,
            "error": f"{type(exc).__name__}: {exc}",
            "summary": f"error={type(exc).__name__}",
        })
        return {
            "success": False,
            "source_window": source_window,
            "conversation_id": conversation_id,
            "result": None,
            "error": f"Dispatcher error: {exc}",
        }

    # ── Log response_sent ──────────────────────────────────────
    result_type = result.get("type", "") if isinstance(result, dict) else ""
    result_module = result.get("module", "") if isinstance(result, dict) else ""
    result_next = result.get("next_action", "") if isinstance(result, dict) else ""
    result_content = result.get("content", "") if isinstance(result, dict) else ""
    log_gateway_event("response_sent", {
        "request_id": request_id,
        "source_window": source_window,
        "conversation_id": conversation_id,
        "success": True,
        "result_type": result_type,
        "result_module": result_module,
        "result_next_action": result_next,
        "content": result_content,
        "summary": f"module={result_module}, next_action={result_next}",
    })

    # ── Return unified response ─────────────────────────────────
    return {
        "success": True,
        "source_window": source_window,
        "conversation_id": conversation_id,
        "result": result,
    }


# ══════════════════════════════════════════════════════════════════
#  Optional FastAPI app (only if FastAPI is installed)
# ══════════════════════════════════════════════════════════════════

_fastapi_available = False
try:
    from fastapi import FastAPI, Request, Query
    from pydantic import BaseModel
    _fastapi_available = True
except ImportError:
    _fastapi_available = False

if _fastapi_available:

    app = FastAPI(
        title="Hermes Local Gateway",
        description="Local gateway for Hermes Agent business orchestration",
        version="0.1.0",
    )

    class MessagePayload(BaseModel):
        """Incoming message payload schema."""
        source: str = "local_api"
        source_window: Optional[str] = None
        frontend_entry: Optional[str] = None
        user_id: str = "gateway_user"
        message_type: str = "text"
        content: str = ""
        attachments: list = []
        conversation_id: str = "gateway_default"
        timestamp: Optional[str] = None

    class HealthResponse(BaseModel):
        status: str
        service: str
        auth_enabled: bool

    @app.get("/health", response_model=HealthResponse)
    async def health():
        """Health check endpoint."""
        return {
            "status": "ok",
            "service": "hermes-local-gateway",
            "auth_enabled": _AUTH_ENABLED,
        }

    @app.post("/api/message")
    async def api_message(payload: MessagePayload, request: Request):
        """Process an incoming message through the Hermes pipeline.

        Requires Authorization: Bearer <token> if auth is enabled.
        """
        # ── Optional auth check ─────────────────────────────────
        if _AUTH_ENABLED:
            auth_header = request.headers.get("Authorization", "")
            if not _verify_bearer_token(auth_header):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={
                        "success": False,
                        "error": "Unauthorized",
                    },
                )

        # ── Process message ─────────────────────────────────────
        payload_dict = payload.model_dump()
        # Remove None values so _resolve_source_window works correctly
        payload_dict = {k: v for k, v in payload_dict.items() if v is not None}
        result = handle_gateway_message(payload_dict)
        return result

    # ═════════════════════════════════════════════════════════════
    #  WeCom callback endpoints (mock — no AES, no real WeCom)
    # ═════════════════════════════════════════════════════════════

    @app.get("/wecom/callback")
    async def wecom_callback_get(
        msg_signature: Optional[str] = None,
        timestamp: Optional[str] = None,
        nonce: Optional[str] = None,
        echostr: Optional[str] = None,
    ):
        """WeCom URL verification callback (GET).

        If WeCom crypto config is available (token + encoding_aes_key + corp_id):
          1. Verify msg_signature
          2. Decrypt echostr
          3. Return plaintext echostr

        If config is incomplete, falls back to mock: return echostr as-is.
        """
        rid = generate_request_id()
        log_gateway_event("wecom_callback_verify_received", {
            "request_id": rid,
            "has_msg_signature": msg_signature is not None,
            "has_timestamp": timestamp is not None,
            "has_nonce": nonce is not None,
            "has_echostr": echostr is not None,
            "summary": f"verify: msg_sig={'yes' if msg_signature else 'no'}, "
                       f"echostr={'yes' if echostr else 'no'}",
        })

        if not echostr:
            from fastapi.responses import JSONResponse
            log_gateway_event("wecom_callback_error", {
                "request_id": rid,
                "error": "missing echostr",
                "summary": "error=missing_echostr",
            })
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "missing echostr"},
            )

        # ── Load crypto config ──────────────────────────────────
        from hermes.runtime.wecom_config import load_wecom_config
        from hermes.runtime.wecom_crypto import (
            verify_signature,
            decrypt_wecom_echostr,
            is_cryptography_available,
        )

        cfg = load_wecom_config(mask_secrets=False)
        crypto_token = cfg.get("callback", {}).get("token", "")
        crypto_aes_key = cfg.get("callback", {}).get("encoding_aes_key", "")
        crypto_corp_id = cfg.get("corp_id", "")
        crypto_has_config = bool(crypto_token and crypto_aes_key
                                 and crypto_corp_id and is_cryptography_available())

        if crypto_has_config:
            # ── Real WeCom verification ─────────────────────────
            sig_ok = verify_signature(
                crypto_token,
                msg_signature or "",
                timestamp or "",
                nonce or "",
                echostr,
            )

            if not sig_ok:
                log_gateway_event("wecom_crypto_verify_failed", {
                    "request_id": rid,
                    "summary": "verify_failed: msg_signature mismatch",
                })
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "error": "invalid msg_signature"},
                )

            try:
                plaintext = decrypt_wecom_echostr(echostr, crypto_aes_key, crypto_corp_id)
            except ValueError as exc:
                log_gateway_event("wecom_crypto_decrypt_failed", {
                    "request_id": rid,
                    "error": str(exc),
                    "summary": "decrypt_failed",
                })
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": "decryption failed"},
                )

            log_gateway_event("wecom_crypto_verify_success", {
                "request_id": rid,
                "summary": "verify_success_decrypted_echostr",
            })

            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(content=plaintext)

        # ── Mock: return echostr as-is (no crypto config) ──────
        log_gateway_event("wecom_crypto_config_incomplete", {
            "request_id": rid,
            "summary": "crypto_config_incomplete_using_mock_echostr",
        })
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=echostr)

    @app.post("/wecom/callback")
    async def wecom_callback_post(request: Request):
        """WeCom message callback (POST).

        Supports:
          - Content-Type: application/json (mock WeCom dict)
          - Content-Type: application/xml or text/xml (WeCom XML)
          - Encrypted XML (containing <Encrypt> element)

        When <Encrypt> is present and crypto config is available:
          1. Verify msg_signature (from query params)
          2. Decrypt <Encrypt> to get plaintext XML
          3. Parse plaintext XML as normal
        """
        rid = generate_request_id()
        content_type = (request.headers.get("content-type") or "").lower()

        log_gateway_event("wecom_callback_message_received", {
            "request_id": rid,
            "content_type": content_type or "unknown",
            "summary": f"wecom_post: content_type={content_type or 'unknown'}",
        })

        try:
            body_bytes = await request.body()
            body_str = body_bytes.decode("utf-8", errors="replace")

            # ── Determine how to parse the body ────────────────
            is_json = "application/json" in content_type

            wecom_dict = None
            raw_xml = None

            if is_json:
                # JSON mode: parse as WeCom message dict
                try:
                    wecom_dict = json.loads(body_str)
                except (json.JSONDecodeError, ValueError) as exc:
                    return _wecom_error(rid, f"Invalid JSON body: {exc}")
            else:
                # XML mode: check for encrypted XML first
                raw_xml = body_str
                has_encrypt = "<Encrypt>" in raw_xml or "<Encrypt " in raw_xml

                if has_encrypt:
                    # ── Encrypted XML path ─────────────────────
                    from hermes.runtime.wecom_config import load_wecom_config
                    from hermes.runtime.wecom_crypto import (
                        verify_signature,
                        decrypt_wecom_message,
                        is_cryptography_available,
                        is_crypto_configured,
                    )

                    if not is_cryptography_available():
                        return _wecom_error(
                            rid,
                            "cryptography library not installed. "
                            "Run: pip install cryptography",
                        )

                    # Load crypto config
                    cfg = load_wecom_config(mask_secrets=False)
                    crypto_token = cfg.get("callback", {}).get("token", "")
                    crypto_aes_key = cfg.get("callback", {}).get("encoding_aes_key", "")
                    crypto_corp_id = cfg.get("corp_id", "")

                    if not (crypto_token and crypto_aes_key and crypto_corp_id):
                        return _wecom_error(
                            rid,
                            "WeCom crypto config incomplete. "
                            "Set WECOM_CALLBACK_TOKEN, WECOM_ENCODING_AES_KEY, "
                            "and WECOM_CORP_ID",
                        )

                    # Parse query params for signature verification
                    query_params = dict(request.query_params)
                    q_msg_sig = query_params.get("msg_signature", "")
                    q_timestamp = query_params.get("timestamp", "")
                    q_nonce = query_params.get("nonce", "")

                    # Parse Encrypt value from XML
                    from hermes.runtime.wecom_xml import parse_wecom_xml
                    enc_dict = parse_wecom_xml(raw_xml)
                    encrypt_value = enc_dict.get("Encrypt", "")

                    if not encrypt_value:
                        return _wecom_error(
                            rid, "Encrypted XML missing <Encrypt> value"
                        )

                    # Verify signature
                    if q_msg_sig:
                        sig_ok = verify_signature(
                            crypto_token, q_msg_sig,
                            q_timestamp, q_nonce, encrypt_value,
                        )
                        if not sig_ok:
                            log_gateway_event("wecom_crypto_verify_failed", {
                                "request_id": rid,
                                "summary": "post_verify_failed_msg_signature",
                            })
                            from fastapi.responses import JSONResponse
                            return JSONResponse(
                                status_code=401,
                                content={
                                    "success": False,
                                    "error": "invalid msg_signature",
                                },
                            )

                    # Decrypt
                    try:
                        decrypted_xml = decrypt_wecom_message(
                            encrypt_value, crypto_aes_key, crypto_corp_id,
                        )
                    except ValueError as exc:
                        log_gateway_event("wecom_crypto_decrypt_failed", {
                            "request_id": rid,
                            "error": str(exc),
                            "summary": "post_decrypt_failed",
                        })
                        return _wecom_error(rid, f"Decryption failed: {exc}")

                    log_gateway_event("wecom_crypto_decrypt_success", {
                        "request_id": rid,
                        "summary": "post_decrypt_success_processing",
                    })

                    # Parse the decrypted XML
                    from hermes.runtime.wecom_xml import is_valid_wecom_xml
                    wecom_dict = parse_wecom_xml(decrypted_xml)

                else:
                    # ── Plain XML path (unchanged) ──────────────
                    from hermes.runtime.wecom_xml import parse_wecom_xml, is_valid_wecom_xml
                    try:
                        wecom_dict = parse_wecom_xml(raw_xml)
                    except ValueError as exc:
                        return _wecom_error(rid, f"XML parse error: {exc}")

                    if not is_valid_wecom_xml(wecom_dict):
                        return _wecom_error(
                            rid,
                            f"Parsed XML missing required WeCom fields. "
                            f"Got keys: {list(wecom_dict.keys())}",
                        )

            if wecom_dict is None:
                return _wecom_error(rid, "Unable to parse request body")

            # ── Process through wecom_adapter ──────────────────
            from hermes.runtime.wecom_adapter import handle_wecom_mock_message
            gateway_response = handle_wecom_mock_message(wecom_dict)

            log_gateway_event("wecom_callback_message_processed", {
                "request_id": rid,
                "success": gateway_response.get("success", False),
                "source_window": gateway_response.get("source_window", ""),
                "summary": f"msg_type={wecom_dict.get('MsgType', '?')}, "
                           f"agent={wecom_dict.get('AgentID', '?')}",
            })

            # ── Auto-reply logic ──────────────────────────────
            reply_result = None
            from hermes.runtime.wecom_client import (
                is_auto_reply_enabled,
                send_wecom_reply_for_gateway_response,
            )

            if is_auto_reply_enabled():
                reply_result = send_wecom_reply_for_gateway_response(
                    wecom_dict, gateway_response,
                )
            else:
                reply_result = {"skipped": True}
                log_gateway_event("wecom_auto_reply_skipped", {
                    "request_id": rid,
                    "summary": "auto_reply_disabled",
                })

            return {
                "success": True,
                "source": "wecom_callback",
                "gateway_response": gateway_response,
                "reply_result": reply_result,
            }

        except Exception as exc:
            log_gateway_event("wecom_callback_error", {
                "request_id": rid,
                "error": f"{type(exc).__name__}: {exc}",
                "summary": f"error={type(exc).__name__}",
            })
            return {"success": False, "error": f"Callback error: {exc}"}


def _wecom_error(request_id: str, message: str) -> dict:
    """Build a uniform WeCom callback error response and log it."""
    log_gateway_event("wecom_callback_error", {
        "request_id": request_id,
        "error": message,
        "summary": "error=wecom_callback",
    })
    return {"success": False, "error": message}


# ══════════════════════════════════════════════════════════════════
#  Startup warning
# ══════════════════════════════════════════════════════════════════

if _fastapi_available and not _AUTH_ENABLED:
    import warnings
    warnings.warn(
        "Gateway token is not configured. "
        "HTTP endpoint is not protected.",
        stacklevel=2,
    )


def is_fastapi_available() -> bool:
    """Return True if FastAPI is installed."""
    return _fastapi_available
