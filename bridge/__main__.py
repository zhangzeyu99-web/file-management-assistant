"""JSON stdin/stdout entry: py -3 -X utf8 -m bridge."""
from __future__ import annotations

import json
import sys

from . import BridgeError, CodexModel, NativeCodexBridge


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise BridgeError("invalid_input", "输入必须是 JSON 对象。")
        action = payload.get("action")
        if action == "generate":
            result = CodexModel().generate_result(payload.get("prompt", ""), timeout=payload.get("timeout", 300))
        elif action in {"list_threads", "list_archived_threads", "read_thread"}:
            with NativeCodexBridge() as native:
                if action == "list_threads":
                    result = native.list_threads(payload.get("limit", 50))
                elif action == "list_archived_threads":
                    result = native.list_archived_threads(
                        limit=payload.get("limit", 50), cursor=payload.get("cursor"), host_id=payload.get("hostId"))
                else:
                    result = native.read_thread(
                        payload.get("threadId", ""), cursor=payload.get("cursor"),
                        turn_limit=payload.get("turnLimit", 5), host_id=payload.get("hostId"),
                        include_outputs=payload.get("includeOutputs", True),
                        max_output_chars_per_item=payload.get("maxOutputCharsPerItem", 20000))
            result = {"ok": True, "data": result}
        else:
            raise BridgeError("action_not_allowed", "仅支持线程列表、归档列表、线程读取和文字生成。")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except BridgeError as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False))
        return 1
    except (ValueError, TypeError, KeyError):
        print(json.dumps(BridgeError("invalid_input", "输入必须是有效的 JSON 请求。").as_dict(), ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
