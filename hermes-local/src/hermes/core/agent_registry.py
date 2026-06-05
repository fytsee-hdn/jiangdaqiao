"""
agent_registry.py — Agent Registry for the GSP architecture.

Loads the agent registry from JSON, provides lookup functions,
and validates agent entries.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

# Default registry path
_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "agent_registry.json"
)

_registry_cache: Optional[List[dict]] = None


def _resolve_registry_path() -> str:
    """Return the resolved absolute path to agent_registry.json."""
    # Try the standard config/ path first
    path = os.path.abspath(_REGISTRY_PATH)
    if os.path.isfile(path):
        return path

    # Fallback: old hermes/agent_registry/ path
    fallback = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "agent_registry", "agent_registry.json"
    )
    if os.path.isfile(os.path.abspath(fallback)):
        return os.path.abspath(fallback)

    return path  # return default even if missing


def load_registry() -> List[dict]:
    """Load the agent registry JSON. Returns a list of agent entries."""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    path = _resolve_registry_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        agents = data.get("agents", [])
        _registry_cache = list(agents)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        _registry_cache = []
    return _registry_cache


def get_agent(agent_id: str) -> Optional[dict]:
    """Look up a single agent by agent_id."""
    for agent in load_registry():
        if agent.get("agent_id") == agent_id:
            return dict(agent)
    return None


def list_agents(
    agent_type: Optional[str] = None,
    status: Optional[str] = None,
) -> List[dict]:
    """List agents, optionally filtered by type and/or status."""
    agents = load_registry()
    if agent_type:
        agents = [a for a in agents if a.get("type") == agent_type]
    if status:
        agents = [a for a in agents if a.get("status") == status]
    return [dict(a) for a in agents]


def is_agent_active(agent_id: str) -> bool:
    """Check if an agent is active."""
    agent = get_agent(agent_id)
    return agent is not None and agent.get("status") == "active"
