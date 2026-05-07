# UX Feedback Log

This document records real usage feedback before implementation. Do not treat these items as solved until the acceptance checks are met in the GUI.

## 2026-05-07 GUI trial feedback

Source: user tested the local GUI at `http://127.0.0.1:8765/`.

### UX-2026-05-07-01: 操作台结果只显示代码框，和真实命令/动作连不上

Priority: P0

Current behavior:
- 点击「查看文件雷达」后，今日操作台下面只展开一个深色 JSON / code 输出框。
- 用户看到的是 `summary_json`、`html_report`、`markdown_report` 等字段，而不是可操作的结果。
- 右侧虽然有一条成功结果，但主操作区没有清楚说明“刚才做了什么、结果在哪、下一步能点什么”。

User impact:
- 非开发者会把 JSON 当成“代码错误”或“没连上实际命令”。
- 用户无法直观看到扫描结果，也不知道应该打开哪个报告或继续哪一步。

Expected behavior:
- 默认展示人能读懂的结果卡片，而不是默认展开 JSON。
- JSON 只作为“高级详情 / 调试信息”隐藏在二级入口。
- 每次执行后应展示：动作名称、处理对象、结果摘要、产出路径、下一步按钮。

Acceptance checks:
- 点击「查看文件雷达」后，主操作区首先出现“文件雷达扫描完成”结果卡。
- 结果卡包含「打开 HTML 报告」「打开 Obsidian 记录」「复制报告路径」「查看高级 JSON」。
- 默认不展示深色代码框。
- 失败时展示清楚错误原因和可重试按钮，而不是只显示 raw JSON。

### UX-2026-05-07-02: 本地文件扫描不能只靠粘贴文本，必须有文件/目录输入框

Priority: P0

Current behavior:
- 今日操作台只有一个文本粘贴框，placeholder 是“把你现在要处理的内容贴进来”。
- 这适合“这段内容放哪”和“提取 AI 上下文”，但不适合“整理本地文件 / 查看文件雷达”。
- 如果用户要扫描本地文件，不能把文件或目录自然放进去。

User impact:
- 用户会以为文件扫描没有真正接入本地文件系统。
- 用户不知道当前扫描的是哪个目录，也不知道能不能临时选择一个文件夹扫描。

Expected behavior:
- 文件类场景要有独立的文件/目录选择区。
- 支持至少三种输入方式：选择目录、拖放文件/文件夹、粘贴本地路径。
- 选择后展示扫描范围、文件数量预估、只读安全提示。

Acceptance checks:
- 「查看文件雷达」入口附近有明确的“选择文件/目录”或“拖放文件到这里”区域。
- 用户粘贴 `D:\some\path` 后，GUI 能识别为本地路径并作为扫描目标传给后端。
- 后端 action 返回本次扫描使用的根目录或文件清单。
- 未选择路径时，GUI 明确说明会使用配置文件里的默认扫描目录。

### UX-2026-05-07-03: 文本归档入口和文件扫描入口混在同一个操作台里

Priority: P1

Current behavior:
- 同一个 textarea 同时承担“粘贴内容归档”“问怎么用”“判断放哪”“复制上下文”“文件雷达扫描”的入口。
- 对用户来说，“内容”和“本地文件”是两种完全不同对象。

Expected behavior:
- 今日操作台拆成两个模式或两个区域：
- `内容处理`：粘贴文本、AI 对话、任务描述、知识片段。
- `本地文件`：选择目录、拖放文件、粘贴路径、查看扫描范围。

Acceptance checks:
- 用户能一眼看出：文本应该放哪里，文件/目录应该放哪里。
- 点击文件类按钮时，优先读取文件输入区；点击文本类按钮时，优先读取文本输入区。

### UX-2026-05-07-04: 结果缺少继续操作按钮，闭环不够

Priority: P1

Current behavior:
- 执行后只有右侧成功列表和 JSON。
- 用户不能从结果直接打开报告、打开生成的 Obsidian 笔记、复制上下文 prompt 或继续下一步。

Expected behavior:
- 每个 action 都应定义 `primary_result` 和 `next_actions`。
- GUI 根据结果渲染按钮，而不是要求用户读 JSON 字段。

Acceptance checks:
- 文件雷达完成后：显示「打开报告」「打开 Obsidian 记录」「复制路径」「继续归档建议」。
- AI 上下文完成后：显示「复制 Prompt」「查看来源」「归档这次对话」。
- 记录类完成后：显示「打开笔记」「继续补充」「复制笔记路径」。

## Product direction notes

- 当前 GUI 的视觉已经比早期版本更像产品，但交互模型仍偏“开发调试台”。
- 下一轮优化的重点不是继续做大屏视觉，而是把“输入对象 -> 执行动作 -> 人能理解的结果 -> 下一步按钮”做成闭环。
- 文件扫描必须承认它处理的是本地路径/文件夹，不应伪装成普通文本处理。
