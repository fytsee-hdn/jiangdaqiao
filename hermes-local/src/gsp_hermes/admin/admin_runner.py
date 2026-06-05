"""
Admin Runner — CLI entry point for System Admin Agent.

Accepts a command text, classifies it via the command router, checks
permissions, routes to the appropriate handler, and returns a response.
"""

from gsp_hermes.admin.admin_command_router import classify_admin_command
from gsp_hermes.admin.admin_audit_logger import log_admin_action, read_admin_log
from gsp_hermes.admin.admin_status_tools import (
    get_system_status_summary,
    get_expense_csv_summary,
    get_state_summary,
    get_gateway_log_summary,
    get_bridge_process_status,
)

# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


def format_bridge_status(bridge):
    """Format bridge process status as a short string."""
    if not bridge.get("running"):
        return "❌ Bridge 未运行"
    procs = bridge.get("processes", [])
    pids = [str(p["pid"]) for p in procs if p.get("pid")]
    return "✅ Bridge 运行中 (PID: {})".format(", ".join(pids) if pids else "?")


def format_csv_status(csv_summary):
    """Format expense CSV summary as a short string."""
    if not csv_summary.get("exists") or csv_summary.get("record_count", 0) == 0:
        return "📊 CSV: 0 条记录"
    return "📊 CSV: {} 条记录".format(csv_summary["record_count"])


def format_state_status(state):
    """Format state directory summary as a short string."""
    count = state.get("state_count", 0)
    if not state.get("exists") or count == 0:
        return "📁 未完成会话: 0"
    return "📁 未完成会话: {}".format(count)


def format_log_status(log_summary):
    """Format gateway log summary as a short string."""
    if not log_summary.get("exists"):
        return "📜 Gateway 日志: 不存在"
    total = log_summary.get("total_lines", 0)
    file_size = log_summary.get("file_size_bytes", 0)
    size_kb = file_size / 1024.0
    counts = log_summary.get("event_counts", {})
    return "📜 Gateway 日志: {} 行 ({:.1f} KB), 错误 {} 次".format(
        total, size_kb, counts.get("error", 0)
    )


def format_status_summary(summary):
    # type: (dict) -> str
    """Format a full status summary dict into a clean terminal-friendly string.

    Parameters
    ----------
    summary : dict
        Must contain keys ``bridge``, ``csv``, ``state``, ``gateway_log``.
        Each key maps to the corresponding status tool dict.

    Returns
    -------
    str
    """
    lines = []
    lines.append("====== 系统状态总览 ======")
    lines.append("")

    # Bridge
    bridge = summary.get("bridge", {})
    lines.append(format_bridge_status(bridge))

    # CSV
    csv_summary = summary.get("csv", {})
    lines.append(format_csv_status(csv_summary))

    # State
    state = summary.get("state", {})
    lines.append(format_state_status(state))

    # Gateway log
    log_summary = summary.get("gateway_log", {})
    lines.append(format_log_status(log_summary))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Intent handlers
# ---------------------------------------------------------------------------


def _handle_system_status():
    """Handle inspect_status / system_status intents."""
    summary = get_system_status_summary()
    return format_status_summary(summary)


def _handle_csv_summary():
    """Handle inspect_csv_summary intent."""
    csv_summary = get_expense_csv_summary(limit=5)
    lines = []
    if not csv_summary.get("exists") or csv_summary.get("record_count", 0) == 0:
        lines.append("📊 报销记录: 无记录")
    else:
        lines.append("📊 报销记录摘要 (最近 {} 条):".format(len(csv_summary.get("recent_records", []))))
        lines.append("   总记录数: {}".format(csv_summary["record_count"]))
        for i, record in enumerate(csv_summary.get("recent_records", []), 1):
            fields = ", ".join(
                "{}={}".format(k, v) for k, v in record.items() if v
            )
            lines.append("   {}. {}".format(i, fields))
    return "\n".join(lines)


def _handle_state_summary():
    """Handle inspect_state_summary intent."""
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


def _handle_bridge_status():
    """Handle inspect_bridge intent."""
    bridge = get_bridge_process_status()
    lines = []
    lines.append(format_bridge_status(bridge))
    if bridge.get("running"):
        for proc in bridge.get("processes", []):
            cmd = proc.get("command_summary", "?")
            pid = proc.get("pid", "?")
            lines.append("   PID {}: {}".format(pid, cmd))
    return "\n".join(lines)


