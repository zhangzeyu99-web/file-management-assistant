"""Local API; the same web interface proxies here during local use."""
import argparse
import json
import shutil
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs, quote

from engine.migration_service import CHUNK_SIZE, MigrationService
from engine.runtime import CloudJobsUnavailable, Runtime
from engine.settings import ROOT, load_settings, validate_startup


def make_handler(runtime=None, *, migration=None):
    workspace = migration or MigrationService(runtime)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, data, code=200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            if self.command == "POST" and code >= 400:
                # Closing before a rejected body arrives can reset the response.
                # Drain a bounded tail without trusting a possibly false length.
                previous_timeout = self.connection.gettimeout()
                deadline, remaining = time.monotonic() + .1, 64 * 1024
                try:
                    while remaining:
                        wait = deadline - time.monotonic()
                        if wait <= 0:
                            break
                        self.connection.settimeout(wait)
                        chunk = self.rfile.read1(min(remaining, 8192))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                except OSError:
                    pass
                finally:
                    self.connection.settimeout(previous_timeout)

        def handle_request(self):
            try:
                host = self.headers.get("Host", "").split(":")[0]
                if host not in {"127.0.0.1", "localhost"}:
                    return self.respond({"error": "仅接受本机请求"}, 403)
                origin = self.headers.get("Origin")
                if origin and urlparse(origin).hostname not in {"127.0.0.1", "localhost"}:
                    return self.respond({"error": "请求来源不匹配"}, 403)
                url = urlparse(self.path)
                if not url.path.startswith("/api/workspace/"):
                    return self.respond({"error": "未找到接口"}, 404)
                path = unquote(url.path[len("/api/workspace/"):])
                args = parse_qs(url.query)
                payload = {}
                if path == "migration/import/chunk" and self.command == "POST":
                    if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/octet-stream":
                        return self.respond({"error": "分块上传需要 application/octet-stream"}, 415)
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= CHUNK_SIZE:
                        return self.respond({"error": "上传分块不能超过 4 MiB"}, 413)
                    body = self.rfile.read(size)
                    if len(body) != size:
                        return self.respond({"error": "上传分块不完整"}, 400)
                    return self.respond(workspace.append_chunk(args.get("upload_id", [""])[0],
                        int(args.get("offset", ["-1"])[0]), body))
                if self.command == "POST":
                    if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                        return self.respond({"error": "请求需要 application/json"}, 415)
                    size = int(self.headers.get("Content-Length", "0"))
                    if size < 0 or size > 18 * 1024 * 1024:
                        return self.respond({"error": "文件过大"}, 413)
                    payload = json.loads(self.rfile.read(size) or b"{}")
                    if not isinstance(payload, dict):
                        return self.respond({"error": "请求内容必须是对象"}, 400)
                if path == "migration/status" and self.command == "GET":
                    return self.respond(workspace.status())
                if path == "migration/import/start" and self.command == "POST":
                    return self.respond(workspace.start_upload(payload), 201)
                if path == "migration/import/preview" and self.command == "POST":
                    return self.respond(workspace.preview(payload))
                if path == "migration/import/cancel" and self.command == "POST":
                    return self.respond(workspace.cancel_upload(payload.get("upload_id")))
                if path == "migration/import/commit" and self.command == "POST":
                    return self.respond(workspace.commit(payload), 202)
                if path.startswith("migration/operations/") and self.command == "GET":
                    return self.respond(workspace.operation(path[len("migration/operations/"):]))
                runtime = workspace.runtime
                if path == "health":
                    return self.respond(workspace.health())
                if path.startswith("migration/download/") and self.command == "GET":
                    if not runtime:
                        return self.respond({"error": "尚未启用知识库"}, 409)
                    target, filename = runtime.migration_download(path[len("migration/download/"):])
                    with target.open("rb") as stream:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/zip")
                        self.send_header("Content-Length", str(target.stat().st_size))
                        self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(filename))
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        shutil.copyfileobj(stream, self.wfile, 1024 * 1024)
                    return
                if not runtime:
                    empty = {"overview": {"projects": [], "recent": [], "note_count": 0, "mode": "local"},
                             "projects": {"items": []}, "jobs": {"items": []},
                             "search": {"query": args.get("q", [""])[0], "items": [], "total": 0}}
                    if self.command == "GET" and path in empty:
                        return self.respond(empty[path])
                    return self.respond({"error": "请先在迁移页面导入知识库", "setup_required": True}, 409)
                if workspace.switching and self.command == "POST":
                    return self.respond({"error": "正在导入并切换知识库，请等待完成"}, 409)
                if path == "overview":
                    return self.respond({**runtime.library.overview(), "mode": "local"})
                if path == "projects":
                    return self.respond({"items": runtime.library.projects()})
                if path.startswith("projects/"):
                    return self.respond(runtime.library.get_project(path[9:]))
                if path == "search":
                    return self.respond(runtime.library.search(args.get("q", [""])[0],
                        limit=max(0, min(5000, int(args.get("limit", ["50"])[0])))))
                if path == "notes/resolve":
                    return self.respond(runtime.library.resolve_wiki_note(
                        args.get("target", [""])[0], args.get("from", [""])[0]))
                if path.startswith("notes/"):
                    return self.respond(runtime.library.get_note(path[6:]))
                if path == "upload" and self.command == "POST":
                    return self.respond(runtime.upload(payload["filename"], payload["content"], payload.get("request_id")), 202)
                if path == "jobs":
                    if self.command == "GET":
                        return self.respond(runtime.list_jobs())
                    return self.respond(runtime.create(payload["kind"], payload.get("input", {}), payload.get("request_id")), 202)
                if path.startswith("jobs/"):
                    parts = path.split("/")
                    job = runtime.get_job(parts[1])
                    if not job:
                        return self.respond({"error": "未找到任务"}, 404)
                    if len(parts) == 3 and self.command == "POST":
                        if parts[2] == "cancel":
                            return self.respond(runtime.cancel_job(parts[1]))
                        if parts[2] == "retry":
                            if not job.get("stale") and job["status"] not in {"failed", "partial", "cancelled"}:
                                return self.respond({"error": "此任务不需要重试"}, 409)
                            return self.respond(runtime.retry_job(parts[1]), 202)
                    return self.respond(job)
                return self.respond({"error": "未找到接口"}, 404)
            except CloudJobsUnavailable as e:
                return self.respond({"error": str(e), "request_id": e.request_id}, 503)
            except (ValueError, KeyError, FileNotFoundError, zipfile.BadZipFile) as e:
                return self.respond({"error": str(e)}, 400)
            except Exception as e:
                return self.respond({"error": str(e)}, 500)

        do_GET = handle_request
        do_POST = handle_request
    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-worker", action="store_true")
    parser.add_argument("--allow-setup", action="store_true")
    parser.add_argument("--web-port", type=int)
    args = parser.parse_args()
    runtime = None
    config = None
    try:
        config = load_settings(args.config)
        validate_startup(config)
        runtime = Runtime(config)
    except (ValueError, OSError) as error:
        if not args.allow_setup or args.config or not str(error).startswith("未找到配置"):
            raise
    if runtime and not args.no_worker:
        runtime.start()
    port = args.port or (config["port"] if config else 8767)
    workspace = MigrationService(runtime, project_root=ROOT, port=port,
                                 web_port=args.web_port or (config["web_port"] if config else 5174),
                                 start_worker=not args.no_worker)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(migration=workspace))
    print(f"Obsidian workspace API http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        if workspace.runtime:
            workspace.runtime.stop.set()
