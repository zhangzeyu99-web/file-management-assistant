"""Conservative automation classification from explicit, visible evidence."""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .native import turn_evidence


_EXPLICIT_HEADER = re.compile(
    r"^(?:Automation (?:ID|Title)|自动化任务\s*(?:ID|编号))\s*[:：]\s*\S",
    re.IGNORECASE,
)
_AUTOMATION_NAME = re.compile(r"^Automation\s*:\s*\S", re.IGNORECASE)
_HEADER_FIELD = re.compile(r"^(?:Automation(?: [A-Za-z]+)?|Last run)\s*:\s*\S", re.IGNORECASE)


def _has_automation_header(text: str) -> bool:
    # Keep horizontal whitespace and Markdown quotation/fence prefixes: an
    # indented code sample or a quoted header is not a task envelope.
    lines = text.lstrip("\ufeff\r\n").splitlines()[:6]
    if not lines:
        return False
    if _EXPLICIT_HEADER.match(lines[0]):
        return True
    if not _AUTOMATION_NAME.match(lines[0]):
        return False
    # The standard desktop envelope starts "Automation: <name>", followed by
    # its ID. A bare mention of Automation in ordinary prose is insufficient.
    for line in lines[1:]:
        if _EXPLICIT_HEADER.match(line):
            return True
        if not _HEADER_FIELD.match(line):
            break
    return False


def is_automation_evidence(metadata: dict[str, Any], turns: Iterable[dict[str, Any]]) -> bool:
    """Recognize explicit automation identity, never a daily-report title.

    ``turns`` may be native turns or already sanitized ``turn_evidence`` turns.
    Only visible user-message text is inspected. Assistant/tool text, quoted
    headers, code blocks, and headers embedded later in a request do not count.
    """
    source = metadata.get("source")
    if isinstance(source, str) and source.casefold() in {"automation", "automations"}:
        return True
    if isinstance(metadata.get("automationId"), str) and metadata["automationId"].strip():
        return True
    for turn in turns:
        for item in turn_evidence(turn)["items"]:
            if item["type"] != "userMessage":
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text:
                text = "\n".join(
                    part["text"] for part in item.get("content", [])
                    if isinstance(part.get("text"), str)
                )
            if _has_automation_header(text):
                return True
    return False
