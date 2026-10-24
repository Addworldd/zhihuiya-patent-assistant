# 纯 MCP 工具直接调用兜底指南

若当前运行环境无法执行本地 Python 脚本 `scripts/zhihuiya_helper.py`，请直接调用已挂载的 `zhihuiya` MCP 工具完成查询：

## 1. 主体/领域概览调用顺序
1. 调用 `search_patents`：
   - 参数：`query_text`（如 `"ANC:(华为) AND TAC:(折叠屏)"`），`limit: 10`，`sort_field: "SCORE"`。
2. 提取返回结果中的 `total_search_result_count`（专利总数）及前 5~8 条专利的 `patent_id`、`pn`、`title`、`current_assignee`、`apdt`。
3. 针对前 5 条专利，调用 `get_patent_legal_status` 获取每件专利的 `simple_legal_status`。
4. 若所选模板包含模块 `E`（技术焦点总结），调用 `bibliography` 获取 `abstracts` 摘要文本。

## 2. 单篇专利精读调用顺序
根据用户所选模板激活的模块按需调用（传入 `patent_number` 或 `patent_id`）：
- **模块 A（基础著录项）**：调用 `bibliography` + `get_patent_legal_status`
- **模块 B（摘要与摘要附图）**：调用 `bibliography` + `abstract_image`（将返回的 `abstract_drawing.path` 以 `![摘要附图](url)` 渲染）
- **模块 C/D（权利要求拆解）**：调用 `claims`（识别 `<div class="indep-clm">` 为独立权利要求，`<div class="dep-clm">` 为从属权利要求）
- **模块 E/F/G（说明书关键段落）**：调用 `description`（按 `技术领域`、`背景技术`、`发明内容`、`附图说明`、`具体实施方式` 切分）
- **模块 H（附图说明与全文附图配对）**：调用 `description` + `fulltext_image`。将 `description` 中 `<a class="see-img-anchor" img-id="XXX" img-title="图1">` 的 `img-id` 与 `fulltext_image` 返回 URL 中的文件名 `XXX.png` 配对，并用 `![图1](url)` 直接渲染
- **模块 I（法律风险）**：调用 `get_patent_legal_status`、`reexamination_invalidation`、`transfer_data`、`pledge_data`、`license_data`
- **模块 J（同族与被引）**：调用 `family`、`forward_citation`
- **模块 K（PDF 全文）**：调用 `pdf`（将返回的 `pdf.path` 以 `[下载PDF全文](url)` 渲染）
- **模块 L（多语种翻译）**：调用 `abstract_translated`、`claim_translated`（`lang: "CN"`）
