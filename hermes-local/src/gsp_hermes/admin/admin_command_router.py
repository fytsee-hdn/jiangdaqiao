"""
Admin Command Router

Classifies admin commands by intent, risk level, and whether they're
allowed based on the entrypoint (admin_cli vs admin_chatbot).
"""

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Keyword-to-intent mappings
# ---------------------------------------------------------------------------

# Low risk intents
LOW_RISK_INTENTS = {
    "inspect_status": [
        "查看状态", "系统状态", "status", "health",
    ],
    "read_logs": [
        "查看日志", "最近日志", "错误日志", "查看错误", "gateway log",
    ],
    "read_logs_summary": [
        "日志摘要", "日志汇总",
    ],
    "inspect_recent_messages": [
        "最近消息", "最近收到的消息", "消息摘要", "recent messages",
    ],
    "inspect_csv_summary": [
        "查看 CSV", "报销记录摘要", "查看报销记录", "expense summary", "csv",
    ],
    "inspect_state_summary": [
        "查看 state", "未完成会话", "未完成 state", "state summary",
    ],
    "inspect_bridge": [
        "查看 bridge", "bridge 进程", "bridge status", "查看进程",
    ],
}

# Medium risk intents
MEDIUM_RISK_INTENTS = {
    "run_tests": [
        "运行测试", "跑测试", "run tests", "pytest", "启动测试",
    ],
    "backup_data": [
        "备份数据", "备份", "backup", "备份系统",
    ],
    "clear_logs": [
        "清理日志", "清除日志", "clear logs", "清空日志",
    ],
    "restart_service": [
        "重启 bridge", "重启服务", "restart", "重新启动",
    ],
    "stop_service": [
        "停止 bridge", "停止服务", "stop bridge",
    ],
    "start_service": [
        "启动 bridge", "启动服务", "start bridge",
    ],
}

# High risk intents (forbidden on chatbot, confirm_required on CLI)
HIGH_RISK_INTENTS = {
    "write_code": [
        "修改代码", "改代码", "修改 handler", "修改 validator",
        "写脚本", "patch", "git commit", "修改 prompt",
    ],
    "modify_env": [
        "修改配置", "修改 .env", "改配置", "修改环境变量",
    ],
    "delete_data": [
        "删除记录", "删除数据", "清空记录", "清除数据",
    ],
    "modify_policies": [
        "修改权限", "改权限", "修改策略",
    ],
    "reset_system": [
        "重置系统", "恢复出厂",
    ],
}

# Forbidden intents (always denied regardless of entrypoint)
FORBIDDEN_INTENTS = {
    "reveal_secret": [
        "查看 token", "查看 secret", "查看 API key", "打印 API key",
        "打开 .env", "显示 .env", "打印 .env", "输出 .env",
        "查看 .env", "读取 .env", "cat .env", "print .env",
        "api key", "apikey", "secret", "token", "password",
        "auth.json", "authorization", "credential", "credentials",
        "输出密钥", "显示密钥", "查看密钥", "密钥",
        "显示密码", "查看密码", "输出密码", "密码",
        "令牌", "凭证", "reveal",
    ],
}

# ---------------------------------------------------------------------------
# Internal permission table
# ---------------------------------------------------------------------------

# Maps (risk_level, entrypoint) -> (allowed, requires_confirmation)
_PERMISSION_TABLE = {
    ("forbidden", "admin_cli"):      (False, False),
    ("forbidden", "admin_chatbot"):  (False, False),
    ("high", "admin_cli"):           (True,  True),
    ("high", "admin_chatbot"):       (False, False),
    ("medium", "admin_cli"):         (True,  True),
    ("medium", "admin_chatbot"):     (True,  True),
    ("low", "admin_cli"):            (True,  False),
    ("low", "admin_chatbot"):        (True,  False),
}

# Reason strings for denied operations
_REASON_FORBIDDEN = "此操作涉及敏感信息，始终不允许执行"
_REASON_HIGH_ON_CHATBOT = "此操作风险较高，请在 CLI 中执行"
_REASON_NO_MATCH = "未匹配到已知指令，按普通对话处理"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize(text):
    """Normalize input text for matching."""
    return text.strip().lower()


