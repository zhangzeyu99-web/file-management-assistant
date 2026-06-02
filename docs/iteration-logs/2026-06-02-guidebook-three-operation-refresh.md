# 2026-06-02 教程资料包三操作刷新

## 本轮迭代计划

目标：修复教程资料包和当前产品主线不一致的问题。GUI 已经收敛为 `添加资料 / 搜索回顾 / 生成 AI 上下文包`，但生成教程脚本仍残留旧知识流、四入口和提醒叙事，容易误导新手。

验收点：

- 生成教程脚本必须围绕三步闭环组织。
- 教程脚本必须解释 `推荐搜索词`、`最多 4 条强证据`、`加入上下文包`。
- 教程脚本不得再出现 `知识流怎么用`、`向下看知识流`、`四入口`、`需要提醒时`。
- 重新生成 `interaction-map.png`、`interaction-states.png`、7 页 PNG 和 PDF。
- `docs/guidebook/README.md` 页码说明要与新教程一致。

## TDD 记录

- RED：新增 `test_generated_guidebook_script_matches_three_operation_positioning` 后失败，脚本缺少 `推荐搜索词`，且仍保留旧教程叙事。
- GREEN：重写 `scripts/generate-guidebook-assets.py` 的交互图、状态图和 7 页教程文案，目标测试通过。

## 生成产物

- `docs/assets/gui/interaction-map.png`
- `docs/assets/gui/interaction-states.png`
- `docs/guidebook/slides/page-01.png` 至 `page-07.png`
- `docs/guidebook/knowledge-action-assistant-tutorial.pdf`

## 自评问题

- 做到了视觉清晰阅读友好了吗：通过。抽查 page-04，标题、说明和两栏卡片清楚。
- 做到了总结归纳到位：通过。教程从旧知识流改为添加资料、搜索回顾、上下文包三步。
- 发给别人能看懂吗：通过。新手不需要理解旧工具或诊断入口。
- 传到 Codex 指引性足够吗：通过。测试约束了脚本中的核心词和禁用旧词。
- GUI 双向交互方便吗：间接通过。教程明确推荐搜索词可验证入库，搜索结果可加入上下文包。
- 信息内容容易编辑吗：通过。教程文案集中在生成脚本，后续统一改一处即可重生 PDF。
- 展示的方式足够方便吗：通过。7 页结构按学习路径排列，不再混入旧知识流页。
- 信息集关联有做吗：通过。教程把入库、搜索证据、上下文包串起来。
- 能让人发散性思考吗：部分通过。教程强调用证据给 AI 续用，但还没有更多案例题。

## 后续关注

- 如果后续 GUI 有交互变化，必须同步重生 guidebook，而不是只改 README。
- 可补一页真实案例，但要避免把教程再次扩成复杂功能说明。
