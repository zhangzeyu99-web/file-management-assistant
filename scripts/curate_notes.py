"""Merge or retire explicitly selected notes using a private reviewed plan.

No source discovery or model calls occur here. Original task outputs remain
byte-for-byte available for exact retries; reading aliases resolve the merged
topic or each retired original.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.incremental import atomic_json, load_state, path_key, writer_lock
from engine.settings import load_settings


class CurationError(ValueError):
    pass


CONFIG_PATHS = ("obsidian_vault", "data_root", "state_path", "output_root")
NOTE_FIELDS = {"note", "check_note"}


def _safe(path):
    path = Path(path).absolute()
    for node in (path, *path.parents):
        if node.is_symlink() or (node.exists() and
                bool(getattr(node.lstat(), "st_file_attributes", 0) & 0x400)):
            raise CurationError("不跟随符号链接或重解析路径：" + str(node))
    return path.resolve()


def _relative(value):
    if not isinstance(value, str):
        raise CurationError("笔记路径必须是知识库相对 Markdown 路径。")
    pure = PurePosixPath(value)
    if (not value or pure.is_absolute() or pure.as_posix() != value or
            "\\" in value or ":" in value or pure.suffix.lower() != ".md" or
            any(p in {".", ".."} or p.startswith(".") for p in pure.parts)):
        raise CurationError("只接受日常知识区的相对 Markdown 路径：" + value)
    return pure.as_posix()


def _config(config):
    result = {key: str(_safe(config[key])) for key in CONFIG_PATHS}
    vault, output = Path(result["obsidian_vault"]), Path(result["output_root"])
    if not vault.is_dir() or not Path(result["data_root"]).is_dir() or not output.is_relative_to(vault):
        raise CurationError("知识库、运行目录或生成目录配置无效。")
    load_state(result["state_path"])
    return result


def _selection(target, sources):
    target = _relative(target)
    sources = _sources(sources)
    if target in sources:
        raise CurationError("至少指定一篇不同于目标的原笔记，不能重复选择。")
    return target, sources


def _sources(sources):
    sources = [_relative(source) for source in sources]
    if not sources or len(set(sources)) != len(sources):
        raise CurationError("至少指定一篇原笔记，不能重复选择。")
    return sources


def _snapshot(path):
    path = _safe(path)
    if not path.exists():
        return {"exists": False}
    if not path.is_file():
        raise CurationError("预期文件却发现目录：" + str(path))
    before = path.stat()
    content = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise CurationError("读取时文件发生变化：" + str(path))
    return {"exists": True, "content": base64.b64encode(content).decode("ascii"),
            "mtime_ns": after.st_mtime_ns, "mode": after.st_mode & 0o777}


def _bytes(snapshot):
    try:
        return base64.b64decode(snapshot["content"], validate=True)
    except (KeyError, ValueError, TypeError) as error:
        raise CurationError("计划中的原文快照无效。") from error


def _json(snapshot, fallback):
    if not snapshot["exists"]:
        return fallback
    value = json.loads(_bytes(snapshot).decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise CurationError("管理记录必须是 JSON 对象。")
    return value


def _remap(value, paths):
    """Move delivery references only; source identities and turn data stay intact."""
    if isinstance(value, list):
        return [_remap(item, paths) for item in value]
    if isinstance(value, dict):
        return {key: paths.get(path_key(item), item)
                if key in NOTE_FIELDS and isinstance(item, str) else _remap(item, paths)
                for key, item in value.items()}
    return value


def _capture(config, target, sources, additions=()):
    vault, data = Path(config["obsidian_vault"]), Path(config["data_root"])
    selected = [vault / relative for relative in ([target] if target is not None else []) + sources + list(additions)]
    if len({path_key(path) for path in selected}) != len(selected):
        raise CurationError("所选路径指向同一笔记，不能重复合并。")
    note_paths = {path_key(path): str(path) for path in selected}
    files = {str(_safe(path)): _snapshot(path) for path in selected}
    if any(not files[str(vault / source)]["exists"] for source in sources):
        raise CurationError("原笔记不存在；未合并或重建。")
    metadata = [vault / ".obsidian/knowledge-layout.json",
                Path(config["output_root"]) / ".note-index.json", Path(config["state_path"])]
    receipt_dir = _safe(data / "receipts")
    if receipt_dir.exists():
        for path in sorted(receipt_dir.glob("*.json")):
            current = _snapshot(path)
            value = _json(current, {})
            if _remap(value, dict.fromkeys(note_paths, "__selected_note__")) != value:
                metadata.append(path)
    files.update({str(_safe(path)): _snapshot(path) for path in metadata})
    layout = _json(files[str(vault / ".obsidian/knowledge-layout.json")], {"version": 1, "path_aliases": {}})
    index = _json(files[str(Path(config["output_root"]) / ".note-index.json")], {"version": 1, "tasks": {}})
    if (layout.get("version") != 1 or not isinstance(layout.get("path_aliases", {}), dict) or
            index.get("version") != 1 or not isinstance(index.get("tasks"), dict)):
        raise CurationError("现有别名或任务身份记录无效；未重建空记录。")
    for task, entry in index["tasks"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise CurationError("任务身份记录无效：" + str(task))
    reserved = {str(relative).casefold() for relative in layout.get("path_aliases", {})}
    reserved.update(entry["path"].casefold() for entry in index["tasks"].values())
    if any(relative.casefold() in reserved for relative in additions):
        raise CurationError("新增稿目标已关联旧入口或任务身份，未覆盖。")
    return files


def plan_merge(config, target, sources, destination=None, *, retire=False, additions=None):
    config = _config(config)
    added = _reviewed_additions(additions)
    if added and not retire:
        raise CurationError("新增复核稿只用于移出旧笔记的计划；合并请提供目标正文。")
    if retire:
        if target is not None:
            raise CurationError("仅移出知识区的计划不能包含目标主题。")
        target, sources = None, _sources(sources)
    else:
        target, sources = _selection(target, sources)
    operation = str(uuid.uuid4())
    files = _capture(config, target, sources, added)
    if any(files[str(Path(config["obsidian_vault"]) / relative)]["exists"] for relative in added):
        raise CurationError("新增稿目标已存在，不能覆盖现有笔记。")
    plan = {"version": 1, "id": operation, "created_at": datetime.now(timezone.utc).isoformat(),
            "config": config, "sources": sources,
            "files": files}
    plan.update({"mode": "retire"} if retire else {"target": target})
    if added:
        plan["additions"] = {relative: content.decode("utf-8") for relative, content in added.items()}
    destination = _safe(destination or Path(config["data_root"]) / "curation/plans" / (operation + ".json"))
    if destination.is_relative_to(Path(config["obsidian_vault"])):
        raise CurationError("计划含完整原文，请存入知识库外的私有运行目录。")
    _new_json(destination, plan)
    return {"ok": True, "plan_path": str(destination), **({"mode": "retire"} if retire else {"canonical": target}),
            **({"added_notes": list(added)} if added else {}),
            "sources": sources, "requires_stopped_executor": True}


def plan_retire(config, sources, destination=None, additions=None):
    return plan_merge(config, None, sources, destination, retire=True, additions=additions)


def _new_json(path, value):
    path = _safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    if path.read_bytes() != content:
        raise CurationError("私有备份读回不一致。")


def _write_bytes(path, content):
    path = _safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".curation-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if Path(temporary).read_bytes() != content:
            raise CurationError("临时文件读回不一致。")
        os.replace(temporary, path)
        if path.read_bytes() != content:
            raise CurationError("写入后读回不一致。")
    finally:
        Path(temporary).unlink(missing_ok=True)


def _json_bytes(value, previous):
    old = _bytes(previous) if previous["exists"] else b""
    encoding = "utf-8-sig" if old.startswith(b"\xef\xbb\xbf") else "utf-8"
    newline = "\r\n" if b"\r\n" in old else "\n"
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").replace("\n", newline).encode(encoding)


def _reviewed_content(path):
    snapshot = _snapshot(path)
    if not snapshot["exists"]:
        raise CurationError("已复核的最终 Markdown 不存在。")
    return _validated_content(_bytes(snapshot))


def _validated_content(content):
    text = content.decode("utf-8-sig")
    title = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    if not title or "\x00" in text or "\ufffd" in text:
        raise CurationError("最终正文缺少标题或包含编码异常。")
    if re.search(r"<!--\s*obsidian-workspace task:", text):
        raise CurationError("最终主题正文不能复制任务身份；全部原身份会保留在历史原文。")
    try:
        from engine.content_policy import validate_note
    except ImportError as error:
        raise CurationError("内容质量检查模块尚未就绪，未执行合并。") from error
    result = validate_note(title.group(1), text)
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise CurationError("最终正文未通过质量检查：" + json.dumps(result, ensure_ascii=False))
    return content


def _reviewed_additions(additions):
    if additions is None:
        return {}
    if not isinstance(additions, dict):
        raise CurationError("新增稿必须是库内路径到已复核 Markdown 的映射。")
    result = {}
    for relative, markdown in additions.items():
        relative = _relative(relative)
        if not isinstance(markdown, str):
            raise CurationError("新增稿必须提供已复核的 Markdown 正文。")
        result[relative] = _validated_content(markdown.encode("utf-8"))
    return result


def _rollback(files, archives, backup, mutated):
    # Retain any already-moved originals outside the vault; never discard them.
    for archived in archives:
        path = Path(archived)
        if path.exists():
            recovered = backup / "recovered-originals" / path.relative_to(Path(archives[archived]))
            recovered.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, recovered)
    for path, before in files.items():
        if path not in mutated:
            continue  # In particular, retain a manual edit detected before our write.
        target = _safe(path)
        if before["exists"]:
            _write_bytes(target, _bytes(before))
            os.chmod(target, before["mode"])
            os.utime(target, ns=(before["mtime_ns"], before["mtime_ns"]))
        elif target.exists():
            target.unlink()  # Only a newly-created canonical/management file.


def apply_plan(config, plan_path, content_path=None):
    config = _config(config)
    plan_path = _safe(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    if (not isinstance(plan, dict) or plan.get("version") != 1 or plan.get("config") != config or
            not re.fullmatch(r"[a-f0-9-]{36}", plan.get("id", "")) or
            plan.get("mode", "merge") not in {"merge", "retire"}):
        raise CurationError("计划不属于当前配置或版本无效。")
    retiring = plan.get("mode") == "retire"
    added = _reviewed_additions(plan.get("additions"))
    if added and not retiring:
        raise CurationError("合并计划不能附加新增稿。")
    operation = "移出知识区" if retiring else "合并"
    if retiring:
        if plan.get("target") is not None:
            raise CurationError("仅移出知识区的计划不能包含目标主题。")
        if content_path is not None:
            raise CurationError("仅移出知识区不接受替代正文。")
        target, sources, content = None, _sources(plan["sources"]), None
    else:
        target, sources = _selection(plan["target"], plan["sources"])
        if content_path is None:
            raise CurationError("合并主题需要已复核的最终正文。")
        content = _reviewed_content(_safe(content_path))
    selected = ([target] if target is not None else []) + sources
    vault, data = Path(config["obsidian_vault"]), Path(config["data_root"])
    new_notes = {str(vault / relative): content for relative, content in added.items()}
    backup = _safe(data / "curation" / plan["id"])
    if backup.is_relative_to(vault):
        raise CurationError("备份目录必须位于知识库外。")
    with ExitStack() as locks:
        for path in (data / "executor.lock", Path(config["state_path"]).with_suffix(".lock"),
                     Path(config["output_root"]) / ".write.lock"):
            locks.enter_context(writer_lock(path))
        result_path = backup / "result.json"
        if result_path.exists():
            saved = json.loads(result_path.read_text(encoding="utf-8-sig"))
            if not isinstance(saved, dict) or saved.get("status") != "committed" or saved.get("plan") != plan:
                raise CurationError("此计划已有未完成或不同的事务，保留备份供恢复。")
            if any(_snapshot(path).get("content") != expected for path, expected in saved["after"].items()):
                raise CurationError(operation + "后文件已有改动，未重跑覆盖。")
            if any((vault / source).exists() for source in sources):
                raise CurationError("原位置已有新笔记，未把它当作已完成合并。")
            if not retiring and _snapshot(vault / target).get("content") != base64.b64encode(content).decode("ascii"):
                raise CurationError("此次复核正文与已完成合并不同，需另建计划。")
            return {**saved["result"], "reused": True}
        if backup.exists():
            raise CurationError("存在未完成事务备份，请先恢复或另建计划：" + str(backup))
        current = _capture(config, target, sources, added)
        if any(current[path]["exists"] for path in new_notes):
            raise CurationError("新增稿目标已存在或在计划后出现，未覆盖。")
        if current != plan.get("files"):
            raise CurationError("原文或关联管理记录在计划后发生变化，请重新生成计划。")
        _new_json(backup / "backup.json", plan)
        # Recheck after backup publication, before any production mutation.
        if _capture(config, target, sources, added) != current:
            raise CurationError("备份期间资料发生变化，未执行合并。")
        histories = {}
        for relative in selected:
            if current[str(vault / relative)]["exists"]:
                kind = "target" if relative == target else "sources"
                histories[relative] = f".source-history/curation/{plan['id']}/{kind}/{relative}"
        paths = {path_key(vault / old): str(vault / new) for old, new in histories.items()}
        alias_path = str(vault / ".obsidian/knowledge-layout.json")
        index_path = str(Path(config["output_root"]) / ".note-index.json")
        layout = _json(current[alias_path], {"version": 1, "path_aliases": {}})
        aliases = layout.setdefault("path_aliases", {})
        aliases.update({relative: histories[relative] if retiring else target for relative in sources})
        aliases.update({history: history for history in histories.values()})
        index = _json(current[index_path], {"version": 1, "tasks": {}})
        for entry in index["tasks"].values():
            if entry["path"] in histories:
                entry["path"] = histories[entry["path"]]
        replacements = {alias_path: _json_bytes(layout, current[alias_path]),
                        index_path: _json_bytes(index, current[index_path])}
        if not retiring:
            replacements[str(vault / target)] = content
        for path, before in current.items():
            if path not in {str(vault / relative) for relative in selected} and path not in replacements and path not in new_notes:
                value = _json(before, {})
                updated = _remap(value, paths)
                if value != updated:
                    replacements[path] = _json_bytes(updated, before)
        archives = {}
        mutated = set()
        try:
            # Publish reviewed additions first. Exclusive creation never replaces
            # a note that appeared after capture, including between this check and open.
            for path, value in new_notes.items():
                if _snapshot(path) != current[path]:
                    raise CurationError("新增稿目标在计划后出现，未覆盖。")
                destination = _safe(path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as handle:
                    mutated.add(path)
                    handle.write(value)
                    handle.flush()
                    os.fsync(handle.fileno())
                if destination.read_bytes() != value:
                    raise CurationError("新增稿读回不一致。")
            for relative, history in histories.items():
                archived = _safe(vault / history)
                if not archived.is_relative_to(vault / ".source-history/curation" / plan["id"]) or archived.exists():
                    raise CurationError("历史原文目标异常，未覆盖。")
                archived.parent.mkdir(parents=True, exist_ok=True)
                archives[str(archived)] = str(vault / ".source-history/curation" / plan["id"])
                original = vault / relative
                if _snapshot(original) != current[str(original)]:
                    raise CurationError("执行合并前原文再次发生变化，已停止写入。")
                if relative == target:
                    _write_bytes(archived, _bytes(current[str(original)]))
                else:
                    mutated.add(str(original))
                    os.replace(original, archived)
                if archived.read_bytes() != _bytes(current[str(original)]):
                    raise CurationError("历史原文读回不一致。")
            for path, value in replacements.items():
                if _snapshot(path) != current[path]:
                    raise CurationError("执行合并前正文或管理记录再次发生变化，已停止写入。")
                mutated.add(path)
                _write_bytes(path, value)
            for path, value in {**new_notes, **replacements}.items():
                if Path(path).read_bytes() != value:
                    raise CurationError("合并结果读回不一致。")
            result = {"ok": True, **({"mode": "retire"} if retiring else {"canonical": target}), "backup_path": str(backup / "backup.json"),
                      **({"added_notes": list(added)} if added else {}),
                      "retired_originals": histories, "reused": False}
            after = {path: base64.b64encode(Path(path).read_bytes()).decode("ascii")
                     for path in [*new_notes, *replacements, *archives]}
            _new_json(result_path, {"version": 1, "status": "committed", "plan": plan,
                                    "result": result, "after": after})
            return result
        except Exception as error:
            try:
                _rollback(current, archives, backup, mutated)
                if result_path.exists():
                    atomic_json(result_path, {"status": "rolled_back"})
                atomic_json(backup / "rollback.json", {"status": "restored", "error": type(error).__name__})
            except Exception as recovery:
                raise CurationError(operation + "失败且自动恢复未完成，原文备份保留于：" + str(backup)) from recovery
            raise CurationError(operation + "失败，已恢复原文和管理记录；备份保留于：" + str(backup)) from error


def apply_merge(config, plan_path, content_path):
    return apply_plan(config, plan_path, content_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="按已复核计划合并或移出指定笔记，保留历史原文与增量身份")
    parser.add_argument("--config")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    mode = plan.add_mutually_exclusive_group(required=True)
    mode.add_argument("--target")
    mode.add_argument("--retire", action="store_true")
    plan.add_argument("--source", action="append", required=True)
    plan.add_argument("--plan-out")
    apply = commands.add_parser("apply")
    apply.add_argument("--plan", required=True)
    apply.add_argument("--content")
    args = parser.parse_args(argv)
    try:
        config = load_settings(args.config)
        result = (plan_retire(config, args.source, args.plan_out) if args.command == "plan" and args.retire
                  else plan_merge(config, args.target, args.source, args.plan_out) if args.command == "plan"
                  else apply_plan(config, args.plan, args.content))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
