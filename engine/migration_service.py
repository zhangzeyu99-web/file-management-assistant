"""Local browser migration, bounded uploads and atomic workspace activation."""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import socket
import threading
import uuid
import zipfile
from pathlib import Path

from .migration import (CONFIG_LIST_PATHS, CONFIG_PATHS, MigrationError, PathMappings,
                        import_bundle, inspect_bundle)
from .settings import ROOT, load_settings, validate_startup

CHUNK_SIZE = 4 * 1024 * 1024
IMPORT_LIMIT = 2 * 1024**3


def documents_directory():
    if os.name == "nt":
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            return Path(buffer.value)
    return Path.home() / "Documents"


def default_destination(base=None):
    base = Path(base) if base else documents_directory()
    for index in range(1, 10000):
        candidate = base / ("个人知识工作台" + (f"-{index}" if index > 1 else ""))
        if not candidate.exists() or candidate.is_dir() and not any(candidate.iterdir()):
            return candidate
    raise MigrationError("无法找到空迁移目录，请选择其他目录。")


def _destination(value):
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        raise MigrationError("目标目录必须是完整路径。")
    for path in [raw, *raw.parents]:
        if path.exists() and (path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
            raise MigrationError("目标目录不能通过链接或重解析点进入。")
    target = raw.resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise MigrationError("目标目录已有内容，请使用新的空目录；不会覆盖已有知识库。")
    return target


def _slug(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:60] or "资料"


def automatic_mappings(config, destination):
    """Map every configured source root; original source files are not copied."""
    destination = Path(destination)
    rows, used = [], set()

    def add(source, target):
        canonical = str(Path(source).resolve()).casefold()
        if canonical not in used:
            used.add(canonical)
            rows.append({"from": str(Path(source).resolve()), "to": str(target.resolve())})

    add(config["obsidian_vault"], destination / "Obsidian-Work")
    add(config["data_root"], destination / "runtime")
    add(config["state_path"], destination / "runtime/checkpoint/state.json")

    def mapped(source):
        try:
            PathMappings(rows).path(source, required=True)
            return True
        except MigrationError:
            return False

    for group in ("watch_roots", "memory_roots"):
        for index, row in enumerate(config.get(group, []), 1):
            source = row["path"] if isinstance(row, dict) else row
            name = row.get("name", Path(source).name) if isinstance(row, dict) else Path(source).name
            if not mapped(source):
                add(source, destination / "sources" / group / f"{index}-{_slug(name)}")
    for key in CONFIG_PATHS:
        if config.get(key) and not mapped(config[key]):
            add(config[key], destination / "sources" / key)
    for key in CONFIG_LIST_PATHS:
        for index, source in enumerate(config.get(key, []), 1):
            if not mapped(source):
                add(source, destination / "sources" / key / str(index))
    return rows


class MigrationService:
    def __init__(self, runtime=None, *, project_root=ROOT, staging_root=None,
                 documents_root=None, runtime_factory=None, port=8767, web_port=5174,
                 start_worker=True, setup_error=None):
        self.runtime = runtime
        self.project_root = Path(project_root).resolve()
        self.staging = Path(staging_root) if staging_root else self.project_root / ".migration-staging"
        self.documents_root = documents_root
        self.runtime_factory = runtime_factory
        self.port, self.web_port = port, web_port
        self.start_worker = start_worker
        self.setup_error = setup_error
        self.uploads, self.operations = {}, {}
        self.lock = threading.RLock()
        self.switching = False

    def status(self):
        runtime = self.runtime
        return {"mode": "local", "configured": runtime is not None,
                "default_destination": str(default_destination(self.documents_root)),
                "device": socket.gethostname(), "can_export": bool(runtime) and not self.switching,
                "import_limit_bytes": IMPORT_LIMIT, "setup_error": self.setup_error,
                "switching": self.switching}

    def health(self):
        if self.runtime:
            return {**self.runtime.health(), "setup_required": False, "migration_switching": self.switching,
                    "config_path": self.runtime.cfg.get("_config_path", ""), "project_root": str(self.project_root)}
        return {"mode": "local", "online": True, "worker_running": False, "active_job": None,
                "native_context": False, "cloud_connected": False, "setup_required": True,
                "setup_error": self.setup_error, "migration_switching": self.switching,
                "config_path": "", "project_root": str(self.project_root)}

    def start_upload(self, payload):
        size, filename = payload.get("size"), payload.get("filename")
        if not isinstance(filename, str) or not filename.lower().endswith(".zip"):
            raise MigrationError("请选择工作台导出的 ZIP 迁移包。")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= IMPORT_LIMIT:
            raise MigrationError("迁移包大小必须在 1 字节到 2 GiB 之间。")
        with self.lock:
            pending = [row for row in self.uploads.values() if not row.get("committed")]
            if len(pending) >= 3 or sum(row["size"] for row in pending) + size > IMPORT_LIMIT:
                raise MigrationError("待导入文件已达到暂存上限，请完成当前导入或重新启动迁移页。")
            self.staging.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(self.staging).free < size + CHUNK_SIZE:
                raise MigrationError("本机暂存磁盘空间不足。")
            upload_id = str(uuid.uuid4())
            path = self.staging / (upload_id + ".zip")
            path.touch(exist_ok=False)
            self.uploads[upload_id] = {"path": path, "size": size, "received": 0,
                                       "filename": filename, "plan": None}
            return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE}

    def _upload(self, upload_id):
        row = self.uploads.get(upload_id)
        if not row:
            raise MigrationError("上传记录不存在或服务已重启，请重新选择迁移包。")
        return row

    def _target(self, value):
        target = _destination(value)
        roots = [self.project_root, self.staging.resolve()]
        if self.runtime:
            config = getattr(self.runtime, "cfg", {})
            roots.extend(Path(config[key]).resolve() for key in ("obsidian_vault", "data_root") if config.get(key))
        if any(target.is_relative_to(root) or root.is_relative_to(target) for root in roots):
            raise MigrationError("新目录必须独立于当前知识库、运行数据和源码目录。")
        return target

    def cancel_upload(self, upload_id):
        with self.lock:
            row = self._upload(upload_id)
            if row.get("committed"):
                raise MigrationError("已提交的导入不能删除上传文件，请等待导入结果。")
            row["path"].unlink(missing_ok=True)
            del self.uploads[upload_id]
            return {"cancelled": True}

    def append_chunk(self, upload_id, offset, content):
        if not content or len(content) > CHUNK_SIZE:
            raise MigrationError("每个上传分块必须在 1 字节到 4 MiB 之间。")
        with self.lock:
            row = self._upload(upload_id)
            if row.get("committed") or row["plan"]:
                raise MigrationError("迁移包已经预检，不能继续修改上传内容。")
            if offset < 0 or offset + len(content) > row["size"]:
                raise MigrationError("分块超出申报文件大小。")
            if offset < row["received"]:
                with row["path"].open("rb") as stream:
                    stream.seek(offset)
                    if offset + len(content) <= row["received"] and stream.read(len(content)) == content:
                        return {"received": row["received"]}
                raise MigrationError("重传分块与已上传内容不一致。")
            if offset != row["received"]:
                raise MigrationError("上传偏移不连续，请从已确认的位置重试。")
            with row["path"].open("ab") as stream:
                stream.write(content)
            row["received"] += len(content)
            return {"received": row["received"]}

    def preview(self, payload):
        with self.lock:
            row = self._upload(payload.get("upload_id"))
            if row.get("committed"):
                raise MigrationError("此迁移包已提交。")
            if row["received"] != row["size"]:
                raise MigrationError("迁移包尚未上传完整。")
            target = self._target(payload.get("destination") or str(default_destination(self.documents_root)))
            try:
                metadata = inspect_bundle(row["path"])
            except zipfile.BadZipFile as error:
                raise MigrationError("迁移包损坏或不是有效 ZIP，请重新选择工作台导出的迁移包。") from error
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise MigrationError("迁移包中的说明文件损坏，请重新选择工作台导出的迁移包。") from error
            mappings = automatic_mappings(metadata["config"], target)
            config_path = target / "workspace.json"
            try:
                checked = import_bundle(row["path"], mappings, config_path, dry_run=True)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise MigrationError("迁移包中的检查点或记录损坏，请重新导出迁移包。") from error
            with zipfile.ZipFile(row["path"]) as archive:
                state = json.loads(archive.read("checkpoint.json").decode("utf-8"))
                names = archive.namelist()
            summary = {"vault_files": sum(name.startswith("vault/") for name in names),
                       "notes": sum(name.startswith("vault/") and name.lower().endswith(".md") for name in names),
                       **{key: len(state[key]) for key in ("files", "threads", "feishu")}}
            warnings = ["原电脑的外部资料文件不会随包复制；已保留总结和增量记录，来源目录已映射到新电脑。",
                        "飞书、模型和线上服务需要在新电脑重新授权；导入不会连接旧云端队列。"]
            if checked.get("unmapped_historical_file_keys"):
                warnings.append("部分已停用的历史文件路径保留为来源记录，不会扫描旧电脑。")
            if self.runtime:
                warnings.append("确认后会切换到独立的新知识库；当前知识库及配置保留。")
            plan = {"upload_id": payload["upload_id"], "destination": str(target),
                    "summary": summary, "mappings": mappings, "warnings": warnings, "ready": True,
                    "config_path": str(config_path)}
            row["plan"] = plan
            return copy.deepcopy(plan)

    def commit(self, payload):
        with self.lock:
            row = self._upload(payload.get("upload_id"))
            if row.get("operation_id"):
                prior = self.operations[row["operation_id"]]
                if prior["status"] != "failed":
                    return copy.deepcopy(prior)
            if not row["plan"] or payload.get("destination") != row["plan"]["destination"]:
                raise MigrationError("请先预检并确认同一个目标目录。")
            if self.switching:
                raise MigrationError("另一项迁移正在进行，请等待完成。")
            if self.runtime and self.runtime.health().get("active_job"):
                raise MigrationError("当前任务正在执行，请等任务结束后再导入并切换。")
            if not row.get("imported"):
                self._target(row["plan"]["destination"])
            operation_id = str(uuid.uuid4())
            operation = {"operation_id": operation_id, "status": "running", "stage": "正在导入并核对资料"}
            self.operations[operation_id] = operation
            row.update(committed=True, operation_id=operation_id)
            self.switching = True
            threading.Thread(target=self._import, args=(row, operation_id), daemon=True,
                             name="workspace-migration").start()
            return copy.deepcopy(operation)

    def operation(self, operation_id):
        with self.lock:
            if operation_id not in self.operations:
                raise MigrationError("迁移任务不存在。")
            return copy.deepcopy(self.operations[operation_id])

    def _factory(self, config):
        if self.runtime_factory:
            return self.runtime_factory(config)
        from .runtime import Runtime
        return Runtime(config)

    def _activate(self, config_path):
        config = load_settings(config_path)
        config["port"], config["web_port"] = self.port, self.web_port
        validate_startup(config)
        # This is a newly created, isolated configuration. Preserve the actual
        # listening ports so the next desktop launch uses this same endpoint.
        config_file = Path(config_path)
        portable = json.loads(config_file.read_text(encoding="utf-8-sig"))
        portable.update(port=self.port, web_port=self.web_port, cloud_url="")
        config_file.write_text(json.dumps(portable, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        old = self.runtime
        new = self._factory(config)
        pointer = self.project_root / ".workspace-active.json"
        # A failed read or write permission check must not stop the old worker.
        previous_pointer = pointer.read_bytes() if pointer.exists() else None
        temporary = pointer.with_name(pointer.name + "." + str(uuid.uuid4()) + ".tmp")
        stopped, published = False, False
        try:
            temporary.write_text(json.dumps({"config": str(config_file.resolve())}), encoding="utf-8")
            if old:
                old.handoff_for_migration()
                stopped = True
            os.replace(temporary, pointer)
            published = True
            self.runtime = new
            self.setup_error = None
            if self.start_worker:
                new.start()
        except Exception:
            self.runtime = old
            try:
                if published:
                    if previous_pointer is None:
                        pointer.unlink(missing_ok=True)
                    else:
                        pointer.write_bytes(previous_pointer)
            finally:
                if old and stopped and self.start_worker:
                    self.runtime = self._factory(old.cfg)
                    self.runtime.start()
            raise
        finally:
            temporary.unlink(missing_ok=True)
        return new

    def _import(self, row, operation_id):
        try:
            plan = row["plan"]
            if not row.get("imported"):
                self._target(plan["destination"])
                row["imported"] = import_bundle(row["path"], plan["mappings"], plan["config_path"])
            imported = row["imported"]
            with self.lock:
                self.operations[operation_id]["stage"] = "正在启用新知识库"
                runtime = self._activate(imported["config"])
                self.operations[operation_id].update(status="completed", stage="已导入并启用",
                    result={"activated": True, "config_path": imported["config"], "vault": imported["vault"],
                            "note_count": runtime.library.overview()["note_count"]})
            try:
                row["path"].unlink(missing_ok=True)
            except OSError:
                # Cleanup cannot turn an activated library into a failed import.
                pass
        except Exception as error:
            with self.lock:
                self.operations[operation_id].update(status="failed", stage="导入未完成", error=str(error))
                if row.get("imported"):
                    self.operations[operation_id]["result"] = {"activated": False,
                        "config_path": row["imported"]["config"], "vault": row["imported"]["vault"],
                        "note_count": row["plan"]["summary"]["notes"]}
        finally:
            with self.lock:
                self.switching = False
