# 当前迭代计划：三操作闭环产品缺陷修复

## 当前判断

本项目继续收敛为三件事：

- 添加资料：真实入库，写 Obsidian 新记录和每文件索引。
- 搜索回顾：从已沉淀证据里给出答案、命中词、摘录和来源路径。
- 生成 AI 上下文包：从确认来源生成可复制 prompt 和 Markdown。

不再恢复知识流首页、提醒、诊断按钮、旧文件管理入口或伪控制台。

## 本轮已修复的产品缺陷

### 1. 真实 vault 连续搜索过慢

问题：真实配置下，搜索回顾每次都重新扫描大目录；`Documents` 这类 watch root 有大量无关文件，导致单次检索约 14-16 秒。

修复：

- watch root 只枚举 `*.md` 和 `*.txt`，不再 `rglob("*")` 全量扫目录。
- `review` 索引增加进程内缓存。
- `organize` 写入新资料后主动清空缓存，保证新资料能被搜到。

验收：

- 首次真实搜索约 6.6 秒。
- 同一进程连续搜索约 0.1-0.6 秒。
- 单元测试覆盖扩展名扫描和缓存失效。

### 2. 首次搜索没有可见等待状态

问题：GUI 点击搜索后只禁用按钮，没有说明正在建立本地索引。用户会误以为点击无效或页面卡住。

修复：

- 点击 `搜索回顾` 后立即显示 `正在建立索引`。
- 文案说明：首查会建立本地索引，后续连续搜索复用缓存。
- `添加资料`、`生成 AI 上下文包`、`检查本地目标` 也有对应处理中状态。

验收：

- GUI 静态测试检查 `renderPendingAction`、`正在建立索引` 和 `首查会建立本地索引`。
- 默认不显示 JSON，不显示黑色控制台。

### 3. 打开来源会覆盖当前搜索结果

问题：用户点击 `打开来源` 时，页面可能用 `open-path` 返回结果覆盖原搜索证据，导致用户失去刚才的上下文。

修复：

- `打开来源` 改为行内状态反馈。
- 打开成功或失败只更新顶部提示，不覆盖证据卡。
- 搜索结果、来源路径、加入上下文包按钮都保留。

验收：

- GUI 静态测试检查 `openPathWithoutReplacingResult` 和 `showInlineStatus`。

### 4. 加入上下文包没有明确反馈

问题：用户从搜索结果点击 `加入上下文包` 后，只滚动到提取区，看不清是否真的选中了来源。

修复：

- 点击后在 `生成 AI 上下文包` 区显示 `已加入上下文包候选`。
- 明确展示候选来源路径。
- 直接给出 `确认生成上下文包` 按钮。

验收：

- GUI 静态测试检查 `renderSeededExtractSource`、`已加入上下文包候选` 和 `确认生成上下文包`。

### 5. 活跃产品文档仍残留旧方向

问题：README 和 GUI 已经收敛到三操作闭环，但部分仍在维护和引用的产品文档还残留旧的首页内容流、资料浏览入口和卡片浏览叙事。继续保留这些表达，会让后续迭代误把产品拉回“展示很多内容”的方向。

修复：

- `docs/PRODUCT_UI_RESEARCH.md` 改成三操作 UI 研究摘记，强调首屏只讲用途、安全边界和三个入口。
- `docs/PRODUCT_RETROSPECTIVE_AND_NEXT_PLAN.md` 改成三操作闭环迭代计划，不再把内容浏览作为下一阶段主线。
- `docs/KNOWLEDGE_DISPLAY_METHOD.md` 改成搜索结果和上下文包的展示方法，不再按列表卡片浏览设计。
- `tests/test_project_quality.py` 扩大活跃文档质量检查，防止旧方向重新进入公共产品文档。

验收：

- 目标质量测试 `test_public_docs_do_not_promote_knowledge_feed_as_core_flow` 通过。
- 活跃产品文档继续只主推 `添加资料 / 搜索回顾 / 生成 AI 上下文包`。
- 旧内容浏览、提醒、诊断和伪控制台只留在历史资料或维护语境，不回到用户主线。

### 6. GUI 服务端仍保留旧内容流后端

问题：公共界面已经不展示内容流，但 `gui_server.py` 仍保留旧的内容流构建、卡片详情和关联推荐逻辑，`tests/test_gui_server.py` 也继续测试这些旧函数。这会让项目看起来已经收敛，实际代码仍背着一套不再使用的产品形态。

修复：

- 删除 `gui_server.py` 中旧内容流构建函数、卡片详情函数、主题关联规则和相关导入。
- 删除只验证旧内容流的 GUI 单元测试。
- `scripts/gui-human-usability.js` 改为检查三个主入口，不再模拟跳转到旧内容浏览区。
- 新增质量测试，禁止 GUI 服务端和真人走读脚本继续保留旧内容流后端和选择器。

