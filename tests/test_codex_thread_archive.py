from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path

from scripts.archive_recent_codex_threads import create_archive


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


class CodexThreadArchiveTests(unittest.TestCase):
    def test_archive_recent_codex_threads_writes_readable_markdown_and_manifest(self) -> None:
        tmp_path = Path.cwd() / ".tmp-tests" / "codex-thread-archive" / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        codex_home = tmp_path / "codex-home"
        output_dir = tmp_path / "archive-output"
        obsidian_note = (
            tmp_path
            / "vault"
            / "\u02d9\u02d9-codex"
            / "16 Codex archive 2026-05-26 to 2026-06-02.md"
        )
        title = "\u8fd0\u8425SOP\u4e3b\u5e93"
        old_title = "\u65e7\u7ebf\u7a0b"
        first_user = "\u6211\u662f\u8981\u4f60\u5e2e\u6211\u6062\u590d\u8fd9\u4e2acodex\u7ebf\u7a0b\uff0c\u8fd0\u8425SOP\u4e3b\u5e93"

        write_jsonl(
            codex_home / "session_index.jsonl",
            [
                {
                    "id": "thread-old",
                    "thread_name": old_title,
                    "updated_at": "2026-05-20T08:00:00Z",
                },
                {
                    "id": "thread-sop",
                    "thread_name": title,
                    "updated_at": "2026-06-02T08:23:31Z",
                },
                {
                    "id": "thread-daily",
                    "thread_name": "Codex Daily Review",
                    "updated_at": "2026-05-27T01:00:00Z",
                },
            ],
        )
        write_jsonl(
            codex_home / "sessions" / "2026" / "06" / "02" / "rollout-thread-sop.jsonl",
            [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "thread-sop",
                        "timestamp": "2026-06-02T08:20:00Z",
                        "cwd": "D:\\codex",
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": first_user,
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "found"}],
                    },
                },
            ],
        )
        write_jsonl(
            codex_home / "archived_sessions" / "rollout-thread-daily.jsonl",
            [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "thread-daily",
                        "timestamp": "2026-05-27T01:00:00Z",
                        "cwd": "D:\\codex\\codex",
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "Automation: Codex Daily Review",
                    },
                },
            ],
        )

        result = create_archive(
            codex_home=codex_home,
            since="2026-05-26",
            until="2026-06-02",
            output_dir=output_dir,
            obsidian_note=obsidian_note,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(2, result["item_count"])
        self.assertEqual(str(output_dir / "codex-thread-delta-archive.md"), result["markdown_path"])
        self.assertEqual(str(output_dir / "codex-thread-delta-manifest.json"), result["manifest_path"])
        self.assertEqual(str(obsidian_note), result["obsidian_note"])

        markdown = (output_dir / "codex-thread-delta-archive.md").read_text(encoding="utf-8")
        self.assertIn("# Codex \u65b0\u589e\u7ebf\u7a0b\u5f52\u6863\uff1a2026-05-26 \u81f3 2026-06-02", markdown)
        self.assertIn(title, markdown)
        self.assertIn("thread-sop", markdown)
        self.assertIn(first_user, markdown)
        self.assertIn("Codex Daily Review", markdown)
        self.assertNotIn(old_title, markdown)

        manifest = json.loads((output_dir / "codex-thread-delta-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(["thread-sop", "thread-daily"], [item["id"] for item in manifest["items"]])
        self.assertEqual(1, manifest["counts_by_topic"]["\u6e38\u620f\u8fd0\u8425/\u4e1a\u52a1 SOP"])
        self.assertEqual(1, manifest["counts_by_topic"]["\u81ea\u52a8\u4efb\u52a1"])
        self.assertEqual(markdown, obsidian_note.read_text(encoding="utf-8"))
