from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any


PATH_KEYS = {
    "runtime_root",
    "obsidian_vault",
    "obsidian_run_dir",
    "knowledge_root",
    "codex_executable",
    "feishu_helper",
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def expand_path_text(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value))


def expand_config_paths(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        return {key: expand_config_paths(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_config_paths(item, parent_key) for item in value]
    if isinstance(value, str) and (parent_key in PATH_KEYS or parent_key == "path"):
        return expand_path_text(value)
    return value


def local_override_path(config_path: Path) -> Path:
    return config_path.with_name("config.local.json")


def load_config(config_path: Path) -> dict[str, Any]:
    base = read_json(config_path)
    override = local_override_path(config_path)
    if config_path.name == "config.json" and override.exists():
        base = deep_merge(base, read_json(override))
    return expand_config_paths(base)
