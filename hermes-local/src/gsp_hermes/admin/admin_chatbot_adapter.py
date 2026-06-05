"""
Admin Chatbot Adapter — WeChat-facing entry point for the System Admin Agent.

This module is NOT connected to the real WeChat gateway yet (that happens
in a later phase).  It provides a message-handling function that:

1.  Checks the caller against ADMIN_ALLOWED_USERS.
2.  Classifies the command via the admin command router.
3.  Logs the action to the admin audit log.
4.  Routes to the appropriate status tool or returns confirmation/rejection
    text based on risk level and permissions.
"""

import os

from gsp_hermes.admin.admin_command_router import classify_admin_command
from gsp_hermes.admin.admin_audit_logger import log_admin_action
from gsp_hermes.admin.admin_status_tools import (
    get_system_status_summary,
    get_expense_csv_summary,
    get_state_summary,
    get_gateway_log_summary,
    get_bridge_process_status,
)

# ---------------------------------------------------------------------------
# Import format_status_summary — with a fallback in case admin_runner
# cannot be imported (e.g. packaging partial imports).
# ---------------------------------------------------------------------------
try:
    from gsp_hermes.admin.admin_runner import format_status_summary
except ImportError:
    # Fallback: build a minimal summary string from the status tool dicts
    def format_status_summary(summary):
        # type: (dict) -> str
        lines = []
        lines.append("====== 系统状态总览 ======")
        lines.append("")

        bridge = summary.get("bridge", {})
        if bridge.get("running"):
            pids = [str(p["pid"]) for p in bridge.get("processes", []) if p.get("pid")]
            lines.append("✅ Bridge 运行中 (PID: {})".format(
                ", ".join(pids) if pids else "?"
            ))
        else:
            lines.append("❌ Bridge 未运行")

        csv_info = summary.get("csv", {})
        if csv_info.get("exists") and csv_info.get("record_count", 0) > 0:
            lines.append("📊 CSV: {} 条记录".format(csv_info["record_count"]))
        else:
            lines.append("📊 CSV: 0 条记录")

        state = summary.get("state", {})
        count = state.get("state_count", 0)
        lines.append("📁 未完成会话: {}".format(count))

        log_info = summary.get("gateway_log", {})
        if log_info.get("exists"):
            total = log_info.get("total_lines", 0)
            size_kb = log_info.get("file_size_bytes", 0) / 1024.0
            err_count = log_info.get("event_counts", {}).get("error", 0)
            lines.append("📜 Gateway 日志: {} 行 ({:.1f} KB), 错误 {} 次".format(
                total, size_kb, err_count
            ))
        else:
            lines.append("📜 Gateway 日志: 不存在")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADMIN_ALLOWED_USERS_ENV = "ADMIN_ALLOWED_USERS"

# ---------------------------------------------------------------------------
# Authorisation helper
# ---------------------------------------------------------------------------


def _get_message_profile(message):
    # type: (dict) -> str
    context = message.get("context") if isinstance(message.get("context"), dict) else {}
    profile = message.get("profile") or message.get("profile_name") or context.get("profile")
    return (profile or "admin").strip().lower()


def _is_admin_profile(message):
    # type: (dict) -> bool
    return _get_message_profile(message) == "admin"


def _get_allowed_users():
    # type: () -> list
    """Return the list of allowed user IDs from the environment variable.

    Reads ``ADMIN_ALLOWED_USERS``, splits by comma and strips whitespace
    from each entry.  Returns an empty list if the variable is not set or
    is empty.
    """
    raw = os.environ.get(_ADMIN_ALLOWED_USERS_ENV, "")
    if not raw or not raw.strip():
        return []
    return [uid.strip() for uid in raw.split(",") if uid.strip()]


# ---------------------------------------------------------------------------
# Low-risk intent routing helpers (inline formatting)
# ---------------------------------------------------------------------------


def _format_csv_summary():
    """Format expense CSV summary as a reply string."""
    csv_summary = get_expense_csv_summary(limit=5)
    lines = []
    if not csv_summary.get("exists") or csv_summary.get("record_count", 0) == 0:
        lines.append("📊 报销记录: 无记录")
    else:
        lines.append("📊 报销记录摘要 (最近 {} 条):".format(
            len(csv_summary.get("recent_records", []))
        ))
        lines.append("   总记录数: {}".format(csv_summary["record_count"]))
        for i, record in enumerate(csv_summary.get("recent_records", []), 1):
            fields = ", ".join(
                "{}={}".format(k, v) for k, v in record.items() if v
            )
            lines.append("   {}. {}".format(i, fields))
    return "\n".join(lines)


