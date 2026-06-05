import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

from gsp_hermes.reimbursement.reimbursement_profile import get_reimbursement_profile_spec, validate_reimbursement_fields
from gsp_hermes.tools.ocr_policy import select_ocr_policy_for_profile


_passed = 0
_failed = 0


def check(cond, label):
    global _passed, _failed
    if cond:
        print(f"  PASS {label}")
        _passed += 1
    else:
        print(f"  FAIL {label}")
        _failed += 1


compliance_policy = select_ocr_policy_for_profile("compliance")
reimbursement_policy = select_ocr_policy_for_profile("reimbursement")
check(compliance_policy.policy_id == "compliance_ocr_extraction", "compliance selects compliance OCR policy")
check(reimbursement_policy.policy_id == "reimbursement_ocr_extraction", "reimbursement selects reimbursement OCR policy")
check("clause" in compliance_policy.required_fields, "compliance OCR requires clause")
check("invoice_number" in reimbursement_policy.required_fields, "reimbursement OCR requires invoice_number")
check("expense_category" in reimbursement_policy.required_fields, "reimbursement OCR requires expense_category")

spec = get_reimbursement_profile_spec()
check(spec.profile == "reimbursement", "reimbursement spec profile")
check(spec.production_ready is False, "reimbursement spec is not production-ready")
missing = validate_reimbursement_fields({"invoice_number": "INV-1", "amount": "10"})
check("vendor" in missing and "currency" in missing, "missing reimbursement fields are reported")

print(f"{_passed} / {_passed + _failed} assertions passed")
if _failed:
    raise SystemExit(1)
