"""Explicitly create a new, empty workspace; existing libraries use migration."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.settings import load_settings, validate_startup


FOLDERS = ("00 入口", "10 项目", "20 方法", "30 资料", "90 历史", ".source-history")


def _target(value, base):
    path = Path(os.path.expandvars(str(value))).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def _relative(path, base):
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:  # Explicit choices on separate Windows drives.
        return str(path)


def setup_workspace(config_path, *, vault=None, data_root=None, now=None):
    """The explicit CLI/function is the only permission to create an empty v1 state."""
    config_path = _target(config_path, Path.cwd())
    base = config_path.parent
    vault = _target(vault or "../Obsidian-Work", base)
    data_root = _target(data_root or "../obsidian-workspace-data", base)
    state_path = data_root / "checkpoint/state.json"
    if config_path.exists() or state_path.exists():
        raise ValueError("配置或检查点已存在，未覆盖；已有知识库请使用迁移入口。")
    if (vault.is_relative_to(data_root) or data_root.is_relative_to(vault)
            or config_path.is_relative_to(vault) or config_path.is_relative_to(data_root)):
        raise ValueError("知识库、运行数据和配置文件须使用互不重叠的位置。")
    for path in (vault, data_root):
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise ValueError("新库目录必须为空，未修改已有资料：" + str(path))
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("新库基线时间必须包含时区。")
    state = {"version": 1, "baseline_at": current.astimezone(timezone.utc).isoformat(),
             "baseline_kind": "explicit_empty_workspace", "files": {}, "threads": {}, "feishu": {}}
    config = {
        "data_root": _relative(data_root, base), "state_path": _relative(state_path, base),
        "obsidian_vault": _relative(vault, base), "output_root": _relative(vault / "30 资料", base),
        "old_output_roots": [], "watch_roots": [], "memory_roots": [],
        "generated_roots": [_relative(vault / name, base) for name in FOLDERS],
        "runtime_roots": [],
        "exclude_dir_names": [".git", ".obsidian", ".codex", ".openclaw", "node_modules", "__pycache__", ".venv"],
        "cloud_url": "", "feishu_enabled": False, "feishu_video_owner": "",
        "port": 8767, "web_port": 5174,
    }
    created_dirs, created_files = [], {}

    def mkdir(path):
        missing = []
        while not path.exists():
            missing.append(path)
            path = path.parent
        for directory in reversed(missing):
            directory.mkdir()
            created_dirs.append(directory)

    def write(path, value):
        content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with path.open("xb") as handle:
            created_files[path] = content
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.read_bytes() != content:
            raise ValueError("初始化文件读回不一致：" + str(path))

    try:
        for folder in FOLDERS:
            mkdir(vault / folder)
        mkdir(vault / ".obsidian")
        mkdir(state_path.parent)
        mkdir(base)
        write(vault / ".obsidian/knowledge-layout.json", {"version": 1, "navigation": True, "path_aliases": {}})
        write(state_path, state)
        # The configuration becomes usable only after the checkpoint exists.
        write(config_path, config)
        validate_startup(load_settings(config_path))
    except Exception:
        for path, expected in reversed(list(created_files.items())):
            if path.is_file() and path.read_bytes() == expected:
                path.unlink()
        for path in reversed(created_dirs):
            try:
                path.rmdir()
            except OSError:
                pass
        raise
    return {"ok": True, "config": str(config_path), "vault": str(vault), "state_path": str(state_path),
            "baseline_at": state["baseline_at"], "sources": "empty", "feishu_enabled": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="显式创建全新空知识库；已有知识库请导入迁移包")
    parser.add_argument("--config", default=str(ROOT / "config.local.json"))
    parser.add_argument("--vault", help="空知识库目录；相对路径按配置文件目录解释")
    parser.add_argument("--data-root", help="空运行目录；相对路径按配置文件目录解释")
    args = parser.parse_args(argv)
    try:
        result = setup_workspace(args.config, vault=args.vault, data_root=args.data_root)
    except (OSError, ValueError) as error:
        print("新库未创建：" + str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
