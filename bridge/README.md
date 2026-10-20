# Codex 读取与模型桥接

本目录只负责两件事：通过已安装的官方桌面 MCP 服务读取线程；通过 `codex exec --ephemeral` 生成文字。它不写 Obsidian、不推进检查点、不创建持久对话、不向原对话发消息。

## Python 接口

```python
from bridge import NativeCodexBridge, CodexModel, BridgeError, turn_evidence, coverage_flags

with NativeCodexBridge() as native:
    recent = native.list_threads(limit=50)
    archived = native.list_archived_threads(limit=50, cursor=None)
    page = native.read_thread(
        "真实线程 ID", turn_limit=5, cursor=None, include_outputs=True,
        max_output_chars_per_item=20000,
    )
    # 原生结构保留：page["thread"], page["page"], page["turns"]。
    # page["page"]["nextCursor"] 交给下次 read_thread，不能自行解码或伪造。
    # 只有增量选择器确认要处理的轮次，才交给模型；reasoning 不作为证据。
    evidence = [turn_evidence(turn) for turn in page["turns"]]
    incomplete = coverage_flags(page)  # explicit truncation/error is partial

text = CodexModel().generate("本次任务和有界材料", timeout=300)
# generate 返回 str。需要用量/执行事件时使用 generate_result，返回 JSON 对象。
```

模型运行禁用 shell、apps、多代理、浏览器、图像和技能搜索，使用只读沙箱、never 审批、临时会话，不继承桌面 MCP 管道。请求通过 stdin 传递，不写入命令参数。原始 stdout/stderr、凭据和模型会话 ID 不暴露到返回结果。`on_event` 只报告模型真实开始与完成，不报告伪进度。

`BridgeError.code` 用于任务状态分类；不可把失败转换为空来源或“无新增”。常见代码：

| 错误 | 状态 |
|---|---|
| `native_context_missing` / `native_unavailable` | 原生来源未连接 |
| `native_disconnected` / `native_read_failed` / `native_call_failed` | 来源读取失败，保留检查点 |
| `native_timeout` | 本次来源未检查完整 |
| `model_unavailable` / `model_failed` / `model_timeout` | 总结失败，不登记成功 |
| `model_incomplete` / `model_tool_use` | 结果未验收，不登记成功 |

## 后台运行依赖

必需的是**字段**，此文档不保存实际值：

- `CODEX_APP_TOOLS_PIPE_PATH`：正在运行的 Codex 桌面原生服务连接。
- `CODEX_THREAD_ID`：真实的执行器调用上下文。MCP 通过 `_meta` 要求此字段；不能用随机线程 ID冒充。
- `CODEX_CLI_PATH`：模型 CLI。未显式设置时可尝试已安装 CLI。
- `CODEX_MCP_NODE_PATH`：可选 Node 路径；默认可回退系统 Node。
- `OBSIDIAN_CODEX_MCP_SERVER`：可选已安装官方 MCP 的 `server.mjs` 路径；默认从官方插件安装目录发现。

本机执行器由当前桌面环境启动时可以继承连接字段。也可将已验证的连接显式传入 `NativeCodexBridge(pipe_path=..., caller_thread_id=...)`。没有此上下文时不会猜测管道、扫描会话 JSONL/SQLite 或修改全局 MCP 配置。

桌面退出或重启可能使原管道失效；服务应显示来源未连接/读取失败，重新取得有效桌面连接后再试。当前桥接不能据此宣称 Windows 登录后、桌面未启动时仍可读取线程。

最近线程接口只支持最多 50 个非置顶线程，置顶完整返回；没有活跃列表分页参数。调用方必须据边界判断覆盖是否完整，不能将一次满页宣称为全账号完整检查。归档与轮次支持 `nextCursor` 分页。

原生 `read_thread` 可能截断过长项目或失败；本桥接保留原结构及错误，不替调用方声称完整。`coverage_flags(page)` 对任意层级的明确 `*truncat*` 标记、partial 状态、error、非完整 itemsView 和明确截断文字返回 `partial:true` 与字段位置；正常 `page.hasMore` 仅表示还需翻页，不自动等于内容截断。原生明确超限错误转为 `native_oversized`。增量算法应保留 `status/startedAt/completedAt/page/items` 和所有部分覆盖边界，只在笔记落盘、读回后 ack。

`turn_evidence()` 默认只提供用户与助手可见消息，排除 reasoning、内部摘要、工具命令和参数，对常见凭据格式做脱敏。必要时显式 `include_tool_results=True`，也只保留状态、退出码和结果文字等少量字段。不要把完整原生响应直接传入模型。

## JSON CLI

从项目根目录调用 `py -3 -X utf8 -m bridge`，stdin 为一个 JSON，请求支持：

```json
{"action":"list_threads","limit":50}
```

```json
{"action":"read_thread","threadId":"真实 ID","turnLimit":5,"cursor":null}
```

```json
{"action":"generate","prompt":"有界材料与输出要求","timeout":300}
```

只输出一个 JSON 对象。只读调用返回 `{"ok":true,"data":...}`；生成返回 `{"ok":true,"text":...,"usage":...,"events":...,"ephemeral":true}`。

## 验证

离线契约测试：`py -3 -X utf8 -m unittest discover -s bridge/tests -v`。

真实探针只读取小页线程并总结无敏感测试句子；正式增量整理不在本模块测试中执行。测试记录见 `verification.json`，不存储用户原始对话或凭据。
