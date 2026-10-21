"""Offline, credential-free transfer of notes and accepted incremental history."""
from __future__ import annotations

import argparse
import copy
import json
import math
import ntpath
import os
import re
import stat
import sys
import tempfile
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

from .incremental import load_state, path_key, stamp, writer_lock
from .privacy import redact_text, sensitive_path
from .settings import load_settings

FORMAT = "obsidian-workspace-migration"
CONFIG_PATHS = ("data_root", "state_path", "obsidian_vault", "output_root",
                "knowledge_root", "obsidian_run_dir", "runtime_root")
CONFIG_LIST_PATHS = ("old_output_roots", "generated_roots", "runtime_roots")
CONFIG_KEYS = {*CONFIG_PATHS, *CONFIG_LIST_PATHS, "watch_roots", "memory_roots",
               "exclude_dir_names", "port", "web_port", "feishu_enabled", "feishu_video_owner", "cloud_url"}
EXCLUDED_DIRS = {".git", ".obsidian", ".codex", ".openclaw", ".lark-cli",
                 "node_modules", "__pycache__", ".venv"}
SOFTWARE_INSTALLERS = {".apk", ".exe", ".msi", ".dmg", ".iso", ".appx", ".msix"}
EXCLUDED_SUFFIXES = {".dpapi", ".lock", ".guard", ".sqlite", ".sqlite3", ".db", ".jsonl",
                     ".key", ".pem", ".p12", ".pfx", ".kdbx"} | SOFTWARE_INSTALLERS
MAX_UNPACKED_BYTES = 8 * 1024**3
VAULT_METADATA = frozenset({".obsidian/knowledge-layout.json", ".obsidian/graph.json",
                            "30 资料/.note-index.json"})


class MigrationError(ValueError):
    pass


