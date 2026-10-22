"""Select new evidence and commit verified outputs without replaying old sources.

The version-1 checkpoint is authoritative. This module deliberately has no init
operation and never reads Codex's internal session files or source file bodies.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import stat
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class IncrementalError(ValueError):
    pass


SENSITIVE_FILENAME = re.compile(
    r"(^\.env|credentials?\.|secrets?\.|^tokens?\.|password|id_rsa|id_ed25519|config\.local|openclaw\.json)", re.I)


def path_key(path):
    return str(Path(os.path.expandvars(str(path))).expanduser().resolve()).casefold()


key = path_key


def stamp(value):
    """Compare epoch seconds, explicit epoch milliseconds, or zoned ISO dates.

    The existing v1 checkpoint uses seconds. Normalization happens only for
    comparisons/new receipts; loading a checkpoint never rewrites old fields.
    """
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        raise IncrementalError("时间不能是布尔值。")
    if isinstance(value, (int, float)) or re.fullmatch(r"\d+(?:\.\d+)?", str(value)):
        result = float(value)
        if result >= 100_000_000_000:
            result /= 1000
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise IncrementalError("时间必须含时区。")
        result = parsed.timestamp()
    if not math.isfinite(result) or result < 0:
        raise IncrementalError("时间无效。")
    return result


def load_state(path):
    target = Path(path)
    if not target.is_file():
        raise IncrementalError("检查点不存在；必须迁移已验收的原记录，不能初始化空状态。")
    state = json.loads(target.read_text(encoding="utf-8-sig"))
    if state.get("version") != 1 or any(not isinstance(state.get(k), dict) for k in ("files", "feishu", "threads")):
        raise IncrementalError("检查点不是可接续的 version 1 格式。")
    return state


def atomic_json(path, value):
    """Replace one UTF-8 JSON file; callers hold the common writer lock."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoding, newline = "utf-8", "\n"
    if target.exists():
        old_bytes = target.read_bytes()
        encoding = "utf-8-sig" if old_bytes.startswith(b"\xef\xbb\xbf") else "utf-8"
        newline = "\r\n" if b"\r\n" in old_bytes else "\n"
    text = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").replace("\n", newline)
    descriptor, temporary = tempfile.mkstemp(prefix="." + target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if Path(temporary).read_bytes().decode(encoding) != text:
            raise IncrementalError("临时文件读回不一致。")
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return True  # Never steal a malformed or legacy lock.
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.GetExitCodeProcess.restype = ctypes.c_int
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if handle:
            try:
                exit_code = ctypes.c_ulong()
                if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return True  # Unknown state must not allow stealing a live writer's lock.
                return exit_code.value == 259  # STILL_ACTIVE; an exited object may retain handles.
            finally:
                kernel.CloseHandle(handle)
        return ctypes.get_last_error() != 87  # Access denied is not a dead process.
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def _writer_guard(path):
    """OS lock serializes stale-lock recovery and is released after a crash."""
    with Path(str(path) + ".guard").open("a+b") as guard:
        if guard.tell() == 0:
            guard.write(b"0")
            guard.flush()
        guard.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(guard.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise IncrementalError("另一个写入者正在登记，请稍后重试。") from None
        try:
            yield
        finally:
            guard.seek(0)
            if os.name == "nt":
                msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)


@contextmanager
def writer_lock(path):
    """One writer gate, with the old .lock marker retained for compatibility."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _writer_guard(target):
        with _legacy_writer_marker(target):
            yield


@contextmanager
def _legacy_writer_marker(target):
    owner = {"pid": os.getpid(), "owner": str(uuid.uuid4()), "createdAt": datetime.now(timezone.utc).isoformat()}
    for attempt in range(2):
        try:
            handle = target.open("x", encoding="utf-8")
            break
        except FileExistsError:
            try:
                before = target.read_text(encoding="utf-8")
                prior = json.loads(before)
                if attempt == 0 and not _process_alive(prior.get("pid")) and target.read_text(encoding="utf-8") == before:
                    target.unlink()
                    continue
            except (OSError, ValueError, AttributeError):
                pass
            raise IncrementalError("另一个写入者正在登记，请稍后重试。") from None
    try:
        with handle:
            json.dump(owner, handle)
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        try:
            if json.loads(target.read_text(encoding="utf-8")).get("owner") == owner["owner"]:
                target.unlink()
        except (OSError, ValueError, AttributeError):
            pass


def _inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def _reparse(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def plan_local(state, config, *, generated_roots=(), runtime_roots=(), memory_roots=None, cursors=None):
    """Enumerate bounded directories, skip known paths before any body reading."""
    excluded = {str(name).casefold() for name in config.get("exclude_dir_names", [])}
    excluded.update({".git", ".codex", ".openclaw", ".lark-cli", ".obsidian", "__pycache__", "node_modules", ".venv"})
    roots = [dict(row, markdown_only=False) for row in config.get("watch_roots", [])]
    if config.get("obsidian_vault"):
        roots.append({"name": "Obsidian全库", "path": config["obsidian_vault"], "max_depth": None, "markdown_only": True})
    if memory_roots is None:
        memory_roots = config.get("memory_roots", [])
    roots.extend(dict(row, markdown_only=True) if isinstance(row, dict) else {"name": "提取记忆", "path": str(row), "markdown_only": True} for row in memory_roots)
    omit = [Path(p).resolve() for p in (*generated_roots, *runtime_roots,
            *config.get("generated_roots", []), *config.get("runtime_roots", []), *config.get("old_output_roots", []),
            *(config.get(k) for k in ("knowledge_root", "obsidian_run_dir", "runtime_root", "output_root", "data_root", "state_path") if config.get(k)))]
    if config.get("obsidian_vault"):
        routine = Path(config["obsidian_vault"]) / "04 例行工作"
        omit.extend(routine / name for name in ("文件管理助手", "知识行动助手", "知识整理助手"))
    found, warnings, sources, resume_cursors = {}, [], [], {}
    cursors = cursors or {}
    for row in roots:
        root = Path(os.path.expandvars(str(row["path"]))).expanduser().resolve()
        name, depth = row.get("name", root.name), row.get("max_depth")
        if depth is not None and (not isinstance(depth, int) or depth < 0):
            raise IncrementalError("扫描深度必须是非负整数。")
        limit = row.get("max_files")
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
            raise IncrementalError("每个来源的扫描上限必须是正整数。")
        cursor = cursors.get(path_key(root))
        after = None
        if cursor:
            relative = Path(cursor)
            if relative.is_absolute() or relative.drive or ".." in relative.parts or not relative.name:
                raise IncrementalError("扫描游标必须是来源内的相对文件路径。")
            after = (tuple(part.casefold() for part in relative.parts[:-1]), relative.name.casefold())
        if not root.is_dir():
            warnings.append(f"来源目录不可用：{root}")
            sources.append({"name": name, "path": str(root), "status": "unavailable"})
            continue
        errors, enumerated, last, capped = [], 0, None, False
        def failed(error):
            errors.append(str(error))
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=failed):
            current = Path(directory)
            if any(_inside(current, skip) for skip in omit):
                dirs[:] = []
                continue
            level = len(current.relative_to(root).parts)
            kept = []
            for child in dirs:
                target = current / child
                try:
                    if child.casefold() not in excluded and (depth is None or level < depth) and not _reparse(target) and not any(_inside(target, skip) for skip in omit):
                        kept.append(child)
                except OSError as error:
                    failed(error)
            dirs[:] = sorted(kept, key=str.casefold)
            for filename in sorted(files, key=str.casefold):
                target = current / filename
                if (filename.startswith("~$") or SENSITIVE_FILENAME.search(filename)
                        or row.get("markdown_only") and target.suffix.lower() != ".md"
                        or any(_inside(target, skip) for skip in omit)):
                    continue
                relative = target.relative_to(root)
                position = (tuple(part.casefold() for part in relative.parts[:-1]), filename.casefold())
                if after is not None and position <= after:
                    continue
                try:
                    if _reparse(target) or not target.is_file():
                        continue
                    identity = path_key(target)
                    modified_at = target.stat().st_mtime
                except OSError as error:
                    failed(error)
                    continue
                found.setdefault(identity, {"path": str(target.resolve()), "root": name,
                                            "modified_at": modified_at})
                enumerated += 1
                last = str(relative)
                if limit is not None and enumerated >= limit:
                    capped = True
                    break
            if capped:
                break
        source = {"name": name, "path": str(root), "status": "partial" if errors or capped else "checked",
                  "enumerated": enumerated, "max_files": limit, "coverage": "continued" if cursor else "from_start"}
        if capped:
            source["resume_cursor"] = last
            resume_cursors[path_key(root)] = last
            warnings.append(f"来源达到扫描上限 {limit}，可能仍有未覆盖文件：{root}")
        sources.append(source)
        warnings.extend(errors)
    files = [row for identity, row in found.items() if identity not in state["files"]]
    files.sort(key=lambda row: path_key(row["path"]))
    local_status = ("not_configured" if not sources else "unavailable" if all(row["status"] == "unavailable" for row in sources)
                    else "partial" if warnings else "checked")
    return {"files": files, "skipped": len(found) - len(files), "warnings": warnings,
            "source_status": {"local": local_status, "threads": "not_checked", "feishu": "not_checked"},
            "sources": sources, "resume_cursors": resume_cursors}


def thread_rows(data):
    if isinstance(data, list):
        return data
    return data.get("pinnedThreads", []) + data.get("threads", [])


def select_plan(state, files=None, threads=None, feishu=None, *, boundary=None, until=None):
    """Select additions without turning newly discovered old IDs into a replay.

    ``boundary`` must come from the accepted baseline manifest, never the largest
    per-thread timestamp. Historical gaps remain unacknowledged and unchanged.
    ``until`` is forwarded to turn selection: a later metadata update does not
    rule out earlier completed turns in that thread.
    """
    window = stamp(boundary) if boundary is not None else None
    if window is not None and window <= 0:
        raise IncrementalError("增量窗口必须使用已验收基线的完成时间。")
    ceiling = stamp(until) if until is not None else None
    if ceiling is not None and ceiling <= 0:
        raise IncrementalError("增量窗口上界必须是有效时间。")
    file_rows, doc_rows = list(files or []), list(feishu or [])
    new_files = list({path_key(r["path"]): r for r in file_rows if path_key(r["path"]) not in state["files"]}.values())
    new_docs = list({r["token"]: r for r in doc_rows if r["token"] not in state["feishu"]}.values())
    work, skipped, historical_gap, metadata_gap = [], 0, 0, 0
    unique = {}
    for row in thread_rows(threads or []):
        if row.get("kind", "codex") != "codex":
            continue
        previous = unique.get(row["id"])
        if previous is None or stamp(row.get("updatedAt")) >= stamp(previous.get("updatedAt")):
            unique[row["id"]] = row
    for item in unique.values():
        previous = state["threads"].get(item["id"])
        if previous is None and window is not None:
            updated = stamp(item.get("updatedAt"))
            if not updated:
                metadata_gap += 1
                skipped += 1
                continue
            if updated <= window:
                historical_gap += 1
                skipped += 1
                continue
        unchanged = previous and item.get("updatedAt") is not None and stamp(item["updatedAt"]) <= stamp(previous.get("updatedAt"))
        oversized = previous and str(previous.get("coverage", "")).startswith("partial_oversized")
        if unchanged and (not previous.get("pending") or oversized):
            skipped += 1
            continue
        planned = {**item, "action": "续聊检查" if previous else "新线程",
                   "after": previous.get("through", 0) if previous else window or 0}
        if ceiling is not None:
            planned["until"] = ceiling
        if previous is None and window is not None:
            planned["coverage"] = "increment_only"
        work.append(planned)
    warnings = []
    if historical_gap:
        warnings.append(f"{historical_gap} 个旧线程缺少逐条登记，保留为历史发现缺口，未读取历史正文。")
    if metadata_gap:
        warnings.append(f"{metadata_gap} 个未登记线程缺少更新时间，尚未检查其正文。")
    return {"files": new_files, "feishu": new_docs, "threads": work,
            "skipped": {"files": len(file_rows)-len(new_files), "feishu": len(doc_rows)-len(new_docs), "threads": skipped},
            "historical_gap": historical_gap, "metadata_gap": metadata_gap, "warnings": warnings,
            "source_status": {name: "not_checked" if value is None else "listed" for name, value in (("local", files), ("threads", threads), ("feishu", feishu))}}


def normalize_turn(turn):
    result = copy.deepcopy(turn)
    for field, alternate in (("id", "turnId"), ("startedAt", "started_at"), ("completedAt", "completed_at")):
        if field not in result and alternate in result:
            result[field] = result[alternate]
    status = result.get("status")
    if isinstance(status, dict):
        status = status.get("type", status.get("status"))
    result["status"] = "completed" if status in ("completed", "complete", "succeeded") else status
    return result


def turn_version(turn):
    return [turn.get("status"), stamp(turn.get("completedAt"))]


def _same_turn_version(previous, turn):
    if not isinstance(previous, (list, tuple)) or len(previous) != 2:
        return False
    try:
        status = normalize_turn({"status": previous[0]})["status"]
        return [status, stamp(previous[1])] == turn_version(turn)
    except (ValueError, TypeError):
        return False


def _valid_completed(turn):
    try:
        return bool(turn.get("id") and turn.get("status") == "completed" and stamp(turn.get("startedAt")) > 0 and stamp(turn.get("completedAt")) >= stamp(turn["startedAt"]))
    except (ValueError, TypeError):
        return False


def select_turns(state, thread_id, turns, *, after=None, until=None):
    previous = state["threads"].get(thread_id, {})
    seen = previous.get("turns", {})
    boundary = stamp(previous.get("through")) if thread_id in state["threads"] else stamp(after)
    ceiling = stamp(until) if until is not None else None
    if ceiling is not None and ceiling <= 0:
        raise IncrementalError("增量窗口上界必须是有效时间。")
    selected, pending = [], []
    emitted = set()
    for raw in turns:
        turn = normalize_turn(raw)
        if ceiling is not None:
            try:
                if stamp(turn.get("startedAt")) > ceiling or stamp(turn.get("completedAt")) > ceiling:
                    continue
            except (ValueError, TypeError):
                pending.append(turn)
                continue
        if not _valid_completed(turn):
            pending.append(turn)
            continue
        version = seen.get(turn["id"])
        if _same_turn_version(version, turn) or turn["id"] in emitted:
            continue
        if version is None and stamp(turn["startedAt"]) <= boundary and stamp(turn["completedAt"]) <= boundary:
            continue
        selected.append(turn)
        emitted.add(turn["id"])
    return {"turns": selected, "pending": pending}


class CheckpointStore:
    def __init__(self, state_path, receipt_dir=None, allowed_note_roots=()):
        self.path = Path(state_path)
        self.receipt_dir = Path(receipt_dir) if receipt_dir else self.path.parent / "receipts"
        self.allowed_note_roots = tuple(Path(p).resolve() for p in allowed_note_roots)

    def _verify(self, lane, item):
        note = Path(item["note"]).resolve()
        if self.allowed_note_roots and not any(_inside(note, root) for root in self.allowed_note_roots):
            raise IncrementalError("交付笔记不在允许写入目录中。")
        expected = item.get("expected_text")
        if not isinstance(expected, str) or not expected.strip():
            raise IncrementalError("登记必须附最终笔记 expected_text，以便实际读回。")
        if not note.is_file() or note.read_text(encoding="utf-8") != expected:
            raise IncrementalError("交付笔记读回不一致，不推进检查点。")
        if "\ufffd" in expected or "\x00" in expected:
            raise IncrementalError("交付笔记有编码异常，不推进检查点。")
        if lane in {"files", "feishu"} and item.get("check_only") and item.get("content_status") != "source_only":
            raise IncrementalError("来源仅检查回执必须明确标记未总结正文。")
        if lane == "threads":
            if item.get("check_only") and item.get("turns") and item.get("content_status") != "source_only":
                raise IncrementalError("仅检查回执登记新轮次必须明确为仅登记来源。")
            if item.get("coverage") == "increment_only" and not stamp(item.get("after")):
                raise IncrementalError("仅增量登记必须保留已验收的基线边界。")
            if any(not _valid_completed(normalize_turn(t)) for t in item.get("turns", [])):
                raise IncrementalError("运行中、失败或缺完成时间的轮次不能登记。")
            if item.get("complete") and item.get("pending"):
                raise IncrementalError("仍有未完成轮次，不能把线程登记为完整。")
            if item.get("complete") and not stamp(item.get("updatedAt")):
                raise IncrementalError("完整登记必须包含原生 updatedAt。")
        identity = path_key(item["path"]) if lane == "files" else item["token"] if lane == "feishu" else item["id"]
        if not identity or not isinstance(identity, str):
            raise IncrementalError("来源标识为空。")
        return identity

    def ack(self, receipt):
        """Commit each verified item independently; failed items never get acked.

        A prepared receipt precedes checkpoint replacement. If interrupted after
        the replacement, a retry preserves its receipt ID and completes delivery.
        Unknown v1 fields, historical references and partial coverage survive.
        """
        result = {"ok": True, "committed": [], "failed": []}
        with writer_lock(self.path.with_suffix(".lock")):
            state = load_state(self.path)
            for lane in ("files", "feishu", "threads"):
                for item in receipt.get(lane, []):
                    try:
                        identity = self._verify(lane, item)
                        candidate = copy.deepcopy(state)
                        previous = candidate[lane].setdefault(identity, {})
                        prior_receipts = previous.setdefault("receipts", [])
                        check_only = lane in {"files", "feishu", "threads"} and item.get("check_only")
                        note_field = "check_note" if check_only else "note"
                        note_path = str(Path(item["note"]).resolve())
                        prior = next((r for r in prior_receipts if r.get(note_field) == note_path), None)
                        receipt_id = prior["id"] if prior else str(uuid.uuid4())
                        record = {"id": receipt_id, "lane": lane, "source": identity, note_field: note_path,
                                  "verifiedAt": prior["verifiedAt"] if prior else datetime.now(timezone.utc).isoformat()}
                        if not prior:
                            prior_receipts.append(record)
                        if not check_only:
                            previous["note"] = note_path
                            if lane == "threads":
                                previous["content_status"] = "knowledge"
                        if check_only and item.get("content_status") == "source_only":
                            previous["check_note"] = note_path
                            previous["content_status"] = record["content_status"] = "source_only"
                        if lane == "files":
                            previous["path"] = item["path"]
                        elif lane == "feishu" and "updatedAt" in item:
                            previous["updatedAt"] = item["updatedAt"]
                        elif lane == "threads":
                            turns = [normalize_turn(t) for t in item.get("turns", [])]
                            previous.setdefault("turns", {}).update({t["id"]: turn_version(t) for t in turns})
                            if item.get("coverage") == "increment_only":
                                previous.setdefault("coverage", "increment_only")
                                previous.setdefault("incremental_boundary", stamp(item["after"]))
                                previous.setdefault("through", stamp(item["after"]))
                            previous.setdefault("through", 0)
                            previous["pending"] = bool(item.get("pending"))
                            if item.get("complete"):
                                previous["updatedAt"] = max(stamp(previous.get("updatedAt")), stamp(item["updatedAt"]))
                                previous["through"] = max(stamp(previous["through"]), max((stamp(t["startedAt"]) for t in turns), default=0))
                            if "title" in item:
                                previous["title"] = item["title"]
                            if item.get("source_type") in {"user", "automation"}:
                                previous["source_type"] = item["source_type"]
                        record_path = self.receipt_dir / f"{receipt_id}.json"
                        atomic_json(record_path, {**record, "status": "verified", "checkpoint_committed": False})
                        atomic_json(self.path, candidate)
                        state = candidate
                        result["committed"].append(record)
                        try:
                            atomic_json(record_path, {**record, "status": "committed", "checkpoint_committed": True})
                        except OSError as error:
                            # The checkpoint is already authoritative; retrying repairs this
                            # delivery marker without pretending the source was not acked.
                            result.setdefault("warnings", []).append({"receipt": receipt_id, "error": str(error), "checkpoint_committed": True})
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        result["failed"].append({"lane": lane, "source": item.get("path") or item.get("token") or item.get("id"), "error": str(error)})
                        result["ok"] = False
        return result
