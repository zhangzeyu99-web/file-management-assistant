import json
import tempfile
import unittest
from pathlib import Path

from engine.library import Library
from engine.navigation import sync_navigation


class NavigationTests(unittest.TestCase):
    def test_new_note_appears_without_rewriting_user_additions_or_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".obsidian").mkdir()
            (root / ".obsidian/knowledge-layout.json").write_text(
                json.dumps({"version": 1, "navigation": True}), encoding="utf-8")
            project = root / "10 项目/洛克计算器/发布状态.md"
            project.parent.mkdir(parents=True)
            project.write_text("---\ndate: 2026-09-30\n---\n# 发布状态\n\n桌面包已经交付，小程序仍待提审。\n", encoding="utf-8")
            overview = project.parent / "洛克计算器.md"
            overview.write_text("---\ntype: navigation\n---\n# 洛克计算器\n\n各端发布与计算口径。\n", encoding="utf-8")
            old = root / "90 历史/旧发布记录.md"
            old.parent.mkdir()
            old.write_text("# 旧发布记录\n\n很早以前的计划。\n", encoding="utf-8")
            template = root / "40 日常/模板/项目笔记模板.md"
            template.parent.mkdir(parents=True)
            template.write_text("# {{title}}\n\n填写项目结论。\n", encoding="utf-8")
            library = Library(root)
            library.refresh()
            self.assertEqual(len(sync_navigation(library)), 3)
            recent = root / "00 入口/知识库最近更新.md"
            self.assertIn("发布状态", recent.read_text(encoding="utf-8"))
            self.assertNotIn("旧发布记录", recent.read_text(encoding="utf-8"))
            self.assertIn("### 2026-09-30", recent.read_text(encoding="utf-8"))
            self.assertIn("## 项目记录", recent.read_text(encoding="utf-8"))
            self.assertNotIn("[[10 项目/洛克计算器/洛克计算器|", recent.read_text(encoding="utf-8"))
            themes = (root / "00 入口/知识库主题目录.md").read_text(encoding="utf-8")
            self.assertIn("### [[10 项目/洛克计算器/洛克计算器|洛克计算器]]", themes)
            self.assertNotIn("- [[10 项目/洛克计算器/洛克计算器|", themes)
            self.assertNotIn("{{title}}", themes)
            self.assertTrue(template.is_file())
            home = root / "00 入口/知识库首页.md"
            with home.open("a", encoding="utf-8") as stream:
                stream.write("\n我的补充。\n")
            library.refresh()
            self.assertEqual(sync_navigation(library), [])
            self.assertTrue(home.read_text(encoding="utf-8").endswith("我的补充。\n"))
            added = root / "30 资料/本地化/术语修订.md"
            added.parent.mkdir(parents=True)
            added.write_text("# 术语修订\n\n同名问题已经逐条修复。\n", encoding="utf-8")
            library.refresh()
            sync_navigation(library)
            self.assertIn("术语修订", recent.read_text(encoding="utf-8"))

    def test_existing_unowned_entry_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".obsidian").mkdir()
            (root / ".obsidian/knowledge-layout.json").write_text(
                '{"version":1,"navigation":true}', encoding="utf-8")
            home = root / "00 入口/知识库首页.md"
            home.parent.mkdir()
            home.write_text("我的手写主页。", encoding="utf-8")
            library = Library(root)
            library.refresh()
            sync_navigation(library)
            self.assertEqual(home.read_text(encoding="utf-8"), "我的手写主页。")


if __name__ == "__main__":
    unittest.main()
