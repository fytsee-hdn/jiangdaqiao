"""
gsp_admin_agent.py — GSP Admin Agent (System Administrator).

Handles system administration tasks: status queries, log inspection,
config checks, data exports, test execution, and audit.

Implements the BaseAgent interface. Can be used via CLI, Admin Chatbot,
or called by the Service Agent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from gsp_hermes.admin.admin_runner import run_admin_command

try:
    from hermes.core.base_agent import BaseAgent
    from hermes.core.message import agent_result_factory
except Exception:
    class BaseAgent:
        pass

    def agent_result_factory(ok, agent_id, reply_text, data=None, error=None):
        return {
            "ok": ok,
            "agent_id": agent_id,
            "reply_text": reply_text,
            "data": data or {},
            "error": error,
        }


class GSPAdminAgent(BaseAgent):
    """System administration agent — status, logs, config, audit."""

    agent_id: str = "gsp_admin_agent"
    display_name: str = "GSP Admin Agent"
    version: str = "0.1.0"
    description: str = (
        "System administration agent. Handles status queries, log inspection, "
        "config checks, data exports, test execution, and audit. "
        "High-risk operations require CLI + confirmation."
    )

    # ══════════════════════════════════════════════════════════════
    #  Safe command mapping (Chatbot-allowed)
    # ══════════════════════════════════════════════════════════════

    _SAFE_COMMANDS = {
        "status": "查看系统状态",
        "logs": "查看最近日志",
        "health": "运行健康检查",
        "help": "显示帮助",
    }

    _HIGH_RISK_COMMANDS = [
        "write_code", "run_shell", "start_service", "stop_service",
        "restart_service", "delete_data", "clear_logs",
    ]

    # ══════════════════════════════════════════════════════════════
    #  BaseAgent interface
    # ══════════════════════════════════════════════════════════════

    def can_handle(self, message: dict, context: Optional[dict] = None) -> float:
        """Check if this is an admin command."""
        content = (message.get("content") or "").strip().lower()
        admin_keywords = [
            "status", "日志", "状态", "health", "config", "配置",
            "系统", "system", "管理", "admin", "log",
            "查看", "status", "检查",
        ]
        for kw in admin_keywords:
            if kw.lower() in content:
                return 0.8
        return 0.1

    def handle(self, message: dict, context: Optional[dict] = None) -> dict:
        """Run admin input through the shared admin pipeline."""
        context = context or {}
        content = (message.get("content") or "").strip()
        source = message.get("source", "cli")
        entrypoint = "admin_cli" if source in ("cli", "admin_cli") else "admin_chatbot"
        profile = (
            message.get("profile")
            or message.get("profile_name")
            or context.get("profile")
            or "admin"
        )
        user_id = message.get("user_id") or context.get("user_id") or ""

        result = run_admin_command(
            content,
            entrypoint=entrypoint,
            user_id=user_id,
            profile=profile,
        )
        return agent_result_factory(
            ok=bool(result.get("success")),
            agent_id=self.agent_id,
            reply_text=result.get("reply_text", ""),
            data=result,
            error=None if result.get("success") else result.get("reason", "admin_command_rejected"),
        )

    def get_supported_message_types(self) -> List[str]:
        return ["text"]

    def get_required_permissions(self) -> List[str]:
        return [
            "inspect_status", "inspect_config_masked",
            "read_logs_summary", "inspect_csv_summary",
        ]

    def health_check(self) -> dict:
        import os
        root = os.path.join(os.path.dirname(__file__), "..", "..")
        data_dir = os.path.join(root, "data")
        logs_dir = os.path.join(root, "logs")

        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "version": self.version,
            "status": "ok",
            "message": "Admin Agent ready.",
            "checks": {
                "data_dir": os.path.isdir(data_dir),
                "logs_dir": os.path.isdir(logs_dir),
            },
        }

    # ══════════════════════════════════════════════════════════════
    #  Internal
    # ══════════════════════════════════════════════════════════════

    def _classify_command(self, content: str) -> str:
        """Classify user input into a command name."""
        norm = content.lower()
        if any(w in norm for w in ["状态", "status"]):
            return "status"
        if any(w in norm for w in ["日志", "log"]):
            return "logs"
        if any(w in norm for w in ["health", "健康"]):
            return "health"
        return "help"

    def _execute_command(self, command: str, message: dict) -> dict:
        """Execute a safe admin command and return result."""
        if command == "help":
            cmds = "\n".join([f"  {k} — {v}" for k, v in self._SAFE_COMMANDS.items()])
            return agent_result_factory(
                ok=True,
                agent_id=self.agent_id,
                reply_text=f"可用的管理员命令：\n{cmds}",
            )

        if command == "status":
            return agent_result_factory(
                ok=True,
                agent_id=self.agent_id,
                reply_text=self.health_check()["message"],
                data=self.health_check(),
            )

        if command == "logs":
            return agent_result_factory(
                ok=True,
                agent_id=self.agent_id,
                reply_text="日志功能已就绪。请使用 `tail -f logs/gateway.log` 查看实时日志。",
            )

        if command == "health":
            return agent_result_factory(
                ok=True,
                agent_id=self.agent_id,
                reply_text="✅ 系统健康检查：通过。",
                data=self.health_check(),
            )

        return agent_result_factory(
            ok=True,
            agent_id=self.agent_id,
            reply_text="Admin Agent 已就绪。输入 'help' 查看可用命令。",
        )
