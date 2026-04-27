# Getting Started

This guide gets the assistant running on a Windows machine with an optional Obsidian vault and optional notification delivery.

## 1. Prerequisites

Install or verify:

```powershell
python --version
node --version
git --version
```

Recommended versions:

- Python 3.11 or newer.
- Node.js 18 or newer.
- Windows PowerShell 5 or newer.

## 2. Clone

```powershell
git clone https://github.com/zhangzeyu99-web/file-management-assistant.git
cd file-management-assistant
```

## 3. Configure

Create a private local override:

```powershell
Copy-Item .\config.example.json .\config.local.json
notepad .\config.local.json
```

Edit at least:

- `runtime_root`: where reports and logs are written.
- `obsidian_vault`: your Obsidian vault path.
- `watch_roots`: folders to scan.
- `allowed_open_roots`: folders the GUI is allowed to open.

`config.local.json` is ignored by Git.

## 4. Test

```powershell
python .\tests\test_config_loader.py -v
python .\tests\test_file_assistant.py -v
python .\tests\test_obsidian_assistant.py -v
python .\tests\test_obsidian_manager.py -v
python .\tests\test_gui_server.py -v
```

## 5. Run A Dry Check

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-file-assistant.ps1 -Mode Test -SkipFeishu
```

The command writes local reports and skips external delivery.

## 6. Open The GUI

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1
```

Open:

```text
http://127.0.0.1:8765/
```

## 7. Optional Scheduled Task

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-scheduled-task.ps1
```

The default task runs daily at `20:30`.
