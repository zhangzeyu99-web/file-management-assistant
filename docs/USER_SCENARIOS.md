# User Scenarios

This project is designed around scenario-first workflows. A user should not need to remember commands before getting value.

## Scenario 1: Daily Review

**User question:** "What should I look at first today?"

Use when starting or ending a workday. The assistant reads the latest file report and Obsidian audit, then turns raw metrics into a short action list.

Run:

```powershell
python .\scenario_playbook.py demo --config .\config.json
```

Expected output:

- A Markdown scenario report under the runtime `runs` directory.
- A JSON evidence file next to the Markdown report.
- A copied Obsidian note under the configured assistant run folder.

Acceptance checks:

- The report links to the latest file and Obsidian outputs when they exist.
- The next action is concrete enough to start immediately.
- No source file is deleted, moved, renamed, or rewritten.

## Scenario 2: Inbox Triage

**User question:** "Where should this note or task go?"

Use when the Obsidian inbox contains temporary ideas, Codex records, downloaded material, or unclear notes. The assistant keeps the workflow small:

- Inbox for temporary capture.
- Daily note for today-specific progress.
- Projects for multi-day work.
- Routine work for recurring automations and reviews.
- Archive for completed reference material.

Acceptance checks:

- Every recommendation has a target bucket.
- Source context stays traceable.
- Original notes are not overwritten.

## Scenario 3: Obsidian Health Check

**User question:** "Is my knowledge base getting messy?"

Use before weekly review, before importing into NotebookLM, or after several long automation sessions. The assistant summarizes the health signals that matter most:

- Empty or stub notes.
- Low-link notes.
- Broken links.
- Untriaged inbox notes.

Acceptance checks:

- Risks are ordered by impact.
- The fix list is small enough to start within 30 minutes.
- The assistant does not bulk-rewrite the vault.

## Scenario 4: Codex Handoff

**User question:** "Continue this task in Codex with the right context."

Use when the GUI or report identifies the next task but execution should continue in a Codex conversation. The generated handoff prompt includes:

- Obsidian vault path.
- Runtime report path.
- Repository path.
- Safety boundary.
- Acceptance checks.

Acceptance checks:

- The prompt contains real local paths.
- The prompt tells Codex to inspect files and reports before acting.
- The prompt includes the no-delete, no-move, no-rename safety boundary.

## GUI Entry

Start the GUI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1
```

Open:

```text
http://127.0.0.1:8765/
```

Use these buttons:

- `查看使用场景`: show the scenario catalog.
- `跑使用场景示例`: generate a local demo report and Obsidian note.

