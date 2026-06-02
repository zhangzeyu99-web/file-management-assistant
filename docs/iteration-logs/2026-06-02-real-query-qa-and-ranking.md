# 2026-06-02 真实查询 QA 与搜索排序迭代自查

## 本轮目标

把“逐个功能 QA”继续往真实使用推进：不仅跑 GUI fixture，还要用真实 Obsidian / 报告 / Codex 归档跑固定中文查询，并修复真实报告暴露的排序缺陷。

## 本轮计划

1. 补真实查询 QA 脚本，固定跑 `运营sop`、`github仓库`、`简历线程`、`Obsidian助手`，并为无匹配场景动态生成 no-match token。
2. 让 QA 同时检查 `review` 和 `extract preview`，只读验证，不生成上下文包。
3. 修复过程日志抢占首条、同一文件重复入索引、教程型来源不优先的问题。
4. 跑真实 QA 和单元回归，再把证据落盘。

## RED 信号

- `test_real_query_qa_script_tracks_true_user_queries` 先失败：`scripts/run-real-query-qa.py` 不存在。
- 真实查询 QA 第一次严格化后失败：`Obsidian助手` 首条是 `2026-06-02 真人式 GUI QA 证据闭环`，不是教程或指南。
- `test_review_prioritizes_user_guides_over_iteration_logs_for_obsidian_assistant` 先失败：存在指南、日记链接和迭代记录时，首条仍是迭代记录或日记。
- `test_review_index_dedupes_notes_seen_from_vault_and_watch_roots` 先失败：同一 vault 文件从 vault root 和 watch root 进入索引两次。

## 修复内容

- 新增 `scripts/run-real-query-qa.py`：
  - 默认读取 `config.local.json`。
  - 只执行 `review` 和 `extract` 的 `mode: "preview"`。
  - 无匹配查询每次动态生成，避免固定假词被写进 Obsidian 后污染下一次搜索。
  - 输出 `real-query-qa-result.json` 和 `summary.md`。
  - 失败时退出非 0。
- `knowledge_assistant.py`：
  - `build_review_index_uncached` 增加全局 path 去重。
  - 新增 `is_iteration_or_qa_item` 和 `query_wants_iteration_or_qa`，普通知识查询下降权过程日志。
  - 新增 `is_user_guide_item`，教程/指南型来源在标题或路径命中全部查询词时加权。
- `scripts/verify-harness.ps1`：
  - 新增 `real_query_qa` 检查。
  - 有 `config.local.json` 时运行真实查询 QA；没有本地配置时安全跳过。
- 测试：
  - 增加真实查询 QA 脚本契约测试。
  - 增加指南优先于迭代日志/日记链接的排序测试。
  - 增加索引全局去重测试。
- 文档：
  - `docs/TEST_PRINCIPLE.md` 写入真实查询 QA 命令和合格标准。
  - `docs/GUI_E2E_TESTING.md` 增加 Real Query QA 区块。

## 改动证据

- 文件：
  - `knowledge_assistant.py`
  - `scripts/run-real-query-qa.py`
  - `tests/test_knowledge_assistant.py`
  - `tests/test_project_quality.py`
  - `docs/TEST_PRINCIPLE.md`
  - `docs/GUI_E2E_TESTING.md`
  - `docs/CURRENT_ITERATION_PLAN.md`
- 真实 QA：
  - `D:\codex\file-management-assistant\output\real-query-qa\20260602-161849\summary.md`
  - `D:\codex\file-management-assistant\output\real-query-qa\20260602-161849\real-query-qa-result.json`
- Obsidian：
  - `D:\Obsidian-Work\02 项目\Codex\迭代记录\2026-06-02 真实查询 QA 与搜索排序.md`

## 九问自查

