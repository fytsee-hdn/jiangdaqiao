---
name: compliance-capability-router
description: Route GSP compliance requests to accepted capabilities, permission checks, source files, database indexes, or blocked/handoff responses.
---

# Compliance Capability Router

Use this skill whenever the user asks what the compliance agent can do, what
skills are available, which database can be queried, or how a request should be
handled.

Accepted capability sources:

- `/Users/HY-yin/hermes-local/config/profiles/compliance_capability_map.v1.json`
- `/Users/HY-yin/hermes-local/config/profiles/compliance.yaml`
- `/Users/HY-yin/hermes-local/config/profiles/compliance_permission_model.v1.json`
- `/Users/HY-yin/hermes-local/config/profiles/compliance_memory_seed.md`
- `/Users/HY-yin/hermes-local/src/hermes/gsp_compliance_agent/prompts/soul.md`
- `/Users/HY-yin/hermes-local/src/gsp_hermes/skills/compliance/`
- `/Users/HY-yin/Documents/Codex-Compliance-System/artifacts/candidate/hermes_compliance_required_skills.v1.json`
- `/Users/HY-yin/Documents/Codex-Compliance-System/artifacts/candidate/hermes_compliance_skill_catalog.v1.json`

Rules:

## Core Database First Policy

For ordinary GSP factory questions about a site area, equipment, process,
job role, contractor, document/evidence requirement, IWAY execution point,
onsite attention point, audit-preparation note, training-preparation note,
SOP-preparation note, or practical "what should we check/do" request, route to
`compliance-database-query` and query the promoted GSP Compliance Core Database
first.

Trigger examples include: 门卫, 危废仓, 化学品仓, 仓库, 消防通道, 叉车, 叉车充电,
锅炉房, 电气房, 食堂, 宿舍, 装卸区, 生产区, 维修区, 承包商, PPE, 台账, 点检,
注意事项, todo list, IWAY执行要求, 现场走访, 审核准备, 需要看什么, 有哪些要求.

Do not start these requests from the legal metadata index or legal clause
library. Legal databases are secondary support only after the core database rows
have been retrieved, and only for source-evidence/legal-basis confirmation.

- Before answering, classify the request as `in_scope`, `out_of_scope`, or
  `needs_clarification`.
- Isolate weather, news, stocks, shopping, restaurants, entertainment, poetry,
  travel, and ordinary life-assistant requests. Do not answer them or call
  unrelated tools.
- Do not answer capability, permission, or database questions from memory or
  prior chat transcripts.
- Do not describe source, legal, customer, checklist, GSP, evidence-matrix, or
  database data as live unless `live_business_data_policy` in the capability map
  says that exact data family is configured.
- Ordinary real-trial business facts are `BLOCKED` while
  `live_business_data_configured` is false.
- Candidate/runtime workspace inspection must be explicitly requested and
  labeled `RUNTIME_WORKSPACE_NOT_LIVE`, `CANDIDATE_ONLY`, or `TEST_DATA`.
- If the user asks to make data official, go live, promote, approve source,
  submit source, or turn candidate/runtime data into live data, route first to
  `compliance-live-data-promotion-request`.
- Explain that Hermes can submit and preliminarily review a promotion request,
  while Codex must verify and the P3 human owner must approve before live data
  is written.
- If a skill exists only as accepted source design but is not callable as a
  runtime tool, say that explicitly.
- If the user asks for a controlled action, identify the permission model role
  and protected action before responding.
- If required source/index/tool evidence is missing, return `BLOCKED` or ask
  for the missing target, rather than improvising.
- For complex, stuck, or multi-step work, remember that tool awareness is part
  of routing. Consider `todo` for lightweight step tracking, `delegate_task` for
  independent side work, and domain workflow tools before generic file/shell
  operations. Do not force these tools for simple answers; do not pretend to use
  a tool that is not visible.
- If a candidate artifact is created or inspected, explain its path,
  candidate/not-live status, purpose, residual risk, and next actor.

Allowed output:

- Capability list with live/candidate/blocked status.
- Route recommendation to a compliance skill family.
- Clarifying question when the target or scope is unclear.
- Out-of-scope isolation response for unrelated requests.
