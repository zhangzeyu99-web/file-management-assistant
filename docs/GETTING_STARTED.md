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

## 3. 四个主入口

- `整理资料`：放入文本、文件目录或 AI 对话，写入新的 Obsidian 整理记录。
- `回顾知识`：输入关键词或问题，返回本地摘要和来源。
- `提取上下文`：输入当前任务，生成 AI 上下文包。
- `今日提醒`：生成今天 1-3 个重点。

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

## 5. 安装每天 9 点提醒

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-scheduled-task.ps1
```

提醒任务只运行 `remind`，生成 1-3 个今日重点；不会触发文件整理、移动、删除或重命名。

## 6. 验证

```powershell
python -m unittest discover -s tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
```
