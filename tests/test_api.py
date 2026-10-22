"""HTTP regression tests using ephemeral local ports and isolated data."""
import base64
import json
import tempfile
import threading
import unittest
import uuid
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from server import make_handler
from test_runtime import SharedCloud, UPLOAD_TEXT, execute_one, fixture


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="obsidian-api-test-")
        self.addCleanup(self.temp.cleanup)
        self.runtime, self.model, _ = fixture(Path(self.temp.name))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.runtime))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)

    def request(self, path, data=None, headers=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
            conn.request("POST" if data is not None else "GET", "/api/workspace/" + path,
                         body, {"Content-Type": "application/json", **(headers or {})})
            response = conn.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            conn.close()

    def test_upload_complete_note_and_overview_refresh_through_api(self):
        status, before = self.request("overview")
        self.assertEqual(status, 200)
        body = {"filename": "网页选择.txt", "content": base64.b64encode(UPLOAD_TEXT.encode()).decode(),
                "request_id": str(uuid.uuid4())}
        status, job = self.request("upload", body)
        self.assertEqual(status, 202, job)
        self.assertEqual(self.request("upload", body)[1]["id"], job["id"])
        execute_one(self.runtime, job)
        status, result = self.request("jobs/" + job["id"])
        self.assertEqual(result["status"], "completed", result)
        card = result["result"]["notes"][0]
        status, note = self.request("notes/" + card["id"])
        self.assertEqual(status, 200)
        self.assertIn("只基于本次提供的测试资料，未执行历史任务。", note["markdown"])
        self.assertIn("星河验收资料", note["markdown"])
        self.assertNotIn(UPLOAD_TEXT, note["markdown"])
        self.assertNotIn("## 收录原文", note["markdown"])
        original = Path(self.runtime.cfg["data_root"]) / "runs" / job["id"] / "source.txt"
        self.assertEqual(original.read_bytes(), UPLOAD_TEXT.encode("utf-8"))
        self.assertIn(original.as_uri(), note["markdown"])
        self.assertEqual(self.request("overview")[1]["note_count"], before["note_count"] + 1)
        self.assertTrue(self.request("search?q=" + quote("星河验收资料"))[1]["items"])
        self.assertEqual(len(self.model.prompts), 1)

    def test_wiki_source_link_opens_archived_note_without_search_or_model(self):
        path = Path(self.runtime.cfg["obsidian_vault"]) / "90 历史" / "计算依据.md"
        path.parent.mkdir()
        path.write_text("# 计算依据\n\n## 原始口径\n\n保留原始字段及完整计算条件。\n", encoding="utf-8")
        self.runtime.library.refresh()
        status, resolved = self.request("notes/resolve?target=" + quote("90 历史/计算依据#原始口径"))
        self.assertEqual(status, 200, resolved)
        self.assertEqual(resolved["anchor"], "原始口径")
        status, note = self.request("notes/" + resolved["note_id"])
        self.assertEqual(status, 200)
        self.assertTrue(note["archived"])
        self.assertIn("完整计算条件", note["markdown"])
        self.assertEqual(self.request("search?q=" + quote("计算依据"))[1]["total"], 0)
        self.assertEqual(self.request("notes/resolve?target=" + quote("../库外"))[0], 400)
        self.assertEqual(self.model.prompts, [])

    def test_update_dedup_cancel_retry_and_terminal_retry_boundary(self):
        status, first = self.request("jobs", {"kind": "update", "input": {}})
        self.assertEqual(status, 202)
        self.assertEqual(self.request("jobs", {"kind": "update", "input": {}})[1]["id"], first["id"])
        status, cancelled = self.request("jobs/" + first["id"] + "/cancel", {})
        self.assertEqual(cancelled["status"], "cancelled")
        status, retry = self.request("jobs/" + first["id"] + "/retry", {})
        self.assertEqual(status, 202)
        self.assertEqual(retry["input"]["retry_of"], first["id"])
        self.assertEqual(self.request("jobs/" + retry["id"] + "/retry", {})[0], 409)
        self.runtime.jobs.cancel(retry["id"])
        status, ingest = self.request("jobs", {"kind": "ingest", "input": {"text": "测试正文", "title": "完成边界"}})
        execute_one(self.runtime, ingest)
        self.assertEqual(self.request("jobs/" + ingest["id"] + "/retry", {})[0], 409)

    def test_invalid_upload_and_cross_origin_do_not_enqueue_work(self):
        status, result = self.request("upload", {"filename": "bad.txt", "content": "!!not-base64!!"})
        self.assertEqual(status, 400, result)
        self.assertEqual(self.request("jobs")[1]["items"], [])
        status, _ = self.request("jobs", {"kind": "update"}, {"Origin": "https://outside.invalid"})
        self.assertEqual(status, 403)
        status, _ = self.request("overview", headers={"Host": "outside.invalid"})
        self.assertEqual(status, 403)
        self.assertEqual(self.request("jobs")[1]["items"], [])

    def test_context_api_keeps_both_selected_note_ids(self):
        notes = self.request("overview")[1]["recent"]
        ids = [note["id"] for note in notes]
        _, job = self.request("jobs", {"kind": "context", "input": {"query": "继续热血测试", "ids": ids + ids[:1]}})
        execute_one(self.runtime, job)
        result = self.request("jobs/" + job["id"])[1]
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual([s["id"] for s in result["result"]["sources"]], ids)

    def test_sync_pending_retry_marks_sync_only_and_keeps_original_input(self):
        _, job = self.request("jobs", {"kind": "update", "input": {"scope": "fixture"}})
        claimed = self.runtime.jobs.claim(self.runtime.owner)
        self.runtime.jobs.update(claimed["id"], self.runtime.owner, status="partial",
                                 result={"sync_pending": True, "notes": [{"id": "already-saved"}]})
        status, retried = self.request("jobs/" + job["id"] + "/retry", {})
        self.assertEqual(status, 202)
        self.assertEqual(retried["input"], {"scope": "fixture", "retry_of": job["id"], "sync_only": True})
        # Cloud sync succeeded, but an original source still needs retry.
        claimed = self.runtime.jobs.claim(self.runtime.owner)
        self.assertEqual(claimed["id"], retried["id"])
        self.runtime.jobs.update(claimed["id"], self.runtime.owner, status="partial",
                                 result={"errors": [{"source": "测试来源", "error": "待重试"}]})
        status, second = self.request("jobs/" + retried["id"] + "/retry", {})
        self.assertEqual(status, 202)
        self.assertEqual(second["input"], {"scope": "fixture", "retry_of": job["id"], "sync_only": False})

    def test_cloud_task_visible_and_update_deduplicated_across_both_entries(self):
        cloud = SharedCloud(Path(self.temp.name) / "cloud")
        self.runtime.cloud = cloud
        remote = cloud.request("jobs", {"kind": "update", "input": {}, "request_id": str(uuid.uuid4())})
        status, submitted = self.request("jobs", {"kind": "update", "input": {}, "request_id": str(uuid.uuid4())})
        self.assertEqual(status, 202)
        self.assertEqual(submitted["id"], remote["id"])
        self.assertEqual(submitted["origin"], "cloud")
        self.assertEqual(self.runtime.jobs.list(), [])
        records = self.request("jobs")[1]
        self.assertEqual([j["id"] for j in records["items"]], [remote["id"]])
        self.assertFalse(records["cloud_cache"]["stale"])
        self.assertEqual(self.request("jobs/" + remote["id"])[1]["id"], remote["id"])
        self.assertIsNone(self.runtime.jobs.claim("must-not-claim-mirror"))
        status, cancelled = self.request("jobs/" + remote["id"] + "/cancel", {})
        self.assertEqual(status, 200)
        self.assertEqual(cloud.store.get(remote["id"])["status"], "cancelled")
        self.assertEqual(cancelled["origin"], "cloud")
        status, retried = self.request("jobs/" + remote["id"] + "/retry", {})
        self.assertEqual(status, 202)
        self.assertEqual(retried["input"]["retry_of"], remote["id"])
        self.assertIsNotNone(cloud.store.get(retried["id"]))
        self.assertEqual(self.runtime.jobs.list(), [])

    def test_cloud_upload_transfers_actual_bytes_without_local_claimable_copy(self):
        cloud = SharedCloud(Path(self.temp.name) / "cloud")
        self.runtime.cloud = cloud
        payload = {"filename": "远端上传.txt", "content": base64.b64encode(UPLOAD_TEXT.encode()).decode(),
                   "request_id": str(uuid.uuid4())}
        status, job = self.request("upload", payload)
        self.assertEqual(status, 202)
        self.assertEqual(cloud.uploads[job["input"]["upload_key"]], UPLOAD_TEXT.encode())
        self.assertEqual(job["origin"], "cloud")
        self.assertEqual(self.runtime.jobs.list(), [])
        self.assertFalse((Path(self.runtime.cfg["data_root"]) / "uploads").exists())

    def test_cloud_disconnection_preserves_stale_cache_and_never_creates_local_fallback(self):
        cloud = SharedCloud(Path(self.temp.name) / "cloud")
        self.runtime.cloud = cloud
        _, job = self.request("jobs", {"kind": "context", "input": {"query": "测试"}, "request_id": str(uuid.uuid4())})
        self.request("jobs")
        cloud.connected = False
        self.runtime._cloud_jobs_attempt = 0
        records = self.request("jobs")[1]
        self.assertTrue(records["cloud_cache"]["stale"])
        self.assertIn("测试云连接断开", records["cloud_cache"]["error"])
        self.assertTrue(records["items"][0]["stale"])
        self.assertEqual(records["items"][0]["status"], "queued")
        self.assertTrue(records["items"][0]["stage"].startswith("上次记录"))
        self.assertTrue(self.request("jobs/" + job["id"])[1]["stale"])
        request_id = str(uuid.uuid4())
        status, failure = self.request("jobs", {"kind": "update", "input": {}, "request_id": request_id})
        self.assertEqual(status, 503)
        self.assertEqual(failure["request_id"], request_id)
        status, _ = self.request("upload", {"filename": "断网.txt", "content": "dGVzdA==", "request_id": str(uuid.uuid4())})
        self.assertEqual(status, 503)
        self.assertEqual(self.request("jobs/" + job["id"] + "/cancel", {})[0], 503)
        self.assertEqual(self.runtime.jobs.list(), [])
        self.assertEqual(len(cloud.store.list()), 1)
        self.assertEqual(cloud.store.get(job["id"])["status"], "queued")
        # A restarted process can display the cache, but cannot claim it.
        from engine.runtime import Runtime
        restarted = Runtime(self.runtime.cfg, model=self.model)
        restarted.cloud = cloud
        self.assertTrue(restarted.list_jobs()["cloud_cache"]["stale"])
        self.assertIsNone(restarted.jobs.claim("must-not-claim-cache"))

    def test_existing_local_task_retry_stays_local_after_cloud_is_configured(self):
        _, old = self.request("jobs", {"kind": "ingest", "input": {"text": "旧任务", "title": "本机旧记录"}})
        self.runtime.jobs.cancel(old["id"])
        cloud = SharedCloud(Path(self.temp.name) / "cloud")
        self.runtime.cloud = cloud
        status, retried = self.request("jobs/" + old["id"] + "/retry", {})
        self.assertEqual(status, 202)
        self.assertEqual(retried["origin"], "local")
        self.assertIsNotNone(self.runtime.jobs.get(retried["id"]))
        self.assertEqual(cloud.store.list(), [])
        records = self.request("jobs")[1]["items"]
        self.assertEqual({j["id"] for j in records}, {old["id"], retried["id"]})

    def test_health_exposes_index_version_without_rescanning_library(self):
        status, health = self.request("health")
        self.assertEqual(status, 200)
        self.assertEqual(health["index_version"], self.runtime.library.refreshed_at)

    def test_slow_cloud_list_cannot_replace_newer_cancelled_cache(self):
        cloud = SharedCloud(Path(self.temp.name) / "cloud")
        self.runtime.cloud = cloud
        _, job = self.request("jobs", {"kind": "update", "input": {}})
        original = cloud.request

        def racing_list(path, payload=None, **kwargs):
            old_response = original(path, payload, **kwargs)
            if path == "jobs" and payload is None:
                self.runtime.cancel_job(job["id"])
            return old_response

        cloud.request = racing_list
        records = self.request("jobs")[1]["items"]
        self.assertEqual(records[0]["status"], "cancelled")
        self.assertEqual(cloud.store.get(job["id"])["status"], "cancelled")
        self.assertEqual(self.runtime.jobs.list(), [])


if __name__ == "__main__":
    unittest.main()
