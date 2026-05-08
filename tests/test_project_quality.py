from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "project_quality.py"
SPEC = importlib.util.spec_from_file_location("project_quality", MODULE_PATH)
assert SPEC and SPEC.loader
project_quality = importlib.util.module_from_spec(SPEC)
sys.modules["project_quality"] = project_quality
SPEC.loader.exec_module(project_quality)


class ProjectQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(__file__).resolve().parents[1]

    def test_quality_gate_passes_for_current_repository(self) -> None:
        result = project_quality.run_checks(self.repo)

        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(len(result["checks"]), 8)

    def test_past_design_ideas_are_captured_as_verifiable_principles(self) -> None:
        result = project_quality.run_checks(self.repo)
        principles = next(item for item in result["checks"] if item["name"] == "project_principles")
        expected = {
            "local-first",
            "safe-by-default",
            "private local configuration",
            "local knowledge organizer",
            "four core actions",
            "obsidian workflow",
            "human-readable gui",
            "portable bootstrap",
            "cloud backup boundary",
            "closed loop",
            "lightweight daily triage",
            "life study work separation",
            "thin gui",
            "validation harness",
            "legacy compatibility",
        }

        self.assertTrue(principles["ok"], principles)
        self.assertTrue(expected.issubset(set(principles["evidence"])), principles)

    def test_public_text_has_no_common_mojibake(self) -> None:
        result = project_quality.run_checks(self.repo)
        mojibake = next(item for item in result["checks"] if item["name"] == "mojibake_scan")

        self.assertTrue(mojibake["ok"], mojibake)

    def test_guidebook_assets_are_published(self) -> None:
        result = project_quality.run_checks(self.repo)
        guidebook = next(item for item in result["checks"] if item["name"] == "guidebook_assets")

        self.assertTrue(guidebook["ok"], guidebook)
        self.assertEqual(7, guidebook["evidence"]["slide_count"])
        self.assertGreater(guidebook["evidence"]["pdf_size"], 100_000)

    def test_stale_legacy_files_are_removed(self) -> None:
        result = project_quality.run_checks(self.repo)
        stale = next(item for item in result["checks"] if item["name"] == "no_stale_legacy_files")

        self.assertTrue(stale["ok"], stale)

    def test_readme_first_screen_explains_product_positioning(self) -> None:
        readme = (self.repo / "README.md").read_text(encoding="utf-8-sig")
        first_screen = "\n".join(readme.splitlines()[:45])

        for phrase in [
            "Obsidian",
            "本地知识整理助手",
            "整理",
            "回顾",
            "提取",
            "提醒",
            "AI 上下文包",
            "知识卡",
            "今日提醒",
            "不会删除",
            "不会移动",
            "不会重命名",
        ]:
            self.assertIn(phrase, first_screen)
        self.assertNotIn("Codex 接手包", first_screen)

    def test_public_docs_promote_four_core_actions(self) -> None:
        public_files = [
            "README.md",
            "docs/ARCHITECTURE.md",
            "docs/USER_SCENARIOS.md",
            "docs/CLOSED_LOOP_USAGE.md",
            "docs/GETTING_STARTED.md",
            "docs/PROJECT_PRINCIPLES.md",
            "docs/SELF_EVOLUTION.md",
            "gui_server.py",
            "scenario_playbook.py",
        ]
        public_text = "\n".join((self.repo / path).read_text(encoding="utf-8-sig") for path in public_files)

        self.assertIn("整理资料", public_text)
        self.assertIn("回顾知识", public_text)
        self.assertIn("提取上下文", public_text)
        self.assertIn("今日提醒", public_text)
        self.assertIn("AI 上下文包", public_text)
        self.assertNotIn("生成 Codex 交接", public_text)
        self.assertNotIn("Codex 交接", public_text)
        self.assertNotIn("AI 交接", public_text)

    def test_interaction_and_guidebook_follow_four_action_positioning(self) -> None:
        public_text = "\n".join(
            (self.repo / path).read_text(encoding="utf-8-sig")
            for path in [
                "docs/GUI_INTERACTION_GUIDE.md",
                "docs/assets/gui/interaction-guide.html",
                "docs/guidebook/README.md",
            ]
        )

        for phrase in [
            "本地知识整理助手",
            "整理资料",
            "回顾知识",
            "提取上下文",
            "今日提醒",
            "AI 上下文包",
            "本地文件",
            "Obsidian",
            "本地文件 / 目录目标",
            "检查本地目标",
        ]:
            self.assertIn(phrase, public_text)
        for obsolete in [
            "今日操作台",
            "执行结果",
            "伪控制台",
            "可视化上下文入口",
            "Codex 接手包",
        ]:
            self.assertNotIn(obsolete, public_text)

    def test_gui_harness_verifies_local_target_workbench(self) -> None:
        script = (self.repo / "scripts" / "gui-e2e-playwright.js").read_text(encoding="utf-8-sig")
        runner = (self.repo / "scripts" / "run-gui-e2e.ps1").read_text(encoding="utf-8-sig")

        for phrase in [
            "#localPaths",
            "#fileDropZone",
            "inspect-local-targets",
            "custom-local-paths",
            "missing-file-target-workbench",
        ]:
            self.assertIn(phrase, script)
        self.assertIn("e2eLocalPath", runner)
        self.assertIn("LocalPathForE2E", runner)
        self.assertIn("[string]$Browser", runner)
        self.assertIn("--browser", runner)
        self.assertIn("read-only flag did not reach browser", runner)


if __name__ == "__main__":
    unittest.main(verbosity=2)
