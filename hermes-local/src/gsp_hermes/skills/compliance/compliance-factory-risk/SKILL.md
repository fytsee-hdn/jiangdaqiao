---
name: compliance-factory-risk
description: Draft candidate factory scope, audit atoms, area/function profiles, risk candidates, onsite assessments, and improvement loops without risk conclusions.
---

# Compliance Factory Risk

Use this skill for factory profile candidates, audit scope boundary, area
inventory, audit atoms, area function profiles, risk candidates, onsite
assessment records, improvement suggestions, and expected evidence.

Accepted evidence:

- `artifacts/candidate/task13_factory_scope_area_inventory.v1.json`
- `artifacts/candidate/task13_audit_atom_area_function_profiles.v1.json`
- `artifacts/candidate/task13_risk_list_engine.v1.json`
- `artifacts/candidate/task13_onsite_risk_assessment_improvement_loop.v1.json`
- `schemas/factory_scope/*.schema.json`

Rules:

- Preserve source/hash, factory/area/function/atom IDs, and human assessment
  requirements.
- Keep risk rating unknown until validated human assessment exists.
- Report missing source, missing boundary, unknown refs, and residual risk.

Forbidden:

- Risk rating conclusion, applicability conclusion, accepted factory profile,
  or checklist update from draft risk candidates alone.

