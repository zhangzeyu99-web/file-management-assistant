"""Receive a service token privately over stdin; persist only DPAPI ciphertext."""
import argparse
import ctypes
import json
import os
import sys
from pathlib import Path
from engine.cloud import save_service_token
from engine.settings import load_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description="从标准输入读取服务令牌，不将令牌写入命令行或配置文件")
    parser.add_argument("--config", help="目标配置文件；也支持输入 JSON 中的 config 字段")
    args = parser.parse_args(argv)
    original = ctypes.c_ulong()
    handle = ctypes.windll.kernel32.GetStdHandle(-10) if os.name == "nt" else None
    console = bool(handle is not None and ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(original)))
    if console:
        ctypes.windll.kernel32.SetConsoleMode(handle, original.value & ~4)
    try:
        print("Ready for service configuration JSON on stdin (input is hidden).", flush=True)
        payload = json.loads(sys.stdin.readline())
        if not isinstance(payload, dict) or not isinstance(payload.get("token"), str) or not payload["token"].strip():
            raise ValueError("输入必须包含非空 token 字符串")
        cfg = load_settings(args.config or payload.get("config"))
        save_service_token(Path(cfg["data_root"]) / "service-token.dpapi", payload["token"])
        print('{"configured":true}')
    except (ValueError, OSError, RuntimeError) as error:
        print(f"服务配置失败：{error}", file=sys.stderr)
        return 2
    finally:
        if console:
            ctypes.windll.kernel32.SetConsoleMode(handle, original.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