验收：

- `test_gui_server_does_not_keep_deprecated_knowledge_feed_backend` 通过。
- GUI 服务端测试通过，确认三主操作、路径检查、打开来源和降级入口仍可用。
- 残留扫描不再发现旧内容流后端函数、旧锚点或旧卡片选择器。

### 7. 真人式 GUI QA 没有按证据闭环走读

问题：真人式 GUI QA 脚本虽然会点击页面，但之前用的是过宽英文查询，并且要求所有结果卡都必须有操作按钮。这样会产生两类问题：一是严格搜索正常返回“未找到”时被误判为失败；二是脚本没有证明“添加资料后，搜索能找到已沉淀证据，再生成 AI 上下文包”这个核心闭环。

修复：

- 搜索问题改为本轮 fixture 能提供证据的 `Evidence-based review`。
- 上下文包请求改为 `Evidence-based review context packaging`，让提取动作基于同一组证据。
- `.result-actions` 只在需要下一步操作的结果中强制检查，不再要求无匹配或路径检查也必须提供操作按钮。
- 未命中状态允许当前严格搜索文案 `已整理资料中没有命中`，避免把正确拒绝弱相关结果误报为失败。
- 严格模式继续保留录屏、截图、网络事件、控制台事件和可读 summary。

验收：

- 目标质量测试先失败后通过，锁定脚本必须使用证据驱动查询。
- 真人式 GUI QA 严格模式通过：actions=6，mechanics_failures=0，ux_issues=0，console=0。
- 输出保留视频、最终截图、JSON 和 Markdown summary，方便下一轮复盘。

### 8. 真实查询 QA 缺失，且过程日志会污染搜索结果

问题：GUI 与 isolated E2E 已能证明三操作按钮可走通，但真实中文查询集没有固定脚本。手工跑 `Obsidian助手` 时发现，最新迭代记录会因为包含测试关键词而排到首条，压过真正的学习指南；索引还会把同一文件从 vault 和 watch root 重复加入，浪费索引容量并污染排序。

修复：

- 新增 `scripts/run-real-query-qa.py`，固定跑 `运营sop`、`github仓库`、`简历线程`、`Obsidian助手`、无匹配查询。
- QA 同时验证 `review` 和 `extract preview`：必须有命中词、证据摘录、来源路径；preview 不写上下文包文件。
- `build_review_index_uncached` 增加全局路径去重，同一文件只入索引一次。
- 普通知识查询下降权 `迭代记录` / `iteration-logs` / `真人式 GUI QA` 来源；如果用户查询本身包含迭代、测试、QA、harness、验证等词，则不降权。
- 教程型来源在标题或路径命中全部查询词时加权，避免日记里的 wiki 链接压过实际指南。
- `verify-harness.ps1` 已接入 `real_query_qa`；有 `config.local.json` 时自动跑真实查询 QA。

验收：

- RED：`Obsidian助手` 首条曾为 `2026-06-02 真人式 GUI QA 证据闭环`。
- GREEN：`Obsidian助手` 首条变为 `2026-04-27 Obsidian 助手学习指南`。
- 真实查询 QA 通过：5/5 passed。
- 总 harness 通过，并包含 `real_query_qa`。

### 9. 真实 GUI 中文查询缺少逐项验收

问题：后端真实查询 QA 通过，不等于用户在网页里能看懂、能点击、能继续提取上下文。之前真实页面暴露过“结果看不懂、关键词不相关、点击无反应”的问题，但没有单独的 GUI 查询验收。

修复：

- 新增 `scripts/gui-real-query-qa.js`，直接在 GUI 中输入 `运营sop`、`github仓库`、`简历线程`、`Obsidian助手` 和动态不存在词。
- 新增 `scripts/run-real-query-gui-qa.ps1`，启动真实本地 GUI，保存 JSON、Markdown 和截图。
- `verify-harness.ps1` 接入 `real_query_gui_qa`；有 `config.local.json` 时自动跑，缺少本地 vault 配置时跳过。
- GUI QA 只执行 `review` 和 `extract preview`，不生成上下文包，不改源文件。

验收：

- 每个命中案例必须在页面里看到一句话答案、命中证据、命中词、证据摘录和来源路径。
- `extract preview` 必须复用搜索回顾的首条证据，且不写 artifacts。
- 无匹配查询必须显示未完成，不显示伪来源。

已验证：

- RED：首次真实 GUI 查询 5 个案例只有 1 个通过，失败集中在提取区没有复用搜索回顾首条证据。
- GREEN：`run-real-query-gui-qa.ps1 -StrictUx` 通过，5/5 passed，`ux_issues=0`，`mechanics_failures=0`，`console=0`。

