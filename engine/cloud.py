"""Owner-private Site service access, with a Windows-protected local token."""
import base64
import ctypes
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


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

    def request(self, path, data=None, *, raw=False):
        if not self.available:
            raise RuntimeError("线上连接尚未配置")
        token = protect(self.token_path.read_bytes(), decrypt=True).decode("utf-8")
        req = urllib.request.Request(self.url + "/api/workspace/" + path,
            data=json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None,
            headers={"OAI-Sites-Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = response.read()
                return payload if raw else json.loads(payload)
        except urllib.error.HTTPError as e:
            # Never echo request headers or secret-bearing response pages.
            message = f"线上服务返回 {e.code}"
            try:
                body = json.loads(e.read())
                message += "：" + str(body.get("error", ""))[:300]
            except Exception:
                pass
            raise RuntimeError(message) from None
