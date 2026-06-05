---
name: compliance-requirement-atomization
description: Draft candidate requirement models, atoms, department ownership, and applicability hooks with traceable source links and no risk/applicability conclusions.
---

# Compliance Requirement Atomization

Use this skill for requirement master candidates, atomization, source
requirement links, department owner matrix candidates, and applicability hook
planning.

Accepted evidence:

- `artifacts/candidate/task12_iway_requirement_model.v1.json`
- `artifacts/candidate/task12_atom_risk_department_applicability.v1.json`
- `schemas/requirement_database/requirement_master.schema.json`
- `schemas/requirement_database/requirement_atom.schema.json`
- `schemas/requirement_database/department_owner_matrix.schema.json`
- `schemas/requirement_database/applicability_rule_hook.schema.json`

Rules:

- Preserve requirement IDs, atom IDs, source links, department basis, and
  applicability dependencies.
- Mark risk as unknown unless validated human assessment exists.
- State Task 13 dependency for factory scope and applicability.
- Return `BLOCKED` for ordinary real-trial requirement, atom, department,
  checklist, or applicability facts until the underlying source files and
  derived requirement dataset are promoted to live business data.
- Inspect Task 12 or runtime workspace records only when the user explicitly
  asks for candidate/runtime inspection, and label the answer `CANDIDATE_ONLY`
  or `RUNTIME_WORKSPACE_NOT_LIVE`.

Forbidden:

- Risk rating, applicability conclusion, accepted checklist/SOP output, or
  department ownership conclusion without source basis.
- Treating Task 12 candidate artifacts or `.hermes` workspace JSONL as live
  requirement authority.
