"""Service router for profile-scoped Hermes requests."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from gsp_hermes.admin.admin_command_router import classify_admin_command
from gsp_hermes.profiles.profile_registry import DEFAULT_PROFILE_CONFIG_DIR, ProfilePolicy, load_profile_policy

ADMIN_ACTION_PREFIXES = ("admin:", "system:")


@dataclass(frozen=True)
class ServiceRouteResult:
    profile: str
    action: str
    allowed: bool
    route: str
    reason: str
    requires_confirmation: bool = False


def _is_admin_action(action: str) -> bool:
    lowered = action.strip().lower()
    return lowered.startswith(ADMIN_ACTION_PREFIXES) or lowered in {"modify_policies", "write_code", "delete_data"}


def route_service_request(
    profile: str,
    action: str,
    command_text: str = "",
    config_dir: Path = DEFAULT_PROFILE_CONFIG_DIR,
) -> ServiceRouteResult:
    policy: ProfilePolicy = load_profile_policy(profile, config_dir)
    if _is_admin_action(action):
        if policy.profile != "admin" or not policy.admin_capabilities:
            return ServiceRouteResult(profile, action, False, "blocked", "Non-admin profile cannot route admin action")
        classified = classify_admin_command(command_text or action, entrypoint="admin_cli")
        return ServiceRouteResult(
            profile,
            action,
            bool(classified["allowed"]),
            "admin",
            str(classified["reason"]),
            bool(classified["requires_confirmation"]),
        )
    if action not in policy.allowed_actions:
        return ServiceRouteResult(profile, action, False, "blocked", "Action is not allowed for profile")
    return ServiceRouteResult(profile, action, True, policy.profile, "Action routed to profile boundary")
