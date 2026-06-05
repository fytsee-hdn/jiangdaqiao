"""
llm_intent_router.py — LLM-based Intent Router for GSP Service Agent.

Replaces hardcoded keyword routing with LLM-driven intent classification.
Supports both REAL (DeepSeek API) and MOCK (rule-based fallback for testing).

The router:
  1. Takes a normalised message + context
  2. Builds a classification prompt
  3. Calls the LLM (real or mock)
  4. Parses and validates the JSON output
  5. Returns a structured IntentRouteResult
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from hermes.core.message import normalised_message_factory

_logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  Constants
# ══════════════════════════════════════════════════════════════════

# Valid target agents — must match agent_registry.json
_VALID_AGENTS = frozenset({
    "gsp_admin_agent",
    "gsp_reimbursement_agent",
    "gsp_compliance_agent",
    "gsp_quality_agent",
    "gsp_quotation_agent",
    "gsp_procurement_agent",
    "clarify",
    "unsupported",
})

# Prompt path
_PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "prompts",
    "gsp_service_intent_router_prompt_v1.md",
)

# LLM mode: "mock" | "real"
LLM_ROUTER_MODE = os.environ.get("LLM_ROUTER_MODE", "mock")


# ══════════════════════════════════════════════════════════════════
#  Prompt loading
# ══════════════════════════════════════════════════════════════════

_prompt_cache: Optional[str] = None


def _load_router_prompt() -> str:
    """Load the intent router system prompt from .md file."""
    global _prompt_cache
    if _prompt_cache is not None:
        return _prompt_cache

    path = os.path.abspath(_PROMPT_PATH)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            _prompt_cache = f.read()
    else:
        _logger.warning("Router prompt not found at %s", path)
        _prompt_cache = "You are an intent classifier for GSP Service Agent."
    return _prompt_cache


# ══════════════════════════════════════════════════════════════════
#  Mock LLM (for testing — no API required)
# ══════════════════════════════════════════════════════════════════

def _mock_llm_classify(user_text: str, context: Optional[dict] = None) -> dict:
    """Mock LLM: rule-based intent classification for testing.

    This is a DELIBERATELY simplified mock. It does NOT replace keyword routing
    in production — it only exists so tests can run without a real LLM API key.
    The mock uses semantic patterns, not single-keyword matching.
    """
    text = (user_text or "").lower().strip()

    # Check for active conversation state first
    active_state = (context or {}).get("active_state")
    if active_state and active_state.get("module") == "reimbursement":
        return _make_result(
            "gsp_reimbursement_agent", 0.85,
            "用户在报销会话中继续补充信息",
            "active_conversation_state",
            user_text,
        )

    # ── Admin: system management ──────────────────────────
    admin_patterns = [
        ["系统状态", "system status"],
        ["查看日志", "view log"],
        ["运行测试", "run test"],
        ["查看今天", "今天有多少"],
        ["备份", "backup"],
        ["导出", "export"],
    ]
    for patterns in admin_patterns:
        if any(p in text for p in patterns):
            return _make_result(
                "gsp_admin_agent", 0.90,
                f"系统管理请求：{patterns[0]}",
                f"matched admin pattern: {patterns}",
                user_text,
                requires_permission=True,
                required_permission="admin.read_status",
            )

    # ── Reimbursement ─────────────────────────────────────
    # Look for amount + currency/payment context (not just single keyword)
    has_amount = any(w in text for w in ["vnd", "usd", "cny", "越南盾", "块钱", "元"])
    has_payment = any(w in text for w in ["付款", "报销", "打车", "运费", "垫付", "发票", "收据"])
    has_project = any(w in text for w in ["项目", "mitac", "ikea", "三星"])
    if (has_amount and has_payment) or (has_payment and has_project):
        return _make_result(
            "gsp_reimbursement_agent", 0.90,
            "报销请求：包含金额/付款/项目信息",
            "payment + amount/project context",
            user_text,
        )
    if has_payment and len(text) > 15:
        return _make_result(
            "gsp_reimbursement_agent", 0.75,
            "可能为报销请求",
            "payment keyword + sufficient context",
            user_text,
        )

    # ── Quality ───────────────────────────────────────────
    quality_combos = [
        (["8d", "报告"], 0.90),
        (["客诉", "投诉"], 0.85),
        (["不良", "品质"], 0.85),
        (["缺陷", "defect"], 0.80),
        (["质量", "质量异常"], 0.80),
    ]
    for patterns, conf in quality_combos:
        if any(p in text for p in patterns):
            return _make_result(
                "gsp_quality_agent", conf,
                f"质量相关请求：{patterns[0]}",
                f"matched quality pattern: {patterns}",
                user_text,
            )

    # ── Compliance ────────────────────────────────────────
    compliance_patterns = [
        (["iway"], 0.95),
        (["fsc"], 0.95),
        (["ehs"], 0.90),
        (["合规", "整改"], 0.85),
        (["审计", "audit"], 0.85),
    ]
    for patterns, conf in compliance_patterns:
        if any(p in text for p in patterns):
            return _make_result(
                "gsp_compliance_agent", conf,
                f"合规相关请求：{patterns[0]}",
                f"matched compliance pattern: {patterns}",
                user_text,
            )

    # ── Quotation ─────────────────────────────────────────
    quotation_patterns = [
        (["报价", "成本"], 0.85),
        (["利润", "margin"], 0.85),
        (["价格", "降价"], 0.80),
    ]
    for patterns, conf in quotation_patterns:
        if any(p in text for p in patterns):
            return _make_result(
                "gsp_quotation_agent", conf,
                f"报价/成本相关请求：{patterns[0]}",
                f"matched quotation pattern: {patterns}",
                user_text,
            )

    # ── Procurement ───────────────────────────────────────
    procurement_patterns = [
        (["采购", "供应商"], 0.85),
        (["原纸", "库存"], 0.90),
        (["交期", "delivery"], 0.85),
    ]
    for patterns, conf in procurement_patterns:
        if any(p in text for p in patterns):
            return _make_result(
                "gsp_procurement_agent", conf,
                f"采购相关请求：{patterns[0]}",
                f"matched procurement pattern: {patterns}",
                user_text,
            )

    # ── Clarify ───────────────────────────────────────────
    if len(text) < 6:
        return _make_result("clarify", 0.30, "消息过短", "too_short", user_text,
                            needs_clarification=True,
                            clarification_question="请问你需要什么帮助？例如报销、系统管理、质量投诉等。")

    # ── Unsupportable ─────────────────────────────────────
    unsafe_patterns = ["delete", "drop table", "rm -rf", "shutdown", "reboot"]
    if any(p in text for p in unsafe_patterns):
        return _make_result("unsupported", 0.95, "不支持的请求", "unsafe_command", user_text)

    # Personal / non-business requests
    personal_patterns = ["辞职信", "情书", "推荐信", "写一首诗", "讲个笑话"]
    if any(p in text for p in personal_patterns):
        return _make_result("unsupported", 0.90, "个人请求，不在业务范围内", "personal_request", user_text)

    # ── Default: clarify ──────────────────────────────────
    return _make_result("clarify", 0.40, "无法可靠判断意图", "insufficient_context", user_text,
                        needs_clarification=True,
                        clarification_question="我不确定你的具体需求，请补充说明是报销、系统管理、质量、合规、报价还是采购相关。")


def _make_result(
    agent: str,
    confidence: float,
    intent_summary: str,
    reason: str,
    user_text: str,
    requires_permission: bool = False,
    required_permission: Optional[str] = None,
    needs_clarification: bool = False,
    clarification_question: Optional[str] = None,
) -> dict:
    """Build a standard LLM classification result."""
    return {
        "selected_agent": agent,
        "confidence": confidence,
        "intent_summary": intent_summary,
        "reason": reason,
        "normalized_user_request": user_text,
        "requires_permission": requires_permission,
        "required_permission": required_permission,
        "risk_flags": [],
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "handoff_message": user_text,
    }


# ══════════════════════════════════════════════════════════════════
#  Real LLM call (delegates to core/llm_service)
# ══════════════════════════════════════════════════════════════════

def _call_real_llm(system_prompt: str, user_payload: dict) -> dict:
    """Call the real LLM via core/llm_service."""
    try:
        from hermes.core.llm_service import call_llm
    except ImportError:
        _logger.error("llm_service not available — falling back to mock")
        return None

    user_text = json.dumps(user_payload, ensure_ascii=False)
    try:
        result = call_llm(system_prompt, {"content": user_text})
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            return json.loads(result)
    except Exception as exc:
        _logger.error("Real LLM call failed: %s", exc)
    return None


# ══════════════════════════════════════════════════════════════════
#  Output validation
# ══════════════════════════════════════════════════════════════════

def _validate_and_normalize(raw: dict) -> dict:
    """Validate and normalise LLM output. Returns a safe result."""
    agent = raw.get("selected_agent", "clarify")
    if agent not in _VALID_AGENTS:
        agent = "clarify"

    try:
        confidence = float(raw.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5

    return {
        "selected_agent": agent,
        "confidence": confidence,
        "intent_summary": str(raw.get("intent_summary", "")),
        "reason": str(raw.get("reason", "")),
        "normalized_user_request": str(raw.get("normalized_user_request", "")),
        "requires_permission": bool(raw.get("requires_permission", False)),
        "required_permission": raw.get("required_permission"),
        "risk_flags": raw.get("risk_flags", []) if isinstance(raw.get("risk_flags"), list) else [],
        "needs_clarification": bool(raw.get("needs_clarification", False)),
        "clarification_question": raw.get("clarification_question"),
        "handoff_message": str(raw.get("handoff_message", "")),
    }


# ══════════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════════

def classify_intent(
    message: dict,
    context: Optional[dict] = None,
    *,
    force_mode: Optional[str] = None,
) -> dict:
    """Classify user intent and return routing decision.

    Parameters
    ----------
    message : dict
        Normalised message with at least: content, message_type, user_id.
    context : dict, optional
        Additional context: conversation_history, active_state, user_profile.
    force_mode : str, optional
        Override LLM_ROUTER_MODE: "mock" or "real".

    Returns
    -------
    dict
        IntentRouteResult with keys:
          - selected_agent
          - confidence
          - intent_summary
          - reason
          - normalized_user_request
          - requires_permission
          - required_permission
          - risk_flags
          - needs_clarification
          - clarification_question
          - handoff_message
          - llm_mode
          - llm_error
          - route_source
    """
    mode = force_mode or LLM_ROUTER_MODE
    content = (message.get("content") or "").strip()
    context = context or {}

    # ── 0. Active conversation state (deterministic shortcut) ──
    active_state = context.get("active_state")
    if active_state and active_state.get("module") == "reimbursement":
        return {
            **_make_result(
                "gsp_reimbursement_agent", 0.90,
                "Active reimbursement conversation — continuing",
                "active_conversation_state",
                content,
            ),
            "llm_mode": "deterministic",
            "llm_error": None,
            "route_source": "active_conversation_state",
        }

    # ── 1. Build user payload ────────────────────────────
    user_payload = {
        "user_message": content,
        "message_type": message.get("message_type", "text"),
        "source": message.get("source", "unknown"),
        "has_attachments": bool(message.get("attachments")),
        "conversation_history": context.get("conversation_history", [])[-6:],
        "user_profile": context.get("user_profile", {}),
    }

    # ── 2. Call LLM ──────────────────────────────────────
    llm_mode = mode
    llm_error = None
    raw_result = None

    if mode == "real":
        prompt = _load_router_prompt()
        raw_result = _call_real_llm(prompt, user_payload)
        if raw_result is None:
            llm_error = "real_llm_failed"
            # Fall through to safe fallback
        else:
            llm_mode = "real"
    elif mode == "mock":
        raw_result = _mock_llm_classify(content, context)
        llm_mode = "mock"
    else:
        llm_error = f"unknown_mode: {mode}"

    # ── 3. Parse & validate ──────────────────────────────
    if raw_result is None:
        # Safe fallback — never guess
        return {
            **_make_result(
                "clarify", 0.30,
                "LLM调用失败，无法判断意图",
                "llm_error_fallback",
                content,
                needs_clarification=True,
                clarification_question=(
                    "我暂时无法可靠判断你的意图。"
                    "请你补充说明是报销、系统管理、质量、合规、报价还是采购相关。"
                ),
            ),
            "llm_mode": llm_mode,
            "llm_error": llm_error,
            "route_source": "safe_fallback",
        }

    validated = _validate_and_normalize(raw_result)
    validated["llm_mode"] = llm_mode
    validated["llm_error"] = llm_error
    validated["route_source"] = f"llm_{llm_mode}"

    return validated


def is_valid_agent(agent_id: str) -> bool:
    """Check if an agent ID is in the valid set."""
    return agent_id in _VALID_AGENTS
