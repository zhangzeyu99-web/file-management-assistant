# Architecture

本地知识整理助手采用薄 GUI + 统一 action 内核。

```text
输入
文本 / 本地路径 / AI 对话 / Obsidian 笔记 / 历史报告

内核
knowledge_assistant.py
organize / review / extract / remind

旧能力
file-radar / obsidian-health / legacy-index / archive-ai-chat

输出
Obsidian 新笔记 / 本地 runtime / AI 上下文包 / 今日提醒
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

- 主入口：整理资料、回顾知识、提取上下文、今日提醒。
- 本地文件 / 目录目标：支持粘贴路径、选择文件、拖放文件。
- 结果卡：展示做了什么、来源是什么、产物在哪、下一步能点什么。
- 高级/诊断：保留旧 action，但不作为新用户主线。

## Safety

The default behavior does not delete, move, rename, or rewrite source files. Write actions only create new Obsidian notes or runtime evidence.

## Backup Boundary

GitHub stores project code, docs, templates, tests, config samples, and scripts. Personal Obsidian vaults and `config.local.json` remain private.
