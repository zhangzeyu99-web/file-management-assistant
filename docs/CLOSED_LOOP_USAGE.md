# Closed Loop Usage

The assistant is mature only if the user can start from a real need, get an output, verify it, and continue without manual glue work.

## Closed Loop Definition

The minimum closed loop is:

```text
User scenario -> assistant action -> local report -> Obsidian note -> next action -> verification
```

The assistant should not stop at advice. It should create durable artifacts that can be reviewed later.

## What The Demo Does

Run:

```powershell
python .\scenario_playbook.py demo --config .\config.json
```

The command:

1. Reads the latest file management report if available.
2. Reads the latest Obsidian management report if available.
3. Builds four scenario cards: daily review, inbox triage, Obsidian health, and Codex handoff.
4. Writes `scenario-demo.md` and `scenario-demo.json` under the runtime `runs` folder.
5. Writes the same Markdown report into the configured Obsidian assistant folder.

## Safety Boundary

The scenario demo is report-only. It does not:

- Delete source files.
- Move source files.
- Rename source files.
- Rewrite existing source documents.
- Bulk-edit the Obsidian vault.

## Verification

Run unit tests:

```powershell
python .\tests\test_scenario_playbook.py -v
python .\tests\test_gui_server.py -v
python .\tests\test_project_quality.py -v
```

Run the release harness:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1
```

Expected evidence:

- `scenario_playbook.py` returns the four scenario IDs.
- `scenario-demo` writes both runtime and Obsidian reports.
- The GUI exposes scenario catalog and demo actions.
- `project_quality.py` verifies scenario-based workflow and closed loop principles.

## Operating Rule

Prefer scenario-first usage:

- If the user asks "what now", run the daily review scenario.
- If the user asks "where should this go", run inbox triage.
- If the user asks "is the knowledge base healthy", run Obsidian health check.
- If the user asks "continue in Codex", generate the Codex handoff prompt.

