# 产品化 UI 研究摘记

本项目参考成熟文件管理和知识管理工具的共性做法，但只落到三个主操作：添加资料、搜索回顾、生成 AI 上下文包。当前不再把首页做成内容流，也不把低频诊断工具放回主线。

## 可复用经验

- 文件要有归属。Dropbox 的组织建议强调清晰层级、命名规则和标签；本项目不移动源文件，但 `添加资料` 结果必须给出 Obsidian 整理记录、文件索引目录和建议归属。
- 找回要靠搜索。Google Drive 和 Dropbox 都把搜索、筛选、最近项作为找回主路径；本项目的 `搜索回顾` 必须基于关键词或问题返回证据来源，不能只展示最近报告。
- 页面要先讲清用途。OpenClaw 101 这类知识站点的可取之处是首屏定位清楚；本项目只保留产品名、一句话定位、安全边界和三个主操作入口。
- 结果要像详情面板。成熟文件管理器会给出选中项的上下文、状态和可执行操作；本项目结果卡固定展示“答案是什么 / 证据在哪 / 产物在哪 / 下一步”。
- 安全边界必须常驻。用户面对文件管理工具时最担心误删、误移、误改；本项目在首屏、结果区和文档里持续强调默认不删除、不移动、不重命名、不重写源文件。

## 落地到当前界面

- 首屏采用深色 hero：产品名、一句话定位、安全边界、三个主操作入口。
- 三个操作区按锚点分离：`#organize`、`#review`、`#extract`，每区只保留一个轻量输入、一个主按钮和一个结果卡。
- 文件区保留在整理区内：路径粘贴、文件选择和拖放仍支持；真实扫描本机目录仍以完整路径为准。
- `添加资料` 结果必须显示 `在 Obsidian 里怎么找` 和 `推荐搜索词`；点击推荐词要能直接触发 `搜索回顾`。
- `搜索回顾` 结果默认最多显示 4 条强证据；每条证据包含标题、命中词、相关原因、摘录、来源路径和操作。
- `生成 AI 上下文包` 先预览候选来源，确认后才写入 Markdown、Obsidian 笔记和可复制 prompt。

## 不做的事

- 不新增云盘式批量移动、删除、重命名。
- 不把 GUI 做成伪控制台。
- 不把高级诊断重新放回主线。
- 不把提醒做成核心入口。
- 不恢复首页内容流或旧资料浏览入口。

## 参考来源

- Google Drive Help: search and filter files with search terms and filter chips. <https://support.google.com/drive/answer/2375114>
- Dropbox Help: folder hierarchy, naming conventions and tags for file organization. <https://help.dropbox.com/organize/organize-folders>
- Dropbox Learn: sorting and view options are safe ways to explore content without moving it. <https://learn.dropbox.com/self-guided-learning/dropbox-fundamentals-course/how-to-organize-in-dropbox>
- Fluent 2 Design System: spacing and layout should establish visual hierarchy and relationships. <https://fluent2.microsoft.design/layout>
- OpenClaw 101: site-style knowledge home with clear hero and learning path. <https://openclaw101.dev/>
