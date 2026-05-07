# Architecture

The project is now an Obsidian + AI Knowledge Action Assistant. File scanning remains one capability, but the main architecture is scenario-first and ACT-driven.

## Four-Layer Architecture

```text
输入层：本地文件 / Obsidian 笔记 / Codex 会话 / OpenClaw 记录 / 手动输入
判断层：生活 / 学习 / 工作 + Action / Card / Time / X-AI
执行层：文件雷达 / Obsidian 体检 / 收件箱归位 / 任务记录 / 知识卡沉淀 / 时间复盘 / Codex 交接
输出层：本地报告 / Obsidian 笔记 / GUI 操作入口 / Codex prompt / 可选通知
```

## Components

| Component | Role |
| --- | --- |
| `config_loader.py` | Loads `config.json`, merges `config.local.json`, expands path variables. |
| `file_assistant.py` | File radar: scans configured folders and renders JSON / Markdown / HTML reports. |
| `obsidian_manager.py` | Read-only Obsidian vault health check. |
| `obsidian_assistant.py` | Guide, Q&A, inbox capture, daily notes, and ACT note helpers. |
| `scenario_playbook.py` | Main orchestration layer for scenario-first workflows and ACT templates. |
| `gui_server.py` | Thin GUI over the same modules and action API. |
| `run-file-assistant.ps1` | Runs file radar and optional follow-up delivery. |
| `run-obsidian-manager.ps1` | Runs Obsidian health check only. |
| `scripts/verify-harness.ps1` | Validation harness for tests, quality gates, dry-runs, and Git state. |

## Data Flow

```text
config.json + config.local.json
        |
        v
输入层数据
        |
        v
scenario_playbook.py
        |
        +--> file_assistant.py -------> report.md / report.html / summary.json
        +--> obsidian_manager.py -----> Obsidian health report
        +--> obsidian_assistant.py ---> Action / Card / Time / X-AI notes
        +--> gui_server.py -----------> scenario buttons and Codex prompt
```

## Safety Boundary

The code can create reports and write explicitly requested Obsidian helper notes. It does not delete, move, rename, or rewrite source files.

Allowed write targets:

- Runtime report directory.
- Obsidian report directory.
- New inbox notes created by `capture`.
- Daily notes appended by `daily`.
- New Action / Card / Time notes created by ACT helpers.

Blocked by design:

- Delete.
- Move.
- Rename.
- Bulk rewrite of existing source notes.
- Unbounded full-disk scan.
