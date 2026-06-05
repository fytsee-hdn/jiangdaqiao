"""
base_agent.py — GSP Agent Architecture: Base Agent Interface.

All agents in the GSP architecture inherit from BaseAgent.
Provides a standard interface for message handling, health checks,
and permission management.

Compatible with Python 3.9+.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional


class BaseAgent(abc.ABC):
    """Base class for all GSP agents (Service, Admin, Business)."""

    # Subclasses MUST override these
    agent_id: str = "base_agent"
    display_name: str = "Base Agent"
    version: str = "0.1.0"
    description: str = "Base agent — override in subclass."

    # ========================================================================
    #  Abstract / required overrides
    # ========================================================================

    @abc.abstractmethod
    def can_handle(self, message: dict, context: Optional[dict] = None) -> float:
        """Return a confidence score 0.0–1.0 indicating whether this agent
        should handle the given message.

        Parameters
        ----------
        message : dict
            Normalised message dict with at least: content, message_type,
            source, user_id.
        context : dict, optional
            Additional context such as conversation history, user profile,
            active state, etc.

        Returns
        -------
        float
            Confidence score.  1.0 = definitely mine, 0.0 = definitely not.
        """
        ...

    @abc.abstractmethod
    def handle(self, message: dict, context: Optional[dict] = None) -> dict:
        """Handle a message and return a standard result dict.

        Parameters
        ----------
        message : dict
            Normalised message dict.
        context : dict, optional
            Additional context.

        Returns
        -------
        dict
            Standard result with keys:
              - ok: bool
              - agent_id: str
              - reply_text: str
              - data: dict
              - audit_event: dict | None
              - next_state: dict | None
              - error: str
        """
        ...

    # ========================================================================
    #  Concrete methods (may be overridden)
    # ========================================================================

    def get_supported_message_types(self) -> List[str]:
        """Return the list of message types this agent can process."""
        return ["text"]

    def get_required_permissions(self) -> List[str]:
        """Return the list of permissions required to invoke this agent."""
        return []

    def health_check(self) -> dict:
        """Return a health / readiness report for this agent."""
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "version": self.version,
            "status": "ok",
            "message": f"{self.display_name} is ready.",
        }

    def __repr__(self) -> str:
        return f"<{self.agent_id} v{self.version}>"
