"""Package tracked working-tree source; never include local libraries or secrets."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    "README.md", "USER_GUIDE.md", "PROJECT.md", "CONTRIBUTING.md", "ACCEPTANCE.md", "AGENTS.md", "CHANGELOG.md", "LICENSE", "VERSION",
    "requirements.txt", "config.example.json", "configure-service.py", "server.py",
    "launch.ps1", "start.ps1", "stop.ps1", "打开工作台.cmd", ".gitattributes", ".gitignore",
}
SOURCE_DIRS = {"engine", "bridge", "scripts", "tests", "docs", ".github", "web"}
OMIT_DIRS = {".git", "node_modules", "__pycache__", ".venv", "output", ".migration-staging", ".next", ".vinext",
             "dist", ".wrangler", ".sites-runtime", ".agents", ".codex", "uploads", "runtime", "receipts",
             "data", "vault", "knowledge", "obsidian-work", "obsidian-workspace-data"}
OMIT_SUFFIXES = {".pyc", ".pyo", ".dpapi", ".sqlite", ".sqlite3", ".db", ".log", ".tsbuildinfo", ".zip", ".jsonl",
                 ".pem", ".key", ".p12", ".pfx"}
REQUIRED = {"打开工作台.cmd", "launch.ps1", "start.ps1", "server.py", "engine/settings.py", "config.example.json",
            "requirements.txt", "web/package.json", "web/package-lock.json"}


def _allowed(name):
    path = PurePosixPath(name)
    if (not name or "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts
            or name != path.as_posix()):
        raise ValueError("打包路径必须是仓库内的规范相对路径：" + name)
    if path.parts[0] not in SOURCE_DIRS and name not in ROOT_FILES:
        return False
    if any(part.casefold() in OMIT_DIRS or part.startswith(".sites-checkout") for part in path.parts):
        return False
    lower = path.name.casefold()
    if (lower.startswith((".env", ".dev.vars")) or lower.endswith(".local.json")
            or lower in {".workspace-active.json", "hosting.local.json", "weekly-active.json", "weekly-archive.json",
                         "config.json", "state.json", "auth.json", "credentials.json", "secrets.json", "tokens.json"}
            or path.suffix.casefold() in OMIT_SUFFIXES):
        return False
    return True


def _tracked(root):
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True)
    return [os.fsdecode(value) for value in result.stdout.split(b"\0") if value]


def package_release(project_root, output, *, include=()):
    root = Path(project_root).resolve()
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise ValueError("发行包已存在，未覆盖：" + str(output))
    names = set()
    for name in _tracked(root):
        if _allowed(name) and (root / name).exists():  # Respect pending tracked deletions.
            names.add(name)
    for name in include:
        if not _allowed(name):
            raise ValueError("显式包含的文件不在公开源码范围：" + name)
        names.add(name)
    if missing := REQUIRED - names:
        raise ValueError("启动包缺少必要源码：" + ", ".join(sorted(missing)))
    paths = {}
    for name in sorted(names):
        path = root.joinpath(*PurePosixPath(name).parts)
        for part in (path, *path.parents):
            if part == root:
                break
            info = part.lstat()
            if part.is_symlink() or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                raise ValueError("启动包不接受链接或目录联接：" + name)
        if not path.is_file() or not path.resolve().is_relative_to(root) or path.resolve() == output:
            raise ValueError("启动包只能包含仓库中的普通源码文件：" + name)
        paths[name] = path
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + output.name + ".", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary)
    try:
        snapshots = {}
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
            for name, path in paths.items():
                before = path.stat()
                archive.write(path, name)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("源码在打包期间变化，请完成修改后重试：" + name)
                snapshots[path] = (after.st_size, after.st_mtime_ns)
        if any((path.stat().st_size, path.stat().st_mtime_ns) != value for path, value in snapshots.items()):
            raise ValueError("源码在打包期间变化，请完成修改后重试。")
        # rename on Windows refuses an existing output; do not overwrite another release.
        if output.exists():
            raise ValueError("发行包已出现，未覆盖：" + str(output))
        temporary.rename(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"ok": True, "output": str(output), "files": len(paths)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="从 Git 跟踪的当前源码生成 Windows 启动 ZIP，不含个人资料")
    parser.add_argument("--output", required=True)
    parser.add_argument("--include", action="append", default=[], help="额外包含尚未暂存的公开源码相对路径，可重复")
    args = parser.parse_args(argv)
    try:
        result = package_release(ROOT, args.output, include=args.include)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("启动包未生成：" + str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
