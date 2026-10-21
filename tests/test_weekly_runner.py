"""Weekly CLI uses mocked HTTP only and isolated private tracking files."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from engine.incremental import atomic_json
from engine.privacy import redact_text
from engine.weekly import open_window
from scripts.weekly_archive import LocalAPI, RunnerError, WeeklyRunner, latest_friday


class FakeAPI:
    def __init__(self):
        self.jobs = {}
        self.notes = {}
        self.calls = []
        self.health = {"weekly_archive": {"version": 1}}

    def __call__(self, path, payload=None):
        self.calls.append((path, copy.deepcopy(payload)))
        if path == "health":
            return copy.deepcopy(self.health)
        if path == "jobs":
            if payload is None:
                return {"items": copy.deepcopy(list(self.jobs.values()))}
            job = {"id": payload["request_id"], "kind": payload["kind"], "input": payload["input"], "status": "queued"}
            self.jobs[job["id"]] = job
            return copy.deepcopy(job)
        if path.startswith("notes/"):
            return copy.deepcopy(self.notes[path.split("/", 1)[1]])
        parts = path.split("/")
        job = self.jobs[parts[1]]
        if len(parts) == 3 and parts[2] == "retry":
            retried = {**copy.deepcopy(job), "id": job["id"] + "-retry", "status": "queued", "result": None}
            retried["input"]["retry_of"] = job["input"].get("retry_of") or job["id"]
            self.jobs[retried["id"]] = retried
            return copy.deepcopy(retried)
        return copy.deepcopy(job)


class FakeCloud:
    def __init__(self, synced_at):
        self.responses = {"health": {"synced_at": synced_at}}
        self.calls = []

    def request(self, path):
        self.calls.append(path)
        return copy.deepcopy(self.responses[path])


class WeeklyRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data, self.vault = self.root / "data", self.root / "vault"
        self.vault.mkdir()
        self.now = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
        self.until = "2026-10-23T11:00:00+00:00"
        self.api, self.cloud = FakeAPI(), FakeCloud(self.now.isoformat())
        self.runner = WeeklyRunner({"data_root": str(self.data), "obsidian_vault": str(self.vault)},
                                   request=self.api, cloud=self.cloud, now=self.now)

    def track(self, job, pending=()):
        self.api.jobs[job["id"]] = copy.deepcopy(job)
        atomic_json(self.runner.active_path, {"version": 1, "outstanding_job_id": job["id"],
                                             "pending_job_ids": list(pending), "previous_job_ids": []})

    def test_queue_refuses_a_different_workspace_on_the_same_port(self):
        self.runner.config_path = str(self.root / "requested.local.json")
        with self.assertRaisesRegex(RunnerError, "其他配置"):
            self.runner.queue()
        self.assertFalse(self.api.jobs)

    def job(self, status="queued", until=None, job_id="weekly-current"):
        return {"id": job_id, "kind": "update", "input": {"weekly_archive": True, "until": until or self.until},
                "status": status}

    def completed(self, pending=()):
        path = self.vault / "具名成果.md"
        markdown = "# 项目统计口径\n\n确认保留实际结果。\naccess_token = test-private-value\n"
        path.write_text(markdown, encoding="utf-8")
        card = {"id": "n_fixture", "path": str(path)}
        self.api.notes[card["id"]] = {**card, "markdown": markdown}
        self.cloud.responses["notes/" + card["id"]] = {"id": card["id"], "markdown": redact_text(markdown)}
        job = self.job("completed")
        job["result"] = {"partial": False, "errors": [], "synced": True, "checkpoint_debt": [], "notes": [card],
                         "archive_window": open_window(self.data, "2026-10-01T00:00:00+00:00", self.until)}
        self.track(job, pending)
        review = {"quality_checked": True, "topics": ["项目统计口径"], "note_ids": [card["id"]],
                  "assessment": "已核对来源、结论和重复内容。"}
        if pending:
            review.update(pending_debt_checked=True, pending_job_ids=list(pending))
        return job, review

    def test_queue_reuses_active_weekly_and_leaves_nonweekly_busy(self):
        job = self.job("running")
        self.api.jobs[job["id"]] = job
        self.api.health.update(worker_running=False, online=False)
        queued = self.runner.queue()
        self.assertEqual((queued["action"], queued["job"]["id"]), ("reused", job["id"]))
        self.assertEqual(queued["execution"], "waiting")
        self.api.jobs["manual"] = {"id": "manual", "kind": "update", "input": {}, "status": "running"}
        self.assertEqual(self.runner.queue()["action"], "busy")
        self.assertFalse(any(payload is not None for _, payload in self.api.calls))
        self.assertEqual(json.loads(self.runner.active_path.read_text(encoding="utf-8"))["outstanding_job_id"], job["id"])

    def test_same_window_retries_partial_and_keeps_cancelled_blocked(self):
        job = self.job("partial")
        self.track(job)
        retried = self.runner.queue()
        self.assertEqual(retried["action"], "retried")
        active = json.loads(self.runner.active_path.read_text(encoding="utf-8"))
        self.assertEqual(active["outstanding_job_id"], job["id"] + "-retry")
        self.assertEqual(active["previous_job_ids"], [job["id"]])
        self.api.jobs[active["outstanding_job_id"]]["status"] = "cancelled"
        posts = sum(payload is not None for _, payload in self.api.calls)
        self.assertEqual(self.runner.queue()["action"], "blocked")
        self.assertEqual(sum(payload is not None for _, payload in self.api.calls), posts)

    def test_later_week_preserves_partial_id_and_queues_stable_new_request(self):
        job = self.job("partial", "2026-10-16T11:00:00+00:00", "weekly-old")
        self.track(job)
        queued = self.runner.queue()
        self.assertEqual(queued["job"]["id"], "weekly-20261023")
        self.assertEqual(queued["job"]["input"]["until"], self.until)
        active = json.loads(self.runner.active_path.read_text(encoding="utf-8"))
        self.assertEqual(active["pending_job_ids"], [job["id"]])
        self.assertEqual(active["previous_job_ids"], [job["id"]])
        self.assertEqual(self.runner.queue()["action"], "reused")
        self.assertEqual(sum(path == "jobs" and payload is not None for path, payload in self.api.calls), 1)

    def test_accept_rejects_partial_unsynced_and_empty_note_without_advancing(self):
        for problem in ("partial", "unsynced", "empty"):
            with self.subTest(problem=problem):
                job, review = self.completed()
                if problem == "partial":
                    self.api.jobs[job["id"]]["status"] = "partial"
                elif problem == "unsynced":
                    self.api.jobs[job["id"]]["result"]["synced"] = False
                else:
                    self.api.notes["n_fixture"]["markdown"] = " \n"
                with self.assertRaises(RunnerError):
                    self.runner.accept(job["id"], review)
                self.assertFalse((self.data / "weekly-archive.json").exists())
                self.assertEqual(self.runner.status()["job"]["id"], job["id"])

    def test_accept_reads_real_remote_redacted_note_and_requires_old_debt_review(self):
        job, review = self.completed(["weekly-old"])
        bad_review = {key: value for key, value in review.items() if key != "pending_debt_checked"}
        with self.assertRaises(RunnerError):
            self.runner.accept(job["id"], bad_review)
        self.cloud.responses["notes/n_fixture"]["markdown"] = "过期远端正文"
        with self.assertRaises(RunnerError):
            self.runner.accept(job["id"], review)
        self.assertFalse((self.data / "weekly-archive.json").exists())
        self.cloud.responses["notes/n_fixture"]["markdown"] = redact_text(self.api.notes["n_fixture"]["markdown"])
        accepted = self.runner.accept(job["id"], review)
        self.assertEqual(accepted["action"], "accepted")
        self.assertNotIn("markdown", json.dumps(accepted))
        self.assertNotIn("test-private-value", json.dumps(accepted))
        state = json.loads((self.data / "weekly-archive.json").read_text(encoding="utf-8"))
        self.assertTrue(state["last_success"]["receipt"]["online_readback"])
        self.assertEqual(state["last_success"]["receipt"]["pending_job_ids"], ["weekly-old"])
        self.assertIsNone(self.runner.status()["active"]["outstanding_job_id"])
        self.assertEqual(self.runner.queue()["action"], "already_accepted")

    def test_accept_rejects_note_path_outside_configured_vault(self):
        job, review = self.completed()
        outside = self.root / "outside.md"
        outside.write_text(self.api.notes["n_fixture"]["markdown"], encoding="utf-8")
        self.api.notes["n_fixture"]["path"] = str(outside)
        self.api.jobs[job["id"]]["result"]["notes"][0]["path"] = str(outside)
        with self.assertRaises(RunnerError):
            self.runner.accept(job["id"], review)
        self.assertEqual(self.cloud.calls, [])

    def test_accept_resolves_reviewed_alias_to_canonical_local_and_remote_note(self):
        job, review = self.completed()
        original = Path(self.api.notes["n_fixture"]["path"])
        canonical = self.vault / "合并后的主题.md"
        canonical.write_text(self.api.notes["n_fixture"]["markdown"], encoding="utf-8")
        original.unlink()
        self.api.notes["n_fixture"].update(id="n_canonical", selected_source_id="n_fixture", path=str(canonical))
        self.cloud.responses["notes/n_fixture"]["id"] = "n_canonical"
        self.assertEqual(self.runner.accept(job["id"], review)["action"], "accepted")
        receipt = json.loads((self.data / "weekly-archive.json").read_text(encoding="utf-8"))["last_success"]["receipt"]
        self.assertEqual(receipt["notes"], [{"id": "n_fixture", "resolved_id": "n_canonical", "path": str(canonical.resolve())}])

    def test_no_note_acceptance_still_requires_remote_snapshot_readback(self):
        job, review = self.completed()
        self.api.jobs[job["id"]]["result"]["notes"] = []
        review.update(note_ids=[], topics=[])
        self.cloud.responses["health"]["synced_at"] = None
        with self.assertRaises(RunnerError):
            self.runner.accept(job["id"], review)
        self.cloud.responses["health"]["synced_at"] = self.now.isoformat()
        self.assertEqual(self.runner.accept(job["id"], review)["note_ids"], [])
        self.assertEqual(self.cloud.calls, ["health", "health"])

    def test_anchor_and_local_api_only(self):
        before = datetime(2026, 10, 23, 10, 59, tzinfo=timezone.utc)
        self.assertEqual(latest_friday(before).isoformat(), "2026-10-16T11:00:00+00:00")
        self.assertEqual(latest_friday(self.now).isoformat(), self.until)
        for endpoint in ("http://outside.example:8767", "https://localhost:8767", "http://localhost:8767/other"):
            with self.subTest(endpoint=endpoint), self.assertRaises(RunnerError):
                LocalAPI(endpoint)
        self.assertEqual(LocalAPI("8767").base, "http://127.0.0.1:8767/api/workspace/")
        with self.assertRaises(RunnerError):
            self.runner.queue("2026-10-24T11:00:00+00:00")
        self.assertEqual(self.api.calls, [])


if __name__ == "__main__":
    unittest.main()
