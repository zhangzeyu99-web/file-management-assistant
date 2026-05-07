# Closed Loop Usage

Closed loop means every user-facing scenario has a user phrase, actual action, safety boundary, output path or generated content, next action, and acceptance checks.

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

## Loop 5: AI Conversation Archive

1. User says: `归档这段 AI 对话`.
2. Assistant writes a new archive note with source, task background, key conclusions, output paths, and open items.
3. The note records what already happened; it does not pretend to prepare a new AI conversation.
4. Acceptance: the archive note is traceable and does not rewrite the original conversation or source files.

## Loop 6: AI Context Retrieval

1. User says: `给 AI 补上下文`.
2. Assistant scans already-organized Obsidian notes, knowledge cards, project records, and reports.
3. Assistant returns source paths, why they match, compressed context, a next request, and a copyable prompt.
4. Acceptance: the new prompt can be pasted into an AI conversation and cites local source paths.
