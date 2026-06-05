"""
wecom_config.py

Centralized WeCom (企业微信) configuration management.

Loads configuration from:
  1. Environment variables
  2. ~/.hermes/.env or ~/hermes-local/.env (dotenv-style, optional)

Provides safe access with secret masking to avoid accidental leaks.
"""

import os
from typing import Any

# ══════════════════════════════════════════════════════════════════
#  Default AgentID fallback
# ══════════════════════════════════════════════════════════════════

_DEFAULT_EXPENSE_AGENT_ID = "1000002"
_DEFAULT_GENERAL_AGENT_ID = "1000003"


# ══════════════════════════════════════════════════════════════════
#  .env file loader (optional)
# ══════════════════════════════════════════════════════════════════


def _load_dotenv() -> None:
    """
    Load .env files if they exist.

    Priority:
      1. ~/.hermes/.env
      2. ~/hermes-local/.env

    Skips silently if neither exists. Only sets variables that are
    not already set in the environment (os.environ.setdefault).
    """
    candidates = [
        os.path.expanduser("~/.hermes/.env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "..", ".env"),
    ]
    for path in candidates:
        path = os.path.abspath(path)
        if os.path.isfile(path):
            _load_dotenv_file(path)


def _load_dotenv_file(path: str) -> None:
    """Parse a simple KEY=VALUE file and set environment defaults."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("\"'")
                if key and val:
                    os.environ.setdefault(key, val)
    except (OSError, IOError):
        pass


# Ensure dotenv is loaded at import time
_load_dotenv()


# ══════════════════════════════════════════════════════════════════
#  Configuration loader
# ══════════════════════════════════════════════════════════════════

_MASKED_VALUE = "[CONFIGURED]"
_SECRET_KEYS = {
    "WECOM_CORP_ID",
    "WECOM_AGENT_EXPENSE_SECRET",
    "WECOM_AGENT_GENERAL_SECRET",
    "WECOM_CALLBACK_TOKEN",
    "WECOM_ENCODING_AES_KEY",
    "HERMES_GATEWAY_TOKEN",
}


def load_wecom_config(mask_secrets: bool = True) -> dict:
    """
    Load WeCom configuration from environment variables.

    Parameters
    ----------
    mask_secrets : bool
        If True (default), secret/token/key values are replaced with
        "[CONFIGURED]" or empty string to prevent accidental leaks.
        If False, returns real values (for internal use only).

    Returns
    -------
    dict with keys: corp_id, agents, callback, gateway, configured
    """
    # ── Read raw values ─────────────────────────────────────────
    corp_id = os.environ.get("WECOM_CORP_ID", "")

    expense_agent_id = os.environ.get(
        "WECOM_AGENT_EXPENSE_ID", _DEFAULT_EXPENSE_AGENT_ID,
    )
    expense_secret = os.environ.get("WECOM_AGENT_EXPENSE_SECRET", "")

    general_agent_id = os.environ.get(
        "WECOM_AGENT_GENERAL_ID", _DEFAULT_GENERAL_AGENT_ID,
    )
    general_secret = os.environ.get("WECOM_AGENT_GENERAL_SECRET", "")

    callback_token = os.environ.get("WECOM_CALLBACK_TOKEN", "")
    encoding_aes_key = os.environ.get("WECOM_ENCODING_AES_KEY", "")

    gateway_token = os.environ.get("HERMES_GATEWAY_TOKEN", "")

    # ── Mask secrets if requested ───────────────────────────────
    def _mask(val: str) -> str:
        if not mask_secrets:
            return val
        return _MASKED_VALUE if val else ""

    # ── Build structured config ─────────────────────────────────
    config = {
        "corp_id": _mask(corp_id) if mask_secrets else corp_id,
        "agents": {
            "expense": {
                "agent_id": expense_agent_id,
                "secret": _mask(expense_secret),
                "source_window": "reimbursement_assistant",
                "frontend_entry": "expense",
            },
            "general": {
                "agent_id": general_agent_id,
                "secret": _mask(general_secret),
                "source_window": "general_assistant",
                "frontend_entry": "general",
            },
        },
        "callback": {
            "token": _mask(callback_token),
            "encoding_aes_key": _mask(encoding_aes_key),
        },
        "gateway": {
            "token_configured": bool(gateway_token),
        },
        "configured": {
            "corp_id": bool(corp_id),
            "expense_agent": bool(expense_agent_id),
            "general_agent": bool(general_agent_id),
            "callback_token": bool(callback_token),
            "encoding_aes_key": bool(encoding_aes_key),
        },
    }

    return config


# ══════════════════════════════════════════════════════════════════
#  Agent mapping (dynamic from config, with fallback)
# ══════════════════════════════════════════════════════════════════


def get_agent_mapping_from_config() -> dict:
    """
    Generate AgentID -> frontend_entry mapping from environment config.

    Falls back to default IDs (1000002 / 1000003) if env vars
    WECOM_AGENT_EXPENSE_ID / WECOM_AGENT_GENERAL_ID are not set.

    Returns
    -------
    dict identical to wecom_adapter.WECOM_AGENT_MAPPING structure
    """
    config = load_wecom_config(mask_secrets=False)
    agents = config["agents"]

    mapping = {}

    expense_id = agents["expense"]["agent_id"]
    if expense_id:
        mapping[expense_id] = {
            "name": "报销助手",
            "frontend_entry": "expense",
            "source_window": "reimbursement_assistant",
        }

    general_id = agents["general"]["agent_id"]
    if general_id:
        mapping[general_id] = {
            "name": "Hermes助手",
            "frontend_entry": "general",
            "source_window": "general_assistant",
        }

    return mapping
