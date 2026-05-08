# Migration And Backup

本项目的云端备份边界很明确：GitHub 备份项目本体，包括代码、文档、模板、测试、配置样例和恢复脚本；个人 Obsidian 内容不进公开仓库。

## 备份范围

- 会进入 GitHub：`knowledge_assistant.py`、`gui_server.py`、`docs/`、`tests/`、`scripts/`、`config.example.json`。
- 不进入 GitHub：`config.local.json`、`output/`、运行报告、个人 Obsidian vault、真实本地文件、私有 token。
- 推荐另行备份个人 vault：Obsidian Sync、网盘同步、私有 Git 仓库都可以，但不要混入公开仓库。

## 恢复命令

```powershell
git clone https://github.com/zhangzeyu99-web/file-management-assistant.git
cd file-management-assistant
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-assistant.ps1 -Demo
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1
```

打开 `http://127.0.0.1:8765/` 后，先用 demo mode 跑通整理、回顾、提取、提醒，再把 `config.local.json` 改成真实路径。

## 生成 Manifest

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\export-backup-manifest.ps1
```

manifest 会写到 `output/backup-manifest.json`，包含 `git rev-parse HEAD` 得到的 commit、`git remote get-url origin` 得到的远端、`restore_commands` 和忽略文件说明。

## 安全边界

迁移和备份脚本只创建配置、demo vault、索引和提醒记录。默认不删除、不移动、不重命名、不重写源文件。
