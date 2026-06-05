"""
test_admin_runner.py

Tests for admin_runner.py function: run_admin_command

A. run_admin_command('查看状态', entrypoint='admin_cli') → success=true, reply contains system info (bridge/CSV/state/log)
B. run_admin_command('查看 CSV') → success=true, reply contains CSV info
C. run_admin_command('备份数据') → success=true, reply contains confirmation like 请确认 or 确认执行
D. run_admin_command('删除记录') → success=true, reply mentions 确认
E. run_admin_command('查看 token') → success=false, reply mentions 拒绝 or 敏感
F. run_admin_command('') → handled gracefully (success or has reply_text)
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

from gsp_hermes.admin.admin_runner import run_admin_command

# ══════════════════════════════════════════════════════════════════
heading("TEST A: '查看状态' via admin_cli → success=true, reply has system info")

r = run_admin_command("查看状态", entrypoint="admin_cli")

check(r.get("success") is True, "success = True")
check(isinstance(r.get("reply_text"), str), "reply_text is a string")
check(len(r.get("reply_text", "")) > 0, "reply_text is non-empty")
# Reply should mention bridge, CSV, state, or log status
reply_a = r.get("reply_text", "")
check("Bridge" in reply_a or "bridge" in reply_a or "CSV" in reply_a or "csv" in reply_a,
      "reply mentions Bridge or CSV status")
check("会话" in reply_a or "state" in reply_a or "State" in reply_a,
      "reply mentions conversation/state info")
check("日志" in reply_a or "log" in reply_a or "Log" in reply_a or "Gateway" in reply_a,
      "reply mentions log or Gateway")
check(r.get("intent") == "inspect_status", "intent = 'inspect_status'")
check(r.get("risk_level") == "low", "risk_level = 'low'")

# ══════════════════════════════════════════════════════════════════
heading("TEST B: '查看 CSV' → success=true, reply contains CSV info")

r = run_admin_command("查看 CSV")

check(r.get("success") is True, "success = True")
reply_b = r.get("reply_text", "")
check("CSV" in reply_b or "csv" in reply_b or "报销" in reply_b or "记录" in reply_b,
      "reply mentions CSV or 报销 or 记录")
check(r.get("intent") == "inspect_csv_summary", "intent = 'inspect_csv_summary'")
check(r.get("risk_level") == "low", "risk_level = 'low'")

# ══════════════════════════════════════════════════════════════════
heading("TEST C: '备份数据' → success=true, reply contains 请确认 or 确认执行")

r = run_admin_command("备份数据")

check(r.get("success") is True, "success = True")
reply_c = r.get("reply_text", "")
check("请确认" in reply_c or "确认执行" in reply_c,
      f"reply contains confirmation phrase: '{reply_c}'")
check(r.get("requires_confirmation") is True, "requires_confirmation = True")
check(r.get("intent") == "backup_data", "intent = 'backup_data'")
check(r.get("risk_level") == "medium", "risk_level = 'medium'")

# ══════════════════════════════════════════════════════════════════
heading("TEST D: '删除记录' → success=true, reply mentions 确认")

r = run_admin_command("删除记录")

check(r.get("success") is True, "success = True")
reply_d = r.get("reply_text", "")
check("确认" in reply_d,
      f"reply mentions 确认: '{reply_d}'")
check(r.get("requires_confirmation") is True, "requires_confirmation = True")
check(r.get("intent") == "delete_data", "intent = 'delete_data'")
check(r.get("risk_level") == "high", "risk_level = 'high'")

# ══════════════════════════════════════════════════════════════════
heading("TEST E: '查看 token' → success=false, reply mentions 拒绝 or 敏感")

r = run_admin_command("查看 token")

check(r.get("success") is False, "success = False")
reply_e = r.get("reply_text", "")
check("拒绝" in reply_e or "敏感" in reply_e or "始终不" in reply_e,
      f"reply mentions denial: '{reply_e}'")
check(r.get("intent") == "reveal_secret", "intent = 'reveal_secret'")
check(r.get("risk_level") == "forbidden", "risk_level = 'forbidden'")

# ══════════════════════════════════════════════════════════════════
heading("TEST F: run_admin_command('') → handled gracefully")

r = run_admin_command("")

# The function should not crash — either success=true or at least has a reply_text
check("success" in r, "result has 'success' key")
check(isinstance(r.get("reply_text"), str), "reply_text is a string")
check(len(r.get("reply_text", "")) > 0, "reply_text is non-empty (graceful handling)")


# ══════════════════════════════════════════════════════════════════
heading("TEST G: business profile cannot execute admin pipeline")

r = run_admin_command("查看状态", profile="compliance")
check(r.get("success") is False, "success = False for compliance profile")
check(r.get("reason") == "profile_not_allowed", "reason = profile_not_allowed")
check("admin profile" in r.get("reply_text", ""), "reply mentions admin profile")

# ══════════════════════════════════════════════════════════════════
heading("SUMMARY")
total = _passed + _failed
print(f"  {_passed} / {total} assertions passed")
if _failed:
    print(f"  {_failed} assertions FAILED")
