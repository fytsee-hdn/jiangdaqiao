---
name: compliance-validation-qc
description: Run or summarize deterministic validation, read-from-disk QC, stale-index checks, manifest/data consistency, and failure injection using controlled statuses.
---

# Compliance Validation QC

Use this skill for schema validation, source-fidelity checks, read-from-disk QC,
stale-index checks, failure injection, manifest/data consistency, and validator
result summaries.

Accepted evidence:

- `artifacts/candidate/task12_database_validation_suite.v1.json`
- `artifacts/candidate/task12_final_verification_result.v1.json`
- `artifacts/candidate/task8_query_reliability_failure_injection_result.v1.json`
- `scripts/check_task12_database_validation_suite.py`
- `scripts/check_task12_final_verification.py`
- `scripts/check_task8_query_reliability_failure_injection.py`

Rules:

- Prefer deterministic validators and disk output.
- Return command, files read, files written, evidence path, and residual risk.
- Use only `BLOCKED`, `FAILED`, or `CANDIDATE_PASS`.
- Validation success is not live promotion. When summarizing validators for
  source, legal/customer, checklist, GSP, evidence, factory/risk, or database
  data, state whether the checked files are candidate, runtime workspace, or
  promoted live files.
- Return `BLOCKED` if the validator target is being used to justify ordinary
  real-trial business answers while `live_business_data_configured` is false.
- For SQLite validation tables such as `validation_findings`, run a pre-insert
  audit before opening the DB write connection. Every finding must have a
  non-empty string `severity`; never rely on a schema default if the INSERT
  explicitly provides a nullable value.
- After inserting validation rows, use write-then-read verification:
  `conn.commit()` -> `PRAGMA wal_checkpoint(TRUNCATE)` when WAL may be active
  -> `conn.close()` -> re-open the DB -> query the persisted row count.
- Manifest values claiming validation result counts must come from
  the re-opened persisted database, not from the in-memory findings list.
- If a manifest or final reply claims a validator result, include the
  evidence path and whether the checked artifact is candidate, runtime
  workspace, or promoted live data.

Pitfall — `severity=NULL` on insertion:

- When building findings programmatically, every finding dict or tuple MUST
  have an explicit non-empty severity string such as `INFO`, `WARNING`, or
  `FAIL`.
- If any finding has `severity=None`, the INSERT into `validation_findings`
  fails with `NOT NULL constraint failed: validation_findings.severity`.
- Pre-insert audit pattern:

```python
for i, finding in enumerate(findings):
    severity = finding.get("severity") if isinstance(finding, dict) else finding[6]
    assert isinstance(severity, str) and severity, (
        f"Finding {i} has null/missing severity"
    )
```

SQLite validation write pattern — Write-then-Read-Verify:

```python
conn.executemany(SQL, rows)
conn.commit()
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
conn.close()

conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
actual = conn.execute(
    "SELECT COUNT(*) FROM validation_findings WHERE validation_run_id=?",
    (validation_run_id,),
).fetchone()[0]
conn.close()
assert actual == expected_count
```

Forbidden:

- `APPROVED`, `COMPLIANT`, `AUDIT_PASS`, legal conclusion, chat-summary proof,
  ignoring failed validator evidence, or equating `CANDIDATE_PASS` with live
  business authority.
