# Getting Started

本地知识整理助手的第一目标是让新机器 clone 后能跑通，再接入你的真实 Obsidian vault。

## 1. 检查环境

```powershell
python --version
powershell -NoProfile -Command "$PSVersionTable.PSVersion"
```

推荐 Python 3.11+ 和 PowerShell 5+。

## 2. 先跑 Demo Mode

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-assistant.ps1 -Demo
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1
```

打开 `http://127.0.0.1:8765/`。demo 会创建本地 demo vault 和 demo 文件；新机器上会生成 `config.local.json`，如果你已经有真实 `config.local.json`，脚本会改写到 `config.demo.json`，避免覆盖私有配置。

## 3. 三个主入口

- `添加资料`：放入文本、完整本地路径或 AI 对话，写入新的 Obsidian 整理记录；路径只生成索引清单。
- `搜索回顾`：输入关键词或问题，返回本地摘要、匹配来源和相关原因。
- `生成 AI 上下文包`：输入当前任务，先预览候选来源，确认后生成 AI 上下文包。

输入不足时助手不会硬写占位记录：没有资料就不生成整理笔记；没有匹配来源就不生成假上下文包；没有结论或可读取来源就不生成知识卡。

## 4. 接入真实 Obsidian

编辑 `config.local.json`：

```json
{
  "obsidian_vault": "D:\\YourVault",
  "knowledge_root": "D:\\YourVault\\04 例行工作\\知识整理助手",
  "runtime_root": "D:\\YourRuntime"
}
```

`config.local.json` 不进 Git。真实本地路径、个人 vault 和运行报告都只保留在你的机器上。

## 5. 安装每天 9 点行动建议

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-scheduled-task.ps1
```

计划任务只运行兼容 action `remind`，生成今日行动建议笔记；不会触发文件整理、移动、删除或重命名。

## 6. 验证

```powershell
python -m unittest discover -s tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
```
