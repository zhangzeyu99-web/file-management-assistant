# Obsidian Workflow Tutorial

This tutorial is for users who want Obsidian to become a practical work record system, not a decorative knowledge graph.

## Core Rule

Do not start with a complicated vault design. Start with a reliable flow:

```text
00 收件箱 -> 01 今日日志 -> 02 项目 / 04 例行工作 -> 99 归档
```

## Folder Roles

| Folder | Use it for |
| --- | --- |
| `00 收件箱` | Temporary notes, links, ideas, and items that are not classified yet. |
| `01 今日日志` | What happened today, what is next, and what is blocked. |
| `02 项目` | Work that lasts more than one day. |
| `03 会议` | Meeting notes and decisions. |
| `04 例行工作` | Repeated workflows, audits, automations, and review reports. |
| `90 模板` | Reusable note templates. |
| `99 归档` | Finished or inactive material kept for traceability. |

## Daily Use

Morning:

- Open today's daily note.
- Write the top tasks for the day.
- Keep it short enough to guide action.

During work:

- Capture loose material into the inbox.
- Let the assistant generate file and Obsidian review reports.
- Avoid reorganizing the vault while doing the real work.

Evening:

- Add completed work, next steps, and blockers.
- Promote reusable workflows into `04 例行工作`.
- Promote sustained topics into `02 项目`.

## Using The Assistant

Generate the guide:

```powershell
python .\obsidian_assistant.py guide
```

Ask where something belongs:

```powershell
python .\obsidian_assistant.py ask "这个内容应该放哪里？"
```

Capture an inbox note:

```powershell
python .\obsidian_assistant.py capture --title "一个想法" --body "先放收件箱，之后整理。" --tags idea
```

Append to today's daily note:

```powershell
python .\obsidian_assistant.py daily --done "完成文件助手检查" --next "整理收件箱" --blocker "暂无"
```

## What The Audit Checks

The Obsidian audit is read-only. It reports:

- Inbox items that need triage.
- Empty or very short notes.
- Notes with no links or backlinks.
- Duplicate titles.
- Broken internal links.
- Folder-style links.
- Codex project notes without index coverage.

The audit does not delete or move notes.
