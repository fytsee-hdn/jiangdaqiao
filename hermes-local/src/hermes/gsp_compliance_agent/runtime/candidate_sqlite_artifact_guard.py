"""Read-only guard for candidate SQLite artifact packages.

This module is accepted Hermes source. It verifies that a candidate SQLite
database and manifest agree with the persisted database on disk. It does not write to the database or to live compliance data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path


class CandidateArtifactError(RuntimeError):
    """Raised when a candidate artifact package is inconsistent."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    if not isinstance(manifest, dict):
        raise CandidateArtifactError(f"Manifest must be a JSON object: {path}")
    return manifest


def _resolve(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else base / path


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise CandidateArtifactError(f"Unsafe table name in manifest: {table!r}")
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def verify_candidate_sqlite_artifact(artifact_dir: Path) -> dict:
    """Verify one candidate SQLite artifact directory.

    Returns a summary dict on success. Raises CandidateArtifactError on any
    mismatch. The database is opened with SQLite `mode=ro`.
    """

    manifests = sorted(artifact_dir.glob("*.manifest.v*.json"))
    if len(manifests) != 1:
        raise CandidateArtifactError(
            f"Expected exactly one *.manifest.v*.json in {artifact_dir}, found {len(manifests)}"
        )
    manifest_path = manifests[0]
    manifest = _load_manifest(manifest_path)

    db_path = _resolve(artifact_dir, manifest.get("db_path"))
    if db_path is None:
        sqlite_files = sorted(artifact_dir.glob("*.sqlite"))
        if len(sqlite_files) != 1:
            raise CandidateArtifactError("Manifest has no db_path and directory does not contain exactly one .sqlite")
        db_path = sqlite_files[0]
    if not db_path.exists():
        raise CandidateArtifactError(f"Database does not exist: {db_path}")

    actual_hash = _sha256(db_path)
    if manifest.get("db_sha256") != actual_hash:
        raise CandidateArtifactError(
            f"Manifest db_sha256 mismatch: manifest={manifest.get('db_sha256')} actual={actual_hash}"
        )

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        table_counts = manifest.get("tables") or {}
        if not isinstance(table_counts, dict) or not table_counts:
            raise CandidateArtifactError("Manifest must contain a non-empty tables object")
        actual_counts = {}
        for table, expected in sorted(table_counts.items()):
            actual = _table_count(conn, table)
            actual_counts[table] = actual
            if actual != expected:
                raise CandidateArtifactError(
                    f"Table count mismatch for {table}: manifest={expected} actual={actual}"
                )

        validation_count = actual_counts.get("validation_findings")
        summary = manifest.get("validation_summary") or {}
        if validation_count is not None and isinstance(summary, dict) and "total_checks" in summary:
            if int(summary["total_checks"]) != validation_count:
                raise CandidateArtifactError(
                    "validation_summary.total_checks mismatch: "
                    f"summary={summary['total_checks']} actual={validation_count}"
                )
    finally:
        conn.close()

    return {
        "status": "PASS",
        "artifact_dir": str(artifact_dir),
        "manifest": str(manifest_path),
        "db_path": str(db_path),
        "db_sha256": actual_hash,
        "tables": actual_counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify candidate SQLite manifest consistency.")
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    try:
        result = verify_candidate_sqlite_artifact(args.artifact_dir)
    except CandidateArtifactError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
