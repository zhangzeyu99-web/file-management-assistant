# Project Principles

This project is a local knowledge organizer for Obsidian and AI workflows. It is not a cloud file cleaner and not a general automation bot.

## Principles

- local-first / 本地优先：files, reports, and Obsidian notes stay on the local machine by default.
- safe-by-default：默认不删除、不移动、不重命名、不重写源文件。
- private local configuration：machine-specific paths and secrets belong in `config.local.json`, which is ignored by Git.
- local knowledge organizer：产品名称统一为本地知识整理助手。
- three primary operations：首页主线统一为添加资料 / 搜索回顾 / 生成 AI 上下文包，对应 organize / review / extract；只保留三件事，其他工具降级为历史说明。
- obsidian workflow：所有沉淀结果优先写成 Obsidian 新笔记，保留来源和下一步。
- human-readable GUI：站点式知识库 + 成熟个人知识工作台风格，默认展示可读结果，不展示伪控制台和旧诊断入口。
- portable bootstrap：`scripts/init-assistant.ps1` 提供 demo mode 和一键初始化，新机器 clone 后可跑通。
- cloud backup boundary：GitHub 备份项目本体；个人 Obsidian 内容不进公开仓库。
- closed loop：每轮改动必须有 acceptance checks，包括单测、GUI E2E、harness 和可复核截图。
- core loop only：添加资料必须真实入库；搜索回顾必须找到已沉淀证据；生成 AI 上下文包必须从证据生成可复制 prompt。
- life / study / work：整理时保留生活 / 学习 / 工作判断，但不强制复杂分类。
- thin gui：GUI 只负责展示和调用，业务分发下沉到 `knowledge_assistant.py`。
- validation harness：`scripts/verify-harness.ps1` 是主验证入口。
- deprecated non-core tools：旧工具已降级，不再出现在首页或默认命令行；需要恢复时必须先证明它能服务三主闭环。

## Non Goals

- 不做源文件搬迁。
- 不做语义向量库。
- 不做外部通知作为核心功能。
- 不把个人 vault 上传到公开仓库。
