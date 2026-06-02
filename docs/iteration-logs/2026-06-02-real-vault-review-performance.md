# 2026-06-02 真实 Vault 搜索回顾性能 QA

## 本轮目标

在已经提交三操作产品 QA 后，用真实配置 `config.local.json` 做只读搜索回顾验收，确认搜索回顾不是只在 demo 数据里可用。

## 真实配置边界

- Obsidian vault：`D:\Obsidian-Work`
- knowledge_root：`D:\Obsidian-Work\04 例行工作\知识行动助手`
- 本轮只运行 `review`，不运行 `organize` 或 `extract generate`，避免写入真实 vault。

## 发现的问题

### 1. PowerShell 中文 here-string 会污染测试输入

第一次测试里中文查询显示为 `??sop`、`????`。这是 Windows 控制台输入编码问题，不是搜索功能本身。

处理方式：

- 真实 QA 脚本里的中文查询统一用 Unicode escape。
- 不再根据 PowerShell 直接显示判断中文文件是否乱码。

### 2. 搜索回顾真实数据耗时偏慢

修复前，真实 vault 单次 `review` 耗时约 14–16 秒。

根因：

- `iter_watch_markdown_notes()` 对 watch root 使用 `root.rglob("*")`。
- `Documents` 这类目录有 5 万多个文件，但真正可索引的 Markdown/TXT 远少于总文件数。
- 旧逻辑会遍历并 stat 大量无关文件。

## 已完成修复

### 1. watch root 只枚举候选扩展

`iter_watch_markdown_notes()` 改为只扫描：

- `*.md`
- `*.txt`

再做深度过滤、mtime 排序和 `max_files` 限制。

### 2. 增加 review 索引进程内缓存

新增：

- `clear_review_index_cache()`
- `review_index_cache_stats()`
- `review_index_cache_key()`
- `build_review_index_uncached()`

行为：

- 同一配置下连续 `review/extract preview` 复用索引。
- `organize` 写入新资料后清缓存，保证新入库资料能被搜索到。
- 缓存 TTL 为 60 秒，避免长期陈旧。

## 验证结果

### 单元测试

```powershell
python -X utf8 -m unittest tests.test_knowledge_assistant.KnowledgeAssistantTests.test_review_index_cache_reuses_index_and_organize_invalidates_it tests.test_knowledge_assistant.KnowledgeAssistantTests.test_watch_root_index_uses_extension_specific_globs -v
```

结果：通过。

### 真实查询结果

真实配置连续查询结果：

| 查询 | 结果 | 首条来源 | 耗时 |
| --- | --- | --- | ---: |
| 运营sop | 命中 | Codex 运营SOP主库线程归档 | 6641.8 ms |
| github仓库 | 命中 | 文件管理助手流程归档 | 295.7 ms |
| 简历线程 | 命中 | 简历 career-ops 主线程归档 | 541.0 ms |
| Obsidian助手 | 命中 | 2026-04-27 | 617.5 ms |
| 不存在的测试关键词 | 未找到 | 无 | 101.7 ms |

对比：

- 修复前：每次约 14–16 秒。
- 修复后：首查约 6.6 秒；同一进程后续查询约 0.1–0.6 秒。

## 自评问题

### 做到了视觉清晰阅读友好吗？

本轮不改视觉，改搜索等待体验。连续搜索不再让用户每次等待十几秒。

### 做到了总结归纳到位，没有废话不遗漏关键信息吗？

搜索结果仍能返回答案、命中词、证据摘录和来源路径；未找到时没有伪完成。

### 发给别人能看懂吗？传到 Codex 指引性足够吗？

本日志记录了真实配置、根因、修复、验证命令和耗时对比，可供下一轮 Codex 直接接上。

### GUI 双向交互方便吗？信息内容容易编辑吗？

连续搜索速度改善后，GUI 的搜索回顾更接近可用产品。仍需继续验证真实 GUI 下的打开来源体验。

### 展示的方式足够方便吗？信息集关联有做吗？能让人发散性思考吗？

信息关联仍依赖证据来源和 AI 上下文包。下一轮应检查真实来源打开后在 Obsidian 中是否容易继续编辑和扩展。

## 下一轮建议

- 用真实 GUI 跑 `review` 只读烟测，确认页面结果排版在真实长路径下不乱。
- 对 `open-path` 做真实 Obsidian URI 打开测试。
- 考虑把首查索引构建状态展示成“正在建立索引”，避免用户误以为卡住。
