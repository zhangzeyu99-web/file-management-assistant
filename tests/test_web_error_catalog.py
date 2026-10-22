import json
from pathlib import Path
import unittest

from engine.user_errors import catalog


class WebErrorCatalogTest(unittest.TestCase):
    def test_published_web_uses_the_same_reviewed_recovery_instructions(self):
        path = Path(__file__).resolve().parents[1] / "web/lib/error-catalog.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), catalog(),
                         "Run scripts/sync_error_catalog.py after changing public errors")
