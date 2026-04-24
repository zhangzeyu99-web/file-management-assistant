# Maintenance Guide

## Update Cadence

Use this repository as the source of truth for the assistant code. Keep runtime reports outside the repository under `D:\codex\file-assistant`.

## Before Each Release

Run:

```powershell
python .\tests\test_file_assistant.py -v
python .\tests\test_obsidian_assistant.py -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-file-assistant.ps1 -Mode Test -SkipFeishu
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1
```

If Feishu delivery changed, also run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-file-assistant.ps1 -Mode Test
```

## Release Checklist

- Tests pass.
- Harness passes.
- No runtime reports are staged.
- No OpenClaw secrets, tokens, app secrets, or open IDs are committed.
- README reflects current setup.
- CHANGELOG has a short entry.
- Commit and push to `main`.

## Safety Rule

Do not add automatic file deletion or file moving without:

- an allow-list,
- a dry-run manifest,
- a rollback plan,
- and at least one successful scheduled dry run.
