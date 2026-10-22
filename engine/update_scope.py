"""Read-only candidate admission and explicit incremental update scope."""
from __future__ import annotations

from pathlib import Path

from .content_policy import source_only_reason


SCOPE = {"version": 1, "threads": "user", "files": "selected", "feishu": False}
_REPO_FILES = {"readme", "changelog", "agents", "claude", "contributing", "license", "acceptance",
               "plan", "project", "releasing", "handoff", "user_guide", "开发交接", "交接记录"}
_REPO_DIRS = {".git", "node_modules", "output", "dist", "build", ".next", "coverage", "iteration-logs"}


def selection_input(payload):
    if not isinstance(payload, dict):
        raise ValueError("任务输入必须是对象")
    if "selection" not in payload:
        return {"threads": None, "files": []}
    if payload.get("weekly_archive"):
        raise ValueError("周归档必须检查完整用户对话范围，不能用手选子集代表整周")
    selection = payload["selection"]
    if not isinstance(selection, dict) or set(selection) != {"threads", "files"}:
        raise ValueError("所选范围须包含 threads 与 files 数组")
    result = {}
    for key in ("threads", "files"):
        values = selection[key]
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("所选范围必须是非空字符串数组")
        if key == "files" and any(not Path(value).is_absolute() for value in values):
            raise ValueError("所选文件必须是允许目录内的绝对路径")
        result[key] = list(dict.fromkeys(values))
    return result


def candidate_file_reason(filename, config):
    """Metadata-only exclusion for discovery, never a judgment of pasted prose."""
    path = Path(filename).resolve()
    vault = Path(config["obsidian_vault"]).resolve()
    if path.is_relative_to(vault):
        return "已有知识库笔记，不重复归档"
    reason = source_only_reason(path)
    if reason:
        return reason
    if path.stat().st_size == 0:
        return "空文件，没有可归档正文"
    # Exact repository-document names only, with an actual repository ancestor.
    # A standalone 方法说明.md remains selectable regardless of its title.
    repo = next((parent for parent in path.parents if (parent / ".git").exists()), None)
    if repo is not None:
        relative = path.relative_to(repo)
        if (path.stem.casefold() in _REPO_FILES or
                any(part.casefold() in _REPO_DIRS for part in relative.parts[:-1])):
            return "仓库说明、交接或运行产物，不自动归档"
    return None
