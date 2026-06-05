"""Accepted profile registry for Hermes.

Policy is loaded only from hermes-local/config/profiles. Runtime files under
.hermes are state and cannot override accepted profile policy.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

HERMES_LOCAL_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROFILE_CONFIG_DIR = HERMES_LOCAL_ROOT / "config" / "profiles"
REQUIRED_PROFILES = ("admin", "compliance", "service", "reimbursement")


@dataclass(frozen=True)
class ProfilePolicy:
    profile: str
    purpose: str
    allowed_entrypoints: List[str]
    admin_capabilities: bool
    may_inherit_admin: bool
    contains_secrets: bool
    runtime_profile_root: str
    default_ocr_policy: str
    allowed_actions: List[str]

    @property
    def is_business_profile(self) -> bool:
        return self.profile != "admin"


def _parse_scalar(value: str):
    value = value.strip()
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value


def _parse_simple_yaml(path: Path) -> Dict[str, object]:
    data: Dict[str, object] = {}
    current_key: Optional[str] = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()
        if not line or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        if indent == 2 and stripped.startswith("- "):
            if current_key is None:
                raise ValueError(f"List item without key in {path}")
            data.setdefault(current_key, []).append(_parse_scalar(stripped[2:]))
            continue
        if indent > 0:
            continue
        if ":" not in line:
            raise ValueError(f"Unsupported profile config line in {path}: {line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value:
            data[key] = _parse_scalar(value)
        else:
            data[key] = []
    return data


def _as_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


def _require_bool(data: Dict[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Profile field {key} must be boolean")
    return value


def load_profile_policy(profile: str, config_dir: Path = DEFAULT_PROFILE_CONFIG_DIR) -> ProfilePolicy:
    path = config_dir / f"{profile}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Accepted profile policy missing for {profile}; .hermes runtime state is not trusted policy"
        )
    data = _parse_simple_yaml(path)
    actual_profile = str(data.get("profile", ""))
    if actual_profile != profile:
        raise ValueError(f"Profile file {path} declares {actual_profile!r}, expected {profile!r}")
    policy = ProfilePolicy(
        profile=actual_profile,
        purpose=str(data.get("purpose", "")),
        allowed_entrypoints=_as_list(data.get("allowed_entrypoints")),
        admin_capabilities=_require_bool(data, "admin_capabilities"),
        may_inherit_admin=_require_bool(data, "may_inherit_admin"),
        contains_secrets=_require_bool(data, "contains_secrets"),
        runtime_profile_root=str(data.get("runtime_profile_root", f".hermes/profiles/{profile}")),
        default_ocr_policy=str(data.get("default_ocr_policy", "shared_ocr")),
        allowed_actions=_as_list(data.get("allowed_actions")),
    )
    validate_profile_policy(policy)
    return policy


def validate_profile_policy(policy: ProfilePolicy) -> None:
    if policy.profile != "admin" and policy.admin_capabilities:
        raise ValueError(f"Business profile {policy.profile} cannot have admin capabilities")
    if policy.may_inherit_admin:
        raise ValueError(f"Profile {policy.profile} cannot inherit admin capabilities")
    if not policy.allowed_entrypoints:
        raise ValueError(f"Profile {policy.profile} must declare allowed entrypoints")
    if not policy.runtime_profile_root.startswith(f".hermes/profiles/{policy.profile}"):
        raise ValueError(f"Profile {policy.profile} runtime root must stay under .hermes/profiles/{policy.profile}")


def load_required_profiles(config_dir: Path = DEFAULT_PROFILE_CONFIG_DIR) -> Dict[str, ProfilePolicy]:
    return {profile: load_profile_policy(profile, config_dir) for profile in REQUIRED_PROFILES}


def can_use_admin_pipeline(profile: str, config_dir: Path = DEFAULT_PROFILE_CONFIG_DIR) -> bool:
    policy = load_profile_policy(profile, config_dir)
    return policy.profile == "admin" and policy.admin_capabilities and not policy.may_inherit_admin
