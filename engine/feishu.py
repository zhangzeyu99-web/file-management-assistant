"""Read Feishu metadata through the installed official CLI and user identity.

No authorization files, document bodies, or write endpoints are accessed here.
Three previously approved discovery lanes are preserved: the user's owned
resources, their edits since the checkpoint, and the known video archive owner.
"""
from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlsplit

from .incremental import stamp


class FeishuError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def cli_command():
    launcher = shutil.which("lark-cli") or shutil.which("lark-cli.cmd")
    if not launcher:
        raise FeishuError("cli_unavailable", "未找到已安装的飞书 CLI，本次未检查飞书。")
    path = Path(launcher)
    script = path.parent / "node_modules" / "@larksuite" / "cli" / "scripts" / "run.js"
    if script.is_file():
        node = path.parent / "node.exe"
        executable = str(node) if node.is_file() else shutil.which("node")
        if executable:
            return [executable, str(script)]
    if path.suffix.casefold() in {".cmd", ".bat", ".ps1"}:
        raise FeishuError("cli_unavailable", "飞书 CLI 的 Node 入口不可用，本次未检查飞书。")
    return [str(path)]


def _decode(text):
    """Ignore non-JSON stderr notices without ever exposing raw CLI output."""
    try:
        value = json.loads((text or "").lstrip("\ufeff"))
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None


def _failure(payload):
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    if not isinstance(error, dict):
        error = {}
    details = " ".join(str(error.get(key, "")) for key in ("type", "subtype", "code", "message")).lower()
    if error.get("missing_scopes") or re.search(r"permission|forbidden|scope|无权|权限不足", details):
        return FeishuError("permission_denied", "飞书用户授权缺少当前读取权限；本次来源未检查完成。")
    if re.search(r"auth|access.token|refresh.token|invalid.token|token.*expir|登录|授权过期|9999166[138]", details):
        return FeishuError("auth_error", "飞书用户令牌无效、过期或尚未登录；本次来源未检查完成。")
    return FeishuError("read_failed", "飞书元数据读取失败；保留上次成功检查时间，稍后重试。")