def _handle_logs(limit=20):
    """Handle read_logs / read_logs_summary / inspect_recent_messages intents."""
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


def _handle_general_chat(text):
    # type: (str) -> str
    """Fallback for unknown / unrecognised intents — treat as general chat."""
    return "收到指令，但未匹配到已知管理操作。您可以说「查看状态」「查看日志」「查看 CSV」等。\n原始输入: {}".format(
        text
    )


# ---------------------------------------------------------------------------
# Main dispatch function
# ---------------------------------------------------------------------------


def _normalize_profile(profile):
    # type: (str) -> str
    return (profile or "admin").strip().lower()


def _is_admin_profile(profile):
    # type: (str) -> bool
    return _normalize_profile(profile) == "admin"


def run_admin_command(text, entrypoint="admin_cli", user_id="", profile="admin"):
    # type: (str, str, str, str) -> dict
    """Run an admin command through the classification and routing pipeline.

    Parameters
    ----------
    text : str
        The raw user command text.
    entrypoint : str, optional
        One of ``"admin_cli"`` (default) or ``"admin_chatbot"``.
    user_id : str, optional
        The user identifier for audit logging.
    profile : str, optional
        The active profile. Only the admin profile can use this pipeline.

    Returns
    -------
    dict
        Keys: ``success``, ``reply_text``, ``intent``, ``risk_level``.
    """
    # 1. Classify
    classification = classify_admin_command(text, entrypoint)
    intent = classification.get("intent", "unknown")
    risk_level = classification.get("risk_level", "low")
    allowed = classification.get("allowed", True)
    requires_confirmation = classification.get("requires_confirmation", False)
    reason = classification.get("reason", "")

    profile = _normalize_profile(profile)

    # 2. Build audit log entry
    audit_entry = {
        "actor": "admin_cli_user",
        "entrypoint": entrypoint,
        "user_id": user_id,
        "intent": intent,
        "risk_level": risk_level,
        "requires_confirmation": requires_confirmation,
        "allowed": allowed,
        "summary": text[:120],
        "data": {"raw_text": text, "profile": profile},
    }

    if not _is_admin_profile(profile):
        audit_entry["allowed"] = False
        audit_entry["data"]["deny_reason"] = "profile_not_allowed"
        log_admin_action(audit_entry)
        return {
            "success": False,
            "reply_text": "当前指令只能由 admin profile 执行。",
            "intent": intent,
            "risk_level": risk_level,
            "profile": profile,
            "reason": "profile_not_allowed",
        }

    log_admin_action(audit_entry)

    # 3. If not allowed — reject and return reason
    if not allowed:
        return {
            "success": False,
            "reply_text": reason,
            "intent": intent,
            "risk_level": risk_level,
            "profile": profile,
        }

    # 4. If requires confirmation — ask user to confirm
    if requires_confirmation:
        intent_cn = {
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
        }.get(intent, intent)
        return {
            "success": True,
            "reply_text": "请确认执行：{}。输入 'yes' 继续。".format(intent_cn),
            "intent": intent,
            "risk_level": risk_level,
            "requires_confirmation": True,
            "profile": profile,
        }

    # 5. Route to handler based on intent
    reply_text = _route_intent(intent, text)

    return {
        "success": True,
        "reply_text": reply_text,
        "intent": intent,
        "risk_level": risk_level,
        "profile": profile,
    }


def _route_intent(intent, text):
    # type: (str, str) -> str
    """Route a known intent to its handler and return a formatted reply string.

    Uses the intent returned by ``classify_admin_command`` plus the original
    *text* for the general-chat fallback.
    """
    handler_map = {
        "inspect_status": _handle_system_status,
        "system_status": _handle_system_status,
        "inspect_csv_summary": _handle_csv_summary,
        "inspect_state_summary": _handle_state_summary,
        "inspect_bridge": _handle_bridge_status,
        "read_logs": _handle_logs,
        "read_logs_summary": _handle_logs,
        "inspect_recent_messages": _handle_logs,
    }

    handler = handler_map.get(intent)
    if handler is not None:
        return handler()
    return _handle_general_chat(text)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if not text:
        print("Usage: python -m hermes.admin_agent.admin_runner <command>")
        sys.exit(1)

    result = run_admin_command(text)
    print(result["reply_text"])
    if not result.get("success"):
        sys.exit(1)
