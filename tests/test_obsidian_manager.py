from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "obsidian_manager.py"
SPEC = importlib.util.spec_from_file_location("obsidian_manager", MODULE_PATH)
assert SPEC and SPEC.loader
obsidian_manager = importlib.util.module_from_spec(SPEC)
sys.modules["obsidian_manager"] = obsidian_manager
SPEC.loader.exec_module(obsidian_manager)


class ObsidianManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vault = self.root / "vault"
        self.runtime = self.root / "runtime"
        (self.vault / "00 收件箱").mkdir(parents=True)
        (self.vault / "02 项目" / "Codex").mkdir(parents=True)
        (self.vault / "04 例行工作").mkdir(parents=True)
        (self.vault / "90 模板").mkdir(parents=True)

        (self.vault / "00 收件箱" / "临时想法.md").write_text("# 临时想法\n\n需要整理。\n", encoding="utf-8")
        (self.vault / "02 项目" / "Codex" / "00 Codex 总览.md").write_text(
            "# Codex 总览\n\n- [[01 已索引]]\n",
            encoding="utf-8",
        )
        (self.vault / "02 项目" / "Codex" / "01 已索引.md").write_text(
            "# 已索引\n\n链接到 [[不存在页面]] 和 [[00 收件箱]]。\n\n示例：`[[02 项目/某项目]]`\n",
            encoding="utf-8",
        )
        (self.vault / "02 项目" / "Codex" / "02 未索引.md").write_text("# 未索引\n\n内容足够但没有入口链接。\n", encoding="utf-8")
        (self.vault / "04 例行工作" / "短.md").write_text("# 短\n", encoding="utf-8")
        (self.vault / "90 模板" / "短模板.md").write_text("# 模板\n", encoding="utf-8")

        self.config = {
            "obsidian_vault": str(self.vault),
            "runtime_root": str(self.runtime),
            "obsidian_run_dir": str(self.vault / "04 例行工作" / "文件管理助手"),
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_classifies_obsidian_internal_findings(self) -> None:
        notes = obsidian_manager.build_notes(self.vault)
        summary = obsidian_manager.build_summary(self.config, notes, obsidian_manager.now_local(), self.runtime)

        self.assertEqual(summary["total_notes"], 6)
        self.assertGreaterEqual(summary["counts"]["inbox_triage"], 1)
        self.assertGreaterEqual(summary["counts"]["empty_or_stub"], 1)
        self.assertGreaterEqual(summary["counts"]["broken_links"], 1)
        self.assertGreaterEqual(summary["counts"]["folder_links"], 1)
        self.assertGreaterEqual(summary["counts"]["unindexed_codex"], 1)
        self.assertNotIn("02 项目/某项目", [item["link"] for item in summary["classifications"]["broken_links"]])

    def test_run_writes_reports_without_modifying_source_notes(self) -> None:
        source_note = self.vault / "00 收件箱" / "临时想法.md"
        before = source_note.read_text(encoding="utf-8")

        config_path = self.root / "config.json"
        config_path.write_text(__import__("json").dumps(self.config, ensure_ascii=False), encoding="utf-8")
        result = obsidian_manager.run(config_path, "Test")

        self.assertTrue(Path(result["summary_json"]).exists())
        self.assertTrue(Path(result["markdown_report"]).exists())
        self.assertTrue(Path(result["obsidian_note"]).exists())
        self.assertEqual(before, source_note.read_text(encoding="utf-8"))
        self.assertFalse(result["safety"]["source_notes_modified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
