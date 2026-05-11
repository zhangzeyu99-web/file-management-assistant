# Architecture

本地知识整理助手采用薄 GUI + 统一 action 内核。

```text
输入
文本 / 本地路径 / AI 对话 / Obsidian 笔记 / 历史报告

内核
knowledge_assistant.py
organize / review / extract

旧能力
remind / file-radar / obsidian-health / legacy-index / archive-ai-chat

输出
Obsidian 新笔记 / 本地 runtime / AI 上下文包
```

## Core Action Layer

所有推荐入口都返回统一结构：

```json
{
  "ok": true,
  "action": "organize",
  "summary": "做了什么",
  "sources": [],
  "artifacts": [],
  "next_actions": [],
  "safety": "不删除、不移动、不重命名、不重写源文件",
  "debug": {}
}
```

## GUI Layer

`docs/assets/gui/workspace.html` 只负责展示和调用 API：

- 首屏：站点式 hero，说明用途、安全边界和三个锚点入口。
- 知识流：从 `/api/status.knowledge_feed` 渲染标题 + 描述卡片，点击只展开详情和来源。
- 主入口：添加资料、搜索回顾、生成 AI 上下文包，分别位于 `#organize`、`#review`、`#extract`；提取区先预览候选来源，确认后才写入上下文包。
- 本地文件 / 目录目标：保留在整理区，支持粘贴路径、选择文件、拖放文件。
- 结果卡：展示状态、做了什么、来源是什么、产物在哪、下一步能点什么；状态区分未完成、找到候选、已生成。
- 工具维护页：`/advanced` 承载低频诊断和资料入口，例如 `file-radar`、`obsidian-health`、`legacy-index`、`open-guidebook`，不打断首页三主线。

## Safety

The default behavior does not delete, move, rename, or rewrite source files. Write actions only create new Obsidian notes or runtime evidence.

## Backup Boundary

GitHub stores project code, docs, templates, tests, config samples, and scripts. Personal Obsidian vaults and `config.local.json` remain private.
