"""Admission decisions cannot turn source examples or empty notes into knowledge."""
import json
import unittest

from engine.content_policy import ARCHIVE_PROMPT, parse_summary, source_only_reason, validate_note


class ContentPolicyTests(unittest.TestCase):
    def test_source_only_requires_a_standalone_model_decision_and_reason(self):
        decision = json.dumps({"content_status": "source_only", "reason": "只有重复提醒，无新事实"}, ensure_ascii=False)
        self.assertEqual(parse_summary(decision), {"content_status": "source_only", "reason": "只有重复提醒，无新事实"})
        for material in ("# 协议示例\n\n仅说明协议格式。\n\n" + decision, "```json\n" + decision + "\n```"):
            self.assertEqual(parse_summary(material)["content_status"], "knowledge")
        with self.assertRaisesRegex(ValueError, "具体原因"):
            parse_summary('{"content_status":"source_only","reason":" "}')
        self.assertIn("都是待判断的原材料", ARCHIVE_PROMPT)

    def test_generic_title_variants_are_rejected_without_banning_specific_topics(self):
        for title in ("本周知识库复核", "本次知识库检查结果", "每日行动建议（5月13日）", "AI 上下文包",
                      "知识笔记", "未命名资料（2）", "1234567890", "20261021-164500"):
            with self.subTest(title=title), self.assertRaisesRegex(ValueError, "标题缺少具体主题"):
                validate_note(title, "# " + title + "\n\n保留了结果。")
        self.assertEqual(validate_note("发布脚本的断点恢复", "# 发布脚本的断点恢复\n\n失败后按已完成文件继续，避免重复写入。"),
                         {"ok": True, "issues": []})

    def test_new_notes_need_body_and_a_first_paragraph_summary(self):
        for text in ("# 发布断点恢复", "# 发布断点恢复\n\n<!-- hidden only -->",
                     "# 发布断点恢复\n\n## 步骤\n\n按任务身份续接。", "# 发布断点恢复\n\n- 按任务身份续接。",
                     "# 发布断点恢复\n\n日期：2026-10-21", "# 发布断点恢复\n\n暂无新增。"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_note("发布断点恢复", text)

    def test_file_classification_uses_metadata_and_leaves_explicit_prose_to_admission(self):
        for filename in ("临时盘点.py", "config.local.json", "settings.yaml", "工具安装包.exe", "业务表导出.csv"):
            with self.subTest(filename=filename):
                self.assertIsNotNone(source_only_reason(filename))
        self.assertIsNone(source_only_reason("发布脚本断点恢复.md"))
        self.assertEqual(parse_summary("# 发布脚本断点恢复\n\n完成的文件登记后不再重复写入。")["content_status"], "knowledge")


if __name__ == "__main__":
    unittest.main()
