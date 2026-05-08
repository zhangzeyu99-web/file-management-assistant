# 产品化 UI 研究摘记

本轮调整参考成熟文件与知识管理工具的共性做法，但只落到本项目的四个核心能力：整理、回顾、提取、提醒。

## 可复用经验

- 文件要有指定归属。Dropbox 的组织建议强调为文件建立清晰层级、命名规则和标签；本项目不移动源文件，但整理结果必须给出建议归属和 Obsidian 新记录。
- 搜索不能只靠目录浏览。Google Drive 和 Dropbox 都把搜索、筛选、最近项、标签作为找回文件的主路径；本项目的“回顾”和“提取”应先让用户输入关键词或任务，再返回来源。
- 留白和分组比堆按钮更重要。Fluent 的布局原则强调用间距建立关系和重点；首页只保留四张主卡，旧能力折叠到高级/诊断。
- 结果要像详情面板。成熟文件管理器会给出选中项的上下文、状态和可执行操作；本项目结果卡固定展示“做了什么 / 来源是什么 / 产物在哪 / 下一步”。
- 安全边界必须常驻。用户面对文件管理工具时最担心误删、误移、误改；本项目在首屏、结果区和文档里持续强调默认不删除、不移动、不重命名、不重写源文件。

## 落地到当前界面

- 首屏增加 `统一入口`、`搜索/筛选`、`来源可追溯`、`最近来源` 四个产品化原则。
- 主输入区增加快速场景，减少用户不知道从哪开始的问题。
- 文件区保留路径粘贴、文件选择和拖放，但明确真实扫描本机目录仍以完整路径为准。
- 结果卡从摘要文本升级为四格详情面板，便于用户判断下一步是否要打开产物、复制 prompt 或继续补充资料。
- 右侧状态从“最近动作”改为“最近来源 / 最近动作”，强化这是给后续回顾和 AI 取用的上下文资产。

## 不做的事

- 不新增云盘式批量移动、删除、重命名。
- 不把 GUI 做成伪控制台。
- 不把高级诊断重新放回主线。
- 不把提醒做成外部通知中心；第一版仍是本地计划任务和 Obsidian 记录。

## 参考来源

- Google Drive Help: search and filter files with search terms and filter chips. <https://support.google.com/drive/answer/2375114>
- Dropbox Help: folder hierarchy, naming conventions and tags for file organization. <https://help.dropbox.com/organize/organize-folders>
- Dropbox Learn: sorting and view options are safe ways to explore content without moving it. <https://learn.dropbox.com/self-guided-learning/dropbox-fundamentals-course/how-to-organize-in-dropbox>
- Fluent 2 Design System: spacing and layout should establish visual hierarchy and relationships. <https://fluent2.microsoft.design/layout>
