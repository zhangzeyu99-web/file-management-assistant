from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "obsidian_assistant.py"
SPEC = importlib.util.spec_from_file_location("obsidian_assistant", MODULE_PATH)
assert SPEC and SPEC.loader
obsidian_assistant = importlib.util.module_from_spec(SPEC)
sys.modules["obsidian_assistant"] = obsidian_assistant
SPEC.loader.exec_module(obsidian_assistant)


class ObsidianAssistantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name) / "vault"
        (self.vault / "02 项目" / "Codex").mkdir(parents=True)
        (self.vault / "00 收件箱").mkdir(parents=True)
        (self.vault / "01 今日日志").mkdir(parents=True)
        (self.vault / "02 项目" / "Codex" / "00 Codex 总览.md").write_text(
            "# Codex 总览\n\n- [[10 高难长任务 Harness 复盘]]\n",
            encoding="utf-8",
        )
        self.config = {
            "obsidian_vault": str(self.vault),
            "obsidian_run_dir": str(self.vault / "04 例行工作" / "知识行动助手"),
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_guide_writes_file_and_overview_link(self) -> None:
        result = obsidian_assistant.command_guide(self.config)
        guide = Path(result["guide"])
        overview = self.vault / "02 项目" / "Codex" / "00 Codex 总览.md"

        self.assertTrue(guide.exists())
        guide_text = guide.read_text(encoding="utf-8")
        overview_text = overview.read_text(encoding="utf-8")
        self.assertIn("Obsidian + AI 知识行动助手使用指南", guide_text)
        self.assertIn("生活 / 学习 / 工作", guide_text)
        self.assertIn("Action / Card / Time / X-AI", guide_text)
        self.assertIn("[[11 Obsidian + AI 知识行动助手使用指南]]", overview_text)
        self.assertNotRegex(guide_text, r"鏂|绠|鍏|浠婃|瀛︿|宸ヤ")

    def test_ask_returns_daily_answer(self) -> None:
        result = obsidian_assistant.command_ask(self.config, "我今天怎么记录工作？", False)
        self.assertTrue(result["ok"])
        self.assertIn("今日轻量规则", result["answer"])
        self.assertIn("Action", result["answer"])

    def test_ask_returns_behavior_profile_answer(self) -> None:
        result = obsidian_assistant.command_ask(self.config, "根据我的习惯怎么帮我？", False)
        self.assertTrue(result["ok"])
        self.assertIn("先读真实文件", result["answer"])
        self.assertIn("不要停在建议", result["answer"])

    def test_capture_and_daily_write_notes(self) -> None:
        capture = obsidian_assistant.command_capture(self.config, "测试想法", "内容", ["idea"])
        self.assertTrue(Path(capture["note"]).exists())

        daily = obsidian_assistant.command_daily(
            self.config,
            done=["完成测试"],
            next_items=["继续整理"],
            blockers=["暂无"],
        )
        daily_path = Path(daily["daily"])
        self.assertTrue(daily_path.exists())
        self.assertIn("完成测试", daily_path.read_text(encoding="utf-8"))

    def test_act_note_helpers_write_expected_sections(self) -> None:
        action = obsidian_assistant.command_action_note(
            self.config,
            title="更新知识行动助手",
            domain="工作",
            goal="完成结构重整",
            source="Codex 会话",
        )
        card = obsidian_assistant.command_card_note(
            self.config,
            title="ACT 方法",
            domain="学习",
            source="Obsidian+AI 课程",
            conclusion="先行动，再沉淀知识。",
        )
        review = obsidian_assistant.command_time_review(
            self.config,
            title="今日复盘",
            period="daily",
            done=["完成结构设计"],
            next_items=["跑验证"],
        )

        action_text = Path(action["note"]).read_text(encoding="utf-8")
        card_text = Path(card["note"]).read_text(encoding="utf-8")
        review_text = Path(review["note"]).read_text(encoding="utf-8")

        self.assertIn("## 任务背景", action_text)
        self.assertIn("## 任务成果", action_text)
        self.assertIn("## 适用场景", card_text)
        self.assertIn("## 关键结论", card_text)
        self.assertIn("## 归档候选", review_text)
        self.assertIn("## 结构调整", review_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
