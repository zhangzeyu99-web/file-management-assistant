import json
import subprocess
import unittest
from unittest.mock import Mock

from engine.feishu import FeishuSource


def document(token="doc-a", updated=1792468803):
    return {"entity_type": "doc", "title_highlighted": "<h>新资料</h> &amp; 来源",
            "summary_highlighted": "这个正文摘要不得进入元数据",
            "result_meta": {"token": token, "update_time": updated, "doc_types": "DOCX",
                            "owner_id": "owner-should-not-return", "url": "https://example.feishu.cn/docx/" + token}}


def success(rows, has_more=False, page_token=""):
    return subprocess.CompletedProcess([], 0, json.dumps({"ok": True, "identity": "user",
        "data": {"results": rows, "has_more": has_more, "page_token": page_token, "total": 999}}),
        "hour-precision notice")


class FeishuTests(unittest.TestCase):
    def test_follows_all_pages_deduplicates_and_only_returns_metadata(self):
        runner = Mock(side_effect=[success([document()], True, "next"), success([document(updated=1792468804), document("doc-b")]),
                                   success([]), success([document()])])
        result = FeishuSource(["official-cli"], video_owner_id="ou_fixture", runner=runner).list_since("2026-10-20T00:00:00+08:00")
        self.assertTrue(result["complete"])
        self.assertEqual(result["status"], "checked")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["updatedAtEpoch"], 1792468804)
        self.assertEqual(result["items"][0]["title"], "新资料 & 来源")
        self.assertNotIn("正文摘要", json.dumps(result, ensure_ascii=False))
        self.assertNotIn("owner-should-not-return", json.dumps(result))
        args = runner.call_args_list[1].args[0]
        self.assertIn("--query=", args)
        self.assertEqual(args[args.index("--as") + 1], "user")
        self.assertEqual(args[args.index("--page-token") + 1], "next")
        self.assertEqual(args[args.index("--page-size") + 1], "20")
        self.assertIn("--mine", args)
        self.assertNotIn("--edited-since", args)
        self.assertIn("--edited-since", runner.call_args_list[2].args[0])
        self.assertIn("--creator-ids", runner.call_args_list[3].args[0])
        self.assertEqual(result["items"][0]["discoveredBy"], ["owned", "video_owner"])
        self.assertEqual(result["groups"]["owned"]["pages"], 2)
        self.assertTrue(all(group["complete"] for group in result["groups"].values()))

    def test_authorization_error_does_not_claim_no_updates_or_expose_error_secrets(self):
        error = {"ok": False, "identity": "user", "error": {"type": "auth", "subtype": "expired_token",
            "message": "refresh_token=secret-token"}}
        runner = Mock(return_value=subprocess.CompletedProcess([], 1, "", json.dumps(error)))
        result = FeishuSource(["official-cli"], runner=runner).list_since(1792468803)
        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], "not_connected")
        self.assertEqual(result["error"]["code"], "auth_error")
        self.assertNotIn("secret-token", json.dumps(result))
        self.assertEqual(runner.call_count, 1)

    def test_mid_page_failure_preserves_candidates_but_never_completes_window(self):
        denied = {"ok": False, "error": {"type": "permission", "missing_scopes": ["scope"]}}
        runner = Mock(side_effect=[success([document()], True, "next"), subprocess.CompletedProcess([], 1, "", json.dumps(denied)),
                                   success([]), success([])])
        result = FeishuSource(["official-cli"], video_owner_id="ou_fixture", runner=runner).list_since(1792468803)
        self.assertEqual(len(result["items"]), 1)
        self.assertFalse(result["complete"])
        self.assertEqual(result["error"]["code"], "permission_denied")
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["groups"]["video_owner"]["complete"])

    def test_missing_or_repeating_page_token_and_bad_rows_remain_partial(self):
        runner = Mock(side_effect=[success([document()], True, "same"), success([], True, "same"), success([]), success([])])
        result = FeishuSource(["official-cli"], video_owner_id="ou_fixture", runner=runner).list_since(1792468803)
        self.assertFalse(result["complete"])
        self.assertEqual(result["error"]["code"], "pagination_error")
        malformed = FeishuSource(["official-cli"], video_owner_id="ou_fixture", runner=Mock(return_value=success([{}, document()]))).list_since(1792468803)
        self.assertFalse(malformed["complete"])
        self.assertEqual(malformed["status"], "partial")
        self.assertEqual(len(malformed["items"]), 1)

    def test_probe_limit_timeout_invalid_json_and_missing_boundary_are_honest(self):
        probe = FeishuSource(["official-cli"], runner=Mock(return_value=success([document()], True, "next")), max_pages=1)
        result = probe.list_since(1792468803)
        self.assertFalse(result["complete"])
        self.assertEqual(result["groups"]["owned"]["nextPageToken"], "next")
        runner = Mock(side_effect=subprocess.TimeoutExpired(["official-cli"], 60))
        result = FeishuSource(["official-cli"], runner=runner).list_since(1792468803)
        self.assertEqual(result["error"]["code"], "timeout")
        invalid = FeishuSource(["official-cli"], runner=Mock(return_value=subprocess.CompletedProcess([], 0, "not JSON", "")))
        self.assertFalse(invalid.list_since(1792468803)["complete"])
        no_boundary = Mock()
        result = FeishuSource(["official-cli"], runner=no_boundary).list_since(None)
        self.assertEqual(result["error"]["code"], "invalid_since")
        no_boundary.assert_not_called()

    def test_missing_video_owner_does_not_silently_shrink_existing_scope(self):
        runner = Mock(return_value=success([]))
        result = FeishuSource(["official-cli"], runner=runner).list_since(1792468803)
        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["groups"]["video_owner"]["status"], "not_configured")
        self.assertEqual(runner.call_count, 2)


if __name__ == "__main__":
    unittest.main()
