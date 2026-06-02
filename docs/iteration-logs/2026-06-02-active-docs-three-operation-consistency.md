# 活跃产品文档三操作一致性迭代

## 本轮计划

目标：修复之前发现的产品缺陷：活跃文档仍保留旧的内容浏览和卡片浏览方向，容易把项目从 `添加资料 / 搜索回顾 / 生成 AI 上下文包` 拉回功能堆叠。

计划：

1. 用质量测试先锁住旧产品叙事不能回流。
2. 重写活跃产品文档，让研究、复盘和展示方法都服务三操作闭环。
3. 把缺陷、修复和验收写入当前迭代计划。
4. 跑目标测试、完整单测、质量脚本、GUI E2E 和 harness。

## RED 信号

新增质量约束前，活跃产品文档仍可能出现旧方向表达：

- 首页内容浏览方向。
- 下滑浏览资料方向。
- 卡片浏览替代证据检索方向。

这些表达和当前产品定义冲突：用户第一眼只应该看到三个真实操作，而不是内容浏览、提醒、诊断或伪控制台。

## 修复内容

- `docs/PRODUCT_UI_RESEARCH.md`：改为三操作 UI 研究摘记，只保留成熟文件管理和知识管理经验中能落到当前闭环的部分。
- `docs/PRODUCT_RETROSPECTIVE_AND_NEXT_PLAN.md`：改为三阶段深化计划，重点是添加资料做实、搜索回顾证据化、AI 上下文包可追溯。
- `docs/KNOWLEDGE_DISPLAY_METHOD.md`：改为结果卡展示方法，结构为一句话答案、命中证据、来源路径、生成产物、下一步。
- `docs/CURRENT_ITERATION_PLAN.md`：补充本轮产品缺陷和验收标准。
- `tests/test_project_quality.py`：把三份活跃文档纳入旧方向禁用检查。

## 自查问题

- 做到了视觉清晰阅读友好了吗：本轮没有重做界面视觉，但清理了会误导界面回退的文档方向；展示方法明确为结果卡而不是内容堆叠。
- 做到了总结归纳到位：通过。三个文档都围绕真实闭环写：入库、证据检索、上下文包。
- 发给别人能看懂吗：通过。文档先讲产品是什么，再讲每个操作的输入、输出和边界。
- 传到 Codex 指引性足够吗：通过。当前迭代计划写明下一轮优先级和质量门禁，后续 Codex 不应恢复旧入口。
- GUI 双向交互方便吗：本轮只修产品文档和计划，未新增交互；已有计划继续要求推荐搜索词、加入上下文包和来源路径操作。
- 信息内容容易编辑吗：通过。文档改为短段、列表和验收标准，方便后续局部修改。
- 展示的方式足够方便吗：部分通过。展示方法已定义，但仍需后续 GUI 走读验证视觉密度。
- 信息集关联有做吗：部分通过。关联被收敛到证据来源和上下文包，不再放到首页内容流。
- 能让人发散性思考吗：部分通过。当前阶段优先收敛，不鼓励发散浏览；下一步可在搜索结果中增加相近关键词建议。

## 验证记录

- 目标质量测试通过：`python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_public_docs_do_not_promote_knowledge_feed_as_core_flow -v`。
- 完整单元测试通过：`python -X utf8 -m unittest discover -s tests -v`，111 tests OK。
- 项目质量脚本通过：`python -X utf8 project_quality.py`，全部 checks ok。
- 功能契约审计通过：`python -X utf8 scripts\audit-feature-contracts.py`，9/9 passed。
- GUI E2E 严格模式通过：`scripts\run-gui-e2e.ps1 -StrictUx`，actions=6，mechanics_failures=0，ux_issues=0。
- verify harness 通过：`scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync`，unit_tests、feature_contracts、core_loop_real、gui_e2e、backup_manifest 均 ok。
