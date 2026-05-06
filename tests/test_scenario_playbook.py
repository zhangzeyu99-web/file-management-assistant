from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scenario_playbook.py"
SPEC = importlib.util.spec_from_file_location("scenario_playbook", MODULE_PATH)
assert SPEC and SPEC.loader
scenario_playbook = importlib.util.module_from_spec(SPEC)
sys.modules["scenario_playbook"] = scenario_playbook
SPEC.loader.exec_module(scenario_playbook)


class ScenarioPlaybookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.vault = self.root / "vault"
        self.obsidian_run_dir = self.vault / "04 例行工作" / "文件管理助手"
        self.config_path = self.root / "config.json"

        file_run = self.runtime / "runs" / "2026-05-06" / "120000"
        obsidian_run = self.runtime / "runs" / "2026-05-06" / "120005-obsidian"
        file_run.mkdir(parents=True)
        obsidian_run.mkdir(parents=True)
        self.obsidian_run_dir.mkdir(parents=True)

        (file_run / "summary.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-05-06 12:00:00 +0800",
                    "total_files": 12,
                    "total_size_mb": 34.5,
                    "counts": {
                        "recent_review": 2,
                        "archive_candidates": 3,
                        "installer_cleanup": 1,
                        "duplicate_groups": 0,
                        "warnings": 0,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (file_run / "report.html").write_text("<h1>file report</h1>", encoding="utf-8")
        (file_run / "report.md").write_text("# file report", encoding="utf-8")
        (obsidian_run / "obsidian-management-summary.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-05-06 12:00:05 +0800",
                    "total_notes": 8,
                    "counts": {
                        "inbox_triage": 2,
                        "empty_or_stub": 1,
                        "low_link_notes": 4,
                        "broken_links": 0,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (obsidian_run / "obsidian-management-report.md").write_text("# obsidian report", encoding="utf-8")

        self.config_path.write_text(
            json.dumps(
                {
                    "runtime_root": str(self.runtime),
                    "obsidian_vault": str(self.vault),
                    "obsidian_run_dir": str(self.obsidian_run_dir),
                    "watch_roots": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_catalog_exposes_scenario_first_workflows(self) -> None:
        config = scenario_playbook.load_config(self.config_path)
        catalog = scenario_playbook.build_scenario_catalog(config)

        ids = {item["id"] for item in catalog}
        self.assertEqual(
            {"daily_review", "inbox_triage", "obsidian_health", "codex_handoff"},
            ids,
        )
        for item in catalog:
            self.assertTrue(item["title"])
            self.assertTrue(item["user_need"])
            self.assertGreaterEqual(len(item["steps"]), 3)
            self.assertGreaterEqual(len(item["safe_actions"]), 2)
            self.assertGreaterEqual(len(item["acceptance_checks"]), 2)
            self.assertIn("不删除", item["safety"])
            self.assertTrue(item["next_action"])
            self.assertTrue(item["prompt"])

    def test_demo_run_writes_json_markdown_and_obsidian_note(self) -> None:
        result = scenario_playbook.run_demo(self.config_path)

        self.assertTrue(result["ok"], result)
        self.assertTrue(Path(result["json_report"]).exists())
        self.assertTrue(Path(result["markdown_report"]).exists())
        self.assertTrue(Path(result["obsidian_note"]).exists())

        markdown = Path(result["markdown_report"]).read_text(encoding="utf-8")
        note = Path(result["obsidian_note"]).read_text(encoding="utf-8")
        self.assertIn("# 使用场景示例闭环报告", markdown)
        self.assertIn("今天先看什么", markdown)
        self.assertIn("12", markdown)
        self.assertIn("闭环验收", note)
        self.assertIn("codex_handoff", note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
