# 本地知识整理助手

给 Obsidian 新手和 AI 工作流用户用的本地知识整理助手：把你放进来的本地文件、Obsidian 笔记和 AI 对话整理成可归档、可回顾、可提取给 AI 续用的个人知识系统。

主界面只保留三个操作：

- **添加资料**：把文本、文件目录或 AI 对话写成新的 Obsidian 整理记录；粘贴真实路径时会生成索引清单和 manifest。
- **搜索回顾**：按关键词或问题做证据检索，返回本地摘要、匹配来源、相关原因和可打开路径。
- **生成 AI 上下文包**：先预览候选来源，确认后再生成可复制 prompt 和 Markdown。

它可以帮你沉淀知识卡、任务记录和 AI 上下文包。默认安全边界：不会删除、不会移动、不会重命名、不会重写你的源文件；只写新的 Obsidian 笔记和本地运行证据。

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

打开 `http://127.0.0.1:8765/`，先用 demo vault 跑通站点式首页，再把 `config.local.json` 改成你的真实 Obsidian 路径。

## GUI 主入口

GUI 现在是站点式知识库：首页首屏只说明用途和安全边界，三张卡片跳转到同页锚点区；下滑后可以浏览持续更新的知识流。

- `添加资料`：在 `#organize` 区输入文本、AI 对话或完整本地路径；路径只做索引清单，不复制、不移动源文件。
- `搜索回顾`：在 `#review` 区检索 Obsidian、助手报告、AI 归档和旧资料索引；无匹配时不编造答案。
- `生成 AI 上下文包`：在 `#extract` 区先预览候选来源，再确认生成 AI 上下文包，包含来源路径、摘要、安全边界和下一步请求。
- `知识流`：从已整理内容生成标题 + 描述卡片，点击只展开详情和来源，不触发写入。

低频能力进入 `/advanced` 工具维护页，例如文件雷达、知识库体检、旧资料索引和本地教程入口；首页不再堆诊断按钮。

## 界面产品化原则

首页按知识站点的信息架构收敛：深色首屏只讲清用途；三个操作作为导航入口；知识流用卡片沉淀标题、描述和来源；结果卡固定展示“做了什么 / 来源是什么 / 产物在哪 / 下一步”。详见 [Product UI Research](docs/PRODUCT_UI_RESEARCH.md) 和 [Product Retrospective And Next Plan](docs/PRODUCT_RETROSPECTIVE_AND_NEXT_PLAN.md)。

## 命令行入口

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-knowledge-assistant.ps1 -Action organize -Text "这段资料需要整理"
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-knowledge-assistant.ps1 -Action review -Query "Obsidian 教程"
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-knowledge-assistant.ps1 -Action extract -Request "继续优化知识库" -Mode preview
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-knowledge-assistant.ps1 -Action extract -Request "继续优化知识库" -Mode generate -SourcePath "C:\YourVault\path\source.md"
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-knowledge-assistant.ps1 -Action remind  # 兼容命令名：生成今日行动建议
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
