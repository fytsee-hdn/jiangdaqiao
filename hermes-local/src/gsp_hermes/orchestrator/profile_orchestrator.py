"""Profile orchestration facade."""

from pathlib import Path
from typing import Optional

from gsp_hermes.service.service_router import ServiceRouteResult, route_service_request


def dispatch_profile_action(profile: str, action: str, command_text: str = "", config_dir: Optional[Path] = None) -> ServiceRouteResult:
    if config_dir is None:
        return route_service_request(profile, action, command_text)
    return route_service_request(profile, action, command_text, config_dir=config_dir)
