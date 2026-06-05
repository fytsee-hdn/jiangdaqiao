#!/usr/bin/env python3
"""Preflight guard for the live Hermes compliance gateway.

The accepted compliance source lives in /Users/HY-yin/hermes-local.  The
profile under ~/.hermes is generated runtime state and must never become the
source of truth.  This guard fails closed when the live gateway is not bound to
the accepted source files.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path


CODEX_REPO_ENV = os.environ.get("CODEX_COMPLIANCE_REPO")
CODEX_REPO = Path(CODEX_REPO_ENV).expanduser() if CODEX_REPO_ENV else None
HERMES_LOCAL = Path("/Users/HY-yin/hermes-local")
PROFILE_HOME = Path("/Users/HY-yin/.hermes/profiles/compliance")
HERMES_AGENT = Path("/Users/HY-yin/.hermes/hermes-agent")
LAUNCH_AGENTS = Path("/Users/HY-yin/Library/LaunchAgents")
COMPLIANCE_LABEL = "ai.hermes.gateway-compliance"
GENERIC_LABEL = "ai.hermes.gateway"

SOURCE_ARCHITECTURE = HERMES_LOCAL / "HERMES_ARCHITECTURE.md"
SOURCE_PROFILE = HERMES_LOCAL / "config/profiles/compliance.yaml"
SOURCE_CAPABILITY_MAP = HERMES_LOCAL / "config/profiles/compliance_capability_map.v1.json"
SOURCE_MEMORY_SEED = HERMES_LOCAL / "config/profiles/compliance_memory_seed.md"
SOURCE_SOUL = HERMES_LOCAL / "src/hermes/gsp_compliance_agent/prompts/soul.md"
SOURCE_SKILLS = HERMES_LOCAL / "src/gsp_hermes/skills/compliance"
SOURCE_SQLITE_ARTIFACT_GUARD = (
    HERMES_LOCAL / "src/hermes/gsp_compliance_agent/runtime/candidate_sqlite_artifact_guard.py"
)
CANONICAL_SOURCES = CODEX_REPO / "manifests/canonical_sources.json" if CODEX_REPO else None
APPROVED_SOURCES = CODEX_REPO / "docs/state/approved_sources.md" if CODEX_REPO else None
PROFILE_SOUL = PROFILE_HOME / "SOUL.md"
PERMISSION_MODEL = HERMES_LOCAL / "config/profiles/compliance_permission_model.v1.json"
CONFIG = PROFILE_HOME / "config.yaml"
PROFILE_ENV = PROFILE_HOME / ".env"
MEMORY = PROFILE_HOME / "memories/MEMORY.md"
STATE_DB = PROFILE_HOME / "state.db"
NO_BUNDLED_SKILLS = PROFILE_HOME / ".no-bundled-skills"
RUNTIME_SKILLS = PROFILE_HOME / "skills"
PROMOTION_REQUESTS = PROFILE_HOME / "promotion_requests"
SESSIONS_DIR = PROFILE_HOME / "sessions"
SESSIONS_INDEX = SESSIONS_DIR / "sessions.json"
ACCEPTED_SKILLS_MANIFEST = RUNTIME_SKILLS / ".accepted_compliance_skills_manifest.json"
SKILLS_PROMPT_SNAPSHOT = PROFILE_HOME / ".skills_prompt_snapshot.json"
ACCESS_GATE = HERMES_AGENT / "gateway/compliance_access_gate.py"
GATEWAY_RUN = HERMES_AGENT / "gateway/run.py"
PROMOTION_REQUEST_TOOL = HERMES_AGENT / "tools/promotion_request_tool.py"
COMPLIANCE_WORKFLOW_TOOL = HERMES_AGENT / "tools/compliance_workflow_tool.py"
FILE_TOOLS = HERMES_AGENT / "tools/file_tools.py"
APPROVAL_TOOL = HERMES_AGENT / "tools/approval.py"
COMPLIANCE_PLIST = LAUNCH_AGENTS / f"{COMPLIANCE_LABEL}.plist"
GENERIC_PLIST = LAUNCH_AGENTS / f"{GENERIC_LABEL}.plist"
GUARD_SCRIPT = PROFILE_HOME / "bin/hermes-compliance-gateway-guard.sh"
SKILLS_SYNC_LOCK = Path("/private/tmp/hermes_compliance_skills_sync.lock")
SESSION_PROMPT_REQUIRED_MARKERS = [
    "Tool Awareness And Stuck-Point Recovery",
    "delegate_task",
    "domain workflow tools",
    "candidate/not-live",
    "promotion_request_queue_requires_submit_promotion_request_tool",
    "intake_source_files",
    "submit_promotion_request",
    "withdraw_promotion_request",
    "amend_promotion_request",
    "create_p3_approval_request",
    "record_promotion_approval",
    "source_files",
    "source_kind",
    "promotion_scope",
    "knowledge_source_upload",
    "structured_database_build",
    "controlled_source_intake_no_shell_required",
    "codex_thread_approval_only_wecom_push_disabled",
    "BLOCKED_STALE_RUNTIME_SESSION",
    "runtime session refresh",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256(path: Path) -> str:
    if not path.exists():
        fail(f"missing required file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    if not path.exists():
        fail(f"missing JSON file: {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_json_if_readable(path):
    """Read optional Codex repo audit files when the caller has access.

    The LaunchAgent runtime guard intentionally avoids depending on files under
    the Codex Documents workspace because macOS privacy controls may block that
    path for launchd jobs. Accepted runtime policy must live in hermes-local;
    repo placement checks run through the Task 16 audit script.
    """

    if path is None or not path.exists():
        return None
    try:
        return load_json(path)
    except PermissionError:
        return None


def read_text_if_readable(path):
    if path is None or not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except PermissionError:
        return None


def launchctl_service_loaded(label: str) -> bool:
    uid = os.getuid()
    result = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{label}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def read_plist(path: Path) -> dict:
    if not path.exists():
        fail(f"missing LaunchAgent plist: {path}")
    with path.open("rb") as fh:
        return plistlib.load(fh)


def require_same_hash(label: str, left: Path, right: Path) -> None:
    left_hash = sha256(left)
    right_hash = sha256(right)
    if left_hash != right_hash:
        fail(f"{label} hash mismatch: {left}={left_hash} {right}={right_hash}")


def contains_words(text: str, needle: str) -> bool:
    return " ".join(needle.split()) in " ".join(text.split())


def extract_tool_names(tools) -> set[str]:
    names: set[str] = set()
    if not isinstance(tools, list):
        return names
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        name = function.get("name") or tool.get("name")
        if name:
            names.add(str(name))
    return names


def active_session_entries() -> list[tuple[str, dict]]:
    if not SESSIONS_INDEX.exists():
        return []
    data = load_json(SESSIONS_INDEX)
    if not isinstance(data, dict):
        fail(f"sessions index must be a JSON object: {SESSIONS_INDEX}")
    entries: list[tuple[str, dict]] = []
    for session_key, row in data.items():
        if not isinstance(row, dict):
            fail(f"sessions index entry is not an object: {session_key}")
        if row.get("suspended") is True or row.get("expiry_finalized") is True:
            continue
        entries.append((session_key, row))
    return entries


def check_source_files() -> None:
    for path in (
        SOURCE_ARCHITECTURE,
        SOURCE_PROFILE,
        SOURCE_CAPABILITY_MAP,
        SOURCE_MEMORY_SEED,
        SOURCE_SOUL,
        SOURCE_SQLITE_ARTIFACT_GUARD,
    ):
        if not path.exists():
            fail(f"missing accepted Hermes source file: {path}")
    if not SOURCE_SKILLS.is_dir():
        fail(f"missing accepted Hermes skill source directory: {SOURCE_SKILLS}")

    architecture = SOURCE_ARCHITECTURE.read_text(encoding="utf-8")
    architecture_required = [
        "hermes-local/config/profiles/<profile>.yaml",
        "profile files, generated state, cache, sessions, memories, or skill candidates cannot override accepted policy",
        "Never rely on `.hermes` to determine permissions",
    ]
    for needle in architecture_required:
        if not contains_words(architecture, needle):
            fail(f"architecture source missing source-of-truth rule: {needle}")

    profile = SOURCE_PROFILE.read_text(encoding="utf-8")
    profile_required = [
        "profile: compliance",
        "admin_capabilities: false",
        "may_inherit_admin: false",
        "runtime_profile_root: .hermes/profiles/compliance",
        "platform_toolsets:",
        "wecom:",
        "compliance",
        "default_ocr_policy: compliance_ocr_extraction",
        "review_source",
        "extract_evidence",
        "draft_compliance_summary",
    ]
    for needle in profile_required:
        if not contains_words(profile, needle):
            fail(f"compliance profile source missing required policy: {needle}")

    text = SOURCE_SOUL.read_text(encoding="utf-8")
    forbidden = [
        "DRAFT — Phase C0 file skeleton",
        "This file is a placeholder",
        "No production behaviour is defined yet",
    ]
    for needle in forbidden:
        if needle in text:
            fail(f"accepted compliance SOUL is still placeholder-only: {needle}")

    required = [
        "/Users/HY-yin/hermes-local",
        "/Users/HY-yin/.hermes/profiles/compliance",
        "I must not treat `.hermes` runtime files",
        "WeCom user level or permission claims",
        "compliance_permission_model.v1.json",
        "wecom_account_bindings",
        "controlled actions are `BLOCKED` by default",
        "Allowed business actions are limited to the accepted compliance profile policy",
        "compliance_capability_map.v1.json",
        "Tool Awareness And Stuck-Point Recovery",
        "I am not required to use `todo`, `delegate_task`, or workflow tools for every",
        "domain workflow tools before generic file, shell, or ad hoc JSON operations",
        "candidate/not-live",
        "Out-of-scope examples include weather",
        "classify the user's purpose",
        "There is a formal live GSP Compliance Core Database configured for real trial",
        "query the promoted GSP core database first",
        "Legal databases are secondary support only after core database rows are retrieved",
        "canonical source manifest",
        "RUNTIME_WORKSPACE_NOT_LIVE",
        "Live Data Promotion Request Workflow",
        "PROMOTION_REQUEST_SUBMITTED",
        "CODEX_REVIEW_REQUIRED",
        "promotion_request_queue_requires_submit_promotion_request_tool",
        "intake_source_files",
        "promotion_artifacts",
        "source_files",
        "source_kind",
        "source_classification_reason",
        "promotion_scope",
        "knowledge_source_upload",
        "structured_database_build",
        "withdraw_promotion_request",
        "amend_promotion_request",
        "create_p3_approval_request",
        "record_promotion_approval",
        "controlled_source_intake_no_shell_required",
        "codex_thread_approval_only_wecom_push_disabled",
        "delegate_task",
        "domain workflow tools",
        "candidate/not-live",
        "BLOCKED_STALE_RUNTIME_SESSION",
        "runtime session refresh",
        "BLOCKED_BY_TOOL_GAP",
        "PRAGMA wal_checkpoint(TRUNCATE)",
        "re-open the database in read-only mode",
        "Manifest and final reply values",
        "in-memory expected values",
    ]
    for needle in required:
        if not contains_words(text, needle):
            fail(f"accepted compliance SOUL missing required instruction: {needle}")

    skill_files = sorted(SOURCE_SKILLS.rglob("SKILL.md"))
    if not skill_files:
        fail("accepted compliance skills directory contains no SKILL.md files")
    for skill in skill_files:
        content = skill.read_text(encoding="utf-8")
        if "Phase C0" in content or "Placeholder skill" in content:
            fail(f"accepted compliance skill is still placeholder-only: {skill}")

    capability_map = load_json(SOURCE_CAPABILITY_MAP)
    capabilities = capability_map.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) < 15:
        fail("accepted capability map must contain at least 15 capability groups")
    capability_ids = {row.get("capability_id") for row in capabilities if isinstance(row, dict)}
    for capability_id in [
        "wecom_intent_and_out_of_scope_isolation",
        "candidate_database_read_only_query",
        "runtime_architecture_contamination_prevention",
        "controlled_self_improvement_skill_proposal",
    ]:
        if capability_id not in capability_ids:
            fail(f"accepted capability map missing capability: {capability_id}")
    out_of_scope = capability_map.get("out_of_scope_isolation") or {}
    if out_of_scope.get("required_before_answer_or_tool_use") is not True:
        fail("accepted capability map must require out-of-scope isolation before answer/tool use")
    if "database_artifacts" in capability_map:
        fail("accepted capability map must not expose legacy database_artifacts as live database targets")
    database_policy = capability_map.get("database_artifact_policy") or {}
    if database_policy.get("live_database_configured") is not True:
        fail("accepted capability map must mark the promoted legal metadata index as a live database artifact")
    live_scope = database_policy.get("live_database_scope")
    if live_scope not in {
        "legal_document_index_metadata_only",
        "legal_document_canonical_metadata_index",
        "legal_document_canonical_metadata_index_and_gsp_compliance_core_database",
    }:
        fail("accepted capability map live database scope is not an accepted live query boundary")
    if live_scope == "legal_document_canonical_metadata_index_and_gsp_compliance_core_database":
        core_db = Path(str(database_policy.get("gsp_compliance_core_database_v1_db", "")))
        if not core_db.exists():
            fail(f"accepted capability map core database path is missing: {core_db}")
        if "GSP_CORE_DATABASE" not in str(database_policy.get("default_real_trial_database_query", "")):
            fail("accepted capability map core database scope must explicitly name GSP core database access")
    default_query_policy = str(database_policy.get("default_real_trial_database_query"))
    if live_scope != "legal_document_canonical_metadata_index_and_gsp_compliance_core_database" and "BLOCKED" not in default_query_policy:
        fail("accepted capability map must block default real-trial database queries except live legal metadata")
    if "legal document metadata" not in str(database_policy.get("legal_document_metadata_queries", "")).lower():
        fail("accepted capability map must allow live legal document metadata queries")
    live_artifacts = capability_map.get("live_database_artifacts")
    if not isinstance(live_artifacts, list):
        fail("accepted capability map live_database_artifacts must be a list")
    if not any(
        isinstance(row, dict)
        and row.get("artifact_id") == "legal_sources:vietnam_legal_document_index:2026_05_25"
        and row.get("status") == "ARCHIVED_THIRD_PARTY_DISCOVERY_ONLY"
        and row.get("chatbot_query_enabled") is False
        and row.get("live_query_enabled") is False
        for row in live_artifacts
    ):
        fail("accepted capability map must archive the legacy third-party legal metadata index")
    if not any(
        isinstance(row, dict)
        and row.get("artifact_id") == "legal_sources:vietnam_a0_b1_crosswalk:2026_05_25"
        and row.get("status") == "ARCHIVED_THIRD_PARTY_CROSSWALK_TRACEABILITY_ONLY"
        and row.get("chatbot_query_enabled") is False
        and row.get("live_query_enabled") is False
        for row in live_artifacts
    ):
        fail("accepted capability map must archive the legacy A0/B1 crosswalk from live query use")
    if not any(
        isinstance(row, dict)
        and row.get("artifact_id") == "legal_sources:vietnam_legal_document_canonical_index:2026_05_25"
        and row.get("status") in {
            "LIVE_READ_ONLY_CANONICAL_METADATA_INDEX",
            "LIVE_READ_ONLY_CANONICAL_METADATA_INDEX_V321_CURRENT_ONLY",
        }
        and row.get("default_query_target") is True
        for row in live_artifacts
    ):
        fail("accepted capability map live_database_artifacts must include the canonical legal metadata index")
    business_policy = capability_map.get("live_business_data_policy") or {}
    live_source_files_configured = business_policy.get("live_source_files_configured") is True
    live_business_data_configured = business_policy.get("live_business_data_configured") is True
    core_database_configured = business_policy.get("compliance_core_database_configured") is True
    if live_business_data_configured and not core_database_configured:
        fail("accepted capability map must not allow live business data without the promoted GSP core database")
    if not live_business_data_configured and business_policy.get("ordinary_real_trial_business_queries") != "BLOCKED":
        fail("accepted capability map must block ordinary real-trial business queries without live structured business data")
    if live_business_data_configured:
        ordinary_policy = str(business_policy.get("ordinary_real_trial_business_queries", ""))
        if "LIVE_ALLOWED" not in ordinary_policy or "GSP_CORE_DATABASE" not in ordinary_policy:
            fail("accepted capability map live business query policy must require the promoted GSP core database")
        core_db = Path(str(business_policy.get("gsp_compliance_core_database_v1_db", "")))
        if not core_db.exists():
            fail(f"accepted capability map GSP core database path is missing: {core_db}")
    if not business_policy.get("knowledge_base_catalog"):
        fail("accepted capability map must point to the live knowledge-base catalog")
    accepted_business_root = "/Users/HY-yin/hermes-local/data/knowledge/compliance/"
    if business_policy.get("accepted_live_root_required_prefix") != accepted_business_root:
        fail("accepted capability map must require hermes-local live business data root")
    labels = set(business_policy.get("candidate_or_runtime_inspection_must_be_labeled") or [])
    for label in ["RUNTIME_WORKSPACE_NOT_LIVE", "CANDIDATE_ONLY", "TEST_DATA"]:
        if label not in labels:
            fail(f"accepted capability map missing non-live inspection label: {label}")
    covered = set(business_policy.get("covered_datasets") or [])
    for dataset in [
        "source_register",
        "legal_sources",
        "customer_requirements",
        "checklists",
        "gsp_standards",
        "evidence_matrix",
        "factory_risk_records",
        "compliance_product_database",
    ]:
        if dataset not in covered:
            fail(f"accepted capability map live business policy missing dataset: {dataset}")
    non_authority_roots = business_policy.get("non_authoritative_roots") or []
    for forbidden_root in [
        "/Users/HY-yin/.hermes/profiles/compliance/workspace/data/knowledge/compliance/",
        "/Users/HY-yin/.hermes/profiles/compliance/workspace/promotion_artifacts/",
        "/Users/HY-yin/Documents/Codex-Compliance-System/artifacts/candidate/",
        "/Users/HY-yin/Desktop/",
    ]:
        if forbidden_root not in non_authority_roots:
            fail(f"accepted capability map must mark root as non-authoritative: {forbidden_root}")
    canonical_sources = load_json_if_readable(CANONICAL_SOURCES)
    if canonical_sources is not None and canonical_sources.get("files") != [] and not live_source_files_configured:
        fail("canonical_sources.json has registered files while live_source_files_configured is false")
    approved_sources_text = read_text_if_readable(APPROVED_SOURCES)
    if (
        approved_sources_text is not None
        and "No approved business source files registered yet" not in approved_sources_text
        and not live_source_files_configured
    ):
        fail("approved_sources.md must show no approved business sources while live_source_files_configured is false")
    candidate_prefix = "/Users/HY-yin/Documents/Codex-Compliance-System/artifacts/candidate/"
    for path in capability_map.get("test_candidate_database_artifacts", []):
        if not str(path).startswith(candidate_prefix):
            fail(f"candidate test artifact path is outside candidate root: {path}")
    for row in capabilities:
        if row.get("capability_id") == "candidate_database_read_only_query":
            if row.get("status") == "LIVE_ALLOWED":
                fail("candidate database query capability must not be LIVE_ALLOWED without an accepted live database")
            forbidden_text = " ".join(row.get("forbidden", []))
            if "Documents/artifacts/candidate" not in forbidden_text:
                fail("candidate database query capability must forbid treating candidate artifacts as live")
        if row.get("capability_id") == "candidate_database_build_coordination":
            build_text = " ".join(row.get("evidence_sources", []) + row.get("should_do", []))
            for needle in [
                "candidate_sqlite_artifact_guard.py",
                "PRAGMA wal_checkpoint(TRUNCATE)",
                "只读重开",
                "expected values",
            ]:
                if needle not in build_text:
                    fail(f"candidate database build capability missing SQLite consistency marker: {needle}")
        if row.get("capability_id") == "validation_qc_failure_injection":
            validation_text = " ".join(row.get("evidence_sources", []) + row.get("should_do", []))
            for needle in [
                "candidate_sqlite_artifact_guard.py",
                "validation_findings",
                "severity",
                "DB hash",
            ]:
                if needle not in validation_text:
                    fail(f"validation QC capability missing SQLite consistency marker: {needle}")
    workflow = capability_map.get("promotion_request_workflow") or {}
    if workflow.get("runtime_request_queue") != "/Users/HY-yin/.hermes/profiles/compliance/promotion_requests/":
        fail("accepted capability map must define the Hermes runtime promotion request queue")
    if workflow.get("runtime_source_intake_root") != "/Users/HY-yin/.hermes/profiles/compliance/workspace/source_intake/":
        fail("accepted capability map must define controlled runtime source intake root")
    if workflow.get("temporary_candidate_artifact_root") != "/Users/HY-yin/.hermes/profiles/compliance/workspace/promotion_artifacts/":
        fail("accepted capability map must route temporary candidate artifacts outside the request queue")
    if workflow.get("p3_approval_request_queue") != "/Users/HY-yin/.hermes/profiles/compliance/p3_approval_requests/":
        fail("accepted capability map must define P3 approval request queue")
    if workflow.get("promotion_approval_record_queue") != "/Users/HY-yin/.hermes/profiles/compliance/promotion_approval_records/":
        fail("accepted capability map must define promotion approval record queue")
    if workflow.get("request_queue_write_rule") != "promotion_request_queue_requires_submit_promotion_request_tool":
        fail("accepted capability map must define controlled-tool-only request queue writes")
    if workflow.get("source_intake_action_id") != "intake_source_files":
        fail("accepted capability map must define intake_source_files as controlled source intake action")
    if workflow.get("submit_action_id") != "submit_promotion_request":
        fail("accepted capability map must define submit_promotion_request as the Hermes intake action")
    if workflow.get("withdraw_action_id") != "withdraw_promotion_request":
        fail("accepted capability map must define withdraw_promotion_request as the Hermes lifecycle action")
    if workflow.get("amend_action_id") != "amend_promotion_request":
        fail("accepted capability map must define amend_promotion_request as the Hermes lifecycle action")
    if workflow.get("p3_approval_request_action_id") != "create_p3_approval_request":
        fail("accepted capability map must define create_p3_approval_request as P3 handoff action")
    if workflow.get("p3_approval_notification_action_id") != "DISABLED_WE_COM_PUSH":
        fail("accepted capability map must disable WeCom P3 approval notification")
    if workflow.get("record_promotion_approval_action_id") != "record_promotion_approval":
        fail("accepted capability map must define record_promotion_approval as P3 decision action")
    if workflow.get("approval_channel") != "codex_thread_only":
        fail("accepted capability map must route P3 approval to Codex thread only")
    if workflow.get("approval_notification_enabled") is not False or workflow.get("wecom_approval_replies_valid") is not False:
        fail("accepted capability map must disable WeCom approval notification and replies")
    if workflow.get("codex_thread_approval_marker") != "codex_thread_approval_only_wecom_push_disabled":
        fail("accepted capability map must define Codex-thread approval marker")
    if workflow.get("approval_action_id") != "approve_promotion":
        fail("accepted capability map must keep approve_promotion separate from request submission")
    if workflow.get("submit_minimum_role_id") != "P1" or workflow.get("approval_minimum_role_id") != "P3":
        fail("accepted capability map must require P1 submit and P3 approve for promotion workflow")
    if workflow.get("source_kind_classification_required_before_submit") is not True:
        fail("accepted capability map must require source kind classification before promotion request submission")
    if workflow.get("promotion_scope_required_before_submit") is not True:
        fail("accepted capability map must require promotion scope classification before promotion request submission")
    if workflow.get("knowledge_source_upload_scope") != "knowledge_source_upload":
        fail("accepted capability map must define knowledge_source_upload as source-file upload scope")
    if "structured_database_build" not in (workflow.get("database_build_scopes") or []):
        fail("accepted capability map must distinguish structured_database_build from source upload")
    for status in [
        "BLOCKED",
        "PRELIMINARY_REVIEW_INCOMPLETE",
        "PROMOTION_REQUEST_SUBMITTED",
        "CODEX_REVIEW_REQUIRED",
        "WITHDRAWN",
        "SUPERSEDED",
        "AMENDED",
    ]:
        if status not in (workflow.get("allowed_request_statuses") or []):
            fail(f"accepted capability map missing promotion request status: {status}")
    for forbidden_action in [
        "write_live_data_root",
        "update_live_manifest",
        "update_capability_map",
        "approve_promotion",
        "claim_live_business_data",
    ]:
        if forbidden_action not in (workflow.get("forbidden_hermes_actions") or []):
            fail(f"accepted capability map missing forbidden Hermes promotion action: {forbidden_action}")
    capability_ids = {row.get("capability_id") for row in capabilities if isinstance(row, dict)}
    if "live_data_promotion_request_intake" not in capability_ids:
        fail("accepted capability map missing live_data_promotion_request_intake capability")
    seed_text = SOURCE_MEMORY_SEED.read_text(encoding="utf-8")
    for needle in [
        "non-authoritative pointer index",
        "Out-Of-Scope Isolation",
        "Business Source And Data Pointers",
        "Database Pointers",
        "Tool Awareness Pointer",
        "Database Build And Validation Pointer",
    ]:
        if needle not in seed_text:
            fail(f"accepted memory seed missing required section: {needle}")
    for needle in [
        "no accepted live compliance product database",
        "approved live source-file set",
        "test/candidate",
        "return `BLOCKED`",
        "RUNTIME_WORKSPACE_NOT_LIVE",
        "Live Data Promotion Request Workflow Pointer",
        "PROMOTION_REQUEST_SUBMITTED",
        "CODEX_REVIEW_REQUIRED",
        "source_kind",
        "source_classification_reason",
        "promotion_scope",
        "knowledge_source_upload",
        "structured_database_build",
        "withdraw_promotion_request",
        "amend_promotion_request",
        "intake_source_files",
        "create_p3_approval_request",
        "record_promotion_approval",
        "controlled_source_intake_no_shell_required",
        "codex_thread_approval_only_wecom_push_disabled",
        "BLOCKED_STALE_RUNTIME_SESSION",
        "runtime session refresh",
        "BLOCKED_BY_TOOL_GAP",
        "PRAGMA wal_checkpoint(TRUNCATE)",
        "re-open the database in read-only mode",
        "db_sha256",
        "in-memory expected",
    ]:
        if needle not in seed_text.lower() and needle not in seed_text:
            fail(f"accepted memory seed missing live database guard: {needle}")
    db_skill = SOURCE_SKILLS / "compliance-database-query/SKILL.md"
    db_skill_text = db_skill.read_text(encoding="utf-8")
    for needle in [
        "live knowledge-base catalog",
        "canonical legal document metadata index",
        "current canonical legal document metadata index",
        "LIVE_ALLOWED_METADATA_ONLY",
        "checklist database",
        "return `BLOCKED`",
        "Do not read test/candidate artifacts unless",
        "Do not read runtime workspace data unless",
    ]:
        if needle not in db_skill_text:
            fail(f"accepted database query skill missing live database guard: {needle}")
    source_skill = SOURCE_SKILLS / "compliance-source-lifecycle/SKILL.md"
    source_skill_text = source_skill.read_text(encoding="utf-8")
    for needle in [
        "Approved live source-file set",
        "manifests/canonical_sources.json",
        "RUNTIME_WORKSPACE_NOT_LIVE",
        "artifacts/candidate",
        "knowledge_source_upload",
        "structured_database_build",
        "customer_requirement",
        "legal_source",
        "intake_source_files",
        "controlled_source_intake_no_shell_required",
    ]:
        if needle not in source_skill_text:
            fail(f"accepted source lifecycle skill missing live source guard: {needle}")
    legal_skill = SOURCE_SKILLS / "compliance-legal-customer-pipeline/SKILL.md"
    legal_skill_text = legal_skill.read_text(encoding="utf-8")
    for needle in [
        "source of truth for live legal/customer",
        "legal text/clause availability",
        "Accepted live customer requirement source files",
        "RUNTIME_WORKSPACE_NOT_LIVE",
        "Task 11 artifacts are candidate pipeline evidence only",
        "When this skill becomes complex or stuck",
        "delegate_task",
        "same fetch, parse, search, or code path fails twice",
        "candidate/not-live",
    ]:
        if needle not in legal_skill_text:
            fail(f"accepted legal/customer skill missing live data guard: {needle}")
    skill_guard_needles = {
        "compliance-capability-router/SKILL.md": [
            "live_business_data_policy",
            "live_business_data_configured",
            "RUNTIME_WORKSPACE_NOT_LIVE",
            "tool awareness",
            "delegate_task",
            "candidate/not-live",
        ],
        "compliance-runtime-governance/SKILL.md": [
            "live business data policy",
            "candidate/runtime business data",
        ],
        "compliance-promotion-rollback/SKILL.md": [
            "/Users/HY-yin/hermes-local/data/knowledge/compliance/",
            "live_business_data_configured",
            "artifacts/candidate",
        ],
        "compliance-database-build-coordination/SKILL.md": [
            "/Users/HY-yin/hermes-local/data/knowledge/compliance/",
            ".hermes` runtime workspace",
            "candidate/runtime workspace records",
            "JSON-to-SQLite conversion pattern",
            "SQLite write safety requirements",
            "conn.commit()",
            "PRAGMA wal_checkpoint(TRUNCATE)",
            "Write-then-Read-Verify checkpoint",
            "Manifest/database consistency",
            "compliance-validation-qc",
        ],
        "compliance-requirement-atomization/SKILL.md": [
            "ordinary real-trial requirement",
            "RUNTIME_WORKSPACE_NOT_LIVE",
            "Task 12 candidate artifacts",
        ],
        "compliance-validation-qc/SKILL.md": [
            "Validation success is not live promotion",
            "live_business_data_configured",
            "equating `CANDIDATE_PASS`",
            "severity=NULL",
            "Pre-insert audit",
            "Write-then-Read-Verify",
            "conn.commit()",
            "PRAGMA wal_checkpoint(TRUNCATE)",
            "re-open the DB",
            "Manifest values",
        ],
        "compliance-review-handoff/SKILL.md": [
            "does not make data live",
            "/Users/HY-yin/hermes-local/data/knowledge/compliance/",
            "promoted live source authority",
        ],
        "compliance-live-data-promotion-request/SKILL.md": [
            "Runtime request queue",
            "submit_promotion_request",
            "PROMOTION_REQUEST_SUBMITTED",
            "Codex verification and P3 human approval",
            "Updating `/Users/HY-yin/hermes-local/data/knowledge/compliance/`",
            "promotion_request_queue_requires_submit_promotion_request_tool",
            "promotion_artifacts",
            "source_files",
            "source_kind",
            "source_classification_reason",
            "promotion_scope",
            "knowledge_source_upload",
            "structured_database_build",
            "withdraw_promotion_request",
            "amend_promotion_request",
            "create_p3_approval_request",
            "record_promotion_approval",
            "codex_thread_approval_only_wecom_push_disabled",
            "BLOCKED_STALE_RUNTIME_SESSION",
            "runtime session refresh",
            "BLOCKED_BY_TOOL_GAP",
        ],
    }
    for rel_path, needles in skill_guard_needles.items():
        skill_text = (SOURCE_SKILLS / rel_path).read_text(encoding="utf-8")
        for needle in needles:
            if needle not in skill_text:
                fail(f"accepted skill missing live business data guard: {rel_path}: {needle}")

    guard_text = SOURCE_SQLITE_ARTIFACT_GUARD.read_text(encoding="utf-8")
    for needle in [
        "mode=ro",
        "Manifest db_sha256 mismatch",
        "Table count mismatch",
        "validation_summary.total_checks mismatch",
        "does not write",
    ]:
        if needle not in guard_text:
            fail(f"candidate SQLite artifact guard missing marker: {needle}")


def check_soul_binding() -> None:
    config_text = CONFIG.read_text(encoding="utf-8")
    if f"soul_path: {SOURCE_SOUL}" not in config_text:
        fail("compliance profile must load SOUL directly from hermes-local source")
    if f"memory_seed_path: {SOURCE_MEMORY_SEED}" not in config_text:
        fail("compliance profile must point memory_seed_path at hermes-local source")
    if PROFILE_SOUL.exists():
        fail(f"runtime SOUL duplicate must not exist; use configured source path: {PROFILE_SOUL}")

def check_permission_model() -> None:
    model = load_json(PERMISSION_MODEL)
    if model.get("deny_by_default") is not True:
        fail("permission model must deny by default")
    if model.get("role_order") != ["P0", "P1", "P2", "P3"]:
        fail("permission model role_order must be P0/P1/P2/P3")
    roles = {role.get("role_id") for role in model.get("roles", [])}
    if roles != {"P0", "P1", "P2", "P3"}:
        fail("permission model roles must contain exactly P0/P1/P2/P3")
    bindings = model.get("wecom_account_bindings")
    if not isinstance(bindings, list):
        fail("permission model wecom_account_bindings must be a list")
    for binding in bindings:
        if binding.get("assigned_role_id") not in roles:
            fail(f"WeCom binding assigns unknown role: {binding}")
    protected_actions = {
        action.get("action_id"): action
        for action in model.get("protected_actions", [])
        if isinstance(action, dict)
    }
    submit_promotion = protected_actions.get("submit_promotion_request")
    intake_source = protected_actions.get("intake_source_files")
    withdraw_promotion = protected_actions.get("withdraw_promotion_request")
    amend_promotion = protected_actions.get("amend_promotion_request")
    create_p3_approval = protected_actions.get("create_p3_approval_request")
    send_p3_approval_notification = protected_actions.get("send_p3_approval_notification")
    record_promotion_approval = protected_actions.get("record_promotion_approval")
    approve_promotion = protected_actions.get("approve_promotion")
    if not submit_promotion:
        fail("permission model must define submit_promotion_request separately from approve_promotion")
    if submit_promotion.get("minimum_role_id") != "P1":
        fail("submit_promotion_request must require minimum role P1")
    if submit_promotion.get("requires_human_approval") is not False:
        fail("submit_promotion_request is request intake and must not be promotion approval")
    if submit_promotion.get("allowed_tool_ids") != ["gateway.submit_promotion_request"]:
        fail("submit_promotion_request must use the dedicated gateway submit action")
    if not intake_source:
        fail("permission model must define intake_source_files")
    if intake_source.get("minimum_role_id") != "P1" or intake_source.get("allowed_tool_ids") != ["gateway.intake_source_files"]:
        fail("intake_source_files must be a P1 controlled source intake action")
    for action_id, action, tool_id in [
        ("withdraw_promotion_request", withdraw_promotion, "gateway.withdraw_promotion_request"),
        ("amend_promotion_request", amend_promotion, "gateway.amend_promotion_request"),
    ]:
        if not action:
            fail(f"permission model must define {action_id}")
        if action.get("minimum_role_id") != "P1":
            fail(f"{action_id} must require minimum role P1")
        if action.get("requires_human_approval") is not False:
            fail(f"{action_id} is request lifecycle control and must not be promotion approval")
        if action.get("allowed_tool_ids") != [tool_id]:
            fail(f"{action_id} must use its dedicated gateway action")
    if not approve_promotion or approve_promotion.get("minimum_role_id") != "P3":
        fail("approve_promotion must remain a P3-only action")
    if not create_p3_approval:
        fail("permission model must define create_p3_approval_request")
    if create_p3_approval.get("minimum_role_id") != "P3" or create_p3_approval.get("allowed_tool_ids") != ["gateway.create_p3_approval_request"]:
        fail("create_p3_approval_request must be a P3 approval handoff action")
    if not send_p3_approval_notification:
        fail("permission model must define send_p3_approval_notification")
    if send_p3_approval_notification.get("minimum_role_id") != "P3" or send_p3_approval_notification.get("allowed_tool_ids") != ["gateway.send_p3_approval_notification"]:
        fail("send_p3_approval_notification must be a P3 approval notification action")
    if not record_promotion_approval:
        fail("permission model must define record_promotion_approval")
    if record_promotion_approval.get("minimum_role_id") != "P3" or record_promotion_approval.get("allowed_tool_ids") != ["gateway.record_promotion_approval"]:
        fail("record_promotion_approval must be a P3 decision recording action")
    role_by_id = {role.get("role_id"): role for role in model.get("roles", []) if isinstance(role, dict)}
    if "submit_promotion_request" not in role_by_id["P1"].get("allowed_action_ids", []):
        fail("P1 must be allowed to submit promotion requests")
    if "intake_source_files" not in role_by_id["P1"].get("allowed_action_ids", []):
        fail("P1 must be allowed to intake source files")
    for action_id in ["withdraw_promotion_request", "amend_promotion_request"]:
        if action_id not in role_by_id["P1"].get("allowed_action_ids", []):
            fail(f"P1 must be allowed to use {action_id}")
    if "submit_promotion_request" not in role_by_id["P0"].get("denied_action_ids", []):
        fail("P0 must be denied submit_promotion_request")
    for action_id in ["withdraw_promotion_request", "amend_promotion_request"]:
        if action_id not in role_by_id["P0"].get("denied_action_ids", []):
            fail(f"P0 must be denied {action_id}")
    for action_id in ["create_p3_approval_request", "send_p3_approval_notification", "record_promotion_approval"]:
        if action_id not in role_by_id["P3"].get("allowed_action_ids", []):
            fail(f"P3 must be allowed to use {action_id}")


def check_live_data_root_binding() -> None:
    """Prevent runtime or candidate data roots from masquerading as live data."""

    capability_map = load_json(SOURCE_CAPABILITY_MAP)
    policy = capability_map.get("database_artifact_policy") or {}
    accepted_root = policy.get(
        "accepted_live_root_required_prefix",
        "/Users/HY-yin/hermes-local/data/knowledge/compliance/",
    ).rstrip("/")
    forbidden_roots = [
        "/Users/HY-yin/.hermes/profiles/compliance/workspace/data/knowledge/compliance",
        "/Users/HY-yin/Documents/Codex-Compliance-System/artifacts/candidate",
    ]

    if PROFILE_ENV.exists():
        for line in PROFILE_ENV.read_text(encoding="utf-8").splitlines():
            if not line.startswith("GSP_COMPLIANCE_DATA_ROOT="):
                continue
            data_root = line.split("=", 1)[1].strip().rstrip("/")
            for forbidden_root in forbidden_roots:
                if data_root.startswith(forbidden_root):
                    fail(f"GSP_COMPLIANCE_DATA_ROOT points to non-live data root: {data_root}")
            if data_root and not data_root.startswith(accepted_root):
                fail(f"GSP_COMPLIANCE_DATA_ROOT must be under accepted live root: {data_root}")

    checklist_tool = HERMES_AGENT / "tools/checklist_query_tool.py"
    if checklist_tool.exists():
        text = checklist_tool.read_text(encoding="utf-8")
        if "/Users/HY-yin/.hermes/profiles/compliance/workspace/data/knowledge/compliance" in text:
            fail("checklist_query_tool.py still falls back to runtime workspace data")
        if "/Users/HY-yin/Documents/Codex-Compliance-System/artifacts/candidate" in text:
            fail("checklist_query_tool.py must not fall back to candidate artifacts")

    if not PROMOTION_REQUEST_TOOL.exists():
        fail(f"missing submit_promotion_request runtime tool: {PROMOTION_REQUEST_TOOL}")
    promotion_tool_text = PROMOTION_REQUEST_TOOL.read_text(encoding="utf-8")
    for needle in [
        'name="submit_promotion_request"',
        'name="withdraw_promotion_request"',
        'name="amend_promotion_request"',
        "HERMES_SESSION_USER_ID",
        "submit_promotion_request_requires_P1_or_higher",
        "withdraw_promotion_request_requires_P1_or_higher",
        "amend_promotion_request_requires_P1_or_higher",
        "PROMOTION_REQUEST_SUBMITTED",
        "CODEX_REVIEW_REQUIRED",
        "WITHDRAWN",
        "SUPERSEDED",
        "AMENDED",
        "live_write_performed",
        "REQUEST_QUEUE",
        "source_files",
        "source_kind",
        "source_classification_reason",
        "promotion_scope",
        "knowledge_source_upload",
        "structured_database_build",
        "multi_source_files_supported",
        "temp_db_path",
        "validation_artifact_path",
    ]:
        if needle not in promotion_tool_text:
            fail(f"submit_promotion_request tool missing required marker: {needle}")
    for forbidden in [
        "manifests/canonical_sources.json",
        "docs/state/approved_sources.md",
        "compliance_capability_map.v1.json",
    ]:
        if f"open({forbidden}" in promotion_tool_text:
            fail(f"submit_promotion_request tool must not update accepted source file: {forbidden}")

    if not COMPLIANCE_WORKFLOW_TOOL.exists():
        fail(f"missing compliance workflow runtime tool: {COMPLIANCE_WORKFLOW_TOOL}")
    workflow_tool_text = COMPLIANCE_WORKFLOW_TOOL.read_text(encoding="utf-8")
    for needle in [
        'name="intake_source_files"',
        'name="create_p3_approval_request"',
        'name="send_p3_approval_notification"',
        'name="record_promotion_approval"',
        "controlled_source_intake_no_shell_required",
        "codex_thread_approval_only_wecom_push_disabled",
        "intake_source_files_requires_P1_or_higher",
        "create_p3_approval_request_requires_P3_or_higher",
        "wecom_p3_approval_notification_disabled_use_codex_thread",
        "record_promotion_approval_requires_P3_or_higher",
        "load_profile_env_for_wecom_delivery",
        "live_write_performed",
    ]:
        if needle not in workflow_tool_text:
            fail(f"compliance workflow tool missing required marker: {needle}")

    queue_guard_marker = "promotion_request_queue_requires_submit_promotion_request_tool"
    if not FILE_TOOLS.exists():
        fail(f"missing file_tools.py runtime write guard: {FILE_TOOLS}")
    if queue_guard_marker not in FILE_TOOLS.read_text(encoding="utf-8"):
        fail("file_tools.py must block generic writes to the compliance promotion request queue")
    if not APPROVAL_TOOL.exists():
        fail(f"missing approval.py runtime command guard: {APPROVAL_TOOL}")
    if queue_guard_marker not in APPROVAL_TOOL.read_text(encoding="utf-8"):
        fail("approval.py must block terminal writes to the compliance promotion request queue")


def check_memory_policy() -> None:
    config_text = CONFIG.read_text(encoding="utf-8")
    if "memory_enabled: false" not in config_text:
        fail("compliance profile memory must be disabled for trial runtime governance")
    if "user_profile_enabled: false" not in config_text:
        fail("compliance profile user profile memory must be disabled; source pointers live in hermes-local")
    for toolset in ["memory", "session_search"]:
        if "disabled_toolsets:" not in config_text or toolset not in config_text:
            fail(f"compliance profile must disable the {toolset} toolset")
    memories_dir = PROFILE_HOME / "memories"
    if memories_dir.exists():
        memory_files = [p for p in memories_dir.rglob("*") if p.is_file()]
        if memory_files:
            fail(f"runtime memory files must not exist for compliance profile: {memory_files}")
    if STATE_DB.exists():
        state_bytes = STATE_DB.read_bytes()
        stale_state_needles = [
            "目前未存储任何关于 Hermes Agent 用户等级体系的信息".encode("utf-8"),
            "Hermes Agent 本身没有内置用户等级分类".encode("utf-8"),
            "没有任何权限检查逻辑".encode("utf-8"),
            b"/Users/HY-yin/Documents/Codex-Compliance-System/artifacts/candidate/task10_permission_model.v1.json",
        ]
        for needle in stale_state_needles:
            if needle in state_bytes:
                fail(f"state.db contains stale governance/session text: {needle!r}")

def check_runtime_skill_policy() -> None:
    if not NO_BUNDLED_SKILLS.exists():
        fail(f"compliance profile must opt out of generic bundled skills: {NO_BUNDLED_SKILLS}")
    config_text = CONFIG.read_text(encoding="utf-8")
    if "skills_readonly" not in config_text:
        fail("compliance WeCom platform must use the read-only skills_readonly toolset")
    if "\n  - skills\n" in config_text or "\n    - skills\n" in config_text:
        fail("compliance WeCom platform must not enable write-capable skills toolset")
    if f"- {SOURCE_SKILLS}" not in config_text:
        fail("compliance profile skills.external_dirs must point to hermes-local accepted skills")
    if "curator:\n  enabled: false" not in config_text:
        fail("compliance runtime curator must be disabled so it cannot create runtime skills")
    if ACCEPTED_SKILLS_MANIFEST.exists():
        fail(f"runtime accepted skill manifest is obsolete under direct-source binding: {ACCEPTED_SKILLS_MANIFEST}")
    if RUNTIME_SKILLS.exists():
        runtime_skill_files = sorted(RUNTIME_SKILLS.rglob("SKILL.md"))
        if runtime_skill_files:
            fail(f"runtime skill copies must not exist under compliance profile: {runtime_skill_files}")
    if SKILLS_PROMPT_SNAPSHOT.exists():
        snapshot = load_json(SKILLS_PROMPT_SNAPSHOT)
        if snapshot.get("manifest") or snapshot.get("skills"):
            fail("runtime skills prompt snapshot must not cache local compliance skill copies")

def check_runtime_tool_registry() -> None:
    python = HERMES_AGENT / "venv/bin/python"
    if not python.exists():
        fail(f"missing Hermes runtime Python: {python}")
    env = os.environ.copy()
    env["HERMES_HOME"] = str(PROFILE_HOME)
    env["PYTHONPATH"] = str(HERMES_AGENT)
    env["PYTHONPYCACHEPREFIX"] = "/private/tmp/hermes_pycache"
    code = (
        "import json\n"
        "from hermes_cli.config import load_config\n"
        "from hermes_cli.tools_config import _get_platform_tools\n"
        "from model_tools import get_tool_definitions\n"
        "cfg = load_config()\n"
        "enabled = sorted(_get_platform_tools(cfg, 'wecom'))\n"
        "disabled = (cfg.get('agent') or {}).get('disabled_toolsets') or None\n"
        "tools = get_tool_definitions(enabled_toolsets=enabled, disabled_toolsets=disabled, quiet_mode=True)\n"
        "names = [t.get('function', {}).get('name') for t in tools]\n"
        "print(json.dumps({'enabled_toolsets': enabled, 'tool_names': names}))\n"
    )
    result = subprocess.run(
        [str(python), "-c", code],
        cwd=str(HERMES_AGENT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        fail(f"Hermes runtime tool registry check failed: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        fail(f"Hermes runtime tool registry returned invalid JSON: {exc}")
    enabled = set(payload.get("enabled_toolsets") or [])
    names = set(payload.get("tool_names") or [])
    if "compliance" not in enabled:
        fail("WeCom platform_toolsets must include the dedicated compliance toolset")
    if "skills_readonly" not in enabled or "skills" in enabled:
        fail("WeCom platform_toolsets must expose read-only skills without write-capable skills toolset")
    if "skill_manage" in names:
        fail("WeCom session must not expose skill_manage for compliance direct-source runtime")
    for tool_name in [
        "skills_list",
        "skill_view",
        "intake_source_files",
        "submit_promotion_request",
        "withdraw_promotion_request",
        "amend_promotion_request",
        "create_p3_approval_request",
        "send_p3_approval_notification",
        "record_promotion_approval",
    ]:
        if tool_name not in names:
            fail(f"WeCom session tool definitions do not expose {tool_name}")


def check_active_session_freshness() -> None:
    for session_key, entry in active_session_entries():
        session_id = entry.get("session_id")
        if not session_id:
            fail(f"active session index entry missing session_id: {session_key}")
        session_path = SESSIONS_DIR / f"session_{session_id}.json"
        if not session_path.exists():
            fail(f"active session index points to missing session file: {session_path}")
        session = load_json(session_path)
        prompt = session.get("system_prompt") or ""
        missing_markers = [
            marker for marker in SESSION_PROMPT_REQUIRED_MARKERS if not contains_words(prompt, marker)
        ]
        if missing_markers:
            fail(
                "active Hermes session is stale and lacks accepted runtime markers: "
                f"{session_key} {session_path} missing={missing_markers}"
            )
        tool_names = extract_tool_names(session.get("tools"))
        missing_tools = {
            "intake_source_files",
            "submit_promotion_request",
            "withdraw_promotion_request",
            "amend_promotion_request",
            "create_p3_approval_request",
            "send_p3_approval_notification",
            "record_promotion_approval",
        } - tool_names
        if missing_tools:
            fail(
                "active Hermes session does not expose required promotion request lifecycle tools; "
                f"missing={sorted(missing_tools)} runtime session refresh required: {session_key} {session_path}"
            )


def check_access_gate_policy() -> None:
    if not ACCESS_GATE.exists():
        fail(f"missing compliance gateway access gate: {ACCESS_GATE}")
    if not GATEWAY_RUN.exists():
        fail(f"missing gateway runner: {GATEWAY_RUN}")

    gate_text = ACCESS_GATE.read_text(encoding="utf-8")
    gate_required = [
        "def evaluate_source",
        "compliance_permission_model.v1.json",
        "wecom_account_bindings",
        "deny_by_default",
        "UNBOUND_DENIAL",
        "FAIL_CLOSED_DENIAL",
        "REQUEST_SUBMITTED",
        "APPROVAL_REPLY_INTAKE_MARKER",
        "CODEX_THREAD_APPROVAL_ONLY_MARKER",
        "codex_thread_approval_only_wecom_push_disabled",
        "def handle_p3_approval_reply",
        "format_request_submitted_message",
        "request access",
        "AUDIT_LOG",
    ]
    for needle in gate_required:
        if needle not in gate_text:
            fail(f"compliance access gate missing required marker: {needle}")

    run_text = GATEWAY_RUN.read_text(encoding="utf-8")
    run_required = [
        "from gateway.compliance_access_gate import",
        "append_audit_event",
        "append_access_request",
        "evaluate_source",
        "format_request_submitted_message",
        "handle_p3_approval_reply",
        "_compliance_gate_authorized",
        "Compliance P3 approval reply handled before agent dispatch",
        "Compliance access denied before agent dispatch",
        "_access_request_response",
        "return _compliance_decision.response_text",
    ]
    for needle in run_required:
        if needle not in run_text:
            fail(f"gateway runner is not wired to hard compliance access gate: {needle}")
    gate_pos = run_text.find("from gateway.compliance_access_gate import")
    agent_pos = run_text.find("_agent_result = await self._handle_message_with_agent", gate_pos)
    if gate_pos < 0 or agent_pos < 0 or gate_pos > agent_pos:
        fail("compliance access gate must run before _handle_message_with_agent")


def check_launch_agents() -> None:
    if GENERIC_PLIST.exists():
        fail(f"generic LaunchAgent plist must not exist: {GENERIC_PLIST}")
    if launchctl_service_loaded(GENERIC_LABEL):
        fail(f"generic LaunchAgent must not be loaded: {GENERIC_LABEL}")

    plist = read_plist(COMPLIANCE_PLIST)
    if plist.get("Label") != COMPLIANCE_LABEL:
        fail("compliance LaunchAgent has wrong Label")
    env = plist.get("EnvironmentVariables", {})
    if env.get("HERMES_HOME") != str(PROFILE_HOME):
        fail("compliance LaunchAgent HERMES_HOME must point to the compliance profile")
    args = plist.get("ProgramArguments", [])
    if not args or args[0] != str(GUARD_SCRIPT):
        fail("compliance LaunchAgent must start through hermes-compliance-gateway-guard.sh")
    stdout = plist.get("StandardOutPath", "")
    stderr = plist.get("StandardErrorPath", "")
    if str(PROFILE_HOME / "logs") not in stdout or str(PROFILE_HOME / "logs") not in stderr:
        fail("compliance LaunchAgent logs must be profile-scoped")


def main() -> int:
    check_source_files()
    check_soul_binding()
    check_permission_model()
    check_live_data_root_binding()
    check_memory_policy()
    check_runtime_skill_policy()
    check_runtime_tool_registry()
    check_active_session_freshness()
    check_access_gate_policy()
    check_launch_agents()
    print("PASS: Hermes compliance runtime governance preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
