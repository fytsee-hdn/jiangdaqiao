# Hermes 法律条款原文抓取提示词 v1

请优先读取下面这个 Hermes-facing source pathway manifest：

`/Users/HY-yin/hermes-local/config/profiles/legal_acquisition/vietnam_legal_clause_acquisition_sources.v1.json`

注意：这个文件只描述法律文件来源途径、来源分级、读取规则和官方验证门槛。它不是法律清单，不能包含具体法律、法规、QCVN 或条款目标，也不能从它生成法律名称清单。

不要读取或使用预置的 candidate target queue。具体法规清单只能来自即时官方来源检索、身份校验和 Codex/人工审核；不能由预制候选队列替代。

重要原则：法规库建设应从“法律法规完整候选索引”开始，再由法规倒推要求、条款、检查项。用户不需要先知道法律领域；业务范围可以用于后续过滤或优先级排序，但不能成为启动法律库建设的前提。

Hermes runtime intake 副本在：

`/Users/HY-yin/.hermes/profiles/compliance/workspace/source_intake/vietnam_legal_clause_acquisition/vietnam_legal_clause_acquisition_sources.v1.json`

Codex 审计副本在：

`/Users/HY-yin/Documents/Codex-Compliance-System/tasks/TASK-20260525-001/vietnam_legal_clause_acquisition_sources.v1.json`

只执行越南法律官方原文与条款候选抓取，不要写入正式知识库，不要生成正式法律结论。

执行要求：

1. 不要在 source pathway manifest 中查找或生成具体法律清单；它只定义来源途径。
2. 不要读取或使用预制 candidate target queue。
3. 如用户要求建立法规库、法规名册、或不了解具体法律领域，启动“官方来源候选法规索引发现”流程，不要要求用户先选择领域。
4. 候选法规索引发现应覆盖法律、法典、 nghị định、thông tư、quyết định、nghị quyết、QCVN/技术法规及替代/修订关系；先输出候选发现报告，不要直接抽取要求。
5. 优先使用 `vn_vbpl_bientap_gateway` 的已知 doc id 或搜索接口获取官方 HTML 原文、metadata、provision tree、references。
6. 对需要 signed PDF 的法律，从 `vanban.chinhphu.vn` / `chinhphu.vn` / `datafiles.chinhphu.vn` 获取 PDF，并保留 PDF hash；如果需要 OCR，只能生成候选文本。
7. 对 `official_search_required` 的法律，只能在 VBPL、Chính phủ、Công báo、主管机关官网中定位官方来源；不能把 HSE、Hugging Face、旧 CSV、旧 atom 输出当作官方原文。
8. 正确顺序是：候选法规索引发现 → 官方身份/效力校验 → 官方原文获取 → 条款拆分 → 适用性分级 → 从法规倒推要求 → 检查项原子化 → Codex 复核 → 人工批准 → 正式入库。
9. 所有输出写到 `/Users/HY-yin/.hermes/profiles/compliance/workspace/promotion_artifacts/legal_clause_acquisition/`。
10. 每个法律至少输出 `official_source_resolution.json`、原文 HTML/PDF 或文本、`source_snapshot.json`、`source_hash.sha256`、`metadata.json`、`extracted_original_text.txt`、`legal_clause_candidates.jsonl`、`clause_extraction_quality_report.json`。
11. 所有输出标记为 `CANDIDATE_ONLY_NOT_LIVE`。
12. 不要写入 `/Users/HY-yin/hermes-local/data/knowledge/compliance/`。
13. 不要提交 promotion request，直到抓取、hash、条款候选、质量报告全部完成。
14. 不要声称法律适用、合规通过、正式数据库完成或已经批准。

完成后请回复抓取状态、成功数量、失败数量、每个失败项的 blocker，以及生成的 evidence 路径。
