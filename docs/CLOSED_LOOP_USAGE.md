# Closed Loop Usage

本项目的闭环不是“自动帮你做完所有整理”，而是让每次操作都留下可回顾、可提取、可验证的结果。

## 操作闭环

1. 输入资料、路径、问题或当前任务。
2. 点击添加资料、搜索回顾，或在生成 AI 上下文包前先预览候选来源。
3. 结果卡显示 summary、sources、artifacts、next_actions。
4. 需要继续问 AI 时，确认候选来源并复制 AI 上下文包。
5. 需要长期保留时，打开 Obsidian 新笔记。

## 验收标准

- 页面只显示三个主入口。
- 默认展示可读结果；诊断细节只在工具维护页按需查看。
- 点击后必须显示做了什么、来源是什么、产物在哪、下一步能点什么。
- 无来源时不能显示已完成；提取上下文必须先出现候选来源。
- 默认不删除、不移动、不重命名、不重写源文件。
- Playwright 必须覆盖首页截图和点击后状态。

## 验证命令

```powershell
python -m unittest discover -s tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync
```