def _format_state_summary():
    """Format state directory summary as a reply string."""
    state = get_state_summary()
    lines = []
    count = state.get("state_count", 0)
    if not state.get("exists") or count == 0:
        lines.append("📁 未完成会话: 0")
    else:
        lines.append("📁 未完成会话: {}".format(count))
        for fname in state.get("state_files", []):
            lines.append("   - {}".format(fname))
    return "\n".join(lines)


def _format_bridge_status():
    """Format bridge process status as a reply string."""
    bridge = get_bridge_process_status()
    lines = []
    if not bridge.get("running"):
        lines.append("❌ Bridge 未运行")
    else:
        procs = bridge.get("processes", [])
        pids = [str(p["pid"]) for p in procs if p.get("pid")]
        lines.append("✅ Bridge 运行中 (PID: {})".format(
            ", ".join(pids) if pids else "?"
        ))
        for proc in procs:
            cmd = proc.get("command_summary", "?")
            pid = proc.get("pid", "?")
            lines.append("   PID {}: {}".format(pid, cmd))
    return "\n".join(lines)


def _format_log_summary(limit=20):
    """Format gateway log summary as a reply string."""
    log_summary = get_gateway_log_summary(limit=limit)
    lines = []
    if not log_summary.get("exists"):
        lines.append("📜 Gateway 日志文件不存在")
        return "\n".join(lines)

    total = log_summary.get("total_lines", 0)
    file_size = log_summary.get("file_size_bytes", 0)
    size_kb = file_size / 1024.0
    counts = log_summary.get("event_counts", {})

    lines.append("📜 Gateway 日志摘要")
    lines.append("   总行数: {} | 大小: {:.1f} KB".format(total, size_kb))
    lines.append("   请求: {} | 响应: {} | 错误: {} | 其它: {}".format(
        counts.get("request_received", 0),
        counts.get("response_sent", 0),
        counts.get("error", 0),
        counts.get("other", 0),
    ))
    lines.append("")
    lines.append("--- 最近 {} 条日志 ---".format(limit))
    for entry in log_summary.get("recent_entries", []):
        lines.append("  {}".format(entry))

    return "\n".join(lines)


def _format_general_help(text):
    # type: (str) -> str
    """Fallback for unrecognised intents — general help text."""
    return (
        "收到指令，但未匹配到已知管理操作。\n"
        "您可以说：\n"
        "  «查看状态»  — 系统整体状态\n"
        "  «查看日志»  — Gateway 日志\n"
        "  «查看 CSV»  — 报销记录摘要\n"
        "  «查看会话»  — 未完成会话列表\n"
        "  «查看 bridge» — Bridge 进程状态\n"
        "原始输入: {}".format(text)
    )


# ---------------------------------------------------------------------------
# Intent routing table for low-risk (no confirmation needed) intents
# ---------------------------------------------------------------------------

_LOW_RISK_ROUTER = {
    "inspect_status": lambda: format_status_summary(get_system_status_summary()),
    "system_status": lambda: format_status_summary(get_system_status_summary()),
    "inspect_csv_summary": _format_csv_summary,
    "inspect_state_summary": _format_state_summary,
    "inspect_bridge": _format_bridge_status,
    "read_logs": lambda: _format_log_summary(limit=20),
    "read_logs_summary": lambda: _format_log_summary(limit=20),
    "inspect_recent_messages": lambda: _format_log_summary(limit=20),
}


def _route_low_risk_intent(intent, text):
    # type: (str, str) -> str
    """Route a low-risk, non-confirmable intent to its formatter.

    Falls back to the general help message if the intent is unknown.
    """
    handler = _LOW_RISK_ROUTER.get(intent)
    if handler is not None:
        return handler()
    return _format_general_help(text)


# ---------------------------------------------------------------------------
# Confirmation prompt builder for medium-risk intents
# ---------------------------------------------------------------------------


