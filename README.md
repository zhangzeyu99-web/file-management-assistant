# 个人知识工作台 · Obsidian

从已整理的资料找回做法、核对来源、准备下一次工作，并只处理新增文件与对话续聊。此仓库的 `main` 现为 v0.2 新版；旧实现保存在 Git 历史与 `legacy-v0.1-before-workspace` 标签中。

## 先做什么

- **找做法**：输入“项目名 + 具体问题”，先看回答，再点来源核对。
- **继续工作**：把相关资料加入已选集合，填写本次目标，生成并复制接续内容。
- **收录资料**：上传实际文件或粘贴正文；成功落盘后可直接阅读和检索。
- **检查并更新**：只处理新文件、新文档入口和线程新完成轮次。失败只重试未完成部分。

[使用说明](USER_GUIDE.md) · [迁移到另一台电脑](docs/MIGRATION.md) · [项目状态与维护](PROJECT.md) · [版本记录](CHANGELOG.md)

## 能迁走什么

整理好的 Markdown 和附件可以原样复制，检索索引在新机重建，不需要重新调用模型总结。迁移工具同时带走增量检查点，映射新旧磁盘路径，防止旧文件因为换盘符被当成新增。

代码仓库不包含个人知识库、运行记录或凭据。仅克隆代码不会获得任何人的笔记。迁移包保存在自己的设备中，具体导出、导入与验收见迁移说明。

## Windows 本机启动

已验证环境为 Python 3.14、Node.js 22.22。需要 Git。AI 动作还需要已登录的 Codex CLI；Codex 对话来源需要从桌面应用的当前工具上下文启动执行器。

```powershell
git clone https://github.com/zhangzeyu99-web/file-management-assistant.git obsidian-workspace
Set-Location obsidian-workspace
py -3 -m pip install -r requirements.txt
Set-Location web
npm ci
Set-Location ..
```

先按 [迁移说明](docs/MIGRATION.md) 导入自己的笔记与已有 v1 检查点，获得私有配置，然后启动：

```powershell
.\start.ps1 -Config "你的迁移目录\config.local.json"
```

默认网页为 `http://127.0.0.1:5174/`，API 为 `127.0.0.1:8767`。启动脚本后台运行服务，不自动发起整理。项目目录的 `config.local.json` 可作为默认配置；字段示例见 [config.example.json](config.example.json)。不会自动创建空检查点或重跑历史全量。

## 检索与同步

检索使用 Markdown 段落索引、项目别名、关键词和问题意图排序；默认使用前六条可见证据生成回答。有相关短笔记的结果表格被漏词时，以完整笔记补充证据。未加入向量搜索，也不自行联网补答案。未找到只说明现有笔记缺少依据，不代表事情没有做过。

线上是经过登录保护的可读副本和持久任务队列，本机执行器主动领取任务。电脑离线时，线上可以阅读已同步资料，新任务等待本机恢复。启用线上需要自己的部署、服务授权和登录；仓库不会绑定到作者的私人站点。部署说明见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

正文提取支持文本、Markdown、DOCX 和有文字层的 PDF；飞书新增入口当前只登记元数据。图片、音视频和工作簿应先走对应专项处理流程，再收录文本结果。原生线程超限、读取不完整和运行中轮次均保留未完成状态。

## 开发与验证

```powershell
py -3 -X utf8 -m unittest discover -s tests -q
py -3 -X utf8 -m unittest discover -s bridge/tests -q
Set-Location web
npx tsc --noEmit
npm run build
```

`tests/ui_server.py` 提供隔离验收入口，不使用生产检查点。模型真实调用和个人资料验收另在私有环境执行，不能由无凭据 CI 代替。发布与回退规则见 [PROJECT.md](PROJECT.md)。

许可证：[MIT](LICENSE)。
