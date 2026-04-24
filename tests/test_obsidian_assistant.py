from __future__ import annotations

import importlib.util
import json
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
            "obsidian_run_dir": str(self.vault / "04 例行工作" / "文件管理助手"),
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_guide_writes_file_and_overview_link(self) -> None:
        result = obsidian_assistant.command_guide(self.config)
        guide = Path(result["guide"])
        overview = self.vault / "02 项目" / "Codex" / "00 Codex 总览.md"

        self.assertTrue(guide.exists())
        self.assertIn("Obsidian 新手使用指南", guide.read_text(encoding="utf-8"))
        self.assertIn("[[11 Obsidian 新手使用指南]]", overview.read_text(encoding="utf-8"))

    def test_ask_returns_daily_answer(self) -> None:
        result = obsidian_assistant.command_ask(self.config, "我今天怎么记录工作？", False)
        self.assertTrue(result["ok"])
        self.assertIn("daily", result["answer"])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
