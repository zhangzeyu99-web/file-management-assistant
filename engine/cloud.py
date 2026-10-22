"""Owner-private Site service access, with a Windows-protected local token."""
import base64
import ctypes
import json
import os
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

from .user_errors import ERRORS

MIGRATION_CHUNK_BYTES = 4 * 1024 * 1024
MIGRATION_CLOUD_LIMIT = 128 * 1024 * 1024


class CloudError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(data: bytes, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("本机服务凭据需要 Windows 凭据保护")
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt = ctypes.windll.crypt32
    ok = crypt.CryptUnprotectData(ctypes.byref(incoming), None, None, None, None, 0, ctypes.byref(outgoing)) if decrypt else crypt.CryptProtectData(ctypes.byref(incoming), "Obsidian workspace", None, None, None, 0, ctypes.byref(outgoing))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.data)


def save_service_token(path, token):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(protect(token.encode("utf-8")))


class Cloud:
    def __init__(self, url, token_path):
        self.url = url.rstrip("/")
        self.token_path = Path(token_path)

    @property
    def available(self):
        return bool(self.url) and self.token_path.exists()

    def request(self, path, data=None, *, raw=False, binary=False):
        if not self.available:
            raise CloudError("cloud_not_configured", "线上连接尚未配置")
        try:
            token = protect(self.token_path.read_bytes(), decrypt=True).decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise CloudError("cloud_auth", "无法使用当前电脑保存的线上服务凭据") from error
        req = urllib.request.Request(self.url + "/api/workspace/" + path,
            data=data if binary else json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None,
            headers={"OAI-Sites-Authorization": "Bearer " + token,
                     "Content-Type": "application/octet-stream" if binary else "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = response.read()
                return payload if raw else json.loads(payload)
        except urllib.error.HTTPError as e:
            # Status is enough to distinguish recovery. Never echo response pages.
            code = {401: "cloud_auth", 403: "cloud_forbidden", 404: "cloud_not_found",
                    400: "request_invalid", 409: "cloud_request_conflict",
                    429: "cloud_rate_limited"}.get(e.code, "cloud_unavailable")
            try:
                body = json.loads(e.read(32768))
                detail = body.get("error_detail") if isinstance(body, dict) else None
                remote_code = detail.get("code") if isinstance(detail, dict) else body.get("error_code")
                if remote_code in ERRORS:
                    code = remote_code
            except (ValueError, AttributeError, TypeError):
                pass
            raise CloudError(code, f"线上服务返回 {e.code}") from None
        except (TimeoutError, socket.timeout) as error:
            raise CloudError("cloud_timeout", "连接线上服务超时") from error
        except urllib.error.URLError as error:
            code = "cloud_timeout" if isinstance(error.reason, (TimeoutError, socket.timeout)) else "cloud_unavailable"
            raise CloudError(code, "无法连接线上服务") from error
        except (UnicodeError, json.JSONDecodeError) as error:
            raise CloudError("cloud_response_invalid", "线上服务返回的数据无法识别") from error

    def upload_migration(self, bundle, job_id, owner, *, progress=None):
        """Upload bounded chunks with the same private service authentication."""
        bundle = Path(bundle)
        size = bundle.stat().st_size
        if size > MIGRATION_CLOUD_LIMIT:
            raise ValueError("迁移包超过线上128 MB上限，请在本机页面导出")
        if size <= 0:
            raise ValueError("迁移包为空，未上传")
        parts = (size + MIGRATION_CHUNK_BYTES - 1) // MIGRATION_CHUNK_BYTES
        if progress:
            progress("迁移包已生成，正在准备私有下载")
        self.request("agent/migration/start",
                     {"job_id": job_id, "owner": owner, "filename": bundle.name, "size": size, "parts": parts})
        with bundle.open("rb") as source:
            for part in range(parts):
                if progress:
                    progress(f"正在上传迁移包片段 {part + 1}/{parts}")
                content = source.read(MIGRATION_CHUNK_BYTES)
                if len(content) != min(MIGRATION_CHUNK_BYTES, size - part * MIGRATION_CHUNK_BYTES):
                    raise RuntimeError("迁移包在上传期间变化，请重试")
                self.request("agent/migration/chunk?" + urlencode(
                    {"job_id": job_id, "part": part, "owner": owner}), content, binary=True)
            if source.read(1) or bundle.stat().st_size != size:
                raise RuntimeError("迁移包在上传期间变化，请重试")
        if progress:
            progress("正在确认私有迁移包下载")
        result = self.request("agent/migration/complete", {"job_id": job_id, "owner": owner})
        if (not isinstance(result, dict) or not isinstance(result.get("filename"), str) or
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.zip", result["filename"]) or
                result.get("size") != size or not result.get("download_url")):
            raise RuntimeError("线上未确认完整迁移包，请重试")
        return {key: result[key] for key in ("filename", "size", "download_url")}
