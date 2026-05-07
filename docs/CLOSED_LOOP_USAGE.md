# Closed Loop Usage

Closed loop means every user-facing scenario has:

- User phrase.
- Actual action.
- Safety boundary.
- Output path or generated content.
- Next action.
- Acceptance checks.

## Loop 1: Today

1. User says: `今天先干什么`.
2. Assistant reads latest file radar and Obsidian health reports.
3. Assistant returns 1-3 priorities only.
4. Assistant separates 生活 / 学习 / 工作.
5. Assistant keeps archive candidates for weekly or monthly review.
6. Acceptance: no source files are deleted, moved, renamed, or rewritten.

## Loop 2: Capture

1. User says: `这段内容放哪`.
2. Assistant preserves source text.
3. Assistant suggests inbox, daily, project, routine, or archive.
4. Assistant writes a new note only when explicitly requested.
5. Acceptance: source and next step are visible.

## Loop 3: ACT Note

1. User says: `记录一个任务` or `这个以后会复用`.
2. Assistant chooses Action or Card.
3. Assistant writes source, next step, and acceptance criteria.
4. Acceptance: note is usable without rereading the whole conversation.

## Loop 4: Review

1. User says: `复盘今天`.
2. Assistant writes a lightweight Time note.
3. Weekly review handles inbox and archive backlog.
4. Monthly review considers structure changes.
5. Acceptance: daily review does not become a burden.

## Loop 5: Codex Handoff

1. User says: `交给 Codex 继续`.
2. Assistant generates an X-AI prompt with vault path, runtime path, reports, goal, safety boundary, and acceptance checks.
3. Codex must read real files before executing.
4. Acceptance: result is written back to local report or Obsidian note.
