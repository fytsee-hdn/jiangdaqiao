---
name: compliance-source-lifecycle
description: Prepare candidate source intake, registry, upload archive, quarantine inventory, and source-promotion readiness checks without promoting source automatically.
---

# Compliance Source Lifecycle

Use this skill for source intake, source classification, source registry,
archive records, upload protocol, quarantine inventory, and source lifecycle gap
checks.

Accepted evidence:

- `artifacts/candidate/task11_source_type_taxonomy.v1.json`
- `artifacts/candidate/task11_upload_archive_protocol.v1.json`
- `artifacts/candidate/task11_source_registry_archive.v1.json`
- `schemas/source_lifecycle/source_registry.schema.json`
- `schemas/source_lifecycle/source_archive_record.schema.json`

Live source status:

- Approved live source-file set: `customer_requirements:ikea_iway_agent_readable_requirements:2026_05_25`.
- The approved live source manifest is `/Users/HY-yin/hermes-local/data/knowledge/compliance/source_manifests/customer_requirements/ikea_iway_agent_readable_requirements-2026_05_25.manifest.json`.
- `manifests/canonical_sources.json` and `docs/state/approved_sources.md`
  register the same approved source files.
- These files are source-file authority only. Structured database rows, clauses,
  checklist atoms, risk records, and compliance conclusions remain unpromoted.
- `.hermes/profiles/compliance/workspace/data/knowledge/compliance/`,
  `artifacts/candidate/`, and discovered Desktop files are not live source
  authority.

Rules:

- Use the controlled `intake_source_files` tool for uploaded source archives or
  source files whenever it is visible. This tool copies/extracts into runtime
  source intake workspace and calculates sha256 hashes without shell unzip/cp
  commands. Marker: `controlled_source_intake_no_shell_required`.
- Require source path, source type, owner, origin, version/date, and hash.
- Classify every source before promotion request intake:
  customer standards, customer codes of conduct, supplier codes of conduct, and
  IWAY-like customer requirements are `customer_requirement`; laws,
  regulations, statutory requirements, and legal-authority standards are
  `legal_source`.
- Keep knowledge source upload separate from structured database build.
  `knowledge_source_upload` registers source files and hashes only;
  `structured_database_build` creates clause records, checklist atoms, risk
  records, or product database rows. Database build work must be explicitly
  requested and routed to the database build and validation skills.
- Prepare candidate registry/archive/quarantine records only.
- If the user asks to make a source official or live, route to
  `compliance-live-data-promotion-request` and collect promotion request fields.
  Do not promote the source from this skill.
- Return `BLOCKED` for ordinary user questions that need live approved source
  facts until a human-approved promotion writes a live manifest and source files
  under `/Users/HY-yin/hermes-local/data/knowledge/compliance/`.
- Inspect runtime workspace, candidate, or discovered-source files only when the
  user explicitly asks for that non-live inspection, and label the answer
  `RUNTIME_WORKSPACE_NOT_LIVE`, `CANDIDATE_ONLY`, or `TEST_DATA`.
- Return `BLOCKED` for missing source, missing hash, schema mismatch, or
  unregistered source.

Forbidden:

- Using shell unzip/cp/mv or generic file writes for routine source intake when
  `intake_source_files` is visible.
- Direct canonical source write.
- Automatic source promotion.
- Source sufficiency or compliance conclusion.
- Treating `.hermes`, `artifacts/candidate`, or Desktop files as approved live
  source authority.
