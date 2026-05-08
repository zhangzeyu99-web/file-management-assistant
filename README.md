# 本地知识整理助手

给 Obsidian 新手和 AI 工作流用户用的本地知识整理助手：把你放进来的本地文件、Obsidian 笔记和 AI 对话整理成可归档、可回顾、可提取给 AI 续用、可定时提醒的个人知识系统。

核心只做四件事：

- **整理**：把文本、文件目录或 AI 对话写成新的 Obsidian 整理记录，保留来源和生活 / 学习 / 工作判断。
- **回顾**：按关键词或问题检索已整理内容，返回本地摘要、匹配来源和可打开路径。
- **提取**：根据当前任务生成 `AI 上下文包`，输出可复制 prompt 和 Markdown。
- **提醒**：每天 9 点生成 1-3 个今日重点，不做定时整理。

它可以帮你沉淀知识卡、任务记录、今日提醒和 AI 上下文包。默认安全边界：不会删除、不会移动、不会重命名、不会重写你的源文件；只写新的 Obsidian 笔记和本地运行证据。

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![PowerShell](https://img.shields.io/badge/PowerShell-5%2B-5391FE)
![License](https://img.shields.io/badge/License-MIT-green)
![Safety](https://img.shields.io/badge/Safety-safe--by--default-orange)

## 5 分钟上手

```powershell
git clone https://github.com/zhangzeyu99-web/file-management-assistant.git
cd file-management-assistant
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-assistant.ps1 -Demo
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1
```

打开 `http://127.0.0.1:8765/`，先用 demo vault 跑通四个入口，再把 `config.local.json` 改成你的真实 Obsidian 路径。

## GUI 主入口

- `整理资料`：文本 / 文件目录 / AI 对话三类输入，写入新的 Obsidian 整理记录。
- `回顾知识`：检索 Obsidian、助手报告、AI 归档和旧资料索引。
- `提取上下文`：生成 AI 上下文包，包含来源路径、摘要、安全边界和下一步请求。
- `今日提醒`：只给今天 1-3 个重点，避免每天被归档候选淹没。

旧能力如文件雷达、知识库体检、记录任务进入 `高级/诊断`，保留兼容但不再作为主线。

## 命令行入口

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-knowledge-assistant.ps1 -Action organize -Text "这段资料需要整理"
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-knowledge-assistant.ps1 -Action review -Query "Obsidian 教程"
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-knowledge-assistant.ps1 -Action extract -Request "继续优化知识库"
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-knowledge-assistant.ps1 -Action remind
```

## 迁移与备份

GitHub 只备份项目本体：代码、文档、模板、测试、配置样例和脚本。个人 Obsidian vault、`config.local.json`、运行报告和真实文件不进入公开仓库。详见 [Migration And Backup](docs/MIGRATION_BACKUP.md)。

## 验证

```powershell
python -m unittest discover -s tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync
```

## License

MIT. See [LICENSE](LICENSE).
