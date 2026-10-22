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

    def retire_plan(self, sources=None, additions=None):
        result = curate.plan_retire(self.config, sources or [self.source], additions=additions)
        self.assertNotIn("canonical", result)
        return Path(result["plan_path"])

    def test_retire_without_canonical_preserves_each_original_alias_and_retry_identity(self):
        plan = self.retire_plan([self.source, self.target])
        with patch.object(curate, "_reviewed_content", side_effect=AssertionError("retirement has no replacement text")):
            result = curate.apply_plan(self.config, plan)
        self.assertEqual(result["mode"], "retire")
        self.assertNotIn("canonical", result)
        originals = {self.source: self.source_bytes, self.target: self.target_bytes}
        for relative, content in originals.items():
            self.assertFalse((self.vault / relative).exists())
            history = result["retired_originals"][relative]
            self.assertTrue(history.startswith(f".source-history/curation/{json.loads(plan.read_text())['id']}/sources/"))
            self.assertEqual((self.vault / history).read_bytes(), content)
        original = self.vault / result["retired_originals"][self.source]
        state = load_state(self.state_path)
        self.assertEqual(state["threads"]["thread-1"]["turns"], self.state["threads"]["thread-1"]["turns"])
        self.assertEqual(state["threads"]["thread-1"]["through"], 9)
        self.assertTrue(state["threads"]["thread-1"]["pending"])
        self.assertEqual(state["files"]["external-source"]["path"], "untouched-source")
        self.assertEqual(state["files"]["external-source"]["note"], str(original))
        self.assertEqual(state["threads"]["thread-1"]["note"], str(original))
        self.assertEqual(state["feishu"]["token"]["check_note"], str(original))
        self.assertEqual(state["threads"]["thread-1"]["receipts"][0]["note"], str(original))
        self.assertEqual(state["custom"], self.state["custom"])
        self.assertEqual(json.loads(self.receipt_path.read_text()), {**self.receipt, "note": str(original)})
        library = Library(self.vault)
        self.assertFalse(library.refresh()["warnings"])
        self.assertEqual(library.overview()["knowledge_count"], 0)
        for relative in originals:
            note = library.get_note("n_" + _encode(relative))
            self.assertTrue(note["archived"])
            self.assertEqual(note["relative"], result["retired_originals"][relative])
        self.assertEqual(library.get_note("n_" + _encode("最早旧标题.md"))["relative"], result["retired_originals"][self.source])
        reused = write_note(self.output, "热血合服旧计算", "# 热血合服旧计算\n\n近三天用户数按去重口径保留。", "original_task",
                            ["https://example.invalid/source"], identity_root=self.vault)
        self.assertTrue(reused["reused"])
        self.assertEqual(Path(reused["note"]), original)
        before = {path: Path(path).read_bytes() for path in json.loads(plan.read_text())["files"] if Path(path).exists()}
        self.assertTrue(curate.apply_plan(self.config, plan)["reused"])
        self.assertEqual(before, {path: Path(path).read_bytes() for path in before})

    def test_retire_rejects_changed_sources_management_and_active_writers(self):
        import os
        for path in (self.source_path, self.state_path, self.output / ".note-index.json", self.layout, self.receipt_path):
            with self.subTest(path=path):
                content, stat = path.read_bytes(), path.stat()
                plan = self.retire_plan()
                path.write_bytes(content + b"\n")
                with self.assertRaisesRegex(curate.CurationError, "计划后发生变化"):
                    curate.apply_plan(self.config, plan)
                self.assertEqual(path.read_bytes(), content + b"\n")
                path.write_bytes(content)
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        plan = self.retire_plan()
        for lock in (self.data / "executor.lock", self.state_path.with_suffix(".lock"), self.output / ".write.lock"):
            with self.subTest(lock=lock), writer_lock(lock), self.assertRaises(ValueError):
                curate.apply_plan(self.config, plan)
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)

    def test_failed_retirement_rolls_back_originals_and_metadata_with_private_backup(self):
        plan = self.retire_plan([self.source, self.target])
        before = json.loads(plan.read_text())["files"]
        real_write, failed = curate._write_bytes, False

        def fail_once(path, content):
            nonlocal failed
            if Path(path) == self.layout and not failed:
                failed = True
                raise OSError("isolated retirement metadata failure")
            return real_write(path, content)

        with patch.object(curate, "_write_bytes", side_effect=fail_once), self.assertRaisesRegex(curate.CurationError, "已恢复原文和管理记录"):
            curate.apply_plan(self.config, plan)
        for path, snapshot in before.items():
            self.assertEqual(Path(path).read_bytes(), curate._bytes(snapshot))
            self.assertEqual(Path(path).stat().st_mtime_ns, snapshot["mtime_ns"])
        backup = self.data / "curation" / json.loads(plan.read_text())["id"]
        self.assertEqual(json.loads((backup / "rollback.json").read_text())["status"], "restored")
        self.assertEqual(len(list((backup / "recovered-originals").rglob("*.md"))), 2)
        self.assertFalse(list((self.vault / ".source-history").rglob("*.md")))

    def test_retire_replay_refuses_modified_history_or_a_recreated_original(self):
        plan = self.retire_plan()
        result = curate.apply_plan(self.config, plan)
        history = self.vault / result["retired_originals"][self.source]
        history.write_bytes(self.source_bytes + b"\n")
        with self.assertRaisesRegex(curate.CurationError, "文件已有改动"):
            curate.apply_plan(self.config, plan)
        history.write_bytes(self.source_bytes)
        self.source_path.write_bytes(b"new manual note")
        with self.assertRaisesRegex(curate.CurationError, "原位置已有新笔记"):
            curate.apply_plan(self.config, plan)
        self.assertEqual(self.source_path.read_bytes(), b"new manual note")

    def test_retire_cli_needs_no_content_and_keeps_unselected_notes(self):
        config_file = self.root / "retire-config.json"
        config_file.write_text(json.dumps(self.config), encoding="utf-8")
        destination = self.root / "retire-plan.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = curate.main(["--config", str(config_file), "plan", "--retire", "--source", self.source,
                                "--plan-out", str(destination)])
        self.assertEqual(code, 0)
        with contextlib.redirect_stdout(io.StringIO()):
            code = curate.main(["--config", str(config_file), "apply", "--plan", str(destination)])
        self.assertEqual(code, 0)
        self.assertFalse(self.source_path.exists())
        self.assertEqual(self.target_path.read_bytes(), self.target_bytes)

    def test_retire_plan_rejects_replacement_content_and_a_tampered_target(self):
        with self.assertRaisesRegex(curate.CurationError, "目标"):
            curate.plan_merge(self.config, self.target, [self.source], retire=True)
        with self.assertRaisesRegex(curate.CurationError, "最终正文"):
            curate.apply_plan(self.config, self.plan())
        plan = self.retire_plan()
        with self.assertRaisesRegex(curate.CurationError, "正文"):
            curate.apply_plan(self.config, plan, self.reviewed)
        value = json.loads(plan.read_text())
        value["target"] = self.target
        plan.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(curate.CurationError, "目标"):
            curate.apply_plan(self.config, plan)
        self.assertTrue(self.source_path.exists())

    def reviewed_additions(self):
        return {"10 项目/项目甲/项目甲邮件发送条件.md": "# 项目甲邮件发送条件\n\n邮件发送前需核对收件范围和资源条件。\n\n审批通过后再执行发送，执行结果单独登记。\n",
                "20 方法/项目甲/项目甲排期检查顺序.md": "# 项目甲排期检查顺序\n\n排期先确认依赖，再核对执行窗口。\n\n每项任务保留负责人和明确截止时间。\n"}

    def test_retirement_creates_reviewed_topics_before_archiving_without_new_checkpoints(self):
        additions = self.reviewed_additions()
        before_tasks = set(json.loads((self.output / ".note-index.json").read_text())["tasks"])
        plan = self.retire_plan(additions=additions)
        saved_plan = json.loads(plan.read_text())
        self.assertEqual(saved_plan["additions"], additions)
        for relative in additions:
            self.assertEqual(saved_plan["files"][str(self.vault / relative)], {"exists": False})
        real_replace = curate.os.replace

        def verify_before_archive(source, destination):
            if Path(source) == self.source_path:
                for relative, text in additions.items():
                    self.assertEqual((self.vault / relative).read_bytes(), text.encode("utf-8"))
            return real_replace(source, destination)

        with patch.object(curate.os, "replace", side_effect=verify_before_archive):
            result = curate.apply_plan(self.config, plan)
        self.assertEqual(result["added_notes"], list(additions))
        self.assertNotIn("canonical", result)
        self.assertEqual(set(json.loads((self.output / ".note-index.json").read_text())["tasks"]), before_tasks)
        original = self.vault / result["retired_originals"][self.source]
        self.assertEqual(load_state(self.state_path)["threads"]["thread-1"]["note"], str(original))
        library = Library(self.vault)
        library.refresh()
        for relative, text in additions.items():
            self.assertEqual(library.get_note("n_" + _encode(relative))["markdown"], text)
        self.assertEqual(library.get_note("n_" + _encode(self.source))["relative"], result["retired_originals"][self.source])
        self.assertTrue(curate.apply_plan(self.config, plan)["reused"])
        changed = self.vault / next(iter(additions))
        changed.write_text(changed.read_text() + "\n人工补充。", encoding="utf-8")
        with self.assertRaisesRegex(curate.CurationError, "文件已有改动"):
            curate.apply_plan(self.config, plan)
        self.assertIn("人工补充", changed.read_text(encoding="utf-8"))

    def test_addition_targets_existing_at_plan_or_created_later_are_never_overwritten(self):
        additions = self.reviewed_additions()
        relative = next(iter(additions))
        target = self.vault / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(b"existing manual note")
        with self.assertRaisesRegex(curate.CurationError, "目标.*存在"):
            self.retire_plan(additions=additions)
        target.unlink()
        plan = self.retire_plan(additions=additions)
        target.write_bytes(b"new manual note after plan")
        with self.assertRaisesRegex(curate.CurationError, "目标.*存在|计划后发生变化"):
            curate.apply_plan(self.config, plan)
        self.assertEqual(target.read_bytes(), b"new manual note after plan")
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)
        self.assertFalse((self.vault / list(additions)[1]).exists())

    def test_addition_transaction_failure_removes_created_drafts_and_restores_sources(self):
        additions = self.reviewed_additions()
        plan = self.retire_plan(additions=additions)
        before = json.loads(plan.read_text())["files"]
        real_write, failed = curate._write_bytes, False

        def fail_once(path, content):
            nonlocal failed
            if Path(path) == self.layout and not failed:
                failed = True
                self.assertFalse(self.source_path.exists())
                self.assertTrue(all((self.vault / relative).is_file() for relative in additions))
                raise OSError("isolated additions publication failure")
            return real_write(path, content)

        with patch.object(curate, "_write_bytes", side_effect=fail_once), self.assertRaisesRegex(curate.CurationError, "已恢复原文和管理记录"):
            curate.apply_plan(self.config, plan)
        for path, snapshot in before.items():
            self.assertEqual(Path(path).exists(), snapshot["exists"])
            if snapshot["exists"]:
                self.assertEqual(Path(path).read_bytes(), curate._bytes(snapshot))
        self.assertTrue(all(not (self.vault / relative).exists() for relative in additions))

    def test_additions_reject_invalid_content_and_hidden_or_escaping_targets_before_planning(self):
        target = next(iter(self.reviewed_additions()))
        destination = self.root / "invalid-additions-plan.json"
        for text in ("# 整理结果\n\n已经完成。", "# 项目甲检查顺序\n\n- 缺少首句概括", "# 项目甲检查顺序\n\n<!-- obsidian-workspace task:copied -->\n\n保留有效步骤。"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                curate.plan_retire(self.config, [self.source], destination, additions={target: text})
            self.assertFalse(destination.exists())
        text = next(iter(self.reviewed_additions().values()))
        for relative in ("../outside.md", ".source-history/new.md", "C:/outside.md"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                curate.plan_retire(self.config, [self.source], destination, additions={relative: text})
        self.assertFalse(destination.exists())
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)

    def test_additions_cannot_claim_a_preserved_old_alias(self):
        text = next(iter(self.reviewed_additions().values()))
        with self.assertRaisesRegex(curate.CurationError, "目标.*旧入口"):
            self.retire_plan(additions={"最早旧标题.md": text})
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)

    def test_an_addition_appearing_at_exclusive_create_is_preserved_and_earlier_drafts_rolled_back(self):
        additions = self.reviewed_additions()
        plan = self.retire_plan(additions=additions)
        first, second = [self.vault / relative for relative in additions]
        real_open, raced = Path.open, False

        def create_before_open(path, mode="r", *args, **kwargs):
            nonlocal raced
            if path == second and mode == "xb" and not raced:
                raced = True
                self.assertTrue(first.is_file())
                second.write_bytes(b"concurrent manual note")
            return real_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", create_before_open), self.assertRaisesRegex(curate.CurationError, "已恢复原文和管理记录"):
            curate.apply_plan(self.config, plan)
        self.assertTrue(raced)
        self.assertFalse(first.exists())
        self.assertEqual(second.read_bytes(), b"concurrent manual note")
        self.assertEqual(self.source_path.read_bytes(), self.source_bytes)


if __name__ == "__main__":
    unittest.main()
