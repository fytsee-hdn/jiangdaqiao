import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

from gsp_hermes.profiles.profile_registry import can_use_admin_pipeline, load_profile_policy, load_required_profiles
from gsp_hermes.profiles.runtime_path_resolver import resolve_profile_runtime_path, runtime_layout


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


profiles = load_required_profiles()
check(set(profiles) == {"admin", "compliance", "service", "reimbursement"}, "required profiles load")
check(can_use_admin_pipeline("admin") is True, "admin can use admin pipeline")
for name in ("compliance", "service", "reimbursement"):
    policy = load_profile_policy(name)
    check(policy.admin_capabilities is False, f"{name} has no admin capability")
    check(policy.may_inherit_admin is False, f"{name} cannot inherit admin")
    check(can_use_admin_pipeline(name) is False, f"{name} cannot use admin pipeline")

runtime_path = resolve_profile_runtime_path("reimbursement", "skills")
check(str(runtime_path).endswith(".hermes/profiles/reimbursement/skills"), "runtime skills path uses .hermes")
layout = runtime_layout("service")
check("sessions" in layout and "logs" in layout and "skills" in layout, "runtime layout includes state kinds")

try:
    load_profile_policy("shadow_only_runtime_profile")
    check(False, "shadow runtime-only profile rejected")
except FileNotFoundError:
    check(True, "shadow runtime-only profile rejected")

print(f"{_passed} / {_passed + _failed} assertions passed")
if _failed:
    raise SystemExit(1)
