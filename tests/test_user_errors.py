"""User recovery contracts, not snapshots of every sentence in the catalog."""
import copy
import errno
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from bridge import BridgeError
from engine.cloud import Cloud, CloudError
from engine.user_errors import catalog, public_payload, record_diagnostic, user_error


class UserErrorTests(unittest.TestCase):
    def test_catalog_has_a_concrete_next_step_and_no_agent_requirement(self):
        for code, detail in catalog().items():
            with self.subTest(code=code):
                self.assertEqual(detail["code"], code)
                self.assertTrue(detail["message"].strip())
                self.assertTrue(detail["action"].strip())
                self.assertIs(type(detail["retryable"]), bool)
                self.assertTrue(detail["help"])
                self.assertNotIn("让 AI", detail["action"])
                self.assertNotIn("联系 AI", detail["action"])

    def test_typed_native_limits_are_not_offered_useless_retry(self):
        detail = user_error(BridgeError("native_oversized", "private native response"))
        self.assertEqual(detail["code"], "native_oversized")
        self.assertFalse(detail["retryable"])
        self.assertIn("添加资料", detail["action"])
        self.assertIn("粘贴", detail["action"])
        self.assertNotIn("private", json.dumps(detail))

    def test_cloud_auth_is_not_misreported_as_network(self):
        for status, code in [(401, "cloud_auth"), (403, "cloud_forbidden"),
                             (404, "cloud_not_found"), (429, "cloud_rate_limited")]:
            with self.subTest(status=status):
                detail = user_error(f"线上服务返回 {status}")
                self.assertEqual(detail["code"], code)
        self.assertEqual(user_error(CloudError("cloud_auth", "credential decrypt failed"))["code"], "cloud_auth")

    def test_migration_recovery_uses_the_actual_failure(self):
        cases = [("目标目录已有内容，请使用新的空目录。", "migration_target_occupied"),
                 ("迁移包损坏或不是有效 ZIP。", "migration_invalid_bundle"),
                 ("当前任务正在执行，请等任务结束。", "migration_busy"),
                 ("本机暂存磁盘空间不足。", "disk_full"),
                 ("上传记录不存在或服务已重启。", "migration_upload_missing"),
                 ("缺少已验收基线时间，不能制作会重新扫描历史的迁移包。", "checkpoint_missing")]
        for text, code in cases:
            with self.subTest(code=code):
                self.assertEqual(user_error(text)["code"], code)

    def test_permissions_and_space_are_not_unknown_or_network_errors(self):
        self.assertEqual(user_error(PermissionError("C:/private/file"))["code"], "file_permission")
        self.assertEqual(user_error(OSError(errno.ENOSPC, "full"))["code"], "disk_full")

    def test_public_result_keeps_completed_and_pending_facts_but_no_raw_exception(self):
        original = {"status": "partial", "result": {"notes": [{"id": "saved", "title": "完成主题"}],
            "errors": [{"source": "某段对话", "thread_id": "native-id", "error_code": "native_oversized",
                        "error": "C:/private/response 该线程超过原生读取限制"}],
            "partial": True, "outstanding": [{"id": "pending", "status": "pending"}]}}
        before = copy.deepcopy(original)
        result = public_payload(original)
        self.assertEqual(original, before)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["result"]["notes"], original["result"]["notes"])
        self.assertEqual(result["result"]["outstanding"], original["result"]["outstanding"])
        row = result["result"]["errors"][0]
        self.assertEqual(row["thread_id"], "native-id")
        self.assertEqual(row["error_code"], "native_oversized")
        self.assertEqual(row["error_detail"]["code"], "native_oversized")
        self.assertNotIn("C:/private", row["error"])

    def test_failed_job_keeps_typed_failure_through_repeated_serialization(self):
        detail = user_error(BridgeError("model_timeout", "private"), diagnostic_id="safe-id")
        job = {"status": "failed", "error": detail["message"], "result": {"failure": detail, "timings": {"model_ms": 2}}}
        once = public_payload(job)
        self.assertEqual(once["error_detail"]["code"], "model_timeout")
        self.assertEqual(public_payload(once), once)
        self.assertEqual(once["result"]["timings"], {"model_ms": 2})

    def test_failure_warnings_are_sanitized_but_range_facts_remain(self):
        original = {"warnings": ["Codex 对话尚未检查：需要本机 Codex 桌面的原生连接和真实调用线程上下文；当前来源未连接。 C:/private",
            "来源目录不可用：C:/private/source", "[Errno 13] Permission denied: C:/private/file",
            "活跃目录有窗口限制，未扩大历史读取。", "3 个旧线程缺少逐条登记，保留历史发现缺口。"]}
        public = public_payload(original)
        self.assertNotIn("C:/private", json.dumps(public))
        self.assertEqual(public["warnings"][-2:], original["warnings"][-2:])
        self.assertEqual([row["code"] for row in public["warning_details"]],
                         ["native_context_missing", "source_directory_unavailable", "file_permission"])
        self.assertEqual(public_payload(public), public)

    def test_unknown_errors_keep_private_details_only_in_local_log(self):
        error = RuntimeError("C:/private/vault API_KEY=sk-this-is-private-credential-example stack trace")
        with tempfile.TemporaryDirectory() as folder:
            reference = record_diagnostic(folder, error, context="test")
            detail = user_error(error, diagnostic_id=reference)
            self.assertEqual(detail["code"], "internal_error")
            self.assertFalse(detail["retryable"])
            self.assertNotIn("C:/private", json.dumps(detail))
            record = json.loads((Path(folder) / "diagnostics/errors.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(record["id"], reference)
            self.assertIn("C:/private/vault", record["detail"])
            self.assertNotIn("sk-this-is-private", record["detail"])

    def test_cloud_http_error_preserves_known_code_without_echoing_body(self):
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder) / "token"
            token.write_bytes(b"encrypted")
            cloud = Cloud("https://example.invalid", token)
            error = urllib.error.HTTPError("https://example.invalid", 400, "bad", {},
                io.BytesIO(json.dumps({"error": "private", "error_detail": {"code": "selection_changed"}}).encode()))
            with patch("engine.cloud.protect", return_value=b"secret"), patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(CloudError) as captured:
                    cloud.request("jobs", {})
            self.assertEqual(captured.exception.code, "selection_changed")
            self.assertNotIn("private", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
