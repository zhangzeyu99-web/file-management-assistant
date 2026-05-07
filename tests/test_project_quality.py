from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "project_quality.py"
SPEC = importlib.util.spec_from_file_location("project_quality", MODULE_PATH)
assert SPEC and SPEC.loader
project_quality = importlib.util.module_from_spec(SPEC)
sys.modules["project_quality"] = project_quality
SPEC.loader.exec_module(project_quality)


class ProjectQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(__file__).resolve().parents[1]

    def test_quality_gate_passes_for_current_repository(self) -> None:
        result = project_quality.run_checks(self.repo)

        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(len(result["checks"]), 8)

    def test_public_docs_do_not_promote_notification_bridge_as_core_feature(self) -> None:
        result = project_quality.run_checks(self.repo)
        bridge_check = next(item for item in result["checks"] if item["name"] == "optional_notification_positioning")

        self.assertTrue(bridge_check["ok"], bridge_check)
        self.assertNotIn("Feishu / Lark Delivery", bridge_check["evidence"])

    def test_past_design_ideas_are_captured_as_verifiable_principles(self) -> None:
        result = project_quality.run_checks(self.repo)
        principles = next(item for item in result["checks"] if item["name"] == "project_principles")
        expected = {
            "local-first",
            "report-only safety",
            "private local configuration",
            "knowledge action assistant",
            "four-layer architecture",
            "act workflow",
            "obsidian workflow",
            "scenario-based workflow",
            "closed loop",
            "lightweight daily triage",
            "life study work separation",
            "thin gui",
            "validation harness",
            "optional integrations",
        }

        self.assertTrue(principles["ok"], principles)
        self.assertTrue(expected.issubset(set(principles["evidence"])), principles)

    def test_public_text_has_no_common_mojibake(self) -> None:
        result = project_quality.run_checks(self.repo)
        mojibake = next(item for item in result["checks"] if item["name"] == "mojibake_scan")

        self.assertTrue(mojibake["ok"], mojibake)

    def test_guidebook_assets_are_published(self) -> None:
        result = project_quality.run_checks(self.repo)
        guidebook = next(item for item in result["checks"] if item["name"] == "guidebook_assets")

        self.assertTrue(guidebook["ok"], guidebook)
        self.assertEqual(7, guidebook["evidence"]["slide_count"])
        self.assertGreater(guidebook["evidence"]["pdf_size"], 100_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
