"""Native paging failures must not lose valid work or acknowledge partial turns."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from bridge import BridgeError
from engine.runtime import Runtime


def turn(identity, started, completed, *, truncated=False):
    return {"id": identity, "status": "completed", "startedAt": started, "completedAt": completed,
            "items": [{"type": "agentMessage", "text": {"text": "完成结果", "truncated": truncated}}]}


def page(turns, cursor=None, order="newest_first"):
    return {"thread": {"id": "thread"}, "turns": turns,
            "page": {"order": order, "hasMore": bool(cursor), "nextCursor": cursor}}


class RuntimeNativeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = Runtime.__new__(Runtime)
        self.runtime.progress = Mock()
        self.state = {"threads": {"thread": {"through": 100, "turns": {}}}}
        self.meta = {"id": "thread", "updatedAt": 300, "hostId": "host"}

    def test_flat_list_keeps_latest_metadata_and_marks_unavailable_sources(self):
        native = Mock()
        native.list_threads.return_value = {
            "pinnedThreads": [{"id": "same", "hostId": "host", "updatedAt": 300, "kind": "codex"}],
            "threads": [{"id": "chat", "kind": "chatgpt", "updatedAt": 400}],
            "unavailableHosts": ["offline"], "unavailableSources": ["remote"],
        }
        native.list_archived_threads.return_value = {
            "threads": [{"id": "same", "hostId": "host", "updatedAt": 100, "kind": "codex"}],
            "nextCursor": None,
        }
        rows, warnings = self.runtime._list_threads(native)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["updatedAt"], 300)
        self.assertEqual(len(warnings), 2)

    def test_archive_paging_failure_retains_recent_and_earlier_archive_rows(self):
        native = Mock()
        native.list_threads.return_value = {"pinnedThreads": [], "threads": [{"id": "recent", "updatedAt": 200}]}
        native.list_archived_threads.side_effect = [
            {"threads": [{"id": "archived", "updatedAt": 100}], "nextCursor": "a"},
            BridgeError("native_timeout", "读取超时"),
        ]
        rows, warnings = self.runtime._list_threads(native)
        self.assertEqual({row["id"] for row in rows}, {"recent", "archived"})
        self.assertTrue(warnings)

    def test_truncated_completed_turn_is_pending_and_never_selected(self):
        native = Mock()
        native.read_thread.return_value = page([turn("bad", 200, 220, truncated=True), turn("good", 120, 130)])
        result = self.runtime._read_new_turns(native, self.meta, self.state)
        self.assertEqual([row["id"] for row in result["turns"]], ["good"])
        self.assertEqual([row["id"] for row in result["pending"]], ["bad"])
        self.assertFalse(result["complete"])

    def test_second_page_error_keeps_completed_first_page_for_individual_ack(self):
        native = Mock()
        native.read_thread.side_effect = [
            page([turn("good", 120, 130)], "next"),
            BridgeError("native_oversized", "超过限制"),
        ]
        result = self.runtime._read_new_turns(native, self.meta, self.state)
        self.assertEqual([row["id"] for row in result["turns"]], ["good"])
        self.assertFalse(result["complete"])
        self.assertTrue(result["errors"])
        self.assertEqual(result["cursor"], "next")

    def test_missing_cursor_with_more_pages_never_marks_complete(self):
        native = Mock()
        data = page([turn("good", 120, 130)])
        data["page"]["hasMore"] = True
        native.read_thread.return_value = data
        result = self.runtime._read_new_turns(native, self.meta, self.state)
        self.assertFalse(result["complete"])
        self.assertTrue(result["errors"])

    def test_early_stop_requires_declared_newest_first_order(self):
        native = Mock()
        native.read_thread.side_effect = [
            page([turn("old", 10, 20)], "next", order="oldest_first"),
            page([turn("new", 120, 130)], order="oldest_first"),
        ]
        result = self.runtime._read_new_turns(native, self.meta, self.state)
        self.assertEqual([row["id"] for row in result["turns"]], ["new"])
        self.assertTrue(result["complete"])
        self.assertEqual(native.read_thread.call_count, 2)

    def test_old_boundary_truncation_does_not_block_new_complete_material(self):
        native = Mock()
        native.read_thread.return_value = page([
            turn("late-completed", 90, 120),
            turn("old", 10, 20, truncated=True),
        ], "older-history")
        result = self.runtime._read_new_turns(native, self.meta, self.state)
        self.assertEqual([row["id"] for row in result["turns"]], ["late-completed"])
        self.assertTrue(result["complete"])
        self.assertEqual(native.read_thread.call_count, 1)


if __name__ == "__main__":
    unittest.main()
