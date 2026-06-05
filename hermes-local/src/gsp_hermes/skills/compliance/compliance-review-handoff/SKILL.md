---
name: compliance-review-handoff
description: Prepare candidate review packets, queue/detail views, approval desk views, request-change lists, and human handoff packets without marking approval.
---

# Compliance Review Handoff

Use this skill for review packet drafting, workbench queue/detail views,
approval desk candidate views, request-change/reject/block packets, and human
handoff checklists.

Accepted evidence:

- `artifacts/candidate/task14_review_packet_standard.v1.json`
- `artifacts/candidate/task14_review_workbench_mvp.v1.json`
- `schemas/review_workbench/review_packet.schema.json`
- `schemas/review_workbench/workbench_action.schema.json`
- `src/gsp_compliance_agent/review_workbench.py`

Rules:

- Include source text refs, proposed output refs, source hashes, uncertainty
  notes, reviewer role, and required decision.
- For promotion requests that Codex has reviewed as `CANDIDATE_PASS`, human P3
  approval must be given in the Codex thread and recorded by Codex.
- `create_p3_approval_request` may exist as legacy/review-packet tooling, but
  it does not create a valid WeCom approval route.
- WeCom approval notifications and WeCom approval replies are disabled and are
  not valid approval evidence.
- Hermes must not send or resend P3 approval notifications and must not treat
  WeCom messages such as `同意`, `批准`, or `approve` as promotion approval.
- Marker: `codex_thread_approval_only_wecom_push_disabled`.
- The approval record is still not a live write.
- Approval handoff must preserve the exact review scope, for example
  `knowledge_source_upload_only` versus `structured_database_build`.
- Do not ask whether you should trigger Codex or live write from WeCom. Say
  Codex must perform the final promotion/write step.
- For `knowledge_source_upload`, call the result a promoted source file or live
  knowledge source, not a formal database.
- Keep all work candidate-only unless a separate approval/promotion workflow
  completes.
- A review packet or human handoff does not make data live. The exact data
  family remains blocked for ordinary real-trial answers until promotion writes
  approved files and a live manifest under
  `/Users/HY-yin/hermes-local/data/knowledge/compliance/`.

Forbidden:

- Treating packet creation as approval, promotion without approval flow, or
  removing uncertainty/source-hash requirements.
- Treating P3 source-file approval as approval for structured database outputs.
- Treating reviewed candidate packets, `.hermes` workspace JSONL, or Desktop
  files as promoted live source authority.
