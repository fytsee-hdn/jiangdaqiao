---
name: compliance-skill-proposal
description: Convert observed runtime failures into candidate skill proposals, root-cause notes, and regression checks without self-promoting into accepted source.
---

# Compliance Skill Proposal

Use this skill when the user asks to summarize a failure, turn an issue into a
skill proposal, prevent recurrence, or decide whether a rule belongs in SOUL,
memory, skill, runtime governance, or gateway code.

Accepted evidence:

- Runtime logs and task evidence for the observed issue.
- `artifacts/candidate/hermes_compliance_skill_lifecycle_policy.v1.md`
- `artifacts/candidate/hermes_compliance_skill_lifecycle_rules.v1.json`
- Task 16 runtime governance findings.

Rules:

- Separate observation from authority.
- Draft candidate skill proposals with trigger, scope, evidence, forbidden
  actions, stop conditions, and tests.
- Ask for approval before changing accepted SOUL, memory seed, skills, gateway,
  or runtime files.

Forbidden:

- Direct self-promotion into accepted source, memory-only skill creation, or
  runtime policy updates without user approval.

