---
name: compliance-legal-customer-pipeline
description: Draft candidate-only legal/customer source clauses, original-text markings, interpretation packets, and update signals with source hashes and human review requirements.
---

# Compliance Legal And Customer Pipeline

Use this skill for legal source acquisition candidates, legal update signals,
customer standard intake, clause candidates, original text marking, and
interpretation packets.

Candidate pipeline references:

- Use pointer-only references. Do not treat any skill reference as the source
  of truth for current live counts, source-gap status, active table/view names,
  queue paths, or classification versions.
- VBPL/API and crosswalk references describe method only.
- Official-text acquisition, legal-priority, clause-library, and baseline
  references are guardrails only; live facts must come from the live catalog,
  the referenced manifest, and sqlite schema.

Live legal/customer data status:

- Live knowledge-base catalog:
  `/Users/HY-yin/hermes-local/data/knowledge/compliance/knowledge_base_catalog.v1.json`
- Do not use this skill file as the source of truth for live legal/customer
  counts, legal text/clause availability, active table/view names, queue paths,
  source-gap status, or classification versions.
- Resolve live source sets, legal metadata databases, legal original-text/clause
  databases, manifests, query views, and blocked-use rules from the live catalog
  at query time.
- Accepted live customer requirement source files may exist in the live catalog,
  but derived customer requirement databases or clause datasets must be
  separately verified from the catalog before use.
- Runtime workspace records are not live accepted legal/customer authority and
  must be labeled `RUNTIME_WORKSPACE_NOT_LIVE` if explicitly inspected.
- Task 11 artifacts are candidate pipeline evidence only; they do not promote
  source files or legal/customer clauses to live use.
- When reporting legal original text or clause data, use only live catalog /
  manifest / sqlite facts and keep output to source-text lookup or pre-
  requirement review unless a separate approved workflow exists.

Rules:

- For legal metadata, source acquisition, legal original text, or clause lookup,
  first read the live catalog and resolve the current database/manifest/query
  view from there.
- Do not answer from memory, old skill prose, historical references, runtime
  workspace queues, or candidate artifacts unless the user explicitly asks for
  non-live inspection.
- For legal original-text or clause questions, answer only within the live
  catalog's allowed source-text lookup scope. Do not convert clause text into
  requirements, checklist obligations, legal advice, compliance conclusions, or
  confirmed baseline.
- Inspect runtime workspace or candidate legal/customer records only when the
  user explicitly asks for non-live inspection, and label the answer
  `RUNTIME_WORKSPACE_NOT_LIVE` or `CANDIDATE_ONLY`.
- Return `BLOCKED` for unregistered source, hash mismatch, missing original
  text, missing review marker, or requested output family not approved in the
  live catalog.
- When this skill becomes complex or stuck, pause and consider visible tools:
  use `todo` for lightweight step tracking; consider `delegate_task` for
  independent source discovery, QC, schema checks, comparison, or output
  packaging; use domain workflow tools before generic shell/file writes. Do not
  force these tools for simple answers and do not pretend to use a tool that is
  not visible.
- If the same fetch, parse, search, or code path fails twice, stop hard-running
  the same approach and report the blocker, alternate tool/path considered, and
  whether Codex or human review is needed.
- After creating candidate legal/customer outputs, state the generated paths,
  candidate/not-live status, purpose of each artifact, residual risk, and next
  actor.

Forbidden:

- Legal advice, compliance conclusion, source-sufficiency conclusion, or direct
  database update.
- Treating candidate pipeline artifacts or `.hermes` workspace JSONL as live
  legal/customer requirements when live hermes-local metadata exists.
- Treating the live legal document metadata index as official legal text or a
  clause database.
- Treating VBPL as complete jurisdiction coverage or treating a partial
  keyword/sample VBPL fetch as a completed legal/regulatory index.

Pitfalls:

- **VBPL API control characters.** VBPL JSON responses can contain raw bytes
  (0x00-0x1f) that break `json.loads()`. Strip with
  `re.sub(r'[\\x00-\\x08\\x0b-\\x0c\\x0e-\\x1f]', '', raw)` before parsing.
- **VBPL pagination field.** `/qtdc/public/doc/all` ignores `pageIndex`. Use
  `pageNumber` and `pageSize`; `pageNumber=0` and `pageNumber=1` both return
  the first page, while `pageNumber=2` returns the next page. Full-index fetches
  must detect duplicate IDs across pages and stop/fail if page counts do not
  increase.
- **Metadata index is not source text archive.** `docAbs` may be present in
  search responses, but a full metadata index must not claim official text
  archive or clause-readiness unless source text is separately archived, hashed,
  and reviewed.

<!-- OFFICIAL_TEXT_ACQUISITION_QUEUE_START -->
- Historical official-text acquisition queue artifacts are not live query
  targets and must not be used as the current execution list.
- For any new official-text acquisition planning, first read the live
  knowledge-base catalog and current classification/executable-view artifacts,
  then build a fresh queue from those current sources.
- Do not use runtime workspace queue paths, old priority labels, or old queue
  counts as live knowledge.
<!-- OFFICIAL_TEXT_ACQUISITION_QUEUE_END -->




<!-- LEGAL_SOURCE_PRIORITY_CLASSIFICATION_STANDARD_START -->
- Before handling legal/regulatory/QCVN/source-priority work, read:
  `references/legal_source_priority_classification_standard.v1.zh.md`
