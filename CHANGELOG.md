# Changelog

## 2026-04-27

- Prepared the project for open-source GitHub publication with SEO-focused README, documentation, security notes, contribution guide, and configurable local overrides.
- Added project quality gates that verify the past product principles: local-first behavior, report-only safety, private config, Obsidian workflow, thin GUI, validation harness, and optional integration positioning.
- Added `config_loader.py` and public/private configuration split with `config.local.json`.
- Added a local GUI control panel at `http://127.0.0.1:8765/`.
- Added safe GUI actions for file scanning, Obsidian auditing, capture, daily notes, ask, guide, opening reports, and Codex handoff prompts.
- Added GUI regression tests.

## 2026-04-24

- Initial standalone release.
- Added bounded scanner and classifiers.
- Added JSON, Markdown, and HTML report generation.
- Added Obsidian run-note output.
- Added optional notification adapter delivery.
- Added Windows scheduled task installer.
- Added unit tests and maintenance checklist.
- Added release verification harness.
- Added Obsidian beginner guide, inbox capture, daily-note, and Q&A helper.
- Added Obsidian behavior-profile links and habit-aware Q&A routing.
- Added read-only Obsidian internal management audit and optional notification delivery.
- Integrated the Obsidian audit into the main scheduled assistant chain.
