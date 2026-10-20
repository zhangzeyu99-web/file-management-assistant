"""Persistent jobs with deduplicated update/export tasks and expiring ownership."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

TERMINAL = {"completed", "partial", "failed", "cancelled"}


class JobStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, input TEXT NOT NULL,
                status TEXT NOT NULL, stage TEXT NOT NULL, result TEXT, error TEXT,
                active_key TEXT UNIQUE, owner TEXT, lease_until INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
            """)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def unpack(row):
        if not row:
            return None
        item = dict(row)
        item["input"] = json.loads(item["input"])
        item["result"] = json.loads(item["result"]) if item["result"] else None
        return item

    def create(self, kind, payload, request_id=None):
        if kind not in {"update", "answer", "context", "ingest", "migration_export"}:
            raise ValueError("不支持的任务类型")
        now = int(time.time() * 1000)
        key = kind if kind in {"update", "migration_export"} else None
        job_id = request_id or str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM jobs WHERE id=? OR (active_key=? AND ? IS NOT NULL)", (job_id, key, key)).fetchone()
            if existing:
                return self.unpack(existing)
            conn.execute("INSERT INTO jobs(id,kind,input,status,stage,active_key,created_at,updated_at) VALUES(?,?,?,'queued','等待本机领取',?,?,?)",
                         (job_id, kind, json.dumps(payload, ensure_ascii=False), key, now, now))
            return self.unpack(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def get(self, job_id):
        with self.connection() as conn:
            return self.unpack(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def list(self):
        with self.connection() as conn:
            return [self.unpack(row) for row in conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 80")]

    def claim(self, owner):
        now = int(time.time() * 1000)
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT id FROM jobs WHERE status='queued' OR (status='running' AND lease_until<?) ORDER BY created_at LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            conn.execute("UPDATE jobs SET status='running',stage='本机已领取',owner=?,lease_until=?,updated_at=? WHERE id=?", (owner, now + 120000, now, row["id"]))
            return self.unpack(conn.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def update(self, job_id, owner, *, status="running", stage=None, result=None, error=None):
        now = int(time.time() * 1000)
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] != "running" or row["owner"] != owner or row["lease_until"] < now:
                raise RuntimeError("任务租约失效或已取消")
            conn.execute("UPDATE jobs SET status=?,stage=?,result=?,error=?,active_key=?,lease_until=?,updated_at=? WHERE id=?",
                         (status, stage or row["stage"], json.dumps(result, ensure_ascii=False) if result is not None else row["result"],
                          error, None if status in TERMINAL else row["active_key"], now + 120000, now, job_id))

    def cancel(self, job_id):
        with self.connection() as conn:
            conn.execute("UPDATE jobs SET status='cancelled',stage='已取消后续处理',active_key=NULL,owner=NULL,updated_at=? WHERE id=? AND status IN ('queued','running')",
                         (int(time.time() * 1000), job_id))
        return self.get(job_id)
