from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import file_assistant
import knowledge_assistant
from config_loader import load_config


DEFAULT_CONFIG = ROOT / "config.json"
ASSET_ROOT = ROOT / "docs" / "assets"

PUBLIC_COPY_REPLACEMENTS = {
    "默认只读": "安全检查",
    "不删除、不移动、不重命名、不重写源文件": "源文件保持原样",
    "站点式知识库": "知识整理首页",
    "首屏极简": "首页聚焦",
    "首页不再堆功能": "首页聚焦三项操作",
    "每次点击后": "操作完成后",
}


def sanitize_public_copy(value: Any) -> str:
    text = str(value or "")
    for old, new in PUBLIC_COPY_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def count_obsidian_notes(config: dict[str, Any]) -> int:
    vault = knowledge_assistant.vault_path(config)
    if not vault.exists():
        return 0
    count = 0
    for path in vault.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(vault).parts):
            continue
        count += 1
    return count


def build_status(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)
    return {
        "ok": True,
        "product": knowledge_assistant.PRODUCT,
        "config": str(config_path),
        "vault": str(knowledge_assistant.vault_path(config)),
        "runtime_root": str(knowledge_assistant.runtime_root(config)),
        "metrics": {
            "core_operations": 3,
            "source_file_mutations": 0,
            "obsidian_notes": count_obsidian_notes(config),
        },
        "safety": knowledge_assistant.SAFETY_TEXT,
    }


