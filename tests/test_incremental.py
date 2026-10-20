import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine import incremental as flow
from engine.ingest import write_note


def fixture_state():
    return {"version": 1, "baseline": "delivered-history", "unknown_future_field": {"keep": True},
            "files": {}, "feishu": {}, "threads": {
                "old": {"updatedAt": 100, "through": 90, "turns": {"done": ["completed", 80]},
                        "coverage": "partial_oversized", "resume_cursor": "keep-cursor", "historical_reference": True}}}


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state_path = self.root / "state.json"
        self.state = fixture_state()
        self.save()
        self.notes = self.root / "generated"
        self.store = flow.CheckpointStore(self.state_path, self.root / "receipts", [self.notes])

    def save(self):
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")

    def note(self, task="task-a", text="真实新增结果"):
        return write_note(self.notes, "新增结果", text, task, ["thread:old"])

    def test_no_empty_initialization_and_unknown_fields_survive(self):
        with self.assertRaises(flow.IncrementalError):
            flow.load_state(self.root / "absent.json")
        turn = {"id": "later", "status": "completed", "startedAt": 110, "completedAt": 120}
        note = self.note()
        result = self.store.ack({"threads": [{"id": "old", "turns": [turn], "updatedAt": 125,
                                            "complete": False, "pending": True, **note}]})
        self.assertTrue(result["ok"])
        state = flow.load_state(self.state_path)
        self.assertEqual(state["version"], 1)
        self.assertEqual(state["unknown_future_field"], self.state["unknown_future_field"])
        for field in ("coverage", "resume_cursor", "historical_reference", "updatedAt", "through"):
            self.assertEqual(state["threads"]["old"][field], self.state["threads"]["old"][field])
        self.assertEqual(state["threads"]["old"]["turns"]["later"], ["completed", 120])

    def test_local_listing_never_reads_bodies_and_excludes_generated_runtime(self):
        source = self.root / "sources"
        source.mkdir()
        old, new = source / "old.md", source / "new.md"
        old.write_text("旧文件已修改，仍不能重读", encoding="utf-8")
        new.write_text("新资料", encoding="utf-8")
        (source / "tokens.txt").write_text("do not read credentials", encoding="utf-8")
        self.state["files"][flow.path_key(old)] = {"baseline": True}
        for folder in (source / "old-generated", source / "new-generated", source / "runtime", source / ".codex"):
            folder.mkdir()
            (folder / "generated.md").write_text("不可再总结", encoding="utf-8")
        config = {"watch_roots": [{"name": "test", "path": str(source), "max_depth": 2}],
                  "knowledge_root": str(source / "old-generated"), "runtime_root": str(source / "runtime")}
        with patch.object(Path, "read_text", side_effect=AssertionError("body read during plan")), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("body read during plan")):
            plan = flow.plan_local(self.state, config, generated_roots=[source / "new-generated"], memory_roots=[])
        self.assertEqual([row["path"] for row in plan["files"]], [str(new.resolve())])
        self.assertEqual(plan["skipped"], 1)
        self.assertEqual(plan["source_status"]["threads"], "not_checked")

    def test_watch_depth_and_missing_source_coverage_are_honest(self):
        source = self.root / "sources"
        nested = source / "nested"
        nested.mkdir(parents=True)
        (source / "a.txt").write_text("one", encoding="utf-8")
        (nested / "b.txt").write_text("two", encoding="utf-8")
        config = {"watch_roots": [{"path": str(source), "max_depth": 0}, {"path": str(self.root / "missing")}]}
        plan = flow.plan_local(self.state, config, memory_roots=[])
        self.assertEqual(len(plan["files"]), 1)
        self.assertEqual(plan["source_status"]["local"], "partial")
        self.assertEqual(plan["sources"][1]["status"], "unavailable")

    def test_watch_limit_continuation_and_unlimited_markdown_vault(self):
        source = self.root / "sources"
        nested = source / "a"
        nested.mkdir(parents=True)
        for path in (source / "a.txt", source / "z.md", nested / "b.md", nested / "c.md"):
            path.write_text("new", encoding="utf-8")
        config = {"watch_roots": [{"path": str(source), "max_depth": 2, "max_files": 2}]}
        first = flow.plan_local(self.state, config, memory_roots=[])
        self.assertEqual(len(first["files"]), 2)
        self.assertEqual(first["sources"][0]["status"], "partial")
        # Cursor survives deletion of the previous final file.
        (source / "z.md").unlink()
        second = flow.plan_local(self.state, config, memory_roots=[], cursors=first["resume_cursors"])
        self.assertEqual({Path(row["path"]).name for row in second["files"]}, {"b.md", "c.md"})
        third = flow.plan_local(self.state, config, memory_roots=[], cursors=second["resume_cursors"])
        self.assertEqual(third["sources"][0]["status"], "checked")
        self.assertEqual(third["files"], [])
        config["obsidian_vault"] = str(source)
        all_vault = flow.plan_local(self.state, config, memory_roots=[])
        self.assertEqual(all_vault["sources"][1]["max_files"], None)
        self.assertEqual(all_vault["sources"][1]["status"], "checked")
        self.assertEqual({Path(row["path"]).name for row in all_vault["files"]}, {"a.txt", "b.md", "c.md"})
        missing = flow.plan_local(self.state, {"watch_roots": [{"path": str(self.root / "missing")}]}, memory_roots=[])
        self.assertEqual(missing["source_status"]["local"], "unavailable")

    def test_timestamp_units_and_representation_do_not_replay_completed_turn(self):
        seconds = 1792468803
        self.assertEqual(flow.stamp(seconds), flow.stamp(seconds * 1000))
        self.assertEqual(flow.stamp(str(seconds)), flow.stamp(str(seconds * 1000)))
        self.state["threads"]["old"].update({"updatedAt": seconds, "through": seconds,
                                             "turns": {"done": ["completed", seconds]}})
        self.assertEqual(flow.select_plan(self.state, threads=[{"id": "old", "updatedAt": seconds * 1000}])["threads"], [])
        turns = [{"id": "done", "status": "completed", "startedAt": (seconds - 1) * 1000, "completedAt": seconds * 1000}]
        self.assertEqual(flow.select_turns(self.state, "old", turns)["turns"], [])
        self.assertEqual(self.state["threads"]["old"]["turns"]["done"], ["completed", seconds])

    def test_check_only_receipt_keeps_real_note_and_oversized_unchanged_is_skipped(self):
        self.state["threads"]["old"].update({"note": "original-summary.md", "pending": True,
                                             "coverage": "partial_oversized_turn"})
        self.save()
        self.assertEqual(flow.select_plan(self.state, threads=[{"id": "old", "updatedAt": 100}])["threads"], [])
        self.assertEqual(len(flow.select_plan(self.state, threads=[{"id": "old", "updatedAt": 101}])["threads"]), 1)
        check = self.note("check")
        result = self.store.ack({"threads": [{"id": "old", "updatedAt": 110, "complete": True,
                                              "check_only": True, "turns": [], **check}]})
        self.assertTrue(result["ok"])
        saved = flow.load_state(self.state_path)["threads"]["old"]
        self.assertEqual(saved["note"], "original-summary.md")
        self.assertEqual(saved["through"], 90)
        self.assertEqual(saved["updatedAt"], 110)
        self.assertEqual(saved["coverage"], "partial_oversized_turn")
        self.assertEqual(result["committed"][0]["check_note"], check["note"])
        self.assertNotIn("note", result["committed"][0])
        retry = self.store.ack({"threads": [{"id": "old", "updatedAt": 110, "complete": True,
                                             "check_only": True, "turns": [], **check}]})
        self.assertEqual(result["committed"][0]["id"], retry["committed"][0]["id"])

    def test_unknown_old_threads_remain_history_gaps_without_checkpoint_mutation(self):
        original = copy.deepcopy(self.state)
        rows = [{"id": "old", "updatedAt": 101}, {"id": "unregistered-old", "updatedAt": 90},
                {"id": "at-boundary", "updatedAt": 100}, {"id": "newly-seen", "updatedAt": 110},
                {"id": "missing-time"}]
        plan = flow.select_plan(self.state, threads=rows, boundary=100)
        self.assertEqual(plan["historical_gap"], 2)
        self.assertEqual(plan["metadata_gap"], 1)
        self.assertEqual([row["id"] for row in plan["threads"]], ["old", "newly-seen"])
        self.assertEqual(plan["threads"][0]["after"], 90)  # Its own accepted coverage wins.
        self.assertEqual(plan["threads"][1]["after"], 100)
        self.assertEqual(plan["threads"][1]["coverage"], "increment_only")
        self.assertEqual(self.state, original)
        self.assertNotIn("unregistered-old", self.state["threads"])

    def test_unknown_thread_turns_use_supplied_baseline_but_keep_late_completion(self):
        turns = [{"id": "historical", "status": "completed", "startedAt": 50, "completedAt": 60},
                 {"id": "at-boundary", "status": "completed", "startedAt": 90, "completedAt": 100},
                 {"id": "late-completion", "status": "completed", "startedAt": 95, "completedAt": 105},
                 {"id": "new", "status": "completed", "startedAt": 101, "completedAt": 109},
                 {"id": "running", "status": "inProgress", "startedAt": 110}]
        chosen = flow.select_turns(self.state, "newly-seen", turns, after=100)
        self.assertEqual([turn["id"] for turn in chosen["turns"]], ["late-completion", "new"])
        self.assertEqual([turn["id"] for turn in chosen["pending"]], ["running"])
        # A larger global boundary cannot erase a known thread's unfinished range.
        own = flow.select_turns(self.state, "old", [turns[1]], after=1000)
        self.assertEqual([turn["id"] for turn in own["turns"]], ["at-boundary"])

    def test_increment_only_receipt_keeps_baseline_floor_after_late_completion(self):
        note = self.note()
        late = {"id": "late", "status": "completed", "startedAt": 95, "completedAt": 105}
        result = self.store.ack({"threads": [{"id": "newly-seen", "updatedAt": 110, "after": 100,
            "coverage": "increment_only", "complete": True, "turns": [late], **note}]})
        self.assertTrue(result["ok"])
        saved = flow.load_state(self.state_path)
        self.assertEqual(saved["threads"]["newly-seen"]["through"], 100)
        self.assertEqual(saved["threads"]["newly-seen"]["coverage"], "increment_only")
        self.assertEqual(saved["threads"]["newly-seen"]["incremental_boundary"], 100)
        historical = {"id": "unregistered-history", "status": "completed", "startedAt": 98, "completedAt": 99}
        self.assertEqual(flow.select_turns(saved, "newly-seen", [historical])["turns"], [])

    def test_metadata_gate_and_later_completion(self):
        rows = [{"id": "old", "updatedAt": 100}, {"id": "new", "updatedAt": 130}]
        self.assertEqual([row["id"] for row in flow.select_plan(self.state, threads=rows)["threads"]], ["new"])
        rows[0]["updatedAt"] = 150
        self.assertEqual(flow.select_plan(self.state, threads=rows)["threads"][0]["action"], "续聊检查")
        turns = [
            {"id": "done", "startedAt": 70, "completedAt": 80, "status": "completed"},
            {"turnId": "late", "started_at": 85, "completed_at": 120, "status": "completed"},
            {"id": "running", "startedAt": 150, "status": "inProgress"},
            {"id": "missing-date", "startedAt": 160, "status": "completed"},
            {"id": "failed", "startedAt": 170, "completedAt": 180, "status": "failed"},
        ]
        selected = flow.select_turns(self.state, "old", turns)
        self.assertEqual([t["id"] for t in selected["turns"]], ["late"])
        self.assertEqual(len(selected["pending"]), 3)
        self.assertNotIn("id", turns[1])  # The native input is not mutated.

    def test_failed_readback_and_running_turn_leave_checkpoint_unchanged(self):
        before = self.state_path.read_bytes()
        note = self.note()
        Path(note["note"]).write_text("人工修改", encoding="utf-8")
        result = self.store.ack({"files": [{"path": str(self.root / "new.txt"), **note}]})
        self.assertFalse(result["ok"])
        self.assertEqual(self.state_path.read_bytes(), before)
        note = self.note("task-b")
        result = self.store.ack({"threads": [{"id": "old", "turns": [{"id": "running", "startedAt": 110, "status": "inProgress"}], **note}]})
        self.assertFalse(result["ok"])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_individual_receipts_idempotence_and_new_output_not_rediscovered(self):
        note = self.note()
        path = str(self.root / "input.txt")
        receipt = {"files": [{"path": path, **note}, {"path": "bad", "note": str(self.notes / "missing.md"), "expected_text": "missing"}]}
        result = self.store.ack(receipt)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["committed"]), 1)
        first = result["committed"][0]["id"]
        again = self.store.ack({"files": [receipt["files"][0]]})
        self.assertEqual(again["committed"][0]["id"], first)
        state = flow.load_state(self.state_path)
        self.assertEqual(len(state["files"][flow.path_key(path)]["receipts"]), 1)
        config = {"watch_roots": [{"path": str(self.root), "max_depth": 4}]}
        plan = flow.plan_local(state, config, generated_roots=[self.notes], runtime_roots=[self.root], memory_roots=[])
        self.assertEqual(plan["files"], [])

    def test_interrupted_checkpoint_write_preserves_original(self):
        before = self.state_path.read_bytes()
        note = self.note()
        real = flow.atomic_json
        def fail_checkpoint(path, value):
            if Path(path) == self.state_path:
                raise OSError("injected replace failure")
            return real(path, value)
        with patch.object(flow, "atomic_json", side_effect=fail_checkpoint):
            result = self.store.ack({"files": [{"path": str(self.root / "new.txt"), **note}]})
        self.assertFalse(result["ok"])
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertFalse(self.state_path.with_suffix(".lock").exists())

    def test_complete_checkpoint_and_active_writer_conflict(self):
        note = self.note()
        receipt = {"threads": [{"id": "old", "updatedAt": 130, "turns": [{"id": "new", "startedAt": 110, "completedAt": 125, "status": "completed"}], "complete": True, "pending": False, **note}]}
        with flow.writer_lock(self.state_path.with_suffix(".lock")):
            with self.assertRaises(flow.IncrementalError):
                self.store.ack(receipt)
        self.assertTrue(self.store.ack(receipt)["ok"])
        state = flow.load_state(self.state_path)
        self.assertEqual(flow.select_plan(state, threads=[{"id": "old", "updatedAt": 130}])["threads"], [])
        self.assertEqual(state["threads"]["old"]["coverage"], "partial_oversized")

    def test_dead_process_lock_recovery_and_receipt_finish_failure(self):
        lock = self.state_path.with_suffix(".lock")
        lock.write_text(json.dumps({"pid": 123456, "owner": "dead"}), encoding="utf-8")
        note = self.note()
        real = flow.atomic_json
        def fail_marker(path, value):
            if Path(path).parent == self.root / "receipts" and value.get("checkpoint_committed"):
                raise OSError("injected receipt finalization failure")
            return real(path, value)
        with patch.object(flow, "_process_alive", return_value=False), patch.object(flow, "atomic_json", side_effect=fail_marker):
            result = self.store.ack({"files": [{"path": str(self.root / "new.txt"), **note}]})
        self.assertTrue(result["ok"])
        self.assertTrue(result["warnings"][0]["checkpoint_committed"])
        self.assertIn(flow.path_key(self.root / "new.txt"), flow.load_state(self.state_path)["files"])
        self.assertFalse(lock.exists())

    @unittest.skipUnless(os.name == "nt", "Windows retained process handle regression")
    def test_exited_process_with_retained_handle_is_not_an_active_writer(self):
        child = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.buffer.read(1)"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        lock = self.root / "held-process.lock"
        try:
            lock.write_text(json.dumps({"pid": child.pid, "owner": "child"}), encoding="utf-8")
            self.assertTrue(flow._process_alive(child.pid))
            with self.assertRaises(flow.IncrementalError):
                with flow.writer_lock(lock):
                    self.fail("An active process lock must not be stolen")
            self.assertEqual(json.loads(lock.read_text(encoding="utf-8"))["owner"], "child")
            child.communicate(b"\n", timeout=10)
            self.assertEqual(child.returncode, 0)
            self.assertGreater(int(child._handle), 0)  # Launcher still owns the exited process object.
            self.assertFalse(flow._process_alive(child.pid))
            with flow.writer_lock(lock):
                self.assertEqual(json.loads(lock.read_text(encoding="utf-8"))["pid"], os.getpid())
            self.assertFalse(lock.exists())
        finally:
            if child.poll() is None:
                child.communicate(b"\n", timeout=10)

    def test_checkpoint_keeps_existing_bom_and_newlines(self):
        self.state_path.write_bytes(b"\xef\xbb\xbf" + (json.dumps(self.state, indent=2) + "\n").replace("\n", "\r\n").encode("utf-8"))
        result = self.store.ack({"files": [{"path": str(self.root / "new.txt"), **self.note()}]})
        self.assertTrue(result["ok"])
        saved = self.state_path.read_bytes()
        self.assertTrue(saved.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", saved)
        self.assertNotIn(b"\n", saved.replace(b"\r\n", b""))


if __name__ == "__main__":
    unittest.main()
