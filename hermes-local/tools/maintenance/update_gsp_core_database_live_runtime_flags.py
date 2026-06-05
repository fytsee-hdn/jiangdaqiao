#!/usr/bin/env python3
"""Synchronize Hermes runtime flags with the live GSP core database."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


CATALOG = Path("/Users/HY-yin/hermes-local/data/knowledge/compliance/knowledge_base_catalog.v1.json")
CAPABILITY = Path("/Users/HY-yin/hermes-local/config/profiles/compliance_capability_map.v1.json")
ACCEPTED_SOUL = Path("/Users/HY-yin/hermes-local/src/hermes/gsp_compliance_agent/prompts/soul.md")
CATALOG_RESOLUTION_NOTE = "Resolve the current default core database from the live knowledge-base catalog at query time."
SOUL_NO_HARDCODE_SENTENCE = "Do not use a hard-coded core database version from prompt text, memory, SOUL, or session history."


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def current_core() -> tuple[str, str, str]:
    catalog = load(CATALOG)
    core_id = catalog.get("default_core_database_entry_id")
    entry = catalog.get("gsp_compliance_core_database_v1") or {}
    core_path = entry.get("live_path")
    core_manifest = entry.get("manifest_path")
    if not core_id or not core_path or not core_manifest:
        raise SystemExit("live catalog does not expose default core database entry/path/manifest")
    if not Path(core_path).exists():
        raise SystemExit(f"core db missing: {core_path}")
    if not Path(core_manifest).exists():
        raise SystemExit(f"core manifest missing: {core_manifest}")
    return str(core_id), str(core_path), str(core_manifest)


def update_catalog(core_id: str) -> None:
    data = load(CATALOG)
    data["blocked_until_separate_promotion"] = [
        "legal advice",
        "compliance conclusions",
        "audit-pass claims",
    ]
    data["live_requirement_atom_policy"] = {
        "status": "LIVE_ALLOWED_FOR_PROMOTED_GSP_CORE_DATABASE",
        "default_core_database_entry_id": core_id,
        "allowed_scope": [
            "IWAY-led clause interpretation lookup",
            "requirement atom lookup from promoted GSP core database",
            "factory-area applicability lookup",
            "subject profile action mapping lookup",
            "audit-preparation and training-preparation notes",
        ],
        "blocked_scope": [
            "final legal opinion",
            "confirmed compliance conclusion",
            "audit-pass claim",
            "claiming Legal Owner approval",
            "claiming subject-profile applicability without owner confirmation",
        ],
        "operator_note_cn": "GSP Compliance Core Database v1 已作为正式 live 查询目标上线；后续按现场反馈和法律更新持续迭代。",
    }
    data["requirement_atom_database_configured"] = True
    data["status"] = "LIVE_KNOWLEDGE_BASE_WITH_GSP_CORE_DATABASE"
    data["last_runtime_policy_sync_at"] = datetime.now(timezone.utc).isoformat()
    dump(CATALOG, data)


def core_database_first_query_policy(core_id: str) -> dict:
    return {
        "status": "LIVE_REQUIRED_FOR_FACTORY_AREA_EQUIPMENT_IWAY_EXECUTION_QUERIES",
        "default_core_database_entry_id": core_id,
        "default_core_database_entry_id_source": str(CATALOG),
        "core_database_resolution_source": str(CATALOG),
        "core_database_version_hardcoding_forbidden": True,
        "first_query_tables": [
            "atom_factory_area_applicability_map",
            "compliance_atom_master",
            "legal_mapping",
            "subject_profile_action_map",
            "evidence_requirement_master",
        ],
        "legal_database_role": "SECONDARY_SUPPORT_AFTER_CORE_DATABASE_ROWS_ARE_RETRIEVED",
    }


def update_capability(core_id: str, core_path: str, core_manifest: str) -> None:
    data = load(CAPABILITY)
    artifact_policy = data.setdefault("database_artifact_policy", {})
    artifact_policy["default_real_trial_database_query"] = "LIVE_ALLOWED_GSP_CORE_DATABASE_AND_LEGAL_METADATA_INDEX"
    artifact_policy["live_database_configured"] = True
    artifact_policy["live_database_scope"] = "legal_document_canonical_metadata_index_and_gsp_compliance_core_database"
    artifact_policy["default_core_database_entry_id"] = core_id
    artifact_policy["gsp_compliance_core_database_v1_db"] = core_path
    artifact_policy["core_database_resolution_source"] = str(CATALOG)
    artifact_policy["core_database_version_hardcoding_forbidden"] = True
    artifact_policy["core_database_resolution_note"] = CATALOG_RESOLUTION_NOTE

    policy = data.setdefault("live_business_data_policy", {})
    policy["live_business_data_configured"] = True
    policy["compliance_core_database_configured"] = True
    policy["default_core_database_entry_id"] = core_id
    policy["default_gsp_compliance_core_database_entry_id"] = core_id
    policy["gsp_compliance_core_database_v1_db"] = core_path
    policy["gsp_compliance_core_database_v1_manifest"] = core_manifest
    policy["core_database_resolution_source"] = str(CATALOG)
    policy["core_database_version_hardcoding_forbidden"] = True
    policy["core_database_resolution_note"] = CATALOG_RESOLUTION_NOTE
    policy["live_database_configured"] = True
    policy["live_database_scope"] = "legal_document_canonical_metadata_index_and_gsp_compliance_core_database"
    policy["ordinary_real_trial_business_queries"] = "LIVE_ALLOWED_WHEN_ANSWER_USES_PROMOTED_GSP_CORE_DATABASE_OR_LIVE_LEGAL_METADATA_INDEX"
    policy["core_database_query_policy"] = {
        "status": "LIVE_ALLOWED",
        "allowed_use": [
            "IWAY-led clause interpretation lookup",
            "requirement atom lookup from promoted GSP core database",
            "factory-area applicability lookup across multiple blocks",
            "subject profile action mapping lookup",
            "audit-preparation and training-preparation notes",
        ],
        "blocked_use": [
            "final legal opinion",
            "confirmed compliance conclusion",
            "audit-pass claim",
            "claiming Legal Owner approval",
            "claiming subject-profile applicability without owner confirmation",
        ],
        "operator_note_cn": "GSP Compliance Core Database v1 is a formal live query target; future changes should be applied as controlled updates.",
    }
    policy["last_runtime_policy_sync_at"] = datetime.now(timezone.utc).isoformat()
    policy["core_database_first_query_policy"] = core_database_first_query_policy(core_id)

    live = data.setdefault("live_data", {})
    live["live_business_data_configured"] = True
    live["compliance_core_database_configured"] = True
    live["default_core_database_entry_id"] = core_id
    live["default_gsp_compliance_core_database_entry_id"] = core_id
    live["gsp_compliance_core_database_v1_db"] = core_path
    live["gsp_compliance_core_database_v1_manifest"] = core_manifest
    live["core_database_resolution_source"] = str(CATALOG)
    live["core_database_version_hardcoding_forbidden"] = True
    live["core_database_resolution_note"] = CATALOG_RESOLUTION_NOTE
    live["live_database_scope"] = "legal_document_canonical_metadata_index_and_gsp_compliance_core_database"
    live["core_database_query_policy"] = {
        "status": "LIVE_ALLOWED",
        "allowed_use": [
            "IWAY-led clause interpretation lookup",
            "requirement atom lookup from promoted GSP core database",
            "factory-area applicability lookup across multiple blocks",
            "subject profile action mapping lookup",
            "audit-preparation and training-preparation notes",
        ],
        "blocked_use": [
            "final legal opinion",
            "confirmed compliance conclusion",
            "audit-pass claim",
            "claiming Legal Owner approval",
            "claiming subject-profile applicability without owner confirmation",
        ],
        "operator_note_cn": "Core database is live; future changes should be applied as controlled updates.",
    }
    live["last_runtime_policy_sync_at"] = datetime.now(timezone.utc).isoformat()
    live["core_database_first_query_policy"] = core_database_first_query_policy(core_id)
    dump(CAPABILITY, data)


def update_soul(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    catalog_sentence = "The live catalog is the authority for its current path, tables,\ncounts, allowed uses, and blocked uses."
    new = (
        f"{catalog_sentence} The current default core database entry\n"
        "must always be resolved at query time from `/Users/HY-yin/hermes-local/data/knowledge/compliance/knowledge_base_catalog.v1.json`.\n"
        f"{SOUL_NO_HARDCODE_SENTENCE}"
    )
    old_versioned_pattern = re.compile(
        re.escape(catalog_sentence)
        + r" The current default core database entry\n"
        + r"is `core_databases:gsp_compliance_core_database_v1:[^`]+` unless the live\n"
        + r"catalog says otherwise\."
    )
    current_no_hardcode_pattern = re.compile(
        re.escape(catalog_sentence)
        + r" The current default core database entry\n"
        + r"must always be resolved at query time from `/Users/HY-yin/hermes-local/data/knowledge/compliance/knowledge_base_catalog\.v1\.json`\.\n"
        + re.escape(SOUL_NO_HARDCODE_SENTENCE)
    )
    text, replaced = old_versioned_pattern.subn(new, text, count=1)
    if not replaced:
        text, replaced = current_no_hardcode_pattern.subn(new, text, count=1)
    if not replaced and SOUL_NO_HARDCODE_SENTENCE not in text:
        text = text.replace(catalog_sentence, new, 1)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    core_id, core_path, core_manifest = current_core()
    update_catalog(core_id)
    update_capability(core_id, core_path, core_manifest)
    update_soul(ACCEPTED_SOUL)
    print("updated", CATALOG)
    print("updated", CAPABILITY)
    print("updated", ACCEPTED_SOUL)
    print("default_core_database_entry_id", core_id)


if __name__ == "__main__":
    main()
