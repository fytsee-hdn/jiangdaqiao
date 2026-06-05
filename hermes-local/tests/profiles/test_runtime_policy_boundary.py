import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

from gsp_hermes.profiles.profile_registry import load_profile_policy


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


with TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    source_profiles = tmp_path / "source_profiles"
    source_profiles.mkdir()
    (source_profiles / "admin.yaml").write_text("""profile: admin
purpose: accepted admin
allowed_entrypoints:
  - admin_cli
admin_capabilities: true
may_inherit_admin: false
contains_secrets: false
runtime_profile_root: .hermes/profiles/admin
default_ocr_policy: shared_ocr
allowed_actions:
  - inspect_status
""", encoding="utf-8")
    runtime_shadow = tmp_path / ".hermes" / "profiles" / "admin"
    runtime_shadow.mkdir(parents=True)
    (runtime_shadow / "profile.yaml").write_text("""profile: admin
admin_capabilities: false
""", encoding="utf-8")

    policy = load_profile_policy("admin", source_profiles)
    check(policy.admin_capabilities is True, ".hermes shadow cannot override source policy")

    only_runtime = tmp_path / ".hermes" / "profiles" / "service"
    only_runtime.mkdir(parents=True)
    (only_runtime / "profile.yaml").write_text("""profile: service
admin_capabilities: true
""", encoding="utf-8")
    try:
        load_profile_policy("service", source_profiles)
        check(False, "runtime-only service is trusted")
    except FileNotFoundError:
        check(True, "runtime-only service fails closed")

print(f"{_passed} / {_passed + _failed} assertions passed")
if _failed:
    raise SystemExit(1)
