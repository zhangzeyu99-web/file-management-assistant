# 结果卡阅读结构迭代

## 目标

继续修复 GUI 里“人类能不能看懂”的问题。上一轮已补齐 `搜索回顾 -> 加入上下文包 -> 确认生成` 的真实闭环，但截图显示结果区仍有两个产品问题：

- 结果卡固定在右栏，左侧留下大块空白，长路径和证据阅读区域被压窄。
- 来源、路径、prompt 和操作按钮虽然分区存在，但缺少明确阅读顺序和使用说明。

## 改动

- 来源证据卡增加 `阅读顺序`、`命中词`、`为什么相关`、`证据摘录`、`来源路径`、`操作`。
- 路径区明确提示 `路径不会被截断，可横向滚动后复制`，避免用户误以为路径被截断。
- Prompt 预览区增加 `怎么使用这个 prompt`：先复制 prompt，再粘贴到新的 AI 对话，并要求 AI 引用来源路径。
- 生成产物卡改成同样的路径阅读结构，减少路径和按钮混在一起的感觉。
- `.site-action-result` 从右栏固定展示改成跨整行展示，输入区在上，结果文档在下，避免结果区域过窄。
- 增加 `test_result_cards_explain_reading_order_paths_and_prompt_usage` 防止展示退回字段堆叠或右栏固定。

## 验收

- 静态 GUI 测试：`python -X utf8 -m unittest tests.test_gui_server.GuiServerTests.test_result_cards_explain_reading_order_paths_and_prompt_usage -v` 通过。
- GUI server 测试：`python -X utf8 -m unittest tests.test_gui_server -v` 通过。
- 项目质量检查：`python -X utf8 project_quality.py` 通过。
- 完整单元测试：`python -X utf8 -m unittest discover -s tests -v` 通过，115 项。
- 真实上下文包 GUI QA：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-context-package-gui-qa.ps1 -StrictUx` 通过。
- 完整 harness：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync` 通过。

真实截图证据：

- 新布局截图：`D:\codex\file-management-assistant\output\context-package-gui-qa\20260602-175019-252-8ce69fc2\final-page.png`
- 完整 harness 截图：`D:\codex\file-management-assistant\output\context-package-gui-qa\20260602-175407-184-30fa9048\final-page.png`

## 自查

| 问题 | 判断 | 证据 | 缺口 | 下一轮改进 |
| --- | --- | --- | --- | --- |
| 做到了视觉清晰阅读友好了吗 | 部分通过 | 结果区跨整行，来源卡按阅读顺序、原因、摘录、路径、操作分区。 | 仍未做完整视觉审美重构，只修了最影响阅读的结果区。 | 用真实查询截图继续检查搜索成功、无结果、上下文包生成三种状态。 |
| 做到了总结归纳到位，没有废话不遗漏关键信息了吗 | 部分通过 | 卡片明确显示为什么相关、证据摘录和来源路径。 | 摘录质量仍依赖后端证据抽取。 | 下一轮检查真实关键词下的摘录是否足够短、准、可引用。 |
| 发给别人能看懂吗 | 部分通过 | prompt 区增加怎么使用说明，路径区解释不会截断。 | 首次使用者仍可能不知道“加入上下文包”和“预览候选”的区别。 | 在三操作说明里补一段更短的流程提示。 |
| 传到 Codex 指引性足够吗 | 通过 | 新测试明确禁止右栏固定和字段堆叠回归。 | 需要保持 harness 长期运行，否则 UI 容易再次退化。 | 把结果卡截图纳入视觉回归清单。 |
| GUI 双向交互方便吗 | 部分通过 | 真实 QA 仍能点击加入上下文包并生成文件。 | 当前只是按钮可用，还没有批量选择多个来源。 | 后续考虑多来源选择，但不能牺牲三主操作清晰度。 |
| 信息内容容易编辑吗 | 部分通过 | 生成 Markdown 和 Obsidian note 仍保留，路径更容易复制打开。 | GUI 本身不直接编辑笔记内容。 | 维持本地编辑优先，GUI 只负责找回和打开。 |
| 展示的方式足够方便吗 | 部分通过 | 结果文档更宽，长路径可滚动，prompt 有独立使用说明。 | 长 prompt 仍只做滚动预览。 | 后续增加 prompt 摘要和完整复制的分离。 |
| 信息集关联有做吗 | 通过 | 来源卡可直接加入上下文包，生成只引用已确认来源。 | 暂无语义关联图。 | 用推荐搜索词和下一步请求承载轻量关联。 |
| 能让人发散性思考吗 | 部分通过 | Prompt 使用说明要求继续查证和引用来源。 | 发散仍弱于专门知识图谱。 | 下一轮从搜索结果生成 2-3 个可追问问题。 |

