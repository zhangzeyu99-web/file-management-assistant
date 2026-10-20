import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from engine.jobs import JobStore


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = JobStore(Path(self.temp.name) / "jobs.sqlite")

    def test_double_update_clicks_share_one_job_and_finish_releases_slot(self):
        for kind in ("update", "migration_export"):
            with self.subTest(kind=kind):
                with ThreadPoolExecutor(max_workers=4) as pool:
                    jobs = list(pool.map(lambda _: self.store.create(kind, {}), range(4)))
                self.assertEqual(len({j["id"] for j in jobs}), 1)
                current = self.store.claim("owner")
                self.store.update(current["id"], "owner", status="completed", result={"notes": []})
                following = self.store.create(kind, {})
                self.assertNotEqual(following["id"], current["id"])
                self.store.cancel(following["id"])

    def test_cancel_or_lost_lease_cannot_overwrite_result(self):
        job = self.store.create("context", {"ids": ["a", "b"]})
        self.store.claim("old")
        self.store.cancel(job["id"])
        with self.assertRaises(RuntimeError):
            self.store.update(job["id"], "old", status="completed")
        self.assertEqual(self.store.get(job["id"])["status"], "cancelled")
        other = self.store.create("update", {})
        self.store.claim("old")
        with self.store.connection() as conn:
            conn.execute("UPDATE jobs SET lease_until=1 WHERE id=?", (other["id"],))
        self.store.claim("new")
        with self.assertRaises(RuntimeError):
            self.store.update(other["id"], "old", status="completed")
        self.store.update(other["id"], "new", status="completed")

    def test_upload_request_id_is_durable_across_restart(self):
        a = self.store.create("ingest", {"filename": "a.txt"}, "upload-test")
        restarted = JobStore(self.store.path)
        b = restarted.create("ingest", {"filename": "a.txt"}, "upload-test")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(len(restarted.list()), 1)


if __name__ == "__main__":
    unittest.main()
