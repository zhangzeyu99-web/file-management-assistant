"""Local API; the same web interface proxies here during local use."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse, parse_qs

from engine.runtime import CloudJobsUnavailable, Runtime
from engine.settings import load_settings


def make_handler(runtime):
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
                if self.command == "POST":
                    size = int(self.headers.get("Content-Length", "0"))
                    if size > 18 * 1024 * 1024:
                        return self.respond({"error": "文件过大"}, 413)
                    payload = json.loads(self.rfile.read(size) or b"{}")
                if path == "health":
                    return self.respond(runtime.health())
                if path == "overview":
                    return self.respond({**runtime.library.overview(), "mode": "local"})
                if path == "projects":
                    return self.respond({"items": runtime.library.projects()})
                if path.startswith("projects/"):
                    return self.respond(runtime.library.get_project(path[9:]))
                if path == "search":
                    return self.respond(runtime.library.search(args.get("q", [""])[0],
                        limit=max(0, min(5000, int(args.get("limit", ["50"])[0])))))
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
            except (ValueError, KeyError, FileNotFoundError) as e:
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
    args = parser.parse_args()
    config = load_settings(args.config)
    runtime = Runtime(config)
    if not args.no_worker:
        runtime.start()
    port = args.port or config["port"]
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(runtime))
    print(f"Obsidian workspace API http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        runtime.stop.set()
