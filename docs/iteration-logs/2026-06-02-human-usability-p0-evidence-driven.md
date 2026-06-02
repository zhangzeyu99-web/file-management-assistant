# 2026-06-02 真人式 GUI QA 证据闭环迭代自查

## 本轮目标

修复之前发现的产品缺陷：GUI 看起来能操作，但测试脚本没有真正证明三操作闭环。目标是让真人式走读按“添加资料 -> 搜索已沉淀证据 -> 生成 AI 上下文包”验证，而不是用泛问题和过宽断言制造假失败。

## 本轮计划

1. 用质量测试锁定真人式 GUI QA 的产品契约。
2. 修复脚本：使用本轮 fixture 证据词，区分需要动作按钮和不需要动作按钮的结果。
3. 跑严格真人式 GUI QA，记录录屏、截图和 summary。
4. 跑完整回归，确认三操作核心不回退。

## RED 信号

- 首次真人式 GUI QA 严格模式失败：
  - run dir: `D:\codex\file-management-assistant\output\human-usability\20260602-154208-155-002e1d17`
  - actions: 6
  - mechanics_failures: 3
  - ux_issues: 7
  - 失败原因：脚本用宽泛英文查询，严格搜索正确返回无证据；脚本还要求路径检查和无匹配结果也必须出现 `.result-actions`。
- 新增目标质量测试先失败：
  - 命令：`python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_gui_harness_verifies_local_target_workbench -v`
  - 失败点：`Evidence-based review` 尚未写入真人式 GUI QA 脚本。

## 修复内容

- `scripts/gui-human-usability.js`：
  - 搜索问题改为 `Evidence-based review`。
  - 上下文包请求改为 `Evidence-based review context packaging`。
  - `requiredResultLabels` 收敛为只强制 `.result-section`。
  - 通过 `requireResultActions` 只对有明确下一步的成功结果强制检查 `.result-actions`。
  - 未命中检查兼容当前严格搜索文案 `已整理资料中没有命中`。
- `tests/test_project_quality.py`：
  - 增加脚本契约检查，防止真人式 QA 退回泛查询或全局强制 result actions。
- `docs/CURRENT_ITERATION_PLAN.md`：
  - 写入第 7 个产品缺陷和 P0 验收状态。

## 改动证据

- 文件：
  - `scripts/gui-human-usability.js`
  - `tests/test_project_quality.py`
  - `docs/CURRENT_ITERATION_PLAN.md`
  - `docs/superpowers/plans/2026-06-02-human-usability-p0.md`
- 测试：
  - 完整单元测试已通过，106 tests OK。
  - 项目质量脚本已通过，全部 checks ok。
  - 功能契约审计已通过，9/9 passed。
  - GUI E2E 严格模式已通过。
  - 真人式 GUI QA 严格模式已通过。
- 截图：
  - `D:\codex\file-management-assistant\output\human-usability\20260602-154515-858-77d71efc\final-page.png`
- 录屏：
  - `D:\codex\file-management-assistant\output\human-usability\20260602-154515-858-77d71efc\human-usability.webm`
- Obsidian：
  - `D:\Obsidian-Work\02 项目\Codex\迭代记录\2026-06-02 真人式 GUI QA 证据闭环.md`

## 九问自查

| 问题 | 判断 | 证据 | 缺口 | 下一轮改进 |
| --- | --- | --- | --- | --- |
| 做到了视觉清晰阅读友好了吗？ | 部分通过 | 脚本已检查默认不显示 JSON，并保留截图。 | 本轮主要修 QA 脚本，不直接改 CSS。 | 下一轮继续用截图检查搜索结果和上下文包布局。 |
| 做到了总结归纳到位，没有废话不遗漏关键信息了吗？ | 通过 | 本日志把问题收敛为“泛查询 + 全局 action 断言”两类缺陷。 | 真实用户查询仍需要继续扩展样本。 | 增加中文真实查询集。 |
| 发给别人能看懂吗？ | 通过 | 本轮计划、RED、修复、验证按顺序记录。 | 外部用户仍不需要看到脚本细节。 | README 只保留三操作使用说明，不暴露 harness 细节。 |
| 传到 Codex 指引性足够吗？ | 通过 | `docs/superpowers/plans/2026-06-02-human-usability-p0.md` 写明文件、命令和期望结果。 | 后续 Codex 仍需读取最新日志再操作。 | 保持当前计划和日志同步。 |
| GUI 双向交互方便吗？ | 部分通过 | 真人式 QA 覆盖点击、填写、路径检查、搜索、上下文包生成。 | 这证明可走通，不等于所有真实路径和真实问题都好用。 | 增加真实查询：运营sop、github仓库、简历线程、Obsidian助手。 |
| 信息内容容易编辑吗？ | 通过 | 迭代计划和日志均为 Markdown。 | GUI 内联编辑仍不是本轮目标。 | 保持产物都是可编辑 Markdown。 |
| 展示的方式足够方便吗？ | 部分通过 | 默认结果区不展示 raw JSON，脚本会检查 result section。 | 视觉截图还需人工继续挑问题。 | 用截图做下一轮 UI 密度复查。 |
| 信息集关联有做吗？ | 部分通过 | 搜索和提取使用同一证据词，验证“证据 -> 上下文包”关联。 | 还没有把更多历史 Codex 线程做成稳定查询集。 | 把真实 Codex 关键词加入回归用例。 |
| 能让人发散性思考吗？ | 部分通过 | 上下文包从证据生成 prompt，能支持继续问 AI。 | 当前迭代优先闭环，不做知识流发散。 | 发散能力放在搜索结果推荐词和上下文包下一步请求里。 |

## 验证记录

- 目标质量测试通过：`python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_gui_harness_verifies_local_target_workbench -v`。
- 真人式 GUI QA 严格模式通过：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-human-usability.ps1 -StrictUx`。
  - run dir: `D:\codex\file-management-assistant\output\human-usability\20260602-154515-858-77d71efc`
  - actions: 6
  - mechanics_failures: 0
  - ux_issues: 0
  - console: 0
- 完整单元测试通过：`python -X utf8 -m unittest discover -s tests -v`，106 tests OK。
- 项目质量脚本通过：`python -X utf8 project_quality.py`，全部 checks ok。
- 功能契约审计通过：`python -X utf8 scripts\audit-feature-contracts.py`，9/9 passed。
- GUI E2E 严格模式通过：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx`。
  - run dir: `D:\codex\file-management-assistant\output\gui-e2e\20260602-155313-840-274ce0c3`
  - actions: 6
  - mechanics_failures: 0
  - ux_issues: 0
- 真人式 GUI QA 严格模式刷新通过：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-human-usability.ps1 -StrictUx`。
  - run dir: `D:\codex\file-management-assistant\output\human-usability\20260602-155351-160-5558f955`
  - actions: 6
  - mechanics_failures: 0
  - ux_issues: 0
  - console: 0
- 总 harness 通过：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync`。
  - unit_tests: ok
  - feature_contracts: ok
  - core_loop_real: ok
  - gui_e2e: ok
  - backup_manifest: ok

## 下一轮改进

- 用真实查询集继续压测搜索准确性：`运营sop`、`github仓库`、`简历线程`、`Obsidian助手`、不存在关键词。
- 检查搜索结果截图，继续减少路径、摘录和按钮的视觉拥挤。
- 把“加入上下文包 -> 生成 prompt”的证据来源展示做成更稳定的可读结构。
