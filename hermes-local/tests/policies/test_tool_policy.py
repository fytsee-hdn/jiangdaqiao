#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from gsp_hermes.core.tool_policy import build_ocr_cache_key, validate_ocr_policy_binding

passed = 0
failed = 0

def check(cond, label):
    global passed, failed
    if cond:
        print("PASS |", label)
        passed += 1
    else:
        print("FAIL |", label)
        failed += 1

shared = {"tool_id": "shared_ocr", "tool_type": "ocr_engine"}
compliance = {
    "policy_id": "compliance_ocr_extraction",
    "policy_type": "ocr_extraction",
    "profile": "compliance",
    "required_fields": ["clause", "source", "page"],
}
finance = dict(compliance, policy_id="finance_ocr_extraction", profile="finance", required_fields=["invoice_number", "amount"])

check(validate_ocr_policy_binding(shared, compliance, "compliance")["valid"] is True, "compliance OCR policy binds to compliance")
check(validate_ocr_policy_binding(shared, compliance, "finance")["valid"] is False, "compliance OCR policy rejected for finance")
check(validate_ocr_policy_binding(shared, finance, "finance")["valid"] is True, "finance OCR policy binds to finance")
key = build_ocr_cache_key("finance", "abc", "shared_ocr", "1", "finance_ocr_extraction")
check("finance" in key and "finance_ocr_extraction" in key, "OCR cache key includes profile and policy")

print(f"RESULTS: {passed} passed | {failed} failed")
sys.exit(0 if failed == 0 else 1)
