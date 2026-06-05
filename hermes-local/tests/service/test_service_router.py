import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

from gsp_hermes.service.service_router import route_service_request


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


r = route_service_request("service", "dispatch_profile_task")
check(r.allowed is True and r.route == "service", "service routes service action")

for profile in ("compliance", "service", "reimbursement"):
    r = route_service_request(profile, "admin:write_code", "修改代码")
    check(r.allowed is False, f"{profile} cannot route admin action")

r = route_service_request("admin", "admin:write_code", "修改代码")
check(r.route == "admin" and r.requires_confirmation is True, "admin can route high admin action with confirmation")

r = route_service_request("reimbursement", "intake_reimbursement")
check(r.allowed is True and r.route == "reimbursement", "reimbursement routes intake")

r = route_service_request("reimbursement", "extract_evidence")
check(r.allowed is False, "reimbursement rejects compliance action")

print(f"{_passed} / {_passed + _failed} assertions passed")
if _failed:
    raise SystemExit(1)
