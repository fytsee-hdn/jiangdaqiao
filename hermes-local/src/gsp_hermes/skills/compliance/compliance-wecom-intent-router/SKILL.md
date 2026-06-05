---
name: compliance-wecom-intent-router
description: Classify WeCom messages into compliance intents, isolate out-of-scope requests, ask clarifying questions, and route controlled actions.
---

# Compliance WeCom Intent Router

Use this skill for every WeCom message before substantive answering or tool use.

Supported compliance intents include candidate query, update request, task
approval, dry-run promotion approval, permission-change request, access
request, runtime governance check, source intake, P3 promotion approval
recording, and clarification.

Out-of-scope examples include weather, news, stocks, travel, restaurants,
shopping, poetry, entertainment, ordinary chat, and general life-assistant
questions.

Rules:

- Classify the user purpose as `in_scope`, `out_of_scope`, or
  `needs_clarification`.
- If classification requires LLM judgement, the classifier may only output route
  metadata: status, reason, and suggested route.
- Do not answer out-of-scope questions and do not call unrelated tools.
- For ambiguous approval, missing target, missing source hash, missing validator,
  or missing audit log, ask a clarifying question or return `BLOCKED`.
- WeCom approval notifications and WeCom approval replies are disabled and are
  not valid approval evidence. If a user replies approve/reject/request changes
  in WeCom, explain that P3 approval must be completed in the Codex thread.
- Do not route WeCom approval text to `record_promotion_approval` and do not
  send or resend approval notifications through `send_p3_approval_notification`.
- Marker: `codex_thread_approval_only_wecom_push_disabled`.
- Controlled actions require permission checks before routing.

Forbidden:

- Directly answering weather or other unrelated content.
- Treating ambiguous approval as valid approval.
- Running direct LLM execution for controlled actions without validators.
