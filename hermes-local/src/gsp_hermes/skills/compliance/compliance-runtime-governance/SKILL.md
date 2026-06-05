---
name: compliance-runtime-governance
description: Verify live runtime architecture, gateway isolation, accepted-source binding, SOUL sync, skill sync, memory/session contamination, and access-gate behavior.
---

# Compliance Runtime Governance

Use this skill for runtime architecture checks, gateway isolation, SOUL source
binding, skill contamination, memory/session contamination, access gate
behavior, and multi-bot profile separation.

Accepted evidence:

- `scripts/check_runtime_governance.py`
- `scripts/check_task16_runtime_architecture_audit.py`
- `/Users/HY-yin/.hermes/profiles/compliance/bin/check_runtime_governance.py`
- `/Users/HY-yin/.hermes/profiles/compliance/logs/gateway.log`
- `/Users/HY-yin/.hermes/hermes-agent/gateway/compliance_access_gate.py`

Rules:

- Check LaunchAgent label, `HERMES_HOME`, active profile, SOUL hash,
  `.no-bundled-skills`, accepted skill manifest, memory seed, access gate, and
  stale state.
- Check live business data policy, live data root binding, candidate/runtime
  workspace contamination, and whether canonical/approved source registers are
  still empty while live data is unconfigured.
- Treat `.hermes/profiles/compliance/workspace/data/knowledge/compliance/`,
  `artifacts/candidate/`, and Desktop-discovered source files as non-live unless
  a promotion manifest under `/Users/HY-yin/hermes-local/data/knowledge/compliance/`
  proves otherwise.
- Report findings with file paths and check names.

Forbidden:

- Generic gateway labels for live compliance, root/default `.hermes` authority,
  generic bundled skill contamination, fail-open access gate, or treating
  candidate/runtime business data as live authority.
