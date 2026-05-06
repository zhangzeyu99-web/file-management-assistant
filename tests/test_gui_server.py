from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "gui_server.py"
SPEC = importlib.util.spec_from_file_location("gui_server", MODULE_PATH)
assert SPEC and SPEC.loader
gui_server = importlib.util.module_from_spec(SPEC)
sys.modules["gui_server"] = gui_server
SPEC.loader.exec_module(gui_server)


class GuiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.vault = self.root / "vault"
        self.config_path = self.root / "config.json"
        (self.runtime / "runs" / "2026-04-27" / "120000").mkdir(parents=True)
        (self.runtime / "runs" / "2026-04-27" / "120000-obsidian").mkdir(parents=True)
        (self.vault / "00 收件箱").mkdir(parents=True)
        (self.vault / "01 今日日志").mkdir(parents=True)
        (self.vault / "04 例行工作" / "文件管理助手").mkdir(parents=True)

        (self.runtime / "runs" / "2026-04-27" / "120000" / "summary.json").write_text(
            json.dumps({"total_files": 3, "counts": {"recent_review": 1}}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.runtime / "runs" / "2026-04-27" / "120000" / "report.html").write_text(
            "<h1>report</h1>",
            encoding="utf-8",
        )
        (self.runtime / "runs" / "2026-04-27" / "120000-obsidian" / "obsidian-management-summary.json").write_text(
            json.dumps({"total_notes": 2, "counts": {"broken_links": 0}}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.runtime / "runs" / "2026-04-27" / "120000-obsidian" / "obsidian-management-report.md").write_text(
            "# obsidian",
            encoding="utf-8",
        )
        self.config_path.write_text(
            json.dumps(
                {
                    "runtime_root": str(self.runtime),
                    "obsidian_vault": str(self.vault),
                    "obsidian_run_dir": str(self.vault / "04 例行工作" / "文件管理助手"),
                    "watch_roots": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_status_reports_latest_file_and_obsidian_outputs(self) -> None:
        status = gui_server.build_status(self.config_path)

        self.assertTrue(status["ok"])
        self.assertEqual(3, status["file_report"]["summary"]["total_files"])
        self.assertTrue(status["file_report"]["html_report"].endswith("report.html"))
        self.assertEqual(2, status["obsidian_report"]["summary"]["total_notes"])
        self.assertTrue(status["obsidian_report"]["markdown_report"].endswith("obsidian-management-report.md"))

    def test_rejects_unknown_action(self) -> None:
        result = gui_server.run_gui_action("delete-everything", {}, self.config_path)

        self.assertFalse(result["ok"])
        self.assertIn("unsupported", result["error"])

    def test_capture_and_daily_actions_write_to_vault(self) -> None:
        capture = gui_server.run_gui_action(
            "capture",
            {"title": "GUI 想法", "body": "从 GUI 写入", "tags": ["gui"]},
            self.config_path,
        )
        daily = gui_server.run_gui_action(
            "daily",
            {"done": "完成 GUI 测试", "next": "继续实现", "blocker": "暂无"},
            self.config_path,
        )

        self.assertTrue(Path(capture["note"]).exists())
        self.assertTrue(Path(daily["daily"]).exists())
        self.assertIn("完成 GUI 测试", Path(daily["daily"]).read_text(encoding="utf-8"))

    def test_codex_prompt_preserves_user_request_and_local_context(self) -> None:
        config = gui_server.load_config(self.config_path)
        prompt = gui_server.build_codex_prompt("帮我整理今天的收件箱", config)

        self.assertIn("帮我整理今天的收件箱", prompt)
        self.assertIn(str(self.vault), prompt)
        self.assertIn("不要删除", prompt)


    def test_scenario_actions_return_catalog_and_write_demo(self) -> None:
        catalog = gui_server.run_gui_action("scenarios", {}, self.config_path)
        ids = {item["id"] for item in catalog["scenarios"]}

        self.assertTrue(catalog["ok"], catalog)
        self.assertIn("daily_review", ids)
        self.assertIn("codex_handoff", ids)

        demo = gui_server.run_gui_action("scenario-demo", {}, self.config_path)

        self.assertTrue(demo["ok"], demo)
        self.assertTrue(Path(demo["markdown_report"]).exists())
        self.assertTrue(Path(demo["obsidian_note"]).exists())
        self.assertEqual(4, len(demo["scenarios"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
