# File Management Assistant

Low-risk Windows file management assistant for Codex/OpenClaw workflows.

It scans selected folders, classifies files into review/archive/reminder buckets, writes JSON/Markdown/HTML reports, updates an Obsidian note, and can send a Feishu interactive card through an existing OpenClaw Feishu bot configuration.

## What It Does

- Scans bounded watch roots instead of crawling the whole disk.
- Produces archive candidates, recent review items, installer cleanup reminders, large-file reminders, screenshot reminders, and exact duplicate groups.
- Writes reports to `D:\codex\file-assistant\runs\<date>\<time>`.
- Writes an Obsidian daily review note.
- Sends a Feishu card through `C:\Users\Administrator\.openclaw\openclaw.json` and `bot-xiaoxia`.
- Never deletes, moves, renames, or modifies source files.

## Repository Layout

```text
.
├── config.json
├── file_assistant.py
├── obsidian_assistant.py
├── run-file-assistant.ps1
├── run-obsidian-assistant.ps1
├── send_report_to_feishu.js
├── scripts/
│   └── install-scheduled-task.ps1
└── tests/
    └── test_file_assistant.py
```

## Requirements

- Windows PowerShell 5+.
- Python 3.11+.
- Node.js 18+.
- Optional: OpenClaw Feishu bot config at `C:\Users\Administrator\.openclaw\openclaw.json`.
- Optional: Obsidian vault path configured in `config.json`.

The scanner itself uses only Python standard library modules.

## Quick Start

Run tests:

```powershell
python .\tests\test_file_assistant.py -v
```

Run scanner and report generation without Feishu:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-file-assistant.ps1 -Mode Test -SkipFeishu
```

Run the full release harness:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1
```

## Obsidian Helper

Generate the beginner guide:

```powershell
python .\obsidian_assistant.py guide
```

Ask a common Obsidian workflow question:

```powershell
python .\obsidian_assistant.py ask "我今天怎么记录工作？"
```

Capture a note into the Obsidian inbox:

```powershell
python .\obsidian_assistant.py capture --title "一个想法" --body "先放收件箱，之后整理。" --tags idea
```

Append to today's daily note:

```powershell
python .\obsidian_assistant.py daily --done "完成文件管理助手" --next "整理收件箱" --blocker "暂无"
```

Run full chain with Feishu:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-file-assistant.ps1 -Mode Test
```

Install daily scheduled task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-scheduled-task.ps1
```

Default schedule: daily at `20:30`.

## Configuration

Edit `config.json` to control:

- Runtime output root.
- Obsidian vault and run-note path.
- Watch roots.
- Max depth and max file count per root.
- Classification thresholds.
- Duplicate hashing limits.

The default config is intentionally conservative. It scans common landing zones only:

- Desktop
- Downloads
- Documents
- Codex output documents
- Obsidian inbox
- Obsidian projects

## Safety Policy

This project is designed as a review and reminder assistant first.

It does not:

- Delete files.
- Move files.
- Rename files.
- Rewrite source documents.
- Scan OpenClaw/Codex secret or session folders by default.

Physical file moving should only be added later behind explicit allow-list rules and a dry-run manifest.

## Feishu Delivery

`send_report_to_feishu.js` reuses the existing OpenClaw Feishu helper:

```text
C:\Users\Administrator\.openclaw\scripts\lib\feishu_bot_card.js
```

No app secret, token, webhook, or open ID is stored in this repository. Runtime credentials remain in the local OpenClaw config.

## Maintenance

Recommended update loop:

1. Change code or config.
2. Run `python .\tests\test_file_assistant.py -v`.
3. Run `python .\tests\test_obsidian_assistant.py -v`.
4. Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\run-file-assistant.ps1 -Mode Test -SkipFeishu`.
5. Commit with a short behavior-focused message.
6. Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1`.
7. Push to GitHub.
8. Run full Feishu test when delivery behavior changed.

## License

MIT. See [LICENSE](LICENSE).
