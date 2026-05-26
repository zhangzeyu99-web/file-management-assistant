# 架构说明

产品主线收敛为三个动作：`organize`、`review`、`extract`。

## 数据流

- `organize`：读取文本或真实本地路径，写 Obsidian 整理记录、索引清单和每文件索引。
- `review`：从 Obsidian、文件索引、Codex 会话索引、历史报告中检索证据，返回答案、命中词、证据摘录和来源路径。
- `extract`：复用 `review` 的候选证据，预览后生成 AI 上下文包 Markdown 和 prompt。

## GUI

GUI 只负责输入、展示和调用 action。首页不再展示知识流、提醒、诊断或旧功能入口。

## 安全边界

默认不删除、不移动、不重命名、不重写源文件；只写新的 Obsidian 笔记和运行证据。
