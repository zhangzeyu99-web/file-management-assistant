# 添加资料真实入库 GUI QA 收口

## 目标

继续按三主操作闭环做逐功能 QA。本轮只补 `添加资料` 的真实 GUI 入库验证，避免产品停留在“按钮能点、结果看起来完成”的层面。

要证明的链路：

1. 用户在 GUI 粘贴真实本地目录。
2. 点击 `检查本地目标` 能识别目录存在。
3. 点击 `添加资料` 会扫描目录文件。
4. 每个可读文件生成独立文件索引笔记。
5. 立即用 `搜索回顾` 搜该目录里的唯一证据词，能命中新生成的文件索引。

## 改动

- 新增 `scripts/gui-organize-ingest-qa.js`：模拟真人在 GUI 中粘贴目录、检查目标、添加资料、再搜索回顾。
- 新增 `scripts/run-organize-ingest-gui-qa.ps1`：创建临时 `demo-source`、`demo-vault`、`demo-runtime`，只在测试输出目录写入，不污染真实 Obsidian。
- 更新 `scripts/verify-harness.ps1`：新增 `organize_ingest_gui_qa`，放在上下文包 QA 前执行。
- 更新 `tests/test_project_quality.py`：要求 organize ingest GUI QA、runner 和 harness 均存在且包含关键断言。
- 更新 `docs/assets/gui/workspace.html` 与 `tests/test_gui_server.py`：补 `overflow-wrap: anywhere`，避免长证据标题撑破卡片。

## 验收

- 静态质量测试：`test_organize_ingest_gui_qa_scans_real_directory_and_reviews_evidence` 通过。
- 结果卡展示测试：`test_result_cards_explain_reading_order_paths_and_prompt_usage` 通过。
- 真实 GUI QA：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-organize-ingest-gui-qa.ps1 -StrictUx` 通过。
- 项目质量检查：`python -X utf8 project_quality.py` 通过。
- 完整单元测试：`python -X utf8 -m unittest discover -s tests -v` 通过，116 项。
- 完整 harness：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync` 通过。

真实证据：

- QA summary：`D:\codex\file-management-assistant\output\organize-ingest-gui-qa\20260603-101639-328-fd30060f\gui-organize-ingest-qa-summary.md`
- QA screenshot：`D:\codex\file-management-assistant\output\organize-ingest-gui-qa\20260603-101639-328-fd30060f\final-page.png`
- 生成文件索引 1：`D:\codex\file-management-assistant\output\organize-ingest-gui-qa\20260603-101639-328-fd30060f\demo-vault\routine\knowledge-organizer\文件索引\20260603-101655-001 alpha-ingest.md`
- 生成文件索引 2：`D:\codex\file-management-assistant\output\organize-ingest-gui-qa\20260603-101639-328-fd30060f\demo-vault\routine\knowledge-organizer\文件索引\20260603-101655-002 beta-ingest.md`
- 搜索命中来源：`D:\codex\file-management-assistant\output\organize-ingest-gui-qa\20260603-101639-328-fd30060f\demo-vault\routine\knowledge-organizer\文件索引\20260603-101655-002 beta-ingest.md`

## 自查

| 问题 | 判断 | 证据 | 缺口 | 下一轮改进 |
| --- | --- | --- | --- | --- |
| 做到了视觉清晰阅读友好了吗 | 部分通过 | 搜索结果证据卡能显示一句话答案、命中证据、路径和来源；长标题已避免撑破卡片。 | 添加资料完成后的结果仍偏信息密集。 | 下一轮检查添加资料结果本身的摘要密度和按钮顺序。 |
| 做到了总结归纳到位，没有废话不遗漏关键信息了吗 | 通过 | QA 强制检查扫描数、文件索引数、搜索命中来源路径。 | 摘录是否足够“像人话”仍要靠真实资料继续测。 | 加一个更接近用户真实资料的 fixture。 |
| 发给别人能看懂吗 | 部分通过 | Summary 写明 demo-source、demo-vault、扫描文件数、生成索引和命中路径。 | 仍需要把 QA 报告做得更短。 | 后续把运行报告压成“做了什么 / 产物在哪 / 是否通过”。 |
| 传到 Codex 指引性足够吗 | 通过 | 新 harness 项会阻止未来只测 inspect 或只测 organize，不测搜索找回。 | 还没有对多层目录和不可读文件做 GUI QA。 | 增加多层目录、二进制文件、空目录边界场景。 |
| GUI 双向交互方便吗 | 通过 | 用户从 GUI 粘贴目录后，无需手工跑 Python，即可完成入库和回顾。 | 文件选择器仍只能提供元数据，真实扫描仍需粘贴路径。 | 保持当前边界，避免声称浏览器能扫描本机目录。 |
| 信息内容容易编辑吗 | 通过 | 独立文件索引写入 demo Obsidian vault，可直接打开编辑。 | GUI 不直接编辑文件索引。 | 仍以 Obsidian 编辑为主。 |
| 展示的方式足够方便吗 | 部分通过 | 来源卡和路径结构可读；长标题换行。 | 添加资料结果截图还需单独做视觉验收。 | 下一轮保存并检查添加资料完成态截图。 |
| 信息集关联有做吗 | 通过 | 搜索回顾命中新生成的文件索引，证明入库和回顾连接起来了。 | 只测了一个唯一关键词。 | 增加文件名、路径片段、正文片段三类检索。 |
| 能让人发散性思考吗 | 部分通过 | 添加资料后已有推荐搜索词和下一步建议。 | 发散问题生成仍不强。 | 在搜索结果里补“可继续追问”的轻量建议。 |