- Default legal metadata queries must use the canonical legal document metadata
  index, not the raw A0+B1 source-row index.
- Historical Hermes legal priority refs and legal atoms may guide priority and
  domain coverage only; they are not official legal sources, clauses,
  requirements, risks, or compliance conclusions.
- Task14 `CANDIDATE_PASS` is engineering validation only. Candidate content
  review needs P2; live promotion needs distinct P3 approval, source hashes,
  traceability, audit log, and rollback plan.
<!-- LEGAL_SOURCE_PRIORITY_CLASSIFICATION_STANDARD_END -->

<!-- LEGAL_PRIORITY_CLASSIFICATION_V2_METHOD_START -->
- Before creating, revising, or judging legal metadata priority ratings, read:
  `references/legal_priority_classification_v2_method.zh.md`
- Use historical Hermes `legal_priority_refs` and `legal_atom_sources` only as
  priority/coverage hints. They are not official legal text, clause evidence,
  compliance conclusions, or promotion evidence.
- Apply hard gates before scoring: fully inactive/unknown status cannot enter
  P0/P1/P2; partial-effective records and legacy/current-status conflicts may
  enter the acquisition queue only with amendment-chain/source-review flags;
  province/city, district/ward, other, or unknown authorities cannot
  enter P0/P1 without factory-location/applicability scope matching; broad
  words such as `an toàn`, `bảo hiểm`, `nước ngoài`, `kỹ thuật`, and
  `xây dựng` cannot independently raise priority.
- When a translation row (`bản dịch văn bản`) and a Vietnamese official row
  share the same legal number, use the Vietnamese official row for P0/P1/OT0/OT1
  acquisition and treat the translation row as reference only.
- For original text acquisition, prefer parseable HTML/API/structured text.
  PDFs are source evidence or manual review material, not the preferred original
  text archive. Third-party sources such as `https://thuvienphapluat.vn`,
  LawNet, LuatVietnam, Hugging Face/GitHub datasets, and old Hermes archives may
  be used as candidate text/discovery/cross-check sources only; keep
  candidate-source flags, URL, fetch time, hash, and official/human verification
  status.
- P0/P1 must have a business-domain, exact historical ID/atom, or clear
  HSE/QCVN signal. Generic QCVN or broad core-law metadata is review material,
  not automatic P0/P1.
- P1/OT1 cannot be assigned from broad metadata alone. National authority,
  active status, implementing document type, and broad domain keywords must be
  treated as P2/OT2 candidates unless there is a specific obligation/factory
  applicability signal, exact historical Hermes/text/atom support, clear
  HSE/QCVN support, core-law support, or status-conflict/amendment-chain review
  need.
- Public-sector or administrative contexts such as civil servants, public
  institutions, military/police staffing, statistics, finance/budget,
  government payroll, job-position management, awards, and public education are
  low-relevance by default. Keep them out of P1/OT1 unless they also contain a
  concrete factory obligation, QCVN/HSE trigger, or exact historical support.
- Keep business priority and original-text acquisition need as separate
  dimensions. Read `original_text_acquisition_need` before making a fetch queue:
  OT0 means immediate blocking official text fetch; OT1 means fetch before
  section/requirement work; OT2 means profile/cross-check first; OT3 means
  monitor/reference only.
- Legal metadata priority outputs are candidate-only acquisition planning
  artifacts. They do not create legal clauses, requirement atoms, legal advice,
  compliance status, or live knowledge-base records.
<!-- LEGAL_PRIORITY_CLASSIFICATION_V2_METHOD_END -->

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

<!-- FACTORY_LEGAL_BASELINE_ASSESSMENT_START -->
- Factory legal baseline answers must be source-gated by the live catalog,
  current manifest, current sqlite schema, official text status, revision-chain
  status, GSP subject profile, and explicit legal-owner approval.
- Do not rely on hardcoded table names, row counts, or historical method files
  in this skill as live facts.
- Never answer that a regulation is confirmed factory baseline or currently
  applicable to GSP unless a separate approved workflow and legal-owner approval
  say so.
<!-- FACTORY_LEGAL_BASELINE_ASSESSMENT_END -->

<!-- FACTORY_LEGAL_BASELINE_REVIEW_V1_START -->
- Historical factory-baseline review artifacts are audit evidence only unless
  the live catalog exposes them as the current active query target.
- For live answers, read the catalog and current sqlite schema. Do not use
  stale table names or old row counts from this skill.
<!-- FACTORY_LEGAL_BASELINE_REVIEW_V1_END -->

<!-- FACTORY_LEGAL_BASELINE_GAP_MODULES_V1_START -->
- Historical gap-module artifacts are planning diagnostics only, not regulations
  and not current legal classification rows unless the live catalog explicitly
  exposes them as active support data.
- Do not use gap-module prose to claim baseline completeness or legal
  applicability.
<!-- FACTORY_LEGAL_BASELINE_GAP_MODULES_V1_END -->

<!-- LEGAL_PRIORITY_CLASSIFICATION_V3_START -->
- Historical priority-classification method. Do not use this block as a live
  query target. Read the live catalog for the active classification table/view.
<!-- LEGAL_PRIORITY_CLASSIFICATION_V3_END -->

<!-- LEGAL_PRIORITY_CLASSIFICATION_V31_START -->
- Historical priority-classification method. Do not use this block as a live
  query target. Read the live catalog for the active classification table/view.
<!-- LEGAL_PRIORITY_CLASSIFICATION_V31_END -->
