---
name: compliance-monitoring-recovery
description: Summarize gateway health, runtime governance, monitoring/recovery protocol, incident logs, backup/restore planning, and go-live readiness evidence.
---

# Compliance Monitoring Recovery

Use this skill for gateway health, runtime governance, monitoring/recovery,
incident log candidates, restore planning, and go-live readiness.

Accepted evidence:

- `artifacts/candidate/task9_readiness_evidence_summary.v1.json`
- `artifacts/candidate/task9_normal_use_runbook.v1.md`
- `artifacts/candidate/task9_go_live_approval_packet.v1.json`
- `artifacts/candidate/task15_monitoring_recovery.v1.json`
- `artifacts/candidate/task15_formal_use_go_live_gate.v1.json`
- `HERMES_GATEWAY_MULTI_BOT_RUNBOOK.md`

Rules:

- Tie readiness/go-live statements to validator and approval evidence.
- Require human approval for restore, external probe, daemon start, or real
  notification.
- Report drift and incident evidence without making go-live claims.

Forbidden:

- Unapproved restore, unapproved real probe/notification, or go-live claim
  without approval evidence.

