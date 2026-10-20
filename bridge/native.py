from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from typing import Any


READ_TOOLS = frozenset({"list_threads", "list_archived_threads", "read_thread"})
HIDDEN_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": str(self)}}


def discover_mcp_server() -> Path:
    explicit = os.environ.get("OBSIDIAN_CODEX_MCP_SERVER")
    if explicit:
        server = Path(explicit)
        if server.is_file():
            return server
        raise BridgeError("native_unavailable", "配置的 Codex 原生工具服务不存在。")
    root = Path.home() / ".codex/plugins/cache/openai-bundled/codex-app-tools"
    candidates = [path for path in root.glob("*/server.mjs") if path.is_file()]
    if not candidates:
        raise BridgeError("native_unavailable", "未找到已安装的 Codex 原生工具服务。")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def node_command() -> str:
    for key in ("CODEX_MCP_NODE_PATH", "CODEX_BROWSER_USE_NODE_PATH"):
        value = os.environ.get(key)
        if value and Path(value).is_file():
            return value
    value = shutil.which("node")
    if not value:
        raise BridgeError("native_unavailable", "未找到原生工具需要的 Node 运行时。")
    return value


class StdioRpc:
    """A small line-delimited JSON-RPC client for the installed MCP server."""

    def __init__(self, command: list[str], *, env: dict[str, str], timeout: float = 60):
        self.timeout = timeout
        self._queue: queue.Queue[Any] = queue.Queue()
        self._lock = threading.Lock()
        self._next_id = 1
        self._closed = False
        try:
            self.process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, encoding="utf-8", text=True,
                env=env, creationflags=HIDDEN_WINDOW,
            )
        except OSError as exc:
            raise BridgeError("native_unavailable", "无法启动 Codex 原生工具服务。") from exc
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            for line in self.process.stdout:
                if line.strip():
                    try:
                        self._queue.put(json.loads(line))
                    except ValueError:
                        self._queue.put(BridgeError("protocol_error", "原生工具返回了无效 JSON。"))
        finally:
            self._queue.put(BridgeError("native_disconnected", "Codex 原生工具连接已关闭。"))

    def _write(self, message: dict[str, Any]) -> None:
        if self._closed:
            raise BridgeError("native_disconnected", "Codex 原生工具连接已关闭。")
        try:
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise BridgeError("native_disconnected", "Codex 原生工具连接已关闭。") from exc

    def notify(self, method: str) -> None:
        self._write({"jsonrpc": "2.0", "method": method})

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            deadline = time.monotonic() + self.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.close()
                    raise BridgeError("native_timeout", "原生工具读取超时；本次来源未检查完成。")
                try:
                    response = self._queue.get(timeout=remaining)
                except queue.Empty:
                    self.close()
                    raise BridgeError("native_timeout", "原生工具读取超时；本次来源未检查完成。")
                if isinstance(response, BridgeError):
                    raise response
                if response.get("id") != request_id:
                    # Notifications do not complete a request.
                    continue
                if "error" in response:
                    raise BridgeError("native_call_failed", "Codex 拒绝原生工具请求，请检查桌面连接和调用上下文。")
                return response.get("result", {})

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()


def decode_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("isError"):
        detail = " ".join(str(item.get("text", "")) for item in result.get("content", []))
        if re.search(r"too (?:large|long)|oversized|exceed.{0,35}(?:limit|size)|超限|超过.{0,12}限制", detail, re.I):
            raise BridgeError("native_oversized", "该线程超过原生读取限制；保留部分覆盖及续读边界。")
        raise BridgeError("native_read_failed", "原生来源读取失败；请保留检查点并稍后重试。")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for item in result.get("content", []):
        if item.get("type") != "text":
            continue
        try:
            value = json.loads(item["text"])
        except (ValueError, KeyError):
            continue
        if isinstance(value, dict):
            return value
    raise BridgeError("protocol_error", "原生工具没有返回结构化读取结果。")


