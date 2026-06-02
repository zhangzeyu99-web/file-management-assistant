# 2026-06-02 可迁移模板初始化

## 本轮目标

继续把项目做成方便的知识管理库，而不是停留在文档原则。上一轮已确认三层结构：`ACT 知识资产`、`AI 身份文件`、`Skills / SOP`。本轮把后两层做成可安装的 Markdown 资产。

## 本轮改动

- 新增 `templates/portable-ai-system/AI 身份文件/AI_IDENTITY.md`。
- 新增 `templates/portable-ai-system/AI 身份文件/AI_COLLABORATION_RULES.md`。
- 新增 `templates/portable-ai-system/AI 身份文件/AI_CONTEXT_BOUNDARY.md`。
- 新增 `templates/portable-ai-system/Skills-SOP/organize.md`。
- 新增 `templates/portable-ai-system/Skills-SOP/review.md`。
- 新增 `templates/portable-ai-system/Skills-SOP/extract.md`。
- `scripts/init-assistant.ps1 -Demo` 会把这些模板安装到 demo vault 的 `knowledge_root`。
- `scripts/init-assistant.ps1 -InstallPortableTemplates` 可把同一套模板安装到真实 vault 的 `knowledge_root`。
- `project_quality.py` 增加 `portable_ai_templates` 检查，防止模板缺失但质量门禁仍通过。

## 产品意义

- 新手可以先跑 demo，不只看到 GUI，也能在 Obsidian 里看到身份文件和 SOP 文件。
- 换到其他 AI 工具时，可以把 `AI 身份文件` 和 `Skills-SOP` 作为协作入口，而不是重新解释项目背景。
- 三主操作的流程被写成普通 Markdown，降低工具迁移成本。

## 自查问题

- 做到了视觉清晰阅读友好了吗？本轮不改 GUI 视觉，但模板用短段落和固定字段，适合 Obsidian 阅读。
- 做到了总结归纳到位，没有废话不遗漏关键信息了吗？模板只保留用途、流程、验收、下一步，不写内部执行噪音。
- 发给别人能看懂吗？模板不依赖 Codex 私有上下文，其他 AI 或人也能理解。
- 传到 Codex 指引性足够吗？SOP 明确添加资料、搜索回顾、生成 AI 上下文包的输入、流程和验收。
- GUI 双向交互方便吗？本轮没有新增 GUI 操作，避免首页再次变复杂。
- 信息内容容易编辑吗？所有模板都是普通 Markdown，可直接在 Obsidian 编辑。
- 展示的方式足够方便吗？模板安装到 `knowledge_root` 下，能被 Obsidian 和后续搜索回顾使用。
- 信息集关联有做吗？身份文件负责人和边界，SOP 负责流程，和三主操作形成关联。
- 能让人发散性思考吗？身份文件留出角色、项目、偏好和禁止项，能引导用户继续补全个人知识系统。

## 剩余风险

- `extract` 还没有自动读取 AI 身份文件摘要。
- GUI 还没有显示“本次上下文是否包含身份偏好”。
- 真实 vault 安装模板需要用户显式运行 `-InstallPortableTemplates`，不会默认写入个人库。
