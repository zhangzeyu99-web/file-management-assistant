# GUI 旧内容流后端清理迭代

## 本轮计划

目标：继续把项目做成方便的本地知识管理库，而不是保留多个互相竞争的产品形态。本轮清理公共界面已经不使用、但仍留在服务端和测试里的旧内容流后端。

计划：

1. 补质量测试，明确 GUI 服务端不能继续保留旧内容流后端。
2. 删除旧内容流构建、卡片详情、关联推荐和对应测试。
3. 修正真人走读脚本，只验证三个主入口。
4. 跑目标测试、GUI 单元测试、完整测试、质量脚本、GUI E2E 和 harness。

## RED 信号

新增质量测试先失败，失败点是 `gui_server.py` 仍包含 `def build_knowledge_feed`。随后把真人走读脚本也纳入同一质量测试，失败点是脚本仍在点击旧内容浏览锚点。

## 修复内容

- `gui_server.py` 删除旧内容流后端，服务端保留更薄的职责：状态、三主 action、路径检查、打开路径。
- `tests/test_gui_server.py` 删除旧内容流专用测试，不再为了旧功能自证维护价值。
- `scripts/gui-human-usability.js` 把“跳到旧内容浏览区”改成“三个主入口都可见”。
- `tests/test_project_quality.py` 增加防回归测试，禁止旧后端函数、旧锚点和旧卡片选择器回流。
- `docs/CURRENT_ITERATION_PLAN.md` 记录本轮缺陷、修复和验收。

## 自查问题

- 做到了视觉清晰阅读友好了吗：通过。虽然本轮不改 CSS，但删除了会诱导恢复旧卡片流的后端，界面主线更干净。
- 做到了总结归纳到位：通过。缺陷被定义为“公共界面已收敛，服务端仍残留旧产品形态”。
- 发给别人能看懂吗：通过。三主操作是唯一主线，旧内容浏览不再作为隐藏实现存在。
- 传到 Codex 指引性足够吗：通过。质量测试会阻止后续 Codex 重新引用旧后端。
- GUI 双向交互方便吗：不直接改变交互，但真人走读脚本已经改为围绕三入口、路径检查、搜索和上下文包。
- 信息内容容易编辑吗：通过。旧内容流的解析和关联函数删除后，服务端更容易维护。
- 展示的方式足够方便吗：部分通过。结果卡仍是主展示；本轮主要减少旧展示路线。
- 信息集关联有做吗：本轮收敛为搜索证据和上下文包关联，不再维护首页卡片关联。
- 能让人发散性思考吗：本轮不鼓励无目标浏览；后续发散应通过搜索结果的相近关键词和上下文包来源完成。

## 验证记录

- 目标质量测试通过：`python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_gui_server_does_not_keep_deprecated_knowledge_feed_backend -v`。
- GUI 服务端测试通过：`python -X utf8 -m unittest tests.test_gui_server -v`，19 tests OK。
- 完整单元测试通过：`python -X utf8 -m unittest discover -s tests -v`，106 tests OK；测试数量减少来自删除旧内容流测试。
- 项目质量脚本通过：`python -X utf8 project_quality.py`，全部 checks ok。
- 功能契约审计通过：`python -X utf8 scripts\audit-feature-contracts.py`，9/9 passed。
- GUI E2E 严格模式通过：`scripts\run-gui-e2e.ps1 -StrictUx`，actions=6，mechanics_failures=0，ux_issues=0。
- verify harness 通过：`scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync`，unit_tests、feature_contracts、core_loop_real、gui_e2e、backup_manifest 均 ok。