| 问题 | 判断 | 证据 | 缺口 | 下一轮改进 |
| --- | --- | --- | --- | --- |
| 做到了视觉清晰阅读友好了吗？ | 部分通过 | QA summary 用表格和分段展示查询、首条来源、命中词和摘录。 | 本轮主要修后端排序，不直接改 GUI 视觉。 | 把真实 QA 的报告结构映射到 GUI 搜索结果展示。 |
| 做到了总结归纳到位，没有废话不遗漏关键信息了吗？ | 通过 | 真实 QA 记录每个查询的答案、来源、命中词、摘录、preview 候选数。 | 还没有把所有历史高频问题都纳入固定集。 | 下一轮增加“运营SOP主库线程”“Codex 启动仓库”等精确问题。 |
| 发给别人能看懂吗？ | 通过 | `summary.md` 能直接看出哪个查询通过、首条是什么、证据是什么。 | 非技术用户仍不需要看 JSON。 | GUI 里只展示 Markdown 同款结构。 |
| 传到 Codex 指引性足够吗？ | 通过 | `docs/TEST_PRINCIPLE.md`、`docs/GUI_E2E_TESTING.md` 和 `verify-harness.ps1` 都已写入真实查询 QA。 | 后续需要继续扩展查询集。 | 下一轮增加更多真实问题。 |
| GUI 双向交互方便吗？ | 部分通过 | 后端结果更准确，减少 GUI 展示错误来源的概率。 | 本轮没有跑真实 GUI 输入这些中文查询。 | 下一轮让 Playwright 在 live/read-only 模式跑真实查询。 |
| 信息内容容易编辑吗？ | 通过 | QA 报告和迭代记录都是 Markdown。 | 真实 QA 查询集目前写在脚本中。 | 后续可抽成 JSON 用例文件。 |
| 展示的方式足够方便吗？ | 部分通过 | 报告表格已能快速看首条来源和命中词。 | GUI 搜索结果仍可能在长摘录下拥挤。 | 用截图继续检查 `review` 结果卡。 |
| 信息集关联有做吗？ | 通过 | 每个查询都验证 `review` 首条是否能被 `extract preview` 复用。 | 只验证 preview，不生成最终 prompt。 | 下一轮抽一个安全 fixture 生成 prompt。 |
| 能让人发散性思考吗？ | 部分通过 | 结果保留 4 个候选来源，可继续生成上下文包。 | 不做知识流浏览。 | 在上下文包 prompt 里强化“下一步问题建议”。 |

## 验证记录

- 目标测试通过：
  - `python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_real_query_qa_script_tracks_true_user_queries -v`
  - `python -X utf8 -m unittest tests.test_knowledge_assistant.KnowledgeAssistantTests.test_review_prioritizes_user_guides_over_iteration_logs_for_obsidian_assistant tests.test_knowledge_assistant.KnowledgeAssistantTests.test_review_index_dedupes_notes_seen_from_vault_and_watch_roots -v`
- 真实查询 QA 通过：`python -X utf8 scripts\run-real-query-qa.py`
  - run dir: `D:\codex\file-management-assistant\output\real-query-qa\20260602-161339`
  - total: 5
  - passed: 5
  - failed: 0
  - `Obsidian助手` 首条：`2026-04-27 Obsidian 助手学习指南`
- 动态 no-match 修复后验证：无匹配查询 `__no_such_topic_<timestamp>__` 返回 0 candidates。
- 总 harness 内置真实查询 QA 通过：
  - `real_query_qa`: ok
  - run dir: `D:\codex\file-management-assistant\output\real-query-qa\20260602-161849`
  - total: 5
  - passed: 5
  - failed: 0
- 完整单元测试通过：`python -X utf8 -m unittest discover -s tests -v`，109 tests OK。
- 项目质量脚本通过：`python -X utf8 project_quality.py`，全部 checks ok。
- 功能契约审计通过：`python -X utf8 scripts\audit-feature-contracts.py`，9/9 passed。
- GUI E2E 严格模式通过：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx`。
  - run dir: `D:\codex\file-management-assistant\output\gui-e2e\20260602-161404-089-52b8bb9c`
  - actions: 6
  - mechanics_failures: 0
  - ux_issues: 0
- 真人式 GUI QA 严格模式通过：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-human-usability.ps1 -StrictUx`。
  - run dir: `D:\codex\file-management-assistant\output\human-usability\20260602-161404-082-c6aa4f43`
  - actions: 6
  - mechanics_failures: 0
  - ux_issues: 0
  - console: 0
- 总 harness 通过：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync`。
  - unit_tests: ok
  - feature_contracts: ok
  - real_query_qa: ok
  - core_loop_real: ok
  - gui_e2e: ok
  - backup_manifest: ok

## 下一轮改进

- 为真实 GUI 增加只读中文查询走读，不只跑后端。
- 继续改搜索结果卡排版，减少长证据摘录和长路径的视觉压力。
