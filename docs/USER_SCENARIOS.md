# User Scenarios

The assistant should start from user language, not internal commands.

| GUI entry | User phrase | What it does | Default safety |
| --- | --- | --- | --- |
| 今天先干什么 | 今天先干什么 | Reads latest reports and returns only 1-3 daily priorities. | Does not process every archive candidate. |
| 查看文件雷达 | 看看哪些文件要管 | Lists recent files, archive candidates, large files, duplicates. | Report only; no delete, move, rename, or rewrite. |
| 这段内容放哪 | 这段内容放哪 | Routes by 生活 / 学习 / 工作, then inbox/daily/project/routine/archive. | Keeps source text and path. |
| 记录一个任务 | 记录一个任务 | Writes an Action note with goal, background, process, result, next step, acceptance checks. | Writes a new note only. |
| 沉淀一张知识卡 | 这个以后会复用 | Writes a Card note with source, use case, conclusion, links, next step. | Does not force complex backlinks. |
| 复盘今天 | 复盘今天 | Writes a lightweight Time review. | Daily review stays lightweight; backlog is weekly/monthly. |
| 检查知识库 | 知识库乱不乱 | Audits inbox, stubs, low-link notes, broken links, duplicate titles, Codex index gaps. | Does not bulk rewrite the vault. |
| 生成 Codex 交接 | 交给 Codex 继续 | Generates a prompt with paths, boundaries, goals, and acceptance criteria. | Requires reading real files before execution. |
| 问答助手 | 我该怎么用 | Answers Obsidian usage questions from local structure and rules. | Does not invent current state. |

## Today Scenario

今日轻量规则:

- Choose 1-3 daily priorities.
- Start with today-related files and notes.
- Do not process every archive candidate every day.
- Split first by 生活 / 学习 / 工作.
- If unsure, write to `00 收件箱` and preserve source.

## ACT Outputs

- Action: task note.
- Card: reusable knowledge note.
- Time: daily, weekly, or monthly review.
- X-AI: Codex/OpenClaw handoff and memory note.

## Scenario Demo

Run:

```powershell
python .\scenario_playbook.py demo --config .\config.json
```

Expected outputs:

- Runtime JSON report.
- Runtime Markdown report.
- Obsidian scenario report.
- `acceptance_checks` for every scenario.