def normalize_result(row):
    if not isinstance(row, dict) or not isinstance(row.get("result_meta"), dict):
        raise FeishuError("invalid_metadata", "飞书结果缺少资源元数据，未将本次检查标记完成。")
    meta = row["result_meta"]
    token, url = meta.get("token"), meta.get("url")
    if not isinstance(token, str) or not token or not isinstance(url, str):
        raise FeishuError("invalid_metadata", "飞书结果缺少 token 或来源链接，未将本次检查标记完成。")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or re.search(r"[\r\n\x00]", url):
        raise FeishuError("invalid_metadata", "飞书结果包含无效来源链接，未将本次检查标记完成。")
    title = row.get("title_highlighted") or row.get("title") or token
    title = html.unescape(re.sub(r"</?(?:h|hb)>", "", str(title), flags=re.I))
    title = " ".join(title.split())
    try:
        updated = stamp(meta.get("update_time", meta.get("update_time_iso")))
        if not updated:
            raise ValueError("missing time")
        updated_iso = datetime.fromtimestamp(updated, timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        raise FeishuError("invalid_metadata", "飞书结果缺少有效更新时间，未将本次检查标记完成。") from None
    return {"token": token, "title": title, "url": url, "updatedAt": updated_iso,
            "updatedAtEpoch": updated, "type": str(meta.get("doc_types", "")),
            "entityType": str(row.get("entity_type", "")), "contentRead": False}


class FeishuSource:
    def __init__(self, command=None, *, video_owner_id=None, runner=None, timeout=60, max_pages=None):
        self.command = list(command) if command is not None else None
        self.runner = runner or subprocess.run
        self.timeout = timeout
        self.video_owner_id = video_owner_id
        if max_pages is not None and (isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1):
            raise ValueError("max_pages 必须是正整数或 None。")
        self.max_pages = max_pages

    def _page(self, command, filters, page_token):
        args = [*command, "--as", "user", "drive", "+search", "--query=",
                *filters, "--sort", "edit_time", "--page-size", "20", "--format", "json"]
        if page_token:
            args.extend(["--page-token", page_token])
        try:
            process = self.runner(args, capture_output=True, text=True, encoding="utf-8",
                                  timeout=self.timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            raise FeishuError("timeout", "飞书元数据读取超时；保留上次成功检查时间，稍后重试。") from None
        except (OSError, UnicodeError):
            raise FeishuError("cli_unavailable", "无法运行飞书 CLI，本次来源未检查完成。") from None
        output, error = _decode(process.stdout), _decode(process.stderr)
        if process.returncode != 0 or not output or output.get("ok") is not True:
            raise _failure(error if error and error.get("ok") is False else output)
        if output.get("identity") != "user":
            raise FeishuError("identity_mismatch", "飞书返回的身份不是当前用户，本次来源未检查完成。")
        data = output.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("results"), list) or not isinstance(data.get("has_more"), bool):
            raise FeishuError("invalid_response", "飞书返回缺少有效分页信息，不能视为无新增。")
        return data

    def list_since(self, since):
        result = {"items": [], "complete": False, "warnings": [], "status": "not_checked",
                  "scope": "owned_user_edits_video_owner", "filterPrecision": "hour", "pages": 0, "groups": {}}
        items = {}
        try:
            boundary = stamp(since)
            if not boundary:
                raise FeishuError("invalid_since", "飞书增量检查需要已有成功检查时间或基线，不能从空时间开始。")
            boundary_iso = datetime.fromtimestamp(boundary, timezone.utc).isoformat()
            result["since"] = boundary_iso
            command = self.command if self.command is not None else cli_command()
            groups = [("owned", ["--mine"]), ("edited", ["--edited-since", boundary_iso]),
                      ("video_owner", ["--creator-ids", self.video_owner_id])]
            connection_error = None
            for group_name, filters in groups:
                group = {"status": "not_checked", "complete": False, "pages": 0}
                result["groups"][group_name] = group
                if connection_error:
                    group.update(status="not_connected", error=connection_error)
                    continue
                if group_name == "video_owner" and not (
                    isinstance(self.video_owner_id, str) and re.fullmatch(r"ou_[A-Za-z0-9_-]+", self.video_owner_id)
                ):
                    group["status"] = "not_configured"
                    result["warnings"].append("未配置原视频归档所有者，飞书三组来源尚未全部检查。")
                    continue
                try:
                    self._scan_group(command, filters, group_name, group, result, items)
                except FeishuError as error:
                    group["status"] = "not_connected" if error.code in {"auth_error", "permission_denied", "cli_unavailable", "identity_mismatch"} else "failed"
                    group["error"] = {"code": error.code, "message": str(error)}
                    result.setdefault("error", group["error"])
                    result["warnings"].append(f"{group_name}：{error}")
                    if error.code in {"auth_error", "cli_unavailable", "identity_mismatch"}:
                        connection_error = group["error"]
            result["complete"] = all(group["complete"] for group in result["groups"].values())
            result["status"] = "checked" if result["complete"] else (
                "not_connected" if all(group["status"] == "not_connected" for group in result["groups"].values()) else "partial")
        except FeishuError as error:
            result["status"] = "not_connected" if error.code in {"auth_error", "permission_denied", "cli_unavailable", "identity_mismatch"} else "failed"
            result["error"] = {"code": error.code, "message": str(error)}
            result["warnings"].append(str(error))
        except (ValueError, TypeError, OverflowError, OSError):
            result["status"] = "failed"
            result["error"] = {"code": "invalid_since", "message": "飞书增量检查时间无效，本次未检查来源。"}
            result["warnings"].append(result["error"]["message"])
        result["items"] = sorted(items.values(), key=lambda row: (-row["updatedAtEpoch"], row["token"]))
        return result

    def _scan_group(self, command, filters, group_name, group, result, items):
        page_token, seen_pages, invalid = None, set(), False
        while True:
            page = self._page(command, filters, page_token)
            group["pages"] += 1
            result["pages"] += 1
            for row in page["results"]:
                try:
                    item = normalize_result(row)
                except (FeishuError, ValueError) as error:
                    invalid = True
                    warning = str(error) if isinstance(error, FeishuError) else "飞书元数据无效，未将本次检查标记完成。"
                    if warning not in result["warnings"]:
                        result["warnings"].append(warning)
                    continue
                previous = items.get(item["token"])
                groups = list(dict.fromkeys([*(previous or {}).get("discoveredBy", []), group_name]))
                if previous is None or item["updatedAtEpoch"] > previous["updatedAtEpoch"]:
                    items[item["token"]] = {**item, "discoveredBy": groups}
                else:
                    previous["discoveredBy"] = groups
            if not page["has_more"]:
                group["complete"] = not invalid
                group["status"] = "partial" if invalid else "checked"
                return
            next_page = page.get("page_token")
            if not isinstance(next_page, str) or not next_page or next_page in seen_pages:
                raise FeishuError("pagination_error", "飞书分页游标缺失或重复，未将本次检查标记完成。")
            seen_pages.add(next_page)
            if self.max_pages is not None and group["pages"] >= self.max_pages:
                group["status"] = "partial"
                result["warnings"].append(f"{group_name}：飞书检查达到本次页数上限，仍有未检查页面。")
                group["nextPageToken"] = next_page
                return
            page_token = next_page
