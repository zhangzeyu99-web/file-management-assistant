# Getting Started

This guide gets the Knowledge Action Assistant running locally.

## 1. Install Prerequisites

```powershell
python --version
powershell -NoProfile -Command "$PSVersionTable.PSVersion"
```

Python 3.11+ is recommended.

## 2. Create Local Config

```powershell
Copy-Item .\config.example.json .\config.local.json
notepad .\config.local.json
```

Edit local paths in `config.local.json`. Do not commit that file.

## 3. Run Tests

```powershell
python -m unittest discover -s tests -v
```

## 4. Start The GUI

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1
```

Open:

```text
http://127.0.0.1:8765/
```

Start with these buttons:

- 今天先干什么
- 记录一个任务
- 这段内容放哪
- 复盘今天
- 检查知识库
- 生成 Codex 交接
- 查看文件雷达
- 打开 Obsidian

## 5. First Useful Workflow

1. Click `今天先干什么`.
2. If you have a concrete task, click `记录一个任务`.
3. If you have reusable knowledge, use `沉淀知识卡`.
4. At the end of the day, click `复盘今天`.

Keep daily work lightweight. Do not process every archive candidate every day.
