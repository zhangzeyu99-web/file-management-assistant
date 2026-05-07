# Project Principles

This project is a local-first Obsidian AI organizing workspace, not a cloud file cleaner. It turns local files, Obsidian notes, AI conversations, and manual input into records that are actionable, reviewable, traceable, and reusable as future AI context.

## Core Positioning

- knowledge action assistant: the product helps users turn messy inputs into Obsidian actions, cards, reviews, archives, and context prompts.
- local-first: user files, reports, and Obsidian notes stay on the local machine by default.
- private local configuration: machine-specific paths and secrets belong in `config.local.json`, which is ignored by git.
- optional integrations: notification hooks are optional delivery channels, not the core open-source promise.
- AI 对话归档: existing AI conversations become traceable archive notes.
- AI 上下文取用: already-organized knowledge becomes copyable context for new AI conversations.

## Four-Layer Architecture

The four-layer architecture is the public mental model:

```text
输入层：本地文件 / Obsidian 笔记 / AI 对话记录 / 手动输入
判断层：生活 / 学习 / 工作 + Action / Card / Time / X-AI
执行层：文件雷达 / Obsidian 体检 / 收件箱归位 / 任务记录 / 知识卡沉淀 / 时间复盘 / AI 对话归档 / AI 上下文取用
输出层：本地报告 / Obsidian 笔记 / GUI 操作入口 / AI 上下文 prompt / 可选通知
```

## Workflow Rules

- ACT workflow: Action / Card / Time / X-AI is the default output model.
- Obsidian workflow: `00 收件箱`, `01 今日日志`, projects, routine work, templates, and archive stay simple and readable.
- life / study / work: every routing decision starts with 生活 / 学习 / 工作 before choosing a folder or template.
- lightweight daily triage: 今日轻量规则 means 1-3 daily priorities only; 不要每天处理全部归档候选.
- scenario-based workflow: GUI and docs start from user phrases such as “今天先干什么” and “这段内容放哪”.
- closed loop: every scenario has outputs, acceptance checks, and a next action.
- archive versus retrieval: archiving saves what happened; retrieval extracts useful context for what happens next.

## Safety Rules

- report-only safety: scans and audits are read-only by default.
- The assistant does not delete, move, rename, or rewrite source files unless a future explicit execution mode adds a whitelist and confirmation boundary.
- Existing source notes and files keep their original context; new records preserve source paths.

## Implementation Rules

- thin gui: the GUI is a thin entry layer over the same underlying modules, not a separate product fork.
- validation harness: `scripts/verify-harness.ps1` and the Python test suite are the release gate.
- closed loop evidence matters more than optimistic claims: reports, written notes, and tests are the proof.
