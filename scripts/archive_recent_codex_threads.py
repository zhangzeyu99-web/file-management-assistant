from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
LOCAL_TZ = timezone(timedelta(hours=8))
MOJIBAKE_MARKERS = ("Ã", "Â", "\ufffd", "閹", "娴", "閻", "缂", "闂", "濮", "閿", "娑", "鎼", "妫", "杩", "绾", "褰")
SKIP_USER_PREFIXES = (
    "# AGENTS.md instructions",
    "<environment_context>",
    "Automation:",
)


@dataclass(frozen=True)
class SessionIndexItem:
    thread_id: str
    title: str
    updated_at: datetime


@dataclass(frozen=True)
class ThreadArchiveItem:
    id: str
    latest_at: str
    title: str
    topic: str
    value: str
    update_kind: str
    cwd: str
    path: str
    message_count: int
    user_message_count: int
    first_user: str
    last_user: str
    action_hint: str


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(LOCAL_TZ)
    except ValueError:
        return None


def day_start(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return datetime.combine(parsed.date(), time.min, tzinfo=LOCAL_TZ)


def day_end(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return datetime.combine(parsed.date(), time.max, tzinfo=LOCAL_TZ)


def maybe_repair_mojibake(value: str) -> str:
    if not value or not any(marker in value for marker in MOJIBAKE_MARKERS):
        return value
    candidates = [value]
    for source_encoding, target_encoding in (("gb18030", "utf-8"), ("latin1", "utf-8")):
        try:
            candidates.append(value.encode(source_encoding, errors="strict").decode(target_encoding, errors="strict"))
        except UnicodeError:
            pass
    return min(candidates, key=lambda item: sum(item.count(marker) for marker in MOJIBAKE_MARKERS))


def one_line(value: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", maybe_repair_mojibake(value)).strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def load_session_index(codex_home: Path) -> dict[str, SessionIndexItem]:
    items: dict[str, SessionIndexItem] = {}
    for row in read_jsonl(codex_home / "session_index.jsonl"):
        thread_id = str(row.get("id") or "")
        updated_at = parse_datetime(str(row.get("updated_at") or ""))
        if not thread_id or not updated_at:
            continue
        title = one_line(str(row.get("thread_name") or thread_id), 120)
        previous = items.get(thread_id)
        if previous is None or updated_at >= previous.updated_at:
            items[thread_id] = SessionIndexItem(thread_id=thread_id, title=title, updated_at=updated_at)
    return items


def infer_id_from_filename(path: Path) -> str:
    match = UUID_RE.search(path.stem)
    if match:
        return match.group(0)
    stem = path.stem
    return stem.removeprefix("rollout-")


def iter_session_files(codex_home: Path) -> Iterable[Path]:
    for root_name in ("sessions", "archived_sessions"):
        root = codex_home / root_name
        if not root.exists():
            continue
        yield from root.rglob("*.jsonl")


def extract_user_text(payload: dict[str, Any]) -> str:
    if payload.get("type") == "user_message" and isinstance(payload.get("message"), str):
        return payload["message"]
    if payload.get("role") != "user":
        return ""
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text") or item.get("input_text") or item.get("content")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def load_thread_file(path: Path) -> dict[str, Any]:
    thread_id = infer_id_from_filename(path)
    timestamp = ""
    cwd = ""
    message_count = 0
    user_messages: list[str] = []

    for row in read_jsonl(path):
        message_count += 1
        payload = row.get("payload")
        if row.get("type") == "session_meta" and isinstance(payload, dict):
            thread_id = str(payload.get("id") or thread_id)
            timestamp = str(payload.get("timestamp") or timestamp)
            cwd = str(payload.get("cwd") or cwd)
            continue
        if not isinstance(payload, dict):
            continue
        text = extract_user_text(payload)
        if not text:
            continue
        cleaned = one_line(text, 260)
        if cleaned and not any(cleaned.startswith(prefix) for prefix in SKIP_USER_PREFIXES):
            user_messages.append(cleaned)

    return {
        "thread_id": thread_id,
        "timestamp": timestamp,
        "cwd": cwd,
        "message_count": message_count,
        "user_messages": user_messages,
        "path": path,
    }


def classify_topic(title: str, first_user: str, cwd: str) -> str:
    text = f"{title}\n{first_user}\n{cwd}".casefold()
    if "daily review" in text or "automation" in text:
        return "自动任务"
    if any(term in text for term in ("运营", "sop", "简历", "游戏", "公告", "合服", "career")):
        return "游戏运营/业务 SOP"
    if any(term in text for term in ("obsidian", "知识", "notebooklm", "助手")):
        return "Obsidian/知识助手"
    if any(term in text for term in ("本地化", "翻译", "术语", "lqa", "localization")):
        return "本地化/术语"
    if any(term in text for term in ("codex", "cursor", "github", "仓库", "thread", "线程", "harness", "gui", "playwright", "computer use")):
        return "Codex/工具链"
    if any(term in text for term in ("释放", "磁盘", "电脑", "host")):
        return "本机维护"
    return "其他"


def value_for(topic: str, user_message_count: int) -> str:
    if topic in {"游戏运营/业务 SOP", "Obsidian/知识助手", "本地化/术语"} and user_message_count >= 2:
        return "高：可作为后续任务上下文"
    if topic == "自动任务":
        return "低：例行自动化证据"
    if user_message_count >= 3:
        return "中：可作为排障或项目线索"
    return "低：入口索引"


def action_hint_for(topic: str) -> str:
    if topic == "自动任务":
        return "只用于确认 daily review 是否运行，不优先阅读。"
    if topic in {"游戏运营/业务 SOP", "Obsidian/知识助手", "本地化/术语"}:
        return "适合加入 AI 上下文包，必要时读取原始 JSONL 复盘。"
    return "保留标题、路径和首尾需求，后续按关键词检索。"


def build_items(codex_home: Path, since: str, until: str) -> list[ThreadArchiveItem]:
    start = day_start(since)
    end = day_end(until)
    index = load_session_index(codex_home)
    file_by_id: dict[str, dict[str, Any]] = {}
    for path in iter_session_files(codex_home):
        data = load_thread_file(path)
        thread_id = data["thread_id"]
        previous = file_by_id.get(thread_id)
        if previous is None or str(path) > str(previous["path"]):
            file_by_id[thread_id] = data

    items: list[ThreadArchiveItem] = []
    for thread_id, index_item in index.items():
        if not (start <= index_item.updated_at <= end):
            continue
        file_data = file_by_id.get(thread_id, {})
        user_messages = file_data.get("user_messages") or []
        first_user = user_messages[0] if user_messages else "未抽取到用户正文"
        last_user = user_messages[-1] if user_messages else first_user
        cwd = str(file_data.get("cwd") or "")
        path = Path(file_data.get("path") or "")
        topic = classify_topic(index_item.title, first_user, cwd)
        user_message_count = len(user_messages)
        update_kind = "自动任务" if topic == "自动任务" else "新增/活跃线程"
        items.append(
            ThreadArchiveItem(
                id=thread_id,
                latest_at=index_item.updated_at.isoformat(),
                title=index_item.title,
                topic=topic,
                value=value_for(topic, user_message_count),
                update_kind=update_kind,
                cwd=cwd or "未记录",
                path=str(path) if str(path) != "." else "未找到原始 JSONL",
                message_count=int(file_data.get("message_count") or 0),
                user_message_count=user_message_count,
                first_user=first_user,
                last_user=last_user,
                action_hint=action_hint_for(topic),
            )
        )

    items.sort(key=lambda item: (item.latest_at, item.id), reverse=True)
    return items


def render_markdown(items: list[ThreadArchiveItem], since: str, until: str, manifest_path: Path) -> str:
    counts_by_topic = Counter(item.topic for item in items)
    high_value = [item for item in items if item.value.startswith("高")]
    lines = [
        "---",
        "type: codex-thread-delta-archive",
        f"created: {datetime.now(LOCAL_TZ).isoformat(timespec='seconds')}",
        f"range: {since} 至 {until}",
        "tags:",
        "  - codex",
        "  - session-index",
        "  - archive",
        "  - delta",
        "---",
        "",
        f"# Codex 新增线程归档：{since} 至 {until}",
        "",
        "## 结论",
        "",
        f"本次归档 {len(items)} 条近期新增或重新活跃的 Codex 线程。这里只保存索引、摘要和原始 JSONL 路径，不复制完整对话，不移动、不删除、不改写原始会话文件。",
        "",
        "## 主题分布",
        "",
    ]
    if counts_by_topic:
        for topic, count in counts_by_topic.most_common():
            lines.append(f"- {topic}：{count} 条")
    else:
        lines.append("- 无新增线程")
    lines.extend(["", "## 优先阅读线程", ""])
    if high_value:
        lines.extend(["| 主题 | 线程 ID | 标题 | 更新时间 | 为什么重要 |", "| --- | --- | --- | --- | --- |"])
        for item in high_value[:8]:
            lines.append(
                f"| {item.topic} | `{item.id}` | {item.title} | {item.latest_at} | {item.value} |"
            )
    else:
        lines.append("本轮没有高价值长任务线程，主要是例行自动化或入口索引。")
    lines.extend(["", "## 全量新增/活跃索引", ""])
    lines.extend(["| 更新时间 | 类型 | 主题 | 价值 | 标题 | 线程 ID |", "| --- | --- | --- | --- | --- | --- |"])
    for item in items:
        lines.append(
            f"| {item.latest_at} | {item.update_kind} | {item.topic} | {item.value} | {item.title} | `{item.id}` |"
        )
    lines.extend(["", "## 详情", ""])
    for item in items:
        lines.extend(
            [
                f"### {item.title}",
                "",
                f"- 类型：{item.update_kind} / {item.topic}",
                f"- 线程 ID：`{item.id}`",
                f"- 最近更新时间：{item.latest_at}",
                f"- 消息规模：{item.message_count} 条消息，用户消息 {item.user_message_count} 条",
                f"- 工作目录：`{item.cwd}`",
                f"- 原始会话：`{item.path}`",
                f"- 首个需求：{item.first_user}",
                f"- 最近需求：{item.last_user}",
                f"- 归档建议：{item.action_hint}",
                "",
            ]
        )
    lines.extend(
        [
            "## 产物",
            "",
            f"- Manifest：`{manifest_path}`",
            "- 原始索引：`C:\\Users\\Administrator\\.codex\\session_index.jsonl`",
            "",
            "## 下次怎么继续",
            "",
            "- 找线程：搜索标题、主题或线程 ID。",
            "- 要复盘：复制“原始会话”路径，让 Codex 读取真实 JSONL。",
            "- 要提取上下文：优先选“优先阅读线程”和高价值主题，不要全量盲打包。",
            "",
        ]
    )
    return "\n".join(lines)


def write_manifest(path: Path, items: list[ThreadArchiveItem], since: str, until: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "range": {"since": since, "until": until},
        "item_count": len(items),
        "counts_by_topic": dict(Counter(item.topic for item in items)),
        "items": [asdict(item) for item in items],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def create_archive(
    *,
    codex_home: Path,
    since: str,
    until: str,
    output_dir: Path,
    obsidian_note: Path | None = None,
) -> dict[str, Any]:
    items = build_items(codex_home, since, until)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "codex-thread-delta-manifest.json"
    markdown_path = output_dir / "codex-thread-delta-archive.md"
    write_manifest(manifest_path, items, since, until)
    markdown = render_markdown(items, since, until, manifest_path)
    markdown_path.write_text(markdown, encoding="utf-8")
    if obsidian_note is not None:
        obsidian_note.parent.mkdir(parents=True, exist_ok=True)
        obsidian_note.write_text(markdown, encoding="utf-8")
    return {
        "ok": True,
        "item_count": len(items),
        "markdown_path": str(markdown_path),
        "manifest_path": str(manifest_path),
        "obsidian_note": str(obsidian_note) if obsidian_note else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive recent Codex thread index entries.")
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
    parser.add_argument("--since", required=True, help="Inclusive start date, for example 2026-05-26.")
    parser.add_argument("--until", required=True, help="Inclusive end date, for example 2026-06-02.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--obsidian-note", type=Path)
    args = parser.parse_args()
    result = create_archive(
        codex_home=args.codex_home,
        since=args.since,
        until=args.until,
        output_dir=args.output_dir,
        obsidian_note=args.obsidian_note,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
