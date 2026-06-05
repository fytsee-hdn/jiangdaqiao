"""OCR policy selection for shared and profile-specific extraction rules."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

HERMES_LOCAL_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TOOL_POLICY_DIR = HERMES_LOCAL_ROOT / "config" / "tool_policies"
PROFILE_TO_OCR_POLICY = {
    "compliance": "compliance_ocr_extraction",
    "reimbursement": "reimbursement_ocr_extraction",
    "admin": "shared_ocr",
    "service": "shared_ocr",
}


@dataclass(frozen=True)
class OcrPolicy:
    policy_id: str
    policy_type: str
    profile: str
    required_fields: List[str]


def _parse_simple_yaml(path: Path) -> Dict[str, object]:
    data: Dict[str, object] = {}
    current_key = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            if current_key is None:
                raise ValueError(f"List item without key in {path}")
            data.setdefault(current_key, []).append(line[4:].strip())
            continue
        if ":" not in line:
            raise ValueError(f"Unsupported policy config line in {path}: {line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        data[key] = value if value else []
    return data


def _policy_file_for(policy_id: str, policy_dir: Path) -> Path:
    return policy_dir / f"{policy_id}.yaml"


def load_ocr_policy(policy_id: str, policy_dir: Path = DEFAULT_TOOL_POLICY_DIR) -> OcrPolicy:
    path = _policy_file_for(policy_id, policy_dir)
    if not path.exists():
        raise FileNotFoundError(f"OCR policy not found: {policy_id}")
    data = _parse_simple_yaml(path)
    return OcrPolicy(
        policy_id=str(data.get("policy_id", policy_id)),
        policy_type=str(data.get("policy_type", "")),
        profile=str(data.get("profile", "shared")),
        required_fields=[str(item) for item in data.get("required_fields", [])],
    )


def select_ocr_policy_for_profile(profile: str, policy_dir: Path = DEFAULT_TOOL_POLICY_DIR) -> OcrPolicy:
    policy_id = PROFILE_TO_OCR_POLICY.get(profile)
    if policy_id is None:
        raise ValueError(f"No OCR policy mapped for profile: {profile}")
    return load_ocr_policy(policy_id, policy_dir)
