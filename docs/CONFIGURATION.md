# Configuration

The project uses two configuration files:

- `config.json`: portable public defaults.
- `config.local.json`: private local overrides, ignored by Git.

The loader merges them in this order:

```text
config.json -> config.local.json
```

## Important Fields

| Field | Purpose |
| --- | --- |
| `runtime_root` | Local directory for generated reports. |
| `obsidian_vault` | Root path of your Obsidian vault. |
| `obsidian_run_dir` | Obsidian folder for generated assistant reports. Default role: `04 例行工作\知识行动助手`. |
| `watch_roots` | Bounded folders scanned by file radar. |
| `obsidian_folders` | Folder names used by Obsidian helpers. |
| `review_keywords` | Keywords that mark recent files for review. |

## Obsidian Folder Model

```text
00 收件箱
01 今日日志
02 项目
03 会议
04 例行工作
90 模板
99 归档
```

## Safety Defaults

- File radar only reports.
- Obsidian health check only audits.
- ACT helpers write new notes.
- The assistant does not delete, move, rename, or rewrite source files.

## Local Override Example

```json
{
  "obsidian_vault": "%USERPROFILE%\\Documents\\Obsidian",
  "runtime_root": "%USERPROFILE%\\file-assistant",
  "watch_roots": [
    {
      "name": "Downloads",
      "path": "%USERPROFILE%\\Downloads",
      "max_depth": 2,
      "max_files": 3500
    }
  ]
}
```
