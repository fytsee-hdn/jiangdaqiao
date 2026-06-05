"""
test_admin_command_router.py

Tests for admin_command_router.py function: classify_admin_command

A. '查看状态' → intent=inspect_status, risk=low, allowed=true
B. '查看最近日志' → intent=read_logs, risk=low, allowed=true
C. '查看 CSV' → intent=inspect_csv_summary, risk=low, allowed=true
D. '运行测试' → intent=run_tests, risk=medium, requires_confirmation=true
E. '备份数据' → intent=backup_data, risk=medium, requires_confirmation=true
F. '修改代码' → intent=write_code, risk=high
G. '删除记录' → intent=delete_data, risk=high
H. '查看 token' → intent=reveal_secret, risk=forbidden, allowed=false
I. '打印 .env' → intent=reveal_secret, risk=forbidden, allowed=false
J. classify_admin_command('修改代码', entrypoint='admin_chatbot') → allowed=false, reason mentions CLI
K. unmatched text '你好' → unknown, allowed=true
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# ── Helpers ────────────────────────────────────────────────────

_passed = 0
_failed = 0


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


# ── Import ─────────────────────────────────────────────────────

from gsp_hermes.admin.admin_command_router import classify_admin_command

# ══════════════════════════════════════════════════════════════════
heading("TEST A: '查看状态' → inspect_status, low, allowed")

r = classify_admin_command("查看状态")
check(r["intent"] == "inspect_status", "intent = 'inspect_status'")
check(r["risk_level"] == "low", "risk_level = 'low'")
check(r["allowed"] is True, "allowed = True")
check(r["requires_confirmation"] is False, "requires_confirmation = False")

# ══════════════════════════════════════════════════════════════════
heading("TEST B: '查看最近日志' → read_logs, low, allowed")

r = classify_admin_command("查看最近日志")
check(r["intent"] == "read_logs", "intent = 'read_logs'")
check(r["risk_level"] == "low", "risk_level = 'low'")
check(r["allowed"] is True, "allowed = True")
check(r["requires_confirmation"] is False, "requires_confirmation = False")

# ══════════════════════════════════════════════════════════════════
heading("TEST C: '查看 CSV' → inspect_csv_summary, low, allowed")

r = classify_admin_command("查看 CSV")
check(r["intent"] == "inspect_csv_summary", "intent = 'inspect_csv_summary'")
check(r["risk_level"] == "low", "risk_level = 'low'")
check(r["allowed"] is True, "allowed = True")
check(r["requires_confirmation"] is False, "requires_confirmation = False")

# ══════════════════════════════════════════════════════════════════
heading("TEST D: '运行测试' → run_tests, medium, requires_confirmation")

r = classify_admin_command("运行测试")
check(r["intent"] == "run_tests", "intent = 'run_tests'")
check(r["risk_level"] == "medium", "risk_level = 'medium'")
check(r["allowed"] is True, "allowed = True")
check(r["requires_confirmation"] is True, "requires_confirmation = True")

# ══════════════════════════════════════════════════════════════════
heading("TEST E: '备份数据' → backup_data, medium, requires_confirmation")

r = classify_admin_command("备份数据")
check(r["intent"] == "backup_data", "intent = 'backup_data'")
check(r["risk_level"] == "medium", "risk_level = 'medium'")
check(r["allowed"] is True, "allowed = True")
check(r["requires_confirmation"] is True, "requires_confirmation = True")

# ══════════════════════════════════════════════════════════════════
heading("TEST F: '修改代码' → write_code, high")

r = classify_admin_command("修改代码")
check(r["intent"] == "write_code", "intent = 'write_code'")
check(r["risk_level"] == "high", "risk_level = 'high'")
check(r["allowed"] is True, "allowed = True (CLI default)")
check(r["requires_confirmation"] is True, "requires_confirmation = True (high on CLI)")

# ══════════════════════════════════════════════════════════════════
heading("TEST G: '删除记录' → delete_data, high")

r = classify_admin_command("删除记录")
check(r["intent"] == "delete_data", "intent = 'delete_data'")
check(r["risk_level"] == "high", "risk_level = 'high'")
check(r["allowed"] is True, "allowed = True (CLI default)")
check(r["requires_confirmation"] is True, "requires_confirmation = True (high on CLI)")

# ══════════════════════════════════════════════════════════════════
heading("TEST H: '查看 token' → reveal_secret, forbidden, allowed=false")

r = classify_admin_command("查看 token")
check(r["intent"] == "reveal_secret", "intent = 'reveal_secret'")
check(r["risk_level"] == "forbidden", "risk_level = 'forbidden'")
check(r["allowed"] is False, "allowed = False")
check("敏感信息" in r.get("reason", ""), "reason mentions 敏感信息")

# ══════════════════════════════════════════════════════════════════
heading("TEST I: '打印 .env' → reveal_secret, forbidden, allowed=false")

r = classify_admin_command("打印 .env")
check(r["intent"] == "reveal_secret", "intent = 'reveal_secret'")
check(r["risk_level"] == "forbidden", "risk_level = 'forbidden'")
check(r["allowed"] is False, "allowed = False")

# ══════════════════════════════════════════════════════════════════
heading("TEST J: '修改代码' via admin_chatbot → disallowed, reason mentions CLI")

r = classify_admin_command("修改代码", entrypoint="admin_chatbot")
check(r["intent"] == "write_code", "intent = 'write_code'")
check(r["risk_level"] == "high", "risk_level = 'high'")
check(r["allowed"] is False, "allowed = False (high risk forbidden on chatbot)")
check("CLI" in r.get("reason", "") or "cli" in r.get("reason", "").lower(),
      f"reason mentions CLI: '{r['reason']}'")

# ══════════════════════════════════════════════════════════════════
heading("TEST K: '你好' (unmatched) → unknown, allowed")

r = classify_admin_command("你好")
check(r["intent"] == "unknown", "intent = 'unknown'")
check(r["risk_level"] == "low", "risk_level = 'low'")
check(r["allowed"] is True, "allowed = True")
check(r["requires_confirmation"] is False, "requires_confirmation = False")

# ══════════════════════════════════════════════════════════════════
heading("SUMMARY")
total = _passed + _failed
print(f"  {_passed} / {total} assertions passed")
if _failed:
    print(f"  {_failed} assertions FAILED")
