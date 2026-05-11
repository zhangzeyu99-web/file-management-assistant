from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODULE_PATH = ROOT / "knowledge_assistant.py"
SPEC = importlib.util.spec_from_file_location("knowledge_assistant", MODULE_PATH)
assert SPEC and SPEC.loader
knowledge_assistant = importlib.util.module_from_spec(SPEC)
sys.modules["knowledge_assistant"] = knowledge_assistant
SPEC.loader.exec_module(knowledge_assistant)


class KnowledgeAssistantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.vault = self.root / "vault"
        self.fixture = self.root / "fixture"
        self.config_path = self.root / "config.json"
        for path in [
            self.runtime,
            self.fixture,
            self.vault / "00 收件箱",
            self.vault / "01 今日日志",
            self.vault / "02 项目" / "Codex",
            self.vault / "04 例行工作" / "知识行动助手",
            self.vault / "04 例行工作" / "知识整理助手",
        ]:
            path.mkdir(parents=True, exist_ok=True)
        (self.fixture / "NotebookLM Obsidian 教程.txt").write_text(
            "NotebookLM 和 Obsidian 学习资料，适合沉淀成知识卡。",
            encoding="utf-8",
        )
        (self.vault / "04 例行工作" / "知识行动助手" / "旧流程复盘.md").write_text(
            "# 旧流程复盘\n\n文件雷达、知识库体检和 Codex 接手包曾经是主流程。",
            encoding="utf-8",
        )
        (self.vault / "02 项目" / "Codex" / "00 Codex 总览.md").write_text(
            "# Codex 总览\n\n记录 Codex 会话、OpenClaw 记忆和 Obsidian 使用习惯。",
            encoding="utf-8",
        )
        self.config_path.write_text(
            json.dumps(
                {
                    "runtime_root": str(self.runtime),
                    "obsidian_vault": str(self.vault),
                    "obsidian_run_dir": str(self.vault / "04 例行工作" / "知识整理助手"),
                    "allowed_open_roots": [str(self.runtime), str(self.vault), str(self.fixture)],
                    "obsidian_folders": {
                        "inbox": "00 收件箱",
                        "daily": "01 今日日志",
                        "projects": "02 项目",
                        "routine": "04 例行工作",
                        "archive": "99 归档",
                        "codex_project": "Codex",
                    },
                    "watch_roots": [
                        {
                            "name": "Fixture",
                            "path": str(self.fixture),
                            "max_depth": 2,
                            "max_files": 100,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def assertUnifiedResult(self, result: dict, action: str) -> None:
        for key in ["ok", "action", "summary", "sources", "artifacts", "next_actions", "safety", "debug"]:
            self.assertIn(key, result, result)
        self.assertTrue(result["ok"], result)
        self.assertEqual(action, result["action"])
        self.assertIn("不删除", result["safety"])
        self.assertIsInstance(result["sources"], list)
        self.assertIsInstance(result["artifacts"], list)
        self.assertIsInstance(result["next_actions"], list)
        self.assertIsInstance(result["debug"], dict)

    def test_four_core_actions_return_unified_schema(self) -> None:
        organize = knowledge_assistant.run_action(
            "organize",
            {
                "kind": "text",
                "text": "NotebookLM Obsidian 教程需要整理，后续给 AI 复用。",
                "source": "unit-test",
            },
            self.config_path,
        )
        review = knowledge_assistant.run_action("review", {"query": "NotebookLM Obsidian"}, self.config_path)
        extract = knowledge_assistant.run_action(
            "extract",
            {"query": "NotebookLM Obsidian", "request": "帮我继续学习 Obsidian"},
            self.config_path,
        )
        remind = knowledge_assistant.run_action("remind", {}, self.config_path)

        self.assertUnifiedResult(organize, "organize")
        self.assertUnifiedResult(review, "review")
        self.assertUnifiedResult(extract, "extract")
        self.assertUnifiedResult(remind, "remind")

        note_paths = [Path(item["path"]) for item in organize["artifacts"] if item.get("type") == "obsidian-note"]
        self.assertTrue(note_paths, organize)
        self.assertTrue(note_paths[0].exists())
        self.assertIn("生活 / 学习 / 工作", note_paths[0].read_text(encoding="utf-8"))

        self.assertIn("本地摘要", review["summary"])
        self.assertTrue(any("NotebookLM" in item.get("title", "") or "NotebookLM" in item.get("summary", "") for item in review["sources"]))

        self.assertIn("AI 上下文包", extract["summary"])
        self.assertTrue(any(item.get("type") == "prompt" for item in extract["artifacts"]))
        markdown_paths = [Path(item["path"]) for item in extract["artifacts"] if item.get("type") == "markdown"]
        self.assertTrue(markdown_paths, extract)
        self.assertTrue(markdown_paths[0].exists())
        self.assertIn("AI 上下文包", markdown_paths[0].read_text(encoding="utf-8"))

        self.assertIn("今日行动建议", remind["summary"])
        self.assertLessEqual(len(remind["next_actions"]), 3)
        self.assertTrue(any(item.get("type") == "obsidian-note" and "今日行动" in item.get("label", "") for item in remind["artifacts"]))

    def test_review_does_not_fallback_to_unrelated_recent_notes(self) -> None:
        result = knowledge_assistant.run_action("review", {"query": "b站"}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("review", result["action"])
        self.assertEqual([], result["sources"])
        self.assertIn("没有找到", result["summary"])
        self.assertNotIn("找到 5 条", result["summary"])

    def test_review_no_match_is_not_reported_as_completed(self) -> None:
        result = knowledge_assistant.run_action("review", {"query": "zzzxxyyqwerty"}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("review", result["action"])
        self.assertEqual([], result["sources"])
        self.assertEqual([], result["artifacts"])

    def test_extract_refuses_to_fake_context_when_no_sources_match(self) -> None:
        result = knowledge_assistant.run_action("extract", {"request": "完全不存在的火星资料主题"}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("extract", result["action"])
        self.assertEqual([], result["sources"])
        self.assertEqual([], [item for item in result["artifacts"] if item.get("type") == "prompt"])
        self.assertIn("没有找到可用上下文", result["summary"])

    def test_extract_preview_returns_candidates_without_writing_files(self) -> None:
        extract_dir = self.vault / "04 例行工作" / "知识整理助手" / "提取"

        result = knowledge_assistant.run_action(
            "extract",
            {"request": "继续学习 Obsidian", "mode": "preview"},
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual("extract", result["action"])
        self.assertGreaterEqual(len(result["sources"]), 1)
        self.assertEqual([], result["artifacts"])
        self.assertIn("候选来源", result["summary"])
        self.assertEqual("preview", result["debug"]["mode"])
        self.assertFalse(extract_dir.exists(), "preview mode must not write an Obsidian package")

    def test_extract_generate_uses_confirmed_source_paths(self) -> None:
        preview = knowledge_assistant.run_action(
            "extract",
            {"request": "继续优化 Codex 记录", "mode": "preview"},
            self.config_path,
        )
        source_path = preview["sources"][0]["path"]

        result = knowledge_assistant.run_action(
            "extract",
            {"request": "继续优化 Codex 记录", "mode": "generate", "source_paths": [source_path]},
            self.config_path,
        )

        self.assertUnifiedResult(result, "extract")
        self.assertEqual([source_path], [item["path"] for item in result["sources"]])
        self.assertTrue(any(item.get("type") == "prompt" for item in result["artifacts"]))
        self.assertTrue(any(item.get("type") == "markdown" for item in result["artifacts"]))
        self.assertEqual("generate", result["debug"]["mode"])

    def test_organize_local_directory_scans_contents_and_writes_manifest(self) -> None:
        source_dir = self.fixture / "AI_Repo"
        source_dir.mkdir()
        (source_dir / "AI_Decision.html").write_text("<h1>AI decision</h1>", encoding="utf-8")
        (source_dir / "AI 调研报告.pdf").write_bytes(b"%PDF-1.4\nfake")

        result = knowledge_assistant.run_action("organize", {"local_paths": str(source_dir)}, self.config_path)

        self.assertUnifiedResult(result, "organize")
        self.assertIn("扫描 2 个文件", result["summary"])
        self.assertEqual(2, result["debug"]["scan"]["total_files"])
        self.assertTrue(any(item.get("type") == "markdown" and "整理清单" in item.get("label", "") for item in result["artifacts"]))
        note_path = next(Path(item["path"]) for item in result["artifacts"] if item.get("type") == "obsidian-note")
        note_text = note_path.read_text(encoding="utf-8")
        self.assertIn("## 路径扫描结果", note_text)
        self.assertIn("AI_Decision.html", note_text)
        self.assertIn("AI 调研报告.pdf", note_text)
        self.assertIn("不会移动源文件", note_text)

    def test_organize_refuses_missing_local_path_without_text(self) -> None:
        missing = self.fixture / "missing-folder"

        result = knowledge_assistant.run_action("organize", {"local_paths": str(missing)}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("organize", result["action"])
        self.assertEqual([], result["artifacts"])
        self.assertIn("路径不存在", result["summary"])
        self.assertEqual("no_existing_local_paths", result["debug"]["reason"])

    def test_organize_selected_files_only_is_metadata_not_scan(self) -> None:
        result = knowledge_assistant.run_action(
            "organize",
            {"selected_files": [{"name": "report.pdf", "size": 1234, "relative_path": "docs/report.pdf"}]},
            self.config_path,
        )

        self.assertFalse(result["ok"], result)
        self.assertEqual("organize", result["action"])
        self.assertEqual([], result["artifacts"])
        self.assertIn("浏览器选择", result["summary"])
        self.assertEqual("metadata_only", result["debug"]["reason"])

    def test_organize_refuses_empty_input_instead_of_writing_placeholder_note(self) -> None:
        result = knowledge_assistant.run_action("organize", {}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("organize", result["action"])
        self.assertEqual([], result["artifacts"])
        self.assertIn("没有提供", result["summary"])

    def test_daily_action_dedupes_repeated_source_titles(self) -> None:
        target = self.vault / "04 例行工作" / "知识整理助手"
        (target / "gui-a.md").write_text("# GUI 快速记录\n\nGUI 今日行动测试。", encoding="utf-8")
        (target / "gui-b.md").write_text("# GUI 快速记录\n\nGUI 重复标题。", encoding="utf-8")
        (target / "gui-c.md").write_text("# GUI 控制台说明\n\nGUI 已改为知识整理入口。", encoding="utf-8")

        result = knowledge_assistant.run_action("remind", {"query": "GUI 今日行动"}, self.config_path)

        self.assertUnifiedResult(result, "remind")
        titles = [item["title"] for item in result["sources"]]
        self.assertEqual(len(titles), len(set(titles)), result)
        self.assertLessEqual(len(titles), 3)

        second = knowledge_assistant.run_action("remind", {"query": "GUI 今日行动"}, self.config_path)
        self.assertUnifiedResult(second, "remind")
        self.assertNotIn("今日行动建议", [item["title"] for item in second["sources"]])

    def test_daily_action_refuses_to_fake_result_without_sources(self) -> None:
        with tempfile.TemporaryDirectory() as empty_root_raw:
            empty_root = Path(empty_root_raw)
            empty_runtime = empty_root / "runtime"
            empty_vault = empty_root / "vault"
            empty_runtime.mkdir()
            (empty_vault / "04 例行工作" / "知识整理助手").mkdir(parents=True)
            config_path = empty_root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "runtime_root": str(empty_runtime),
                        "obsidian_vault": str(empty_vault),
                        "obsidian_run_dir": str(empty_vault / "04 例行工作" / "知识整理助手"),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = knowledge_assistant.run_action("remind", {}, config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("remind", result["action"])
        self.assertEqual([], result["sources"])
        self.assertEqual([], result["artifacts"])

    def test_legacy_second_pass_indexes_existing_notes_without_moving_them(self) -> None:
        old_paths = [
            self.vault / "04 例行工作" / "知识行动助手" / "旧流程复盘.md",
            self.vault / "02 项目" / "Codex" / "00 Codex 总览.md",
        ]

        result = knowledge_assistant.build_legacy_index(knowledge_assistant.load_config(self.config_path))

        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(result["count"], 2)
        self.assertTrue(Path(result["index_note"]).exists())
        index_text = Path(result["index_note"]).read_text(encoding="utf-8")
        self.assertIn("旧流程复盘", index_text)
        self.assertIn("Codex 总览", index_text)
        for path in old_paths:
            self.assertTrue(path.exists(), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
