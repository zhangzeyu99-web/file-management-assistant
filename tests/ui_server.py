"""Isolated UI server: real model, deterministic native/Feishu fixtures.

Run `py -3 -X utf8 tests/ui_server.py --prepare` once to create the fixture.
Run without --prepare to serve its config; this never uses personal sources.
"""
import argparse
import json
import sys
import tempfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge import CodexModel
from engine.incremental import load_state
from engine.runtime import Runtime
from engine.settings import load_settings
from server import make_handler
from test_runtime import FakeFeishu, FakeNative, UPLOAD_TEXT, fixture, page, turn

CONFIG = ROOT / "output" / "phase0" / "config.json"
THREAD_ID = "00000000-0000-4000-8000-000000000001"


def native_fixture():
    return FakeNative(
        [{"id": THREAD_ID, "kind": "codex", "updatedAt": 200, "title": "热血测试续聊"}],
        {THREAD_ID: page([
            turn("fixture-new", 100, 180, "新增已完成事实：验收清单已补入角色重名校验；分服活跃数据仍待补齐。"),
            turn("fixture-old", 60, 80, "旧计划已经整理，不能再记为本次新成果。"),
        ])},
    )


def prepare():
    if CONFIG.exists():
        return load_settings(CONFIG)
    root = Path(tempfile.mkdtemp(prefix="obsidian-workspace-phase0-"))
    runtime, _, _ = fixture(root)
    state = load_state(runtime.cfg["state_path"])
    state["threads"][THREAD_ID] = {"updatedAt": 100, "through": 90,
        "turns": {"fixture-old": ["completed", 80]}, "note": str(root / "vault" / "热血测试方案.md")}
    Path(runtime.cfg["state_path"]).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "sources" / "热血新增测试.txt").write_text(
        "热血增量测试资料：新增决定，测试服角色映射表保存七天；本轮未实施合服。", encoding="utf-8")
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    (CONFIG.parent / "待上传资料.txt").write_text(UPLOAD_TEXT, encoding="utf-8")
    CONFIG.write_text(json.dumps(runtime.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return runtime.cfg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    config = prepare()
    if args.prepare:
        print(json.dumps({"config": str(CONFIG), "vault": config["obsidian_vault"], "port": config["port"]}, ensure_ascii=False))
        return
    root = Path(config["data_root"]).parent.resolve()
    if not root.name.startswith("obsidian-workspace-phase0-") or not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError("UI 验证配置必须指向独立的临时测试目录")
    runtime = Runtime(config, model=CodexModel(cwd=ROOT / "bridge"), native_factory=native_fixture)
    with patch("engine.feishu.FeishuSource", FakeFeishu):
        runtime.start()
        server = ThreadingHTTPServer(("127.0.0.1", config["port"]), make_handler(runtime))
        print("Isolated workspace API http://127.0.0.1:" + str(config["port"]), flush=True)
        try:
            server.serve_forever()
        finally:
            runtime.stop.set()
            server.server_close()


if __name__ == "__main__":
    main()
