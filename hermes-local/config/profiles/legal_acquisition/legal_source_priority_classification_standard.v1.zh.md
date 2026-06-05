# Hermes 法律来源与优先级分级标准 v1

status: ACCEPTED_HERMES_RUNTIME_REFERENCE

generated_at: 2026-05-25T03:57:11Z

本文件是 Hermes compliance profile 的正式执行参考。它定义来源权威等级、数据生命周期等级、canonical 合并口径、业务优先级、Task14 审批门槛，以及历史 Hermes 数据的允许用途。

## 0. 使用入口

Hermes 在处理越南法律法规、QCVN、法律原文获取、法规库建设、metadata 查询、A0/B1 缺口、历史 Hermes legal priority/atom 参考时，必须先读本文件。

相关正式入口：

- 法律来源路径 manifest：`/Users/HY-yin/hermes-local/config/profiles/legal_acquisition/vietnam_legal_clause_acquisition_sources.v1.json`
- 正式知识库 catalog：`/Users/HY-yin/hermes-local/data/knowledge/compliance/knowledge_base_catalog.v1.json`
- 默认 canonical 法律 metadata index：`/Users/HY-yin/hermes-local/data/knowledge/compliance/databases/legal_sources/vietnam_legal_document_index/2026_05_25/canonical/legal_document_canonical_index.sqlite`
- canonical manifest：`/Users/HY-yin/hermes-local/data/knowledge/compliance/databases/legal_sources/vietnam_legal_document_index/2026_05_25/canonical/legal_document_canonical_index.manifest.v1.json`
- A0/B1 crosswalk：`/Users/HY-yin/hermes-local/data/knowledge/compliance/databases/legal_sources/vietnam_legal_document_index/2026_05_25/crosswalk/a0_b1_crosswalk.sqlite`

## 1. 来源权威分级

### A0：官方结构化基准

- 代表来源：VBPL API / VBPL detail。
- 用途：正式 metadata、法规身份、官方来源报告的生效状态字段、条文树候选、A0 canonical baseline。
- 可作为正式 metadata 来源，但不能自动代表条款库已完成。
- 条件：必须保存 source snapshot/hash、official_verified_at、精确编号/标题/机关/日期匹配。

### A1：官方政府门户 / 签章 PDF

- 代表来源：`vanban.chinhphu.vn`、`chinhphu.vn`、`datafiles.chinhphu.vn`。
- 用途：2025+ 新文件、VBPL 未覆盖文件、签章 PDF 官方原文、政府门户 metadata。
- PDF/OCR 只能先作为候选，条款 promotion 前必须做提取质量审查。

### A2：官方公报 / 发布证明

- 代表来源：`congbao.chinhphu.vn`。
- 用途：发布证据、官方公报交叉验证、官方来源补强。
- 不优先作为条款抽取来源，除非 A0/A1 不可用。

### A3：部委 / 主管机关来源

- 代表来源：发布机关官网、部委官网、QCVN/TCVN 附件来源。
- 用途：QCVN、技术法规附件、Circular/Thông tư 附件、主管机关实施文件。
- QCVN 不能只搜编号；必须先定位发布它的 Circular/Thông tư，再验证版本有效性和替代/修订情况。

### B1-B4：第三方数据库

- 代表来源：Hugging Face / TVPL-derived / VBPL-derived fallback / limited corpus。
- 用途：discovery、关系提示、doc_id/title/issuer/date 线索、覆盖缺口、候选文本比对。
- 禁止用途：正式效力状态、官方原文依据、直接条款入库、直接 promotion evidence。

### C1-C2：第三方网页 / HSE 专项来源

- 代表来源：TVPL、LawNet、LuatVietnam、ATLD/HSE、legacy HSE archive。
- 用途：人工可读交叉验证、候选来源定位、技术文本比对。
- 禁止用途：正式法律依据、QCVN 版本有效性结论、效力状态结论。

### D1：训练/评测/工具数据

- 代表来源：GitHub 法律语料、QA 数据集、模型训练集、工具 repo。
- 用途：模型评测、抽取实验、工具参考。
- 禁止用途：source registry、正式条款抽取、当前法律/效力状态判断、promotion evidence。

### legacy_reference：历史 Hermes 数据

- 代表来源：历史 Hermes legal priority refs、legal atom sources、old CSV/JSONL、legacy reset artifacts。
- 用途：优先级参考、领域覆盖提示、旧工作对照、遗漏风险提示。
- 禁止用途：正式法规来源、官方原文、条款依据、要求依据、合规结论。

## 2. 数据状态分级

### LIVE_READ_ONLY_CANONICAL_METADATA_INDEX

- 默认正式法规 metadata 查询入口。
- 当前默认口径是官方网站导出的 canonical official metadata documents，不是旧第三方 raw source rows。
- 用途：法规 metadata 是否存在、编号、标题、发布机关、发布日期、生效日期、canonical 数量、source identity。

### ARCHIVED_THIRD_PARTY_DISCOVERY_ONLY

- 旧第三方/B1 原始来源行索引，已从正式 live 查询入口移除。
- 只用于历史对账、缺口线索、回滚证据和审计追溯。
- 不得用于 chatbot 检索、默认 metadata 查询、正式法规来源、法律条款数量、条款依据、要求拆解、GSP atom 生成或工厂合规回答。

### ARCHIVED_THIRD_PARTY_CROSSWALK_TRACEABILITY_ONLY

