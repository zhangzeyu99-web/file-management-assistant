# 2026-06-02 三操作公共接口与 GUI QA 收敛

## 本轮目标

继续把项目收敛成方便使用的本地知识管理库，不再让旧的知识流、伪控制台或诊断入口回到公共产品界面。

本轮只围绕三件事做 QA：

- 添加资料：真实读取资料，写入新 Obsidian 记录和索引。
- 搜索回顾：基于证据返回答案、命中词、摘录和来源路径。
- 生成 AI 上下文包：先预览候选来源，再生成可复制 prompt。

## 发现的问题

### 1. 公共状态接口仍暴露旧知识流

`/api/status` 仍返回 `knowledge_feed`，GUI 也读取 `status.knowledge_feed` 和 `status.file_report`。

问题影响：

- 首页虽然不展示知识流，但公共接口仍保留旧产品形态。
- 首页指标出现 `-`，用户无法理解统计含义。
- 后续测试文档可能继续把知识流当成主流程。

### 2. GUI E2E 每个动作多等待 30 秒

页面已经删除默认 JSON 调试框 `#out`，但 E2E 仍在每次操作后调用 `#out.evaluate()`。

问题影响：

- `#out` 不存在时 Playwright 默认等待约 30 秒。
- 5 个动作会额外拖慢 150 秒以上。
- 测试通过也不能代表成熟产品体验，因为 QA 本身被旧实现拖慢。

### 3. E2E wrapper 缺少 run-code 超时保护

`run-gui-e2e.ps1` 直接等待 `playwright-cli run-code`，出问题时可能长时间挂住。

问题影响：

- 测试失败时缺少清晰证据。
- GUI server 和 Playwright 进程可能残留。

## 已完成修复

### 公共产品接口

- `build_status()` 不再返回 `knowledge_feed`。
- 首页指标改成：
  - 核心操作：3
  - 源文件改动：0
  - Obsidian 笔记：当前 vault 的 Markdown 数
  - 最近刷新：当前时间
- GUI 不再读取 `status.file_report` 或 `status.knowledge_feed`。

### GUI E2E

- `isOutputVisible()` 先检查 `#out` 是否存在，不存在立即返回。
- 每个动作记录 `duration_ms`。
- E2E 报告字段从旧的 `knowledge_detail` 改为 `three_operations`。
- `run-gui-e2e.ps1` 增加 `Invoke-PlaywrightRunCode`：
  - stdout/stderr 写入文件；
  - run-code 有 300 秒上限；
  - 超时后关闭 Playwright session；
  - 清理 session 相关进程。

### 文档与测试

- `docs/GUI_E2E_TESTING.md` 改为三操作 QA，不再要求知识流和知识卡详情。
- `tests/test_gui_server.py` 增加公共状态接口不暴露知识流的断言。
- `tests/test_project_quality.py` 增加 E2E 超时保护和 `#out` 等待防回归断言。

## 验证结果

### 目标测试

```powershell
python -X utf8 -m unittest tests.test_gui_server.GuiServerTests.test_status_reports_three_operation_product_status_without_public_feed tests.test_gui_server.GuiServerTests.test_html_exposes_only_three_primary_operations_without_knowledge_feed tests.test_project_quality.ProjectQualityTests.test_public_docs_do_not_promote_knowledge_feed_as_core_flow -v
```

结果：通过。

### 相关测试

```powershell
python -X utf8 -m unittest tests.test_gui_server -v
python -X utf8 -m unittest tests.test_project_quality -v
python -X utf8 project_quality.py
```

结果：通过。

### GUI E2E

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
```

结果：通过。

最新 E2E：

- run_dir: `D:\codex\file-management-assistant\output\gui-e2e\20260602-133911-387-9aabe048`
- actions: 5
- mechanics_failures: 0
- ux_issues: 0

动作耗时：

- 检查本地目标：1920 ms
- 添加资料：1907 ms
- 搜索回顾：2932 ms
- 预览候选来源：2874 ms
- 确认生成上下文包：1908 ms

## 自评问题

### 做到了视觉清晰阅读友好吗？

本轮没有大改视觉，但修复了首页统计含义不清的问题。现在首页指标能对应三操作产品语义。

### 做到了总结归纳到位，没有废话不遗漏关键信息吗？

当前结果卡仍按答案、证据、产物、下一步展示；本轮主要防止旧知识流和无意义统计干扰用户。

### 发给别人能看懂吗？传到 Codex 指引性足够吗？

本轮文档明确记录了缺陷、影响、修复和验证命令。新 Codex 线程可直接按本日志继续 QA。

### GUI 双向交互方便吗？信息内容容易编辑吗？

三操作保留真实输入、路径检查、来源打开和 prompt 复制。仍需下一轮继续检查“打开来源”在真实 Obsidian 中的体验。

### 展示的方式足够方便吗？信息集关联有做吗？能让人发散性思考吗？

公共首页不再做知识流展示。信息关联转移到搜索回顾和 AI 上下文包的证据来源中，避免首页变成杂乱卡片流。

## 下一轮建议

- 对真实 Obsidian vault 跑一次只读搜索回顾，检查真实数据的命中质量。
- 对 `添加资料` 跑一个真实目录小样本，确认每个可读文件都能生成独立索引。
- 对 `open-path` 在真实 Obsidian 中手动验证 URI 打开体验。
