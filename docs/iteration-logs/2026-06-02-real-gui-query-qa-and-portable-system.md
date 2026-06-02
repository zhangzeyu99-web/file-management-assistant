# 2026-06-02 真实 GUI 查询 QA 与可迁移三层系统

## 本轮判断

项目继续保持三操作主线：添加资料、搜索回顾、生成 AI 上下文包。

参考视频《3层Obsidian文件系统，如何适配所有AI？随时迁移》（BV1Zj5i6MESx）后，本轮不新增 GUI 入口。视频的可用部分是底层组织原则：

- ACT 知识资产：本项目落到添加资料、整理记录、每文件索引和知识卡证据。
- AI 身份文件：本项目落到上下文包里的偏好、协作边界和安全说明。
- Skills / SOP：本项目落到模板、README、测试原则和 harness。

这三层只能增强三操作闭环，不能把首页重新扩成多功能工作台。

## 修复的产品缺陷

### 1. 后端真实查询不能代表 GUI 真实可用

缺陷：`run-real-query-qa.py` 证明后端能检索，但没有证明用户在网页里输入中文问题时能看到证据、路径和下一步。

修复：

- 新增 `scripts/gui-real-query-qa.js`。
- 新增 `scripts/run-real-query-gui-qa.ps1`。
- `verify-harness.ps1` 接入 `real_query_gui_qa`。

验收：

- RED：首次真实 GUI 查询 5 个案例只有 1 个通过。
- GREEN：`run-real-query-gui-qa.ps1 -StrictUx` 通过，5/5 passed。

### 2. 生成 AI 上下文包时检索词被通用包装词污染

缺陷：用户输入 `为“github仓库”生成 AI 上下文包` 时，检索会把 `AI`、`上下文` 当成主题词，导致 preview 首条不复用搜索回顾首条证据。

修复：

- 新增 `extract_search_query()`，从包装式任务中提取真实检索主题。
- `request` 保留用户完整任务，`query` 只用于证据排序。
- 单测覆盖 quoted topic 规范化。

验收：

- `test_extract_preview_uses_quoted_task_topic_instead_of_packaging_words` 先失败后通过。
- 真实 GUI 查询中 `运营sop`、`github仓库`、`简历线程`、`Obsidian助手` 的 extract preview 都复用 review 首条来源。

### 3. 业务未命中不应制造浏览器控制台错误

缺陷：正常未找到返回 HTTP 400，会在浏览器控制台留下资源错误。用户看到的是“未完成”，但 QA 层会记录 console error。

修复：

- 新增 `http_status_for_action_result()`。
- `status=not_found` 改为 HTTP 200 + `ok=false`。
- 真正未知 action 和路径错误仍返回错误状态。

验收：

- `test_not_found_action_results_use_http_200_for_clean_gui_console` 先失败后通过。
- 真实 GUI 查询最终结果：5/5 passed，`ux_issues=0`，`mechanics_failures=0`，`console=0`。

## 这轮自查

- 视觉清晰阅读友好：本轮没有大改视觉，但验证了页面真实结果卡能显示答案、证据、命中词、摘录和路径。
- 总结归纳到位：视频原则已压缩为 ACT / AI 身份文件 / Skills-SOP 三个底层映射，没有扩展新入口。
- 发给别人能看懂：新增 GUI QA summary 用表格列出 query、首条来源、命中词和候选数。
- 传到 Codex 指引性：`CURRENT_ITERATION_PLAN.md`、`TEST_PRINCIPLE.md`、`GUI_E2E_TESTING.md` 已写入新命令和验收。
- GUI 双向交互：已验证搜索结果能进入 extract preview；本轮仍未验证“点击加入上下文包再确认生成”的真实中文案例。
- 信息内容编辑：路径、证据和 summary 已落到 Markdown 报告，后续可继续改为更像飞书文档的段落结构。
- 信息集关联：已要求 extract preview 复用 review 首条来源，避免上下文包从无关证据生成。

## 下一步缺口

- 把真实中文 GUI QA 扩展到“从搜索结果点击加入上下文包，再确认生成”的写入场景，建议使用 demo vault，不直接写真实 vault。
- 继续优化搜索结果卡的文档感，特别是长路径、摘录和操作按钮的阅读层次。
- 把真实查询案例抽成数据文件，避免脚本里硬编码越来越多。

## 本轮追加：近期 Codex 线程归档

用户要求修完已知问题后继续跑近期 Codex 线程归档。本轮新增可复用脚本 `scripts/archive_recent_codex_threads.py`，只读取 `C:\Users\Administrator\.codex\session_index.jsonl` 和原始 `rollout-*.jsonl`，生成索引归档，不移动、不删除、不改写原始会话。