def _get_risk_level(intent):
    """Return the risk level for a given intent string."""
    if intent in FORBIDDEN_INTENTS:
        return "forbidden"
    if intent in HIGH_RISK_INTENTS:
        return "high"
    if intent in MEDIUM_RISK_INTENTS:
        return "medium"
    if intent in LOW_RISK_INTENTS:
        return "low"
    return "low"


def _match_intent(text):
    """Match normalized text against keyword lists.

    Returns (intent_name, [matched_terms]) or ("", []).
    Priority order: forbidden > high > medium > low.
    """
    lowered = _normalize(text)

    # Check forbidden first
    for intent, keywords in FORBIDDEN_INTENTS.items():
        matched = [kw for kw in keywords if kw in lowered]
        if matched:
            return intent, matched

    # High risk
    for intent, keywords in HIGH_RISK_INTENTS.items():
        matched = [kw for kw in keywords if kw in lowered]
        if matched:
            return intent, matched

    # Medium risk
    for intent, keywords in MEDIUM_RISK_INTENTS.items():
        matched = [kw for kw in keywords if kw in lowered]
        if matched:
            return intent, matched

    # Low risk
    for intent, keywords in LOW_RISK_INTENTS.items():
        matched = [kw for kw in keywords if kw in lowered]
        if matched:
            return intent, matched

    return "", []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_admin_command(text, entrypoint="admin_cli"):
    # type: (str, str) -> Dict[str, object]
    """Classify an admin command by intent, risk level, and permissions.

    Parameters
    ----------
    text : str
        The raw user input / command text.
    entrypoint : str
        One of ``"admin_cli"`` or ``"admin_chatbot"``.

    Returns
    -------
    dict with keys:
        intent              - matched intent name or "unknown"
        risk_level          - "low" | "medium" | "high" | "forbidden"
        requires_confirmation - bool
        allowed             - bool
        reason              - explanation string
        suggested_action    - suggested CLI action string
        matched_terms       - list of matched keyword substrings
    """
    intent, matched_terms = _match_intent(text)

    if not intent:
        return {
            "intent": "unknown",
            "risk_level": "low",
            "requires_confirmation": False,
            "allowed": True,
            "reason": _REASON_NO_MATCH,
            "suggested_action": "",
            "matched_terms": [],
        }

    risk_level = _get_risk_level(intent)

    # Look up permission from table
    allowed, requires_confirmation = _PERMISSION_TABLE.get(
        (risk_level, entrypoint), (True, False)
    )

    # Build reason string based on why it was denied
    if risk_level == "forbidden":
        reason = _REASON_FORBIDDEN
    elif risk_level == "high" and entrypoint == "admin_chatbot":
        reason = _REASON_HIGH_ON_CHATBOT
    elif allowed:
        reason = "操作允许"
    else:
        reason = "操作不允许在当前入口执行"

    # Suggested CLI action (informational only)
    suggested_action = ""
    if risk_level == "high" and entrypoint == "admin_chatbot":
        suggested_action = "请在管理员 CLI 终端中执行此操作"
    elif risk_level == "forbidden":
        suggested_action = "此操作不被允许，请检查输入"

    return {
        "intent": intent,
        "risk_level": risk_level,
        "requires_confirmation": requires_confirmation,
        "allowed": allowed,
        "reason": reason,
        "suggested_action": suggested_action,
        "matched_terms": matched_terms,
    }


def check_permission(intent, entrypoint="admin_cli"):
    # type: (str, str) -> Dict[str, object]
    """Check permission for a known intent code.

    Parameters
    ----------
    intent : str
        A known intent name (e.g. ``"inspect_status"``, ``"write_code"``).
    entrypoint : str
        One of ``"admin_cli"`` or ``"admin_chatbot"``.

    Returns
    -------
    dict with keys: allowed, requires_confirmation, risk_level
    """
    risk_level = _get_risk_level(intent)
    allowed, requires_confirmation = _PERMISSION_TABLE.get(
        (risk_level, entrypoint), (True, False)
    )
    return {
        "allowed": allowed,
        "requires_confirmation": requires_confirmation,
        "risk_level": risk_level,
    }
