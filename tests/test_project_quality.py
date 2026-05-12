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
            "three primary operations",
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

    def test_iteration_review_protocol_is_persisted_and_enforced(self) -> None:
        result = project_quality.run_checks(self.repo)
        protocol = next(item for item in result["checks"] if item["name"] == "iteration_review_protocol")
        protocol_text = (self.repo / "docs" / "ITERATION_REVIEW_PROTOCOL.md").read_text(encoding="utf-8-sig")

        self.assertTrue(protocol["ok"], protocol)
        for question in [
            "做到了视觉清晰阅读友好了吗",
            "做到了总结归纳到位",
            "发给别人能看懂吗",
            "传到 Codex 指引性足够吗",
            "GUI 双向交互方便吗",
            "信息内容容易编辑吗",
            "展示的方式足够方便吗",
            "信息集关联有做吗",
            "能让人发散性思考吗",
        ]:
            self.assertIn(question, protocol_text)
        self.assertIn("docs/iteration-logs", protocol_text)
        self.assertIn("Obsidian", protocol_text)

    def test_design_md_reference_is_persisted_for_future_ui_iterations(self) -> None:
        result = project_quality.run_checks(self.repo)
        design = next(item for item in result["checks"] if item["name"] == "design_system_reference")
        project_design = (self.repo / "DESIGN.md").read_text(encoding="utf-8-sig")
        vibe_reference = (self.repo / "docs" / "design-references" / "vibeui-mintlify-DESIGN.md").read_text(encoding="utf-8-sig")

        self.assertTrue(design["ok"], design)
        self.assertIn("# Design System: Mintlify", vibe_reference)
        for phrase in [
            "Mintlify",
            "documentation-as-product",
            "知识详情",
            "关联内容",
            "可追问问题",
            "默认不做后台管理系统",
        ]:
            self.assertIn(phrase, project_design)

    def test_readme_first_screen_explains_product_positioning(self) -> None:
        readme = (self.repo / "README.md").read_text(encoding="utf-8-sig")
        first_screen = "\n".join(readme.splitlines()[:45])

        for phrase in [
            "Obsidian",
            "本地知识整理助手",
            "添加资料",
            "搜索回顾",
            "生成 AI 上下文包",
            "AI 上下文包",
            "知识卡",
            "不会删除",
            "不会移动",
            "不会重命名",
        ]:
            self.assertIn(phrase, first_screen)
        self.assertNotIn("Codex 接手包", first_screen)

    def test_public_docs_promote_three_primary_operations(self) -> None:
        public_files = [
            "README.md",
            "docs/ARCHITECTURE.md",
            "docs/ADVANCED_TOOLS_REDESIGN.md",
            "docs/USER_SCENARIOS.md",
            "docs/CLOSED_LOOP_USAGE.md",
            "docs/GETTING_STARTED.md",
            "docs/PROJECT_PRINCIPLES.md",
            "docs/SELF_EVOLUTION.md",
            "gui_server.py",
            "scenario_playbook.py",
        ]
        public_text = "\n".join((self.repo / path).read_text(encoding="utf-8-sig") for path in public_files)

        self.assertIn("添加资料", public_text)
        self.assertIn("搜索回顾", public_text)
        self.assertIn("生成 AI 上下文包", public_text)
        self.assertIn("AI 上下文包", public_text)
        self.assertNotIn("生成 Codex 交接", public_text)
        self.assertNotIn("Codex 交接", public_text)
        self.assertNotIn("AI 交接", public_text)

    def test_advanced_tools_page_replaces_home_advanced_area(self) -> None:
        home = (self.repo / "docs" / "assets" / "gui" / "workspace.html").read_text(encoding="utf-8-sig")
        advanced = (self.repo / "docs" / "assets" / "gui" / "advanced.html").read_text(encoding="utf-8-sig")

        self.assertIn('href="/advanced"', home)
        self.assertIn("tools-entry", home)
        self.assertNotIn("高级/诊断", home)
        self.assertNotIn("advanced-grid", home)
        self.assertNotIn("runLegacyAction", home)
        for action in ["file-radar", "obsidian-health", "legacy-index", "open-obsidian", "open-guidebook", "open-interaction-guide"]:
            self.assertIn(f"runTool('{action}')", advanced)
        self.assertNotIn("查看高级 JSON", advanced)
        self.assertNotIn("console-output", advanced)

    def test_gui_server_does_not_embed_obsolete_html(self) -> None:
        server = (self.repo / "gui_server.py").read_text(encoding="utf-8-sig")

        self.assertNotIn("LEGACY_HTML", server)
        self.assertNotIn("今日操作台", server)
        self.assertNotIn("查看高级 JSON", server)
        self.assertNotIn("console-output", server)

    def test_interaction_and_guidebook_follow_three_operation_positioning(self) -> None:
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
            "添加资料",
            "搜索回顾",
            "生成 AI 上下文包",
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
        human_script = (self.repo / "scripts" / "gui-human-usability.js").read_text(encoding="utf-8-sig")
        human_runner = (self.repo / "scripts" / "run-gui-human-usability.ps1").read_text(encoding="utf-8-sig")

        for phrase in [
            ".feature-anchor",
            "#knowledgeDetail",
            "data-knowledge-card",
            "knowledge_detail",
            "has_related",
            "has_prompts",
            "一句话结论",
            "关联内容",
            "可追问问题",
            "#localPaths",
            "#fileDropZone",
            "inspect-local-targets",
            "custom-local-paths",
            "missing-file-target-section",
        ]:
            self.assertIn(phrase, script)
        self.assertIn("e2eLocalPath", runner)
        self.assertIn("LocalPathForE2E", runner)
        self.assertIn("[string]$Browser", runner)
        self.assertIn("--browser", runner)
        self.assertIn("read-only flag did not reach browser", runner)
        self.assertIn("Invoke-PlaywrightClose", runner)
        self.assertIn("Wait-Process -Timeout", runner)

        for phrase in [
            "human-usability.webm",
            "video-start",
            "video-stop",
            "StrictUx",
            "humanLocalPath",
        ]:
            self.assertIn(phrase, human_runner)
        for phrase in [
            "timeline",
            "console_events",
            "network_events",
            "inspect-local-targets",
            "expectedStatus",
            "expectedResponseOk",
            "review no-match",
            "没有命中已整理资料",
            "没有找到已整理内容",
            "/advanced",
            "[data-tool-card]",
        ]:
            self.assertIn(phrase, human_script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
