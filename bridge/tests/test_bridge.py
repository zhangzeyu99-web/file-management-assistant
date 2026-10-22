from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from bridge.model import CodexModel, parse_model_events
from bridge.native import BridgeError, NativeCodexBridge, StdioRpc, coverage_flags, decode_tool_result, turn_evidence


def success_output(text: str = "测试总结") -> str:
    return "\n".join(json.dumps(row) for row in [
        {"type": "thread.started", "thread_id": "ephemeral-test"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
        {"type": "turn.completed", "usage": {"output_tokens": 8}},
    ])


class NativeContractTests(unittest.TestCase):
    def test_missing_desktop_context_is_not_empty_success(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(BridgeError) as error:
                NativeCodexBridge()
        self.assertEqual(error.exception.code, "native_context_missing")

    def test_native_error_content_is_not_reported_as_a_successful_empty_page(self):
        with self.assertRaises(BridgeError) as error:
            decode_tool_result({"isError": True, "content": [{"type": "text", "text": "secret=not-for-output"}]})
        self.assertEqual(error.exception.code, "native_read_failed")
        self.assertNotIn("secret", str(error.exception))

    def test_read_preserves_page_cursor_completion_and_items(self):
        expected = {"thread": {"id": "t"}, "page": {"nextCursor": "opaque", "hasMore": True},
                    "turns": [{"id": "r", "status": "completed", "startedAt": 10, "completedAt": 20,
                               "items": [{"type": "agentMessage", "text": "结果"}]}]}
        native = NativeCodexBridge.__new__(NativeCodexBridge)
        native.caller_thread_id = "real-caller"
        native.rpc = Mock()
        native.rpc.request.return_value = {"content": [{"type": "text", "text": json.dumps(expected)}]}
        actual = native.read_thread("t", cursor="older-page", turn_limit=1, host_id="host")
        self.assertEqual(actual, expected)
        params = native.rpc.request.call_args.args[1]
        self.assertEqual(params["arguments"]["cursor"], "older-page")
        self.assertEqual(params["arguments"]["hostId"], "host")
        self.assertEqual(params["_meta"]["openai/threadId"], "real-caller")

    def test_writing_tools_are_rejected_before_rpc(self):
        native = NativeCodexBridge.__new__(NativeCodexBridge)
        native.rpc = Mock()
        with self.assertRaises(BridgeError):
            native.call("send_message_to_thread", {"message": "do not send"})
        native.rpc.request.assert_not_called()

    def test_reasoning_is_not_forwarded_as_evidence(self):
        result = turn_evidence({"id": "r", "status": "completed", "startedAt": 1, "completedAt": 2,
                                "items": [{"type": "reasoning", "summary": "internal"},
                                          {"type": "agentMessage", "text": "visible"},
                                          {"type": "userMessage", "content": []}]})
        self.assertEqual([item["type"] for item in result["items"]], ["agentMessage", "userMessage"])
        self.assertEqual(result["completedAt"], 2)

    def test_credentials_and_tool_arguments_are_not_forwarded_to_model(self):
        result = turn_evidence({
            "items": [
                {"type": "agentMessage", "text": 'API_KEY="fake-secret"\nAuthorization: Bearer private-value'},
                {"type": "commandExecution", "command": "echo private", "output": "private"},
                {"type": "reasoning", "summary": "internal"},
            ],
            "error": {"message": "credential=private"},
        })
        text = json.dumps(result)
        self.assertNotIn("fake-secret", text)
        self.assertNotIn("private", text)
        self.assertNotIn("internal", text)
        self.assertEqual(len(result["items"]), 1)

    def test_explicit_truncation_is_partial_but_normal_pagination_is_not(self):
        self.assertFalse(coverage_flags({"page": {"hasMore": True, "nextCursor": "cursor"}})["partial"])
        result = coverage_flags({"turns": [{"items": [{"outputTruncated": True}]}]})
        self.assertTrue(result["partial"])
        self.assertEqual(result["reasons"], ["turns[0].items[0].outputTruncated"])
        self.assertTrue(coverage_flags({"items": [{"text": "[output truncated]"}]})["partial"])

    def test_wrapped_native_text_is_preserved_without_internal_fields(self):
        result = turn_evidence({"items": [
            {"type": "agentMessage", "text": {"text": "已完成", "truncated": True}},
            {"type": "userMessage", "content": [{"type": "inputText", "text": "请总结"}]},
            {"type": "commandExecution", "output": {"text": "验证通过", "truncated": False}},
        ]}, include_tool_results=True)
        self.assertEqual(result["items"][0]["text"], "已完成")
        self.assertEqual(result["items"][2]["output"], "验证通过")
        self.assertTrue(result["coverage"]["partial"])

    def test_rpc_timeout_closes_its_child_without_leaking_raw_stderr(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / "fake.py"
            fake.write_text("import sys,time\nsys.stderr.write('credential=fake')\ntime.sleep(10)\n", encoding="utf-8")
            rpc = StdioRpc([sys.executable, str(fake)], env=dict(os.environ), timeout=0.05)
            try:
                with self.assertRaises(BridgeError) as error:
                    rpc.request("initialize", {})
                self.assertEqual(error.exception.code, "native_timeout")
                self.assertIsNotNone(rpc.process.poll())
                self.assertNotIn("credential", str(error.exception))
            finally:
                rpc.close()


class ModelContractTests(unittest.TestCase):
    def test_completed_model_text_is_required(self):
        self.assertEqual(parse_model_events(success_output())["text"], "测试总结")
        with self.assertRaises(BridgeError):
            parse_model_events('{"type":"turn.started"}')
        with self.assertRaises(BridgeError):
            parse_model_events('{"type":"turn.failed","error":{"message":"private"}}')

    def test_tool_execution_invalidates_a_summary(self):
        with self.assertRaises(BridgeError) as error:
            parse_model_events(
                '{"type":"item.completed","item":{"type":"command_execution","command":"private"}}\n'
                + success_output())
        self.assertEqual(error.exception.code, "model_tool_use")

    def test_generate_returns_text_and_is_ephemeral_readonly_with_no_desktop_pipe(self):
        fake = subprocess.CompletedProcess([], 0, success_output(), "not returned")
        model = CodexModel.__new__(CodexModel)
        model.command = ["codex.exe"]
        model.cwd = str(Path(__file__).parent)
        phases = []
        with patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "private-pipe", "CODEX_THREAD_ID": "caller"}):
            with patch("bridge.model.subprocess.run", return_value=fake) as run:
                result = model.generate("只总结测试材料", on_event=phases.append)
        self.assertIsInstance(result, str)
        self.assertEqual(result, "测试总结")
        args, kwargs = run.call_args
        self.assertIn("--ephemeral", args[0])
        self.assertIn("read-only", args[0])
        self.assertIn("--ignore-user-config", args[0])
        self.assertIn('model_reasoning_effort="low"', args[0])
        self.assertFalse(any("service_tier" in item for item in args[0]))
        self.assertIn("shell_tool", args[0])
        self.assertNotIn("CODEX_APP_TOOLS_PIPE_PATH", kwargs["env"])
        self.assertNotIn("CODEX_THREAD_ID", kwargs["env"])
        self.assertEqual(phases, [{"phase": "model_started"}, {"phase": "model_completed"}])

    def test_timeout_cannot_return_success(self):
        model = CodexModel.__new__(CodexModel)
        model.command, model.cwd = ["codex.exe"], "."
        with patch("bridge.model.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 1)):
            with self.assertRaises(BridgeError) as error:
                model.generate("test", timeout=1)
        self.assertEqual(error.exception.code, "model_timeout")


if __name__ == "__main__":
    unittest.main()
