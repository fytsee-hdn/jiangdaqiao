---
name: compliance-live-data-promotion-request
description: Submit live business data promotion requests and run preliminary material completeness review without promoting data or approving live use.
---

# Compliance Live Data Promotion Request

Use this skill when a user asks to make source files, legal/customer
requirements, checklists, GSP standards, evidence matrices, source registers,
factory/risk records, or product databases become official live data.

Hermes role:

- Intake source and promotion intent.
- Check whether required fields and evidence are present.
- Submit or describe a runtime promotion request packet.
- Hand the request to Codex for independent verification.

Runtime request queue:

- `/Users/HY-yin/.hermes/profiles/compliance/promotion_requests/`

Submission rule:

- Hermes must submit runtime promotion packets only through the
  `submit_promotion_request` tool.
- Hermes must classify the source before submission:
  `source_kind=customer_requirement` for customer standards, customer codes of
  conduct, supplier codes of conduct, and customer requirement packs such as
  IWAY; `source_kind=legal_source` only for laws, regulations, statutory
  requirements, or legal-authority standards.
- Hermes must state `source_classification_reason` before submission. If it
  cannot distinguish customer-vs-legal source authority, it must return
  `PRELIMINARY_REVIEW_INCOMPLETE` and ask for clarification.
- Hermes must choose a `promotion_scope` before submission:
  `knowledge_source_upload` for source-file upload/registration only,
  `structured_database_build` for clause extraction, requirement atomization,
  checklist/risk/database outputs, and `source_and_database_build` only when
  both are requested.
- A customer PDF upload is not a database build. Do not require `temp_db_path`,
  clause atoms, checklist atoms, or risk records for `knowledge_source_upload`.
- Hermes must not use generic `write_file`, `patch`, shell redirection,
  `tee`, `cp`, `mv`, scripts, or ad hoc JSON creation to write directly into
  the runtime request queue.
- The queue is controlled-tool-only:
  `promotion_request_queue_requires_submit_promotion_request_tool`.

Request lifecycle tools:

- Hermes may use `withdraw_promotion_request` to withdraw a pending request
  owned by the current WeCom requester. P3 may withdraw any pending request.
- Hermes may use `amend_promotion_request` to correct source kind, data
  family, promotion scope, source files, or evidence paths. The old active
  request becomes `SUPERSEDED`, and the new request requires Codex review.
- These lifecycle tools do not approve promotion, reject promotion, or write
  live data.

P3 approval handoff:

- After Codex review returns `CANDIDATE_PASS`, human P3 approval must be given
  in the Codex thread and recorded by Codex.
- `create_p3_approval_request` may exist as legacy/review-packet tooling, but
  it does not create a valid WeCom approval route.
- WeCom approval notifications and WeCom approval replies are disabled and are
  not valid approval evidence.
- Hermes must not send or resend P3 approval notifications and must not treat
  WeCom messages such as `同意`, `批准`, or `approve` as promotion approval.
- Marker: `codex_thread_approval_only_wecom_push_disabled`.
- Approval recording still does not write live data. Codex must perform any
  live write after approval.
- Do not say you can trigger Codex, trigger live write, or perform the final
  promotion step from WeCom. Say Codex must do it.
- For `knowledge_source_upload`, call the result a promoted source file or live
  knowledge source, not a formal database. A database exists only after a
  separate `structured_database_build` approval and promotion.

Tool visibility and stale-session rule:

- If the current session does not expose `submit_promotion_request`, Hermes
  must treat the runtime as `BLOCKED_STALE_RUNTIME_SESSION`.
- Hermes must not claim that the tool is undeployed from conversation-visible
  tools alone. A missing tool in the current session usually means the WeCom
  session is stale and runtime session refresh is required.
- Hermes must not create `BLOCKED_BY_TOOL_GAP` promotion drafts, offer manual
  queue moves, or fall back to generic file writes. The only valid queue
  submission is an actual `submit_promotion_request` call.
- If the tool is not visible or a submission call cannot be made, reply with
  `BLOCKED_STALE_RUNTIME_SESSION`, explain that the runtime session/tool
  binding must be refreshed, and stop.

Temporary candidate artifacts:

- Candidate extraction outputs, temporary databases, manifests, and validation
  reports must be written under runtime workspace, for example:
  `/Users/HY-yin/.hermes/profiles/compliance/workspace/promotion_artifacts/<draft_id>/`
- Do not place temporary databases or derived JSON/JSONL outputs under the
  promotion request queue. The queue is only for the controlled request packet.

Required request fields:

- requester platform, WeCom ID, and permission role check result
- requested action: `submit_promotion_request`
- data family
- source path, source type, source owner, origin, version/date, language
- source kind, source classification reason, and promotion scope
- source hash, hash algorithm, and how the hash was obtained; for multi-file
  source sets, include `source_files` with each file's absolute path and sha256
- candidate/runtime/discovered-source label
- candidate artifact paths or runtime record paths, including `temp_db_path`,
  `source_manifest_path`, and `validation_artifact_path` when generated or when
  the promotion scope includes a structured database build
- intended live scope
- expected live target family under
  `/Users/HY-yin/hermes-local/data/knowledge/compliance/`
- preliminary missing evidence list
- rollback requirement
- explicit note that Codex verification and P3 human approval are required
- explicit note that `record_promotion_approval` records only the P3 decision
  and does not perform live promotion

Preliminary review checks:

- Source path and source hash are present, or `source_files` is present with
  one absolute path and sha256 per file.
- Data family is one of source_register, legal_sources, customer_requirements,
  checklists, gsp_standards, evidence_matrix, factory_risk_records, or
  compliance_product_database.
- Customer standards and customer codes of conduct use
  `data_family=customer_requirements`, `source_kind=customer_requirement`, and
  a customer source type such as `customer_standard`.
- Laws, regulations, statutory requirements, and legal-authority standards use
  `data_family=legal_sources`, `source_kind=legal_source`, and a legal source
  type such as `law` or `regulation`.
- `knowledge_source_upload` means source-file registration only. It is separate
  from structured database build, and it does not claim that clauses, checklist
  atoms, risk records, or live database rows have been created.
- Candidate/runtime/discovered-source status is labeled.
- Intended live scope is explicit.
- Request does not ask Hermes to write live files, update manifests, update
  capability maps, or approve promotion.

Allowed statuses:

- `BLOCKED`
- `PRELIMINARY_REVIEW_INCOMPLETE`
- `PROMOTION_REQUEST_SUBMITTED`
- `CODEX_REVIEW_REQUIRED`
- `WITHDRAWN`
- `SUPERSEDED`
- `AMENDED`

Forbidden:

- Promoting data to live.
- Updating `/Users/HY-yin/hermes-local/data/knowledge/compliance/`.
- Updating `manifests/canonical_sources.json`, `docs/state/approved_sources.md`,
  `compliance_capability_map.v1.json`, runtime baseline, SOUL, memory, or skills.
- Treating preliminary review as Codex verification.
- Treating request submission as P3 promotion approval.
- Treating `create_p3_approval_request` or `record_promotion_approval` as a
  live write or approval to expand source-only scope into database scope.
- Making legal, compliance, source-sufficiency, risk, applicability, or audit
  conclusions.
