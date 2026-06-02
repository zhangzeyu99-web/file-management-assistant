# Human GUI Usability P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the real GUI walkthrough prove the three-operation product loop instead of producing false failures or testing broad, ungrounded queries.

**Architecture:** Keep the product surface as `添加资料 / 搜索回顾 / 生成 AI 上下文包`. The GUI harness should use evidence introduced by the same run, inspect the user-readable result card, and only require action buttons when a useful next action should exist.

**Tech Stack:** Python `unittest`, Playwright via `scripts/run-gui-human-usability.ps1`, static quality checks in `tests/test_project_quality.py`, Markdown iteration logs.

---

### Task 1: Lock the Harness Contract

**Files:**
- Modify: `tests/test_project_quality.py`
- Modify: `scripts/gui-human-usability.js`

- [x] **Step 1: Write the failing test**

Add assertions that the human walkthrough uses grounded evidence terms and no longer requires `.result-actions` for every result card.

Run:

```powershell
python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_gui_harness_verifies_local_target_workbench -v
```

Expected before the fix: `FAIL` on missing `Evidence-based review`.

- [x] **Step 2: Implement the minimal harness fix**

Change the script to:

- Search `Evidence-based review` after organizing a fixture.
- Request extraction with `Evidence-based review context packaging`.
- Require `.result-actions` only for organize, successful review, extract preview, and extract generate.
- Accept the current no-match wording when strict review correctly finds no evidence.

- [x] **Step 3: Verify the targeted contract**

Run:

```powershell
python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_gui_harness_verifies_local_target_workbench -v
```

Expected after the fix: `OK`.

### Task 2: Prove the Human Walkthrough

**Files:**
- Verify: `scripts/run-gui-human-usability.ps1`
- Output: `output/human-usability/<run-id>/`

- [x] **Step 1: Run strict usability walkthrough**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-human-usability.ps1 -StrictUx
```

Expected: `mechanics_failures=0`, `ux_issues=0`, video and screenshot saved.

- [x] **Step 2: Re-run after documentation is updated**

Run the same command after this plan and the iteration log are written, so final reporting uses fresh evidence.

### Task 3: Persist the Product Defect Review

**Files:**
- Modify: `docs/CURRENT_ITERATION_PLAN.md`
- Create: `docs/iteration-logs/2026-06-02-human-usability-p0-evidence-driven.md`
- Create: `D:\Obsidian-Work\02 项目\Codex\迭代记录\2026-06-02 真人式 GUI QA 证据闭环.md`

- [x] **Step 1: Update the current iteration plan**

Add the defect: the human GUI QA previously used broad English prompts and over-required action buttons, so it did not prove the real three-operation closed loop.

- [x] **Step 2: Add the iteration log**

Record:

- The initial failing human run.
- The RED static test.
- The script fix.
- The strict human run evidence.
- The nine self-review questions.

- [x] **Step 3: Add the Obsidian record**

Write the same decision in Obsidian so the next Codex session can recover the reasoning without relying on chat history.

### Task 4: Full Verification and Publish

**Files:**
- Verify: repository test and harness scripts
- Publish: Git commit and `origin/main`

- [x] **Step 1: Run full verification**

Run:

```powershell
python -X utf8 -m unittest discover -s tests -v
python -X utf8 project_quality.py
python -X utf8 scripts\audit-feature-contracts.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-human-usability.ps1 -StrictUx
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync
```

Expected: all commands exit `0`; GUI E2E and human walkthrough both report `mechanics_failures=0` and `ux_issues=0`.

- [ ] **Step 2: Commit and push**

Run:

```powershell
git add scripts\gui-human-usability.js tests\test_project_quality.py docs\CURRENT_ITERATION_PLAN.md docs\iteration-logs\2026-06-02-human-usability-p0-evidence-driven.md docs\superpowers\plans\2026-06-02-human-usability-p0.md
git commit -m "Make human GUI QA evidence-driven"
git push origin main
```

Expected: local `HEAD` and `origin/main` point to the same commit.
