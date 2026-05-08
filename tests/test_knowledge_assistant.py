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

        self.assertIn("今日提醒", remind["summary"])
        self.assertLessEqual(len(remind["next_actions"]), 3)

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
