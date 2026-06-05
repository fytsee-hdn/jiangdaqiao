#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SOUL = ROOT / "src/hermes/gsp_compliance_agent/prompts/soul.md"
SOURCE_PERMISSION = ROOT / "config/profiles/compliance_permission_model.v1.json"
RUNTIME_CONFIG = Path("/Users/HY-yin/.hermes/profiles/compliance/config.yaml")

passed = 0
failed = 0


def check(cond, label):
    global passed, failed
    if cond:
        print("  PASS", label)
        passed += 1
    else:
        print("  FAIL", label)
        failed += 1


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


text = SOURCE_SOUL.read_text(encoding="utf-8")
check("DRAFT — Phase C0 file skeleton" not in text, "compliance SOUL is not skeleton-only")
check("This file is a placeholder" not in text, "compliance SOUL is not placeholder-only")
check("compliance_permission_model.v1.json" in text, "SOUL points to hermes-local permission model")
check("I must not treat `.hermes` runtime files" in text, "SOUL forbids .hermes as accepted policy")
check("controlled actions are `BLOCKED` by default" in " ".join(text.split()), "SOUL declares deny-by-default user binding")

model = json.loads(SOURCE_PERMISSION.read_text(encoding="utf-8"))
check(model.get("deny_by_default") is True, "permission model denies by default")
check(model.get("role_order") == ["P0", "P1", "P2", "P3"], "permission model role order is P0-P3")
check(isinstance(model.get("wecom_account_bindings"), list), "permission model has WeCom bindings list")

config_text = RUNTIME_CONFIG.read_text(encoding="utf-8")
check(f"soul_path: {SOURCE_SOUL}" in config_text, "runtime profile loads SOUL directly from hermes-local source")
check("skills_readonly" in config_text, "runtime profile uses read-only skill toolset")
check("/Users/HY-yin/hermes-local/src/gsp_hermes/skills/compliance" in config_text, "runtime profile points to accepted skill source root")

print(f"{passed} / {passed + failed} assertions passed")
sys.exit(0 if failed == 0 else 1)
