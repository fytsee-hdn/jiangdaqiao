---
name: compliance-promotion-rollback
description: Assess candidate promotion readiness, rollback plans, accepted-output gates, and blocked promotion reasons without performing real accepted writes.
---

# Compliance Promotion Rollback

Use this skill for promotion readiness, negative promotion tests, rollback
planning, accepted-output gate checks, and P3 approval requirements.

Use `compliance-live-data-promotion-request` first when the user is submitting
a new promotion request from Hermes. Use this skill after a request exists and
the question is about promotion readiness, blocked reasons, approval gates, or
rollback.

Accepted evidence:

- `artifacts/candidate/task7_promotion_gate_protocol.v1.json`
- `artifacts/candidate/task7_negative_promotion_tests.v1.json`
- `artifacts/candidate/task7_rollback_quarantine_evidence.v1.json`
- `artifacts/candidate/task14_approval_promotion_flow.v1.json`
- `artifacts/candidate/task14_acceptance_rollback_trial.v1.json`

Rules:

- Require source hashes, traceability refs, validator `CANDIDATE_PASS`, audit
  log reference, P3 approval, and rollback plan.
- Distinguish simulation/dry-run from real accepted write.
- Promotion for any source, legal/customer requirement, checklist, GSP standard,
  evidence matrix, factory/risk record, or product database must target
  `/Users/HY-yin/hermes-local/data/knowledge/compliance/` and create/update a
  live manifest.
- Keep `live_business_data_configured` false until the exact promoted data
  family has source hashes, approval record, manifest, rollback plan, and
  runtime baseline update.
- A Hermes-submitted promotion request is intake evidence only. It must be
  independently verified by Codex before any human P3 promotion approval.
- Return blocked reason for missing prerequisites.

Forbidden:

- Real accepted write without approved workflow, promotion to `.hermes`, missing
  prior content approval, promotion to `artifacts/candidate` or Desktop as live
  authority, or business conclusion language.
