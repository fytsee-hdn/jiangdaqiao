"""
test_admin_chatbot_adapter.py

Tests for admin_chatbot_adapter.py function: handle_admin_chatbot_message

A. ADMIN_ALLOWED_USERS not set → authorized=false, reply contains '仅限系统管理员'
B. Set ADMIN_ALLOWED_USERS=owner123, user_id=owner123, content='查看状态'
   → authorized=true, success=true
C. user_id not in allowlist → unauthorized
D. authorized user sends '查看 token' → forbidden, reply doesn't contain token/key
E. '备份数据' → requires_confirmation or suggests backup, not direct execution
F. '修改代码' → rejected or suggests CLI
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

from gsp_hermes.admin.admin_chatbot_adapter import handle_admin_chatbot_message

# ══════════════════════════════════════════════════════════════════
heading("TEST A: ADMIN_ALLOWED_USERS not set → unauthorized, reply mentions admin-only")

# Ensure env var is not set
if "ADMIN_ALLOWED_USERS" in os.environ:
    del os.environ["ADMIN_ALLOWED_USERS"]

r = handle_admin_chatbot_message({"user_id": "owner", "content": "status"})
check(r["authorized"] is False, "authorized = False")
check("仅限系统管理员" in r["reply_text"], "reply contains '仅限系统管理员'")
check(r["success"] is False, "success = False")

# ══════════════════════════════════════════════════════════════════
heading("TEST B: ADMIN_ALLOWED_USERS=owner123, user_id=owner123, '查看状态' → authorized, success")

os.environ["ADMIN_ALLOWED_USERS"] = "owner123"

r = handle_admin_chatbot_message({"user_id": "owner123", "content": "查看状态"})
check(r["authorized"] is True, "authorized = True")
check(r["success"] is True, "success = True")
check("状态" in r["reply_text"] or "总览" in r["reply_text"],
      "reply mentions system status")

# ══════════════════════════════════════════════════════════════════
heading("TEST C: user_id not in allowlist → unauthorized")

# ADMIN_ALLOWED_USERS still = 'owner123'
r = handle_admin_chatbot_message({"user_id": "some_random_user", "content": "查看状态"})
check(r["authorized"] is False, "authorized = False")
check(r["success"] is False, "success = False")
check("仅限系统管理员" in r["reply_text"], "reply contains '仅限系统管理员'")

# ══════════════════════════════════════════════════════════════════
heading("TEST D: authorized user sends '查看 token' → forbidden, reply doesn't leak token/key")

r = handle_admin_chatbot_message({"user_id": "owner123", "content": "查看 token"})
check(r["authorized"] is True, "authorized = True (user is in allowlist)")
check(r["success"] is False, "success = False (forbidden intent)")
check(r["intent"] == "reveal_secret", "intent = 'reveal_secret'")
check(r["risk_level"] == "forbidden", "risk_level = 'forbidden'")
# Ensure the reply does NOT contain actual token or key values
reply_lower = r["reply_text"].lower()
check("token" not in reply_lower or "敏感" in r["reply_text"],
      "reply does not leak token/key (may mention '敏感')")
check(len(r["reply_text"]) > 0, "reply is non-empty")

# ══════════════════════════════════════════════════════════════════
heading("TEST E: '备份数据' → requires_confirmation, suggests confirmation")

r = handle_admin_chatbot_message({"user_id": "owner123", "content": "备份数据"})
check(r["authorized"] is True, "authorized = True")
check(r["success"] is True, "success = True (requires confirmation)")
check(r["requires_confirmation"] is True, "requires_confirmation = True")
check("确认" in r["reply_text"], "reply asks for confirmation (contains '确认')")
# Must not execute backup directly — the reply must be a confirmation prompt,
# not actual backup output
check("备份" in r["reply_text"], "reply mentions backup")
check("yes" in r["reply_text"].lower() or "确认" in r["reply_text"],
      "reply mentions 'yes' or '确认'")

# ══════════════════════════════════════════════════════════════════
heading("TEST F: '修改代码' → rejected (forbidden on chatbot), suggests CLI")

r = handle_admin_chatbot_message({"user_id": "owner123", "content": "修改代码"})
check(r["authorized"] is True, "authorized = True")
check(r["success"] is False, "success = False (rejected)")
check(r["intent"] == "write_code", "intent = 'write_code'")
check(r["risk_level"] == "high", "risk_level = 'high'")
check("CLI" in r["reply_text"] or "cli" in r["reply_text"].lower()
      or "终端" in r["reply_text"],
      "reply suggests CLI")


# ══════════════════════════════════════════════════════════════════
heading("TEST G: authorized user with business profile is denied admin chatbot")

os.environ["ADMIN_ALLOWED_USERS"] = "owner123"
r = handle_admin_chatbot_message({"user_id": "owner123", "profile": "compliance", "content": "查看状态"})
check(r["authorized"] is True, "authorized = True")
check(r["success"] is False, "success = False for business profile")
check(r["intent"] == "profile_gate", "intent = profile_gate")
check("admin profile" in r["reply_text"], "reply mentions admin profile")

# ══════════════════════════════════════════════════════════════════
# Cleanup
heading("CLEANUP")

if "ADMIN_ALLOWED_USERS" in os.environ:
    del os.environ["ADMIN_ALLOWED_USERS"]
    print("  ✅ os.environ['ADMIN_ALLOWED_USERS'] cleaned up")
else:
    print("  ℹ️  ADMIN_ALLOWED_USERS already clean (Test A kept it clear)")

# ══════════════════════════════════════════════════════════════════
heading("SUMMARY")

total = _passed + _failed
print(f"  {_passed} / {total} assertions passed")
if _failed:
    print(f"  {_failed} assertions FAILED")
