# Architecture

The project is an Obsidian AI organizing workspace. File scanning is one capability, but the main workflow is scenario-first: local files, Obsidian notes, and AI conversations become archive records, reusable knowledge, daily actions, and AI-usable context.

## Four-Layer Architecture

```text
输入层：本地文件 / Obsidian 笔记 / AI 对话记录 / 手动输入
判断层：生活 / 学习 / 工作 + Action / Card / Time / X-AI
执行层：文件雷达 / Obsidian 体检 / 收件箱归位 / 任务记录 / 知识卡沉淀 / 时间复盘 / AI 对话归档 / AI 上下文取用
输出层：本地报告 / Obsidian 笔记 / GUI 操作入口 / AI 上下文 prompt / 可选通知
```

## Components

| Component | Role |
| --- | --- |
| `config_loader.py` | Loads `config.json`, merges `config.local.json`, expands path variables. |
| `file_assistant.py` | File radar: scans configured folders and renders JSON / Markdown / HTML reports. |
| `obsidian_manager.py` | Read-only Obsidian vault health check. |
| `obsidian_assistant.py` | Guide, Q&A, inbox capture, daily notes, and ACT note helpers. |
| `assistant_evolution.py` | Guidebook catalog, self-evolution report, AI conversation archive, and AI context retrieval. |
| `scenario_playbook.py` | Scenario-first workflow catalog and ACT templates. |
| `gui_server.py` | Thin GUI over the same modules and action API. |

## Data Flow

```text
config.json + config.local.json
        |
        v
本地文件 / Obsidian / AI 对话输入
        |
        v
scenario_playbook.py + assistant_evolution.py
        |
        +--> file_assistant.py -------> report.md / report.html / summary.json
        +--> obsidian_manager.py -----> Obsidian health report
        +--> obsidian_assistant.py ---> Action / Card / Time notes
        +--> assistant_evolution.py --> AI 对话归档 / AI 上下文 prompt
        +--> gui_server.py -----------> scenario buttons and natural-language actions
```

## Safety Boundary

The code can create reports and write explicitly requested Obsidian helper notes. It does not delete, move, rename, or rewrite source files.

Allowed write targets:

- Runtime report directory.
- Obsidian report directory.
- New inbox notes created by `capture`.
- Daily notes appended by `daily`.
- New Action / Card / Time notes created by ACT helpers.
- New AI conversation archive notes created by `archive-ai-chat`.

Blocked by design:

- Delete.
- Move.
- Rename.
- Bulk rewrite of existing source notes.
- Unbounded full-disk scan.
