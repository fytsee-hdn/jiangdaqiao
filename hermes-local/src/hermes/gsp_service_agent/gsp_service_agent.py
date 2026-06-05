"""
gsp_service_agent.py — GSP Service Agent (Central Dispatcher).

The GSP Service Agent is the entry point for all user messages.
It normalises input, classifies intent via LLM, checks permissions,
and routes to the correct business agent.

KEY PRINCIPLE: Intent classification is done by the LLM Intent Router,
NOT by hardcoded keyword rules. The only deterministic shortcuts are:
  1. Active conversation state continuation
  2. Runtime safety (block dangerous commands)
  3. LLM failure → safe fallback (ask user)

DEPRECATED: The old _ROUTING_KEYWORDS dict and keyword-based routing
have been removed. See llm_intent_router.py for the replacement.

Implements the BaseAgent interface.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from hermes.core.base_agent import BaseAgent
from hermes.core.message import normalised_message_factory, agent_result_factory
from hermes.core.agent_registry import get_agent, is_agent_active
from hermes.gsp_service_agent.llm_intent_router import classify_intent

_logger = logging.getLogger(__name__)


class GSPServiceAgent(BaseAgent):
    """Central dispatch agent — LLM-driven intent routing."""

    agent_id: str = "gsp_service_agent"
    display_name: str = "GSP Service Agent"
    version: str = "0.2.0"
    description: str = (
        "Central dispatch agent. Uses LLM intent classification to route "
        "user messages to the appropriate business agent. "
        "Does NOT make business decisions. "
        "Does NOT use hardcoded keyword routing."
    )

    # ══════════════════════════════════════════════════════════════
    #  BaseAgent interface
    # ══════════════════════════════════════════════════════════════

    def can_handle(self, message: dict, context: Optional[dict] = None) -> float:
        """Service Agent handles anything — dispatch is its job."""
        return 1.0

    def handle(self, message: dict, context: Optional[dict] = None) -> dict:
        """Route using LLM Intent Router.

        Flow:
          1. Runtime safety check
          2. LLM intent classification
          3. Handle special intents (clarify, unsupported)
          4. Permission check (code-level, not LLM)
          5. Load and call target agent
          6. Return result
        """
        content = (message.get("content") or "").strip()
        user_id = message.get("user_id", "unknown_user")
        source = message.get("source", "unknown")
        context = context or {}

        # ── 1. Runtime safety check ──────────────────────────
        safety = self._safety_check(content)
        if safety["blocked"]:
            self._log_route(user_id, source, "blocked", 1.0, "safety_blocked")
            return agent_result_factory(
                ok=False,
                agent_id=self.agent_id,
                reply_text=safety["message"],
                audit_event={
                    "event": "safety_blocked",
                    "user_id": user_id,
                    "reason": safety["reason"],
                },
                error="runtime_safety_blocked",
            )

        # ── 2. LLM Intent Classification ─────────────────────
        intent = classify_intent(message, context)
        selected = intent["selected_agent"]
        confidence = intent["confidence"]
        route_source = intent.get("route_source", "llm")

        self._log_route(user_id, source, selected, confidence, route_source)

        # ── 3. Handle special intents ────────────────────────
        if selected == "clarify":
            return agent_result_factory(
                ok=True,
                agent_id=self.agent_id,
                reply_text=intent.get("clarification_question")
                or "请问你需要什么帮助？",
                data={
                    "selected_agent": "clarify",
                    "confidence": confidence,
                    "route_source": route_source,
                },
                audit_event=self._audit(intent, "clarify_sent"),
            )

        if selected == "unsupported":
            return agent_result_factory(
                ok=True,
                agent_id=self.agent_id,
                reply_text=(
                    "抱歉，你的请求超出了我当前能处理的范围。"
                    "我可以帮你处理报销、系统管理、质量投诉、合规审计、报价分析和采购查询。"
                ),
                data={
                    "selected_agent": "unsupported",
                    "confidence": confidence,
                    "route_source": route_source,
                },
                audit_event=self._audit(intent, "unsupported"),
            )

        # ── 4. Permission check (CODE-LEVEL, not LLM) ────────
        if intent.get("requires_permission"):
            user_role = context.get("user_role", "employee")
            permission_ok = self._check_permission(selected, user_role)
            if not permission_ok:
                return agent_result_factory(
                    ok=False,
                    agent_id=self.agent_id,
                    reply_text=(
                        "你没有执行该管理操作的权限。"
                        "请使用 GSP Service Agent 入口提交普通业务请求，或联系管理员。"
                    ),
                    data={
                        "selected_agent": selected,
                        "permission_denied": True,
                    },
                    audit_event=self._audit(intent, "permission_denied"),
                    error="permission_denied",
                )

        # ── 5. Load and call target agent ────────────────────
        target_result = self._call_target_agent(selected, message, intent)

        return agent_result_factory(
            ok=target_result.get("ok", True),
            agent_id=self.agent_id,
            reply_text=target_result.get("reply_text", ""),
            data={
                "selected_agent": selected,
                "confidence": confidence,
                "route_source": route_source,
                "intent_summary": intent.get("intent_summary", ""),
                "target_result": target_result.get("data", {}),
            },
            audit_event=self._audit(intent, f"routed_to_{selected}"),
        )

    def get_supported_message_types(self) -> List[str]:
        return ["text", "image", "pdf", "file", "multi"]

    def get_required_permissions(self) -> List[str]:
        return ["route_message"]

    def health_check(self) -> dict:
        from hermes.core.agent_registry import list_agents
        agents = list_agents()
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "version": self.version,
            "status": "ok",
            "message": f"Service Agent ready (LLM Intent Router v{self.version}). "
                       f"{len(agents)} agents in registry.",
            "registered_agents": [a["agent_id"] for a in agents],
            "router_mode": "llm_intent_router",
        }

    # ══════════════════════════════════════════════════════════════
    #  Internal: safety check
    # ══════════════════════════════════════════════════════════════

    def _safety_check(self, content: str) -> dict:
        """Block dangerous commands. This is DETERMINISTIC, not keyword routing."""
        blocked_patterns = [
            "rm -rf", "chmod", "chown", "kill -9",
            "DROP TABLE", "DELETE FROM",
            "修改代码", "执行命令", "运行脚本",
            "查看 token", "查看 secret", "打印 API key",
        ]
        norm = content.lower()
        for pattern in blocked_patterns:
            if pattern.lower() in norm:
                return {
                    "blocked": True,
                    "reason": f"blocked_pattern: {pattern}",
                    "message": (
                        "当前入口仅用于业务处理，不能执行系统维护、代码修改或敏感配置操作。"
                        "如需维护系统，请使用 GSP Admin Agent。"
                    ),
                }
        return {"blocked": False, "reason": "", "message": ""}

    # ══════════════════════════════════════════════════════════════
    #  Internal: permission check
    # ══════════════════════════════════════════════════════════════

    def _check_permission(self, target_agent: str, user_role: str) -> bool:
        """Code-level permission check. LLM never decides permissions."""
        if target_agent == "gsp_admin_agent":
            return user_role in ("owner", "admin")
        # All other agents are accessible to all roles
        return True

    # ══════════════════════════════════════════════════════════════
    #  Internal: call target agent
    # ══════════════════════════════════════════════════════════════

    def _call_target_agent(
        self, agent_id: str, message: dict, intent: dict
    ) -> dict:
        """Load and call the target agent. Handles unavailable agents gracefully."""
        # Check agent exists and is active
        agent_info = get_agent(agent_id)
        if agent_info is None:
            return {
                "ok": False,
                "reply_text": f"Agent '{agent_id}' 未在系统中注册。",
                "data": {},
            }

        status = agent_info.get("status", "unknown")
        if status == "skeleton":
            display = agent_info.get("display_name", agent_id)
            return {
                "ok": True,
                "reply_text": f"{display} 骨架已就绪。业务逻辑尚未实现。",
                "data": {"agent_status": "skeleton"},
            }

        # Try to load and call the agent
        try:
            agent = self._load_agent_instance(agent_id, agent_info)
            if agent is None:
                return {
                    "ok": False,
                    "reply_text": f"无法加载 Agent '{agent_id}'。",
                    "data": {"error": "load_failed"},
                }

            result = agent.handle(message)
            return {
                "ok": result.get("ok", True),
                "reply_text": result.get("reply_text", ""),
                "data": {
                    "agent_id": agent_id,
                    "result": result.get("data", {}),
                },
            }
        except Exception as exc:
            _logger.error("Agent %s handle failed: %s", agent_id, exc)
            return {
                "ok": False,
                "reply_text": f"Agent '{agent_id}' 处理请求时出错，请稍后重试。",
                "data": {"error": str(exc)},
            }

    def _load_agent_instance(self, agent_id: str, agent_info: dict):
        """Dynamically load an agent instance from its entry_class."""
        entry_class = agent_info.get("entry_class", "")
        if not entry_class:
            return None

        # Map: "hermes.gsp_reimbursement_agent.gsp_reimbursement_agent.GSPReimbursementAgent"
        parts = entry_class.rsplit(".", 1)
        if len(parts) != 2:
            return None

        module_path, class_name = parts
        try:
            import importlib
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name, None)
            if cls is None:
                return None
            return cls()
        except (ImportError, AttributeError) as exc:
            _logger.warning("Cannot load agent %s: %s", agent_id, exc)
            return None

    # ══════════════════════════════════════════════════════════════
    #  Internal: logging
    # ══════════════════════════════════════════════════════════════

    def _log_route(
        self, user_id: str, source: str, target: str,
        confidence: float, route_source: str,
    ):
        """Log routing decision (no secrets)."""
        _logger.info(
            "Route: user=%s source=%s → %s (conf=%.2f via %s)",
            self._safe(user_id), self._safe(source),
            target, confidence, route_source,
        )

    def _audit(self, intent: dict, event: str) -> dict:
        """Build an audit event dict."""
        return {
            "event": event,
            "selected_agent": intent.get("selected_agent", ""),
            "confidence": intent.get("confidence", 0),
            "route_source": intent.get("route_source", ""),
            "intent_summary": intent.get("intent_summary", ""),
        }

    @staticmethod
    def _safe(s: str, max_len: int = 30) -> str:
        if not isinstance(s, str):
            return str(s)[:max_len]
        return s[:max_len] if len(s) > max_len else s
