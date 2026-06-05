#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from gsp_hermes.core.skill_policy import can_load_skill, can_promote_skill, validate_skill_manifest

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

accepted = {
    "scope": "profile",
    "profile": "compliance",
    "status": "accepted",
    "allowed_profiles": ["compliance"],
    "source_agent": "compliance.iway_import",
    "contains_sensitive_data": False,
    "approved_by": "human_owner",
}

check(validate_skill_manifest(accepted)["valid"] is True, "accepted manifest valid")
check(can_load_skill(accepted, "compliance")["allowed"] is True, "matching profile can load accepted skill")
check(can_load_skill(accepted, "finance")["allowed"] is False, "cross-profile skill denied")

candidate = dict(accepted, status="candidate")
check(can_load_skill(candidate, "compliance")["allowed"] is False, "candidate skill not loadable")

missing = {"status": "accepted"}
check(validate_skill_manifest(missing)["valid"] is False, "missing manifest fields invalid")
check(can_load_skill(missing, "compliance")["allowed"] is False, "missing manifest denied")

sensitive = dict(accepted, contains_sensitive_data=True)
check(can_promote_skill(sensitive, "accepted", approved_by="human_owner")["allowed"] is False, "sensitive skill cannot promote")
check(can_promote_skill(candidate, "accepted", approved_by="")["allowed"] is False, "human approval required")
check(can_promote_skill(candidate, "accepted", approved_by="human_owner")["allowed"] is True, "human approval allows non-sensitive promotion")

print(f"RESULTS: {passed} passed | {failed} failed")
sys.exit(0 if failed == 0 else 1)
