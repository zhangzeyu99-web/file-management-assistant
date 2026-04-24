from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "file_assistant.py"
SPEC = importlib.util.spec_from_file_location("file_assistant", MODULE_PATH)
assert SPEC and SPEC.loader
file_assistant = importlib.util.module_from_spec(SPEC)
sys.modules["file_assistant"] = file_assistant
SPEC.loader.exec_module(file_assistant)


class FileAssistantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = dt.datetime(2026, 4, 24, 20, 0, tzinfo=dt.datetime.now().astimezone().tzinfo)
        self.config = {
            "runtime_root": str(self.root / "runtime"),
            "obsidian_run_dir": str(self.root / "obsidian"),
            "watch_roots": [
                {
                    "name": "Downloads",
                    "path": str(self.root / "Downloads"),
                    "max_depth": 2,
                    "max_files": 100,
                }
            ],
            "exclude_dir_names": [".git", "node_modules"],
            "recent_days": 7,
            "archive_after_days": 30,
            "installer_after_days": 14,
            "large_file_mb": 200,
            "hash_duplicate_min_mb": 0,
            "hash_duplicate_limit": 20,
            "top_limit": 20,
            "review_keywords": ["报告", "report"],
        }
        (self.root / "Downloads").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_file(self, relative: str, contents: bytes, days_old: int) -> Path:
        path = self.root / "Downloads" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        stamp = (self.now - dt.timedelta(days=days_old)).timestamp()
        path.touch()
        import os

        os.utime(path, (stamp, stamp))
        return path

    def test_classifies_recent_document_and_old_installer(self) -> None:
        self.write_file("项目报告.md", b"recent", days_old=1)
        self.write_file("setup.exe", b"installer", days_old=20)
        records, warnings = file_assistant.build_records(self.config, self.now)
        classified = file_assistant.classify_records(records, self.config)

        self.assertEqual([], warnings)
        self.assertEqual(1, len(classified["recent_review"]))
        self.assertEqual(1, len(classified["installer_cleanup"]))
        self.assertIn("项目报告.md", classified["recent_review"][0]["path"])
        self.assertIn("setup.exe", classified["installer_cleanup"][0]["path"])

    def test_detects_exact_duplicates(self) -> None:
        payload = b"same payload"
        self.write_file("a.bin", payload, days_old=3)
        self.write_file("b.bin", payload, days_old=4)
        records, _ = file_assistant.build_records(self.config, self.now)
        duplicates = file_assistant.detect_duplicates(records, self.config)

        self.assertEqual(1, len(duplicates))
        self.assertEqual(2, duplicates[0]["count"])

    def test_run_writes_reports_and_obsidian_note(self) -> None:
        self.write_file("项目报告.md", b"recent", days_old=1)
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")
        summary = file_assistant.run(config_path, "Test")

        self.assertTrue(Path(summary["summary_json"]).exists())
        self.assertTrue(Path(summary["markdown_report"]).exists())
        self.assertTrue(Path(summary["html_report"]).exists())
        self.assertTrue(Path(summary["obsidian_note"]).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