### 10. 提取区被“生成 AI 上下文包”通用词带偏

问题：用户在提取区输入 `为“github仓库”生成 AI 上下文包` 时，后端会把 `AI`、`上下文` 也当作检索词，导致首选来源偏向泛上下文包或测试记录，而不是搜索回顾刚找到的证据。

修复：

- 新增 `extract_search_query()`，把 `为“X”生成 AI 上下文包`、`为“X”打包上下文` 等表达规范化为检索主题 `X`。
- `request` 保留完整用户任务，`query` 只用于证据检索和排序。
- 正常业务未命中 `status=not_found` 改为 HTTP 200 + `ok=false`，避免浏览器控制台把“未找到”当资源错误。
- 真人 GUI 脚本同步把 no-match 预期改为 200 + `ok=false`。

验收：

- 单测覆盖：`extract preview` 对 `为“github仓库”生成 AI 上下文包` 必须复用 `review("github仓库")` 的首条证据。
- GUI 真实查询覆盖：`运营sop`、`github仓库`、`简历线程`、`Obsidian助手` 的 preview 首条必须复用 review 首条。
- 未命中结果不制造 console error。

## 下一轮优先级

### P0：真实 GUI 走读

目标：用真实页面跑三操作，不只验证接口。

状态：已完成本轮修复。真人式 GUI QA 现在使用本轮整理 fixture 的证据词走读，而不是用宽泛问题制造假失败。

验收：

- 搜索 `运营sop`、`github仓库`、`简历线程`、`Obsidian助手`、不存在关键词。
- 每个命中结果必须能看到答案、命中词、证据摘录、路径。
- 打开来源不覆盖搜索结果。
- 加入上下文包后能看到已选来源，并能生成 prompt。

已验证：

- 质量测试覆盖真人式 GUI QA 脚本必须使用证据驱动查询。
- `run-gui-human-usability.ps1 -StrictUx` 覆盖添加资料、路径检查、搜索命中、搜索未命中、上下文包预览和生成。
- `scripts/run-real-query-qa.py` 覆盖真实中文查询集，防止迭代日志、QA 记录和重复索引污染搜索首条结果。

### P1：真实 Obsidian 可找回路径

目标：用户打开 Obsidian 后能快速找到工具写入的笔记。

状态：已完成第一版。`添加资料` 结果现在返回 `debug.obsidian_locations`，GUI 会展示“在 Obsidian 里怎么找”，README、快速上手和 GUI 说明已写明默认目录。

验收：

- README 和 GUI 使用说明写清楚默认写入目录。
- `添加资料` 结果明确显示 Obsidian 笔记路径、文件索引目录、manifest。
- `搜索回顾` 结果中的路径可以复制，并能作为 AI 上下文包来源。

已验证：

- 后端测试覆盖 `organize` 返回 vault、整理记录、整理目录、文件索引目录和 search hint。
- GUI 静态测试覆盖“在 Obsidian 里怎么找”、整理记录、整理目录、文件索引目录。

### P2：搜索展示继续减噪

目标：搜索结果更像知识卡，不像接口日志。

状态：已完成第一版。GUI 现在默认只展示前 4 条强证据，更多来源折叠成提示，不再把 6 条来源一起堆在结果区。

验收：

- 首屏最多展示 3-5 条强相关证据。已实现：默认展示 4 条。
- 每条证据固定结构：标题、命中词、为什么相关、摘录、来源路径、操作。
- 弱相关或泛索引不能排在强证据前。

已验证：

- GUI 静态测试覆盖 `sources.slice(0, 4)`、`data-source-evidence-card`、`hiddenSourceCount` 和 `source-more-card`。
- E2E 报告字段 `review_source_cards_visible_max_four=true`。
- `run-gui-e2e.ps1 -StrictUx` 通过，`mechanics_failures=0`，`ux_issues=0`。

### P3：教程资料包不再误导到旧知识流

目标：新手导入 NotebookLM 或阅读 PDF 时，只学到当前三步闭环，不再看到旧知识流、提醒或四入口叙事。

状态：已完成第一版。`scripts/generate-guidebook-assets.py` 已改为三步闭环教程，并重新生成 7 页 PNG 与 PDF。

验收：

- 教程脚本必须包含添加资料、搜索回顾、生成 AI 上下文包、推荐搜索词、最多 4 条强证据、加入上下文包。
- 教程脚本不得再包含 `知识流怎么用`、`向下看知识流`、`四入口`、`需要提醒时`。
- `docs/guidebook/README.md` 页码说明与新教程一致。

## 暂不做

- 不恢复提醒功能。
- 不恢复知识流首页。
- 不接外部大模型或向量库。
- 不移动、删除、重命名源文件。
- 不把个人 Obsidian vault 上传到公开仓库。