def _json(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _absolute(value):
    return isinstance(value, str) and (Path(value).is_absolute() or PureWindowsPath(value).is_absolute())


def _normal(value):
    if PureWindowsPath(value).is_absolute():
        return ntpath.normpath(value).replace("\\", "/").rstrip("/").casefold()
    return os.path.normpath(value).replace("\\", "/").rstrip("/").casefold()


class PathMappings:
    """Explicit longest-prefix mapping; never infer a new home or drive."""

    def __init__(self, rows):
        if not isinstance(rows, list) or not rows:
            raise MigrationError("路径映射必须是非空的 from/to 对象数组。")
        self.rows = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise MigrationError("每项路径映射必须是含 from/to 的对象。")
            source, target = row.get("from"), row.get("to")
            if not _absolute(source) or not _absolute(target):
                raise MigrationError("映射的 from/to 都必须是完整绝对路径。")
            source_key = _normal(str(Path(source).resolve()))
            if source_key in seen:
                raise MigrationError("同一个旧路径不能重复映射。")
            seen.add(source_key)
            self.rows.append((source_key, str(Path(target).resolve())))
        self.rows.sort(key=lambda pair: len(pair[0]), reverse=True)

    def path(self, value, *, required=False):
        canonical = str(Path(value).resolve())
        normalized = _normal(canonical)
        # normpath preserves the suffix spelling for readable source references.
        clean = ntpath.normpath(canonical).replace("\\", "/") if PureWindowsPath(canonical).is_absolute() else os.path.normpath(canonical).replace("\\", "/")
        for source, target in self.rows:
            if normalized == source or normalized.startswith(source + "/"):
                suffix = PurePosixPath(clean).parts[len(PurePosixPath(source).parts):]
                return str(Path(target).joinpath(*suffix))
        if required:
            raise MigrationError("缺少显式路径映射：" + value)
        return value

    def tree(self, value):
        if isinstance(value, str):
            return self.path(value) if _absolute(value) else value
        if isinstance(value, list):
            return [self.tree(item) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                mapped = path_key(self.path(key)) if _absolute(key) else key
                if mapped in result:
                    raise MigrationError("路径映射导致检查点键冲突，未导入：" + mapped)
                result[mapped] = self.tree(item)
            if result.get("lane") == "files" and _absolute(result.get("source")):
                result["source"] = path_key(result["source"])
            return result
        return value


def _inactive(data_root, state_path):
    for lock in (Path(data_root) / "executor.lock", Path(state_path).with_suffix(".lock")):
        if lock.exists():
            raise MigrationError("请先停止本机执行器并确认写入已结束；发现运行锁：" + str(lock))


class _ExecutorSession:
    """Proof scoped to the thread currently holding the executor's OS lock."""

    def __init__(self, data_root):
        self.data_root = Path(data_root).resolve()
        self.thread = threading.get_ident()
        self.marker = json.loads((self.data_root / "executor.lock").read_text(encoding="utf-8"))
        self.active = True

    def validate(self):
        marker = json.loads((self.data_root / "executor.lock").read_text(encoding="utf-8"))
        if (not self.active or self.thread != threading.get_ident() or
                marker != self.marker or marker.get("pid") != os.getpid() or not marker.get("owner")):
            raise MigrationError("当前执行器不再持有导出所需的独占锁。")


@contextmanager
def executor_session(data_root):
    """Hold the real writer lock; callers cannot opt out of its ownership checks."""
    with writer_lock(Path(data_root) / "executor.lock"):
        session = _ExecutorSession(data_root)
        try:
            yield session
        finally:
            session.active = False


def export_active_bundle(config, destination, session, *, progress=None):
    """Export from the serial worker, while owning both executor and state locks."""
    if not isinstance(session, _ExecutorSession) or session.data_root != Path(config["data_root"]).resolve():
        raise MigrationError("导出必须由当前知识库的独占执行器执行。")
    session.validate()
    state_lock = Path(config["state_path"]).with_suffix(".lock")
    with writer_lock(state_lock):
        state_owner = state_lock.read_bytes()

        def validate():
            session.validate()
            if state_lock.read_bytes() != state_owner:
                raise MigrationError("检查点写入锁已失效，迁移包未发布。")

        return _export_bundle(config, destination, validate=validate, progress=progress)


def _safe_file(path):
    if path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
        raise MigrationError("迁移不跟随符号链接或重解析点：" + str(path))


def _excluded(path):
    return (sensitive_path(path) or path.name.casefold() in {"auth.json", ".npmrc", ".netrc", "_netrc"} or
            path.suffix.lower() in EXCLUDED_SUFFIXES or
            path.name.lower().endswith((".sqlite-wal", ".sqlite-shm")) or
            any(part.casefold() in EXCLUDED_DIRS for part in path.parts))


def _validate_graph_settings(data):
    """Native graph preferences only; no plugin settings or arbitrary payloads."""
    booleans = {"collapse-filter", "showTags", "showAttachments", "hideUnresolved", "showOrphans",
                "collapse-color-groups", "collapse-display", "showArrow", "collapse-forces", "close"}
    numbers = {"textFadeMultiplier", "nodeSizeMultiplier", "lineSizeMultiplier", "centerStrength",
               "repelStrength", "linkStrength", "linkDistance", "scale"}
    if not isinstance(data, dict) or set(data) - booleans - numbers - {"search", "colorGroups"}:
        raise ValueError("图谱设置包含不支持的字段")

    def number(value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False

    def query(value):
        if not isinstance(value, str) or redact_text(value) != value:
            raise ValueError("图谱筛选必须是文字，且不能包含显式凭据")

    for key in booleans & data.keys():
        if not isinstance(data[key], bool):
            raise ValueError("图谱显示开关必须是布尔值")
    for key in numbers & data.keys():
        if not number(data[key]) or data[key] < 0:
            raise ValueError("图谱外观和力度必须是有限非负数字")
    if "search" in data:
        query(data["search"])
    if "colorGroups" in data:
        if not isinstance(data["colorGroups"], list):
            raise ValueError("图谱颜色组必须是数组")
        for group in data["colorGroups"]:
            if not isinstance(group, dict) or set(group) != {"query", "color"}:
                raise ValueError("图谱颜色组只允许筛选和颜色")
            query(group["query"])
            color = group["color"]
            if (not isinstance(color, dict) or set(color) != {"a", "rgb"}
                    or not number(color["a"]) or not 0 <= color["a"] <= 1
                    or not isinstance(color["rgb"], int) or isinstance(color["rgb"], bool)
                    or not 0 <= color["rgb"] <= 0xFFFFFF):
                raise ValueError("图谱颜色必须是有效的透明度和 RGB 色值")


def _validate_vault_metadata(relative, content):
    """Only explicitly portable Obsidian metadata may bypass exclusions."""
    if relative not in VAULT_METADATA:
        return

    def note_path(value):
        if not isinstance(value, str):
            raise ValueError("笔记路径必须是字符串")
        path = PurePosixPath(value)
        if (not value or path.is_absolute() or "\\" in value or ":" in value
                or path.as_posix() != value or path.suffix.lower() != ".md"
                or any(part.startswith(".") and not (index == 0 and part == ".source-history")
                       for index, part in enumerate(path.parts))):
            raise ValueError("必须使用知识库相对笔记路径，不能包含绝对路径或越界路径")

    try:
        if relative == ".obsidian/graph.json":
            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("图谱设置不接受重复字段")
                    result[key] = value
                return result
            data = json.loads(content.decode("utf-8-sig"), object_pairs_hook=unique_object)
            _validate_graph_settings(data)
            return
        data = json.loads(content.decode("utf-8-sig"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("不支持的管理元数据版本")
        if relative == ".obsidian/knowledge-layout.json":
            aliases = data.get("path_aliases", {})
            if not isinstance(aliases, dict):
                raise ValueError("旧路径映射必须是对象")
            if "navigation" in data and not isinstance(data["navigation"], bool):
                raise ValueError("导航开关必须是布尔值")
            for old, new in aliases.items():
                note_path(old)
                note_path(new)
        else:
            if not isinstance(data.get("tasks"), dict):
                raise ValueError("任务身份映射必须是对象")
            for task_id, entry in data["tasks"].items():
                if (not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", task_id) or not isinstance(entry, dict)
                        or entry.get("status") not in {"reserved", "written"}):
                    raise ValueError("任务身份记录无效")
                note_path(entry.get("path"))
    except (UnicodeError, ValueError, TypeError) as error:
        raise MigrationError("知识库管理元数据无效（" + relative + "）：" + str(error)) from error


def _read_stable(path):
    _safe_file(path)
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise MigrationError("文件在导出期间变化，请停止写入后重试：" + str(path))
    return data


def _portable_config(cfg, state):
    result = {key: copy.deepcopy(value) for key, value in cfg.items() if key in CONFIG_KEYS}
    result.setdefault("memory_roots", [])
    for key in ("watch_roots", "memory_roots"):
        result[key] = [{k: v for k, v in row.items() if k in {"name", "path", "max_depth", "max_files"}}
                       if isinstance(row, dict) else row for row in result.get(key, [])]
    # A copied config must never silently resume the old cloud queue.
    result["cloud_url"] = ""
    baseline = Path(state.get("baseline", ""))
    if not stamp(state.get("baseline_at")):
        manifest = baseline / "run-manifest.json"
        if not manifest.is_file():
            raise MigrationError("缺少已验收基线时间，不能制作会重新扫描历史的迁移包。")
        state["baseline_at"] = json.loads(_read_stable(manifest).decode("utf-8-sig")).get("completed_at")
    if not stamp(state.get("baseline_at")):
        raise MigrationError("基线完成时间无效。")
    if not result.get("feishu_video_owner"):
        owner_file = baseline / "feishu-video-owner-page-1.json"
        if owner_file.is_file():
            page = json.loads(_read_stable(owner_file).decode("utf-8-sig"))
            owners = {r.get("result_meta", {}).get("owner_id") for r in page.get("data", {}).get("results", [])}
            owners.discard(None)
            owners.discard("")
            if len(owners) == 1:
                result["feishu_video_owner"] = owners.pop()
    return result


def _references(value, field):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == field and _absolute(item):
                yield item
            yield from _references(item, field)
    elif isinstance(value, list):
        for item in value:
            yield from _references(item, field)


def export_bundle(config, destination):
    """Read source state/vault only. A stopped executor is required."""
    cfg = load_settings(config)
    _inactive(cfg["data_root"], cfg["state_path"])
    with executor_session(cfg["data_root"]) as session:
        return export_active_bundle(cfg, destination, session)


def _export_bundle(cfg, destination, *, validate, progress=None):
    data_root, state_path, vault = (Path(cfg[key]).resolve() for key in ("data_root", "state_path", "obsidian_vault"))
    validate()
    destination = Path(destination).resolve()
    if destination.exists():
        raise MigrationError("迁移包已存在，未覆盖：" + str(destination))
    if any(destination.is_relative_to(root) for root in (data_root, vault)):
        raise MigrationError("迁移包必须保存到运行数据目录和笔记库之外。")
    state_before = _read_stable(state_path)
    state = load_state(state_path)
    portable = _portable_config(cfg, state)
    if not vault.is_dir():
        raise MigrationError("笔记库不存在。")
    files = {}
    excluded, installers = 0, 0
    for folder, dirs, names in os.walk(vault, followlinks=False):
        for name in list(dirs):
            child = Path(folder) / name
            if _excluded(child):
                dirs.remove(name)
                excluded += 1
            else:
                _safe_file(child)
        for name in names:
            path = Path(folder) / name
            if _excluded(path):
                excluded += 1
                installers += path.suffix.lower() in SOFTWARE_INSTALLERS
                continue
            files["vault/" + path.relative_to(vault).as_posix()] = path
    # Keep layout/link aliases, task identities and native graph preferences,
    # not the surrounding plugin settings. Note paths remain vault-relative.
    for relative in sorted(VAULT_METADATA):
        path = vault / relative
        for parent in [path.parent, *path.parent.parents]:
            if parent == vault:
                break
            if parent.exists():
                _safe_file(parent)
        if path.exists():
            _safe_file(path)
            if not path.is_file():
                raise MigrationError("知识库管理元数据不是文件：" + relative)
            files["vault/" + relative] = path
    for value in _references(state, "note"):
        path = Path(value).resolve()
        if not path.is_relative_to(vault) or "vault/" + path.relative_to(vault).as_posix() not in files:
            raise MigrationError("检查点引用的笔记不在可迁移库内：" + value)
    for value in _references(state, "check_note"):
        path = Path(value).resolve()
        if not path.is_relative_to(data_root) or not path.name.endswith("-check.md") or not path.is_file():
            raise MigrationError("私有来源检查记录缺失或超出运行目录：" + value)
        files["runtime/" + path.relative_to(data_root).as_posix()] = path
    receipts = data_root / "receipts"
    if receipts.is_dir():
        for path in receipts.glob("*.json"):
            files["runtime/receipts/" + path.name] = path
    for filename in ("source-checks.json", "weekly-archive.json"):
        record = data_root / filename
        if record.is_file():
            files["runtime/" + filename] = record
    manifest = {
        "format": FORMAT, "version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "config": portable, "excluded_file_or_directory_count": excluded,
        "software_installers_excluded": installers,
        "omitted": ["credentials", "locks", "raw_sessions", "queue", "uploads", "model_cache", "task_history",
                    "obsidian_plugin_settings", "software_installers"],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + "." + str(uuid.uuid4()) + ".tmp")
    snapshots = {}
    try:
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", _json(manifest))
            archive.writestr("checkpoint.json", _json(state))
            for index, (name, path) in enumerate(sorted(files.items()), 1):
                validate()
                if progress:
                    progress(index, len(files))
                current = path.stat()
                content = _read_stable(path)
                if name.startswith("vault/"):
                    _validate_vault_metadata(name[6:], content)
                after = path.stat()
                if (current.st_size, current.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise MigrationError("文件在导出期间变化，请停止写入后重试：" + str(path))
                info = zipfile.ZipInfo.from_file(path, name, strict_timestamps=False)
                info.compress_type = zipfile.ZIP_DEFLATED
                # Standard DOS time is only accurate to two seconds. Keep its
                # usual ZIP metadata and add the original nanoseconds as a small
                # entry comment so library dates and tie-breaking remain exact.
                info.comment = _json({"mtime_ns": current.st_mtime_ns})
                archive.writestr(info, content)
                snapshots[path] = (current.st_size, current.st_mtime_ns)
        validate()
        if state_path.read_bytes() != state_before:
            raise MigrationError("检查点在导出期间变化，请停止写入后重试。")
        if any((path.stat().st_size, path.stat().st_mtime_ns) != version for path, version in snapshots.items()):
            raise MigrationError("笔记或运行记录在导出期间变化，请停止写入后重试。")
        temporary.rename(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {"ok": True, "bundle": str(destination), "vault_files": sum(n.startswith("vault/") for n in files),
            "runtime_records": sum(n.startswith("runtime/") for n in files),
            "software_installers_excluded": installers, "omitted": manifest["omitted"]}


def _members(archive):
    seen, total = set(), 0
    for info in archive.infolist():
        name = info.filename
        path = PurePosixPath(name)
        if (not name or "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts or
                name != path.as_posix() or name.casefold() in seen):
            raise MigrationError("迁移包包含不安全或重复路径：" + name)
        if stat.S_ISLNK(info.external_attr >> 16) or info.is_dir():
            raise MigrationError("迁移包不接受链接或显式目录项。")
        managed = name.startswith("vault/") and name[6:] in VAULT_METADATA
        if _excluded(Path(name)) and not managed:
            raise MigrationError("迁移包包含禁止迁移的文件：" + name)
        allowed = (name in {"manifest.json", "checkpoint.json", "runtime/source-checks.json",
                            "runtime/weekly-archive.json"} or
                   name.startswith("vault/") or
                   re.fullmatch(r"runtime/receipts/[^/]+\.json", name) or
                   re.fullmatch(r"runtime/runs/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+-check\.md", name))
        if not allowed:
            raise MigrationError("迁移包包含范围外内容：" + name)
        seen.add(name.casefold())
        total += info.file_size
        if total > MAX_UNPACKED_BYTES:
            raise MigrationError("迁移包解压内容超过 8 GiB 上限。")
        if managed:
            _validate_vault_metadata(name[6:], archive.read(info))
    if not {"manifest.json", "checkpoint.json"} <= seen:
        raise MigrationError("迁移包缺少说明或检查点。")


def inspect_bundle(bundle):
    with zipfile.ZipFile(bundle) as archive:
        _members(archive)
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != FORMAT or manifest.get("version") != 1:
            raise MigrationError("不支持的迁移包格式。")
        return {"format": FORMAT, "version": 1, "config": manifest["config"],
                "omitted": manifest.get("omitted", []),
                "software_installers_excluded": manifest.get("software_installers_excluded", 0)}


def _map_config(config, mappings):
    if set(config) - CONFIG_KEYS:
        raise MigrationError("迁移包配置包含不支持的字段。")
    result = copy.deepcopy(config)
    for key in CONFIG_PATHS:
        if key in result:
            result[key] = mappings.path(result[key], required=True)
    for key in CONFIG_LIST_PATHS:
        result[key] = [mappings.path(value, required=True) for value in result.get(key, [])]
    for key in ("watch_roots", "memory_roots"):
        for index, row in enumerate(result.get(key, [])):
            if isinstance(row, dict):
                row["path"] = mappings.path(row["path"], required=True)
            else:
                result[key][index] = mappings.path(row, required=True)
    result["cloud_url"] = ""
    return result


def _write_new(target, data):
    """Publish a read-back file without replacing an existing destination."""
    temporary = target.with_name(".ow-" + str(uuid.uuid4()) + ".tmp")
    try:
        with temporary.open("xb") as output:
            output.write(data)
        if temporary.read_bytes() != data:
            raise MigrationError("写入读回不一致：" + str(target))
        if os.name == "nt":
            # Windows rename refuses an existing destination, and works on
            # ordinary FAT/exFAT disks without requiring hard-link support.
            os.rename(temporary, target)
        else:
            os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_target(target, expected):
    for path in [target, *target.parents]:
        if path.exists():
            _safe_file(path)
    if not target.is_file() or target.read_bytes() != expected:
        raise MigrationError("目标内容在导入期间发生变化，未发布配置：" + str(target))


def _mtime_ns(info):
    if info.comment:
        try:
            value = json.loads(info.comment.decode("utf-8"))["mtime_ns"]
        except (UnicodeError, ValueError, KeyError, TypeError) as error:
            raise MigrationError("迁移包文件时间元数据无效：" + info.filename) from error
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MigrationError("迁移包 mtime_ns 必须是非负整数：" + info.filename)
        return value
    # Packages created before precise mtime metadata use the standard ZIP time.
    return int(datetime(*info.date_time).timestamp() * 1_000_000_000)


def _import_bundle(bundle, mapping_rows, config_out, *, dry_run=False):
    mappings = PathMappings(mapping_rows)
    with zipfile.ZipFile(bundle) as archive:
        _members(archive)
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != FORMAT or manifest.get("version") != 1:
            raise MigrationError("不支持的迁移包格式。")
        config = _map_config(manifest["config"], mappings)
        data_root, state_path, vault = (Path(config[key]).resolve() for key in ("data_root", "state_path", "obsidian_vault"))
        config_out = Path(config_out).resolve()
        _inactive(data_root, state_path)
        if data_root.exists() and any(data_root.iterdir()):
            raise MigrationError("目标运行目录必须为空；不会覆盖已有队列、凭据或检查点。")
        if state_path.exists() or config_out.exists():
            raise MigrationError("目标配置或检查点已存在，未覆盖。")
        if not Path(config["output_root"]).is_relative_to(vault):
            raise MigrationError("新笔记输出目录必须在迁移后的笔记库内。")
        original_state = json.loads(archive.read("checkpoint.json").decode("utf-8"))
        if original_state.get("version") != 1 or any(not isinstance(original_state.get(k), dict) for k in ("files", "threads", "feishu")):
            raise MigrationError("迁移包检查点不是 version 1。")
        if not stamp(original_state.get("baseline_at")):
            raise MigrationError("迁移包没有独立可用的基线时间。")
        state = mappings.tree(original_state)
        pending = {state_path: _json(state), config_out: _json(config)}
        mtimes = {}
        if len(pending) != 2:
            raise MigrationError("配置与检查点目标不能相同。")
        for name in archive.namelist():
            if name.startswith("vault/"):
                target = vault.joinpath(*PurePosixPath(name[6:]).parts)
            elif name.startswith("runtime/"):
                target = data_root.joinpath(*PurePosixPath(name[8:]).parts)
            else:
                continue
            if target in pending:
                raise MigrationError("迁移目标路径冲突：" + str(target))
            data = archive.read(name)
            if name.startswith("runtime/") and name.endswith(".json"):
                data = _json(mappings.tree(json.loads(data.decode("utf-8-sig"))))
            pending[target] = data
            mtimes[target] = _mtime_ns(archive.getinfo(name))
        for field in ("note", "check_note"):
            for value in _references(state, field):
                target = Path(value).resolve()
                if target not in pending:
                    raise MigrationError("迁移后的检查点引用没有对应笔记或检查记录：" + value)
        for target, data in pending.items():
            for parent in [target, *target.parents]:
                if parent.exists():
                    _safe_file(parent)
            if target.exists() and (not target.is_file() or target.read_bytes() != data):
                raise MigrationError("目标已有不同内容，未覆盖人工文件：" + str(target))
        result = {"ok": True, "dry_run": dry_run, "config": str(config_out), "state_path": str(state_path),
                  "vault": str(vault), "files_to_create": sum(not p.exists() for p in pending),
                  "existing_identical_files": sum(p.exists() for p in pending),
                  "unmapped_historical_file_keys": sum(mappings.path(k) == k for k in original_state["files"]),
                  "omitted": manifest["omitted"], "cloud_connected": False}
        if dry_run:
            return result
        created, created_dirs = [], []
        try:
            # The new config only becomes startable after notes and checkpoint
            # have all been verified. Never expose a checkpoint before its notes.
            order = [p for p in pending if p not in {state_path, config_out}] + [state_path, config_out]
            for target in order:
                if target == config_out:
                    for completed, expected in pending.items():
                        if completed != config_out:
                            _verify_target(completed, expected)
                if target.exists():
                    _verify_target(target, pending[target])
                    continue
                missing = []
                for parent in target.parents:
                    if parent.exists():
                        _safe_file(parent)
                        break
                    missing.append(parent)
                for parent in reversed(missing):
                    try:
                        parent.mkdir()
                        created_dirs.append(parent)
                    except FileExistsError:
                        _safe_file(parent)
                _write_new(target, pending[target])
                created.append(target)
                if target in mtimes:
                    os.utime(target, ns=(target.stat().st_atime_ns, mtimes[target]))
        except BaseException:
            for target in reversed(created):
                if target.is_file() and not target.is_symlink() and target.read_bytes() == pending[target]:
                    target.unlink()
            for directory in reversed(created_dirs):
                try:
                    directory.rmdir()  # Only our new, still-empty directories.
                except OSError:
                    pass
            raise
        return result


def import_bundle(bundle, mapping_rows, config_out, *, dry_run=False):
    """Validate first; serialize writers independently of the empty data root."""
    if dry_run:
        return _import_bundle(bundle, mapping_rows, config_out, dry_run=True)
    with writer_lock(Path(tempfile.gettempdir()) / "obsidian-workspace-import.lock"):
        return _import_bundle(bundle, mapping_rows, config_out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="离线迁移笔记和增量记录；不携带凭据或任务队列。")
    commands = parser.add_subparsers(dest="action", required=True)
    export = commands.add_parser("export")
    export.add_argument("--config")
    export.add_argument("--output", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--bundle", required=True)
    restore = commands.add_parser("import")
    restore.add_argument("--bundle", required=True)
    restore.add_argument("--mappings", required=True, help="UTF-8 JSON 数组，每项含绝对路径 from/to")
    restore.add_argument("--config-out", required=True)
    restore.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "export":
            result = export_bundle(args.config, args.output)
        elif args.action == "inspect":
            result = inspect_bundle(args.bundle)
        else:
            rows = json.loads(Path(args.mappings).read_text(encoding="utf-8-sig"))
            result = import_bundle(args.bundle, rows, args.config_out, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
