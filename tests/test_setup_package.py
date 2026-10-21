"""New-user initialization and release packaging never use personal workspaces."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from engine.incremental import load_state, plan_local
from engine.settings import load_settings, validate_startup
from scripts import package_release as package
from scripts import setup_workspace as setup


class NewWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "source/config.local.json"
        self.now = datetime(2026, 10, 23, 11, tzinfo=timezone.utc)

    def test_explicit_setup_creates_portable_empty_baseline_without_old_sources(self):
        result = setup.setup_workspace(self.config, now=self.now)
        config = load_settings(self.config)
        validate_startup(config)
        state = load_state(config["state_path"])
        self.assertEqual(self.now.isoformat(), state["baseline_at"])
        self.assertEqual({key: {} for key in ("files", "threads", "feishu")},
                         {key: state[key] for key in ("files", "threads", "feishu")})
        self.assertEqual([], config["watch_roots"])
        self.assertEqual([], config["memory_roots"])
        self.assertFalse(config["feishu_enabled"])
        self.assertEqual("", config["cloud_url"])
        portable = json.loads(self.config.read_text(encoding="utf-8"))
        for key in ("data_root", "state_path", "obsidian_vault", "output_root"):
            self.assertFalse(Path(portable[key]).is_absolute())
        for folder in setup.FOLDERS:
            self.assertTrue((Path(result["vault"]) / folder).is_dir())
        layout = json.loads((Path(result["vault"]) / ".obsidian/knowledge-layout.json").read_text(encoding="utf-8"))
        self.assertTrue(layout["navigation"])
        self.assertEqual({}, layout["path_aliases"])

    def test_existing_config_and_nonempty_vault_or_data_are_preserved(self):
        for conflict in ("config", "vault", "state", "data"):
            with self.subTest(conflict=conflict):
                base = self.root / conflict
                config, vault, data = base / "source/config.local.json", base / "vault", base / "data"
                target = {"config": config, "vault": vault / "已有笔记.md",
                          "state": data / "checkpoint/state.json", "data": data / "jobs.sqlite"}[conflict]
                target.parent.mkdir(parents=True)
                target.write_bytes(b"MUST_KEEP")
                with self.assertRaises(ValueError):
                    setup.setup_workspace(config, vault=vault, data_root=data, now=self.now)
                self.assertEqual(b"MUST_KEEP", target.read_bytes())
                if conflict != "config":
                    self.assertFalse(config.exists())
                if conflict != "state":
                    self.assertFalse((data / "checkpoint/state.json").exists())

    def test_overlapping_locations_and_naive_baseline_fail_before_writes(self):
        with self.assertRaises(ValueError):
            setup.setup_workspace(self.config, vault=self.root / "vault", data_root=self.root / "vault/data")
        with self.assertRaises(ValueError):
            setup.setup_workspace(self.config, now=datetime(2026, 10, 23))
        self.assertFalse(self.config.exists())
        self.assertFalse((self.root / "vault").exists())

    def test_failed_startup_validation_rolls_back_only_new_files(self):
        self.config.parent.mkdir(parents=True)
        existing = self.config.parent / "README.md"
        existing.write_text("keep", encoding="utf-8")
        with patch.object(setup, "validate_startup", side_effect=ValueError("synthetic failure")):
            with self.assertRaisesRegex(ValueError, "synthetic failure"):
                setup.setup_workspace(self.config, now=self.now)
        self.assertEqual("keep", existing.read_text(encoding="utf-8"))
        self.assertFalse(self.config.exists())
        self.assertFalse((self.root / "Obsidian-Work").exists())
        self.assertFalse((self.root / "obsidian-workspace-data").exists())

    def test_source_scan_excludes_configured_checkpoint_without_inventing_memory_sources(self):
        source = self.root / "sources"
        source.mkdir()
        note = source / "真实新资料.txt"
        note.write_text("new source", encoding="utf-8")
        checkpoint = source / "state.json"
        checkpoint.write_text("synthetic checkpoint", encoding="utf-8")
        plan = plan_local({"version": 1, "files": {}, "threads": {}, "feishu": {}},
                          {"watch_roots": [{"path": str(source)}], "state_path": str(checkpoint)})
        self.assertEqual([str(note.resolve())], [row["path"] for row in plan["files"]])
        self.assertEqual(1, len(plan["sources"]))


class ReleasePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        self.root.mkdir()
        self.output = self.root.parent / "Windows.zip"
        self.tracked = sorted(package.REQUIRED)
        for name in self.tracked:
            self.write(name, "synthetic source")
        self.patch = patch.object(package, "_tracked", return_value=self.tracked)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_archive_uses_working_source_and_omits_private_and_generated_files(self):
        private = ["config.local.json", "web/.dev.vars", "web/node_modules/library.js", "web/dist/server.js",
                   "output/handoff.md", "engine/state.json", "web/credentials.json", "web/data/笔记.md"]
        for name in private:
            self.write(name, "PRIVATE_MUST_NOT_EXPORT")
        self.tracked.extend(private)
        self.write("server.py", "current modified source")
        result = package.package_release(self.root, self.output)
        self.assertTrue(result["ok"])
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(package.REQUIRED, set(archive.namelist()))
            self.assertEqual(b"current modified source", archive.read("server.py"))
            self.assertNotIn(b"PRIVATE_MUST_NOT_EXPORT", b"".join(archive.read(name) for name in archive.namelist()))

    def test_explicit_new_source_can_be_included_but_private_or_traversal_cannot(self):
        self.write("scripts/new_feature.py", "new public code")
        package.package_release(self.root, self.output, include=["scripts/new_feature.py"])
        with zipfile.ZipFile(self.output) as archive:
            self.assertIn("scripts/new_feature.py", archive.namelist())
        for name in ("../outside.py", "scripts/../config.local.json", "web/.env", "config.local.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                package.package_release(self.root, self.root.parent / "refused.zip", include=[name])
        self.assertFalse((self.root.parent / "refused.zip").exists())

    def test_missing_entrypoint_and_existing_release_are_not_silently_replaced(self):
        self.tracked.remove("打开工作台.cmd")
        with self.assertRaisesRegex(ValueError, "必要源码"):
            package.package_release(self.root, self.output)
        self.assertFalse(self.output.exists())
        self.tracked.append("打开工作台.cmd")
        self.output.write_bytes(b"EXISTING_RELEASE")
        with self.assertRaises(ValueError):
            package.package_release(self.root, self.output)
        self.assertEqual(b"EXISTING_RELEASE", self.output.read_bytes())

    def test_source_mtime_before_zip_epoch_is_clamped_without_modifying_source(self):
        path = self.root / "server.py"
        path.write_text("old timestamp source", encoding="utf-8")
        os.utime(path, ns=(0, 0))
        original_mtime = path.stat().st_mtime_ns
        package.package_release(self.root, self.output)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(b"old timestamp source", archive.read("server.py"))
            self.assertEqual((1980, 1, 1, 0, 0, 0), archive.getinfo("server.py").date_time)
        self.assertEqual(original_mtime, path.stat().st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
