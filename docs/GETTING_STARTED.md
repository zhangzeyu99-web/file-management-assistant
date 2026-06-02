# 快速上手

本地知识整理助手只保留三个真实操作：添加资料、搜索回顾、生成 AI 上下文包。

## 1. 启动

第一次使用可以先跑 demo 初始化：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-assistant.ps1 -Demo
```

这会创建 demo vault，并写入 `AI_IDENTITY.md`、`AI_COLLABORATION_RULES.md`、`AI_CONTEXT_BOUNDARY.md` 和 `Skills-SOP` 三主操作模板。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1
```

打开 `http://127.0.0.1:8765/`。

如果你已经把 `config.local.json` 改成真实 Obsidian 路径，可以安装可迁移 AI 身份文件和 SOP：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-assistant.ps1 -InstallPortableTemplates
```

## 2. 添加资料

- 粘贴一段文本，或粘贴真实本地文件 / 目录路径。
- 点击 `添加资料`。
- 结果会写入新的 Obsidian 整理记录。
- 如果路径下有可读文件，会为每个文件生成独立索引条目。
- 源文件不会被删除、移动、重命名或重写。

## 3. 搜索回顾

- 输入关键词或问题，例如 `运营sop`。
- 结果必须包含一句话答案、命中词、证据摘录和来源路径。
- 如果没有可靠证据，会显示未找到，不会用弱相关内容伪装答案。

## 4. 生成 AI 上下文包

- 输入当前任务。
- 先预览候选来源。
- 确认来源后生成 Markdown 和可复制 prompt。
- 如果已安装 `AI 身份文件`，prompt 会附带身份偏好和上下文边界摘要。
- 身份文件不替代证据；没有候选来源时仍不会生成上下文包。

## 验收标准

添加资料能真实入库；搜索回顾能找到已沉淀证据；AI 上下文包能从证据生成 prompt。
