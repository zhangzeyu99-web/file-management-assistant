"""Synthetic regressions for opt-in discovery and narrow automatic summaries."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.incremental import load_state, path_key
from engine.update_scope import selection_input
from tests.test_runtime import fixture, execute_one, page, turn


class UpdateScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime, self.model, self.native = fixture(self.root)
        self.state_path = Path(self.runtime.cfg["state_path"])

    def state(self):
        return load_state(self.state_path)

    def save(self, state):
        self.state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def known(self, key, **fields):
        state = self.state()
        state["threads"][key] = {"updatedAt": 100, "through": 90, "turns": {}, **fields}
        self.save(state)
        self.native.rows.append({"id": key, "updatedAt": 200, "title": key})
        self.native.pages[key] = page([turn("new-" + key, 101, 150)])

    def run_job(self, kind="update", payload=None):
        return execute_one(self.runtime, self.runtime.create(kind, payload or {}))

    def test_preview_only_reads_metadata_excludes_repo_noise_and_never_acknowledges(self):
        self.known("用户日报需求")
        self.known("oversized", pending=True, coverage="partial_oversized")
        self.native.rows.append({"id": "automation", "updatedAt": 1792470000, "automationId": "fixture-auto"})
        sources = self.root / "sources"
        (sources / ".git").mkdir()
        for name in ("README.md", "CHANGELOG.md", "AGENTS.md", "临时.py", "表格.csv", "图片.png"):
            (sources / name).write_text("PRIVATE_BODY", encoding="utf-8")
        (sources / "空白.md").write_bytes(b"")
        good = sources / "断点恢复方法.md"
        good.write_text("这是一份可选择的具体方法。", encoding="utf-8")
        (self.root / "vault" / "新的人工笔记.md").write_text("已有知识不得重复总结", encoding="utf-8")
        state_before = self.state_path.read_bytes()
        notes_before = sorted(str(p) for p in (self.root / "vault").rglob("*.md"))
        with patch.object(self.native, "read_thread", side_effect=AssertionError("preview must not read turns")), \
             patch.object(self.model, "generate", side_effect=AssertionError("preview must not model")), \
             patch.object(self.runtime, "_refresh_library", side_effect=AssertionError("preview must not write navigation")), \
             patch("engine.runtime.extract_path", side_effect=AssertionError("preview must not read bodies")):
            job = self.run_job("update_preview", {"include_files": True})
        self.assertEqual("completed", job["status"], job)
        rows = {row["id"]: row for row in job["result"]["candidates"]}
        self.assertEqual({"用户日报需求", "oversized", str(good.resolve())}, set(rows))
        self.assertTrue(rows["用户日报需求"]["selected"])
        self.assertFalse(rows["oversized"]["selected"])
        self.assertIn("内容过长", rows["oversized"]["group"])
        self.assertFalse(rows[str(good.resolve())]["selected"])
        self.assertTrue(any("仓库说明" in row["reason"] for row in job["result"]["excluded"]))
        self.assertEqual(state_before, self.state_path.read_bytes())
        self.assertEqual(notes_before, sorted(str(p) for p in (self.root / "vault").rglob("*.md")))
        self.assertFalse((self.runtime.data / "runs").exists())
        self.assertFalse((self.runtime.data / "receipts").exists())

    def test_preview_cache_reuses_directory_but_reselects_current_checkpoint(self):
        self.known("first")
        self.known("second")
        self.native.rows[0]["message"] = "BODY_MUST_NOT_CACHE"
        with patch.object(self.native, "list_threads", wraps=self.native.list_threads) as listing:
            first = self.run_job("update_preview")
            state = self.state()
            state["threads"]["first"]["updatedAt"] = 200
            self.save(state)
            second = self.run_job("update_preview", {"include_files": True})
        self.assertEqual(1, listing.call_count)
        self.assertEqual({"first", "second"}, {row["id"] for row in first["result"]["candidates"]})
        self.assertEqual(["second"], [row["id"] for row in second["result"]["candidates"]])
        self.assertFalse(first["result"]["scope"]["directory_cache"]["cached"])
        self.assertTrue(second["result"]["scope"]["directory_cache"]["cached"])
        self.assertNotIn("BODY_MUST_NOT_CACHE", json.dumps(self.runtime._preview_directory))
        self.assertEqual([], self.native.reads)
        self.assertEqual([], self.model.prompts)
        self.assertFalse((self.runtime.data / "runs").exists())

    def test_confirmed_update_never_uses_preview_directory_cache(self):
        self.known("selected")
        with patch.object(self.native, "list_threads", wraps=self.native.list_threads) as listing:
            self.run_job("update_preview")
            self.native.rows = []
            result = self.run_job(payload={"selection": {"threads": ["selected"], "files": []}})
        self.assertEqual(2, listing.call_count)
        self.assertEqual("partial", result["status"])
        self.assertTrue(result["result"]["selection_incomplete"])
        self.assertEqual([], self.native.reads)
        self.assertEqual([], self.model.prompts)

    def test_preview_forced_refresh_and_expiry_fetch_again_and_keep_coverage_warnings(self):
        self.known("selected")
        self.native.rows += [{"id": "history-" + str(i), "updatedAt": 10} for i in range(49)]
        with patch.object(self.native, "list_threads", wraps=self.native.list_threads) as listing:
            first = self.run_job("update_preview")
            cached = self.run_job("update_preview", {"include_files": True})
            self.assertEqual(first["result"]["warnings"], cached["result"]["warnings"])
            self.assertEqual("partial", cached["status"])
            self.assertEqual(1, listing.call_count)
            fresh = self.run_job("update_preview", {"refresh": True})
            self.assertFalse(fresh["result"]["scope"]["directory_cache"]["cached"])
            self.assertEqual(2, listing.call_count)
            self.runtime._preview_directory["expires_at"] = 0
            self.run_job("update_preview")
            self.assertEqual(3, listing.call_count)
        with self.assertRaises(ValueError):
            self.runtime.create("update_preview", {"refresh": "yes"})

    def record_read_error(self, source, *, thread_id=None, cloud=False):
        error = {"source": source, "error": "原生轮次分页读取失败：该线程超过原生读取限制；保留部分覆盖及续读边界。"}
        if thread_id:
            error.update(thread_id=thread_id, error_code="native_oversized")
        job = self.runtime.jobs.create("update", {})
        self.runtime.jobs.claim(self.runtime.owner)
        self.runtime.jobs.update(job["id"], self.runtime.owner, status="partial", result={"errors": [error]})
        saved = self.runtime.jobs.get(job["id"])
        if cloud:
            # A loaded cache is read locally; no cloud API call is allowed here.
            self.runtime._cloud_jobs[saved["id"]] = {"job": saved}
            with self.runtime.jobs.connection() as connection:
                connection.execute("DELETE FROM jobs WHERE id=?", (saved["id"],))
        return saved

    def test_historical_limit_error_restricts_unmarked_state_without_ack_and_allows_explicit_retry(self):
        self.known("large", pending=True, coverage="increment_only")
        self.record_read_error("large")
        before = self.state_path.read_bytes()
        preview = self.run_job("update_preview")
        row = preview["result"]["candidates"][0]
        self.assertEqual("large", row["id"])
        self.assertFalse(row["selected"])
        self.assertIn("内容过长", row["group"])
        ordinary = self.run_job()
        self.assertEqual("completed", ordinary["status"])
        self.assertEqual([], self.native.reads)
        self.assertEqual(before, self.state_path.read_bytes())
        weekly = self.run_job(payload={"weekly_archive": True, "until": "2026-10-20T19:00:00+08:00"})
        self.assertEqual("partial", weekly["status"])
        self.assertTrue(weekly["result"]["checkpoint_debt"])
        explicit = self.run_job(payload={"selection": {"threads": ["large"], "files": []}})
        self.assertEqual("completed", explicit["status"], explicit)
        self.assertEqual([("large", None)], self.native.reads)
        self.assertFalse(self.state()["threads"]["large"]["pending"])
        self.assertEqual(set(), self.runtime._known_restricted_threads(self.native.rows, self.state()))

    def test_legacy_same_title_errors_do_not_exclude_ambiguous_threads_but_ids_from_cloud_do(self):
        self.known("one", pending=True)
        self.known("two", pending=True)
        for row in self.native.rows:
            row["title"] = "相同标题"
        self.record_read_error("相同标题")
        ambiguous = self.run_job("update_preview")
        self.assertTrue(all(row["selected"] for row in ambiguous["result"]["candidates"]))
        self.record_read_error("相同标题", thread_id="two", cloud=True)
        precise = self.run_job("update_preview")
        selected = {row["id"]: row["selected"] for row in precise["result"]["candidates"]}
        self.assertEqual({"one": True, "two": False}, selected)
        self.assertEqual([], self.native.reads)
        self.assertEqual([], self.model.prompts)

    def test_new_read_limit_errors_include_thread_id_and_prevent_next_default_repeat(self):
        from bridge import BridgeError
        self.known("limited", pending=True, coverage="increment_only")
        self.native.pages["limited"] = BridgeError("native_oversized", "该线程超过原生读取限制；保留部分覆盖及续读边界。")
        before = self.state_path.read_bytes()
        first = self.run_job()
        self.assertEqual("partial", first["status"], first)
        error = first["result"]["errors"][0]
        self.assertEqual("limited", error["thread_id"])
        self.assertEqual("native_oversized", error["error_code"])
        second = self.run_job()
        self.assertEqual("completed", second["status"])
        self.assertEqual([("limited", None)], self.native.reads)
        self.assertEqual(before, self.state_path.read_bytes())
        preview = self.run_job("update_preview")
        self.assertFalse(preview["result"]["candidates"][0]["selected"])

    def test_named_outstanding_running_and_interrupted_are_not_errors_or_acknowledged(self):
        self.known("所选进展")
        self.native.pages["所选进展"] = page([
            turn("running", 170, status="inProgress", text="PRIVATE_PENDING_BODY"),
            turn("stopped", 160, status="interrupted", text="PRIVATE_INTERRUPTED_BODY"),
            turn("cancelled", 155, status="cancelled", text="PRIVATE_CANCELLED_BODY"),
            turn("done", 101, 150, text="新增已完成事实"),
        ])
        first = self.run_job(payload={"selection": {"threads": ["所选进展"], "files": []}})
        self.assertEqual("partial", first["status"], first)
        self.assertEqual([], first["result"]["errors"])
        self.assertEqual(1, len(first["result"]["notes"]))
        outstanding = first["result"]["outstanding"][0]
        self.assertEqual("所选进展", outstanding["thread_id"])
        self.assertEqual("所选进展", outstanding["title"])
        by_id = {row["turn_id"]: row for row in outstanding["turns"]}
        self.assertEqual({"running", "stopped", "cancelled"}, set(by_id))
        self.assertEqual("inProgress", by_id["running"]["status"])
        self.assertEqual("running", by_id["running"]["reason_code"])
        self.assertEqual("interrupted", by_id["stopped"]["reason_code"])
        self.assertEqual("cancelled", by_id["cancelled"]["reason_code"])
        self.assertIn("执行中", outstanding["reason"])
        self.assertIn("中断", outstanding["reason"])
        self.assertNotIn("PRIVATE_", json.dumps(outstanding))
        self.assertEqual({"done"}, set(self.state()["threads"]["所选进展"]["turns"]))
        retry = execute_one(self.runtime, self.runtime.retry_job(first["id"]))
        self.assertEqual("partial", retry["status"], retry)
        self.assertEqual(first["result"]["notes"], retry["result"]["notes"])
        self.assertEqual(first["result"]["outstanding"], retry["result"]["outstanding"])
        self.assertEqual(1, len(self.model.prompts))

    def test_named_outstanding_distinguishes_truncated_turn_from_unread_pages(self):
        self.known("截断资料")
        self.native.pages["截断资料"] = page([
            turn("cut", 160, 180, text="PRIVATE_TRUNCATED_BODY", truncated=True),
            turn("done", 101, 150),
        ])
        result = self.run_job(payload={"selection": {"threads": ["截断资料"], "files": []}})
        detail = result["result"]["outstanding"][0]
        self.assertEqual("completed", detail["turns"][0]["status"])
        self.assertEqual("truncated", detail["turns"][0]["reason_code"])
        self.assertNotIn("PRIVATE_TRUNCATED_BODY", json.dumps(detail))
        self.assertNotIn("cut", self.state()["threads"]["截断资料"]["turns"])
        self.known("分页资料")
        self.native.pages["分页资料"] = page([turn("ready", 101, 150)])
        self.native.pages["分页资料"]["page"]["hasMore"] = True
        paged = self.run_job(payload={"selection": {"threads": ["分页资料"], "files": []}})
        detail = paged["result"]["outstanding"][0]
        self.assertEqual("分页资料", detail["title"])
        self.assertEqual([], detail["turns"], "unread pages must not invent turn IDs")
        self.assertEqual("pagination_incomplete", detail["reasons"][0]["reason_code"])
        self.assertIn("分页", detail["reason"])
        self.assertEqual({"ready"}, set(self.state()["threads"]["分页资料"]["turns"]))
        self.assertEqual(1, len(paged["result"]["notes"]))

    def test_default_update_never_scans_files_or_feishu_and_only_models_user_completed_turns(self):
        self.known("用户日报需求")
        self.known("自动例行")
        automatic = self.native.pages["自动例行"]["turns"][0]
        automatic["items"].insert(0, {"type": "userMessage", "text": "Automation: 日报\nAutomation ID: fixture-auto"})
        self.native.rows.append({"id": "explicit-auto", "updatedAt": 1792470000, "source": "automation"})
        before = self.state()
        with patch("engine.runtime.plan_local", side_effect=AssertionError("default must not discover files")), \
             patch("engine.feishu.FeishuSource", side_effect=AssertionError("default must not discover Feishu")):
            result = self.run_job()
        self.assertEqual("completed", result["status"], result)
        self.assertEqual(1, len(self.model.prompts))
        self.assertIn("用户日报需求", self.model.prompts[0])
        self.assertNotIn("Automation ID", self.model.prompts[0])
        self.assertNotIn("explicit-auto", [item[0] for item in self.native.reads])
        state = self.state()
        self.assertEqual("automation", state["threads"]["自动例行"]["source_type"])
        self.assertEqual("source_only", state["threads"]["自动例行"]["content_status"])
        self.assertEqual(before["files"], state["files"])
        self.assertEqual(before["feishu"], state["feishu"])
        self.assertEqual(1, len(result["result"]["notes"]))
        self.run_job()
        self.assertEqual(1, len(self.model.prompts))

    def test_explicit_thread_success_is_not_partial_because_of_unselected_history_or_list_limit(self):
        self.known("selected")
        self.known("unselected", pending=True, coverage="partial")
        self.native.rows += [{"id": "history-" + str(i), "updatedAt": 10} for i in range(48)]
        before = copy.deepcopy(self.state()["threads"]["unselected"])
        result = self.run_job(payload={"selection": {"threads": ["selected"], "files": []}})
        self.assertEqual("completed", result["status"], result)
        self.assertEqual([("selected", None)], self.native.reads)
        self.assertEqual(before, self.state()["threads"]["unselected"])
        self.assertEqual(0, result["result"]["sources"]["threads"]["historical_gap"])
        self.assertTrue(result["result"]["scope"]["discovery_warnings"])

    def test_missing_selected_thread_is_partial_without_ack(self):
        before = self.state_path.read_bytes()
        result = self.run_job(payload={"selection": {"threads": ["missing"], "files": []}})
        self.assertEqual("partial", result["status"], result)
        self.assertTrue(result["result"]["selection_incomplete"])
        self.assertEqual(before, self.state_path.read_bytes())

    def test_files_require_explicit_selection_and_revalidate_roots_and_baseline(self):
        sources = self.root / "sources"
        chosen, unchosen, old = [sources / name for name in ("方法甲.md", "方法乙.md", "旧资料.md")]
        outside = self.root / "不允许的资料.md"
        for file in (chosen, unchosen, old, outside):
            file.write_text("具体方法：失败时保留已完成记录，只重做失败步骤。", encoding="utf-8")
        state = self.state()
        state["files"][path_key(old)] = {"baseline": True}
        self.save(state)
        with patch.object(self.native, "list_threads", side_effect=AssertionError("empty thread selection must not list")):
            result = self.run_job(payload={"selection": {"threads": [], "files": [str(chosen), str(old), str(outside)]}})
        self.assertEqual("partial", result["status"], result)
        self.assertEqual(1, result["result"]["counts"]["files"])
        self.assertEqual(1, len(self.model.prompts))
        self.assertNotIn(path_key(unchosen), self.state()["files"])
        self.assertNotIn(path_key(outside), self.state()["files"])
        self.assertEqual({"baseline": True}, self.state()["files"][path_key(old)])
        self.assertIn(path_key(chosen), self.state()["files"])

    def test_retry_freezes_selection_and_keeps_prior_success_without_acknowledging_unselected(self):
        a, b, c = [self.root / "sources" / (name + ".md") for name in ("方法甲", "方法乙", "未选方法")]
        for file in (a, b, c):
            file.write_text("具体方法：失败时保留已完成记录，只重做失败步骤。", encoding="utf-8")
        original = self.runtime._note
        def fail_b(title, *args, **kwargs):
            if title == b.stem:
                raise OSError("fixture write failed")
            return original(title, *args, **kwargs)
        with patch.object(self.runtime, "_note", side_effect=fail_b):
            first = self.run_job(payload={"selection": {"threads": [], "files": [str(a), str(b)]}})
        self.assertEqual("partial", first["status"], first)
        retry = self.run_job(payload={"retry_of": first["id"], "selection": {"threads": [], "files": [str(c)]}})
        self.assertEqual("completed", retry["status"], retry)
        self.assertEqual(2, len(self.model.prompts))
        self.assertIn(first["result"]["notes"][0], retry["result"]["notes"])
        self.assertEqual(2, retry["result"]["counts"]["files"])
        self.assertNotIn(path_key(c), self.state()["files"])

    def test_legacy_retry_preserves_saved_cards_but_no_longer_discovers_files(self):
        first = self.runtime.create("update", {})
        path, journal = self.runtime._journal(first)
        journal["items"] = {"file:old-source": {"done": True, "card": {"id": "old-note", "title": "已保存方法"}}}
        journal["result"] = {"errors": [{"source": "legacy file", "error": "old failure"}], "partial": True}
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(journal), encoding="utf-8")
        with patch("engine.runtime.plan_local", side_effect=AssertionError("legacy retry must narrow files")):
            result = execute_one(self.runtime, first)
        self.assertEqual("completed", result["status"], result)
        self.assertEqual(1, result["result"]["counts"]["files"])
        self.assertEqual("old-note", result["result"]["notes"][0]["id"])
        self.assertEqual([], self.model.prompts)

    def test_oversized_defaults_to_unselected_even_after_metadata_changes_but_can_be_opted_in(self):
        self.known("large", pending=True, coverage="partial_oversized")
        before = copy.deepcopy(self.state()["threads"]["large"])
        ordinary = self.run_job()
        self.assertEqual("completed", ordinary["status"], ordinary)
        self.assertEqual([], self.native.reads)
        self.assertEqual(before, self.state()["threads"]["large"])
        self.assertEqual(1, ordinary["result"]["scope"]["default_excluded"][0]["count"])
        weekly = self.run_job(payload={"weekly_archive": True, "until": "2026-10-20T19:00:00+08:00"})
        self.assertEqual("partial", weekly["status"], weekly)
        self.assertTrue(weekly["result"]["checkpoint_debt"])
        self.assertFalse((self.runtime.data / "weekly-archive.json").exists())
        explicit = self.run_job(payload={"selection": {"threads": ["large"], "files": []}})
        self.assertEqual("completed", explicit["status"], explicit)
        self.assertEqual([("large", None)], self.native.reads)
        self.assertFalse(self.state()["threads"]["large"]["pending"])

    def test_new_thread_note_does_not_inherit_an_unrelated_previous_note_as_source(self):
        self.known("new-topic")
        state = self.state()
        old = self.root / "vault" / "热血测试方案.md"
        state["threads"]["new-topic"]["note"] = str(old)
        self.save(state)
        result = self.run_job()
        self.assertEqual("completed", result["status"], result)
        note = Path(result["result"]["notes"][0]["path"]).read_text(encoding="utf-8")
        self.assertIn("codex://threads/new-topic", note)
        self.assertNotIn(old.name, note)
        self.assertEqual(1, note.count("codex://threads/"))
        self.assertIn("跨主题时不得继承旧事实", self.model.prompts[0])

    def test_weekly_cannot_accept_a_handpicked_subset_as_whole_week(self):
        with self.assertRaisesRegex(ValueError, "手选子集"):
            self.runtime.create("update", {"weekly_archive": True,
                "selection": {"threads": [], "files": []}})
        self.assertEqual([], self.runtime.jobs.list())

    def test_preview_validation_and_missing_baseline_never_read_history(self):
        for value in ({"selection": None}, {"selection": {"threads": [], "files": ["relative.md"]}},
                      {"selection": {"threads": "all", "files": []}}):
            with self.assertRaises(ValueError):
                selection_input(value)
        with self.assertRaises(ValueError):
            self.runtime.create("update_preview", {"include_files": "yes"})
        state = self.state()
        state.pop("baseline_at")
        self.save(state)
        self.native.rows = [{"id": "unknown", "updatedAt": 1792470000}]
        preview = self.run_job("update_preview")
        self.assertEqual("partial", preview["status"], preview)
        self.assertEqual([], preview["result"]["candidates"])
        self.assertEqual([], self.native.reads)
        self.assertEqual([], self.model.prompts)


if __name__ == "__main__":
    unittest.main()
