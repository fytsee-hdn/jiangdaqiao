---
name: compliance-database-query
description: Answer GSP compliance database questions only from live knowledge-base catalogs, disk-backed databases, or explicitly requested candidate artifacts with cited paths and counted fields.
---

# Compliance Database Query

Use this skill for questions about database counts, database contents, query
indexes, checklist records, evidence links, status indexes, traceability, or
source-backed lookup results.

Live database status:

- The live knowledge-base catalog is
  `/Users/HY-yin/hermes-local/data/knowledge/compliance/knowledge_base_catalog.v1.json`.
- Do not use this skill file as the source of truth for live database paths,
  counts, source-gap status, legal text/clause availability, active table/view
  names, or classification versions.
- Resolve every live database path, manifest path, table/view name, count, and
  blocked-use rule from the live catalog, the referenced manifest, and the
  sqlite schema at query time.
- Candidate and runtime workspace artifacts are not live accepted data unless
  the user explicitly asks for candidate/runtime inspection; label them
  `CANDIDATE_ONLY` or `RUNTIME_WORKSPACE_NOT_LIVE`.
- No accepted live compliance product database, checklist database, GSP
  standard database, evidence matrix, requirement atom database, risk database,
  legal conclusion, compliance conclusion, or audit-pass record is configured
  unless the live catalog says otherwise.

Rules:

- First classify whether the user is asking about a compliance product database,
  legal metadata index, legal original-text/clause lookup, source file set,
  candidate artifact, or Hermes runtime state.
- Never answer database facts from memory, session search, or conversational
  recall.
- For legal document metadata, legal source index coverage, whether a legal
  document appears in the index, or canonical legal document counts, read the
  live catalog and resolve the current canonical legal document metadata index,
  active manifest, and active table/view before querying.
- For A0/B1 identity or status-monitoring, resolve the live crosswalk from the
  catalog before querying.
- For official legal text or clause lookup, read the live catalog and clause
  library manifest first. If a live clause/original-text database is configured
  there, answer only within its allowed source-text lookup scope. If not,
  return `BLOCKED`.
- For requirements, checklist database, checklists, risks, legal advice,
  compliance conclusions, audit-pass claims, or confirmed baseline claims,
  return `BLOCKED` unless the live catalog shows a separate approved workflow
  and database for that exact output family.
- For source-file existence or source-file metadata, answer from the live
  knowledge-base catalog or live source manifest when the requested source set
  is registered.
- Do not read test/candidate artifacts unless the user explicitly asks for
  `test`, `candidate`, `legacy`, or artifact inspection.
- Do not read runtime workspace data unless the user explicitly asks for runtime
  workspace inspection, and label the result `RUNTIME_WORKSPACE_NOT_LIVE`.
- Before giving a count, read the target artifact from disk and identify the
  SQLite table, JSON field, or collection counted.
- Include the artifact path, schema/version if present, count method, and any
  ambiguity.
- If the target artifact is missing, stale, ambiguous, or outside the allowed
  profile scope, return `BLOCKED` with the missing evidence.

Required output fields:

- `status`
- `database_or_index_path`
- `field_or_collection_counted`
- `count_method`
- `residual_risk`

Allowed statuses:

- `LIVE_ALLOWED_METADATA_ONLY`
- `BLOCKED`
- `CANDIDATE_ONLY`
- `TEST_DATA`
- `RUNTIME_WORKSPACE_NOT_LIVE`

<!-- LEGAL_PRIORITY_CLASSIFICATION_V2_LIVE_TABLE_START -->
## Live Legal Metadata Query Guard

- Do not use this skill file as the source of truth for live table names, view
  names, row counts, priority counts, version status, or baseline status.
- For every live legal metadata question, first read the live knowledge-base
  catalog JSON and use the catalog's current legal metadata entry, active table,
  active view, manifest path, and blocked-use rules.
- If this skill, memory, old logs, or historical references conflict with the
  live catalog, manifest, or sqlite schema, the live catalog/manifest/sqlite
  wins and the prose is stale.
- Classification labels are metadata/coverage triage only. They are not legal
  applicability conclusions and not confirmed factory baseline.
- Requirement atoms, checklists, risk ratings, legal advice, compliance
  conclusions, audit-pass claims, and confirmed factory baseline claims require
  a separate approved workflow.
<!-- LEGAL_PRIORITY_CLASSIFICATION_V2_LIVE_TABLE_END -->

- Original text and clause library method:
  `references/legal_original_text_clause_library_method.zh.md`

<!-- LEGAL_ORIGINAL_TEXT_CLAUSE_LIBRARY_V1_START -->
## Live Legal Clause Query Guard

- Do not use this skill file as the source of truth for live clause-library
  counts, status, source-gap state, table names, or query-view names.
- For every original-text or clause lookup, read the live knowledge-base catalog
  JSON, then the live clause-library manifest named by the catalog, then query
  the sqlite database/view named there.
- If skill prose conflicts with the live catalog, manifest, or sqlite counts,
  the live catalog/manifest/sqlite wins and this prose is stale.
- Use the clause library only for original legal text, article/clause text
  lookup, source traceability, and pre-requirement clause review workflow.
- Do not derive requirement atoms, checklists, risks, legal opinions,
  compliance conclusions, audit-pass claims, applicability conclusions, or
  confirmed factory baseline from clause lookup without a separate approved
  workflow.
<!-- LEGAL_ORIGINAL_TEXT_CLAUSE_LIBRARY_V1_END -->
