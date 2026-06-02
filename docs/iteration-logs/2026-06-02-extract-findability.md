# 2026-06-02 AI 上下文包找回迭代

## 本轮目标

补齐三主操作中的最后一段找回体验：`生成 AI 上下文包` 不只要生成 prompt，还要告诉用户在 Obsidian 里哪里能找到上下文包笔记、上下文包目录和本次运行证据。

## 问题

`extract` 已经写入 runtime Markdown 和 Obsidian note，但 GUI 只把它们放进普通产物卡。用户能复制 prompt，却不一定知道：

- Obsidian 里的上下文包笔记在哪里。
- 以后按任务回看上下文包应该打开哪个目录。
- 本次运行证据对应哪个 runtime Markdown。

这会破坏“可归档、可回顾、可提取给 AI 续用”的闭环。

## 修复

### 1. 后端结构化位置字段

`extract` generate 结果新增 `debug.extract_locations`：

- `vault`
- `knowledge_root`
- `extract_note`
- `extract_dir`
- `runtime_markdown`
- `search_hint`

### 2. GUI 文档式展示

新增 `renderExtractLocation()`，只在 `extract` generate 成功后显示：

- 上下文包笔记：本次 Obsidian Markdown。
- 上下文包目录：后续回看和复用入口。
- runtime Markdown：本次运行证据。

### 3. E2E 验收

Playwright 严格走读新增 `extract_findability` 标志，检查：

- 页面结果包含 `上下文包在 Obsidian 里怎么找`。
- 页面结果包含 `上下文包目录`。
- 后端响应包含 `debug.extract_locations.extract_note`、`extract_dir`、`runtime_markdown`。

## 验证记录

```powershell
python -X utf8 -m unittest tests.test_knowledge_assistant.KnowledgeAssistantTests.test_extract_generate_exposes_obsidian_context_package_locations -v
python -X utf8 -m unittest tests.test_gui_server.GuiServerTests.test_html_explains_where_to_find_generated_context_packages -v
python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_gui_harness_verifies_local_target_workbench -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
```

已确认：

- `extract_findability`: true
- `obsidian_findability`: true
- `seeded_context_from_review`: true
- `preview_before_generate`: true
- 机械失败：0
- UX issue：0

## 自查

| 问题 | 判断 | 证据 | 仍需改进 |
| --- | --- | --- | --- |
| 做到了视觉清晰阅读友好了吗？ | 部分通过 | 上下文包位置拆成三张来源卡，不再塞进普通摘要。 | 还要看真实长路径在截图中的换行效果。 |
| 做到了总结归纳到位，没有废话不遗漏关键信息了吗？ | 通过 | 只展示笔记、目录、runtime 三个用户需要的位置。 | 无。 |
| 发给别人能看懂吗？ | 部分通过 | README、快速上手、GUI 说明已写入找回路径。 | 还可补一张三步流程图。 |
| 传到 Codex 指引性足够吗？ | 通过 | `debug.extract_locations` 可被 Codex 直接读取。 | 后续可自动把 E2E 报告也整理成知识卡。 |
| GUI 双向交互方便吗？ | 部分通过 | 位置卡支持复制路径和打开路径。 | 打开路径仍依赖本机后端和 OS 关联。 |
| 信息内容容易编辑吗？ | 通过 | 上下文包是 Markdown，可在 Obsidian 直接编辑。 | 无。 |
| 展示的方式足够方便吗？ | 部分通过 | 找回区与 prompt 预览区分离。 | 多来源上下文包的来源卡仍可继续压缩。 |
| 信息集关联有做吗？ | 通过 | 搜索证据 -> 上下文包 -> Obsidian 笔记/目录已形成链路。 | 文件索引反链到整理记录仍待强化。 |
| 能让人发散性思考吗？ | 部分通过 | search hint 提醒可搜标题、来源路径、prompt 关键词。 | 还缺推荐追问和相近检索词。 |

## 下一轮

优先强化文件索引和整理记录的双向关联；同时给添加资料结果生成推荐检索词，让用户更容易回顾刚入库的资料。
