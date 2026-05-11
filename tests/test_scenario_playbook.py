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
        self.obsidian_run_dir = self.vault / "04 例行工作" / "知识行动助手"
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
                        "recent_review": 3,
                        "archive_candidates": 25,
                        "installer_cleanup": 1,
                        "large_files": 2,
                        "duplicate_groups": 0,
                        "warnings": 0,
                    },
                    "classifications": {
                        "recent_review": [
                            {"path": r"C:\Users\Administrator\Documents\New project\CSCSE_UCSC_degree_certification_pack\README.md"},
                            {"path": r"D:\codex\output\notebooklm-obsidian-assistant-pack-2026-04-27"},
                            {"path": r"C:\Users\Administrator\Downloads\巨神东南亚更新公告 5.7_tha.xlsx"},
                        ],
                        "large_files": [
                            {"path": r"C:\Users\Administrator\Downloads\OpenAI.Codex.msix", "size_mb": 413},
                            {"path": r"C:\Users\Administrator\Videos\NotebookLM课程素材.mp4", "size_mb": 380},
                        ],
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
                        "inbox_triage": 4,
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

    def test_catalog_exposes_knowledge_action_workflows(self) -> None:
        config = scenario_playbook.load_config(self.config_path)
        catalog = scenario_playbook.build_scenario_catalog(config)

        ids = {item["id"] for item in catalog}
        self.assertEqual(
            {
                "today",
                "file_radar",
                "inbox_route",
                "action_note",
                "card_capture",
                "time_review",
                "obsidian_health",
                "ai_chat_archive",
                "ai_context_retrieval",
                "assistant_qa",
            },
            ids,
        )
        for item in catalog:
            self.assertTrue(item["title"])
            self.assertTrue(item["user_phrase"])
            self.assertTrue(item["does"])
            self.assertIn("不删除", item["safety"])
            self.assertTrue(item["next_action"])

    def test_daily_review_is_lightweight_and_domain_separated(self) -> None:
        config = scenario_playbook.load_config(self.config_path)
        today = next(item for item in scenario_playbook.build_scenario_catalog(config) if item["id"] == "today")

        combined = "\n".join(today["steps"] + today["acceptance_checks"])
        self.assertIn("今日轻量规则", combined)
        self.assertIn("不要每天处理全部归档候选", combined)
        self.assertIn("最多 3 条行动建议", combined)
        self.assertIn("今日相关", today["next_action"])
        self.assertEqual(["生活", "学习", "工作"], [item["name"] for item in today["domain_buckets"]])

    def test_domain_classifier_splits_life_study_and_work(self) -> None:
        self.assertEqual(
            "生活",
            scenario_playbook.classify_domain(
                r"C:\Users\Administrator\Documents\New project\CSCSE_UCSC_degree_certification_pack\README.md"
            )["name"],
        )
        self.assertEqual(
            "学习",
            scenario_playbook.classify_domain(r"D:\codex\output\notebooklm-obsidian-assistant-pack-2026-04-27")["name"],
        )
        self.assertEqual(
            "工作",
            scenario_playbook.classify_domain(r"C:\Users\Administrator\Downloads\巨神东南亚更新公告 5.7_tha.xlsx")["name"],
        )

    def test_act_templates_are_exposed(self) -> None:
        templates = scenario_playbook.build_act_templates()

        self.assertEqual(["Action", "Card", "Time", "X-AI"], [item["name"] for item in templates])
        for item in templates:
            joined = "\n".join(item["fields"])
            self.assertIn("来源", joined)
            self.assertIn("下一步", joined)
            self.assertIn("验收标准", joined)

    def test_demo_run_writes_json_markdown_and_obsidian_note(self) -> None:
        result = scenario_playbook.run_demo(self.config_path)

        self.assertTrue(result["ok"], result)
        self.assertTrue(Path(result["json_report"]).exists())
        self.assertTrue(Path(result["markdown_report"]).exists())
        self.assertTrue(Path(result["obsidian_note"]).exists())

        markdown = Path(result["markdown_report"]).read_text(encoding="utf-8")
        note = Path(result["obsidian_note"]).read_text(encoding="utf-8")
        self.assertIn("# 知识行动助手场景闭环报告", markdown)
        self.assertIn("四层结构", markdown)
        self.assertIn("今日轻量规则", markdown)
        self.assertIn("生活 / 学习 / 工作", markdown)
        self.assertIn("Action / Card / Time / X-AI", markdown)
        self.assertIn("ai_chat_archive", note)
        self.assertIn("ai_context_retrieval", note)
        self.assertNotRegex(markdown, r"鏂|绠|鍏|浠婃|瀛︿|宸ヤ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