def _build_confirmation_text(intent):
    # type: (str) -> str
    """Return a human-readable confirmation prompt for *intent*."""
    _KNOWN_OPERATIONS = {
        "run_tests": "运行测试",
        "backup_data": "备份数据",
        "clear_logs": "清理日志",
        "restart_service": "重启服务",
        "stop_service": "停止服务",
        "start_service": "启动服务",
        "write_code": "修改代码",
        "modify_env": "修改配置",
        "delete_data": "删除数据",
        "modify_policies": "修改权限",
        "reset_system": "重置系统",
    }
    label = _KNOWN_OPERATIONS.get(intent, intent)
    return "请确认执行：{}。输入 'yes' 继续。".format(label)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def handle_admin_chatbot_message(message):
    # type: (dict) -> dict
    """Handle an incoming message from the WeChat chatbot interface.

    Parameters
    ----------
    message : dict
        Input schema::

            {
                "source": "wechat_chatbot",
                "bot_name": "Hermes管理员助手",
                "user_id": "",
                "content": "",
                "conversation_id": ""
            }

    Returns
    -------
    dict
        Schema::

            {
                "success": True/False,
                "authorized": True/False,
                "reply_text": "",
                "intent": "",
                "risk_level": "",
                "requires_confirmation": False
            }
    """
    # Default empty response
    response = {
        "success": False,
        "authorized": False,
        "reply_text": "",
        "intent": "",
        "risk_level": "",
        "requires_confirmation": False,
        "profile": _get_message_profile(message),
    }

    # ------------------------------------------------------------------
    # Step 1: Identity check
    # ------------------------------------------------------------------
    allowed_users = _get_allowed_users()
    if not allowed_users:
        # No admin chatbot configured
        response["reply_text"] = "当前入口仅限系统管理员使用。"
        return response

    user_id = message.get("user_id", "")
    if user_id not in allowed_users:
        response["reply_text"] = "当前入口仅限系统管理员使用。"
        return response

    # Mark as authorized — the user passed identity check
    response["authorized"] = True

    if not _is_admin_profile(message):
        profile = _get_message_profile(message)
        log_admin_action({
            "actor": "admin_chatbot_user",
            "entrypoint": "admin_chatbot",
            "user_id": user_id,
            "intent": "profile_gate",
            "risk_level": "forbidden",
            "requires_confirmation": False,
            "allowed": False,
            "summary": "profile_not_allowed",
            "data": {"profile": profile, "deny_reason": "profile_not_allowed"},
        })
        response["success"] = False
        response["intent"] = "profile_gate"
        response["risk_level"] = "forbidden"
        response["reply_text"] = "当前入口仅限 admin profile 使用。"
        return response

    # ------------------------------------------------------------------
    # Step 2: Classify command
    # ------------------------------------------------------------------
    content = message.get("content", "")
    classification = classify_admin_command(content, entrypoint="admin_chatbot")

    intent = classification.get("intent", "unknown")
    risk_level = classification.get("risk_level", "low")
    allowed = classification.get("allowed", True)
    requires_confirmation = classification.get("requires_confirmation", False)
    reason = classification.get("reason", "")

    # ------------------------------------------------------------------
    # Step 3: Log the action (attempted action logging, not result)
    # ------------------------------------------------------------------
    audit_entry = {
        "actor": "admin_chatbot_user",
        "entrypoint": "admin_chatbot",
        "user_id": user_id,
        "intent": intent,
        "risk_level": risk_level,
        "requires_confirmation": requires_confirmation,
        "allowed": allowed,
        "summary": content[:120],
        "data": {"raw_text": content, "profile": response.get("profile")},
    }
    log_admin_action(audit_entry)

    # ------------------------------------------------------------------
    # Step 4: Build response based on classification result
    # ------------------------------------------------------------------
    response["intent"] = intent
    response["risk_level"] = risk_level
    response["requires_confirmation"] = requires_confirmation

    if not allowed:
        # Rejected by the command router (e.g. high-risk on chatbot,
        # or forbidden intent)
        response["success"] = False
        response["reply_text"] = reason
        return response

    if requires_confirmation:
        # Medium risk — needs user confirmation
        response["success"] = True
        response["reply_text"] = _build_confirmation_text(intent)
        return response

    # Allowed, low risk (no confirmation needed) — route to tools
    response["success"] = True
    response["reply_text"] = _route_low_risk_intent(intent, content)
    return response
