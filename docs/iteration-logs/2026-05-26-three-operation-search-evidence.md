# 2026-05-26 三操作闭环与证据检索迭代

## 本轮目标

把产品主线收敛为三件事：添加资料、搜索回顾、生成 AI 上下文包。GUI 不再展示知识流、提醒、诊断入口和默认 JSON；搜索必须基于已入库证据返回答案、命中词、摘录和来源路径。

## 主要改动

- `添加资料`：真实扫描文本、文件、目录；为可读文件生成独立索引条目；只写新 Obsidian 记录和运行清单，不改源文件。
- `搜索回顾`：改成严格证据检索；精确短语、标题、正文摘录优先；重复运行报告和泛索引降权；无可靠证据返回未找到。
- `生成 AI 上下文包`：复用搜索候选，预览后生成 Markdown 和可复制 prompt；prompt 必须包含来源路径。
- GUI：首页只保留三操作；结果区改为一句话答案、命中证据、生成产物、Prompt 预览和下一步建议。
- 测试：补充 `运营sop`、无匹配、目录入库、上下文包预览/生成、GUI 三入口和视觉回归用例。

## 自检问题

- 做到了视觉清晰阅读友好了吗？基本做到。结果从黑框/混排改为文档卡片，长路径改为可横向滚动的路径 chip。
- 做到了总结归纳到位，没有废话不遗漏关键信息了吗？搜索结果强制输出答案、命中词、证据摘录和来源路径，弱相关内容不再伪装成完成。
- 发给别人能看懂吗？能。README 和上手文档现在只讲三操作闭环。
- 传到 Codex 指引性足够吗？能。AI 上下文包从搜索证据生成，并保留来源路径和安全边界。
- GUI 双向交互方便吗？比上一版好，但仍是本地 Python action 驱动，不是完整后台任务队列。
- 信息内容容易编辑吗？落盘为 Markdown 和 Obsidian 笔记，可直接编辑。
- 展示的方式足够方便吗？搜索卡片、产物卡片和 prompt 预览已分区；后续可继续压缩来源卡密度。
- 信息集关联有做吗？本轮做了来源路径、命中词和加入上下文包的关联。
- 能让人发散性思考吗？当前优先保证准确闭环，发散式相关问题暂未恢复到首页。

## 验证结果

- `python -X utf8 -m unittest discover -s tests -v`：91 项通过。
- `python -X utf8 project_quality.py`：通过。
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx`：通过，0 个 mechanics failure，0 个 UX issue。
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-harness.ps1 -AllowDirty -SkipRemoteSync`：通过。
- 真实数据查询：`运营sop` 命中 `D:\codex\output\doc\sop_kb_export_20260420\README.md`；`不存在的测试关键词` 正确返回未找到。

## 下一轮改进

- 搜索结果增加“为什么其他候选被排除”的调试视图，但默认不展示。
- 对 Obsidian 中长期沉淀的 Codex 会话做更稳定的标题索引和别名表。
- 将 GUI 的“加入上下文包”改为可见的候选篮，避免用户不知道已选择哪些来源。
