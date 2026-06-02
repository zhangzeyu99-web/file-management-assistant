# GUI E2E Testing

The GUI can be tested with Playwright through `scripts/run-gui-e2e.ps1`.

The default mode is isolated and safe:

- creates a temporary fixture file folder under `output/gui-e2e/`
- creates a temporary Obsidian vault under `output/gui-e2e/`
- starts a temporary GUI server on port `8767`
- clicks real GUI buttons through Playwright
- verifies `/api/action` requests and responses
- verifies the three public operation anchors: 添加资料、搜索回顾、生成 AI 上下文包
- checks returned local paths exist
- writes a JSON report, Markdown summary, hero screenshot, and final-state screenshot

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

### Chrome Channel

Use the system Chrome browser for a closer user-facing smoke test:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -Browser chrome -StrictUx
```

For the live GUI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -BaseUrl http://127.0.0.1:8765/ -Browser chrome -ReadOnly -StrictUx
```

## Current UX checks

The E2E audit now verifies these product-level behaviors:

- action results do not default to a black JSON/code box
- the first screen exposes only the three public operation cards
- feature cards jump to `#organize`, `#review`, and `#extract`
- the public status API does not expose the deprecated `knowledge_feed`
- the organize section exposes `#localPaths`, file picker, folder picker, and drag/drop zone
- the harness fills `e2eLocalPath`, clicks `检查本地目标`, and verifies `inspect-local-targets`
- after `添加资料`, the result must show `在 Obsidian 里怎么找` and `文件索引目录`
- the organize response must include structured `debug.obsidian_locations`
- after `添加资料`, the result must show `推荐搜索词`
- the organize response must include non-empty `debug.recommended_search_terms`
- clicking a recommended term must fill `搜索回顾` and execute review
- the strict report must set `three_operations.recommended_search_term_review=true`
- search results must render no more than four visible evidence cards by default
- the strict report must set `three_operations.review_source_cards_visible_max_four=true`
- after `搜索回顾`, the user can click `加入上下文包` from a source card
- the extract section must then show `已加入上下文包候选`
- the harness clicks `确认生成上下文包` from the selected review source before running the preview flow
- extract flow clicks `预览候选来源` first, then clicks `确认生成上下文包`
- after context package generation, the result must show `上下文包在 Obsidian 里怎么找` and `上下文包目录`
- the extract response must include structured `debug.extract_locations`
- in full isolated mode, local target inspection must use `custom-local-paths` when a local path is provided
- result cards expose readable answers, evidence, artifacts, and next-action buttons without default JSON

These are product UX failures, not backend mechanics failures. The script separates them so we can prove real operations work while still tracking what must be fixed before the GUI feels usable.

## Harness contract

- `scripts/run-gui-e2e.ps1` creates an isolated fixture folder and passes it to the browser as `e2eLocalPath`.
- `scripts/gui-e2e-playwright.js` writes that path into the local target input before clicking buttons.
- Read-only live smoke tests still click `检查本地目标`, but skip write-producing actions.
- Strict mode fails on missing feature anchors, missing local target inputs, `local-target-not-recognized`, raw JSON default output, missing Obsidian findability, missing context-package findability, missing review-to-context selection, missing preview-before-generate flow, or missing next-action buttons.

## Human Usability Recording

For a more realistic user flow, run the video harness:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-human-usability.ps1 -Headed -StrictUx
```

This mode uses a temporary fixture vault and records the interaction to `output/human-usability/<run>/human-usability.webm`. It simulates a desktop user who reads the hero, pastes a local path, runs organize/review/extract, copies the context prompt, and verifies that non-core diagnostics are no longer part of the main workflow.

For the live local GUI without writing test notes into the real vault:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-human-usability.ps1 -BaseUrl http://127.0.0.1:8765/ -ReadOnly -Headed -StrictUx
```

The human harness records `human-usability.webm`, `final-page.png`, `human-usability-result.json`, and `human-usability-summary.md`.
