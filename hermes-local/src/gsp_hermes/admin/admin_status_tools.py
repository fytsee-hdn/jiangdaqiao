"""
Read-only status reporting tools for System Admin Agent.
These tools inspect system state without modifying anything.
All functions are fail-safe — catch all exceptions and return default values.
"""

import csv
import json
import os
import subprocess

# ---------------------------------------------------------------------------
# PATH constants — resolved relative to this file's location
# ---------------------------------------------------------------------------

_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.abspath(os.path.join(_FILE_DIR, "..", "..", ".."))

_GATEWAY_LOG = os.path.join(_PROJECT_DIR, "logs", "gateway.log")
_CSV_PATH = os.path.join(_PROJECT_DIR, "data", "expenses", "expenses.csv")
_STATE_DIR = os.path.join(_PROJECT_DIR, "data", "state")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_last_lines(path, limit):
    """Return the last *limit* lines from *path* as a list."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        return [line.rstrip("\n\r") for line in lines[-limit:]]
    except Exception:
        return []


def _truncate(text, max_chars=100):
    """Truncate *text* to *max_chars* characters."""
    if text is None:
        return ""
    text = str(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


# ---------------------------------------------------------------------------
# 1. get_bridge_process_status
# ---------------------------------------------------------------------------

def get_bridge_process_status():
    """
    Check whether relevant bridge/gateway processes are running.

    Returns
    -------
    dict
        {"running": bool, "processes": [{"pid": int, "command_summary": str}, ...]}
    """
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"running": False, "processes": []}

        keywords = ["run_weixin_bridge", "start_gateway"]
        processes = []
        for line in result.stdout.splitlines():
            line_lower = line.lower()
            if any(kw in line_lower for kw in keywords):
                parts = line.split(None, 10)
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1])
                    except (ValueError, IndexError):
                        pid = 0
                    command_summary = parts[-1] if len(parts) > 10 else " ".join(parts[2:])
                    if len(command_summary) > 120:
                        command_summary = command_summary[:120] + "..."
                    processes.append({"pid": pid, "command_summary": command_summary})

        return {"running": len(processes) > 0, "processes": processes}

    except Exception:
        return {"running": False, "processes": []}


# ---------------------------------------------------------------------------
# 2. get_gateway_log_summary
# ---------------------------------------------------------------------------

def get_gateway_log_summary(limit=20):
    """
    Read and summarise the gateway log file.

    Parameters
    ----------
    limit : int
        Number of recent entries to return.

    Returns
    -------
    dict
        {"exists": bool, "file_size_bytes": int, "total_lines": int,
         "event_counts": {...}, "recent_entries": [str, ...]}
    """
    default = {
        "exists": False,
        "file_size_bytes": 0,
        "total_lines": 0,
        "event_counts": {"request_received": 0, "response_sent": 0, "error": 0, "other": 0},
        "recent_entries": [],
    }

    try:
        if not os.path.isfile(_GATEWAY_LOG):
            return default

        file_size_bytes = os.path.getsize(_GATEWAY_LOG)

        with open(_GATEWAY_LOG, "r", encoding="utf-8", errors="replace") as fh:
            all_lines = fh.readlines()

        total_lines = len(all_lines)
        event_counts = {"request_received": 0, "response_sent": 0, "error": 0, "other": 0}

        for line in all_lines:
            lower = line.lower()
            if "error" in lower:
                event_counts["error"] += 1
            elif "request_received" in lower or "request received" in lower:
                event_counts["request_received"] += 1
            elif "response_sent" in lower or "response sent" in lower:
                event_counts["response_sent"] += 1
            else:
                event_counts["other"] += 1

        recent_raw = [_truncate(l.rstrip("\n\r"), 100) for l in all_lines[-limit:]]

        return {
            "exists": True,
            "file_size_bytes": file_size_bytes,
            "total_lines": total_lines,
            "event_counts": event_counts,
            "recent_entries": recent_raw,
        }

    except Exception:
        return default


# ---------------------------------------------------------------------------
# 3. get_expense_csv_summary
# ---------------------------------------------------------------------------

def get_expense_csv_summary(limit=5):
    """
    Read and summarise the expenses CSV file.

    Parameters
    ----------
    limit : int
        Number of recent records to return.

    Returns
    -------
    dict
        {"exists": bool, "record_count": int, "recent_records": [dict, ...]}
    """
    default = {"exists": False, "record_count": 0, "recent_records": []}

    try:
        if not os.path.isfile(_CSV_PATH):
            return default

        records = []
        with open(_CSV_PATH, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                records.append(row)

        record_count = len(records)
        recent_records = records[-limit:]

        return {
            "exists": True,
            "record_count": record_count,
            "recent_records": recent_records,
        }

    except Exception:
        return default


# ---------------------------------------------------------------------------
# 4. get_state_summary
# ---------------------------------------------------------------------------

def get_state_summary():
    """
    List and count JSON state files in the state directory.

    Returns
    -------
    dict
        {"exists": bool, "state_count": int, "state_files": [str, ...]}
    """
    default = {"exists": False, "state_count": 0, "state_files": []}

    try:
        if not os.path.isdir(_STATE_DIR):
            return default

        state_files = sorted(
            f for f in os.listdir(_STATE_DIR) if f.endswith(".json")
        )

        return {
            "exists": True,
            "state_count": len(state_files),
            "state_files": state_files,
        }

    except Exception:
        return default


# ---------------------------------------------------------------------------
# 5. get_system_status_summary
# ---------------------------------------------------------------------------

def get_system_status_summary():
    """
    Combine all status-reporting functions into a single summary dict.

    Returns
    -------
    dict
        {"bridge": {...}, "gateway_log": {...}, "csv": {...}, "state": {...}}
    """
    return {
        "bridge": get_bridge_process_status(),
        "gateway_log": get_gateway_log_summary(),
        "csv": get_expense_csv_summary(),
        "state": get_state_summary(),
    }
