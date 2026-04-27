# Obsidian File Management Assistant

Local-first Windows assistant for file archiving, Obsidian vault review, daily work capture, and Codex/OpenClaw handoff.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![PowerShell](https://img.shields.io/badge/PowerShell-5%2B-5391FE)
![License](https://img.shields.io/badge/License-MIT-green)
![Safety](https://img.shields.io/badge/Safety-report--only-orange)

**Keywords:** Obsidian assistant, personal knowledge management, file management automation, Windows productivity, local-first AI workflow, Codex assistant, OpenClaw, Feishu/Lark notification, PKM, knowledge base audit.

## Why This Project Exists

This project turns scattered desktop files, downloads, Codex outputs, and Obsidian notes into a safe daily review workflow. It scans only configured folders, creates readable reports, writes selected Obsidian notes, and optionally sends Feishu/Lark cards through an existing OpenClaw bot setup.

It is intentionally conservative: by default it does **not** delete, move, rename, or rewrite source files.

## 中文简介

这是一个本地优先的文件与 Obsidian 管理助手。它适合用来做每日文件复盘、收件箱整理、Obsidian 内部结构审计、工作日志记录，以及把任务复制回 Codex 会话继续处理。默认只生成报告和写入明确指定的笔记，不会自动删除、移动或改名源文件。

## Features

- Bounded file scanning for Desktop, Downloads, Documents, Obsidian, and custom folders.
- Archive candidates, recent review items, installer cleanup reminders, large-file reminders, and duplicate groups.
- JSON, Markdown, and HTML reports under a configurable runtime directory.
- Read-only Obsidian vault audit: inbox triage, stub notes, low-link notes, duplicate titles, broken links, folder-style links, and Codex index coverage.
- Local GUI control panel at `http://127.0.0.1:8765/`.
- Obsidian helper commands for beginner guides, Q&A, inbox capture, and daily notes.
- Optional Feishu/Lark card delivery through a local OpenClaw helper.
- Windows Scheduled Task installer for daily review automation.
- Unit tests and a release verification harness.

## Screenshots

The GUI is generated locally and does not require a hosted backend. Start it with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1
```

Then open:

```text
http://127.0.0.1:8765/
```

## Quick Start

1. Install prerequisites:

```powershell
python --version
node --version
powershell -NoProfile -Command "$PSVersionTable.PSVersion"
```

2. Clone the repository:

```powershell
git clone https://github.com/zhangzeyu99-web/file-management-assistant.git
cd file-management-assistant
```

3. Create your local configuration:

```powershell
Copy-Item .\config.example.json .\config.local.json
notepad .\config.local.json
```

4. Run tests:

```powershell
python .\tests\test_config_loader.py -v
python .\tests\test_file_assistant.py -v
python .\tests\test_obsidian_assistant.py -v
python .\tests\test_obsidian_manager.py -v
python .\tests\test_gui_server.py -v
```

5. Run the assistant without Feishu/Lark delivery:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-file-assistant.ps1 -Mode Test -SkipFeishu
```

6. Start the GUI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1
```

## Repository Layout

```text
.
|-- config.json
|-- config.example.json
|-- config_loader.py
|-- file_assistant.py
|-- obsidian_assistant.py
|-- obsidian_manager.py
|-- gui_server.py
|-- run-file-assistant.ps1
|-- run-obsidian-manager.ps1
|-- run-obsidian-assistant.ps1
|-- start-assistant-gui.ps1
|-- send_report_to_feishu.js
|-- send_obsidian_report_to_feishu.js
|-- docs/
|-- scripts/
|   |-- install-scheduled-task.ps1
|   `-- verify-harness.ps1
`-- tests/
```

## Configuration Model

`config.json` is the public safe default. `config.local.json` is ignored by Git and should contain your private local paths.

The loader merges them in this order:

```text
config.json -> config.local.json
```

Supported path values can use Windows environment variables such as `%USERPROFILE%` and `%LOCALAPPDATA%`.

Read the full configuration guide:

[docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## Obsidian Tutorial

If you are new to Obsidian, start here:

[docs/OBSIDIAN_WORKFLOW_TUTORIAL.md](docs/OBSIDIAN_WORKFLOW_TUTORIAL.md)

The shortest workflow is:

```text
00 收件箱 -> 01 今日日志 -> 02 项目 / 04 例行工作 -> 99 归档
```

## GUI Capabilities

The local GUI can:

- Run the full file and Obsidian check.
- Run only the file scanner.
- Run only the Obsidian audit.
- Open the latest HTML report.
- Open the Obsidian vault.
- Ask the Obsidian helper.
- Capture text into the Obsidian inbox.
- Append work notes to today's daily note.
- Generate a Codex handoff prompt for the current conversation.
- Open Codex Desktop if the executable path is configured.

## Feishu / Lark Delivery

Feishu/Lark delivery is optional. The repository does not store app secrets, tokens, webhooks, or open IDs.

By default the sender looks for:

```text
%USERPROFILE%\.openclaw\scripts\lib\feishu_bot_card.js
%USERPROFILE%\.openclaw\openclaw.json
```

You can override the helper path with:

```powershell
$env:FEISHU_BOT_CARD_HELPER="C:\path\to\feishu_bot_card.js"
```

## Safety Policy

This project is designed as a review, reminder, and capture assistant.

It does not:

- Delete files.
- Move files.
- Rename files.
- Rewrite source documents.
- Scan secret/session folders by default.
- Commit credentials.

Any future destructive action should require an allow-list, a dry-run manifest, and a rollback plan.

## Scheduled Task

Install the default daily Windows Scheduled Task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-scheduled-task.ps1
```

Default schedule: daily at `20:30`.

## Validation

Run the release harness:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1
```

The harness checks Git state, unit tests, secret-like patterns, dry-run execution, and remote sync state.

## Documentation

- [Getting Started](docs/GETTING_STARTED.md)
- [Configuration](docs/CONFIGURATION.md)
- [Obsidian Workflow Tutorial](docs/OBSIDIAN_WORKFLOW_TUTORIAL.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Maintenance](MAINTENANCE.md)
- [Security](SECURITY.md)

## License

MIT. See [LICENSE](LICENSE).
