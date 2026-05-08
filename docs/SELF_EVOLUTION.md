# Self Evolution

下一阶段优化必须继续服务四功能主线，而不是继续堆按钮。

## 交互更方便

- 首页保留四卡，不增加主入口。
- 结果卡继续压缩成 summary、sources、artifacts、next_actions。
- 高级 JSON 只在调试时展开。

## 安装部署更快捷

- `scripts/init-assistant.ps1 -Demo` 必须在新机器上无个人资料也能跑通。
- `config.example.json` 只保留可迁移占位路径。
- `scripts/install-scheduled-task.ps1` 只安装每天 9 点提醒任务。

## 引导深度思考

- 整理资料时问：这条内容属于生活 / 学习 / 工作哪一类？以后如何复用？
- 回顾知识时问：来源是否足够？有没有遗漏路径？
- 提取上下文时问：AI 需要哪些真实来源、边界和验收标准？
- 今日提醒时问：今天只推进哪 1-3 件事？

## 内容如何调用

- 日常使用先回顾，再提取 AI 上下文包。
- 需要长期沉淀时再整理成 Obsidian 新笔记。
- 旧资料不移动，先通过 `legacy-index` 建索引。
