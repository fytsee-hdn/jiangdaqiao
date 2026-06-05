# 越南法律文件来源途径摘要

- 状态：source_pathway_manifest_only_no_legal_targets_not_live
- 这是“法律文件来源途径”摘要，只能描述来源分级、来源 URL、读取方式、官方验证门槛。
- 这个摘要和同名 manifest 不得包含具体法律、法规、QCVN、条款目标、条款名称或分级清单。
- 不要读取或使用预制 candidate target queue；这种文件容易被误读成“准法律清单”。
- 法规库建设必须先从官方来源倒推“尽可能完整的候选法规索引”，再由法规原文倒推条款、要求和检查项。
- 用户不需要先知道法律领域或业务范围；业务范围只能作为后续过滤、优先级排序或适用性判断条件，不能作为启动法规库建设的前提。
- 如果需要处理具体法规目标，必须从即时官方来源发现开始，生成本次任务的候选发现结果；正式入库仍需要 Hermes 输出 evidence、Codex 复核、人工批准、Codex promotion。

核心官方来源：

- VBPL Biên tập Gateway: `https://vbpl-bientap-gateway.moj.gov.vn/api`
- Chính phủ / vanban：`https://vanban.chinhphu.vn/`, `https://chinhphu.vn/`, `https://datafiles.chinhphu.vn/`。PDF 主要作为身份/发布证据和 hash 留存；原文入库优先使用可解析 HTML/API/结构化文本，PDF OCR 文本只作为候选。
- Công báo: `https://congbao.chinhphu.vn/`
- 主管部委官网：用于 QCVN/技术法规附件和版本有效性验证

第三方来源只能作为发现或交叉验证：

- `https://thuvienphapluat.vn` / Hugging Face / TVPL / LawNet / LuatVietnam / ATLD / GitHub 数据集可作为候选原文恢复、发现和交叉验证来源，但不能作为正式法律来源、official verified 原文或效力状态依据。
