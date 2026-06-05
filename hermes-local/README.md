# Hermes Local

Hermes Local is the accepted source and live-data workspace for GSP Hermes business automation.

## Current Source Of Truth

- Profile policy: `config/profiles/`
- Tool policy: `config/tool_policies/`
- Main source code: `src/gsp_hermes/`
- Accepted compliance skills: `src/gsp_hermes/skills/compliance/`
- Retained legacy source: `src/hermes/`
- Live compliance knowledge base: `data/knowledge/compliance/`
- Runtime output only: `var/`

## Data Boundary

Current live databases, manifests, approval records, and source materials remain under `data/knowledge/compliance/`. Historical rollback data and duplicate backups were moved to `/Users/HY-yin/hermes-archive/hermes-local-data-cleanup-20260605/`.

## Do Not Treat As Source Of Truth

- `.hermes/` runtime state
- archived cleanup data under `/Users/HY-yin/hermes-archive/`
- legacy pointers under `src/hermes/` when a corresponding `src/gsp_hermes/` source exists

See `HERMES_ARCHITECTURE.md` for the full architecture contract.
