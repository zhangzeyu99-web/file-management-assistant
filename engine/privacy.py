"""Exclude credential files and redact explicit credential values from summaries."""
import re
from pathlib import Path

SENSITIVE_NAME = re.compile(r"(^\.env|credentials?\.|secrets?\.|^tokens?\.|password|id_rsa|id_ed25519|config\.local|openclaw\.json)", re.I)
ASSIGNMENT = re.compile(r"""(?im)((?:api[_-]?key|app[_-]?secret|access[_-]?token|refresh[_-]?token|password|authorization)\s*["']?\s*[:=]\s*)(["']?)[^\s,;"'\r\n]+""")
BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-=]{12,}")
TOKEN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,})\b")


def sensitive_path(path):
    return bool(SENSITIVE_NAME.search(Path(path).name))


def redact_text(text):
    text = ASSIGNMENT.sub(r"\1[已隐藏凭据]", text)
    return TOKEN.sub("[已隐藏凭据]", BEARER.sub("Bearer [已隐藏凭据]", text))


def redact_tree(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_tree(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_tree(v) for k, v in value.items()}
    return value
