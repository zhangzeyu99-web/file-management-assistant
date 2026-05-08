# Closed Loop Usage

本项目的闭环不是“自动帮你做完所有整理”，而是让每次操作都留下可回顾、可提取、可验证的结果。

## 操作闭环

1. 输入资料、路径、问题或当前任务。
2. 点击整理资料、回顾知识、提取上下文或今日提醒。
3. 结果卡显示 summary、sources、artifacts、next_actions。
4. 需要继续问 AI 时，复制 AI 上下文包。
5. 需要长期保留时，打开 Obsidian 新笔记。

## 验收标准

- 页面只显示四个主入口。
- 默认不展示黑色 JSON。
- 点击后必须显示做了什么、来源是什么、产物在哪、下一步能点什么。
- 默认不删除、不移动、不重命名、不重写源文件。
- Playwright 必须覆盖首页截图和点击后状态。

## 验证命令

```powershell
python -m unittest discover -s tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync
```