- 旧 A0/B1 对照库，已从正式 live 查询入口移除。
- 只作为旧第三方来源与官方网站 canonical 数据之间的历史对照、gap lead review 和审计追溯证据。
- 不得把 B1 match、B1 gap 或 raw total 当作当前法律依据、条款依据、法律条款数量或合规要求。

### CANDIDATE_ONLY_NOT_LIVE

- 候选产物，只能用于审核和 promotion request。
- 不得当作正式知识库回答。

### DISCOVERY_ONLY_NOT_CANONICAL

- 第三方发现线索。
- 需经 A0/A1/A2/A3 官方验证后才可能进入正式路径。

### BLOCKED

- 缺少官方原文、hash、traceability、review、审批、权限或工具时必须拒答/暂停。

## 3. Canonical 合并与计数规则

- A0/VBPL 记录进入 canonical index，作为默认正式 metadata 口径。
- B1 confirmed match 不重复计数，只作为 `source_links`。
- B1 在 A0/VBPL 中找不到的记录进入 monitor，状态为 discovery-only。
- status conflict 不直接裁决生效状态，进入 review 队列。
- raw total 只能称为 archived third-party/source-lineage raw rows。
- 默认对用户暴露的法规 metadata 数量必须使用 canonical index。

当前已知口径：

- raw source rows：321438。
- A0/VBPL official metadata rows：168018。
- B1 third-party discovery rows：153420。
- confirmed A0/B1 matches：145010。
- canonical official metadata documents：168018。
- B1 VBPL-missing monitor rows：106。

## 4. 业务优先级分级

### P0_now：立即处理

适用条件：

- 当前业务/工厂 profile 直接触发。
- 影响核心合规基线或会阻断审核。
- 近期有效、即将生效、或 2025+ 高风险新规。
- QCVN/技术法规与当前产品、设备、化学品、PCCC、OHS、环境、劳动、社保、最低工资、外籍员工等直接相关。

历史 Hermes priority refs 可提示 P0 领域，例如：labour、social_insurance、chemicals、PCCC、environment、OHS、wage、foreign_worker。

### P1_before_section：章节开始前必须处理

适用条件：

- 影响某个 IWAY section 或专项审核判断。
- 重要实施细则、处罚/执法文件、status conflict、QCVN 版本确认。
- 不一定阻断全部流程，但进入相关章节前必须完成官方核验。

### Important_P2_Active：重要补充

适用条件：

- 提供频率、证书、限值、记录、证据、处罚细节。
- 不阻断最小可运行法规库，但影响检查项完整性和后续审核质量。

### P3_Reference：参考/低优先级

适用条件：

- 历史文件、地方性弱相关文件、低相关 discovery lead、弱业务触发项。
- 仅在扩展覆盖或专项追溯时处理。

## 5. 历史 Hermes 数据使用标准

历史 Hermes legal priority refs：

- 可用于判断“先找什么”和“哪些领域容易遗漏”。
- 可用字段包括 `legal_domain`、`blocking_scope`、`factory_profile_trigger`、`affected_sections`、`text_priority`。
- 不得把其中的 law_id/law_name 当作已确认正式法规目标；必须重新走 A-tier 官方发现/验证。

历史 Hermes legal atom sources：

- 可用于识别领域、部门、检查对象、证据类型、潜在 requirement/atom 结构。
- 典型领域包括 ENV、CHEM、PCCC、LABOR、CONST。
- 所有 atom 仍为 candidate/reference；不得作为正式条款、要求、检查项或风险评级。

## 6. Task14 审批与 promotion 分级

- `CANDIDATE_PASS` 不是批准，只是工程验证通过。
- 候选内容审核最低需要 P2，并且必须有 source hash、traceability、uncertainty、review packet、validator pass。
- 正式 promotion 必须 P3，并且必须有独立 promotion decision、audit log、source hash、traceability、rollback plan。
- 缺少 source hash、traceability、validator pass、P3 approval、audit log、rollback plan 的 promotion 必须 `BLOCKED`。
- Hermes 不得自己 promote，不得写 live root，不得声称 approval、compliance、risk、applicability、go-live、audit-pass conclusion。

## 7. 回答边界

允许回答：

- 某法规是否存在于 canonical metadata index。
- 正式 metadata 数量。
- A0/B1 是否匹配。
- 某 B1 是否 discovery-only。
- 哪些法规/来源应优先获取官方原文。
- QCVN 应走哪个来源路径。
- promotion 还缺哪些 review / hash / traceability / approval。

禁止回答：

- 法规原文内容。
- 条款解释。
- 要求分解。
- 检查项原子化。
- 风险评级。
- 合规/不合规结论。
- 法律意见。
- audit pass。

原因：当前正式库完成的是 metadata/canonical/crosswalk，不是正式原文库、条款库、要求库或风险库。

## 8. Hermes 执行顺序

当用户要求处理法律/法规/法规库/QCVN/条款/要求时：

1. 先判断是否属于 compliance profile；无关问题隔离。
2. 读取本分级标准和 source pathway manifest。
3. 对 metadata 查询，默认使用 canonical index。
4. 对 A0/B1 身份、缺口、状态冲突，使用 crosswalk。
5. 对具体法律原文获取，走 A0 → A1 → A2 → A3；第三方只能作为 discovery。
6. 对 QCVN，先找发布 Circular/Thông tư，再找附件和版本有效性。
7. 对历史 Hermes 数据，只用作优先级和覆盖提示。
8. 所有新输出写 candidate workspace，标记 `CANDIDATE_ONLY_NOT_LIVE`。
9. 需要正式入库时提交 promotion request，由 Codex 复核，P3 批准，Codex promotion。
