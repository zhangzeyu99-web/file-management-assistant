from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "config_loader.py"
SPEC = importlib.util.spec_from_file_location("config_loader", MODULE_PATH)
assert SPEC and SPEC.loader
config_loader = importlib.util.module_from_spec(SPEC)
sys.modules["config_loader"] = config_loader
SPEC.loader.exec_module(config_loader)


class ConfigLoaderTests(unittest.TestCase):
    def test_merges_local_override_and_expands_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.json"
            local = root / "config.local.json"
            os.environ["FILE_ASSISTANT_TEST_ROOT"] = str(root)
            config.write_text(
                json.dumps(
                    {
                        "runtime_root": "%FILE_ASSISTANT_TEST_ROOT%\\runtime",
                        "obsidian_folders": {"inbox": "00 收件箱", "daily": "01 今日日志"},
                        "watch_roots": [{"name": "Base", "path": "%FILE_ASSISTANT_TEST_ROOT%\\base"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            local.write_text(
                json.dumps(
                    {
                        "obsidian_folders": {"daily": "Daily"},
                        "watch_roots": [{"name": "Local", "path": "%FILE_ASSISTANT_TEST_ROOT%\\local"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            loaded = config_loader.load_config(config)

        self.assertTrue(str(loaded["runtime_root"]).endswith("\\runtime"))
        self.assertEqual("00 收件箱", loaded["obsidian_folders"]["inbox"])
        self.assertEqual("Daily", loaded["obsidian_folders"]["daily"])
        self.assertEqual("Local", loaded["watch_roots"][0]["name"])
        self.assertNotIn("%FILE_ASSISTANT_TEST_ROOT%", loaded["watch_roots"][0]["path"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
