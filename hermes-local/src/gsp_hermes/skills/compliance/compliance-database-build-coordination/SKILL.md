---
name: compliance-database-build-coordination
description: Coordinate candidate database builds and update plans through deterministic builders, manifests, and validators without LLM-generated business rows.
---

# Compliance Database Build Coordination

Use this skill when the user asks to prepare, plan, or coordinate a candidate
database build or update.

Accepted evidence:

- `artifacts/candidate/task12_output_engine_contracts.v1.json`
- `artifacts/candidate/task12_database_validation_suite.v1.json`
- `src/gsp_compliance_agent/product_workbench.py`
- `scripts/compliance_product_workbench.py`
- `src/gsp_compliance_agent/legacy_reset_database.py`
- `scripts/build_legacy_reset_database.py`

Rules:

- Require canonical source manifest, builder config, output target, and
  validator plan.
- Use deterministic builders only after approval.
- Produce build readiness checklists and candidate output manifest drafts.
- Keep build outputs candidate-only unless a separate promotion workflow writes
  the exact approved data family under
  `/Users/HY-yin/hermes-local/data/knowledge/compliance/` with source hashes,
  live manifest, approval record, and rollback plan.
- Return `BLOCKED` if the user asks to build from `.hermes` runtime workspace,
  Desktop-discovered files, or `artifacts/candidate` as if they were approved
  live sources.
- Require schema, source-fidelity, and read-from-disk QC before any
  `CANDIDATE_PASS` claim.

JSON-to-SQLite conversion pattern (legal index / large dumps):

- Use this pattern when a candidate JSON legal index is converted into a
  structured SQLite artifact for query, incremental update, or Codex review.
- When a candidate SQLite artifact already exists, use the accepted read-only
  helper
  `/Users/HY-yin/hermes-local/src/hermes/gsp_compliance_agent/runtime/candidate_sqlite_artifact_guard.py`
  to verify manifest/database consistency before summarizing it.
- Expected candidate output set: `.sqlite` database, `.sql` schema, and
  `.manifest.v1.json`. Store conversion or validation notes outside
  `hermes-local`.
- These outputs remain `CANDIDATE_ONLY_NOT_LIVE` until Codex and the approved
  promotion workflow write the exact approved data family under the live root.

SQLite write safety requirements:

- Every SQLite write script must explicitly call `conn.commit()` before closing
  the connection.
- If WAL mode may be active, force a checkpoint before close:
  `PRAGMA wal_checkpoint(TRUNCATE)`.
- After closing, re-open the database and verify the persisted state with
  `SELECT COUNT(*)` or equivalent deterministic queries for every table that the
  manifest will claim.
- Generate manifest values only from the re-opened, persisted database.
  Do not use the same in-memory list or expected counter that was used for the
  INSERT.
- Compute `db_sha256` only after all SQLite writes, commits, checkpoints, and
  read-back verification are complete. After computing `db_sha256`, do not
  modify the database in the same task.
- If any read-back count, hash, or manifest value does not match, stop with
  `FAILED` or `BLOCKED`; do not publish `CANDIDATE_PASS`.

Pitfalls discovered in JSON-to-SQLite builds:

1. **Column template consistency:** When inserting from multiple sources
   (for example B1 third-party, VBPL official, and signal queues), every INSERT
   must use the same ordered column list. Rows that lack fields get explicit
   NULL values, not a shorter value list.
2. **Nullable cross-source observation links:** If status observations can come
   from signals that have no matching document row, the link field must allow
   NULL and carry source/status evidence separately.
3. **Batch inserts for 100K+ rows:** Use deterministic batching such as
   `executemany` with a bounded batch size. Avoid holding all transformed rows
   in memory when streaming is possible.
4. **Write-then-Read-Verify checkpoint:** Any workflow that writes rows to
   SQLite and then generates manifests claiming those row counts MUST
   include this checkpoint: commit -> WAL checkpoint -> close -> re-open ->
   query persisted counts -> compare against expected -> generate manifests.
5. **Manifest/database consistency:** A manifest must be treated as stale if the database hash changes after
   it was generated.

Loading requirement:

- Before starting a candidate DB build or validation run, also load
  `compliance-validation-qc`. It contains validation-specific insertion and
  manifest-consistency checks such as the `severity=NULL` pitfall.

Forbidden:

- Accepted database write, production database update, LLM prose generated rows,
  skipped validators, or treating candidate/runtime workspace records as live
  source input.
