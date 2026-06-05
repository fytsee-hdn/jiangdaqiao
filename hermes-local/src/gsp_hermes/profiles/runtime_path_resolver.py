"""Runtime path resolver for generated Hermes profile state."""

from pathlib import Path
from typing import Dict

ALLOWED_RUNTIME_KINDS = {
    "sessions",
    "memory",
    "logs",
    "outputs",
    "cache",
    "skills",
    "state",
}

DEFAULT_RUNTIME_ROOT = Path.home() / ".hermes" / "profiles"


def resolve_profile_runtime_path(profile: str, kind: str, runtime_root: Path = DEFAULT_RUNTIME_ROOT) -> Path:
    if not profile or "/" in profile or ".." in profile:
        raise ValueError("Invalid profile name")
    if kind not in ALLOWED_RUNTIME_KINDS:
        raise ValueError(f"Unsupported runtime kind: {kind}")
    return runtime_root / profile / kind


def runtime_layout(profile: str, runtime_root: Path = DEFAULT_RUNTIME_ROOT) -> Dict[str, Path]:
    return {kind: resolve_profile_runtime_path(profile, kind, runtime_root) for kind in sorted(ALLOWED_RUNTIME_KINDS)}


def is_source_policy_path(path: Path) -> bool:
    normalized = str(path)
    return "/hermes-local/config/profiles/" in normalized
