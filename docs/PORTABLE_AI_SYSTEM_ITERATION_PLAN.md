# 可迁移 AI 知识系统迭代计划

## 来源依据

本轮参考视频《3层Obsidian文件系统，如何适配所有AI？随时迁移》（BV1Zj5i6MESx）。可确认材料来自 B 站元数据与 ASR 转写；官方 AI 摘要不可用。

视频的可落地观点：

- 本地优先：重要资料放在自己可控的本地文件和 Obsidian 里，避免平台封号、平台崩溃或导出失败导致上下文丢失。
- ACT 知识资产：把正在做的事、沉淀的知识卡、与时间相关的记录分层保存，给 AI 一个可检索入口。
- AI 身份文件：用固定文件记录用户是谁、工作偏好、沟通准则和协作边界，让不同 AI 工具快速进入状态。
- Skills / SOP：把重复流程写成普通 Markdown 步骤，让 AI 按你的方式执行，而不是每次从零解释。
- 可迁移：这些文件都是本地 Markdown，目标是可迁移、可复用、随时切换 AI 工具。

## 对当前项目的判断

当前项目不应该继续增加入口。它已经被多轮反馈收敛成三件事：

- 添加资料必须真实入库。
- 搜索回顾必须能找到已沉淀证据。
- 生成 AI 上下文包必须从证据生成可复制 prompt。

三层文件系统应该作为底层组织原则，而不是变成第四个 GUI 功能。

## 结构映射

| 视频三层 | 本项目落点 | 验收标准 |
| --- | --- | --- |
| ACT 知识资产 | `organize` 写 Obsidian 整理记录、每文件索引、知识卡片来源 | 输入真实路径后，每个可读文件都有独立索引条目，可被 `review` 搜到 |
| AI 身份文件 | 项目文档、用户偏好、协作规则、上下文包边界 | `extract` 输出里包含偏好、边界、来源路径，不把 AI 内部指令暴露给普通用户 |
| Skills / SOP | 三主操作流程、测试基准、GUI E2E、迭代复盘 | 新 AI 或新机器 clone 后能按 README 跑通 demo 和验证命令 |

## 本轮修复项

### 1. 点击来源必须真实可用

缺陷：搜索或上下文包结果里的来源路径可见，但点击后不一定能打开，用户会认为功能无效。

修复：

- `open-path` 只允许打开配置白名单内路径。
- Obsidian vault 内 Markdown 使用 `obsidian://open` 打开。
- 非 vault 文件或目录使用系统默认方式打开。
- 越权路径返回错误，不静默失败。

验收：

- 单测覆盖 vault Markdown、越权路径。
- GUI E2E 输出的路径必须真实存在。

### 2. E2E 结束必须清理服务端

缺陷：GUI E2E 跑完后可能残留 `gui_server.py` 监听端口，下一次测试状态不可信。

修复：

- 增加 `Stop-GuiServer`，同时清理启动进程和监听端口。
- Playwright 关闭只做 best-effort，避免关闭浏览器过程拖死整体测试。

验收：

- 质量测试检查脚本包含统一清理路径。
- E2E 后复核测试端口没有残留监听。

### 3. 公开文档不再宣传旧知识流

缺陷：README 和 DESIGN 残留“站点式知识流”主线，和三操作闭环冲突。

修复：

- README 只讲添加资料、搜索回顾、生成 AI 上下文包。
- DESIGN 改为三操作结果详情和可迁移三层原则。
- `PROJECT_PRINCIPLES` 增加 portable ai three layers。

验收：

- 质量测试禁止 README/DESIGN 宣传旧知识流。
- 质量测试要求公开文档包含 ACT 知识资产、AI 身份文件、Skills / SOP。

### 4. 三层系统不增加入口，只增强三操作

缺陷：如果把视频里的 ACT、AI 身份文件、Skills/SOP 直接做成新入口，项目会重新膨胀成多按钮工作台。

修复：

- ACT 知识资产落到 `添加资料`：写整理记录、文件索引、可搜索证据。
- AI 身份文件落到 `生成 AI 上下文包`：作为偏好和边界摘要，不替代证据来源。
- Skills/SOP 落到项目模板、README、测试原则和 harness：让新 AI 或新机器能按同一套步骤恢复。
- 真实 GUI 查询 QA 作为可迁移系统的验收入口：页面输入真实问题后，必须找到证据并能预览上下文包。

验收：

- `run-real-query-gui-qa.ps1 -StrictUx` 通过。
- `verify-harness.ps1` 包含 `real_query_gui_qa`。
- 三层原则只出现在底层结构和文档，不回到首页做第四功能。

## 下一阶段计划

### 已落地：AI 身份文件与 Skills / SOP 初始化

- 已新增版本化模板：`AI_IDENTITY.md`、`AI_COLLABORATION_RULES.md`、`AI_CONTEXT_BOUNDARY.md`。
- 已新增三主操作 SOP：`Skills-SOP/organize.md`、`Skills-SOP/review.md`、`Skills-SOP/extract.md`。
- `scripts/init-assistant.ps1 -Demo` 会把模板写入 demo vault 的 `knowledge_root`。
- 真实 vault 可通过 `scripts/init-assistant.ps1 -InstallPortableTemplates` 安装同一套模板。

### 阶段 A：把 AI 身份文件产品化

- 已实现：`extract` 预览时提示是否发现 AI 身份文件，生成时把身份偏好和上下文边界摘要写入 prompt 与 Markdown。
- 边界：AI 身份文件不能替代证据来源；没有搜索候选或确认来源时仍拒绝生成上下文包。
- GUI 只展示“本次上下文是否包含身份偏好”，不新增主入口。

### 阶段 B：把 Skills / SOP 产品化

- 在 README 增加“换到其他 AI 工具时怎么用”。
- 验证：不用 Codex，只读 Markdown 也能执行同样流程。

### 阶段 C：把 ACT 资产检索做实

- 添加资料继续强化每文件索引。
- 搜索回顾按 ACT 类型展示：行动记录、知识卡、时间记录、AI 会话。
- 生成上下文包按证据类型压缩，不混入无关旧报告。

## 本轮不做

- 不恢复提醒功能。
- 不恢复知识流首页。
- 不做自动移动、删除、重命名源文件。
- 不接向量库或外部大模型。
- 不把个人 Obsidian vault 上传到公开仓库。
