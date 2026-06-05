---
name: compliance-permission-and-access
description: Resolve WeCom account binding, P0/P1/P2/P3 role, protected actions, approval authority, and access-request flow from the accepted permission model.
---

# Compliance Permission And Access

Use this skill when the user asks about level, role, approval authority,
allowed actions, blocked actions, or access requests.

Accepted evidence:

- `/Users/HY-yin/hermes-local/config/profiles/compliance_permission_model.v1.json`
- `/Users/HY-yin/.hermes/profiles/compliance/logs/compliance_access_gate.jsonl`
- `/Users/HY-yin/.hermes/profiles/compliance/access_requests/`

Rules:

- Always read permission from the accepted permission model.
- Match the current WeCom ID against `wecom_account_bindings`.
- Unknown, missing, duplicate, suspended, or revoked bindings are `BLOCKED`.
- Resolve role inheritance recursively before explaining allowed actions. Do not
  read only the role's direct `allowed_action_ids`; P2 inherits P1/P0, and P3
  inherits P2/P1/P0 unless an explicit denied action blocks the action.
- Explain P0/P1/P2/P3 role, effective inherited actions, direct denied actions,
  and approval authority.
- Access requests may be recorded, but the agent must not self-approve them.

Forbidden:

- Inferring owner/admin from DM access, local gateway access, memory, session
  history, or runtime files.
- Changing permissions without explicit approved workflow.
