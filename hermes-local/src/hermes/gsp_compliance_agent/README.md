# GSP Compliance Agent

**Status: controlled production trial runtime contract.**

This agent is the compliance business profile on Hermes. Accepted runtime policy
is loaded from `hermes-local`, while `.hermes/profiles/compliance` is generated
runtime state only.

## Accepted Source

- `config/profiles/compliance.yaml`
- `config/profiles/compliance_permission_model.v1.json`
- `src/hermes/gsp_compliance_agent/prompts/soul.md`
- `src/gsp_hermes/skills/compliance/`

## Runtime Boundary

The compliance profile must not use `.hermes` sessions, memories, generated
profile files, or runtime skill candidates as accepted policy. Runtime reads the
accepted SOUL and compliance skills directly from this repository.

## Business Boundary

Outputs remain DRAFT unless a human-reviewed workflow explicitly approves a
separate official promotion. The agent may organise evidence and draft candidate
matrices, work packages, standards, overlays, and training/checklist plans, but
it does not make legal judgements, certify compliance, or publish official
policies.
