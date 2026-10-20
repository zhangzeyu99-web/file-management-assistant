"""Cross-directory offline migration, using private temporary fixture data only."""
import copy
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from engine.incremental import load_state, path_key, plan_local
from engine.library import Library
from engine.migration import MigrationError, export_bundle, import_bundle, inspect_bundle


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="obsidian-migration-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old, self.new = self.root / "old-machine", self.root / "new-machine"
        self.vault, self.data = self.old / "vault", self.old / "data"
        self.sources = self.old / "sources"
        for folder in (self.vault, self.data / "receipts", self.sources, self.old / "baseline"):
            folder.mkdir(parents=True)
        self.note = self.vault / "人工笔记.md"
        self.note_bytes = "# 人工笔记\r\n\r\n迁移验收术语：保留正文与人工增补。\r\n".encode("utf-8")
        self.note.write_bytes(self.note_bytes)
        (self.vault / "cover.png").write_bytes(b"fixture-attachment")
        (self.vault / ".env").write_text("SECRET_MUST_NOT_EXPORT", encoding="utf-8")
        (self.vault / "auth.json").write_text('{"token":"SECRET_MUST_NOT_EXPORT"}', encoding="utf-8")
        raw = self.vault / ".codex" / "sessions" / "raw.jsonl"
        raw.parent.mkdir(parents=True)
        raw.write_text("RAW_SESSION_MUST_NOT_EXPORT", encoding="utf-8")
        self.source = self.sources / "已总结.txt"
        self.source.write_text("不要重新模型总结此来源", encoding="utf-8")
        check = self.data / "runs" / "old-job" / "private-check.md"
        check.parent.mkdir(parents=True)
        check.write_text("# 来源已检查，无新增完成轮次。", encoding="utf-8")
        (check.parent / "journal.json").write_text("TASK_HISTORY_MUST_NOT_EXPORT", encoding="utf-8")
        (check.parent / "model.md").write_text("MODEL_CACHE_MUST_NOT_EXPORT", encoding="utf-8")
        (self.data / "service-token.dpapi").write_bytes(b"SECRET_MUST_NOT_EXPORT")
        (self.data / "jobs.sqlite").write_bytes(b"QUEUE_MUST_NOT_EXPORT")
        (self.data / "uploads").mkdir()
        (self.data / "uploads" / "pending.txt").write_text("UPLOAD_MUST_NOT_EXPORT", encoding="utf-8")
        self.receipt = {"id": "receipt1", "lane": "threads", "source": "thread",
                        "check_note": str(check), "verifiedAt": "2026-10-20T12:00:00+08:00"}
        self.file_receipt = {"id": "file-receipt", "lane": "files", "source": path_key(self.source),
                             "note": str(self.note), "verifiedAt": "2026-10-20T12:00:00+08:00"}
        (self.data / "receipts" / "receipt1.json").write_text(json.dumps(self.receipt), encoding="utf-8")
        (self.data / "receipts" / "file-receipt.json").write_text(json.dumps(self.file_receipt), encoding="utf-8")
        (self.data / "source-checks.json").write_text('{"feishu":"2026-10-20T12:00:00+08:00"}', encoding="utf-8")
        self.state = {
            "version": 1, "baseline": str(self.old / "baseline"),
            "files": {path_key(self.source): {"path": str(self.source), "baseline": True, "receipts": [self.file_receipt]},
                      path_key(self.note): {"path": str(self.note), "baseline": True}},
            "threads": {"thread": {"updatedAt": 100, "through": 90, "turns": {"done": ["completed", 80]},
                                  "coverage": "partial_oversized", "pending": True,
                                  "historical_reference": True, "note": str(self.note),
                                  "receipts": [self.receipt]}},
            "feishu": {"token1": {"baseline": True}}, "custom_v1_field": {"keep": [1, "原值"]},
        }
        self.state_path = self.data / "state.json"
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
        baseline = self.old / "baseline"
        (baseline / "run-manifest.json").write_text('{"completed_at":"2026-10-20T10:00:00+08:00"}', encoding="utf-8")
        (baseline / "feishu-video-owner-page-1.json").write_text(
            '{"data":{"results":[{"result_meta":{"owner_id":"ou_fixture_video"}}]}}', encoding="utf-8")
        self.config = {"data_root": str(self.data), "state_path": str(self.state_path),
                       "obsidian_vault": str(self.vault), "output_root": str(self.vault / "generated"),
                       "old_output_roots": [], "memory_roots": [],
                       "watch_roots": [{"name": "资料", "path": str(self.sources), "max_depth": 2, "max_files": 50}],
                       "cloud_url": "https://fixture.invalid", "app_secret": "SECRET_MUST_NOT_EXPORT",
                       "port": 8767, "web_port": 5199}
        self.config_path = self.old / "private.local.json"
        self.config_path.write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")
        self.bundle = self.root / "transfer.zip"
        self.mappings = [{"from": str(self.old), "to": str(self.new)}]
        self.config_out = self.new / "config.local.json"

    def export(self):
        return export_bundle(self.config_path, self.bundle)

    def restore(self, **kwargs):
        return import_bundle(self.bundle, self.mappings, self.config_out, **kwargs)

    def test_path_relocation_preserves_notes_checkpoint_and_no_old_source_is_new(self):
        before = self.state_path.read_bytes()
        self.export()
        self.assertEqual(self.state_path.read_bytes(), before)
        summary = inspect_bundle(self.bundle)
        self.assertEqual(summary["config"]["cloud_url"], "")
        self.assertNotIn("app_secret", summary["config"])
        self.assertEqual(summary["config"]["feishu_video_owner"], "ou_fixture_video")
        with zipfile.ZipFile(self.bundle) as archive:
            contents = b"".join(archive.read(name) for name in archive.namelist())
            for forbidden in (b"SECRET_MUST_NOT_EXPORT", b"RAW_SESSION_MUST_NOT_EXPORT",
                              b"TASK_HISTORY_MUST_NOT_EXPORT", b"MODEL_CACHE_MUST_NOT_EXPORT",
                              b"QUEUE_MUST_NOT_EXPORT", b"UPLOAD_MUST_NOT_EXPORT"):
                self.assertNotIn(forbidden, contents)
        preview = self.restore(dry_run=True)
        self.assertTrue(preview["dry_run"])
        self.assertFalse(self.new.exists())
        self.restore()
        config = json.loads(self.config_out.read_text(encoding="utf-8"))
        self.assertEqual(config["web_port"], 5199)
        state = load_state(config["state_path"])
        self.assertEqual((self.new / "vault" / "人工笔记.md").read_bytes(), self.note_bytes)
        self.assertEqual((self.new / "vault" / "cover.png").read_bytes(), b"fixture-attachment")
        self.assertEqual(state["custom_v1_field"], self.state["custom_v1_field"])
        thread = state["threads"]["thread"]
        for key in ("updatedAt", "through", "turns", "coverage", "pending", "historical_reference"):
            self.assertEqual(thread[key], self.state["threads"]["thread"][key])
        self.assertEqual(thread["note"], str(self.new / "vault" / "人工笔记.md"))
        self.assertEqual(thread["receipts"][0]["check_note"], str(self.new / "data" / "runs" / "old-job" / "private-check.md"))
        file_receipt = json.loads((self.new / "data" / "receipts" / "file-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(file_receipt["source"], path_key(self.new / "sources" / self.source.name))
        self.assertEqual(state["baseline_at"], "2026-10-20T10:00:00+08:00")
        self.assertFalse(Path(state["baseline"]).exists(), "不复制旧运行目录仍须可独立接续")
        self.assertEqual(state["feishu"], self.state["feishu"])
        restored_library, original_library = Library(self.new / "vault"), Library(self.vault)
        restored_library.refresh()
        original_library.refresh()
        self.assertGreater(restored_library.overview()["note_count"], 0)
        self.assertEqual(restored_library.overview()["note_count"], original_library.overview()["note_count"])
        hits = restored_library.search("迁移验收术语")["items"]
        self.assertTrue(hits, "迁移后的真实正文必须可以检索")
        self.assertIn("迁移验收术语", restored_library.get_note(hits[0]["note_id"])["markdown"])
        new_source = self.new / "sources" / self.source.name
        new_source.parent.mkdir()
        shutil.copyfile(self.source, new_source)
        planned = plan_local(state, config, generated_roots=[config["output_root"]], runtime_roots=[config["data_root"]])
        self.assertEqual(planned["files"], [], "换路径不能把已总结来源重新当成新增")
        new_file = self.new / "sources" / "真新增.txt"
        new_file.write_text("新材料", encoding="utf-8")
        planned = plan_local(state, config, generated_roots=[config["output_root"]], runtime_roots=[config["data_root"]])
        self.assertEqual([Path(row["path"]) for row in planned["files"]], [new_file])

    def test_missing_mapping_and_existing_different_note_refuse_before_writes(self):
        self.export()
        with self.assertRaisesRegex(MigrationError, "缺少显式路径映射"):
            import_bundle(self.bundle, [{"from": str(self.vault), "to": str(self.new / "vault")}], self.config_out)
        self.assertFalse(self.new.exists())
        existing = self.new / "vault" / "人工笔记.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("新电脑已人工修改", encoding="utf-8")
        with self.assertRaisesRegex(MigrationError, "未覆盖人工文件"):
            self.restore()
        self.assertEqual(existing.read_text(encoding="utf-8"), "新电脑已人工修改")
        self.assertFalse((self.new / "data").exists())
        self.assertFalse(self.config_out.exists())

    def test_existing_identical_note_is_preserved_and_existing_checkpoint_refused(self):
        self.export()
        existing = self.new / "vault" / "人工笔记.md"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(self.note_bytes)
        before = existing.stat().st_mtime_ns
        self.assertEqual(self.restore()["existing_identical_files"], 1)
        self.assertEqual(existing.stat().st_mtime_ns, before)
        with self.assertRaisesRegex(MigrationError, "运行目录必须为空"):
            self.restore()

    def test_new_notes_preserve_precise_mtime_library_dates_and_search_order(self):
        other = self.vault / "早期笔记.md"
        other.write_bytes(self.note_bytes.replace("人工增补".encode("utf-8"), "资料增补".encode("utf-8")))
        # Both are within the same ZIP two-second window; insertion order is
        # opposite to their true age, so DOS time alone cannot pass this check.
        os.utime(self.note, ns=(1577934245800000000, 1577934245800000000))
        os.utime(other, ns=(1577934245200000000, 1577934245200000000))
        before = {p.name: p.stat().st_mtime_ns for p in (self.note, other)}
        original = Library(self.vault)
        original.refresh()
        original_hits = original.search("迁移验收术语")["items"]
        self.assertGreaterEqual(len(original_hits), 2)
        self.export()
        with zipfile.ZipFile(self.bundle) as archive:
            info = archive.getinfo("vault/" + self.note.name)
            self.assertEqual(json.loads(info.comment)["mtime_ns"], before[self.note.name])
            self.assertEqual(info.date_time[0], 2020)
        self.restore()
        for name, expected in before.items():
            self.assertEqual((self.new / "vault" / name).stat().st_mtime_ns, expected)
        restored = Library(self.new / "vault")
        restored.refresh()
        hits = restored.search("迁移验收术语")["items"]
        self.assertEqual([(r["id"], r["modified_at"]) for r in hits],
                         [(r["id"], r["modified_at"]) for r in original_hits])

    def test_legacy_zip_time_fallback_and_invalid_precise_time_refusal(self):
        self.export()
        for malformed in (False, True):
            with self.subTest(malformed=malformed):
                altered = self.root / ("bad-time.zip" if malformed else "legacy-time.zip")
                with zipfile.ZipFile(self.bundle) as source, zipfile.ZipFile(altered, "w") as target:
                    for info in source.infolist():
                        if info.filename.startswith(("vault/", "runtime/")):
                            info.comment = b'{"mtime_ns":true}' if malformed else b""
                        target.writestr(info, source.read(info.filename))
                destination = self.root / ("bad-time" if malformed else "legacy-time")
                mappings = [{"from": str(self.old), "to": str(destination)}]
                if malformed:
                    with self.assertRaisesRegex(MigrationError, "mtime_ns"):
                        import_bundle(altered, mappings, destination / "config.local.json")
                    self.assertFalse(destination.exists())
                else:
                    self.assertTrue(import_bundle(altered, mappings, destination / "config.local.json")["ok"])

    def test_active_source_lock_refuses_export_without_touching_state(self):
        before = self.state_path.read_bytes()
        (self.data / "executor.lock").write_text('{"owner":"running"}', encoding="utf-8")
        with self.assertRaisesRegex(MigrationError, "停止本机执行器"):
            self.export()
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertFalse(self.bundle.exists())

    def test_software_installers_are_omitted_but_archives_and_documents_remain(self):
        for name in ("下载软件.apk", "安装器.EXE", "数据附件.zip", "档案.rar", "说明.pdf"):
            (self.vault / name).write_bytes(("fixture:" + name).encode("utf-8"))
        result = self.export()
        self.assertEqual(result["software_installers_excluded"], 2)
        self.assertIn("software_installers", result["omitted"])
        self.assertEqual(inspect_bundle(self.bundle)["software_installers_excluded"], 2)
        self.restore()
        for name in ("下载软件.apk", "安装器.EXE"):
            self.assertFalse((self.new / "vault" / name).exists())
        for name in ("数据附件.zip", "档案.rar", "说明.pdf"):
            self.assertEqual((self.new / "vault" / name).read_bytes(), (self.vault / name).read_bytes())

    def test_archive_traversal_is_rejected_without_extracting(self):
        self.export()
        with zipfile.ZipFile(self.bundle, "a") as archive:
            archive.writestr("../escaped.txt", "must not escape")
        with self.assertRaisesRegex(MigrationError, "不安全"):
            self.restore()
        self.assertFalse(self.new.exists())
        self.assertFalse((self.root / "escaped.txt").exists())

    def test_colliding_checkpoint_paths_are_rejected(self):
        other = self.old / "other" / self.source.name
        self.state["files"][path_key(other)] = {"path": str(other), "baseline": True}
        self.state_path.write_text(json.dumps(self.state), encoding="utf-8")
        self.export()
        rows = self.mappings + [{"from": str(self.old / "other"), "to": str(self.new / "sources")}]
        with self.assertRaisesRegex(MigrationError, "检查点键冲突"):
            import_bundle(self.bundle, rows, self.config_out)
        self.assertFalse(self.new.exists())

    def test_write_failure_rolls_back_new_files_and_never_exposes_config(self):
        self.export()
        from engine.migration import _write_new
        written = []

        def fail_after_first(path, data):
            if written:
                raise OSError("模拟磁盘写入失败")
            _write_new(path, data)
            written.append(path)

        with patch("engine.migration._write_new", side_effect=fail_after_first):
            with self.assertRaisesRegex(OSError, "模拟磁盘写入失败"):
                self.restore()
        self.assertFalse(self.config_out.exists())
        self.assertFalse((self.new / "data" / "state.json").exists())
        self.assertTrue(written)
        self.assertTrue(all(not path.exists() for path in written))
        self.assertFalse((self.new / "data").exists(), "失败留下的空运行子目录不能阻止下一次导入")
        self.assertTrue(self.restore()["ok"])

    def test_note_changed_after_preflight_is_not_silently_skipped(self):
        self.export()
        existing = self.new / "vault" / "人工笔记.md"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(self.note_bytes)
        from engine.migration import _write_new
        changed = False

        def edit_during_import(path, data):
            nonlocal changed
            _write_new(path, data)
            if not changed:
                existing.write_text("导入期间的人工修改", encoding="utf-8")
                changed = True

        with patch("engine.migration._write_new", side_effect=edit_during_import):
            with self.assertRaisesRegex(MigrationError, "导入期间发生变化"):
                self.restore()
        self.assertEqual(existing.read_text(encoding="utf-8"), "导入期间的人工修改")
        self.assertFalse(self.config_out.exists())
        self.assertFalse((self.new / "data" / "state.json").exists())

    def test_all_notes_rechecked_before_config_publish_preserves_late_manual_edit(self):
        self.export()
        from engine.migration import _write_new
        note = self.new / "vault" / "人工笔记.md"

        def edit_after_note_check(path, data):
            _write_new(path, data)
            if path.name == "state.json":
                note.write_text("已写笔记随后被人工修改", encoding="utf-8")

        with patch("engine.migration._write_new", side_effect=edit_after_note_check):
            with self.assertRaisesRegex(MigrationError, "导入期间发生变化"):
                self.restore()
        self.assertEqual(note.read_text(encoding="utf-8"), "已写笔记随后被人工修改")
        self.assertFalse(self.config_out.exists())
        self.assertFalse((self.new / "data" / "state.json").exists())

    @unittest.skipUnless(os.name == "nt", "Windows 普通磁盘的重命名分支")
    def test_windows_import_does_not_require_hardlinks(self):
        self.export()
        with patch("engine.migration.os.link", side_effect=OSError("磁盘不支持硬链接")):
            self.assertTrue(self.restore()["ok"])

    @unittest.skipUnless(os.name == "nt", "Windows 长路径边界回归")
    def test_windows_legal_long_chinese_note_uses_short_atomic_temp_name(self):
        relative = Path("04 例行工作") / "个人知识工作台" / "接续材料"
        target_parent = self.new / "vault" / relative
        name_length = 245 - len(str(target_parent)) - 1 - len(".md")
        self.assertGreater(name_length, 20)
        name = ("根据使用说明准备接续材料" * 20)[:name_length] + ".md"
        source = self.vault / relative / name
        source.parent.mkdir(parents=True)
        source.write_bytes(self.note_bytes)
        target = target_parent / name
        old_temporary = target.with_name("." + name + ".12345678-1234-1234-1234-123456789abc.tmp")
        self.assertLess(len(str(target)), 260)
        self.assertGreaterEqual(len(str(old_temporary)), 260)
        self.export()
        self.assertTrue(self.restore()["ok"])
        self.assertEqual(target.read_bytes(), self.note_bytes)
        self.assertFalse(list(target_parent.glob(".ow-*.tmp")))

    def test_missing_baseline_cannot_create_replayable_empty_history(self):
        (self.old / "baseline" / "run-manifest.json").unlink()
        with self.assertRaisesRegex(MigrationError, "缺少已验收基线时间"):
            self.export()
        self.assertFalse(self.bundle.exists())


if __name__ == "__main__":
    unittest.main()
