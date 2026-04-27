# Project Principles

This document turns the original product ideas into checks that can be verified by code, docs, and the release harness.

## Local-First

The assistant runs on the user's machine. It reads configured local folders and writes local reports before any optional integration is used.

## Report-Only Safety

The default behavior is report-only. The project does not delete, move, rename, or rewrite source files. Obsidian writes are limited to explicit helper actions such as inbox capture, daily note append, and report generation.

## Private Local Configuration

Public defaults live in `config.json` and `config.example.json`. Machine-specific paths and private settings belong in `config.local.json`, which is ignored by Git.

## Obsidian Workflow

The recommended Obsidian workflow is intentionally small:

```text
00 收件箱 -> 01 今日日志 -> 02 项目 / 04 例行工作 -> 99 归档
```

Obsidian should stay practical: capture first, organize later, and keep source paths traceable.

## Thin GUI

The GUI is a thin control layer over the same modules used by command-line runs:

- `file_assistant.py`
- `obsidian_manager.py`
- `obsidian_assistant.py`

It should not introduce separate hidden behavior.

## Validation Harness

The repository should stay maintainable through repeatable validation:

- Unit tests.
- `scripts/verify-harness.ps1`.
- Project quality checks in `project_quality.py`.
- Dry-run execution before release.

## Optional Integrations

Notification hooks are optional integrations, not the core product. The core product is local scanning, Obsidian workflow support, safe reporting, and repeatable validation.
