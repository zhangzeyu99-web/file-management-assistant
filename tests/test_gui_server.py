from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "gui_server.py"
SPEC = importlib.util.spec_from_file_location("gui_server", MODULE_PATH)
assert SPEC and SPEC.loader
gui_server = importlib.util.module_from_spec(SPEC)
sys.modules["gui_server"] = gui_server
SPEC.loader.exec_module(gui_server)


class GuiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_root = Path(__file__).resolve().parents[1] / ".tmp-tests"
        self.tmp_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=self.tmp_root)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.vault = self.root / "vault"
        self.config_path = self.root / "config.json"
        (self.runtime / "runs" / "2026-04-27" / "120000").mkdir(parents=True)
        (self.runtime / "runs" / "2026-04-27" / "120000-obsidian").mkdir(parents=True)
        (self.vault / "00 收件箱").mkdir(parents=True)
        (self.vault / "01 今日日志").mkdir(parents=True)
        (self.vault / "04 例行工作" / "知识行动助手").mkdir(parents=True)
        (self.vault / "02 项目" / "知识行动助手" / "Card").mkdir(parents=True)
        (self.vault / "02 项目" / "知识行动助手" / "Card" / "AI 上下文取用.md").write_text(
            "# AI 上下文取用\n\n类型：Card\n来源：产品化计划\n\n## 关键结论\n\n先扫描已整理知识库，再把相关路径、摘要和下一步请求补给新的 AI 对话。\n",
            encoding="utf-8",
        )

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

    def test_status_reports_three_operation_product_status_without_public_feed(self) -> None:
        status = gui_server.build_status(self.config_path)

        self.assertTrue(status["ok"])
        self.assertEqual("本地知识整理助手", status["product"]["name"])
        self.assertEqual(str(self.vault), status["vault"])
        self.assertEqual(str(self.runtime), status["runtime_root"])
        self.assertNotIn("file_report", status)
        self.assertNotIn("obsidian_report", status)
        self.assertNotIn("scenarios", status)
        self.assertNotIn("guidebook", status)
        self.assertNotIn("knowledge_feed", status)
        self.assertEqual(3, status["metrics"]["core_operations"])
        self.assertEqual(0, status["metrics"]["source_file_mutations"])

    def test_status_counts_obsidian_markdown_notes_for_home_metric(self) -> None:
        (self.vault / "01 今日日志" / "2026-05-26.md").write_text("# 今日笔记", encoding="utf-8")
        (self.vault / "00 收件箱" / "clip.md").write_text("# 收件箱资料", encoding="utf-8")
        (self.vault / ".obsidian").mkdir()
        (self.vault / ".obsidian" / "appearance.json").write_text("{}", encoding="utf-8")

        status = gui_server.build_status(self.config_path)

        self.assertEqual(3, status["metrics"]["obsidian_notes"])

    def test_rejects_unknown_action(self) -> None:
        result = gui_server.run_gui_action("delete-everything", {}, self.config_path)

        self.assertFalse(result["ok"])
        self.assertIn("unsupported", result["error"])

    def test_not_found_action_results_use_http_200_for_clean_gui_console(self) -> None:
        self.assertEqual(200, gui_server.http_status_for_action_result({"ok": False, "status": "not_found"}))
        self.assertEqual(400, gui_server.http_status_for_action_result({"ok": False, "error": "unsupported action"}))

    def test_non_core_gui_actions_are_deprecated(self) -> None:
        for action in [
            "today",
            "file-radar",
            "obsidian-health",
            "full-scan",
            "guide",
            "scenarios",
            "scenario-demo",
            "guidebook",
            "onboarding",
            "deep-thinking",
            "knowledge-index",
            "archive-ai-chat",
            "build-ai-context",
            "ask",
            "capture",
            "daily",
            "action-note",
            "card-note",
            "time-review",
            "inbox-route",
            "codex-prompt",
            "open-obsidian",
            "open-guidebook",
            "open-interaction-guide",
            "open-codex",
            "remind",
            "legacy-index",
        ]:
            with self.subTest(action=action):
                result = gui_server.run_gui_action(action, {}, self.config_path)
                self.assertFalse(result["ok"], result)
                self.assertEqual(action, result["action"])
                self.assertEqual("deprecated", result["status"])
                self.assertEqual(["添加资料", "搜索回顾", "生成 AI 上下文包"], result["next_actions"])

    def test_local_target_input_is_inspected_and_used_by_organize(self) -> None:
        manual_dir = self.root / "manual-target"
        manual_dir.mkdir()
        manual_file = manual_dir / "manual-report.md"
        manual_file.write_text("# manual report\n\nGUI should scan this pasted path only.", encoding="utf-8")

        inspect = gui_server.run_gui_action(
            "inspect-local-targets",
            {"local_paths": str(manual_file), "selected_files": [{"name": "manual-report.md", "size": 42}]},
            self.config_path,
        )
        organize = gui_server.run_gui_action("organize", {"local_paths": str(manual_dir)}, self.config_path)

        self.assertTrue(inspect["ok"], inspect)
        self.assertEqual("inspect-local-targets", inspect["action"])
        self.assertEqual("custom-local-paths", inspect["mode"])
        self.assertEqual(1, inspect["summary"]["target_count"])
        self.assertEqual(1, inspect["summary"]["existing_count"])
        self.assertEqual(1, inspect["summary"]["selected_file_count"])
        self.assertEqual(str(manual_file), inspect["targets"][0]["path"])
        self.assertTrue(inspect["targets"][0]["is_file"])

        self.assertTrue(organize["ok"], organize)
        self.assertEqual("organize", organize["action"])
        self.assertIn("已扫描 1 个文件", organize["summary"])
        self.assertEqual(1, organize["debug"]["scan"]["total_files"])
        self.assertTrue(any(item.get("type") == "markdown" and "整理清单" in item.get("label", "") for item in organize["artifacts"]))

    def test_open_path_opens_vault_markdown_with_obsidian_uri(self) -> None:
        note = self.vault / "02 项目" / "知识行动助手" / "Card" / "AI 上下文取用.md"

        with patch.object(gui_server.webbrowser, "open") as open_mock, patch.object(gui_server.os, "startfile") as start_mock:
            result = gui_server.run_gui_action("open-path", {"path": str(note)}, self.config_path)

        self.assertTrue(result["ok"], result)
        self.assertEqual("obsidian", result["opened_as"])
        open_mock.assert_called_once()
        opened_uri = open_mock.call_args.args[0]
        self.assertTrue(opened_uri.startswith("obsidian://open?"), opened_uri)
        self.assertIn("vault=vault", opened_uri)
        self.assertIn("AI%20%E4%B8%8A%E4%B8%8B%E6%96%87%E5%8F%96%E7%94%A8.md", opened_uri)
        start_mock.assert_not_called()

    def test_open_path_rejects_files_outside_allowed_roots(self) -> None:
        outside = self.root / "outside.md"
        outside.write_text("# outside\n\n不应被 GUI 打开。", encoding="utf-8")
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["allowed_open_roots"] = [str(self.runtime), str(self.vault)]
        self.config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

        with patch.object(gui_server.webbrowser, "open") as open_mock, patch.object(gui_server.os, "startfile") as start_mock:
            result = gui_server.run_gui_action("open-path", {"path": str(outside)}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertIn("not allowed", result["error"])
        open_mock.assert_not_called()
        start_mock.assert_not_called()

    def test_removed_act_shortcuts_do_not_write_to_vault(self) -> None:
        before = set(self.vault.rglob("*.md"))

        for action in ["capture", "daily", "action-note", "card-note", "time-review"]:
            result = gui_server.run_gui_action(
                action,
                {"title": "GUI 不应写入", "body": "旧 ACT 快捷入口已下线"},
                self.config_path,
            )
            self.assertFalse(result["ok"], result)

        after = set(self.vault.rglob("*.md"))
        self.assertEqual(before, after)

    def test_old_ai_archive_and_context_actions_are_not_gui_products(self) -> None:
        archive = gui_server.run_gui_action("archive-ai-chat", {"title": "NotebookLM 教程讨论"}, self.config_path)
        context = gui_server.run_gui_action("build-ai-context", {"query": "AI 上下文取用"}, self.config_path)

        self.assertFalse(archive["ok"], archive)
        self.assertFalse(context["ok"], context)
        self.assertEqual("deprecated", archive["status"])
        self.assertEqual("deprecated", context["status"])
        self.assertIn("生成 AI 上下文包", context["next_actions"])

    def test_core_knowledge_actions_are_exposed_through_gui_api(self) -> None:
        organize = gui_server.run_gui_action(
            "organize",
            {"kind": "text", "text": "NotebookLM Obsidian 教程需要整理", "source": "GUI test"},
            self.config_path,
        )
        review = gui_server.run_gui_action("review", {"query": "NotebookLM Obsidian"}, self.config_path)
        extract = gui_server.run_gui_action("extract", {"query": "NotebookLM", "request": "继续学习 Obsidian"}, self.config_path)

        for action, result in {
            "organize": organize,
            "review": review,
            "extract": extract,
        }.items():
            self.assertTrue(result["ok"], result)
            self.assertEqual(action, result["action"])
            for key in ["summary", "sources", "artifacts", "next_actions", "safety", "debug"]:
                self.assertIn(key, result, result)
        self.assertIn("AI 上下文包", extract["summary"])

    def test_html_exposes_only_three_primary_operations_without_knowledge_feed(self) -> None:
        html = gui_server.HTML

        for label in [
            "本地知识整理助手",
            "添加资料",
            "搜索回顾",
            "生成 AI 上下文包",
            "AI 上下文包",
            "本地文件 / 目录目标",
            "粘贴本地路径",
            "拖放文件到这里",
            "检查本地目标",
        ]:
            self.assertIn(label, html)
        self.assertNotIn("今日提醒", html)
        self.assertNotIn("今日行动</h2>", html)
        self.assertNotIn("href=\"#remind\"", html)
        self.assertNotIn("runCoreAction('remind')", html)
        self.assertEqual(3, html.count('class="feature-anchor"'))
        for required in [
            "site-hero",
            "feature-anchor",
            'href="#organize"',
            'href="#review"',
            'href="#extract"',
            "action-section",
            "site-action-result",
            "只生成建议和新记录",
            "不改动你的源文件",
            "feature-icons.png",
            'id="localPaths"',
            'id="fileDropZone"',
            'type="file"',
            "runCoreAction('organize')",
            "runCoreAction('review')",
            "previewExtract()",
            "generateExtractFromPreview()",
            "候选来源",
            "确认生成上下文包",
            "inspect-local-targets",
            "readLocalTargets()",
            "一句话答案",
            "命中证据",
            "命中词",
            "证据摘录",
            "加入上下文包",
            "metrics?.obsidian_notes",
            "metrics?.core_operations",
            "metrics?.source_file_mutations",
        ]:
            self.assertIn(required, html)
        self.assertNotIn("status.knowledge_feed", html)
        self.assertNotIn("status.file_report", html)
        self.assertNotIn("statFeed", html)
        self.assertNotIn("statFiles", html)
        for productized in [
            "来源可追溯",
            "命中证据",
            "下一步建议",
            "result-sections",
            "noMatchReview",
            "未完成",
            "找到候选",
            "已生成",
        ]:
            self.assertIn(productized, html)
        self.assertIn("renderOutput(data, {show: false})", html)
        self.assertIn("renderActionResult(renderTarget, data)", html)
        self.assertNotIn("<symbol", html)
        self.assertNotIn("<svg", html)
        self.assertNotIn("Codex 文件管理小助手", html)
        self.assertNotIn("生成 Codex 交接", html)
        self.assertNotIn("AI 交接", html)
        self.assertNotIn("今日操作台", html)
        self.assertNotIn("执行结果", html)
        self.assertNotIn("伪控制台", html)
        self.assertNotIn("可视化上下文入口", html)
        self.assertNotIn("Obsidian AI 整理工作台", html)
        self.assertNotIn("Codex 接手包", html)
        self.assertNotIn("生成 Codex 接手包", html)
        self.assertNotIn("这不是 Codex 本体", html)
        self.assertNotIn("不是替代 Codex", html)
        self.assertNotIn("workbenchResult", html)
        self.assertNotIn("primary-actions", html)
        self.assertNotIn("status-panel", html)
        self.assertNotIn("本地状态摘要", html)
        self.assertNotIn("站点式知识库", html)
        self.assertNotIn("首屏极简", html)
        self.assertNotIn("默认只读", html)
        self.assertNotIn("不删除、不移动、不重命名、不重写源文件", html)
        self.assertNotIn("四个轻量操作区", html)
        self.assertNotIn("首页不再堆功能", html)
        self.assertNotIn("每次点击后", html)
        self.assertNotIn("hero-kicker", html)
        self.assertNotIn("知识流", html)
        self.assertNotIn('id="knowledgeFeed"', html)
        self.assertNotIn("renderKnowledgeFeed", html)
        self.assertNotIn("openKnowledgeDetail", html)
        self.assertNotIn("完成情况", html)
        self.assertNotIn("保存位置", html)
        self.assertNotIn("boundary-grid", html)
        self.assertNotIn("boundary-card", html)
        self.assertNotIn("hero-illustration.png", html)
        self.assertNotIn("高级/诊断", html)
        self.assertNotIn("advanced-grid", html)
        self.assertNotIn("runLegacyAction", html)
        self.assertNotIn("工具维护页", html)
        self.assertNotIn("工具页", html)
        self.assertNotIn('href="/advanced"', html)
        self.assertNotIn("tools-entry", html)
        for deprecated_action in [
            "file-radar",
            "obsidian-health",
            "legacy-index",
            "archive-ai-chat",
            "build-ai-context",
            "open-obsidian",
            "open-guidebook",
            "open-interaction-guide",
        ]:
            self.assertNotIn(deprecated_action, html)
        self.assertNotIn("function toggleOutput", html)
        self.assertNotRegex(html, r"鏂|绠|鍏|浠婃|瀛︿|宸ヤ")
        self.assertNotIn('<button class="result-button" onclick="toggleOutput()">', html)
        self.assertNotIn('<button class="advanced-button" onclick="toggleOutput()">', html)

    def test_result_layout_uses_document_cards_for_sources_paths_prompt_and_artifacts(self) -> None:
        html = gui_server.HTML

        for required in [
            "result-document",
            "result-summary-card",
            "source-card-grid",
            "source-card",
            "data-source-evidence-card",
            "visibleSources",
            "hiddenSourceCount",
            "source-more-card",
            "path-chip",
            "artifact-shelf",
            "artifact-card",
            "prompt-preview",
            "renderSourceCards",
            "renderArtifactShelf",
            "renderPromptPreview",
            "复制路径",
            "复制 prompt",
            "打开产物",
        ]:
            self.assertIn(required, html)
        self.assertIn("sources.slice(0, 4)", html)
        self.assertNotIn("sources.slice(0, 6)", html)
        self.assertNotIn("最近来源：", html)
        self.assertNotIn("产物路径：", html)

    def test_html_shows_pending_indexing_and_non_destructive_source_actions(self) -> None:
        html = gui_server.HTML

        for required in [
            "renderPendingAction",
            "正在建立索引",
            "首查会建立本地索引",
            "openPathWithoutReplacingResult",
            "showInlineStatus",
            "打开来源中",
            "renderSeededExtractSource",
            "已加入上下文包候选",
            "确认生成上下文包",
        ]:
            self.assertIn(required, html)
        self.assertNotIn("openSpecificPath(path) {\n      if (!path) return null;\n      return api(\"open-path\"", html)

    def test_html_explains_where_to_find_new_obsidian_notes(self) -> None:
        html = gui_server.HTML

        for required in [
            "renderObsidianLocation",
            "在 Obsidian 里怎么找",
            "整理记录",
            "文件索引目录",
            "打开整理目录",
            "搜索回顾可直接搜文件名、路径或摘录关键词",
        ]:
            self.assertIn(required, html)

    def test_html_shows_recommended_search_terms_after_organize(self) -> None:
        html = gui_server.HTML

        for required in [
            "renderRecommendedSearchTerms",
            "推荐搜索词",
            "点击后会自动填入搜索回顾并执行",
            "runReviewForTerm",
            "recommended_search_terms",
        ]:
            self.assertIn(required, html)

    def test_html_explains_where_to_find_generated_context_packages(self) -> None:
        html = gui_server.HTML

        for required in [
            "renderExtractLocation",
            "上下文包在 Obsidian 里怎么找",
            "上下文包笔记",
            "上下文包目录",
            "runtime Markdown",
            "搜索回顾可搜上下文包标题、来源路径或 prompt 关键词",
        ]:
            self.assertIn(required, html)

    def test_advanced_page_is_degraded_to_static_notice(self) -> None:
        advanced = (gui_server.ROOT / "docs" / "assets" / "gui" / "advanced.html").read_text(encoding="utf-8-sig")

        for phrase in ["旧工具已降级", "添加资料", "搜索回顾", "生成 AI 上下文包"]:
            self.assertIn(phrase, advanced)
        for obsolete in [
            "查看高级 JSON",
            "console-output",
            "今日操作台",
            "伪控制台",
            "runLegacyAction",
            "runTool(",
            "查看文件雷达",
            "检查知识库",
            "二次整理旧资料",
            "打开 Obsidian",
            "打开教程 PDF",
            "打开交互说明",
            "file-radar",
            "obsidian-health",
            "legacy-index",
        ]:
            self.assertNotIn(obsolete, advanced)

    def test_interaction_guide_action_is_deprecated_in_gui_api(self) -> None:
        result = gui_server.run_gui_action("open-interaction-guide", {}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("deprecated", result["status"])

    def test_evolution_actions_are_not_public_gui_products(self) -> None:
        for action in ["onboarding", "deep-thinking", "knowledge-index", "guidebook"]:
            result = gui_server.run_gui_action(action, {"query": "ACT 方法"}, self.config_path)
            self.assertFalse(result["ok"], result)
            self.assertEqual("deprecated", result["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