def split_local_paths(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif value is None:
        raw_items = []
    else:
        raw_items = str(value).replace(";", "\n").splitlines()
    paths: list[str] = []
    for item in raw_items:
        cleaned = str(item).strip().strip('"').strip("'")
        if cleaned:
            paths.append(cleaned)
    return list(dict.fromkeys(paths))


def extract_local_target_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("local_paths", "target_paths", "paths", "path_text", "target_path"):
        paths.extend(split_local_paths(payload.get(key)))
    return list(dict.fromkeys(paths))


def selected_file_metadata(payload: dict[str, Any]) -> list[dict[str, Any]]:
    selected = payload.get("selected_files") or []
    if not isinstance(selected, list):
        return []
    files: list[dict[str, Any]] = []
    for item in selected[:50]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        files.append(
            {
                "name": name,
                "size": int(item.get("size") or 0),
                "type": str(item.get("type") or ""),
                "relative_path": str(item.get("relative_path") or ""),
            }
        )
    return files


def inspect_local_targets(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    paths = extract_local_target_paths(payload)
    selected_files = selected_file_metadata(payload)
    if not paths:
        defaults = [
            {
                "name": str(root.get("name") or Path(str(root.get("path") or "")).name),
                "path": str(root.get("path") or ""),
                "max_depth": int(root.get("max_depth", 2)),
                "max_files": int(root.get("max_files", 2000)),
            }
            for root in config.get("watch_roots", [])
        ]
        return {
            "ok": True,
            "action": "inspect-local-targets",
            "mode": "configured-defaults",
            "summary": {
                "target_count": len(defaults),
                "existing_count": sum(1 for item in defaults if Path(item["path"]).exists()),
                "selected_file_count": len(selected_files),
            },
            "targets": defaults,
            "selected_files": selected_files,
            "safety": "安全检查：未粘贴路径时使用 config.json / config.local.json 的扫描目录；不改动源文件。",
        }

    targets: list[dict[str, Any]] = []
    for raw_path in paths:
        target = Path(raw_path).expanduser()
        exists = target.exists()
        is_dir = target.is_dir() if exists else False
        is_file = target.is_file() if exists else False
        item: dict[str, Any] = {
            "path": str(target),
            "exists": exists,
            "is_dir": is_dir,
            "is_file": is_file,
            "kind": "directory" if is_dir else "file" if is_file else "missing",
        }
        if is_file:
            stat = target.stat()
            item.update({"size_bytes": int(stat.st_size), "extension": file_assistant.normalize_extension(target)})
        elif is_dir:
            files = file_assistant.iter_files(
                target,
                max_depth=int(payload.get("max_depth") or 2),
                max_files=int(payload.get("max_files") or 100),
                excluded_dirs={str(name).lower() for name in config.get("exclude_dir_names", [])},
            )
            item.update({"preview_file_count": len(files), "preview_files": [str(path) for path in files[:8]]})
        targets.append(item)

    return {
        "ok": True,
        "action": "inspect-local-targets",
        "mode": "custom-local-paths",
        "summary": {
            "target_count": len(targets),
            "existing_count": sum(1 for item in targets if item["exists"]),
            "directory_count": sum(1 for item in targets if item["is_dir"]),
            "file_count": sum(1 for item in targets if item["is_file"]),
            "selected_file_count": len(selected_files),
        },
        "targets": targets,
        "selected_files": selected_files,
        "safety": "只读检查；不会删除、移动、重命名或重写源文件。",
    }


GUI_CORE_ACTIONS = {"organize", "review", "extract"}
GUI_SUPPORT_ACTIONS = {"inspect-local-targets", "open-path"}
DEPRECATED_GUI_ACTIONS = {
    "today",
    "file-radar",
    "file-scan",
    "obsidian-health",
    "obsidian-audit",
    "full-scan",
    "guide",
    "scenarios",
    "scenario-demo",
    "guidebook",
    "onboarding",
    "deep-thinking",
    "knowledge-index",
    "archive-ai-chat",
    "build-ai-context",
    "self-evolution",
    "ask",
    "capture",
    "daily",
    "action-note",
    "card-note",
    "time-review",
    "inbox-route",
    "codex-prompt",
    "open-obsidian",
    "open-guidebook",
    "open-interaction-guide",
    "open-codex",
    "remind",
    "legacy-index",
}


def deprecated_gui_action(action: str) -> dict[str, Any]:
    return {
        "ok": False,
        "action": action,
        "status": "deprecated",
        "summary": "这个入口已从 GUI 产品主线降级。当前只保留三件事：添加资料、搜索回顾、生成 AI 上下文包。",
        "error": "deprecated gui action",
        "sources": [],
        "artifacts": [],
        "next_actions": ["添加资料", "搜索回顾", "生成 AI 上下文包"],
        "safety": knowledge_assistant.SAFETY_TEXT,
        "debug": {"reason": "core_loop_only"},
    }


def run_gui_action(action: str, payload: dict[str, Any] | None = None, config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = payload or {}

    if action in GUI_CORE_ACTIONS:
        return knowledge_assistant.run_action(action, payload, config_path)

    if action in DEPRECATED_GUI_ACTIONS:
        return deprecated_gui_action(action)

    if action == "inspect-local-targets":
        config = load_config(config_path)
        return inspect_local_targets(config, payload)

    if action == "open-path":
        config = load_config(config_path)
        target = Path(str(payload.get("path") or ""))
        if not target.exists():
            return {"ok": False, "error": f"path not found: {target}"}
        allowed_roots = configured_open_roots(config)
        if allowed_roots and not path_is_inside_any_root(target, allowed_roots):
            return {"ok": False, "error": f"path not allowed: {target}"}
        opened_as = "system"
        vault = Path(str(config.get("obsidian_vault") or "")).expanduser()
        if target.suffix.lower() == ".md" and vault.exists():
            try:
                relative = target.resolve().relative_to(vault.resolve()).as_posix()
                uri = f"obsidian://open?vault={quote(vault.name)}&file={quote(relative)}"
                webbrowser.open(uri)
                opened_as = "obsidian"
            except ValueError:
                os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            os.startfile(str(target))  # type: ignore[attr-defined]
        return {"ok": True, "opened": str(target), "opened_as": opened_as}

    return {"ok": False, "error": f"unsupported action: {action}"}


def http_status_for_action_result(result: dict[str, Any]) -> int:
    if result.get("ok"):
        return 200
    if result.get("status") == "not_found":
        return 200
    return 400


def configured_open_roots(config: dict[str, Any]) -> list[Path]:
    roots = config.get("allowed_open_roots")
    if not roots:
        roots = [config.get("runtime_root"), config.get("obsidian_vault"), config.get("knowledge_root")]
    return [Path(str(item)).expanduser() for item in roots if item]


def path_is_inside_any_root(target: Path, roots: list[Path]) -> bool:
    try:
        resolved_target = target.resolve()
    except OSError:
        return False
    for root in roots:
        if not root.exists():
            continue
        try:
            resolved_target.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


HTML = (ROOT / "docs" / "assets" / "gui" / "workspace.html").read_text(encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    config_path = DEFAULT_CONFIG

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path in {"/advanced", "/advanced/"}:
            advanced = ROOT / "docs" / "assets" / "gui" / "advanced.html"
            body = advanced.read_bytes()
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.send_header("content-length", "0")
            self.end_headers()
            return
        if parsed.path.startswith("/assets/"):
            relative = unquote(parsed.path.removeprefix("/assets/"))
            target = (ASSET_ROOT / relative).resolve()
            asset_root = ASSET_ROOT.resolve()
            if not str(target).startswith(str(asset_root)) or not target.is_file():
                self._json({"ok": False, "error": "asset not found"}, 404)
                return
            content_types = {
                ".html": "text/html; charset=utf-8",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }
            content_type = content_types.get(target.suffix.lower(), "application/octet-stream")
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("content-type", content_type)
            self.send_header("cache-control", "no-cache")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/status":
            self._json(build_status(self.config_path))
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/action":
            self._json({"ok": False, "error": "not found"}, 404)
            return
        length = int(self.headers.get("content-length") or "0")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            result = run_gui_action(str(data.get("action") or ""), data.get("payload") or {}, self.config_path)
            self._json(result, http_status_for_action_result(result))
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._json({"ok": False, "error": str(exc)}, 500)


def main() -> None:
    parser = argparse.ArgumentParser(description="知识行动助手 GUI")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    Handler.config_path = Path(args.config)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        webbrowser.open(url)
    print(json.dumps({"ok": True, "url": url}, ensure_ascii=False))
    server.serve_forever()


if __name__ == "__main__":
    main()
