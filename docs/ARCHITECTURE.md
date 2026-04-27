# Architecture

The assistant is a small local-first toolchain.

## Components

| Component | Role |
| --- | --- |
| `config_loader.py` | Loads `config.json`, merges `config.local.json`, expands path variables. |
| `file_assistant.py` | Scans configured folders and renders file review reports. |
| `obsidian_manager.py` | Performs read-only Obsidian vault audit and renders reports. |
| `obsidian_assistant.py` | Provides guide, Q&A, inbox capture, and daily note helpers. |
| `gui_server.py` | Serves a local control panel and safe action API. |
| `send_report_to_feishu.js` | Optional local notification adapter for file reports. |
| `send_obsidian_report_to_feishu.js` | Optional local notification adapter for Obsidian audit reports. |
| `run-file-assistant.ps1` | Runs the main chain and optional delivery. |
| `run-obsidian-manager.ps1` | Runs the Obsidian audit only. |

## Data Flow

```text
config.json
  + config.local.json
        |
        v
file_assistant.py -----> JSON / Markdown / HTML reports
        |
        v
obsidian_manager.py ---> Obsidian audit report
        |
        v
optional notification hooks
```

The GUI uses the same underlying modules. It does not introduce separate behavior for scanning, auditing, or note writing.

## Safety Boundary

The code can create reports and write explicitly requested Obsidian helper notes. It does not perform destructive source-file operations.

Allowed write targets:

- Runtime report directory.
- Obsidian report directory.
- Obsidian inbox notes created by `capture`.
- Obsidian daily notes appended by `daily`.

Blocked by design:

- Delete.
- Move.
- Rename.
- Bulk rewrite of existing source notes.
- Unbounded full-disk scan.
