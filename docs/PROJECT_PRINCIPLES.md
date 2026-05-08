# Project Principles

This project is a local knowledge organizer for Obsidian and AI workflows. It is not a cloud file cleaner and not a general automation bot.

## Principles

- local-first / 本地优先：files, reports, and Obsidian notes stay on the local machine by default.
- safe-by-default：默认不删除、不移动、不重命名、不重写源文件。
- private local configuration：machine-specific paths and secrets belong in `config.local.json`, which is ignored by Git.
- local knowledge organizer：产品名称统一为本地知识整理助手。
- four core actions：主线统一为整理 / 回顾 / 提取 / 提醒，对应 organize / review / extract / remind。
- obsidian workflow：所有沉淀结果优先写成 Obsidian 新笔记，保留来源和下一步。
- human-readable GUI：成熟个人知识工作台风格，默认不展示黑色 JSON，GUI 输出必须让人能直接理解。
- portable bootstrap：`scripts/init-assistant.ps1` 提供 demo mode 和一键初始化，新机器 clone 后可跑通。
- cloud backup boundary：GitHub 备份项目本体；个人 Obsidian 内容不进公开仓库。
- closed loop：每轮改动必须有 acceptance checks，包括单测、GUI E2E、harness 和可复核截图。
- lightweight daily triage：每天 9 点只生成 1-3 个重点，不做定时整理。
- life / study / work：整理时保留生活 / 学习 / 工作判断，但不强制复杂分类。
- thin gui：GUI 只负责展示和调用，业务分发下沉到 `knowledge_assistant.py`。
- validation harness：`scripts/verify-harness.ps1` 是主验证入口。
- legacy compatibility：旧 action 保留兼容，但只放在高级/诊断里。

## Non Goals

- 不做源文件搬迁。
- 不做语义向量库。
- 不做外部通知作为核心功能。
- 不把个人 vault 上传到公开仓库。
