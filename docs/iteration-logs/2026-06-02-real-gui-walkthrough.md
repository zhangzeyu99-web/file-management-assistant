# 2026-06-02 真实 GUI 走读迭代

## 本轮判断

之前的缺陷不是页面按钮完全无效，而是测试只证明“接口能返回”，没有证明“用户能沿着页面完成闭环”。本轮把测试合同改成真人路径：添加资料后能在 Obsidian 找到，搜索结果能加入上下文包，AI 上下文包能从已选证据生成。

## 迭代计划

### P0 真实闭环

- 添加资料：结果必须显示 `在 Obsidian 里怎么找`、整理记录、整理目录、文件索引目录。
- 搜索回顾：结果必须保留来源卡，并提供 `加入上下文包`。
- 生成 AI 上下文包：从搜索结果加入的来源必须显示 `已加入上下文包候选`，再确认生成 prompt。

### P1 测试合同

- GUI E2E 不只点按钮，还检查关键文案、结构化 `obsidian_locations`、候选来源篮和生成动作。
- 严格模式遇到缺失 Obsidian 找回、缺失 review-to-context、默认 JSON、弱结果卡都要失败。

### P2 后续产品缺口

- 给 extract 结果补“上下文包在哪里找”的同类位置字段。
- 给 organize 结果生成推荐检索词。
- 文件索引条目反链到本次整理记录，减少资料散落感。

## 已修复

- `scripts/gui-e2e-playwright.js` 新增 `obsidian_findability` 标志，检查 GUI 文案和后端结构化位置。
- `scripts/gui-e2e-playwright.js` 新增 `seeded_context_from_review` 标志，模拟用户从搜索证据点击 `加入上下文包`。
- E2E 现在会先生成“已选来源上下文包”，再跑原来的 preview/generate 流程。
- `docs/GUI_E2E_TESTING.md` 已把这些检查写入 harness contract。

## 验证记录

```powershell
python -X utf8 -m unittest tests.test_project_quality.ProjectQualityTests.test_gui_harness_verifies_local_target_workbench -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -StrictUx
```

结果：

- 静态测试通过。
- GUI E2E strict 通过。
- E2E 动作数：6。
- 机械失败：0。
- UX issue：0。
- `obsidian_findability`：true。
- `seeded_context_from_review`：true。
- `preview_before_generate`：true。

## 自查

| 问题 | 判断 | 证据 | 仍需改进 |
| --- | --- | --- | --- |
| 做到了视觉清晰阅读友好了吗？ | 部分通过 | 结果区已用可读卡片展示 Obsidian 找回和候选来源。 | 还要继续压缩重复产物卡。 |
| 做到了总结归纳到位，没有废话不遗漏关键信息了吗？ | 部分通过 | E2E 强制检查找回路径、候选来源和 prompt 生成。 | extract 结果还缺独立找回目录说明。 |
| 发给别人能看懂吗？ | 部分通过 | 用户路径可描述为添加、搜索、加入上下文包、生成。 | README 还需要同步最新 E2E 走读说明。 |
| 传到 Codex 指引性足够吗？ | 通过 | 结构化 `obsidian_locations` 和 E2E JSON 都可被 Codex 读取。 | 后续可把测试报告自动入库成知识卡。 |
| GUI 双向交互方便吗？ | 部分通过 | 搜索来源能反向加入上下文包，已不只是展示。 | 打开路径仍依赖本地后端能力和 OS 行为。 |
| 信息内容容易编辑吗？ | 通过 | 产物仍是 Markdown、路径和 prompt。 | 无。 |
| 展示的方式足够方便吗？ | 部分通过 | 长路径用卡片和 chip，默认不显示 JSON。 | 来源多时需要更好的折叠和排序。 |
| 信息集关联有做吗？ | 部分通过 | 搜索证据和 AI 上下文包已打通。 | 文件索引与整理记录的反链还要加强。 |
| 能让人发散性思考吗？ | 部分通过 | 搜索证据可以继续生成 AI prompt。 | 还缺相近关键词和推荐追问。 |

## 下一轮建议

先补 extract 找回位置，再做文件索引反链和推荐检索词。不要恢复知识流、提醒、诊断入口到首页，避免三主操作再次发散。
