# 2026-06-02 Obsidian 找回路径迭代

## 本轮目标

修复用户入库后不知道“Obsidian 笔记在哪里、怎么打开、怎么继续搜索”的问题。核心不是新增功能，而是让 `添加资料` 的结果真正可找回、可复盘、可继续被 AI 调用。

## 修复内容

### 1. 后端输出找回位置

`organize` 现在在 `debug.obsidian_locations` 中返回：

- `vault`
- `knowledge_root`
- `organize_note`
- `organize_dir`
- `file_index_dir`
- `first_file_index_note`
- `search_hint`

同时新增 `obsidian-directory` 产物，用户可以直接打开整理目录。

### 2. GUI 展示找回说明

`添加资料` 结果新增 `在 Obsidian 里怎么找` 区块，固定展示：

- 整理记录：本次入库主笔记。
- 整理目录：按时间回看所有入库记录。
- 文件索引目录：按文件名、路径或摘录关键词找每个可读文件。

### 3. 文档补齐

README、快速上手和 GUI 说明都补充了默认目录：

- `04 例行工作\知识整理助手\整理`
- `04 例行工作\知识整理助手\文件索引`
- `04 例行工作\知识整理助手\AI 上下文包`

## 验证

目标测试：

```powershell
python -X utf8 -m unittest tests.test_knowledge_assistant.KnowledgeAssistantTests.test_organize_exposes_obsidian_findability_locations -v
python -X utf8 -m unittest tests.test_gui_server.GuiServerTests.test_html_explains_where_to_find_new_obsidian_notes -v
```

结果：通过。

## 自查

| 问题 | 判断 | 证据 | 缺口 | 下一轮改进 |
| --- | --- | --- | --- | --- |
| 做到了视觉清晰阅读友好吗？ | 部分通过 | GUI 有独立“在 Obsidian 里怎么找”区块。 | 还未截图验证真实长路径在浏览器里的排版。 | 跑真实 GUI 走读并保存截图。 |
| 做到了总结归纳到位，没有废话不遗漏关键信息了吗？ | 通过 | 固定展示整理记录、整理目录、文件索引目录。 | AI 上下文包目录在 organize 结果里不展示。 | extract 结果也补“上下文包在哪里找”。 |
| 发给别人能看懂吗？ | 通过 | README 和快速上手写清默认目录。 | 真实用户仍需要知道自己的 `knowledge_root` 配置。 | 配置页或状态区显示当前 knowledge_root。 |
| 传到 Codex 指引性足够吗？ | 通过 | 后端返回结构化 `obsidian_locations`，可被 Codex 读取。 | 还没有专门的上下文包找回字段。 | 给 extract 增加同类位置字段。 |
| GUI 双向交互方便吗？ | 部分通过 | 找回卡有复制路径和打开按钮。 | 未用真实浏览器测试打开目录体验。 | P0 真实 GUI 走读覆盖打开目录。 |
| 信息内容容易编辑吗？ | 通过 | 产物都是 Markdown 和路径字段。 | 无。 | 保持。 |
| 展示的方式足够方便吗？ | 部分通过 | 目录拆成三张卡，比普通产物列表清楚。 | 产物区和找回区可能重复显示部分路径。 | 后续可把普通产物区按类型折叠。 |
| 信息集关联有做吗？ | 部分通过 | 整理记录、文件索引和搜索回顾已经串起来。 | 搜索结果还未显式反链到“本次整理记录”。 | 强化文件索引里的关联整理记录展示。 |
| 能让人发散性思考吗？ | 部分通过 | search hint 告诉用户可搜文件名、路径、摘录关键词。 | 还未给出推荐检索词。 | organize 可输出建议搜索词。 |

## 下一步

继续 P0 真实 GUI 走读：用真实页面跑 `添加资料 -> 搜索回顾 -> 加入上下文包 -> 生成 prompt`，检查长路径、打开来源、已选候选和截图。

