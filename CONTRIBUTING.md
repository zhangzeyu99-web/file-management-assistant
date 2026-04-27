# Contributing

Contributions should preserve the safety model: report first, no destructive file operations by default.

## Local Checks

Run:

```powershell
python .\tests\test_config_loader.py -v
python .\tests\test_file_assistant.py -v
python .\tests\test_obsidian_assistant.py -v
python .\tests\test_obsidian_manager.py -v
python .\tests\test_gui_server.py -v
python .\tests\test_project_quality.py -v
```

Before release, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1
```

## Pull Request Expectations

- Explain user impact.
- Include tests for behavior changes.
- Keep secrets and local runtime reports out of the diff.
- Do not introduce delete, move, rename, or rewrite behavior without a dry-run manifest and explicit allow-list.