class NativeCodexBridge:
    """Only the three public, read-only desktop history tools are exposed.

    The desktop pipe and caller thread are connection context, not credentials.
    No history database, rollout JSONL, or private app API is accessed.
    """

    def __init__(
        self, *, pipe_path: str | None = None, caller_thread_id: str | None = None,
        server_path: str | Path | None = None, timeout: float = 60,
    ):
        self.pipe_path = pipe_path or os.environ.get("CODEX_APP_TOOLS_PIPE_PATH")
        self.caller_thread_id = caller_thread_id or os.environ.get("CODEX_THREAD_ID")
        if not self.pipe_path or not self.caller_thread_id:
            raise BridgeError(
                "native_context_missing",
                "需要本机 Codex 桌面的原生连接和真实调用线程上下文；当前来源未连接。",
            )
        env = dict(os.environ)
        env["CODEX_APP_TOOLS_PIPE_PATH"] = self.pipe_path
        env["CODEX_APP_TOOLS_DEFERRED"] = "1"
        self.rpc = StdioRpc(
            [node_command(), str(server_path or discover_mcp_server())],
            env=env, timeout=timeout,
        )
        try:
            self.rpc.request("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "obsidian-workspace-readonly", "version": "1.0"},
            })
            self.rpc.notify("notifications/initialized")
            schema = self.rpc.request("tools/list", {})
            available = {item["name"] for item in schema.get("tools", [])}
            if not READ_TOOLS.issubset(available):
                raise BridgeError("native_incompatible", "已安装的原生工具缺少所需的只读接口。")
        except BaseException:
            self.close()
            raise

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in READ_TOOLS:
            raise BridgeError("action_not_allowed", "知识工作台只允许原生线程读取。")
        result = decode_tool_result(self.rpc.request("tools/call", {
            "name": name, "arguments": arguments,
            "_meta": {
                "openai/threadId": self.caller_thread_id,
                "openai/toolCallId": "obsidian-read-" + str(uuid.uuid4()),
            },
        }))
        expected = ("turns",) if name == "read_thread" else ("threads",)
        if not all(isinstance(result.get(key), list) for key in expected):
            raise BridgeError("protocol_error", "原生工具返回缺少预期数据；不能视为无新增。")
        if name == "read_thread" and not all(isinstance(result.get(key), dict) for key in ("thread", "page")):
            raise BridgeError("protocol_error", "原生轮次返回缺少分页或线程元数据。")
        return result

    def list_threads(self, limit: int = 50) -> dict[str, Any]:
        if not 1 <= limit <= 50:
            raise BridgeError("invalid_input", "最近线程页大小应为 1 到 50。")
        return self.call("list_threads", {"limit": limit})

    def list_archived_threads(
        self, *, limit: int = 50, cursor: str | None = None, host_id: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 50:
            raise BridgeError("invalid_input", "归档线程页大小应为 1 到 50。")
        args: dict[str, Any] = {"source": "codex", "limit": limit}
        if cursor:
            args["cursor"] = cursor
        if host_id:
            args["hostId"] = host_id
        return self.call("list_archived_threads", args)

    def read_thread(
        self, thread_id: str, *, cursor: str | None = None, turn_limit: int = 5,
        host_id: str | None = None, include_outputs: bool = True,
        max_output_chars_per_item: int = 20000,
    ) -> dict[str, Any]:
        if not thread_id or not 1 <= turn_limit <= 10 or not 0 <= max_output_chars_per_item <= 20000:
            raise BridgeError("invalid_input", "线程 ID、页大小或输出长度无效。")
        args: dict[str, Any] = {
            "threadId": thread_id, "turnLimit": turn_limit,
            "includeOutputs": include_outputs,
            "maxOutputCharsPerItem": max_output_chars_per_item,
        }
        if cursor:
            args["cursor"] = cursor
        if host_id:
            args["hostId"] = host_id
        return self.call("read_thread", args)

    def close(self) -> None:
        self.rpc.close()

    def __enter__(self) -> "NativeCodexBridge":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def redact_credentials(text: str) -> str:
    """Remove common credential forms; never add environment values to evidence."""
    text = re.sub(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", text, flags=re.I)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{16,}", "[REDACTED]", text)
    text = re.sub(
        r"""((?:["']?)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|app[_-]?secret|password|authorization)(?:["']?)\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}\]]+)""",
        r"\1[REDACTED]", text, flags=re.I,
    )
    return text


def coverage_flags(page_or_turn: dict[str, Any]) -> dict[str, Any]:
    """Report explicit truncation separately from normal older-page availability."""
    reasons: list[str] = []
    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                location = f"{path}.{key}" if path else key
                name = key.lower()
                if ("truncat" in name and item not in (None, False, 0, "", [])) or (
                    name in {"coverage", "status"} and isinstance(item, str) and "partial" in item.lower()
                ):
                    reasons.append(location)
                elif name == "itemsview" and isinstance(item, str) and item in {"summary", "notLoaded"}:
                    reasons.append(location)
                elif name == "error" and item:
                    reasons.append(location)
                walk(item, location)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str) and re.search(
            r"\[(?:output |content |text )?truncated(?:[^\]]*)\]|<truncated>|"
            r"\b(?:output|content|text) (?:was )?truncated\b|"
            r"（[^）]{0,20}(?:已截断|输出截断)[^）]{0,20}）", value, re.I
        ):
            reasons.append(path)
    walk(page_or_turn, "")
    return {"partial": bool(reasons), "reasons": list(dict.fromkeys(reasons)),
            "has_more_pages": bool(page_or_turn.get("page", {}).get("hasMore"))}


def turn_evidence(turn: dict[str, Any], *, include_tool_results: bool = False) -> dict[str, Any]:
    """Only visible user/assistant text by default; no reasoning or metadata.

    Necessary tool results are opt-in and field-limited. Commands, arguments,
    internal summaries and environment snapshots are never forwarded.
    """
    def visible_text(value: Any) -> str:
        if isinstance(value, str):
            return redact_credentials(value)
        if isinstance(value, dict):
            return visible_text(value.get("text", ""))
        return ""

    items = []
    for item in turn.get("items", []):
        kind = item.get("type")
        clean: dict[str, Any] = {"type": kind, "id": item.get("id")}
        if kind == "agentMessage":
            clean["text"] = visible_text(item.get("text", ""))
        elif kind == "userMessage":
            content = item.get("content", [])
            clean["content"] = [
                {"type": "text", "text": visible_text(part.get("text", ""))}
                for part in content
                if isinstance(part, dict) and part.get("type") in {"text", "inputText", "input_text"}
            ] if isinstance(content, list) else [{"type": "text", "text": visible_text(content)}]
            if item.get("text"):
                clean["text"] = visible_text(item["text"])
        elif include_tool_results and kind in {"commandExecution", "mcpToolCall", "dynamicToolCall", "fileChange"}:
            for key in ("status", "exitCode", "success", "output", "aggregatedOutput", "error"):
                if key in item:
                    value = item[key]
                    clean[key] = redact_credentials(value) if isinstance(value, str) else (
                        value if value is None or isinstance(value, (bool, int, float))
                        else visible_text(value) or "[structured result omitted]"
                    )
        else:
            continue
        items.append(clean)
    return {**{key: turn.get(key) for key in ("id", "status", "startedAt", "completedAt")},
            "error": {"present": True} if turn.get("error") else None,
            "items": items, "coverage": coverage_flags(turn)}
