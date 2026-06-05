# Hermes Evidence Governance

## Purpose

Evidence governance prevents Hermes from claiming business work is complete when the actual file or runtime state does not support the claim.

## Evidence Source Rule

Claims must be backed by read-from-disk evidence. For files, Hermes must read the final file path being reported. For runtime state, Hermes must read the resolved path under `.hermes/profiles/<profile>/`.

Script output, memory, previous summaries, and plan text are not enough for completion claims.

## Completion Claim Rule

Before saying complete, verified, pass, ready, no missing fields, or equivalent, Hermes must verify:

- the exact file or runtime path;
- the version being reported;
- the relevant counts or fields;
- the profile boundary;
- any residual failures or warnings.

If metrics are involved, recompute them where practical rather than copying them from a report.

## Contradiction Rule

If a report claim conflicts with file content, Hermes must not return candidate pass. It must report:

- contradicted claim;
- actual evidence from disk;
- affected file or version;
- whether repair is possible inside current scope;
- next allowed action.

## Multi-Version Rule

When multiple output versions exist, Hermes must name which version each metric refers to. It must not claim a universal pass if any active version still fails.

Older versions should be clearly deprecated or excluded by an accepted workflow before they stop mattering.

## Runtime Boundary

`.hermes` can provide runtime evidence, but not policy authority. Evidence read from `.hermes` may describe what happened at runtime; it cannot override `hermes-local` profile policy.

## Business-Agent Status Labels

Hermes business reports should use clear status labels:

- `CANDIDATE_PASS`: business candidate output appears valid under the checks run.
- `FAILED`: output exists but failed checks.
- `BLOCKED`: required source, policy, approval, or verification is missing.

Final business or architecture approval remains outside Hermes unless a later approved process explicitly defines otherwise.
