#!/usr/bin/env python3
"""Expire active Hermes compliance sessions so gateway reloads current runtime rules."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


SESSIONS_INDEX = Path("/Users/HY-yin/.hermes/profiles/compliance/sessions/sessions.json")
BACKUP_DIR = Path("/Users/HY-yin/hermes-local/data/knowledge/compliance/rollback/runtime_session_refresh/gsp_core_database_live_policy")


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"sessions.{now.replace(':', '').replace('+', 'Z')}.json"
    shutil.copy2(SESSIONS_INDEX, backup)

    data = json.loads(SESSIONS_INDEX.read_text(encoding="utf-8"))
    expired = []
    for key, row in data.items():
        if not isinstance(row, dict):
            continue
        if row.get("suspended") is True and row.get("expiry_finalized") is True:
            continue
        row["suspended"] = True
        row["expiry_finalized"] = True
        row["resume_pending"] = False
        row["resume_reason"] = "runtime session refresh after GSP core database live policy update"
        row["last_resume_marked_at"] = now
        row["cleaned_at"] = now
        expired.append(key)

    SESSIONS_INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "backup": str(backup), "expired_sessions": expired}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
