"""
test_admin_audit_logger.py

Tests for the Admin Audit Logger (admin_audit_logger.py).

A. log_admin_action({'actor':'test','intent':'inspect_status','risk_level':'low'})
   creates admin_agent.log
B. Log entry has event_type=admin_action, actor, intent, risk_level
C. timestamp has +07:00 timezone
D. token field in data dict is [REDACTED]
E. secret field redacted
F. api_key field redacted
G. password field redacted
H. read_admin_log(limit=5) returns entries
I. clear_admin_log() works
"""

import json
import os
import sys
import tempfile

os.environ["HERMES_ADMIN_LOG_PATH"] = os.path.join(
    tempfile.gettempdir(), "hermes_admin_audit_logger_test.jsonl"
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

_passed = 0
_failed = 0
_skipped = 0


def heading(title: str) -> None:
    width = 64
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print('=' * width)


def check(cond: bool, label: str) -> None:
    global _passed, _failed
    if cond:
        print(f"  ✅ {label}")
        _passed += 1
    else:
        print(f"  ❌ {label}")
        _failed += 1


def skip(label: str) -> None:
    global _skipped
    print(f"  ⏭️  {label}")
    _skipped += 1


from gsp_hermes.admin.admin_audit_logger import (
    log_admin_action,
    clear_admin_log,
    read_admin_log,
)

# ══════════════════════════════════════════════════════════════════
heading("TEST A: log_admin_action creates admin_agent.log")

clear_admin_log()

# Simple action with no 'data' field
log_admin_action({
    "actor": "test",
    "intent": "inspect_status",
    "risk_level": "low",
})

from gsp_hermes.admin.admin_audit_logger import _ensure_log_path
log_path = _ensure_log_path()

check(os.path.isfile(log_path), "admin_agent.log exists after log_admin_action")

# ══════════════════════════════════════════════════════════════════
heading("TEST B: Log entry has event_type, actor, intent, risk_level")

entries = read_admin_log(limit=5)
entry = entries[0] if entries else {}

check("event_type" in entry, "event_type key present")
check(entry.get("event_type") == "admin_action", "event_type = admin_action")
check(entry.get("actor") == "test", "actor = test")
check(entry.get("intent") == "inspect_status", "intent = inspect_status")
check(entry.get("risk_level") == "low", "risk_level = low")

# ══════════════════════════════════════════════════════════════════
heading("TEST C: timestamp has +07:00 timezone")

ts = entry.get("timestamp", "")
check(ts.endswith("+07:00"), f"timestamp ends with +07:00 (got: {ts[-6:] if len(ts) >= 6 else ts})")

# ══════════════════════════════════════════════════════════════════
heading("TEST D-G: Sensitive field redaction in data dict")

# Write a new entry with sensitive fields inside the data dict
clear_admin_log()

log_admin_action({
    "actor": "test_redact",
    "intent": "check_redaction",
    "risk_level": "high",
    "data": {
        "token": "sk-abc123",
        "secret": "my-secret-value",
        "api_key": "key-9876",
        "password": "p@ssw0rd",
        "safe_field": "this should stay",
        "raw_text": "请打印 .env",
    },
})

entries = read_admin_log(limit=5)
entry = entries[0] if entries else {}
data = entry.get("data", {})

check(data.get("token") == "[REDACTED]", "token field is [REDACTED]")
check(data.get("secret") == "[REDACTED]", "secret field is [REDACTED]")
check(data.get("api_key") == "[REDACTED]", "api_key field is [REDACTED]")
check(data.get("password") == "[REDACTED]", "password field is [REDACTED]")
check(data.get("safe_field") == "this should stay", "safe_field is not redacted")
check(data.get("raw_text") == "[REDACTED]", "raw_text with .env is [REDACTED]")

# ══════════════════════════════════════════════════════════════════
heading("TEST H: read_admin_log(limit=5) returns entries")

# We just logged 1 entry, let's add 3 more so limit logic is exercised
for i in range(3):
    log_admin_action({
        "actor": "multi",
        "intent": f"test_{i}",
        "risk_level": "low",
    })

results = read_admin_log(limit=5)
check(len(results) >= 1, f"read_admin_log returned {len(results)} entries (expected >= 1)")
# We should have 4 entries total: 1 redact test + 3 multi entries
check(len(results) == 4, f"read_admin_log returned {len(results)} entries (expected 4)")

# ══════════════════════════════════════════════════════════════════
heading("TEST I: clear_admin_log() works")

clear_admin_log()
check(not os.path.isfile(log_path), "admin_agent.log deleted after clear_admin_log()")
empty = read_admin_log(limit=5)
check(len(empty) == 0, "read_admin_log returns [] after clear")

# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════
total = _passed + _failed + _skipped
print(f"\n{'=' * 64}")
print(f"  Results: {_passed} passed, {_failed} failed, {_skipped} skipped / {total} total")
print('=' * 64)

if _failed:
    sys.exit(1)
