# GUI E2E Testing

The GUI can be tested with Playwright through `scripts/run-gui-e2e.ps1`.

The default mode is isolated and safe:

- creates a temporary fixture file folder under `output/gui-e2e/`
- creates a temporary Obsidian vault under `output/gui-e2e/`
- starts a temporary GUI server on port `8767`
- clicks real GUI buttons through Playwright
- verifies `/api/action` requests and responses
- checks returned local paths exist
- writes a JSON report, Markdown summary, and screenshot

Every run uses a unique millisecond timestamp plus a short GUID suffix. This prevents Playwright session collisions when several E2E runs start close together.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1
```

Run visibly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -Headed
```

Include buttons that open external programs or OS paths:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -IncludeOpeners
```

Attach to an existing local GUI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -BaseUrl http://127.0.0.1:8765/
```

Read-only smoke test for an existing local GUI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -BaseUrl http://127.0.0.1:8765/ -ReadOnly
```

Strict UX mode fails when known UX issues still exist:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
```

## Current UX checks

The E2E audit currently flags these issues:

- action results default to a black JSON/code box
- file scanning has no file picker, directory picker, drag-drop area, or explicit local path input
- file radar results do not expose clear next-action buttons in the main workbench

These are product UX failures, not backend mechanics failures. The script separates them so we can prove real operations work while still tracking what must be fixed before the GUI feels usable.
