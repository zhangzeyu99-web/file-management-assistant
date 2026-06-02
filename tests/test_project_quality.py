from __future__ import annotations

import importlib.util
import subprocess
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
            "core loop only",
            "life study work separation",
            "thin gui",
            "validation harness",
            "deprecated non-core tools",
        }

        self.assertTrue(principles["ok"], principles)
        self.assertTrue(expected.issubset(set(principles["evidence"])), principles)

    def test_public_text_has_no_common_mojibake(self) -> None:
        result = project_quality.run_checks(self.repo)
        mojibake = next(item for item in result["checks"] if item["name"] == "mojibake_scan")

        self.assertTrue(mojibake["ok"], mojibake)

    def test_quality_scan_ignores_test_temp_directory(self) -> None:
        temp_dir = self.repo / ".tmp-tests" / "vanishing"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / "config.json"
        temp_file.write_text("temporary test fixture", encoding="utf-8")

        files = project_quality.iter_public_text_files(self.repo)

        self.assertNotIn(temp_file, files)

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
        latest_by_mtime = max((self.repo / "docs" / "iteration-logs").glob("*.md"), key=lambda path: path.stat().st_mtime)
        self.assertEqual(str(latest_by_mtime.relative_to(self.repo)), protocol["evidence"]["latest_log"])
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
            "结果详情",
            "命中证据",
            "生成产物",
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

    def test_public_docs_explain_portable_three_layer_ai_system(self) -> None:
        public_text = "\n".join(
            (self.repo / path).read_text(encoding="utf-8-sig")
            for path in [
                "README.md",
                "docs/PROJECT_PRINCIPLES.md",
                "docs/PORTABLE_AI_SYSTEM_ITERATION_PLAN.md",
            ]
        )

        for phrase in [
            "ACT 知识资产",
            "AI 身份文件",
            "Skills / SOP",
            "可迁移",
            "可复用",
            "随时切换 AI 工具",
        ]:
            self.assertIn(phrase, public_text)

    def test_public_docs_do_not_promote_knowledge_feed_as_core_flow(self) -> None:
        active_docs = "\n".join(
            (self.repo / path).read_text(encoding="utf-8-sig")
            for path in [
                "README.md",
                "DESIGN.md",
                "docs/PRODUCT_UI_RESEARCH.md",
                "docs/PRODUCT_RETROSPECTIVE_AND_NEXT_PLAN.md",
                "docs/KNOWLEDGE_DISPLAY_METHOD.md",
                "docs/GUI_E2E_TESTING.md",
                "docs/CLOSED_LOOP_USAGE.md",
            ]
        )

        self.assertNotIn("持续更新的知识流", active_docs)
        self.assertNotIn("下滑后可以浏览", active_docs)
        self.assertNotIn("知识流不是文件列表", active_docs)
        self.assertNotIn("浅色知识流", active_docs)
        self.assertNotIn("下滑增加知识流", active_docs)
        self.assertNotIn("展示当前知识流", active_docs)
        self.assertNotIn("把知识流做成可持续入口", active_docs)
        self.assertNotIn("知识流摘要质量", active_docs)
        self.assertNotIn("用户进入知识流", active_docs)
        self.assertNotIn("知识流卡片", active_docs)
        self.assertNotIn("knowledge-card details", active_docs)
        self.assertNotIn("jumps to the knowledge feed", active_docs)
        self.assertNotIn("opens a knowledge card", active_docs)

    def test_gui_server_does_not_keep_deprecated_knowledge_feed_backend(self) -> None:
        gui_server = (self.repo / "gui_server.py").read_text(encoding="utf-8-sig")
        gui_tests = (self.repo / "tests" / "test_gui_server.py").read_text(encoding="utf-8-sig")
        human_usability = (self.repo / "scripts" / "gui-human-usability.js").read_text(encoding="utf-8-sig")

        for phrase in [
            "def build_knowledge_feed",
            "def project_codex_feed_items",
            "def structured_feed_summary",
            "def attach_related_feed_items",
            "TOPIC_RULES",
        ]:
            self.assertNotIn(phrase, gui_server)
        self.assertNotIn("build_knowledge_feed", gui_tests)
        for phrase in [
            "knowledge feed",
            "knowledge-feed",
            'href="#knowledge"',
            "[data-knowledge-card]",
        ]:
            self.assertNotIn(phrase, human_usability)

    def test_portable_ai_templates_are_versioned_and_documented(self) -> None:
        result = project_quality.run_checks(self.repo)
        portable_templates = next(item for item in result["checks"] if item["name"] == "portable_ai_templates")
        expected = [
            "templates/portable-ai-system/AI 身份文件/AI_IDENTITY.md",
            "templates/portable-ai-system/AI 身份文件/AI_COLLABORATION_RULES.md",
            "templates/portable-ai-system/AI 身份文件/AI_CONTEXT_BOUNDARY.md",
            "templates/portable-ai-system/Skills-SOP/organize.md",
            "templates/portable-ai-system/Skills-SOP/review.md",
            "templates/portable-ai-system/Skills-SOP/extract.md",
        ]
        combined = "\n".join(
            (self.repo / path).read_text(encoding="utf-8-sig")
            for path in [
                "README.md",
                "docs/GETTING_STARTED.md",
                "docs/MIGRATION_BACKUP.md",
                "docs/PORTABLE_AI_SYSTEM_ITERATION_PLAN.md",
            ]
        )

        self.assertTrue(portable_templates["ok"], portable_templates)
        self.assertEqual(expected, portable_templates["evidence"])
        for relative in expected:
            path = self.repo / relative
            self.assertTrue(path.exists(), relative)
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("来源", text)
            self.assertIn("下一步", text)
        self.assertIn("-InstallPortableTemplates", combined)
        self.assertIn("AI_IDENTITY.md", combined)
        self.assertIn("Skills-SOP", combined)

    def test_demo_initialization_installs_identity_files_and_sops(self) -> None:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.repo / "scripts" / "init-assistant.ps1"),
                "-Demo",
            ],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

        root = self.repo / "demo" / "vault" / "routine" / "knowledge-organizer"
        for relative in [
            "AI 身份文件/AI_IDENTITY.md",
            "AI 身份文件/AI_COLLABORATION_RULES.md",
            "AI 身份文件/AI_CONTEXT_BOUNDARY.md",
            "Skills-SOP/organize.md",
            "Skills-SOP/review.md",
            "Skills-SOP/extract.md",
        ]:
            path = root / relative
            self.assertTrue(path.exists(), relative)
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("本地知识整理助手", text)
            self.assertIn("下一步", text)

    def test_cli_exposes_only_three_core_actions(self) -> None:
        runner = (self.repo / "run-knowledge-assistant.ps1").read_text(encoding="utf-8-sig")
        readme = (self.repo / "README.md").read_text(encoding="utf-8-sig")

        self.assertIn('[string]$Action = "review"', runner)
        self.assertIn('[ValidateSet("organize", "review", "extract")]', runner)
        self.assertNotIn("remind", runner)
        self.assertNotIn("legacy-index", runner)
        self.assertIn("只保留三件事", readme)

    def test_advanced_tools_are_not_public_product_entrypoints(self) -> None:
        home = (self.repo / "docs" / "assets" / "gui" / "workspace.html").read_text(encoding="utf-8-sig")
        advanced = (self.repo / "docs" / "assets" / "gui" / "advanced.html").read_text(encoding="utf-8-sig")

        self.assertNotIn('href="/advanced"', home)
        self.assertNotIn("tools-entry", home)
        self.assertNotIn("工具维护页", home)
        self.assertNotIn("高级/诊断", home)
        self.assertNotIn("advanced-grid", home)
        self.assertNotIn("runLegacyAction", home)
        for action in ["file-radar", "obsidian-health", "legacy-index", "open-obsidian", "open-guidebook", "open-interaction-guide"]:
            self.assertNotIn(f"runTool('{action}')", advanced)
            self.assertNotIn(action, home)
        self.assertNotIn("查看高级 JSON", advanced)
        self.assertNotIn("console-output", advanced)
        self.assertIn("旧工具已降级", advanced)

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

    def test_generated_guidebook_script_matches_three_operation_positioning(self) -> None:
        script = (self.repo / "scripts" / "generate-guidebook-assets.py").read_text(encoding="utf-8-sig")

        for phrase in [
            "添加资料",
            "搜索回顾",
            "生成 AI 上下文包",
            "推荐搜索词",
            "最多 4 条强证据",
            "加入上下文包",
        ]:
            self.assertIn(phrase, script)
        for obsolete in [
            "知识流怎么用",
            "向下看知识流",
            "四入口",
            "需要提醒时",
        ]:
            self.assertNotIn(obsolete, script)

    def test_gui_harness_verifies_local_target_workbench(self) -> None:
        script = (self.repo / "scripts" / "gui-e2e-playwright.js").read_text(encoding="utf-8-sig")
        runner = (self.repo / "scripts" / "run-gui-e2e.ps1").read_text(encoding="utf-8-sig")
        human_script = (self.repo / "scripts" / "gui-human-usability.js").read_text(encoding="utf-8-sig")
        human_runner = (self.repo / "scripts" / "run-gui-human-usability.ps1").read_text(encoding="utf-8-sig")

        for phrase in [
            ".feature-anchor",
            "一句话答案",
            "命中证据",
            "生成产物",
            "Obsidian 教程",
            "AI 身份文件已可用",
            "本地知识整理助手产品负责人",
            "#localPaths",
            "#fileDropZone",
            "inspect-local-targets",
            "custom-local-paths",
            "missing-file-target-section",
            "if ((await output.count()) === 0) return false",
        ]:
            self.assertIn(phrase, script)
        for phrase in [
            "obsidian_findability",
            "在 Obsidian 里怎么找",
            "文件索引目录",
            "seeded_context_from_review",
            "已加入上下文包候选",
            "确认生成已选上下文包",
            "extract_findability",
            "上下文包在 Obsidian 里怎么找",
            "上下文包目录",
            "recommended_search_terms",
            "推荐搜索词",
            "organize_recommended_search_terms",
            "recommended_search_term_review",
            "runReviewForTerm",
            "推荐词一键搜索回顾",
            "review_source_cards_visible_max_four",
            "data-source-evidence-card",
        ]:
            self.assertIn(phrase, script)
        self.assertIn("e2eLocalPath", runner)
        self.assertIn("LocalPathForE2E", runner)
        self.assertIn("[string]$Browser", runner)
        self.assertIn("--browser", runner)
        self.assertIn("read-only flag did not reach browser", runner)
        self.assertIn("Invoke-PlaywrightClose", runner)
        self.assertIn("Start-Process -FilePath \"npx.cmd\"", runner)
        self.assertIn("Stop-GuiServer", runner)
        self.assertIn("Stop-PortServer -TargetPort $Port", runner)
        self.assertIn("$StartedServer = $false", runner)
        self.assertIn("$script:StartedServer = $true", runner)
        self.assertIn("if ($script:StartedServer)", runner)
        self.assertIn("Invoke-PlaywrightRunCode", runner)
        self.assertIn("run-code timed out", runner)
        self.assertIn("Stop-PlaywrightSessionProcesses", runner)
        self.assertIn("AI_IDENTITY.md", runner)
        self.assertIn("AI_CONTEXT_BOUNDARY.md", runner)

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
            "Evidence-based review",
            "context packaging",
            'const requiredResultLabels = ["result-section"]',
            "没有命中已整理资料",
            "没有找到已整理内容",
        ]:
            self.assertIn(phrase, human_script)
        self.assertNotIn('const requiredResultLabels = ["result-section", "result-actions"]', human_script)

    def test_real_query_qa_script_tracks_true_user_queries(self) -> None:
        script = (self.repo / "scripts" / "run-real-query-qa.py").read_text(encoding="utf-8-sig")

        for phrase in [
            "运营sop",
            "github仓库",
            "简历线程",
            "Obsidian助手",
            "MISSING_QUERY_PREFIX",
            "__no_such_topic_",
            "review",
            "extract",
            "mode\": \"preview\"",
            "must_not_match_top",
            "matched_terms",
            "evidence_excerpt",
            "summary.md",
            "real-query-qa-result.json",
        ]:
            self.assertIn(phrase, script)

    def test_real_query_gui_qa_clicks_true_user_queries(self) -> None:
        script_path = self.repo / "scripts" / "gui-real-query-qa.js"
        runner_path = self.repo / "scripts" / "run-real-query-gui-qa.ps1"
        harness_path = self.repo / "scripts" / "verify-harness.ps1"

        self.assertTrue(script_path.exists(), script_path)
        self.assertTrue(runner_path.exists(), runner_path)
        script = script_path.read_text(encoding="utf-8-sig")
        runner = runner_path.read_text(encoding="utf-8-sig")
        harness = harness_path.read_text(encoding="utf-8-sig")

        for phrase in [
            "运营sop",
            "github仓库",
            "简历线程",
            "Obsidian助手",
            "MISSING_QUERY_PREFIX",
            "#reviewInput",
            "data-source-evidence-card",
            "matched_terms",
            "evidence_excerpt",
            "preview-only",
            "gui-real-query-qa-result.json",
            "gui-real-query-qa-summary.md",
        ]:
            self.assertIn(phrase, script)
        for phrase in [
            "config.local.json",
            "gui-real-query-qa.js",
            "real-query-gui-qa",
            "screenshot",
            "review + extract preview only",
        ]:
            self.assertIn(phrase, runner)
        self.assertIn("real_query_gui_qa", harness)


if __name__ == "__main__":
    unittest.main(verbosity=2)
