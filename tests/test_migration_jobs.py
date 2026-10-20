"""Web migration jobs use isolated notes, real locks, and fake private transport."""
import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from engine.cloud import Cloud, MIGRATION_CHUNK_BYTES, MIGRATION_CLOUD_LIMIT
from engine.incremental import writer_lock
from engine.migration import MigrationError, executor_session, export_active_bundle
from tests.test_runtime import fixture, SharedCloud


class MigrationJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workspace-export-job-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runtime, self.model, _ = fixture(self.root)
        self.addCleanup(self.stop_worker)

    def stop_worker(self):
        self.runtime.stop.set()
        if self.runtime.worker:
            self.runtime.worker.join(timeout=8)

    def execute(self, job, *, remote=False):
        store = self.runtime.cloud.store if remote else self.runtime.jobs
        claimed = store.claim(self.runtime.owner)
        self.assertEqual(claimed["id"], job["id"])
        with executor_session(self.runtime.data) as session:
            self.runtime._executor_session = session
            try:
                self.runtime.execute(claimed, remote)
            finally:
                self.runtime._executor_session = None
        return store.get(job["id"])

    def test_local_export_with_cloud_config_uses_local_download_and_preserves_package(self):
        self.runtime.cloud = SharedCloud(self.root)
        vault = Path(self.runtime.cfg["obsidian_vault"])
        note = next(vault.glob("*.md"))
        before_bytes = note.read_bytes()
        os.utime(note, ns=(1577934245800000000, 1577934245800000000))
        before_time = note.stat().st_mtime_ns
        (vault / ".env").write_text("NEVER_EXPORT_CREDENTIAL", encoding="utf-8")
        state = Path(self.runtime.cfg["state_path"]).read_bytes()
        job = self.runtime.create("migration_export", {})
        self.assertEqual(job["origin"], "local")
        duplicate = self.runtime.create("migration_export", {})
        self.assertEqual(duplicate["id"], job["id"])
        finished = self.execute(job)
        self.assertEqual(finished["status"], "completed", finished)
        bundle, filename = self.runtime.migration_download(job["id"])
        self.assertFalse(bundle.is_relative_to(self.runtime.data))
        self.assertFalse(bundle.is_relative_to(vault))
        self.assertEqual(finished["result"]["download_url"], "/api/workspace/migration/download/" + job["id"])
        self.assertEqual(finished["result"]["filename"], filename)
        self.assertEqual(finished["result"]["size"], bundle.stat().st_size)
        with zipfile.ZipFile(bundle) as archive:
            info = archive.getinfo("vault/" + note.name)
            self.assertEqual(archive.read(info), before_bytes)
            self.assertEqual(json.loads(info.comment)["mtime_ns"], before_time)
            self.assertNotIn("vault/.env", archive.namelist())
            self.assertEqual(json.loads(archive.read("manifest.json"))["config"]["cloud_url"], "")
        self.assertEqual(Path(self.runtime.cfg["state_path"]).read_bytes(), state)
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.runtime.cloud.requests, [])
        with self.assertRaises(ValueError):
            self.runtime.migration_download("../state.json")
        with self.runtime.jobs.connection() as connection:
            connection.execute("UPDATE jobs SET result=? WHERE id=?",
                               (json.dumps({"filename": "../state.json", "size": 10}), job["id"]))
        with self.assertRaises(ValueError):
            self.runtime.migration_download(job["id"])

    def test_export_requires_live_executor_and_state_lock_failure_never_advances_checkpoint(self):
        before = Path(self.runtime.cfg["state_path"]).read_bytes()
        job = self.runtime.create("migration_export", {})
        claimed = self.runtime.jobs.claim(self.runtime.owner)
        self.runtime.execute(claimed)
        self.assertEqual(self.runtime.jobs.get(job["id"])["status"], "failed")
        retry = self.runtime.retry_job(job["id"])
        with writer_lock(Path(self.runtime.cfg["state_path"]).with_suffix(".lock")):
            result = self.execute(retry)
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(Path(self.runtime.cfg["state_path"]).read_bytes(), before)
        self.assertFalse(self.runtime.migration_exports.exists())
        with executor_session(self.runtime.data) as session:
            pass
        with self.assertRaises((MigrationError, OSError)):
            export_active_bundle(self.runtime.cfg, self.root / "expired.zip", session)
        self.assertFalse((self.root / "expired.zip").exists())

    def test_note_changed_after_stable_read_is_rejected_without_publishing(self):
        from engine import migration
        original = migration._read_stable
        note = next(Path(self.runtime.cfg["obsidian_vault"]).glob("*.md"))
        before = Path(self.runtime.cfg["state_path"]).read_bytes()

        def changed(path):
            content = original(path)
            if path == note:
                path.write_bytes(content + b"\nmanual edit\n")
            return content

        job = self.runtime.create("migration_export", {})
        with patch("engine.migration._read_stable", side_effect=changed):
            result = self.execute(job)
        self.assertEqual(result["status"], "failed", result)
        self.assertIn("导出期间变化", result["error"])
        self.assertEqual(Path(self.runtime.cfg["state_path"]).read_bytes(), before)
        self.assertFalse(list(self.runtime.migration_exports.glob("*.zip")))
        self.assertIn(b"manual edit", note.read_bytes())

    def test_update_and_export_are_serial_and_idle_handoff_releases_executor(self):
        entered, release = threading.Event(), threading.Event()
        events = []

        def update(_):
            events.append("update-start")
            entered.set()
            self.assertTrue(release.wait(5))
            events.append("update-end")
            return {"notes": []}

        from engine import migration
        original = migration._read_stable

        def read(path):
            events.append("export-read")
            self.assertTrue((self.runtime.data / "executor.lock").exists())
            self.assertTrue(Path(self.runtime.cfg["state_path"]).with_suffix(".lock").exists())
            return original(path)

        self.runtime.create("update", {})
        with patch.object(self.runtime, "run_update", side_effect=update), patch(
                "engine.migration._read_stable", side_effect=read):
            self.runtime.start()
            self.assertTrue(entered.wait(3))
            export = self.runtime.create("migration_export", {})
            self.assertEqual(self.runtime.jobs.get(export["id"])["status"], "queued")
            with self.assertRaisesRegex(ValueError, "执行或领取"):
                self.runtime.handoff_for_migration()
            self.assertFalse(self.runtime.stop.is_set())
            release.set()
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                finished = self.runtime.jobs.get(export["id"])
                if finished["status"] in {"completed", "failed"} and not self.runtime._claiming:
                    break
                time.sleep(0.02)
            self.assertEqual(finished["status"], "completed", finished)
            self.runtime.handoff_for_migration()
        self.assertLess(events.index("update-end"), events.index("export-read"))
        self.assertFalse(self.runtime.worker.is_alive())
        self.assertFalse((self.runtime.data / "executor.lock").exists())

    def test_remote_upload_failure_retry_reuses_verified_bundle_without_reexport(self):
        class Remote(SharedCloud):
            def __init__(self, root):
                super().__init__(root)
                self.fail = True
                self.bundles = []

            def request(self, path, payload=None, **kwargs):
                if path.startswith("agent/jobs/"):
                    return self.store.update(path.rsplit("/", 1)[-1], payload["owner"],
                                             **{k: v for k, v in payload.items() if k != "owner"})
                return super().request(path, payload, **kwargs)

            def upload_migration(self, bundle, job_id, owner, **kwargs):
                self.bundles.append(bundle)
                if self.fail:
                    raise RuntimeError("隔离测试：网络中断")
                return {"filename": bundle.name, "size": bundle.stat().st_size,
                        "download_url": "/api/workspace/migration/download/" + job_id}

        remote = self.runtime.cloud = Remote(self.root)
        before = Path(self.runtime.cfg["state_path"]).read_bytes()
        job = remote.store.create("migration_export", {})
        failed = self.execute(job, remote=True)
        self.assertEqual(failed["status"], "failed", failed)
        remote.fail = False
        retry = remote.store.create("migration_export", {"retry_of": job["id"]})
        with patch("engine.runtime.export_active_bundle", side_effect=AssertionError("must reuse accepted ZIP")):
            finished = self.execute(retry, remote=True)
        self.assertEqual(finished["status"], "completed", finished)
        self.assertEqual(remote.bundles[0], remote.bundles[1])
        self.assertEqual(Path(self.runtime.cfg["state_path"]).read_bytes(), before)
        self.assertEqual(self.model.prompts, [])


