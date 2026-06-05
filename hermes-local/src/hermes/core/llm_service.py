"""
llm_client.py

Unified LLM calling interface for ~/hermes-local modules.

Current mode: REAL (calls DeepSeek via OpenAI-compatible API).
To switch to mock: set LLM_MODE = "mock" below.

Modes:
  - MOCK : returns predefined responses (for testing / offline dev)
  - REAL : calls DeepSeek (OpenAI-compatible) API via urllib (stdlib)
"""

import json
import os
import urllib.request
import urllib.error
from typing import Any

# ── Auto-load Hermes .env ─────────────────────────────────────
_env_paths = [
    os.path.expanduser("~/.hermes/.env"),
    os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
]
for _p in _env_paths:
    _abs = os.path.abspath(_p)
    if os.path.isfile(_abs):
        with open(_abs) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())

# ── Mode switch ────────────────────────────────────────────────
LLM_MODE = "real"  # Change to "mock" for offline testing

# ── DeepSeek config (OpenAI-compatible) ────────────────────────
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")


def call_llm(system_prompt: str, user_payload: dict) -> dict:
    """
    Call an LLM and return parsed JSON result.

    Parameters
    ----------
    system_prompt : str
        System-level instruction (e.g. the reimbursement prompt).
    user_payload : dict
        User message content. Must be JSON-serialisable.

    Returns
    -------
    dict
        On success: the parsed JSON from the model.
        On failure: {"error": ..., "raw_response": ..., "fallback_message": ...}
    """
    if LLM_MODE == "real":
        return _call_real(system_prompt, user_payload)
    else:
        return _call_mock(system_prompt, user_payload)


# ══════════════════════════════════════════════════════════════
#  REAL MODE — DeepSeek (OpenAI-compatible API)
# ══════════════════════════════════════════════════════════════

def _log_token_usage(usage: dict, system_prompt: str, user_payload: dict) -> None:
    """Log token usage from a DeepSeek API call to gateway.log."""
    try:
        from hermes.runtime.gateway_logger import log_gateway_event
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        log_gateway_event("llm_token_usage", {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "model": DEEPSEEK_MODEL,
            "system_prompt_length": len(system_prompt),
        })
    except Exception:
        pass  # Logging failure must never crash LLM calls

def _call_real(system_prompt: str, user_payload: dict) -> dict:
    """Call DeepSeek chat completion via OpenAI-compatible REST API."""

    if not DEEPSEEK_API_KEY:
        return {
            "error": "no_api_key",
            "raw_response": "",
            "fallback_message": (
                "DEEPSEEK_API_KEY 未设置。请检查 ~/.hermes/.env 或环境变量。"
            ),
        }

    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 2000,
    }).encode("utf-8")

    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        return {
            "error": "api_error",
            "raw_response": str(exc),
            "fallback_message": f"LLM API 调用失败: {exc}",
        }

    # ── Log token usage ────────────────────────────────────────
    usage = body.get("usage", {})
    if usage:
        _log_token_usage(usage, system_prompt, user_payload)

    # Extract assistant content
    try:
        raw_text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {
            "error": "unexpected_response_format",
            "raw_response": json.dumps(body, ensure_ascii=False),
            "fallback_message": "LLM 返回了意外格式的响应。",
        }

    # Parse the content as JSON
    return _parse_json(raw_text)


# ══════════════════════════════════════════════════════════════
#  MOCK MODE — rule-based fallback for testing
# ══════════════════════════════════════════════════════════════

# Predefined mock responses keyed by scenario fingerprint
_MOCK_RESPONSES = {}

# Will be populated by register_mock()
def register_mock(fingerprint_fn, response_fn):
    """Register a mock response function for a matching scenario."""
    _MOCK_RESPONSES[id(fingerprint_fn)] = (fingerprint_fn, response_fn)


