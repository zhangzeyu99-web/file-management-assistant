# 2026-06-02 搜索结果证据卡减噪

## 本轮迭代计划

目标：修复 `搜索回顾` 结果区信息密度过高的问题，让页面更像可读知识卡，而不是接口日志或来源堆叠。

验收点：

- 搜索结果默认只展示前 4 条强证据。
- 更多来源不丢失，但折叠为提示，避免首屏拥挤。
- 每条真实证据卡有稳定标记，便于 E2E 按用户可见卡片计数。
- 不改变后端检索排序，不削弱证据来源，只调整默认展示密度。

## TDD 记录

- RED：`test_result_layout_uses_document_cards_for_sources_paths_prompt_and_artifacts` 先失败，当前 HTML 缺少 `data-source-evidence-card`、`visibleSources`、`hiddenSourceCount` 和 `source-more-card`。
- RED：`test_gui_harness_verifies_local_target_workbench` 先失败，E2E 缺少 `review_source_cards_visible_max_four`。
- GREEN：GUI 改为 `sources.slice(0, 4)`；真实证据卡加 `data-source-evidence-card="true"`；更多来源用 `source-more-card` 折叠提示；E2E 统计可见证据卡数量。

## 验证结果

- `python -X utf8 -m unittest tests.test_gui_server.GuiServerTests.test_result_layout_uses_document_cards_for_sources_paths_prompt_and_artifacts -v`：通过。
- `python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_gui_harness_verifies_local_target_workbench -v`：通过。
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx`：通过，`mechanics_failures=0`，`ux_issues=0`。
- E2E 读回：`three_operations.review_source_cards_visible_max_four=true`。

## 自评问题

- 做到了视觉清晰阅读友好了吗：通过。默认 4 条证据减少首屏拥挤，更多来源不再打断阅读。
- 做到了总结归纳到位：部分通过。本轮只处理展示密度，证据摘要质量仍由后端检索和摘录逻辑决定。
- 发给别人能看懂吗：通过。用户能先看少量强证据，再决定是否换关键词继续查。
- 传到 Codex 指引性足够吗：通过。E2E 字段明确记录搜索结果是否超量展示。
- GUI 双向交互方便吗：通过。前 4 条证据仍保留复制路径、打开来源、加入上下文包。
- 信息内容容易编辑吗：通过。搜索框和关键词仍可调整，折叠提示鼓励更具体检索。
- 展示的方式足够方便吗：通过。真实证据卡和更多来源提示分离，视觉层级更清楚。
- 信息集关联有做吗：通过。证据卡仍能继续进入 AI 上下文包。
- 能让人发散性思考吗：部分通过。折叠提示引导换关键词，但还没有提供自动相近关键词。

## 后续关注

- 如果真实查询仍返回弱相关来源，应继续调后端排序和摘要，而不是继续堆更多卡片。
- 可考虑给折叠提示增加“继续搜索相近关键词”的一键建议，但要先有测试证明不是伪功能。
