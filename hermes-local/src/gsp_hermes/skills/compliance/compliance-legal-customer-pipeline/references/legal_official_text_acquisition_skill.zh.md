# Hermes 法律原文获取技能摘要

status: CANDIDATE_ONLY_NOT_LIVE

## 适用场景

当用户要求 Hermes 获取、归档或复核越南法规官方原文时使用本技能。该技能只处理 source evidence acquisition，不输出法律适用结论、合规结论、requirement atoms、checklist 或 confirmed factory baseline。

## 输入

- 已推广或候选的法规 metadata index。
- 已经过 jurisdiction、document type、status、revision-chain、negative-scope 和 profile-trigger 分层的获取队列。
- 每条记录至少应包含 `source_record_id`、`law_id`、`title_vi`、`document_type`、`official_url_or_id` 或可追溯的官方来源线索。

## 官方来源优先级

- A0/VBPL detail API：优先使用 `https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc/{doc_id}`。
- A1 政府/主管机关门户及签章 PDF：用于 VBPL 不足、源站交叉验证或官方 PDF 证据。
- A2 官方公报/出版源：用于状态、发布与替代链证据。
- A3 部委/监管机关页面、QCVN/技术附件源：用于专业法规、技术规范和附件补证。
- B 类第三方源只可作为 discovery/cross-check，不得作为 accepted official source。

## 获取动作

1. 从队列读取记录，确认该记录不是 backlog，或用户明确要求处理 backlog。
2. 从 live/candidate metadata index 解析 `vbpl://doc/{doc_id}`。
3. 调用 VBPL detail API，保存原始 JSON。
4. 提取 `documentContent.content` 保存 HTML。
5. 从 HTML 提取纯文本，仅用于检索和人工核验。
6. 对 raw JSON、HTML、text 分别计算 SHA-256。
7. 做 source-fidelity 检查：`law_id` 应与官方 `docNum` 或正文前段编号匹配，标题关键词应有基本匹配。
8. 记录 `fetch_status`、`source_fidelity_check`、官方状态字段、路径、hash、错误信息和边界标志。

## 输出字段

每条获取结果至少保留：

- `source_record_id`
- `law_id`
- `title_vi`
- `document_type`
- `primary_module`
- `official_source_tier`
- `official_url_or_id`
- `official_doc_id`
- `official_api_url`
- `fetch_status`
- `official_doc_num`
- `official_title`
- `official_doc_type`
- `official_agency`
- `official_issue_date`
- `official_effective_from`
- `official_effective_to`
- `official_effect_status`
- `raw_json_path`
- `html_path`
- `text_path`
- `raw_json_sha256`
- `html_sha256`
- `text_sha256`
- `source_fidelity_check`
- `source_fidelity_reason_cn`
- `candidate_official_text_archived`

## 队列解释

- A1：precision-first immediate baseline candidate。可先做 official text acquisition，但获取完成后仍需人工/legal owner 审核。
- A2-C：第二优先 official text acquisition candidate。
- A2-S：status/effectiveness repair；获取原文用于确认生效、废止、部分有效、未来生效或 metadata 冲突。
- A2-R：revision-chain consolidation；获取原文用于关联主法、修订法、处罚法、替代链，不得把 amendment/penalty 文件单独当 baseline。
- A2-P：profile-trigger evidence；获取原文只作为后续主体画像判断资料，不能直接进入执行清单。
- A2-N：negative-scope legal owner review；获取原文用于判断是否被 negative scope filter 误伤。
- backlog：默认不抓取，除非用户明确要求或 legal owner 指定。

## Task14 交接

获取完成后应生成 candidate review packet：

- `packet_type` 使用 `legal_clause`，但 `item_type` 应使用 `source_text`，表示官方原文证据复核，不表示已经拆解法律条款。
- `reviewer_role` 默认 P2；promotion 或 accepted output 需要后续 P3 独立批准。
- `source_hashes` 必须包含 raw JSON、HTML 和 text hash。
- `traceability_refs` 必须包含原队列、source record、law id、官方 API 和 archive path。
- `uncertainty_summary` 必须说明这是 candidate source evidence，不是适用性/合规/风险结论。

## 禁止边界

- 不得生成 checklist。
- 不得生成 requirement atoms。
- 不得作法律适用结论。
- 不得作合规、风险、审计通过或 source-sufficiency 结论。
- 不得标记 `confirmed_factory_baseline=true`。
- 不得标记 `can_enter_factory_must_baseline_now=true`，除非另有 legal owner approval 且 promotion flow 完成。
- 不得直接写 live database、accepted output 或 `.hermes` runtime。

## 本轮 v3.2.1 经验参数

- A1 official text acquisition：50/50 archived，source-fidelity PASS 50。
- A2 non-backlog official text acquisition：565/565 archived，source-fidelity PASS 565。
- A2 backlog 未处理，仍保留为 coverage buffer。
- A2-P 199 条虽已归档原文，但仍只作为 profile-trigger evidence。
