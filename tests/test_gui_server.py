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

    def test_status_reports_latest_file_and_obsidian_outputs(self) -> None:
        status = gui_server.build_status(self.config_path)

        self.assertTrue(status["ok"])
        self.assertEqual("本地知识整理助手", status["product"]["name"])
        self.assertEqual(3, status["file_report"]["summary"]["total_files"])
        self.assertTrue(status["file_report"]["html_report"].endswith("report.html"))
        self.assertEqual(2, status["obsidian_report"]["summary"]["total_notes"])
        self.assertTrue(status["obsidian_report"]["markdown_report"].endswith("obsidian-management-report.md"))
        self.assertIn("today", {item["id"] for item in status["scenarios"]})
        self.assertIn("knowledge_feed", status)
        self.assertGreaterEqual(len(status["knowledge_feed"]), 1)
        first_card = status["knowledge_feed"][0]
        for key in ["title", "description", "type", "source_path", "updated_at", "tags", "action_hint"]:
            self.assertIn(key, first_card)
        self.assertTrue(first_card["source_path"].endswith("AI 上下文取用.md"))

    def test_knowledge_feed_dedupes_repeated_titles(self) -> None:
        cards_dir = self.vault / "02 项目" / "知识行动助手" / "Card"
        for index in range(2):
            (cards_dir / f"AI 对话归档 {index}.md").write_text(
                "# AI 对话归档\n\n同类对话归档记录，只应在首页知识流保留一张代表卡。\n",
                encoding="utf-8",
            )
        (cards_dir / "old-product-name.md").write_text(
            "# 文件管理助手复盘\n\n旧产品定位内容应该保留在库里，但不应进入首页知识流。\n",
            encoding="utf-8",
        )
        (cards_dir / "old-action.md").write_text(
            "# 记录一个任务\n\n旧功能入口已经降级，不应作为首页知识卡标题露出。\n",
            encoding="utf-8",
        )

        feed = gui_server.build_knowledge_feed(gui_server.load_config(self.config_path), limit=8)
        titles = [item["title"] for item in feed]

        self.assertEqual(1, titles.count("AI 对话归档"))
        self.assertNotIn("文件管理助手复盘", titles)
        self.assertNotIn("记录一个任务", titles)
        self.assertLessEqual(len(feed), 8)

    def test_knowledge_feed_prioritizes_codex_session_index_and_cards(self) -> None:
        codex_dir = self.vault / "02 项目" / "Codex"
        cards_dir = codex_dir / "知识卡片"
        cards_dir.mkdir(parents=True)
        (codex_dir / "13 Codex 会话标题索引.md").write_text(
            "# Codex 会话标题索引\n\n## 用法\n- 标题按真实 Codex 会话抽取。\n\n## 主题概览\n- AI 工作流/Codex: 66\n\n## 近期标题速览\n- Obsidian 使用指南 `1 天`\n",
            encoding="utf-8",
        )
        (cards_dir / "知识整理助手三主操作.md").write_text(
            "# 知识整理助手三主操作\n\n添加资料、搜索回顾、生成 AI 上下文包。\n",
            encoding="utf-8",
        )

        feed = gui_server.build_knowledge_feed(gui_server.load_config(self.config_path), limit=3)
        titles = [item["title"] for item in feed]
        types = [item["type"] for item in feed]

        self.assertEqual("Codex 会话标题索引", titles[0])
        self.assertEqual("Codex 会话已按主题和近期标题建立索引，可按标题回到原始会话。", feed[0]["takeaway"])
        self.assertIn("知识整理助手三主操作", titles)
        self.assertIn("会话索引", types)
        self.assertIn("知识卡片", types)

    def test_knowledge_detail_is_type_specific_and_connects_related_items(self) -> None:
        codex_dir = self.vault / "02 项目" / "Codex"
        cards_dir = codex_dir / "知识卡片"
        cards_dir.mkdir(parents=True)
        (codex_dir / "13 Codex 会话标题索引.md").write_text(
            "# Codex 会话标题索引\n\n## 用法\n- 标题按真实 Codex 会话抽取。\n- 复制来源路径让 Codex 读取原始 JSONL。\n\n## 主题概览\n- AI 工作流/Codex: 66\n- Obsidian/知识库: 24\n\n## 近期标题速览\n- Obsidian 使用指南 `1 天`\n- 知识卡片沉淀 `2 天`\n",
            encoding="utf-8",
        )
        (cards_dir / "Codex 上下文包规则.md").write_text(
            "# Codex 上下文包规则\n\n## 适用场景\n把 Codex 会话变成 AI 上下文包。\n\n## 关键结论\n- Codex 继续任务前必须读取来源路径。\n\n## 下次怎么用\n- 生成 AI 上下文包时引用会话索引。\n",
            encoding="utf-8",
        )

        feed = gui_server.build_knowledge_feed(gui_server.load_config(self.config_path), limit=3)
        index_item = feed[0]

        self.assertEqual("session-index", index_item["detail_kind"])
        section_titles = [section["title"] for section in index_item["detail_sections"]]
        self.assertIn("怎么使用这个索引", section_titles)
        self.assertIn("主题分布", section_titles)
        self.assertIn("近期会话入口", section_titles)
        self.assertTrue(any("沉淀成知识卡" in item for item in index_item["thinking_prompts"]))
        self.assertTrue(any(item["title"] == "Codex 上下文包规则" for item in index_item["related_items"]))

    def test_knowledge_feed_uses_topic_related_items_instead_of_loose_keywords(self) -> None:
        codex_dir = self.vault / "02 项目" / "Codex"
        cards_dir = codex_dir / "知识卡片"
        cards_dir.mkdir(parents=True)
        (codex_dir / "13 Codex 会话标题索引.md").write_text(
            "# Codex 会话标题索引\n\n## 主题概览\n- AI 工作流/Codex: 66\n\n## 近期标题速览\n- 上下文包生成 `1 天`\n",
            encoding="utf-8",
        )
        (cards_dir / "AI 上下文包规则.md").write_text(
            "# AI 上下文包规则\n\n## 适用场景\n给新的 AI 对话补充已整理上下文。\n\n## 关键结论\n- 先预览候选来源，再生成 prompt。\n",
            encoding="utf-8",
        )
        (cards_dir / "生活收纳清单.md").write_text(
            "# 生活收纳清单\n\n## 适用场景\n整理衣柜、证件和日用品。\n\n## 关键结论\n- 按使用频率分层收纳。\n",
            encoding="utf-8",
        )

        feed = gui_server.build_knowledge_feed(gui_server.load_config(self.config_path), limit=4)
        index_item = feed[0]

        self.assertIn("codex-session", index_item["topic_keys"])
        self.assertIn("ai-context", index_item["topic_keys"])
        self.assertTrue(any(item["title"] == "AI 上下文包规则" for item in index_item["related_items"]))
        self.assertFalse(any(item["title"] == "生活收纳清单" for item in index_item["related_items"]))
        self.assertTrue(all(item["why"].startswith("同属主题：") for item in index_item["related_items"]))

    def test_plain_note_detail_gets_reader_friendly_sections_from_full_markdown(self) -> None:
        note_dir = self.vault / "02 项目" / "学习资料"
        note_dir.mkdir(parents=True)
        (note_dir / "NotebookLM 学习笔记.md").write_text(
            "# NotebookLM 学习笔记\n\n## 背景\n为了学会用 NotebookLM 教 Obsidian，需要把资料包、教程和问答路径整理清楚。\n\n## 关键结论\n- 先上传资料包，再按问题学习。\n- 不要一次处理所有历史文件。\n\n## 下一步\n- 生成一份给 AI 的上下文包。\n",
            encoding="utf-8",
        )

        feed = gui_server.build_knowledge_feed(gui_server.load_config(self.config_path), limit=20)
        item = next(entry for entry in feed if entry["title"] == "NotebookLM 学习笔记")
        section_titles = [section["title"] for section in item["detail_sections"]]

        self.assertEqual("NotebookLM 学习笔记", item["title"])
        self.assertNotIn("##", item["description"])
        self.assertIn("阅读摘要", section_titles)
        self.assertIn("关键信息", section_titles)
        self.assertIn("下一步", section_titles)
        self.assertTrue(any("上传资料包" in value for value in item["conclusions"]))

    def test_knowledge_feed_exposes_structured_reading_fields(self) -> None:
        codex_dir = self.vault / "02 项目" / "Codex"
        cards_dir = codex_dir / "知识卡片"
        cards_dir.mkdir(parents=True)
        (cards_dir / "知识整理助手三主操作.md").write_text(
            """---
type: Card
tags:
  - knowledge-assistant
---

# 知识整理助手三主操作

## 适用场景
把 GUI 从伪控制台收敛成真实有用的知识入口。

## 关键结论
- 添加资料是索引清单，不是复制或搬家。
- 搜索回顾是证据检索，不是无来源问答。

## 下次怎么用
- 输入真实路径生成索引。
- 选择候选来源生成上下文包。

## 来源
- knowledge_assistant.py: `D:\\codex\\file-management-assistant\\knowledge_assistant.py`
""",
            encoding="utf-8",
        )

        feed = gui_server.build_knowledge_feed(gui_server.load_config(self.config_path), limit=1)
        item = feed[0]

        self.assertEqual("知识整理助手三主操作", item["title"])
        self.assertNotIn("type: Card", item["description"])
        self.assertEqual("添加资料是索引清单，不是复制或搬家。", item["takeaway"])
        self.assertIn("真实有用的知识入口", item["scenario"])
        self.assertEqual(2, len(item["conclusions"]))
        self.assertEqual(2, len(item["next_steps"]))
        self.assertTrue(item["source_items"][0]["path"].endswith("knowledge_assistant.py"))

    def test_rejects_unknown_action(self) -> None:
        result = gui_server.run_gui_action("delete-everything", {}, self.config_path)

        self.assertFalse(result["ok"])
        self.assertIn("unsupported", result["error"])

    def test_scenario_entry_actions_return_results(self) -> None:
        today = gui_server.run_gui_action("today", {}, self.config_path)
        file_radar = gui_server.run_gui_action("file-radar", {}, self.config_path)
        health = gui_server.run_gui_action("obsidian-health", {}, self.config_path)

        self.assertTrue(today["ok"], today)
        self.assertIn("今日行动规则", today["summary"])
        self.assertTrue(file_radar["ok"], file_radar)
        self.assertIn("html_report", file_radar)
        self.assertTrue(health["ok"], health)
        self.assertIn("markdown_report", health)

    def test_local_target_input_is_inspected_and_used_by_file_radar(self) -> None:
        manual_dir = self.root / "manual-target"
        manual_dir.mkdir()
        manual_file = manual_dir / "manual-report.md"
        manual_file.write_text("# manual report\n\nGUI should scan this pasted path only.", encoding="utf-8")

        inspect = gui_server.run_gui_action(
            "inspect-local-targets",
            {"local_paths": str(manual_file), "selected_files": [{"name": "manual-report.md", "size": 42}]},
            self.config_path,
        )
        radar = gui_server.run_gui_action("file-radar", {"local_paths": str(manual_file)}, self.config_path)
        organize = gui_server.run_gui_action("organize", {"local_paths": str(manual_dir)}, self.config_path)

        self.assertTrue(inspect["ok"], inspect)
        self.assertEqual("inspect-local-targets", inspect["action"])
        self.assertEqual("custom-local-paths", inspect["mode"])
        self.assertEqual(1, inspect["summary"]["target_count"])
        self.assertEqual(1, inspect["summary"]["existing_count"])
        self.assertEqual(1, inspect["summary"]["selected_file_count"])
        self.assertEqual(str(manual_file), inspect["targets"][0]["path"])
        self.assertTrue(inspect["targets"][0]["is_file"])

        self.assertTrue(radar["ok"], radar)
        self.assertEqual("file-radar", radar["action"])
        self.assertEqual("custom-local-paths", radar["target_mode"])
        self.assertEqual(1, radar["total_files"])
        self.assertEqual(1, radar["scan_targets"]["summary"]["existing_count"])
        self.assertTrue(Path(radar["html_report"]).exists())
        self.assertTrue(Path(radar["summary_json"]).exists())

        self.assertTrue(organize["ok"], organize)
        self.assertEqual("organize", organize["action"])
        self.assertIn("已扫描 1 个文件", organize["summary"])
        self.assertEqual(1, organize["debug"]["scan"]["total_files"])
        self.assertTrue(any(item.get("type") == "markdown" and "整理清单" in item.get("label", "") for item in organize["artifacts"]))

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
        self.assertIn("AI 上下文取用", prompt)
        self.assertNotIn("交接记录", prompt)

    def test_ai_chat_archive_and_context_actions_are_separate(self) -> None:
        archive = gui_server.run_gui_action(
            "archive-ai-chat",
            {
                "title": "NotebookLM 教程讨论",
                "source": "Codex 会话",
                "background": "讨论如何让 Obsidian 新手理解助手用途",
                "conclusions": "归档 AI 对话和提取 AI 上下文必须分成两个功能",
                "outputs": "README 与 GUI 首屏",
                "open_items": "补产品化文案",
            },
            self.config_path,
        )
        context = gui_server.run_gui_action(
            "build-ai-context",
            {"query": "AI 上下文取用", "request": "继续优化产品首屏"},
            self.config_path,
        )

        self.assertTrue(archive["ok"], archive)
        self.assertEqual("archive-ai-chat", archive["action"])
        self.assertTrue(Path(archive["note"]).exists())
        archive_text = Path(archive["note"]).read_text(encoding="utf-8")
        self.assertIn("AI 对话归档", archive_text)
        self.assertIn("已有 AI 对话整理", archive_text)
        self.assertNotIn("补充给新的 AI 对话", archive_text)

        self.assertTrue(context["ok"], context)
        self.assertEqual("build-ai-context", context["action"])
        self.assertIn("sources", context)
        self.assertIn("compressed_context", context)
        self.assertIn("next_request", context)
        self.assertIn("safety", context)
        self.assertTrue(any(str(item["path"]).endswith("AI 上下文取用.md") for item in context["sources"]), context)
        self.assertIn("继续优化产品首屏", context["prompt"])
        self.assertIn("AI 上下文取用", context["prompt"])

    def test_core_knowledge_actions_are_exposed_through_gui_api(self) -> None:
        organize = gui_server.run_gui_action(
            "organize",
            {"kind": "text", "text": "NotebookLM Obsidian 教程需要整理", "source": "GUI test"},
            self.config_path,
        )
        review = gui_server.run_gui_action("review", {"query": "NotebookLM Obsidian"}, self.config_path)
        extract = gui_server.run_gui_action("extract", {"query": "NotebookLM", "request": "继续学习 Obsidian"}, self.config_path)
        remind = gui_server.run_gui_action("remind", {}, self.config_path)

        for action, result in {
            "organize": organize,
            "review": review,
            "extract": extract,
            "remind": remind,
        }.items():
            self.assertTrue(result["ok"], result)
            self.assertEqual(action, result["action"])
            for key in ["summary", "sources", "artifacts", "next_actions", "safety", "debug"]:
                self.assertIn(key, result, result)
        self.assertIn("AI 上下文包", extract["summary"])
        self.assertIn("今日行动建议", remind["summary"])

    def test_html_exposes_three_primary_operations_without_product_drift(self) -> None:
        html = gui_server.HTML

        for label in [
            "本地知识整理助手",
            "添加资料",
            "搜索回顾",
            "生成 AI 上下文包",
            "AI 上下文包",
            "工具维护页",
            "知识流",
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
            'id="knowledgeFeed"',
            "renderKnowledgeFeed",
            "openKnowledgeDetail",
            "一句话结论",
            "适用场景",
            "关键结论",
            "继续使用",
            "关联内容",
            "可追问问题",
            "renderDetailSections",
            "renderRelatedItems",
            "renderThinkingPrompts",
            "data-knowledge-card",
            "action-section",
            "site-action-result",
            "只生成建议和新记录",
            "不改动你的源文件",
            "工具维护页",
            'href="/advanced"',
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
        ]:
            self.assertIn(required, html)
        for productized in [
            "向下浏览",
            "来源可追溯",
            "完成情况",
            "参考来源",
            "保存位置",
            "下一步建议",
            "result-sections",
            "noMatchReview",
            "未完成",
            "找到候选",
            "已生成",
            "工具维护页",
            'href="/advanced"',
        ]:
            self.assertIn(productized, html)
        self.assertIn("renderOutput(data, {show: false})", html)
        self.assertIn("renderActionResult(renderTarget, data)", html)
        self.assertIn("tools-entry", html)
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
        self.assertNotIn("boundary-grid", html)
        self.assertNotIn("boundary-card", html)
        self.assertNotIn("hero-illustration.png", html)
        self.assertNotIn("高级/诊断", html)
        self.assertNotIn("advanced-grid", html)
        self.assertNotIn("runLegacyAction", html)
        self.assertNotIn("function toggleOutput", html)
        self.assertNotRegex(html, r"鏂|绠|鍏|浠婃|瀛︿|宸ヤ")
        self.assertNotIn('<button class="result-button" onclick="toggleOutput()">', html)
        self.assertNotIn('<button class="advanced-button" onclick="toggleOutput()">', html)

    def test_advanced_tools_page_exposes_only_real_actions(self) -> None:
        advanced = (gui_server.ROOT / "docs" / "assets" / "gui" / "advanced.html").read_text(encoding="utf-8-sig")

        for phrase in ["工具维护页", "诊断与维护", "打开资料", "查看文件雷达", "检查知识库", "二次整理旧资料", "打开 Obsidian", "打开教程 PDF", "打开交互说明"]:
            self.assertIn(phrase, advanced)
        for action in ["file-radar", "obsidian-health", "legacy-index", "open-obsidian", "open-guidebook", "open-interaction-guide"]:
            self.assertIn(f"runTool('{action}')", advanced)
        for readable_source in ["data?.by_root", "data.total_files", "来源根"]:
            self.assertIn(readable_source, advanced)
        for obsolete in ["查看高级 JSON", "console-output", "今日操作台", "伪控制台", "runLegacyAction"]:
            self.assertNotIn(obsolete, advanced)

    def test_interaction_guide_action_exposes_generated_assets(self) -> None:
        result = gui_server.run_gui_action("open-interaction-guide", {}, self.config_path)

        self.assertTrue(result["ok"], result)
        self.assertEqual("/assets/gui/interaction-guide.html", result["url"])
        self.assertTrue(Path(result["opened"]).exists())
        self.assertTrue(any(path.endswith("interaction-map.png") for path in result["assets"]))
        self.assertTrue(any(path.endswith("interaction-states.png") for path in result["assets"]))
        for path in result["assets"]:
            self.assertTrue(Path(path).exists(), path)

    def test_evolution_actions_return_actionable_outputs(self) -> None:
        onboarding = gui_server.run_gui_action("onboarding", {}, self.config_path)
        thinking = gui_server.run_gui_action("deep-thinking", {}, self.config_path)
        knowledge = gui_server.run_gui_action("knowledge-index", {"query": "ACT 方法"}, self.config_path)
        guidebook = gui_server.run_gui_action("guidebook", {}, self.config_path)

        self.assertTrue(onboarding["ok"], onboarding)
        self.assertIn("commands", onboarding)
        self.assertTrue(thinking["ok"], thinking)
        self.assertEqual(["Action", "Card", "Time", "X-AI"], [item["mode"] for item in thinking["prompts"]])
        self.assertTrue(knowledge["ok"], knowledge)
        self.assertIn("items", knowledge["index"])
        self.assertTrue(guidebook["ok"], guidebook)
        self.assertEqual(7, guidebook["page_count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
