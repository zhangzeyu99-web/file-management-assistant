from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "assistant_evolution.py"
SPEC = importlib.util.spec_from_file_location("assistant_evolution", MODULE_PATH)
assert SPEC and SPEC.loader
assistant_evolution = importlib.util.module_from_spec(SPEC)
sys.modules["assistant_evolution"] = assistant_evolution
SPEC.loader.exec_module(assistant_evolution)


class AssistantEvolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vault = self.root / "vault"
        self.runtime = self.root / "runtime"
        self.config_path = self.root / "config.json"
        (self.vault / "02 项目" / "知识行动助手" / "Action").mkdir(parents=True)
        (self.vault / "02 项目" / "知识行动助手" / "Card").mkdir(parents=True)
        (self.vault / "04 例行工作" / "知识行动助手" / "Time").mkdir(parents=True)
        (self.vault / "02 项目" / "知识行动助手" / "Action" / "任务 A.md").write_text(
            "# 任务 A\n\n类型：Action\n来源：Codex 会话\n\n## 下一步\n\n- 验证 GUI 入口。\n",
            encoding="utf-8",
        )
        (self.vault / "02 项目" / "知识行动助手" / "Card" / "ACT 方法.md").write_text(
            "# ACT 方法\n\n类型：Card\n来源：教程\n\n## 关键结论\n\n先行动，再沉淀知识。\n",
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

    def test_guidebook_catalog_tracks_pdf_and_pages(self) -> None:
        catalog = assistant_evolution.build_guidebook_catalog(Path(__file__).resolve().parents[1])

        self.assertTrue(catalog["ok"], catalog)
        self.assertTrue(catalog["pdf"].endswith("knowledge-action-assistant-tutorial.pdf"))
        self.assertEqual(7, catalog["page_count"])
        self.assertEqual(7, len(catalog["slides"]))

    def test_initialization_plan_is_fast_and_non_destructive(self) -> None:
        plan = assistant_evolution.build_initialization_plan(self.config_path)

        self.assertTrue(plan["ok"], plan)
        self.assertIn("一键初始化", plan["title"])
        self.assertIn("config.local.json", "\n".join(plan["steps"]))
        self.assertIn("start-assistant-gui.ps1", "\n".join(plan["commands"]))
        self.assertIn("不删除", plan["safety"])

    def test_deep_thinking_prompts_cover_four_act_modes(self) -> None:
        prompts = assistant_evolution.build_deep_thinking_prompts()

        self.assertEqual(["Action", "Card", "Time", "X-AI"], [item["mode"] for item in prompts])
        combined = "\n".join(question for item in prompts for question in item["questions"])
        self.assertIn("为什么现在做", combined)
        self.assertIn("验收标准", combined)
        self.assertIn("复用条件", combined)
        self.assertIn("边界", combined)

    def test_knowledge_index_and_call_plan_make_notes_reusable(self) -> None:
        config = assistant_evolution.load_config(self.config_path)
        index = assistant_evolution.build_knowledge_index(config)
        call = assistant_evolution.build_knowledge_call_plan(config, "我想复用 ACT 方法")

        self.assertGreaterEqual(index["count"], 2)
        self.assertIn("ACT 方法", [item["title"] for item in index["items"]])
        self.assertTrue(call["ok"], call)
        self.assertIn("ACT 方法", call["top_matches"][0]["title"])
        self.assertIn("引用这条 Card", call["next_action"])

    def test_self_evolution_report_writes_runtime_and_obsidian_outputs(self) -> None:
        result = assistant_evolution.run_self_evolution(self.config_path)

        self.assertTrue(result["ok"], result)
        self.assertTrue(Path(result["markdown_report"]).exists())
        self.assertTrue(Path(result["json_report"]).exists())
        self.assertTrue(Path(result["obsidian_note"]).exists())
        report = Path(result["markdown_report"]).read_text(encoding="utf-8")
        self.assertIn("交互怎么更方便", report)
        self.assertIn("安装部署初始化更快捷", report)
        self.assertIn("引领使用者深度思考", report)
        self.assertIn("归纳内容如何调用", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