class CloudMigrationTests(unittest.TestCase):
    def test_binary_parts_private_header_and_complete_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = root / "token.dpapi"
            token.write_bytes(b"encrypted-test-value")
            bundle = root / "synthetic.zip"
            content = b"\x00\xfffixture" * (MIGRATION_CHUNK_BYTES // 9 + 2)
            bundle.write_bytes(content)
            cloud = Cloud("https://fixture.invalid", token)
            requests = []

            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    pass
                def read(self):
                    return json.dumps({"filename": "knowledge-2026-10-20.zip", "size": len(content),
                                       "download_url": "/api/workspace/migration/download/test"}).encode()

            def receive(request, **_):
                requests.append(request)
                self.assertEqual(request.get_header("Oai-sites-authorization"), "Bearer private-test-token")
                return Response()

            with patch("engine.cloud.protect", return_value=b"private-test-token"), patch(
                    "engine.cloud.urllib.request.urlopen", side_effect=receive):
                result = cloud.upload_migration(bundle, "test-job", "test-owner")
            chunks = [row for row in requests if "/chunk?" in row.full_url]
            self.assertEqual(len(chunks), 2)
            self.assertTrue(all(row.get_header("Content-type") == "application/octet-stream" for row in chunks))
            self.assertEqual(b"".join(row.data for row in chunks), content)
            self.assertEqual(len(chunks[0].data), MIGRATION_CHUNK_BYTES)
            self.assertEqual(result["size"], len(content))
            self.assertEqual(result["filename"], "knowledge-2026-10-20.zip")

    def test_cloud_download_filename_rejects_paths_and_control_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "local.zip"
            bundle.write_bytes(b"fixture")
            cloud = Cloud("", Path(directory) / "unused")
            for filename in ("../export.zip", "folder\\export.zip", "bad\r\nheader.zip", ".zip"):
                with self.subTest(filename=filename), patch.object(cloud, "request", return_value={
                        "filename": filename, "size": bundle.stat().st_size, "download_url": "/download"}):
                    with self.assertRaisesRegex(RuntimeError, "未确认完整迁移包"):
                        cloud.upload_migration(bundle, "test", "owner")

    def test_cloud_size_limit_fails_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "large.zip"
            with bundle.open("wb") as output:
                output.truncate(MIGRATION_CLOUD_LIMIT + 1)
            cloud = Cloud("", Path(directory) / "unused")
            with patch.object(cloud, "request", side_effect=AssertionError("must not upload")):
                with self.assertRaisesRegex(ValueError, "本机页面导出"):
                    cloud.upload_migration(bundle, "test", "owner")


if __name__ == "__main__":
    unittest.main()
