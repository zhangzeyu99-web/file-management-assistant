# Configuration

The project uses a two-layer configuration model.

```text
config.json -> config.local.json
```

`config.json` is safe to commit. `config.local.json` is ignored by Git and should contain local paths, private vault locations, and machine-specific settings.

## Important Fields

| Field | Purpose |
| --- | --- |
| `runtime_root` | Report and log output directory. |
| `obsidian_vault` | Root path of the Obsidian vault. |
| `obsidian_run_dir` | Where assistant reports are written inside Obsidian. |
| `codex_executable` | Optional Codex Desktop executable path. |
| `allowed_open_roots` | GUI allow-list for opening local paths. |
| `obsidian_folders` | Folder names used by the Obsidian helper and audit. |
| `watch_roots` | Bounded folders scanned by the file assistant. |
| `exclude_dir_names` | Directory names skipped during scanning. |
| `recent_days` | Recent review threshold. |
| `archive_after_days` | Archive candidate age threshold. |
| `installer_after_days` | Installer cleanup age threshold. |
| `large_file_mb` | Large file reminder threshold. |
| `hash_duplicate_min_mb` | Minimum file size for duplicate hashing. |
| `hash_duplicate_limit` | Maximum files hashed per duplicate pass. |
| `review_keywords` | Keywords that promote a file into the review bucket. |

## Environment Variables In Paths

Path fields support Windows environment variables:

```json
{
  "runtime_root": "%USERPROFILE%\\file-assistant",
  "obsidian_vault": "%USERPROFILE%\\Documents\\Obsidian"
}
```

## Local Override Example

```json
{
  "runtime_root": "D:\\file-assistant",
  "obsidian_vault": "D:\\Obsidian-Work",
  "allowed_open_roots": [
    "D:\\file-assistant",
    "D:\\Obsidian-Work"
  ],
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

## Optional Notification Hooks

External notification delivery is optional. Provider-specific helpers and credentials should stay outside this repository. If you use the included sender adapters, set the helper path through an environment variable:

```powershell
$env:FEISHU_BOT_CARD_HELPER="C:\path\to\provider_helper.js"
```

Run without delivery:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-file-assistant.ps1 -Mode Test -SkipFeishu
```
