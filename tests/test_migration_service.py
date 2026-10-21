"""Browser migration through real HTTP; all files and runtimes are isolated."""
import io
import json
import os
import threading
import time
import unittest
import zipfile
from types import SimpleNamespace
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from unittest.mock import Mock, patch

from engine.incremental import load_state, path_key
from engine.migration_service import CHUNK_SIZE, MigrationService
from engine.runtime import Runtime
from engine import settings
from server import make_handler
from tests import test_migration as fixtures


class BrowserMigrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.MigrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.project = self.root / "independent-checkout"
        self.project.mkdir()
        self.documents = self.root / "Documents"
        self.documents.mkdir()
        self.service = MigrationService(project_root=self.project, documents_root=self.documents,
                                        start_worker=False)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(migration=self.service))
        self.service.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.fixture.export()
        self.content = self.fixture.bundle.read_bytes()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, path, payload=None, *, raw=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        content_type = "application/octet-stream" if raw is not None else "application/json"
        try:
            connection.request("POST" if body is not None else "GET", "/api/workspace/" + path,
                               body, {"Content-Type": content_type, **(headers or {})})
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data) if response.getheader("Content-Type", "").startswith(
                "application/json") else data
        finally:
            connection.close()

    def upload(self):
        status, result = self.request("migration/import/start",
                                     {"filename": "工作台.zip", "size": len(self.content)})
        self.assertEqual(201, status, result)
        upload_id = result["upload_id"]
        for offset in range(0, len(self.content), 101):
            status, result = self.request(f"migration/import/chunk?upload_id={upload_id}&offset={offset}",
                                         raw=self.content[offset:offset + 101])
            self.assertEqual(200, status, result)
        return upload_id

    def terminal(self, operation_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status, result = self.request("migration/operations/" + operation_id)
            self.assertEqual(200, status)
            if result["status"] != "running":
                return result
            time.sleep(.02)
        self.fail("Migration did not reach a terminal state")

    def test_empty_machine_upload_preview_import_activates_same_api_and_preserves_checkpoint(self):
        self.assertTrue(self.request("health")[1]["setup_required"])
        self.assertEqual([], self.request("projects")[1]["items"])
        self.assertEqual([], self.request("jobs")[1]["items"])
        self.assertEqual(0, self.request("overview")[1]["note_count"])
        self.assertFalse((self.project / ".workspace-active.json").exists())
        occupied = self.documents / "个人知识工作台"
        occupied.mkdir()
        (occupied / "人工.txt").write_text("不可覆盖", encoding="utf-8")
        upload_id = self.upload()
        status, preview = self.request("migration/import/preview", {"upload_id": upload_id})
        self.assertEqual(200, status, preview)
        target = Path(preview["destination"])
        self.assertNotEqual(occupied, target)
        self.assertFalse(target.exists())
        self.assertEqual(1, preview["summary"]["notes"])
        payload = {"upload_id": upload_id, "destination": str(target)}
        status, operation = self.request("migration/import/commit", payload)
        self.assertEqual(202, status, operation)
        result = self.terminal(operation["operation_id"])
        self.assertEqual("completed", result["status"], result)
        self.assertTrue(result["result"]["activated"])
        self.assertEqual(operation["operation_id"], self.request("migration/import/commit", payload)[1]["operation_id"])
        config_path = Path(result["result"]["config_path"])
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual("", config["cloud_url"])
        self.assertEqual(self.server.server_port, config["port"])
        self.assertEqual(self.fixture.note_bytes, (Path(config["obsidian_vault"]) / self.fixture.note.name).read_bytes())
        state = load_state(config["state_path"])
        self.assertEqual(self.fixture.state["threads"]["thread"]["through"], state["threads"]["thread"]["through"])
        source = Path(config["watch_roots"][0]["path"]) / self.fixture.source.name
        self.assertIn(path_key(source), state["files"])
        self.assertFalse(self.request("health")[1]["setup_required"])
        self.assertEqual(1, self.request("overview")[1]["note_count"])
        with patch.object(settings, "ROOT", self.project):
            self.assertEqual(str(config_path), settings.load_settings()["_config_path"])
        self.assertEqual("不可覆盖", (occupied / "人工.txt").read_text(encoding="utf-8"))
        self.assertFalse((self.project / "config.local.json").exists())

    def test_without_codex_cli_import_read_search_and_export_work_but_ai_jobs_fail_clearly(self):
        self.service.start_worker = True

        def stop_runtime():
            runtime = self.service.runtime
            if runtime:
                runtime.stop.set()
                if runtime.worker:
                    runtime.worker.join(timeout=8)
                    self.assertFalse(runtime.worker.is_alive())
        self.addCleanup(stop_runtime)

        def finish_job(job_id):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                status, job = self.request("jobs/" + job_id)
                self.assertEqual(200, status, job)
                if job["status"] in {"completed", "partial", "failed", "cancelled"}:
                    return job
                time.sleep(.02)
            self.fail("Task did not reach a terminal state")

        # Use the real model's executable discovery, never a fake model/runtime.
        with patch.dict(os.environ, {"CODEX_CLI_PATH": ""}), patch(
                "bridge.model.shutil.which", return_value=None) as discover:
            upload_id = self.upload()
            status, preview = self.request("migration/import/preview", {"upload_id": upload_id})
            self.assertEqual(200, status, preview)
            status, operation = self.request("migration/import/commit", {
                "upload_id": upload_id, "destination": preview["destination"]})
            self.assertEqual(202, status, operation)
            imported = self.terminal(operation["operation_id"])
            self.assertEqual("completed", imported["status"], imported)
            self.assertTrue(imported["result"]["activated"])
            self.assertFalse(self.request("health")[1]["setup_required"])
            self.assertEqual(1, self.request("overview")[1]["note_count"])
            status, found = self.request("search?q=" + quote("迁移验收术语"))
            self.assertEqual(200, status, found)
            self.assertTrue(found["items"])
            source = found["items"][0]
            note = self.request("notes/" + source["note_id"])[1]
            self.assertIn("保留正文与人工增补", note["markdown"])
            runtime = self.service.runtime
            checkpoint = Path(runtime.cfg["state_path"])
            before_state = checkpoint.read_bytes()
            status, exported = self.request("jobs", {"kind": "migration_export", "input": {}})
            self.assertEqual(202, status, exported)
            exported = finish_job(exported["id"])
            self.assertEqual("completed", exported["status"], exported)
            status, package = self.request("migration/download/" + exported["id"])
            self.assertEqual(200, status)
            with zipfile.ZipFile(io.BytesIO(package)) as archive:
                self.assertEqual(self.fixture.note_bytes, archive.read("vault/" + self.fixture.note.name))
            discover.assert_not_called()
            for kind in ("answer", "context"):
                status, job = self.request("jobs", {"kind": kind, "input": {
                    "query": "迁移验收术语是什么？", "ids": [source["id"]]}})
                self.assertEqual(202, status, job)
                failed = finish_job(job["id"])
                self.assertEqual("failed", failed["status"], failed)
                self.assertIn("安装 Codex CLI", failed["error"])
                self.assertIn("登录", failed["error"])
                self.assertFalse((failed.get("result") or {}).get("markdown"))
            self.assertTrue(discover.called)
            self.assertEqual(before_state, checkpoint.read_bytes())
            self.assertEqual(1, self.request("overview")[1]["note_count"])
            self.assertIsNone(runtime.model)

    def test_early_post_rejections_deliver_json_when_body_follows_headers(self):
        body = b'{"filename":"bundle.zip","size":10}'
        cases = [
            (403, "migration/import/start", body,
             {"Content-Type": "application/json", "Origin": "https://foreign.invalid"}),
            (415, "migration/import/start", body, {"Content-Type": "text/plain"}),
            (413, "migration/import/chunk", b"x",
             {"Content-Type": "application/octet-stream", "Content-Length": str(CHUNK_SIZE + 1)}),
        ]
        for expected, route, content, headers in cases:
            with self.subTest(status=expected):
                connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=1)
                try:
                    connection.putrequest("POST", "/api/workspace/" + route)
                    for key, value in {"Content-Length": str(len(content)), **headers}.items():
                        connection.putheader(key, value)
                    connection.endheaders()
                    # A browser can send its body after the server rejects its headers.
                    # Closing before these bytes arrive used to abort response reads.
                    time.sleep(.02)
                    connection.send(content)
                    response = connection.getresponse()
                    self.assertEqual(expected, response.status)
                    self.assertIsInstance(json.loads(response.read())["error"], str)
                finally:
                    connection.close()
        self.assertFalse(self.service.uploads)

    def test_chunk_transport_rejects_csrf_wrong_offset_and_modified_retry(self):
        status, _ = self.request("migration/import/start", {"filename": "bundle.zip", "size": 10},
                                 headers={"Origin": "https://foreign.invalid"})
        self.assertEqual(403, status)
        self.assertEqual(415, self.request("migration/import/start", {"filename": "x.zip", "size": 10},
                                          headers={"Content-Type": "text/plain"})[0])
        upload_id = self.request("migration/import/start", {"filename": "bundle.zip", "size": 10})[1]["upload_id"]
        route = f"migration/import/chunk?upload_id={upload_id}&offset="
        self.assertEqual(400, self.request(route + "2", raw=b"abc")[0])
        self.assertEqual({"received": 3}, self.request(route + "0", raw=b"abc")[1])
        self.assertEqual({"received": 3}, self.request(route + "0", raw=b"abc")[1])
        self.assertEqual(400, self.request(route + "0", raw=b"abd")[0])
        self.assertEqual(400, self.request("migration/import/preview", {"upload_id": upload_id})[0])
        self.assertEqual(400, self.request("migration/import/chunk?upload_id=../../state&offset=0", raw=b"x")[0])
        self.assertEqual(413, self.request(route + "3", raw=b"x",
                         headers={"Content-Length": str(CHUNK_SIZE + 1)})[0])
        self.assertEqual({"cancelled": True}, self.request("migration/import/cancel", {"upload_id": upload_id})[1])
        self.assertFalse(self.service.uploads)
        bad_id = self.request("migration/import/start", {"filename": "broken.zip", "size": 3})[1]["upload_id"]
        self.request(f"migration/import/chunk?upload_id={bad_id}&offset=0", raw=b"bad")
        code, error = self.request("migration/import/preview", {"upload_id": bad_id})
        self.assertEqual(400, code)
        self.assertIn("迁移包损坏或不是有效 ZIP", error["error"])
        self.assertFalse((self.project / ".workspace-active.json").exists())

    def test_existing_directory_and_active_task_are_never_overwritten_or_switched(self):
        upload_id = self.upload()
        occupied = self.root / "existing"
        occupied.mkdir()
        note = occupied / "human.md"
        note.write_text("existing", encoding="utf-8")
        self.assertEqual(400, self.request("migration/import/preview",
                         {"upload_id": upload_id, "destination": str(occupied)})[0])
        self.assertEqual(400, self.request("migration/import/preview",
                         {"upload_id": upload_id, "destination": str(self.project / "nested-library")})[0])
        _, preview = self.request("migration/import/preview", {"upload_id": upload_id})

        class Busy:
            def health(self):
                return {"active_job": "in-progress"}
        self.service.runtime = Busy()
        status, _ = self.request("migration/import/commit",
                                 {"upload_id": upload_id, "destination": preview["destination"]})
        self.assertEqual(400, status)
        self.assertFalse(Path(preview["destination"]).exists())
        self.assertEqual("existing", note.read_text())
        self.assertFalse((self.project / ".workspace-active.json").exists())

    def test_activation_failure_preserves_original_selection_and_can_retry_without_reimport(self):
        pointer = self.project / ".workspace-active.json"
        pointer.write_text('{"config":"untouched-original-config"}', encoding="utf-8")
        original = pointer.read_bytes()
        upload_id = self.upload()
        _, preview = self.request("migration/import/preview", {"upload_id": upload_id})
        payload = {"upload_id": upload_id, "destination": preview["destination"]}
        self.service.runtime_factory = lambda _: (_ for _ in ()).throw(ValueError("合成的启用失败"))
        _, operation = self.request("migration/import/commit", payload)
        failed = self.terminal(operation["operation_id"])
        self.assertEqual("failed", failed["status"])
        self.assertFalse(failed["result"]["activated"])
        self.assertEqual(original, pointer.read_bytes())
        self.service.runtime_factory = Runtime
        _, retry = self.request("migration/import/commit", payload)
        self.assertEqual("completed", self.terminal(retry["operation_id"])["status"])

    def test_idle_existing_runtime_is_handed_off_without_replacing_old_config(self):
        previous_config = self.project / "config.local.json"
        original = b'{"description":"original configuration"}'
        previous_config.write_bytes(original)
        old = SimpleNamespace(health=lambda: {"active_job": None}, handoff_for_migration=Mock(), cfg={})
        self.service.runtime = old
        upload_id = self.upload()
        _, preview = self.request("migration/import/preview", {"upload_id": upload_id})
        _, operation = self.request("migration/import/commit",
                                    {"upload_id": upload_id, "destination": preview["destination"]})
        self.assertEqual("completed", self.terminal(operation["operation_id"])["status"])
        old.handoff_for_migration.assert_called_once()
        self.assertEqual(original, previous_config.read_bytes())
        self.assertIsNot(old, self.service.runtime)

    def test_unreadable_selection_does_not_stop_existing_runtime(self):
        pointer = self.project / ".workspace-active.json"
        pointer.write_text('{"config":"previous"}', encoding="utf-8")
        old = SimpleNamespace(health=lambda: {"active_job": None}, handoff_for_migration=Mock(), cfg={})
        self.service.runtime = old
        upload_id = self.upload()
        _, preview = self.request("migration/import/preview", {"upload_id": upload_id})
        original_read = Path.read_bytes
        def unreadable(path):
            if path == pointer:
                raise PermissionError("合成：选择记录被占用")
            return original_read(path)
        with patch.object(Path, "read_bytes", unreadable):
            _, operation = self.request("migration/import/commit",
                                        {"upload_id": upload_id, "destination": preview["destination"]})
            result = self.terminal(operation["operation_id"])
        self.assertEqual("failed", result["status"])
        old.handoff_for_migration.assert_not_called()
        self.assertIs(old, self.service.runtime)
        self.assertEqual('{"config":"previous"}', pointer.read_text(encoding="utf-8"))

    def test_download_stream_uses_validated_job_and_ignores_arbitrary_path_parameter(self):
        artifact = self.root / "verified-export.zip"
        content = b"verified-export" * 90000
        artifact.write_bytes(content)
        def verified(job_id):
            if job_id != "completed-export":
                raise ValueError("仅可下载已完成的迁移导出任务")
            return artifact, "工作台迁移.zip"
        self.service.runtime = SimpleNamespace(migration_download=verified)
        status, result = self.request("migration/download/completed-export?path=unrelated-file")
        self.assertEqual(200, status)
        self.assertEqual(content, result)
        self.assertEqual(400, self.request("migration/download/unrelated-file")[0])


if __name__ == "__main__":
    unittest.main()
