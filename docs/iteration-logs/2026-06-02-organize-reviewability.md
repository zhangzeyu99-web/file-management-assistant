# 2026-06-02 添加资料可回顾性迭代

## 本轮目标

让 `添加资料` 不只是把资料写进 Obsidian，而是让用户马上知道“下一步该搜什么、从哪里回看、文件索引和整理记录如何关联”。

## 问题

此前 `添加资料` 已经能生成整理记录和独立文件索引，文件索引里也有 `关联整理记录`。但缺口仍然明显：

- 整理记录本身没有列出本次生成的文件索引路径。
- GUI 没有告诉用户可以用哪些关键词回顾刚入库内容。
- 用户需要自己从文件名、路径和摘录里猜搜索词，入库到回顾的链路不够顺。

## 修复

### 1. 推荐搜索词

`organize` 新增 `debug.recommended_search_terms`，来源包括：

- 整理标题。
- 可读文件名。
- 可读文件摘录中的稳定标识词。

GUI 在添加资料结果中显示 `推荐搜索词`，按钮可复制，复制后可直接粘到 `搜索回顾`。

### 2. 整理记录反链文件索引

整理记录新增：

- `## 推荐搜索词`
- `## 关联文件索引`

这样从整理记录能回到每个独立文件索引，从文件索引也能通过 `关联整理记录` 回到本次入库主笔记。

### 3. E2E 验收

Playwright 严格走读新增 `organize_recommended_search_terms` 标志，检查：

- 页面结果包含 `推荐搜索词`。
- 后端响应包含非空 `debug.recommended_search_terms`。

## 验证记录

```powershell
python -X utf8 -m unittest tests.test_knowledge_assistant.KnowledgeAssistantTests.test_organize_adds_recommended_search_terms_and_file_index_backlinks -v
python -X utf8 -m unittest tests.test_gui_server.GuiServerTests.test_html_shows_recommended_search_terms_after_organize -v
python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_gui_harness_verifies_local_target_workbench -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
```

已确认：

- `organize_recommended_search_terms`: true
- `obsidian_findability`: true
- `extract_findability`: true
- `seeded_context_from_review`: true
- 机械失败：0
- UX issue：0

## 自查

| 问题 | 判断 | 证据 | 仍需改进 |
| --- | --- | --- | --- |
| 做到了视觉清晰阅读友好了吗？ | 部分通过 | GUI 新增独立推荐搜索词卡片。 | 推荐词过多时需要更好的折叠。 |
| 做到了总结归纳到位，没有废话不遗漏关键信息了吗？ | 通过 | 只展示能直接用于搜索回顾的词。 | 无。 |
| 发给别人能看懂吗？ | 通过 | README、快速上手和 GUI 说明已解释推荐词用途。 | 无。 |
| 传到 Codex 指引性足够吗？ | 通过 | `debug.recommended_search_terms` 可被 Codex 读取并用于后续测试。 | 后续可让 Codex 自动用推荐词跑回顾抽检。 |
| GUI 双向交互方便吗？ | 部分通过 | 推荐词按钮可复制，能接到搜索回顾。 | 还没有一键把词填入搜索框。 |
| 信息内容容易编辑吗？ | 通过 | 推荐词和反链写进 Markdown 整理记录。 | 无。 |
| 展示的方式足够方便吗？ | 部分通过 | 推荐词从普通产物区独立出来。 | 仍需截图确认移动端换行。 |
| 信息集关联有做吗？ | 通过 | 整理记录链接文件索引，文件索引反链整理记录。 | 未来可加 Obsidian 双链格式。 |
| 能让人发散性思考吗？ | 部分通过 | 推荐词降低回顾门槛。 | 可继续生成相近追问和主题标签。 |

## 下一轮

优先做“推荐词一键填入搜索回顾并执行”的 GUI 交互，进一步减少手工复制粘贴。
