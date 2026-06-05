#!/usr/bin/env python3
"""Independent live read-back QC for GSP Compliance Core Database v1."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


LIVE_ROOT = Path("/Users/HY-yin/hermes-local/data/knowledge/compliance")
CATALOG = LIVE_ROOT / "knowledge_base_catalog.v1.json"
CATALOG_MD = LIVE_ROOT / "knowledge_base_catalog.v1.md"
LIVE_MANIFEST = LIVE_ROOT / "live_manifest.json"

EXPECTED_SHEETS = {"Summary", "Compliance_Atoms", "Atom_Area_Applicability", "Atom_IWAY_Crosswalk", "QC_Report"}


def main() -> int:
    findings: list[dict[str, str]] = []

    def add(gate: str, ok: bool, message: str) -> None:
        findings.append({"gate_id": gate, "status": "PASS" if ok else "NEEDS_FIX", "message": message})

    required = [CATALOG, CATALOG_MD, LIVE_MANIFEST]
    missing = [str(path) for path in required if not path.exists()]
    add("LIVE_GSP_CORE_00", not missing, f"missing={missing}")
    if missing:
        return finish(findings)

    catalog = load(CATALOG)
    live = load(LIVE_MANIFEST)
    entry_id = str(catalog.get("default_core_database_entry_id") or "")
    entry = catalog.get("gsp_compliance_core_database_v1") if isinstance(catalog.get("gsp_compliance_core_database_v1"), dict) else {}
    db_path = Path(str(entry.get("live_path") or ""))
    manifest_path = Path(str(entry.get("manifest_path") or ""))
    source_manifest_path = Path(str(entry.get("source_manifest_path") or ""))
    required_live = [db_path, manifest_path, source_manifest_path]
    missing_live = [str(path) for path in required_live if not str(path) or not path.exists()]
    add("LIVE_GSP_CORE_01", not missing_live, f"missing_live={missing_live}")
    if missing_live:
        return finish(findings)

    manifest = load(manifest_path)
    source_manifest = load(source_manifest_path)
    manifest_entry_id = str(manifest.get("knowledge_entry_id") or "")
    source_entry_id = str(source_manifest.get("knowledge_entry_id") or "")
    add("LIVE_GSP_CORE_02", manifest_entry_id == entry_id, f"manifest_entry={manifest_entry_id}, catalog_default={entry_id}")
    add("LIVE_GSP_CORE_03", source_entry_id == entry_id, f"source_manifest_entry={source_entry_id}, catalog_default={entry_id}")
    add("LIVE_GSP_CORE_04", live.get("default_core_database_entry_id") == entry_id, f"live_default={live.get('default_core_database_entry_id')}")

    db_hash = sha256(db_path)
    expected_db_hashes = {
        value
        for value in [
            manifest.get("db_sha256"),
            manifest.get("sha256"),
            source_manifest.get("db_sha256"),
            source_manifest.get("sha256"),
            entry.get("sha256"),
        ]
        if value
    }
    add("LIVE_GSP_CORE_05", bool(expected_db_hashes) and expected_db_hashes == {db_hash}, f"db_hash={db_hash}, expected={sorted(expected_db_hashes)}")

    xlsx_value = entry.get("xlsx_path") or manifest.get("xlsx_path") or source_manifest.get("xlsx_path")
    xlsx_path = Path(str(xlsx_value)) if xlsx_value else None
    if xlsx_path and xlsx_path.exists():
        xlsx_hash = sha256(xlsx_path)
        expected_xlsx_hashes = {
            value
            for value in [manifest.get("xlsx_sha256"), source_manifest.get("xlsx_sha256"), entry.get("xlsx_sha256")]
            if value
        }
        add("LIVE_GSP_CORE_06", not expected_xlsx_hashes or expected_xlsx_hashes == {xlsx_hash}, f"xlsx_hash={xlsx_hash}, expected={sorted(expected_xlsx_hashes)}")
    else:
        add("LIVE_GSP_CORE_06", True, "xlsx artifact is not configured for current default core DB")

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        add("LIVE_GSP_CORE_07", integrity == "ok", f"sqlite_integrity={integrity}")
        expected_counts = expected_int_counts(manifest, source_manifest, entry)
        counts = {}
        missing_count_objects = []
        for name in expected_counts:
            if not sqlite_object_exists(conn, name):
                missing_count_objects.append(name)
                continue
            counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        add(
            "LIVE_GSP_CORE_08",
            not missing_count_objects and counts == expected_counts,
            f"counts={counts}, expected={expected_counts}, missing_objects={missing_count_objects}",
        )
        orphan_legal = conn.execute(
            """
            SELECT COUNT(*)
              FROM legal_mapping l
             WHERE NOT EXISTS (
                   SELECT 1 FROM compliance_atom_master a
                    WHERE a.atom_id = l.atom_id
             )
            """
        ).fetchone()[0]
        missing_area = conn.execute(
            """
            SELECT COUNT(*)
              FROM compliance_atom_master a
             WHERE NOT EXISTS (
                   SELECT 1 FROM atom_factory_area_applicability_map m
                    WHERE m.atom_id = a.atom_id
             )
            """
        ).fetchone()[0]
        add("LIVE_GSP_CORE_09", orphan_legal == 0 and missing_area == 0, f"orphan_legal={orphan_legal}, missing_area={missing_area}")
        false_approval = conn.execute(
            """
            SELECT COUNT(*) FROM compliance_atom_master
             WHERE atom_status LIKE 'APPROVED%'
            """
        ).fetchone()[0]
        false_approval += conn.execute(
            """
            SELECT COUNT(*) FROM legal_mapping
             WHERE legal_mapping_status LIKE 'APPROVED%'
            """
        ).fetchone()[0]
        add("LIVE_GSP_CORE_10", false_approval == 0, f"false_approval={false_approval}")

    if xlsx_path and xlsx_path.exists():
        sheets = read_xlsx_sheets(xlsx_path)
        add("LIVE_GSP_CORE_11", EXPECTED_SHEETS.issubset(sheets), f"xlsx_sheets={sorted(sheets)}")
    else:
        add("LIVE_GSP_CORE_11", True, "xlsx artifact is not configured for current default core DB")
    md_text = CATALOG_MD.read_text(encoding="utf-8")
    add("LIVE_GSP_CORE_12", entry_id in md_text and "GSP Compliance Core Database v1" in md_text, "catalog markdown contains core database section")
    guardrails = manifest.get("guardrails", {})
    guard_ok = (
        guardrails.get("not_confirmed_factory_baseline") is True
        and guardrails.get("not_final_legal_opinion") is True
        and guardrails.get("not_checklist") is True
        and guardrails.get("not_audit_pass") is True
    )
    add("LIVE_GSP_CORE_13", guard_ok, f"guardrails_ok={guard_ok}")
    return finish(findings)


def finish(findings: list[dict[str, str]]) -> int:
    overall = "PASS" if all(row["status"] == "PASS" for row in findings) else "NEEDS_FIX"
    print(json.dumps({"overall_status": overall, "findings": findings}, ensure_ascii=False, indent=2))
    return 0 if overall == "PASS" else 1


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_int_counts(*sources: dict) -> dict[str, int]:
    for source in sources:
        counts = None
        if isinstance(source, dict):
            counts = source.get("candidate_counts") or source.get("counts")
        if isinstance(counts, dict):
            parsed = {
                str(key): int(value)
                for key, value in counts.items()
                if isinstance(value, int) and not isinstance(value, bool)
            }
            if parsed:
                return parsed
    return {}


def sqlite_object_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name=? AND type IN ('table', 'view')",
        (name,),
    ).fetchone()
    return row is not None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_xlsx_sheets(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("xl/workbook.xml"))
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return {node.attrib["name"] for node in root.findall(".//main:sheet", ns)}


if __name__ == "__main__":
    raise SystemExit(main())
