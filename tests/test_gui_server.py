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
        (self.vault / "04 例行工作" / "知识行动助手").mkdir(parents=True)

        (self.runtime / "runs" / "2026-04-27" / "120000" / "summary.json").write_text(
            json.dumps({"total_files": 3, "counts": {"recent_review": 1, "archive_candidates": 2}}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.runtime / "runs" / "2026-04-27" / "120000" / "report.html").write_text(
            "<h1>report</h1>",
            encoding="utf-8",
        )
        (self.runtime / "runs" / "2026-04-27" / "120000-obsidian" / "obsidian-management-summary.json").write_text(
            json.dumps({"total_notes": 2, "counts": {"broken_links": 0, "inbox_triage": 1}}, ensure_ascii=False),
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
                    "obsidian_run_dir": str(self.vault / "04 例行工作" / "知识行动助手"),
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
        self.assertEqual("知识行动助手", status["product"]["name"])
        self.assertEqual(3, status["file_report"]["summary"]["total_files"])
        self.assertTrue(status["file_report"]["html_report"].endswith("report.html"))
        self.assertEqual(2, status["obsidian_report"]["summary"]["total_notes"])
        self.assertTrue(status["obsidian_report"]["markdown_report"].endswith("obsidian-management-report.md"))
        self.assertIn("today", {item["id"] for item in status["scenarios"]})

    def test_rejects_unknown_action(self) -> None:
        result = gui_server.run_gui_action("delete-everything", {}, self.config_path)

        self.assertFalse(result["ok"])
        self.assertIn("unsupported", result["error"])

    def test_scenario_entry_actions_return_results(self) -> None:
        today = gui_server.run_gui_action("today", {}, self.config_path)
        file_radar = gui_server.run_gui_action("file-radar", {}, self.config_path)
        health = gui_server.run_gui_action("obsidian-health", {}, self.config_path)

        self.assertTrue(today["ok"], today)
        self.assertIn("今日轻量规则", today["summary"])
        self.assertTrue(file_radar["ok"], file_radar)
        self.assertIn("html_report", file_radar)
        self.assertTrue(health["ok"], health)
        self.assertIn("markdown_report", health)

    def test_capture_daily_and_act_actions_write_to_vault(self) -> None:
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
        action = gui_server.run_gui_action(
            "action-note",
            {"title": "GUI 任务", "domain": "工作", "goal": "验证入口", "source": "GUI"},
            self.config_path,
        )
        card = gui_server.run_gui_action(
            "card-note",
            {"title": "GUI 知识卡", "domain": "学习", "source": "GUI", "conclusion": "入口可用"},
            self.config_path,
        )
        review = gui_server.run_gui_action(
            "time-review",
            {"title": "GUI 复盘", "period": "daily", "done": "完成入口验证", "next": "跑测试"},
            self.config_path,
        )

        self.assertTrue(Path(capture["note"]).exists())
        self.assertTrue(Path(daily["daily"]).exists())
        self.assertTrue(Path(action["note"]).exists())
        self.assertTrue(Path(card["note"]).exists())
        self.assertTrue(Path(review["note"]).exists())
        self.assertIn("完成 GUI 测试", Path(daily["daily"]).read_text(encoding="utf-8"))

    def test_codex_prompt_preserves_user_request_and_local_context(self) -> None:
        config = gui_server.load_config(self.config_path)
        prompt = gui_server.build_codex_prompt("帮我整理今天的收件箱", config)

        self.assertIn("帮我整理今天的收件箱", prompt)
        self.assertIn(str(self.vault), prompt)
        self.assertIn("生活 / 学习 / 工作", prompt)
        self.assertIn("不删除", prompt)

    def test_html_exposes_scenario_first_buttons_without_mojibake(self) -> None:
        html = gui_server.HTML

        for label in ["今天先干什么", "记录一个任务", "这段内容放哪", "复盘今天", "检查知识库", "生成 Codex 交接", "查看文件雷达", "打开 Obsidian"]:
            self.assertIn(label, html)
        self.assertNotRegex(html, r"鏂|绠|鍏|浠婃|瀛︿|宸ヤ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
