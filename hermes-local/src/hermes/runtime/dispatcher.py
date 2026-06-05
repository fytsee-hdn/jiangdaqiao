"""
dispatcher.py

Router / Dispatcher layer — the third and final stage of the
incoming-message pipeline.

Full pipeline:
    raw_message
      → normalize_message()        [message_normalizer]
      → source_prefilter()         [source_prefilter]
      → dispatcher                 [this module]
      → final routing decision

The dispatcher interprets the prefilter's *next_action* and invokes
the appropriate module handler (or falls back to the global agent).
"""

import sys
import os

# Allow importing sibling modules when run directly
_src = os.path.dirname(os.path.abspath(__file__))
if _src not in sys.path:
    sys.path.insert(0, os.path.dirname(_src))  # hermes/

from hermes.runtime.message_normalizer import normalize_message
from hermes.runtime.source_prefilter import source_prefilter
from hermes.modules.reimbursement.handler import (
    handle_reimbursement_message,
)
from hermes.modules.reimbursement.state_store import get_state
from hermes.modules.reimbursement.handler import (
    _CONFIRM_WORDS as _CONFIRMATION_WORDS,
    _CANCEL_WORDS,
)

# ── Reimbursement keywords (shared with call_global_agent0) ────
_REIMBURSEMENT_KEYWORDS = [
    "报销", "发票", "收据", "付款", "费用",
    "invoice", "receipt", "payment", "expense",
]

_QUALITY_KEYWORDS = [
    "8D", "品质", "质量", "客诉", "complaint", "defect",
]

_COMPLIANCE_KEYWORDS = [
    "IWAY", "FSC", "EHS", "审计", "合规", "audit", "compliance",
]


def handle_incoming_message(raw_message: dict) -> dict:
    """
    Full pipeline entry point.

    Accepts a raw message dict → normalizes → prefilters → dispatches.

    Multi-turn support: if a conversation already has active state
    from a prior reimbursement exchange, bypass the prefilter and
    route directly to the reimbursement module so that follow-up
    messages ("项目是 IKEA HCF") don't get misrouted.
    """
    # Stage 1: normalize
    normalized = normalize_message(raw_message)

    # ── State-aware shortcut (multi-turn conversations) ─────────
    conv_id = normalized.get("conversation_id", "default")
    existing_state = get_state(conv_id)
    if existing_state and existing_state.get("module") == "reimbursement":
        return call_reimbursement_module(normalized, {})

    # Stage 2: prefilter
    prefilter_result = source_prefilter(normalized)

    next_action = prefilter_result.get("next_action", "")

    # ── Dispatch based on prefilter result ─────────────────────
    if next_action == "route_to_reimbursement_module":
        return call_reimbursement_module(
            normalized,
            prefilter_result,
        )

    if next_action == "send_to_global_agent0":
        return _dispatch_global_agent0(normalized, prefilter_result)

    # Fallback — should never happen with current prefilter
    return {
        "type": "error",
        "next_action": "unknown_next_action",
        "content": f"Unrecognised next_action: '{next_action}'",
        "prefilter_result": prefilter_result,
    }


# ══════════════════════════════════════════════════════════════
#  call_reimbursement_module (mock)
# ══════════════════════════════════════════════════════════════

def call_reimbursement_module(
    message: dict,
    routing_context: dict,
) -> dict:
    """
    Delegate to the real reimbursement module handler.

    For text messages → LLM-based extraction.
    For file messages (image/pdf/file) → mock OCR signal.
    """
    return handle_reimbursement_message(message, routing_context)


# ══════════════════════════════════════════════════════════════
#  call_global_agent0 (mock)
# ══════════════════════════════════════════════════════════════

def _dispatch_global_agent0(
    message: dict,
    prefilter_result: dict,
) -> dict:
    """
    Mock global agent — simple keyword-based dispatch.

    (No LLM — placeholder logic only.)
    """
    content = (message.get("content") or "").strip().lower()
    source_window = prefilter_result.get("source_window", "")

    # Rule 0: confirmation words for an active reimbursement conversation
    if source_window == "reimbursement_assistant" and content.strip() in {
        w.lower() for w in _CONFIRMATION_WORDS
    }:
        return call_reimbursement_module(message, prefilter_result)

    # Rule 0b: cancel words → route to reimbursement handler
    if content.strip() in {w.lower() for w in _CANCEL_WORDS}:
        return call_reimbursement_module(message, prefilter_result)

    # Rule 1: reimbursement keywords → re-route to reimbursement module
    if _has_any(content, _REIMBURSEMENT_KEYWORDS):
        # Forward to the reimbursement module
        return call_reimbursement_module(message, prefilter_result)

    # Rule 2: quality / complaint keywords → module not enabled
    if _has_any(content, _QUALITY_KEYWORDS):
        return {
            "type": "module_not_enabled",
            "module": "quality",
            "next_action": "ask_clarification",
            "content": (
                "检测到品质相关关键词（8D / 客诉 / 质量），"
                "但品质模块尚未启用。请联系管理员开通。"
            ),
        }

    # Rule 3: compliance / audit keywords → module not enabled
    if _has_any(content, _COMPLIANCE_KEYWORDS):
        return {
            "type": "module_not_enabled",
            "module": "compliance",
            "next_action": "ask_clarification",
            "content": (
                "检测到合规模块关键词（IWAY / FSC / EHS / 审计），"
                "但合规模块尚未启用。请联系管理员开通。"
            ),
        }

    # Rule 4: nothing matched → clarify
    return {
        "type": "ask_clarification",
        "module": "unknown",
        "next_action": "ask_clarification",
        "content": (
            "我没有理解您的需求，请进一步说明您想要做什么。"
        ),
    }


# ── Internal helper ──────────────────────────────────────────

def _has_any(text: str, keywords: list) -> bool:
    """Return True if *text* contains any of the *keywords*."""
    for kw in keywords:
        if kw.lower() in text:
            return True
    return False
