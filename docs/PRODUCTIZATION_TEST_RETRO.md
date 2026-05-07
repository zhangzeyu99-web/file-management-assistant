# Productization Test Retro

Date: 2026-05-07

This retro records what happened when the GUI was tested as a product, not only as a set of backend commands.

## Test runs

| Run | Scope | Result |
| --- | --- | --- |
| Isolated full E2E | Temporary fixture files, temporary vault, temporary GUI server | 13 actions clicked, 0 mechanics failures, 14 UX issues |
| Existing GUI smoke | Existing `127.0.0.1:8765`, read-only mode | 7 actions clicked, 0 mechanics failures, 7 UX issues |
| Strict UX gate | Temporary full E2E with UX failure treated as release blocker | Expected failure with UX exit code |
| Standard harness | Unit tests, quality checks, dry runs, scheduled task, remote sync | Passed after commit and push |

## What worked

- GUI buttons do call real `/api/action` endpoints.
- Core backend actions return successful HTTP responses.
- Isolated E2E can create temporary fixture files, temporary Obsidian notes, reports, and screenshots without touching the real vault.
- Path checks confirm generated report and note paths exist in isolated mode.
- Read-only smoke mode can test the live local GUI without intentionally writing new notes.

## What failed as a product experience

### 1. The main result is still a developer JSON box

Most actions finish successfully, but the user sees a black JSON/code panel. That makes a working backend feel broken because the visible result is not a product-level answer.

Required fix:

- Render a human-readable result card by default.
- Hide raw JSON behind "advanced details".
- Keep JSON for debugging only.

### 2. File scanning has no file or directory input

The GUI says it can organize local files, but the main workbench only has a text area. A user cannot naturally drop files, choose a folder, or paste a path into a dedicated file area.

Required fix:

- Add a file/folder workbench area.
- Support path paste, drag/drop, and a visible scan target summary.
- Make the default configured scan roots explicit when no custom path is chosen.

### 3. Action results do not close the loop

After file radar, health check, note creation, or context extraction, the user needs obvious next buttons. The current flow forces the user to inspect raw fields such as report path, note path, or prompt.

Required fix:

- File radar: show "open report", "open generated Obsidian note", "copy path", "view archive candidates".
- AI context: show "copy prompt", "view sources", "archive this chat".
- Note creation: show "open note", "copy note path", "continue editing".

### 4. Live smoke reveals too many raw local paths

The existing GUI smoke test showed that safe actions can still expose large amounts of raw local-path detail in the black output panel. That is useful for debugging but too noisy and too private as a default user-facing result.

Required fix:

- Summarize paths by category and count.
- Show only the top few relevant paths in normal mode.
- Put full path lists behind an explicit "advanced details" control.

### 5. Test tooling must also be productized

Parallel E2E runs initially collided because run directories and Playwright session names were timestamp-only. The fix was to add millisecond precision and a short GUID suffix.

Required fix:

- Keep unique run IDs for every E2E invocation.
- Treat test-harness reliability issues as product issues, because unreliable tests hide real UX problems.

## Release gates for the next GUI iteration

Before calling the GUI product-ready, these checks must pass:

- `scripts/run-gui-e2e.ps1` passes in isolated mode.
- `scripts/run-gui-e2e.ps1 -BaseUrl http://127.0.0.1:8765/ -ReadOnly` passes against the live local GUI.
- `scripts/run-gui-e2e.ps1 -StrictUx` passes, meaning no known UX blockers remain.
- No action defaults to a visible black JSON/code panel.
- File scanning has a visible file/folder/path input.
- File radar returns visible next-action buttons.
- Read-only smoke mode does not create real Obsidian notes.

## Next implementation order

1. Replace default JSON output with result cards and action-specific next buttons.
2. Add the file/folder/path input area.
3. Split the workbench into content mode and local-file mode.
4. Add E2E assertions for the new result cards and file input.
5. Re-run strict UX gate and update this retro with the before/after result.