验收结果：

- 单元测试：`python -X utf8 -m unittest tests.test_codex_thread_archive -v` 通过。
- 真实归档范围：2026-05-26 至 2026-06-02。
- 归档线程数：24 条。
- 本地产物：`D:\codex\file-assistant\codex-thread-archive\2026-06-02\codex-thread-delta-archive.md`。
- Manifest：`D:\codex\file-assistant\codex-thread-archive\2026-06-02\codex-thread-delta-manifest.json`。
- Obsidian 产物：`D:\Obsidian-Work\02 项目\Codex\16 Codex 新增线程归档 2026-05-26 至 2026-06-02.md`。
- 关键命中：`运营SOP主库`，线程 ID `019da997-deca-7870-a059-b24ee8e005e1`，原始会话路径已写入归档。

本轮暴露的边界：

- PowerShell `Get-Content` 在当前终端会把 UTF-8 中文显示成乱码，但 Python UTF-8 读回、`rg` 搜索和文件内容本身正常。
- 当前沙箱不适合跑使用默认 `%TEMP%` 的完整 `unittest discover`，需要在授权环境中验证完整套件。

## 本轮追加：搜索结果生成上下文包 GUI 闭环

前一轮留下的核心缺口是：GUI 已能把真实搜索结果带入 `extract preview`，但没有验证用户点击“加入上下文包”之后，再点击“确认生成上下文包”是否真的写出 Markdown 和 Obsidian 笔记。

本轮补齐内容：

- 新增 `scripts/gui-context-package-qa.js`：模拟真人从 `搜索回顾` 输入中文查询，点击来源卡的 `加入上下文包`，再确认生成。
- 新增 `scripts/run-context-package-gui-qa.ps1`：创建临时 demo vault 和 demo runtime，只在测试目录写入，不污染真实 Obsidian vault。
- 更新 `scripts/verify-harness.ps1`：新增 `context_package_gui_qa` 检查项，让完整 harness 覆盖这个闭环。
- 更新 `tests/test_project_quality.py`：要求 GUI QA、runner、harness 都具备“搜索结果 -> 上下文包候选 -> 生成 prompt/Markdown/Obsidian 笔记”的证据。

验收结果：

- 静态 QA：`test_context_package_gui_qa_generates_prompt_from_seeded_review_source` 通过。
- 真实 GUI QA：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-context-package-gui-qa.ps1 -StrictUx` 通过，`ux_issues=0`，`mechanics_failures=0`，`console=0`。
- 完整单元测试：`python -X utf8 -m unittest discover -s tests -v` 通过，114 项。
- 项目质量检查：`python -X utf8 project_quality.py` 通过。
- 完整 harness：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync` 通过。

本轮真实产物：

- GUI QA summary：`D:\codex\file-management-assistant\output\context-package-gui-qa\20260602-173829-260-c05abfe0\gui-context-package-qa-summary.md`
- GUI QA screenshot：`D:\codex\file-management-assistant\output\context-package-gui-qa\20260602-173829-260-c05abfe0\final-page.png`
- 生成的 demo runtime Markdown：`D:\codex\file-management-assistant\output\context-package-gui-qa\20260602-173829-260-c05abfe0\demo-runtime\knowledge-assistant\2026-06-02\173840\extract\20260602-173840 Obsidian 教程闭环证据.md`
- 生成的 demo Obsidian 笔记：`D:\codex\file-management-assistant\output\context-package-gui-qa\20260602-173829-260-c05abfe0\demo-vault\04 例行工作\知识整理助手\提取\20260602-173840 Obsidian 教程闭环证据.md`

本轮自查：

- 视觉清晰阅读友好：本轮重点是补交互真实闭环，未改视觉，但确认生成后不展示 JSON，结果卡显示 prompt 和产物路径。
- 总结归纳到位：上下文包不再停留在候选预览，已验证可从证据生成可复制 prompt。
- 发给别人能看懂：summary 记录 query、首条来源、产物路径和 prompt 预览。
- 传到 Codex 指引性：harness 已加入该链路，后续 Codex 不应再只测 preview。
- GUI 双向交互：已从搜索结果卡片完成到生成文件的真实点击链路。
- 信息内容编辑：生成 Markdown 和 demo Obsidian note 均可直接打开编辑。
- 展示方式方便：仍有下一轮空间，重点是把 prompt 和来源路径做成更像文档卡片的阅读结构。
- 信息集关联：生成只使用搜索命中的已确认来源。
- 发散性思考：当前侧重可靠闭环，后续再优化相近关键词和推荐补充资料。
