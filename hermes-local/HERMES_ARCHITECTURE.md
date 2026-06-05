# Hermes Project Architecture

## Purpose

Hermes is a profile-governed business automation workspace for GSP workflows. The current architecture is intentionally rebuilt from a clean root. Legacy code, runtime state, auth/session files, caches, and uncertain business artifacts are preserved in an independent backup, but they are not active source of truth.

This file is the first-level architecture entry point for other repositories that need to understand or integrate with Hermes.


## Responsibility Split

Codex owns architecture construction and workflow governance. That includes repository structure, task packages, approval records, protected governance state, source policy changes, and final architecture evidence.

Hermes is a business agent layer. Hermes works inside accepted profile policies to process business tasks, create candidate business outputs, draft evidence, summarize runtime observations, and propose runtime skill candidates. Hermes does not approve architecture, change source policy from runtime state, or turn generated `.hermes` content into accepted source.

Business-agent outputs from Hermes are candidate outputs until reviewed or accepted through the relevant Codex-managed workflow.

## Roots

Hermes uses two roots with different authority.

```text
/Users/HY-yin/hermes-local
```

Business source root. Stores accepted policy, architecture, source code, tests, profile definitions, and reviewed reusable business assets.

```text
/Users/HY-yin/.hermes
```

Generated runtime root. Stores sessions, logs, cache, outputs, and state. For production compliance, skills and memory-like policy pointers are read directly from `hermes-local`; runtime copies cannot define or override permissions.

```text
/Users/HY-yin/hermes-independent-backup/TASK-20260522-004_20260522_191614
```

Independent preservation backup. Stores uncertain legacy/runtime/raw content with original relative root structure. It is not active source of truth.

## Source Of Truth Rule

Accepted profile policy is loaded only from:

```text
hermes-local/config/profiles/<profile>.yaml
```

Runtime profile state is stored only under:

```text
.hermes/profiles/<profile>/
```

A profile that exists only in `.hermes` must fail closed. `.hermes` profile files, generated state, cache, sessions, memories, or skill candidates cannot override accepted policy from `hermes-local`.

## Required Profiles

### admin

System administration and controlled operations. This is the only admin-capable profile.

Core requirements:

- may use admin CLI/chatbot entrypoints when allowlisted;
- admin chatbot rejects high-risk operations;
- forbidden secret requests are always denied;
- audit logs redact sensitive fields;
- business profiles cannot inherit admin capability.

### compliance

Compliance source review and evidence drafting.

Core requirements:

- no admin capability;
- uses compliance OCR extraction policy;
- focuses on clauses, sources, pages, versions, and evidence trace;
- cannot route admin operations through service.

### service

Service routing and profile orchestration.

Core requirements:

- no admin capability;
- routes allowed profile actions only;
- blocks admin actions for non-admin profiles;
- cannot become a privilege escalation layer;
- dispatches to profile boundaries without restoring legacy code.

### reimbursement

Reimbursement intake, OCR policy selection, field validation, evidence, and draft output boundary.

Core requirements:

- no admin capability;
- does not inherit old `finance` behavior by default;
- uses `reimbursement_ocr_extraction` policy;
- validates invoice/receipt/reimbursement fields;
- current implementation is an architecture boundary and deterministic stub, not production automation.

## OCR And Shared Tools

Shared tool implementations belong under:

```text
hermes-local/src/gsp_hermes/tools/
```

Tool behavior must be selected through policy rather than hard-coded into profiles.

Current OCR policy split:

- `shared_ocr`: common OCR outputs and constraints;
- `compliance_ocr_extraction`: compliance evidence fields;
- `reimbursement_ocr_extraction`: reimbursement invoice/receipt fields;
- legacy `finance_ocr_extraction`: preserved historical policy, not the primary reimbursement profile policy.

## Skill Lifecycle

Accepted reusable business skill specs live under:

```text
hermes-local/src/gsp_hermes/skills/<profile>/
```

Production profiles should load those skills directly as read-only source. Agent-generated skill ideas are proposals until a reviewed task updates `hermes-local`; runtime skill copies cannot automatically become accepted source assets.

## Active Code Layout

```text
hermes-local/
  config/
    profiles/
    tool_policies/
  docs/
    architecture/
    profiles/
    migration/
  src/
    gsp_hermes/
      admin/
      core/
      orchestrator/
      profiles/
      reimbursement/
      service/
      tools/
  tests/
    admin/
    policies/
    profiles/
    reimbursement/
    service/
  var/
    logs/
    uploads/
    tmp/
    backups/
```


## Operating Model

Hermes business agents should follow a lightweight task loop rather than a full architecture workflow:

1. Identify the active profile and accepted policy.
2. Restate the business objective and output target.
3. Execute the business task within the profile boundary.
4. Verify outputs from disk or deterministic state where applicable.
5. Repair obvious non-scope-breaking issues.
6. Report candidate business results with evidence paths and residual risks.

Large tasks should be decomposed by file, record range, domain, or exception queue. Code-first processing is preferred for deterministic extraction, counting, validation, and merging. LLM judgment should be reserved for ambiguous or semantic cases.

Hermes should not create sample-only deliverables unless the user explicitly asks for a sample.

## Integration Requirements For Other Repositories

Other repositories integrating with Hermes should follow these rules:

1. Treat `hermes-local/config/profiles` as the only accepted profile policy source.
2. Treat `.hermes` as generated runtime state only.
3. Never rely on `.hermes` to determine permissions, admin capability, OCR policy, or entrypoints.
4. Use service/profile APIs instead of importing legacy backup code.
5. Write runtime outputs to `.hermes/profiles/<profile>/outputs` or the appropriate runtime subdirectory.
6. Do not write generated state into `hermes-local/config/profiles`.
7. Do not read secret/session/auth bodies from `.hermes` unless a later approved task explicitly authorizes it.
8. Do not delete or mutate independent backup content without a separate approved migration task.


## Evidence Governance

Hermes completion claims must be evidence-backed. For any claim such as complete, verified, passed, ready, or no missing fields, Hermes must read the final file or runtime state from disk and recompute or cross-check the relevant facts.

If a claim conflicts with file content, the result is not a candidate pass. The report must state the contradiction, affected files, and next allowed repair step.

When multiple versions exist, Hermes must name which version each metric refers to and must not hide failures in older active outputs.

## Verification Baseline

The current accepted candidate passed:

- profile registry checks;
- runtime policy boundary checks;
- service router checks;
- reimbursement OCR policy checks;
- retained admin command/router/chatbot/audit tests;
- retained skill/tool policy tests;
- task package, evidence pack, and workflow state checks.

## Current Status

Status: `CANDIDATE_PASS`, accepted by Human Owner in conversation.

This status means the architecture is accepted as the current Hermes foundation, while future business automation still requires separate scoped tasks and verification.
