"""Synthetic coverage tests for missed, retried and partially delivered weeks."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from engine.weekly import STATE_FILENAME, WeeklyArchiveError, advance_window, open_window


class WeeklyArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = "2026-10-01T00:00:00+08:00"
        self.friday = "2026-10-23T19:00:00+08:00"
        self.receipt = {"job_status": "completed", "quality_checked": True,
                        "local_readback": True, "online_synced": True}

    def accept(self, window, job_id="weekly-one", **kwargs):
        args = {"verified": True, "receipt": self.receipt,
                "accepted_at": "2026-11-20T20:00:00+08:00", **kwargs}
        return advance_window(self.root, window, job_id, **args)

    def test_first_window_does_not_claim_accepted_history(self):
        window = open_window(self.root, self.baseline, self.friday)
        self.assertEqual(window["since"], "2026-10-16T11:00:00+00:00")
        self.assertEqual(window["until"], "2026-10-23T11:00:00+00:00")
        self.assertTrue(window["first_run"])
        self.assertFalse(window["catch_up"])
        self.assertEqual(window["checkpoint_debt"], "retain")
        self.assertFalse((self.root / STATE_FILENAME).exists())
        recent = open_window(self.root, "2026-10-21T12:00:00+08:00", self.friday)
        self.assertEqual(recent["since"], "2026-10-21T04:00:00+00:00")

    def test_missed_weeks_start_at_last_accepted_endpoint(self):
        first = open_window(self.root, self.baseline, self.friday)
        self.accept(first)
        later = open_window(self.root, self.baseline, "2026-11-06T19:00:00+08:00")
        self.assertEqual(later["since"], first["until"])
        self.assertTrue(later["catch_up"])
        self.assertFalse(later["first_run"])
        self.accept(later, "weekly-two")
        stored = json.loads((self.root / STATE_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(stored["accepted_until"], later["until"])
        self.assertEqual(stored["last_success"]["job_id"], "weekly-two")

    def test_retry_keeps_original_until_and_does_not_mutate_journal(self):
        first = open_window(self.root, self.baseline, self.friday)
        retry = open_window(self.root, self.baseline, "2026-10-30T19:00:00+08:00", first)
        self.assertEqual(retry, first)
        retry["since"] = "not-a-time"
        self.assertNotEqual(retry, first)
        self.assertFalse((self.root / STATE_FILENAME).exists())

    def test_partial_or_unverified_delivery_cannot_advance(self):
        window = open_window(self.root, self.baseline, self.friday)
        bad_receipts = [None, {}, {**self.receipt, "job_status": "partial"}]
        for key in ("quality_checked", "local_readback", "online_synced"):
            bad_receipts.extend([{**self.receipt, key: False}, {**self.receipt, key: 1}])
        for receipt in bad_receipts:
            with self.subTest(receipt=receipt), self.assertRaises(WeeklyArchiveError):
                self.accept(window, receipt=receipt)
        with self.assertRaises(WeeklyArchiveError):
            self.accept(window, verified=False)
        self.assertFalse((self.root / STATE_FILENAME).exists())

    def test_failed_next_week_preserves_prior_success(self):
        first = open_window(self.root, self.baseline, self.friday)
        self.accept(first)
        before = (self.root / STATE_FILENAME).read_bytes()
        following = open_window(self.root, self.baseline, "2026-10-30T19:00:00+08:00")
        with self.assertRaises(WeeklyArchiveError):
            self.accept(following, "weekly-two", receipt={**self.receipt, "online_synced": False})
        self.assertEqual(before, (self.root / STATE_FILENAME).read_bytes())

    def test_duplicate_acceptance_is_idempotent_and_stale_jobs_cannot_regress(self):
        first = open_window(self.root, self.baseline, self.friday)
        original = self.accept(first)
        self.assertEqual(self.accept(first), original)
        following = open_window(self.root, self.baseline, "2026-10-30T19:00:00+08:00")
        self.accept(following, "weekly-two")
        before = (self.root / STATE_FILENAME).read_bytes()
        with self.assertRaises(WeeklyArchiveError):
            self.accept(first)
        self.assertEqual(before, (self.root / STATE_FILENAME).read_bytes())

    def test_skipping_a_week_or_overlapping_an_accepted_window_is_rejected(self):
        first = open_window(self.root, self.baseline, self.friday)
        self.accept(first)
        following = open_window(self.root, self.baseline, "2026-10-30T19:00:00+08:00")
        for since in ("2026-10-24T11:00:00+00:00", "2026-10-22T11:00:00+00:00"):
            altered = {**following, "since": since}
            altered["catch_up"] = since.startswith("2026-10-22")
            with self.subTest(since=since), self.assertRaises(WeeklyArchiveError):
                self.accept(altered, "weekly-two")

    def test_corrupt_or_missing_state_cannot_be_silently_reset(self):
        first = open_window(self.root, self.baseline, self.friday)
        with self.assertRaises(WeeklyArchiveError):
            self.accept({**first, "first_run": False})
        target = self.root / STATE_FILENAME
        for text in ("not-json", "[]", '{"version": 2}', '{"version": 1}',
                     '{"version": 1, "accepted_until": "2026-10-23T19:00:00+08:00"}'):
            target.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(WeeklyArchiveError):
                open_window(self.root, self.baseline, self.friday)
            self.assertEqual(target.read_text(encoding="utf-8"), text)

    def test_invalid_time_and_impossible_boundaries_do_not_open_window(self):
        for now in ("2026-10-23T19:00:00", "bad", None, datetime(2026, 10, 23)):
            with self.subTest(now=now), self.assertRaises(WeeklyArchiveError):
                open_window(self.root, self.baseline, now)
        with self.assertRaises(WeeklyArchiveError):
            open_window(self.root, "2026-10-24T00:00:00+08:00", self.friday)
        first = open_window(self.root, self.baseline, self.friday)
        with self.assertRaises(WeeklyArchiveError):
            self.accept(first, accepted_at="2026-10-23T18:00:00+08:00")
        self.accept(first)
        with self.assertRaises(WeeklyArchiveError):
            open_window(self.root, self.baseline, self.friday)

    def test_frozen_window_cannot_change_scope_or_lose_checkpoint_debt(self):
        window = open_window(self.root, self.baseline, self.friday)
        for changed in ({**window, "checkpoint_debt": "drop"},
                        {**window, "catch_up": True}, {**window, "timezone": "UTC"}):
            with self.subTest(changed=changed), self.assertRaises(WeeklyArchiveError):
                open_window(self.root, self.baseline, self.friday, changed)
        with self.assertRaises(WeeklyArchiveError):
            open_window(self.root, self.baseline, "2026-10-22T19:00:00+08:00", window)


if __name__ == "__main__":
    unittest.main()
