# 2026-06-02 推荐搜索词一键回顾

## 本轮迭代计划

目标：修复 `添加资料` 后仍需要手动复制关键词到 `搜索回顾` 的断点，让刚入库资料可以被立即验证。

验收点：

- `添加资料` 结果里的推荐搜索词不再只是复制按钮，而是点击后自动填入 `搜索回顾`。
- 点击推荐词后必须真实调用 `review` action，并在结果区展示证据检索结果。
- GUI E2E 必须记录 `three_operations.recommended_search_term_review=true`。
- README、Getting Started、GUI 说明和 E2E 文档同步说明这条闭环。

## TDD 记录

- RED：`test_html_shows_recommended_search_terms_after_organize` 先失败，缺少“点击后会自动填入搜索回顾并执行”和 `runReviewForTerm`。
- RED：`test_gui_harness_verifies_local_target_workbench` 先失败，E2E harness 缺少 `recommended_search_term_review` 和“推荐词一键搜索回顾”。
- GREEN：已实现推荐词按钮调用 `runReviewForTerm`，并补上 E2E 检查逻辑。

## 自评问题

- 做到了视觉清晰阅读友好了吗：本轮没有改大布局，只把“复制按钮”改成更符合用户预期的动作按钮，减少手动中转。
- 做到了总结归纳到位：结果页仍保留推荐词来源说明，新增行为不改变入库摘要。
- 发给别人能看懂吗：文案从“复制后粘贴”改为“点击后自动填入并执行”，操作含义更直接。
- 传到 Codex 指引性足够吗：E2E 报告会明确记录推荐词是否能触发真实 `review`。
- GUI 双向交互方便吗：添加资料后的下一步可直接进入搜索回顾，不再要求用户手动搬运关键词。
- 信息内容容易编辑吗：推荐词仍来自后端 `recommended_search_terms`，用户可继续在搜索框里修改。
- 展示的方式足够方便吗：推荐词作为按钮保留在入库结果中，位置和原先一致，认知负担较小。
- 信息集关联有做吗：入库记录、推荐搜索词、搜索回顾三者形成可验证关联。
- 能让人发散性思考吗：推荐词可以作为继续追问、生成上下文包或补充资料的起点。

## 验证结果

- `python -X utf8 -m unittest tests.test_gui_server.GuiServerTests.test_html_shows_recommended_search_terms_after_organize -v`：通过。
- `python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_gui_harness_verifies_local_target_workbench -v`：通过。
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx`：通过，`mechanics_failures=0`，`ux_issues=0`。
- E2E 读回：`three_operations.recommended_search_term_review=true`。
- `python -X utf8 -m unittest discover -s tests -v`：通过，110 tests。
- `python -X utf8 project_quality.py`：通过。
- `python -X utf8 scripts\audit-feature-contracts.py`：通过，9/9 contracts。
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync`：通过。

## 后续关注

- 如果后续推荐词数量过多，应优先改成“首选 3 个 + 展开更多”，避免结果卡重新变拥挤。
