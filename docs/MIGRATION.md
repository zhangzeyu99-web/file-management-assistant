# 把知识工作台迁到另一台 Windows 电脑

迁移分为代码、个人资料、重新授权三部分。GitHub 提供代码；私有 ZIP 提供笔记和增量记录；登录和机器凭据在新机重新配置。克隆仓库后不会自动获得个人资料，也不会自动运行全量整理。

## 旧电脑：导出

先等当前任务结束，再停止本机执行器。保留原库不动，先在另一目录验证恢复。导出期间也不要编辑 Obsidian 笔记。

```powershell
.\stop.ps1 -Config "D:\KnowledgeData\config.local.json"
py -3 -X utf8 scripts/migrate_workspace.py export --config "D:\KnowledgeData\config.local.json" --output "E:\PrivateBackup\knowledge.zip"
```

如果当前电脑仍使用旧版兼容配置，可以省略 `--config` 和 `-Config`。迁移包必须在笔记库及运行数据目录之外，已有 ZIP 不会覆盖。导出后可用原配置重新运行 `start.ps1`。

包里包含：

- Obsidian 库内可迁移的笔记和附件，保留正文原始字节、修改时间与相对链接。
- 完整 v1 增量检查点，包括已处理文件、线程轮次、失败和待处理状态。
- 已完成回执、来源检查记录，以及检查点引用的私有检查说明。
- 从旧基线提炼出的时间边界与视频来源配置，使新机不依赖旧项目目录。

不会携带凭据、原始 Codex 会话、运行锁、待执行队列、上传暂存、模型缓存、任务历史和 Obsidian 插件设置。软件安装包（APK、EXE、MSI、DMG、ISO、APPX、MSIX）明确排除并报告数量；需要时另行复制。ZIP/RAR 等压缩附件继续保留。原始扫描目录中的文件也不包含在包里，需要另行复制到新位置；仅阅读已整理笔记不需要这些源文件。

## 新电脑：安装和指定新路径

按仓库 README 安装 Python、Node 和项目依赖。先检查迁移包中的旧路径：

```powershell
py -3 -X utf8 scripts/migrate_workspace.py inspect --bundle "E:\PrivateBackup\knowledge.zip"
```

新建一个仅保存在自己电脑的 `paths.local.json`，为旧路径填写新路径，例如：

```json
[
  {"from": "D:\\OldVault", "to": "E:\\Knowledge\\Vault"},
  {"from": "D:\\OldRuntime", "to": "E:\\Knowledge\\Runtime"},
  {"from": "D:\\OldCheckpoint\\state.json", "to": "E:\\Knowledge\\Runtime\\state.json"},
  {"from": "D:\\OldSources", "to": "E:\\Knowledge\\Sources"}
]
```

以上只是示例，必须按包中的 `config` 填写。所有配置目录、文件监控根与记忆根都需要映射；可以用较上层目录映射其子目录，也可用更具体的映射覆盖。运行数据目录必须为空，配置和检查点必须是新文件。已存在的笔记只有正文完全相同时才保留，不会覆盖人工修改。

先试导入，再正式导入：

```powershell
py -3 -X utf8 scripts/migrate_workspace.py import --bundle "E:\PrivateBackup\knowledge.zip" --mappings "E:\Knowledge\paths.local.json" --config-out "E:\Knowledge\config.local.json" --dry-run
py -3 -X utf8 scripts/migrate_workspace.py import --bundle "E:\PrivateBackup\knowledge.zip" --mappings "E:\Knowledge\paths.local.json" --config-out "E:\Knowledge\config.local.json"
.\start.ps1 -Config "E:\Knowledge\config.local.json" -Check
.\start.ps1 -Config "E:\Knowledge\config.local.json"
```

新旧路径映射也会作用于检查点中的绝对文件键，因此已经总结的来源不会只因换盘符再次入队。没有映射的旧历史文件键会保留并报告数量；它们不自动变成新的扫描目录。Markdown 正文中写过的旧绝对来源路径会原样保留，需从新位置查找原文件；站内笔记阅读不受影响。

## 恢复后核对

打开首页，查找几个熟悉的问题，打开来源确认正文；再检查配置里的扫描目录都已复制或明确调整。检索索引会从现有笔记重建，不会重新调用模型写摘要。尚未完成的事项继续保留，迁移不将它们标记成成功。

继续 AI 整理需要在新机重新登录 Codex CLI。读取 Codex 对话还要求新机能访问相应对话，并从 Codex Desktop 当前会话的原生工具上下文启动；迁移包不复制旧对话数据库，也不保证另一台电脑自动拥有旧对话。飞书来源需要重新配置自己的授权。

导入默认关闭线上连接。需要接回同一线上队列时，先停用旧机执行器，再按 [部署说明](DEPLOYMENT.md) 配置新机服务令牌。不要让两台电脑同时写同一知识库和检查点。

## 验证范围

迁移测试覆盖异目录恢复、路径变化后跳过已总结来源、保留人工正文与待处理状态、冲突拒绝和失败回滚。本版已用真实资料完成独立目录恢复，核对全部笔记与附件的原始字节、修改时间、增量记录和多类问题的检索顺序，均一致。它证明数据可搬迁，但不代替第二台实体电脑的安装、登录和原生对话可用性验证。
