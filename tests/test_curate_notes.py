"""Real merges and injected failures use temporary vaults, never user data."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine.incremental import load_state, path_key, writer_lock
from engine.ingest import IngestError, write_note
from engine.library import Library, _encode
from scripts import curate_notes as curate


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="curation-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.vault, self.data = self.root / "vault", self.root / "runtime"
        self.output = self.vault / "30 资料"
        for directory in (self.output, self.data / "receipts", self.vault / ".obsidian"):
            directory.mkdir(parents=True, exist_ok=True)
        self.target = "10 项目/热血合服/热血合服活跃计算.md"
        self.source = "30 资料/热血合服旧计算.md"
        self.target_path, self.source_path = self.vault / self.target, self.vault / self.source
        self.target_path.parent.mkdir(parents=True)
        self.target_bytes = b"\xef\xbb\xbf" + "# 热血合服活跃计算\r\n\r\n旧口径尚待核对。\r\n".encode("utf-8")
        self.target_path.write_bytes(self.target_bytes)
        self.written = write_note(self.output, "热血合服旧计算", "# 热血合服旧计算\n\n近三天用户数按去重口径保留。", "original_task",
                                  ["https://example.invalid/source"], identity_root=self.vault)
        self.assertEqual(Path(self.written["note"]), self.source_path)
        self.source_bytes = self.source_path.read_bytes()
        self.layout = self.vault / ".obsidian/knowledge-layout.json"
        self.layout.write_text(json.dumps({"version": 1, "navigation": True,
                                         "path_aliases": {"最早旧标题.md": self.source}, "custom": "keep"}), encoding="utf-8")
        self.receipt = {"id": "keep-receipt", "note": str(self.source_path), "lane": "threads",
                        "source": "thread-1", "verifiedAt": "2026-10-01T00:00:00Z",
                        "status": "committed", "checkpoint_committed": True}
        self.receipt_path = self.data / "receipts/keep-receipt.json"
        self.receipt_path.write_text(json.dumps(self.receipt), encoding="utf-8")
        self.state_path = self.data / "state.json"
        self.state = {"version": 1, "files": {"external-source": {"note": str(self.source_path), "path": "untouched-source"}},
                      "feishu": {"token": {"check_note": str(self.source_path), "content_status": "source_only"}},
                      "threads": {"thread-1": {"note": str(self.source_path), "turns": {"turn-1": ["completed", 7]},
                                                "through": 9, "pending": True, "receipts": [self.receipt]}},
                      "custom": {"keep": [1, 2]}}
        self.state_path.write_text(json.dumps(self.state), encoding="utf-8")
        self.config = {"obsidian_vault": str(self.vault), "data_root": str(self.data),
                       "state_path": str(self.state_path), "output_root": str(self.output)}
        self.reviewed = self.root / "reviewed.md"
        self.final = "# 热血合服活跃计算\r\n\r\n活跃采用近三天去重用户数，不除以三。\r\n\r\n保留查询时段和付费用户的独立统计。\r\n".encode("utf-8-sig")
        self.reviewed.write_bytes(self.final)

    def plan(self, target=None, sources=None):
        result = curate.plan_merge(self.config, target or self.target, sources or [self.source])
        return Path(result["plan_path"])

    def test_merge_keeps_original_retry_identity_aliases_and_checkpoint_receipts(self):
        plan = self.plan()
        result = curate.apply_merge(self.config, plan, self.reviewed)
        self.assertFalse(self.source_path.exists())
        self.assertEqual(self.target_path.read_bytes(), self.final)
        original = self.vault / result["retired_originals"][self.source]
        self.assertEqual(original.read_bytes(), self.source_bytes)
        self.assertEqual((self.vault / result["retired_originals"][self.target]).read_bytes(), self.target_bytes)
        state = load_state(self.state_path)
        self.assertEqual(state["threads"]["thread-1"]["turns"], self.state["threads"]["thread-1"]["turns"])
        self.assertEqual(state["threads"]["thread-1"]["through"], 9)
        self.assertTrue(state["threads"]["thread-1"]["pending"])
        self.assertEqual(state["custom"], self.state["custom"])
        self.assertEqual(state["files"]["external-source"]["path"], "untouched-source")
        self.assertEqual(state["threads"]["thread-1"]["note"], str(original))
        receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt, {**self.receipt, "note": str(original)})
        reused = write_note(self.output, "热血合服旧计算", "# 热血合服旧计算\n\n近三天用户数按去重口径保留。", "original_task",
                            ["https://example.invalid/source"], identity_root=self.vault)
        self.assertTrue(reused["reused"])
        self.assertEqual(Path(reused["note"]), original)
        library = Library(self.vault)
        self.assertFalse(library.refresh()["warnings"])
        old = library.get_note("n_" + _encode(self.source))
        earliest = library.get_note("n_" + _encode("最早旧标题.md"))
        self.assertEqual(old["relative"], self.target)
        self.assertEqual(earliest["relative"], self.target)
        self.assertEqual(library.get_note("n_" + _encode(result["retired_originals"][self.source]))["markdown"], self.source_bytes.decode("utf-8"))
        second = curate.apply_merge(self.config, plan, self.reviewed)
        self.assertTrue(second["reused"])
        with self.assertRaises(IngestError):
            write_note(self.output, "热血合服旧计算", "# 热血合服旧计算\n\n错误的新正文。", "original_task", identity_root=self.vault)

    def test_source_and_management_edits_after_plan_are_never_overwritten(self):
        for which in ("source", "target", "state", "index", "layout", "receipt"):
            with self.subTest(which=which):
                paths = {"source": self.source_path, "target": self.target_path, "state": self.state_path,
                         "index": self.output / ".note-index.json", "layout": self.layout, "receipt": self.receipt_path}
                path = paths[which]
                original = path.read_bytes()
                before = path.stat()
                plan = self.plan()
                path.write_bytes(original + b"\n")
                with self.assertRaisesRegex(curate.CurationError, "计划后发生变化"):
                    curate.apply_merge(self.config, plan, self.reviewed)
                self.assertEqual(path.read_bytes(), original + b"\n")
                path.write_bytes(original)
                import os
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

    def test_multiple_sources_and_previous_target_tasks_keep_exact_retries(self):
        target_text = "# 热血合服统计总口径\n\n活跃和付费口径需合并核对。"
        second_text = "# 热血合服付费统计\n\n付费用户也采用近三天去重口径。"
        target_note = write_note(self.output, "热血合服统计总口径", target_text, "target_task", identity_root=self.vault)
        second_note = write_note(self.output, "热血合服付费统计", second_text, "second_task", identity_root=self.vault)
        target = Path(target_note["note"]).relative_to(self.vault).as_posix()
        second = Path(second_note["note"]).relative_to(self.vault).as_posix()
        originals = {target: Path(target_note["note"]).read_bytes(), self.source: self.source_bytes,
                     second: Path(second_note["note"]).read_bytes()}
        result = curate.apply_merge(self.config, self.plan(target=target, sources=[self.source, second]), self.reviewed)
        self.assertEqual(len(result["retired_originals"]), 3)
        for relative, original in originals.items():
            self.assertEqual((self.vault / result["retired_originals"][relative]).read_bytes(), original)
        for title, text, task in (("热血合服统计总口径", target_text, "target_task"),
                                  ("热血合服付费统计", second_text, "second_task")):
            retry = write_note(self.output, title, text, task, identity_root=self.vault)
            self.assertTrue(retry["reused"])
            self.assertTrue(Path(retry["note"]).is_relative_to(self.vault / ".source-history/curation"))
        index = json.loads((self.output / ".note-index.json").read_text(encoding="utf-8"))
        self.assertEqual(set(index["tasks"]), {"original_task", "target_task", "second_task"})

    def test_live_executor_and_note_writer_locks_reject_merge(self):
        plan = self.plan()
        for lock in (self.data / "executor.lock", self.state_path.with_suffix(".lock"), self.output / ".write.lock"):
            with self.subTest(lock=lock), writer_lock(lock):
                with self.assertRaises(ValueError):
                    curate.apply_merge(self.config, plan, self.reviewed)
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)
        self.assertEqual(self.target_path.read_bytes(), self.target_bytes)

    def test_failed_metadata_publish_restores_exact_originals_and_retains_backup(self):
        plan = self.plan()
        before = json.loads(plan.read_text(encoding="utf-8"))["files"]
        real_write = curate._write_bytes
        failed = False

        def fail_once(path, content):
            nonlocal failed
            if Path(path) == self.layout and not failed:
                failed = True
                raise OSError("simulated metadata write failure")
            return real_write(path, content)

        with patch.object(curate, "_write_bytes", side_effect=fail_once):
            with self.assertRaisesRegex(curate.CurationError, "已恢复原文和管理记录"):
                curate.apply_merge(self.config, plan, self.reviewed)
        for path, snapshot in before.items():
            self.assertEqual(Path(path).read_bytes(), curate._bytes(snapshot))
            self.assertEqual(Path(path).stat().st_mtime_ns, snapshot["mtime_ns"])
        operation = json.loads(plan.read_text(encoding="utf-8"))["id"]
        backup = self.data / "curation" / operation
        self.assertEqual(json.loads((backup / "rollback.json").read_text())["status"], "restored")
        self.assertTrue((backup / "backup.json").is_file())
        recovered = list((backup / "recovered-originals").rglob("*.md"))
        self.assertEqual(len(recovered), 2)
        self.assertFalse(list((self.vault / ".source-history").rglob("*.md")))

    def test_quality_gate_rejects_placeholder_and_copied_task_markers(self):
        plan = self.plan()
        for content in ("# 整理结果\n\n已经完成。", "# 热血合服计算\n\n<!-- obsidian-workspace task:copy -->\n\n有效说明。"):
            with self.subTest(content=content):
                self.reviewed.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    curate.apply_merge(self.config, plan, self.reviewed)
        self.assertEqual(self.target_path.read_bytes(), self.target_bytes)
        self.assertFalse((self.data / "curation" / json.loads(plan.read_text())["id"]).exists())

    def test_manual_edit_during_apply_is_detected_and_not_rolled_back(self):
        plan = self.plan()
        real_write = curate._write_bytes
        manual = self.target_bytes + "\r\n正在手工补充。".encode("utf-8")

        def edit_target_before_publish(path, content):
            if Path(path) == self.layout:
                self.target_path.write_bytes(manual)
            return real_write(path, content)

        with patch.object(curate, "_write_bytes", side_effect=edit_target_before_publish):
            with self.assertRaisesRegex(curate.CurationError, "已恢复原文和管理记录"):
                curate.apply_merge(self.config, plan, self.reviewed)
        self.assertEqual(self.target_path.read_bytes(), manual)
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)

    def test_existing_manual_edit_after_merge_is_not_reset_on_replay(self):
        plan = self.plan()
        curate.apply_merge(self.config, plan, self.reviewed)
        self.target_path.write_bytes(self.final + "\n人工补充。".encode("utf-8"))
        with self.assertRaisesRegex(curate.CurationError, "合并后文件已有改动"):
            curate.apply_merge(self.config, plan, self.reviewed)

    def test_missing_checkpoint_and_unsafe_paths_do_not_initialize_or_mutate(self):
        for path in ("../outside.md", ".source-history/old.md", "C:/outside.md", "10 项目/../outside.md", "notes\\old.md"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.plan(sources=[path])
        self.state_path.unlink()
        with self.assertRaisesRegex(ValueError, "检查点不存在"):
            self.plan()
        self.assertFalse(self.state_path.exists())
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)

    def test_new_target_and_cli_use_explicit_config_without_real_workspace(self):
        config_file = self.root / "fixture.json"
        config_file.write_text(json.dumps(self.config), encoding="utf-8")
        destination = self.root / "private-plan.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = curate.main(["--config", str(config_file), "plan", "--target", "10 项目/热血合服/合服去重统计.md",
                                "--source", self.source, "--plan-out", str(destination)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["plan_path"], str(destination))
        with contextlib.redirect_stdout(io.StringIO()):
            code = curate.main(["--config", str(config_file), "apply", "--plan", str(destination), "--content", str(self.reviewed)])
        self.assertEqual(code, 0)
        self.assertEqual((self.vault / "10 项目/热血合服/合服去重统计.md").read_bytes(), self.final)


if __name__ == "__main__":
    unittest.main()
