import unittest

from bridge.classification import is_automation_evidence
from bridge.native import turn_evidence


def user_turn(text, *, content=False):
    item = {"type": "userMessage"}
    item.update({"content": [{"type": "inputText", "text": text}]} if content else {"text": text})
    return {"items": [item]}


class AutomationEvidenceTests(unittest.TestCase):
    def test_explicit_metadata_does_not_depend_on_title(self):
        self.assertTrue(is_automation_evidence({"source": "automation"}, []))
        self.assertTrue(is_automation_evidence({"source": "automations"}, []))
        self.assertTrue(is_automation_evidence({"automationId": "fixture-daily-run"}, []))
        self.assertFalse(is_automation_evidence({"title": "自动化日报", "automationId": ""}, []))

    def test_standard_visible_user_headers_raw_and_sanitized(self):
        samples = [
            "Automation: 每日整理\nAutomation ID: fixture-daily\nAutomation memory: memory.md\n\n检查新增资料。",
            "Automation ID: fixture-daily\n检查新增资料。",
            "Automation Title: 每日整理\n检查新增资料。",
            "自动化任务ID：fixture-daily\n检查新增资料。",
            "\ufeff\n自动化任务 ID: fixture-daily\n检查新增资料。",
        ]
        for text in samples:
            with self.subTest(text=text):
                raw = user_turn(text, content=True)
                self.assertTrue(is_automation_evidence({}, [raw]))
                self.assertTrue(is_automation_evidence({}, [turn_evidence(raw)]))

    def test_ordinary_daily_report_request_is_not_automation(self):
        self.assertFalse(is_automation_evidence(
            {"title": "每日工作总结"}, [user_turn("帮我整理昨天的日报，按项目分组。")]))
        self.assertFalse(is_automation_evidence(
            {"title": "设置自动化"}, [user_turn("请创建一个每天整理笔记的自动任务。")]))
        self.assertFalse(is_automation_evidence({}, [user_turn("Automation: 想讨论的功能")]))

    def test_quotes_code_and_later_body_headers_do_not_count(self):
        samples = [
            "请解释这个任务头：\nAutomation ID: fixture",
            "> Automation ID: fixture\n这是一段引用。",
            "```text\nAutomation ID: fixture\n```",
            "    Automation ID: fixture\n缩进代码示例。",
            "说明\n\nAutomation Title: 每日整理",
            "Automation: 文档\n普通说明正文。\nAutomation ID: 引用示例",
            "Automation: 文档\n\nAutomation ID: 引用示例",
            "Automation: 文档\n" + "Automation memory: entry\n" * 5 + "Automation ID: too-late",
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assertFalse(is_automation_evidence({}, [user_turn(text)]))

    def test_assistant_tool_and_reasoning_headers_are_never_identity(self):
        items = [{"type": kind, "text": "Automation ID: fixture", "output": "Automation ID: fixture"}
                 for kind in ("agentMessage", "reasoning", "commandExecution", "mcpToolCall")]
        self.assertFalse(is_automation_evidence({}, [{"items": items}]))


if __name__ == "__main__":
    unittest.main()
