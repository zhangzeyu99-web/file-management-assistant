# 测试基准

本项目的测试基准不是单一脚本，而是一组可验证的质量门：产品原则、操作闭环、GUI 端到端、项目质量扫描和总 harness。任何功能改动都必须能说明对应的验证信号。

## 1. 产品原则基准

来源：`docs/PROJECT_PRINCIPLES.md`

- 本地优先：文件、报告和 Obsidian 笔记默认留在本机。
- 默认安全：不删除、不移动、不重命名、不重写源文件。
- 三主操作：首页只主推添加资料、搜索回顾、生成 AI 上下文包。
- GUI 可读：默认展示人能读懂的结果，不用黑色 JSON 框冒充结果。
- 云端边界：GitHub 只备份项目本体，不上传个人 Obsidian vault。

## 2. 操作闭环基准

来源：`docs/CLOSED_LOOP_USAGE.md`

每次操作至少回答四个问题：

- 做了什么。
- 来源是什么。
- 产物在哪里。
- 下一步能做什么。

失败态必须真实：

- 没有输入时不能显示完成。
- 没有来源时不能显示完成。
- 搜索无匹配时必须提示缺少证据。
- 生成 AI 上下文包必须先预览候选来源，再确认生成。

## 3. GUI E2E 基准

来源：`docs/GUI_E2E_TESTING.md`

Playwright 必须覆盖：

- 首页不是功能堆叠页，而是站点式知识入口。
- 首页只保留三个主操作锚点：添加资料、搜索回顾、生成 AI 上下文包。
- 知识卡片可展开详情和来源。
- 添加资料区能识别真实本地路径。
- 搜索回顾返回匹配来源、摘要和下一步。
- AI 上下文包先预览候选来源，再确认生成。
- 默认不展示原始 JSON。
- 严格 UX 模式发现已知问题时必须失败。

## 4. 项目质量基准

来源：`project_quality.py`

质量扫描必须覆盖：

- 必备文档齐全。
- 公共配置不泄露本机私有路径。
- `config.local.json` 不入 Git。
- 安全策略写清楚不删除、不移动、不重命名、不重写。
- 三主操作和旧 action 兼容关系仍成立。
- 设计规范和迭代复盘文档存在。
- guidebook 资源存在。
- 公开文本没有乱码。
- 旧版冗余文件不回到主线。

## 5. 总 harness 基准

来源：`scripts/verify-harness.ps1`

完整验证入口包括：

- `git_status`：确认工作区状态，除非显式允许 dirty。
- `unit_tests`：运行主要 Python 单元测试。
- `secret_scan`：检查 token 或密钥样式文本。
- `feature_contracts`：审计功能契约产物。
- `dry_run`：跑文件助手测试模式。
- `obsidian_manager_dry_run`：跑 Obsidian 管理测试模式。
- `scheduled_task_deprecated`：确认旧提醒计划任务安装入口已降级，不再作为核心闭环。
- `gui_e2e`：运行 GUI 严格 UX 端到端测试。
- `backup_manifest`：生成备份清单。
- `remote`：确认本地 HEAD 与 GitHub main 一致。

## 6. 推荐验证命令

```powershell
cd D:\codex\file-management-assistant
python -m unittest discover -s tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync
```

## 7. 判定规则

- 如果单测失败，先修业务逻辑。
- 如果 GUI E2E 失败，先修真实交互，不用说明文案掩盖。
- 如果质量扫描失败，先修文档、边界、乱码或冗余。
- 如果 harness 失败，不能宣称完整验证通过。
- 如果只跑了部分测试，汇报必须写清楚覆盖范围和未覆盖风险。

