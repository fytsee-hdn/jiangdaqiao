"""Reimbursement profile boundary."""

from dataclasses import dataclass
from typing import List

from gsp_hermes.tools.ocr_policy import OcrPolicy, select_ocr_policy_for_profile

REIMBURSEMENT_PROFILE = "reimbursement"


@dataclass(frozen=True)
class ReimbursementProfileSpec:
    profile: str
    ocr_policy_id: str
    required_fields: List[str]
    production_ready: bool = False


def get_reimbursement_profile_spec() -> ReimbursementProfileSpec:
    policy: OcrPolicy = select_ocr_policy_for_profile(REIMBURSEMENT_PROFILE)
    return ReimbursementProfileSpec(
        profile=REIMBURSEMENT_PROFILE,
        ocr_policy_id=policy.policy_id,
        required_fields=policy.required_fields,
        production_ready=False,
    )


def validate_reimbursement_fields(fields: dict) -> List[str]:
    spec = get_reimbursement_profile_spec()
    return [field for field in spec.required_fields if not fields.get(field)]
