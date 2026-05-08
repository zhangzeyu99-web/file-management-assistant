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

    def test_html_exposes_scenario_first_buttons_without_mojibake(self) -> None:
        html = gui_server.HTML

        for label in [
            "今天先干什么",
            "记录一个任务",
            "这段内容放哪",
            "复盘今天",
            "检查知识库",
            "归档 AI 对话",
            "提取 AI 上下文",
            "复制上下文 prompt",
            "查看文件雷达",
            "打开 Obsidian",
            "快速初始化",
            "打开教程 PDF",
            "查看交互说明图",
            "查看交互说明",
            "新手 10 分钟上手",
            "本地上下文概览",
            "上下文来源",
            "Codex 接手包",
            "生成 Codex 接手包",
            "查看高级 JSON",
            "接手包预览",
            "本地文件 / 目录目标",
            "粘贴本地路径",
            "拖放文件到这里",
            "检查本地目标",
        ]:
            self.assertIn(label, html)
        for required in [
            "Obsidian AI 整理工作台",
            "可视化上下文入口",
            "本地文件",
            "Obsidian",
            "历史报告",
            "本地上下文概览",
            "默认只读",
            "这不是 Codex 本体",
            "不是替代 Codex",
            "让 Codex 接手时少读上下文",
            "本地文件扫描使用配置目录",
            "默认不展示黑色 JSON",
            "hero-illustration.png",
            "feature-icons.png",
            "interaction-guide.html",
            'id="localPaths"',
            'id="fileDropZone"',
            'type="file"',
            "inspect-local-targets",
            "readLocalTargets()",
            "runFileRadar()",
        ]:
            self.assertIn(required, html)
        self.assertIn("renderOutput(data, {show: false})", html)
        self.assertIn("renderWorkbenchResult(action, data)", html)
        self.assertNotIn("<symbol", html)
        self.assertNotIn("<svg", html)
        self.assertNotIn("Codex 文件管理小助手", html)
        self.assertNotIn("生成 Codex 交接", html)
        self.assertNotIn("AI 交接", html)
        self.assertNotIn("今日操作台", html)
        self.assertNotIn("执行结果", html)
        self.assertNotIn("伪控制台", html)
        self.assertNotRegex(html, r"鏂|绠|鍏|浠婃|瀛︿|宸ヤ")

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