def _call_mock(system_prompt: str, user_payload: dict) -> dict:
    """Mock LLM — rule-based responses for test scenarios."""

    content = (
        user_payload.get("message", {})
        .get("content", "")
        if isinstance(user_payload.get("message"), dict)
        else str(user_payload)
    ).strip().lower()

    routing = user_payload.get("routing_context", {})

    # ── Scenario: full expense details ─────────────────────────
    if "haoyu" in content and "230000" in content and "ikea" in content and "hcf" in content:
        return {
            "module": "reimbursement",
            "intent_type": "new_reimbursement",
            "conversation_state": "awaiting_confirmation",
            "document_type": "text",
            "need_ocr": False,
            "extracted_fields": {
                "applicant": "Haoyu",
                "project": "IKEA HCF",
                "expense_category": "Transportation",
                "amount": 230000,
                "currency": "VND",
                "payment_date": "2026-05-11",
                "payment_method": "cash",
                "payee": "",
                "invoice_status": "No Invoice",
                "receipt_status": "Receipt Uploaded",
                "remark": "",
            },
            "missing_fields": [],
            "clarification_questions": [],
            "risk_flag": "Low",
            "status": "Draft",
            "next_action": "ask_user_confirmation",
            "tool_to_call": None,
            "user_message": (
                "已识别报销信息如下，请确认：\n"
                "报销人：Haoyu\n项目：IKEA HCF\n"
                "费用类型：Transportation\n金额：230,000 VND\n"
                "付款日期：2026-05-11\n付款方式：cash\n"
                "发票状态：No Invoice\n凭证状态：Receipt Uploaded\n"
                "请确认是否正确？"
            ),
        }

    # ── Scenario: incomplete expense (no dates, no invoice status) ──
    if "keda" in content or ("打车" in content and "230000" in content and "haoyu" in content):
        return {
            "module": "reimbursement",
            "intent_type": "new_reimbursement",
            "conversation_state": "collecting_fields",
            "document_type": "text",
            "need_ocr": False,
            "extracted_fields": {
                "applicant": "Haoyu",
                "project": "",
                "expense_category": "Transportation",
                "amount": 230000,
                "currency": "VND",
                "payment_date": "",
                "payment_method": "",
                "payee": "",
                "invoice_status": "",
                "receipt_status": "",
                "remark": "",
            },
            "missing_fields": [
                "project", "payment_date",
                "invoice_status", "receipt_status",
            ],
            "clarification_questions": [
                "请问这笔费用属于哪个项目？",
                "付款日期是哪天？",
                "有发票吗？",
                "有付款凭证吗？",
            ],
            "risk_flag": "Low",
            "status": "Draft",
            "next_action": "ask_missing_fields",
            "tool_to_call": None,
            "user_message": (
                "我已识别部分信息：\n"
                "报销人：Haoyu\n费用类型：Transportation\n金额：230,000 VND\n\n"
                "还需要补充以下信息：\n"
                "1. 项目名称\n2. 付款日期\n3. 发票状态\n4. 凭证状态"
            ),
        }

    # ── Scenario: over 5M VND ──────────────────────────────────
    if "6200000" in content or "620万" in content:
        return {
            "module": "reimbursement",
            "intent_type": "new_reimbursement",
            "conversation_state": "awaiting_confirmation",
            "document_type": "text",
            "need_ocr": False,
            "extracted_fields": {
                "applicant": "Haoyu",
                "project": "IKEA HCF",
                "expense_category": "Logistics",
                "amount": 6200000,
                "currency": "VND",
                "payment_date": "2026-05-11",
                "payment_method": "bank_transfer",
                "payee": "",
                "invoice_status": "Invoice Pending",
                "receipt_status": "",
                "remark": "",
            },
            "missing_fields": [],
            "clarification_questions": [
                "Số tiền vượt quá 5.000.000 VND. Vui lòng xác nhận có cần tách thành nhiều hóa đơn không? / Amount exceeds 5,000,000 VND. Please confirm whether this will be split into multiple invoices."
            ],
            "risk_flag": "Medium",
            "status": "Draft",
            "next_action": "ask_user_confirmation",
            "tool_to_call": None,
            "user_message": (
                "已识别报销信息：\n"
                "报销人：Haoyu\n项目：IKEA HCF\n"
                "费用类型：Logistics\n金额：6,200,000 VND\n"
                "付款日期：2026-05-11\n付款方式：bank_transfer\n"
                "发票状态：Invoice Pending\n\n"
                "⚠️ 金额超过 5,000,000 VND，请确认是否需要拆分成多张发票？"
            ),
        }

    # ── Scenario: unclear / non-reimbursement text ─────────────
    return {
        "module": "reimbursement",
        "intent_type": "other",
        "conversation_state": "collecting_fields",
        "document_type": "text",
        "need_ocr": False,
        "extracted_fields": {
            "applicant": "",
            "project": "",
            "expense_category": "",
            "amount": None,
            "currency": "",
            "payment_date": "",
            "payment_method": "",
            "payee": "",
            "invoice_status": "",
            "receipt_status": "",
            "remark": "",
        },
        "missing_fields": [
            "applicant", "project", "expense_category",
            "amount", "currency", "payment_date",
            "invoice_status", "receipt_status",
        ],
        "clarification_questions": [
            "请提供报销人姓名。",
            "请提供项目名称。",
            "请提供费用类型。",
            "请提供金额和币种。",
        ],
        "risk_flag": "Low",
        "status": "Draft",
        "next_action": "ask_missing_fields",
        "tool_to_call": None,
        "user_message": (
            "我没有识别出有效的报销信息。"
            "请提供报销人、项目、费用类型、金额、币种、付款日期等信息。"
        ),
    }


# ══════════════════════════════════════════════════════════════
#  JSON Parsing
# ══════════════════════════════════════════════════════════════

def _parse_json(raw_text: str) -> dict:
    """Try to parse raw text as JSON. Returns parsed dict or error dict."""
    # Try direct parse first
    text = raw_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        for fence in ["```json\n", "```\n", "```json", "```"]:
            if text.startswith(fence):
                text = text[len(fence):]
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object within the text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        return {
            "error": "invalid_json",
            "raw_response": raw_text,
            "fallback_message": "模型返回格式不是合法 JSON。",
        }
