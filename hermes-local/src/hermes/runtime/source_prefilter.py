"""
source_prefilter.py

Source Prefilter — lightweight routing layer that sits AFTER
message_normalizer.  It inspects the normalized message's
source_window, message_type, and content keywords, then decides
whether the message can be fast-pathed to a dedicated module or
should fall through to the global agent.

Output guarantees:
  stage, source_window, suggested_module, confidence,
  fast_path, next_action, reason
"""

from typing import Any

# ── keyword lists ──────────────────────────────────────────────

_REIMBURSEMENT_KEYWORDS = [
    # Chinese
    "报销", "发票", "收据", "付款", "金额",
    "打车", "出租车", "交通费", "物流费",
    "餐费", "样品费", "费用", "退款",
    # English
    "invoice", "receipt", "payment", "expense",
    "reimbursement",
    # Vietnamese (common in cross-border scenarios)
    "hóa đơn", "thanh toán", "chi phí", "biên lai",
]

_QUALITY_BUSINESS_KEYWORDS = [
    # Chinese
    "品质", "质量", "客诉", "8D",
    "不良", "缺陷", "投诉", "IWAY", "FSC", "EHS",
    "审计", "合规", "整改", "客户",
    "报价", "邮件", "项目",
    # English
    "quotation", "customer", "price",
    "email", "project",
]

_FAST_PATH_FILE_TYPES = {"image", "pdf", "file"}


def source_prefilter(message: dict) -> dict:
    """
    Pre-filter a *normalized* message and return a routing decision.

    Parameters
    ----------
    message : dict
        Output of ``normalize_message()`` — guaranteed to contain
        *source_window*, *message_type*, *content*, etc.

    Returns
    -------
    dict
        Routing decision with these keys:
          stage            "source_prefilter"
          source_window    copied from input
          suggested_module e.g. "reimbursement", "unknown"
          confidence       0.0 – 1.0
          fast_path        bool — can skip global agent?
          next_action      str  — routing instruction
          reason           str  — human-readable explanation
    """
    message = message or {}
    source_window = (message.get("source_window") or "").strip()
    message_type = (message.get("message_type") or "").strip().lower()
    content = (message.get("content") or "").strip().lower()

    # ── Helper: match any keyword in text ──────────────────────
    def _has_any(text: str, keywords: list) -> bool:
        text_lower = text.lower()
        for kw in keywords:
            if kw.lower() in text_lower:
                return True
        return False

    # ── Rule E: general_assistant → always global ──────────────
    if source_window == "general_assistant":
        return _decision(
            source_window=source_window,
            suggested_module="unknown",
            confidence=0.3,
            fast_path=False,
            next_action="send_to_global_agent0",
            reason=(
                f"source_window='{source_window}' — "
                "no dedicated module; forward to global agent"
            ),
        )

    # ── Remaining rules apply to reimbursement_assistant ───────
    if source_window == "reimbursement_assistant":
        # Rule A: file message types → fast-path
        if message_type in _FAST_PATH_FILE_TYPES:
            return _decision(
                source_window=source_window,
                suggested_module="reimbursement",
                confidence=0.95,
                fast_path=True,
                next_action="route_to_reimbursement_module",
                reason=(
                    f"message_type='{message_type}' matches "
                    f"fast-path file types"
                ),
            )

        # Rule B: reimbursement keywords match → fast-path
        if _has_any(content, _REIMBURSEMENT_KEYWORDS):
            return _decision(
                source_window=source_window,
                suggested_module="reimbursement",
                confidence=0.9,
                fast_path=True,
                next_action="route_to_reimbursement_module",
                reason=(
                    "content matches reimbursement-related keywords"
                ),
            )

        # Rule C: quality / business keywords → global agent
        if _has_any(content, _QUALITY_BUSINESS_KEYWORDS):
            return _decision(
                source_window=source_window,
                suggested_module="unknown",
                confidence=0.45,
                fast_path=False,
                next_action="send_to_global_agent0",
                reason=(
                    "content matches quality / compliance / business "
                    "keywords — not reimbursement"
                ),
            )

        # Rule D: reimbursement_assistant, unclear content
        return _decision(
            source_window=source_window,
            suggested_module="reimbursement",
            confidence=0.7,
            fast_path=False,
            next_action="send_to_global_agent0",
            reason=(
                "source_window='reimbursement_assistant' but "
                "no strong signal — forward to global agent "
                "with reimbursement context"
            ),
        )

    # ── Unknown source_window ──────────────────────────────────
    return _decision(
        source_window=source_window,
        suggested_module="unknown",
        confidence=0.3,
        fast_path=False,
        next_action="send_to_global_agent0",
        reason=(
            f"source_window='{source_window}' is not recognised; "
            "forward to global agent"
        ),
    )


# ── Internal helper ────────────────────────────────────────────

def _decision(
    source_window: str,
    suggested_module: str,
    confidence: float,
    fast_path: bool,
    next_action: str,
    reason: str,
) -> dict:
    return {
        "stage": "source_prefilter",
        "source_window": source_window,
        "suggested_module": suggested_module,
        "confidence": confidence,
        "fast_path": fast_path,
        "next_action": next_action,
        "reason": reason,
    }
