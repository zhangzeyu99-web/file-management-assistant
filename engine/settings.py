"""Explicit portable configuration; never bind a new checkout to another PC."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH_FIELDS = ("data_root", "state_path", "obsidian_vault", "output_root",
               "runtime_root", "knowledge_root", "obsidian_run_dir", "codex_executable")
ROOT_LISTS = ("old_output_roots", "generated_roots", "runtime_roots", "allowed_open_roots")


def _read_config(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ValueError(f"配置文件不存在：{path}") from None
    except (OSError, UnicodeError) as error:
        raise ValueError(f"无法读取配置文件 {path}：{error}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"配置 JSON 无效：{path}，第 {error.lineno} 行") from None
    if not isinstance(value, dict):
        raise ValueError(f"配置必须是 JSON 对象：{path}")
    return value


def _path(value, base, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"配置 {field} 必须是非空路径")
    expanded = os.path.expandvars(value)
    if re.search(r"%[A-Za-z_][A-Za-z0-9_]*%|\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*", expanded):
        raise ValueError(f"配置 {field} 包含未定义的环境变量")
    target = Path(expanded).expanduser()
    return str((target if target.is_absolute() else base / target).resolve())


def _port(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError(f"配置 {field} 必须是 1 到 65535 的整数端口")
    return value


def load_settings(path=None, *, api_port=None, web_port=None):
    """Explicit path, browser-selected workspace, local config, then environment."""
    local = ROOT / "config.local.json"
    active = ROOT / ".workspace-active.json"
    if path:
        selected, source = Path(_path(str(path), Path.cwd(), "Config")), "explicit"
    elif active.is_file():
        selected, source = Path(_path(_read_config(active).get("config"), ROOT, "active.config")), "selected"
    elif local.is_file():
        selected, source = local.resolve(), "project"
    elif os.environ.get("OW_CONFIG"):
        selected, source = Path(_path(os.environ["OW_CONFIG"], Path.cwd(), "OW_CONFIG")), "environment"
    else:
        raise ValueError("未找到配置。请导入迁移包，或显式运行 scripts/setup_workspace.py 创建全新库；"
                         "也可使用 -Config / --config / OW_CONFIG 指定已有配置；不会自动初始化空检查点。")
    result = _read_config(selected)
    base = selected.parent
    for key in PATH_FIELDS[:4]:
        if key not in result:
            raise ValueError(f"缺少配置：{key}")
    for key in PATH_FIELDS:
        if key in result:
            result[key] = _path(result[key], base, key)
    for key in ROOT_LISTS:
        values = result.setdefault(key, [])
        if not isinstance(values, list):
            raise ValueError(f"配置 {key} 必须是路径列表")
        result[key] = [_path(value, base, f"{key}[{index}]") for index, value in enumerate(values)]
    for key in ("watch_roots", "memory_roots"):
        values = result.setdefault(key, [])
        if not isinstance(values, list):
            raise ValueError(f"配置 {key} 必须是来源列表")
        normalized = []
        for index, value in enumerate(values):
            field = f"{key}[{index}]"
            if isinstance(value, dict):
                normalized.append({**value, "path": _path(value.get("path"), base, field + ".path")})
            elif key == "memory_roots":
                normalized.append(_path(value, base, field))
            else:
                raise ValueError(f"配置 {field} 必须是包含 path 的对象")
        result[key] = normalized
    data_root, vault = Path(result["data_root"]), Path(result["obsidian_vault"])
    if data_root.is_relative_to(vault) or vault.is_relative_to(data_root):
        raise ValueError("配置 data_root 与 obsidian_vault 必须互不包含，避免私有运行记录进入知识库")
    if not Path(result["output_root"]).is_relative_to(vault):
        raise ValueError("配置 output_root 必须位于 obsidian_vault 内")
    result["port"] = _port(api_port if api_port is not None else result.get("port", 8767), "port")
    result["web_port"] = _port(web_port if web_port is not None else result.get("web_port", 5174), "web_port")
    if result["port"] == result["web_port"]:
        raise ValueError("API 端口和 Web 端口不能相同")
    result.setdefault("cloud_url", "")
    result["_config_path"] = str(selected) if selected else ""
    result["_config_source"] = source
    return result


def validate_startup(config):
    from .incremental import load_state
    load_state(config["state_path"])
    if not Path(config["obsidian_vault"]).is_dir():
        raise ValueError("Obsidian 目录不存在；请先完成资料迁移或修改 obsidian_vault")


def main(argv=None):
    parser = argparse.ArgumentParser(description="只读解析启动配置，不创建检查点或启动服务")
    parser.add_argument("--config")
    parser.add_argument("--api-port", type=int)
    parser.add_argument("--web-port", type=int)
    parser.add_argument("--check-startup", action="store_true")
    parser.add_argument("--allow-setup", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_settings(args.config, api_port=args.api_port, web_port=args.web_port)
        if args.check_startup:
            validate_startup(config)
        summary = {key: config[key] for key in ("data_root", "state_path", "obsidian_vault", "output_root", "port", "web_port")}
        summary.update(config_path=config["_config_path"], config_source=config["_config_source"])
        print(json.dumps(summary))
    except (ValueError, OSError) as error:
        if args.allow_setup and not args.config and str(error).startswith("未找到配置"):
            api_port = args.api_port if args.api_port is not None else 8767
            web_port = args.web_port if args.web_port is not None else 5174
            if not 1 <= api_port <= 65535 or not 1 <= web_port <= 65535 or api_port == web_port:
                print("启动配置错误：API 与 Web 必须使用不同的有效端口。", file=sys.stderr)
                return 2
            print(json.dumps({"data_root": str(ROOT / ".migration-staging"), "port": api_port,
                              "web_port": web_port, "config_path": "", "config_source": "setup",
                              "setup_required": True}))
            return 0
        print(f"启动配置错误：{error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
