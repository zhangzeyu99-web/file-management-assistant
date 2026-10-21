"""Queue, inspect and verify weekly archives through the existing local API."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.incremental import atomic_json, stamp, writer_lock
from engine.cloud import Cloud
from engine.privacy import redact_text
from engine.settings import load_settings
from engine.weekly import advance_window


CHINA = timezone(timedelta(hours=8))


class RunnerError(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RunnerError("本机 API 不应重定向；未跟随其他地址。")


class LocalAPI:
    def __init__(self, endpoint):
        value = str(endpoint)
        if value.isdigit():
            value = "http://127.0.0.1:" + value
        parsed = urlsplit(value)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path.rstrip("/") not in {"", "/api/workspace"}):
            raise RunnerError("--api 只允许本机 http://127.0.0.1:端口 或 http://localhost:端口。")
        if not parsed.port or not 1 <= parsed.port <= 65535:
            raise RunnerError("本机 API 需要有效端口。")
        self.base = f"{parsed.scheme}://{parsed.netloc}/api/workspace/"
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())

    def __call__(self, path, payload=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(self.base + path, data=body, headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=30) as response:
                result = json.load(response)
        except HTTPError as error:
            raise RunnerError(f"本机 API 返回 HTTP {error.code}，未登记完成。") from None
        except URLError as error:
            raise RunnerError(f"本机 API 无法连接：{error.reason}") from None
        if not isinstance(result, dict):
            raise RunnerError("本机 API 返回格式无效。")
        return result


def latest_friday(now):
    local = now.astimezone(CHINA)
    anchor = local.replace(hour=19, minute=0, second=0, microsecond=0)
    anchor -= timedelta(days=(local.weekday() - 4) % 7)
    if anchor > local:
        anchor -= timedelta(days=7)
    return anchor.astimezone(timezone.utc)


def _weekly(job):
    return (job.get("kind") == "update" and isinstance(job.get("input"), dict)
            and job["input"].get("weekly_archive") is True)


def _ids(value):
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value) and len(set(value)) == len(value)


class WeeklyRunner:
    def __init__(self, config, *, api=None, request=None, cloud=None, now=None):
        if not isinstance(config, dict) or not all(isinstance(config.get(key), str) and config[key]
                                                 for key in ("data_root", "obsidian_vault")):
            raise RunnerError("配置必须包含 data_root 和 obsidian_vault。")
        self.data = Path(config["data_root"]).resolve()
        self.vault = Path(config["obsidian_vault"]).resolve()
        self.active_path = self.data / "weekly-active.json"
        self.config_path = config.get("_config_path")
        self.request = request or LocalAPI(api or f"http://127.0.0.1:{config.get('port', 8767)}")
        self.cloud = cloud or Cloud(config.get("cloud_url", ""), self.data / "service-token.dpapi")
        self.now = now or datetime.now(timezone.utc)
        if not isinstance(self.now, datetime) or self.now.tzinfo is None:
            raise RunnerError("当前时间必须包含时区。")

    def _active(self):
        if not self.active_path.exists():
            return {"version": 1, "pending_job_ids": [], "previous_job_ids": []}
        value = json.loads(self.active_path.read_text(encoding="utf-8-sig"))
        if (not isinstance(value, dict) or value.get("version") != 1
                or not _ids(value.get("pending_job_ids", [])) or not _ids(value.get("previous_job_ids", []))
                or value.get("outstanding_job_id") is not None and not (
                    isinstance(value["outstanding_job_id"], str) and value["outstanding_job_id"])):
            raise RunnerError("周任务跟踪记录异常，未覆盖已有记录。")
        value.setdefault("pending_job_ids", [])
        value.setdefault("previous_job_ids", [])
        return value

    def _save(self, active):
        active["updated_at"] = self.now.isoformat()
        atomic_json(self.active_path, active)

    def _job(self, job_id):
        job = self.request("jobs/" + quote(job_id, safe=""))
        if not isinstance(job, dict) or job.get("id") != job_id or job.get("stale"):
            raise RunnerError("未取得该任务的当前状态，保留待处理记录。")
        return job

    def _remember(self, active, job):
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id or not _weekly(job):
            raise RunnerError("API 未返回有效周归档任务。")
        previous = active.get("outstanding_job_id")
        if previous and previous != job_id and previous not in active["previous_job_ids"]:
            active["previous_job_ids"].append(previous)
        active.update(outstanding_job_id=job_id, until=job["input"].get("until"))
        self._save(active)

    def queue(self, until=None):
        endpoint = stamp(until) if until is not None else latest_friday(self.now).timestamp()
        if not 0 < endpoint <= self.now.timestamp():
            raise RunnerError("--until 必须是有效时间，且不晚于当前。")
        until_iso = datetime.fromtimestamp(endpoint, timezone.utc).isoformat()
        with writer_lock(self.active_path.with_suffix(".lock")):
            active = self._active()
            health = self.request("health")
            if self.config_path and (not isinstance(health.get("config_path"), str)
                                     or Path(health["config_path"]).resolve() != Path(self.config_path).resolve()):
                raise RunnerError("本机端口使用其他配置，未创建周归档任务。")
            if not isinstance(health.get("weekly_archive"), dict) or health["weekly_archive"].get("version") != 1:
                raise RunnerError("当前执行器尚不支持周归档窗口，未创建任务。")
            execution = "waiting" if health.get("worker_running") is False or health.get("online") is False else "available"
            listing = self.request("jobs")
            if not isinstance(listing.get("items"), list) or any(not isinstance(job, dict) for job in listing["items"]):
                raise RunnerError("任务列表格式无效，未创建任务。")
            outstanding = self._job(active["outstanding_job_id"]) if active.get("outstanding_job_id") else None
            if outstanding and not _weekly(outstanding):
                raise RunnerError("跟踪记录指向非周任务，未自动替换。")
            if outstanding and outstanding.get("status") in {"completed", "cancelled"}:
                action = "awaiting_acceptance" if outstanding["status"] == "completed" else "blocked"
                return {"ok": True, "action": action, "job": outstanding, "active": active}
            running = [job for job in listing["items"]
                       if job.get("kind") == "update" and job.get("status") in {"queued", "running"}]
            if any(not _weekly(job) for job in running) or len(running) > 1:
                return {"ok": True, "action": "busy", "jobs": running, "active": active}
            if running:
                job = self._job(running[0]["id"])
                if outstanding and job["id"] != outstanding["id"]:
                    if outstanding.get("status") not in {"partial", "failed"}:
                        return {"ok": True, "action": "busy", "jobs": running, "active": active}
                    if stamp(job["input"].get("until")) > stamp(outstanding["input"].get("until")):
                        active["pending_job_ids"] = list(dict.fromkeys([*active["pending_job_ids"], outstanding["id"]]))
                self._remember(active, job)
                return {"ok": True, "action": "reused", "execution": execution, "job": job, "active": active}
            if outstanding:
                if outstanding.get("status") in {"queued", "running"}:
                    return {"ok": True, "action": "reused", "execution": execution, "job": outstanding, "active": active}
                if outstanding.get("status") not in {"failed", "partial"}:
                    raise RunnerError("周任务状态未知，保留待处理记录。")
                if endpoint <= stamp(outstanding["input"].get("until")):
                    job = self.request("jobs/" + quote(outstanding["id"], safe="") + "/retry", {})
                    self._remember(active, job)
                    return {"ok": True, "action": "retried", "execution": execution, "job": job, "active": active}
                active["pending_job_ids"] = list(dict.fromkeys([*active["pending_job_ids"], outstanding["id"]]))
                self._save(active)
            elif endpoint <= stamp(active.get("last_accepted_until")):
                return {"ok": True, "action": "already_accepted", "active": active}
            date = datetime.fromtimestamp(endpoint, CHINA).strftime("%Y%m%d")
            job = self.request("jobs", {"kind": "update", "input": {"weekly_archive": True, "until": until_iso},
                                        "request_id": "weekly-" + date})
            if not _weekly(job):
                return {"ok": True, "action": "busy", "job": job, "active": active}
            self._remember(active, job)
            return {"ok": True, "action": "queued", "execution": execution, "job": job, "active": active}

    def status(self, job_id=None):
        active = self._active()
        selected = job_id or active.get("outstanding_job_id")
        return {"ok": True, "job": self._job(selected) if selected else None, "active": active}

    def accept(self, job_id, review):
        with writer_lock(self.active_path.with_suffix(".lock")):
            active = self._active()
            if active.get("outstanding_job_id") != job_id:
                raise RunnerError("只能验收当前跟踪的待验收周任务。")
            job = self._job(job_id)
            result = job.get("result")
            if (not _weekly(job) or job.get("status") != "completed" or not isinstance(result, dict)
                    or result.get("partial") or result.get("errors") or result.get("checkpoint_debt")
                    or result.get("synced") is not True):
                raise RunnerError("实际任务须 completed、无未完成来源且已同步线上，才能验收。")
            notes = result.get("notes")
            if not isinstance(notes, list) or any(not isinstance(note, dict) for note in notes):
                raise RunnerError("任务笔记列表无效。")
            note_ids = [note.get("id") for note in notes]
            if not _ids(note_ids):
                raise RunnerError("任务笔记标识无效或重复。")
            if (not isinstance(review, dict) or review.get("quality_checked") is not True
                    or not isinstance(review.get("topics"), list) or not _ids(review.get("note_ids"))
                    or set(review["note_ids"]) != set(note_ids)
                    or not isinstance(review.get("assessment"), str) or not review["assessment"].strip()):
                raise RunnerError("复核文件须包含真实质量结论、topics、完整 note_ids 和非空 assessment。")
            pending = active["pending_job_ids"]
            if pending and (review.get("pending_debt_checked") is not True
                            or not _ids(review.get("pending_job_ids")) or set(review["pending_job_ids"]) != set(pending)):
                raise RunnerError("复核文件须逐项覆盖 pending_job_ids，并确认 pending_debt_checked。")
            readbacks, expected_notes = [], []
            for note in notes:
                actual = self.request("notes/" + quote(note["id"], safe=""))
                markdown = actual.get("markdown")
                resolved_id = actual.get("id")
                alias = resolved_id != note["id"]
                if (not isinstance(resolved_id, str) or not resolved_id
                        or alias and actual.get("selected_source_id") != note["id"]
                        or not isinstance(markdown, str) or not markdown.strip()):
                    raise RunnerError("笔记正文为空或标识不一致，未验收。")
                actual_path = actual.get("path")
                if not isinstance(actual_path, str) or not Path(actual_path).is_absolute():
                    raise RunnerError("笔记缺少本机绝对路径。")
                local = Path(actual_path).resolve(strict=True)
                if not local.is_relative_to(self.vault) or local.suffix.lower() != ".md":
                    raise RunnerError("笔记路径须位于配置知识库内。")
                if not alias:
                    card_path = note.get("path")
                    if (not isinstance(card_path, str) or not Path(card_path).is_absolute()
                            or Path(card_path).resolve(strict=True) != local):
                        raise RunnerError("任务与 API 笔记路径不一致，未验收。")
                if not local.is_file() or local.read_text(encoding="utf-8-sig") != markdown:
                    raise RunnerError("本机笔记与 API 正文读回不一致，未验收。")
                readbacks.append({"id": note["id"], "resolved_id": resolved_id, "path": str(local)})
                expected_notes.append((note["id"], resolved_id, redact_text(markdown)))
            try:
                online = self.cloud.request("health")
                if not isinstance(online, dict) or not stamp(online.get("synced_at")):
                    raise RunnerError("线上快照尚无已同步记录，未验收。")
                for note_id, resolved_id, expected in expected_notes:
                    remote = self.cloud.request("notes/" + quote(note_id, safe=""))
                    if (not isinstance(remote, dict) or remote.get("id") != resolved_id
                            or remote.get("markdown") != expected):
                        raise RunnerError("远端笔记与本机脱敏正文读回不一致，未验收。")
            except (OSError, ValueError, TypeError, RuntimeError):
                raise RunnerError("线上快照或笔记尚未读回一致，未验收。") from None
            receipt = {"job_status": job["status"], "quality_checked": True, "local_readback": True,
                       "online_synced": True, "online_readback": True, "online_synced_at": online["synced_at"],
                       "note_ids": note_ids, "notes": readbacks,
                       "topics": review["topics"], "assessment": review["assessment"],
                       "pending_debt_checked": review.get("pending_debt_checked", not pending), "pending_job_ids": pending}
            accepted = advance_window(self.data, result.get("archive_window"), job_id,
                                      verified=True, receipt=receipt, accepted_at=self.now.isoformat())
            active.update(outstanding_job_id=None, pending_job_ids=[], last_accepted_job_id=job_id,
                          last_accepted_until=accepted["accepted_until"])
            self._save(active)
            return {"ok": True, "action": "accepted", "job_id": job_id,
                    "accepted_until": accepted["accepted_until"], "note_ids": note_ids,
                    "online_readback": True, "pending_job_ids_reviewed": pending}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="可选私有配置；默认沿用已选工作区或本项目配置")
    parser.add_argument("--api", help="本机 API 地址或端口；默认读取配置 port")
    commands = parser.add_subparsers(dest="command", required=True)
    queue = commands.add_parser("queue", help="提交或续接本周任务，不等待执行")
    queue.add_argument("--until", help="可选冻结上界（带时区 ISO），默认最近一个周五北京时间 19:00")
    status = commands.add_parser("status", help="读取真实任务状态")
    status.add_argument("--job")
    accept = commands.add_parser("accept", help="真实读回后登记人工/自动化质量验收")
    accept.add_argument("--job", required=True)
    accept.add_argument("--review", required=True, help="已经完成质量复核的 JSON 文件")
    args = parser.parse_args(argv)
    try:
        config = load_settings(args.config)
        runner = WeeklyRunner(config, api=args.api)
        if args.command == "queue":
            result = runner.queue(args.until)
        elif args.command == "status":
            result = runner.status(args.job)
        else:
            review = json.loads(Path(args.review).read_text(encoding="utf-8-sig"))
            result = runner.accept(args.job, review)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
