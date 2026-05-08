from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config


WIKI_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")
WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+")
TOP_LIMIT = 12


@dataclasses.dataclass(frozen=True)
class NoteRecord:
    path: Path
    relative_path: str
    folder: str
    title: str
    size_bytes: int
    modified_at: str
    age_days: float
    word_count: int
    outgoing_links: tuple[str, ...]


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def vault_path(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_vault") or "D:\\Obsidian-Work")


def runtime_root(config: dict[str, Any]) -> Path:
    return Path(config.get("runtime_root") or "D:\\codex\\file-assistant")


def folder_name(config: dict[str, Any], key: str, default: str) -> str:
    return str(config.get("obsidian_folders", {}).get(key, default))


def obsidian_run_dir(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_run_dir") or vault_path(config) / folder_name(config, "routine", "04 例行工作") / "知识行动助手")


def read_note(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def relative_note_path(vault: Path, path: Path) -> str:
    return path.relative_to(vault).as_posix()


def extract_links(text: str) -> tuple[str, ...]:
    text = strip_code_blocks_and_spans(text)
    links: list[str] = []
    for raw in WIKI_LINK_RE.findall(text):
        cleaned = raw.strip().replace("\\", "/")
        if cleaned:
            links.append(cleaned)
    for raw in MARKDOWN_LINK_RE.findall(text):
        cleaned = raw.strip().replace("\\", "/")
        if cleaned:
            links.append(cleaned)
    return tuple(dict.fromkeys(links))


def strip_code_blocks_and_spans(text: str) -> str:
    without_fences = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]+`", "", without_fences)


def iter_note_paths(vault: Path) -> list[Path]:
    if not vault.exists():
        return []
    paths = []
    for path in vault.rglob("*.md"):
        if ".obsidian" in path.parts:
            continue
        paths.append(path)
    return sorted(paths)


def build_notes(vault: Path, reference_time: dt.datetime | None = None) -> list[NoteRecord]:
    reference = reference_time or now_local()
    records: list[NoteRecord] = []
    for path in iter_note_paths(vault):
        stat = path.stat()
        text = read_note(path)
        relative_path = relative_note_path(vault, path)
        folder = relative_path.split("/", 1)[0] if "/" in relative_path else "根目录"
        modified = dt.datetime.fromtimestamp(stat.st_mtime, tz=reference.tzinfo)
        records.append(
            NoteRecord(
                path=path,
                relative_path=relative_path,
                folder=folder,
                title=path.stem,
                size_bytes=int(stat.st_size),
                modified_at=modified.strftime("%Y-%m-%d %H:%M:%S %z"),
                age_days=round(max(0.0, (reference - modified).total_seconds() / 86400), 2),
                word_count=len(WORD_RE.findall(text)),
                outgoing_links=extract_links(text),
            )
        )
    return records


def note_indexes(notes: list[NoteRecord]) -> tuple[set[str], set[str], dict[str, list[NoteRecord]]]:
    by_relative = {note.relative_path[:-3] for note in notes}
    by_relative.update(note.relative_path for note in notes)
    by_title = {note.title for note in notes}
    title_groups: dict[str, list[NoteRecord]] = {}
    for note in notes:
        title_groups.setdefault(note.title, []).append(note)
    return by_relative, by_title, title_groups


def normalize_link_target(target: str) -> str:
    cleaned = target.strip().replace("\\", "/")
    if cleaned.endswith(".md"):
        cleaned = cleaned[:-3]
    return cleaned.strip("/")


def link_exists(target: str, by_relative: set[str], by_title: set[str]) -> bool:
    normalized = normalize_link_target(target)
    if not normalized:
        return True
    if normalized in by_relative or f"{normalized}.md" in by_relative:
        return True
    return Path(normalized).name in by_title


def backlink_counts(notes: list[NoteRecord]) -> dict[str, int]:
    by_relative, by_title, title_groups = note_indexes(notes)
    counts = {note.relative_path: 0 for note in notes}
    for note in notes:
        for link in note.outgoing_links:
            normalized = normalize_link_target(link)
            if normalized in by_relative:
                key = normalized if normalized.endswith(".md") else f"{normalized}.md"
                if key in counts:
                    counts[key] += 1
                    continue
            title = Path(normalized).name
            if title in by_title:
                for target in title_groups.get(title, []):
                    counts[target.relative_path] += 1
    return counts


def table_items(items: list[dict[str, Any]], columns: list[tuple[str, str]], limit: int = TOP_LIMIT) -> str:
    if not items:
        return "暂无。\n"
    lines = [
        "| " + " | ".join(title for title, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for item in items[:limit]:
        values = [str(item.get(key, "")).replace("\n", " ") for _, key in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def by_folder(notes: list[NoteRecord]) -> list[dict[str, Any]]:
    groups: dict[str, list[NoteRecord]] = {}
    for note in notes:
        groups.setdefault(note.folder, []).append(note)
    return [
        {
            "folder": folder,
            "notes": len(items),
            "size_kb": round(sum(item.size_bytes for item in items) / 1024, 2),
        }
        for folder, items in sorted(groups.items())
    ]


def is_existing_directory_link(vault: Path, target: str) -> bool:
    normalized = normalize_link_target(target)
    return bool(normalized) and (vault / normalized).is_dir()


def find_broken_links(vault: Path, notes: list[NoteRecord]) -> list[dict[str, Any]]:
    by_relative, by_title, _ = note_indexes(notes)
    broken: list[dict[str, Any]] = []
    for note in notes:
        for link in note.outgoing_links:
            if is_existing_directory_link(vault, link):
                continue
            if not link_exists(link, by_relative, by_title):
                broken.append({"note": note.relative_path, "link": link})
    return broken


def find_folder_links(vault: Path, notes: list[NoteRecord]) -> list[dict[str, Any]]:
    folder_links: list[dict[str, Any]] = []
    for note in notes:
        for link in note.outgoing_links:
            if is_existing_directory_link(vault, link):
                folder_links.append({"note": note.relative_path, "link": link})
    return folder_links


def classify_notes(vault: Path, notes: list[NoteRecord], config: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    config = config or {}
    inbox = folder_name(config, "inbox", "00 收件箱")
    templates = folder_name(config, "templates", "90 模板")
    archive = folder_name(config, "archive", "99 归档")
    projects = folder_name(config, "projects", "02 项目")
    codex_project = folder_name(config, "codex_project", "Codex")
    codex_prefix = f"{projects}/{codex_project}/"
    backlinks = backlink_counts(notes)
    by_relative, by_title, title_groups = note_indexes(notes)

    empty_or_stub = [
        note for note in notes
        if note.word_count <= 12 and note.folder not in {templates}
    ]
    inbox_triage = [
        note for note in notes
        if note.folder == inbox
    ]
    low_link_notes = [
        note for note in notes
        if len(note.outgoing_links) == 0
        and backlinks.get(note.relative_path, 0) == 0
        and note.folder not in {templates, archive}
    ]
    duplicate_titles = [
        {
            "title": title,
            "count": len(group),
            "paths": "；".join(item.relative_path for item in group[:5]),
        }
        for title, group in sorted(title_groups.items())
        if len(group) > 1
    ]
    broken_links = find_broken_links(vault, notes)
    folder_links = find_folder_links(vault, notes)
    unindexed_codex = [
        note for note in notes
        if note.relative_path.startswith(codex_prefix)
        and note.title[:2].isdigit()
        and backlinks.get(note.relative_path, 0) == 0
        and note.title != "00 Codex 总览"
    ]

    def note_to_item(note: NoteRecord) -> dict[str, Any]:
        return {
            "path": note.relative_path,
            "folder": note.folder,
            "words": note.word_count,
            "links": len(note.outgoing_links),
            "backlinks": backlinks.get(note.relative_path, 0),
            "modified_at": note.modified_at,
            "age_days": note.age_days,
        }

    return {
        "empty_or_stub": [note_to_item(item) for item in sorted(empty_or_stub, key=lambda n: n.word_count)[:TOP_LIMIT]],
        "inbox_triage": [note_to_item(item) for item in sorted(inbox_triage, key=lambda n: n.age_days, reverse=True)[:TOP_LIMIT]],
        "low_link_notes": [note_to_item(item) for item in sorted(low_link_notes, key=lambda n: (n.folder, n.title))[:TOP_LIMIT]],
        "duplicate_titles": duplicate_titles[:TOP_LIMIT],
        "broken_links": broken_links[:TOP_LIMIT],
        "folder_links": folder_links[:TOP_LIMIT],
        "unindexed_codex": [note_to_item(item) for item in sorted(unindexed_codex, key=lambda n: n.relative_path)[:TOP_LIMIT]],
    }


def build_summary(config: dict[str, Any], notes: list[NoteRecord], generated_at: dt.datetime, run_dir: Path) -> dict[str, Any]:
    classifications = classify_notes(vault_path(config), notes, config)
    counts = {name: len(items) for name, items in classifications.items()}
    return {
        "ok": True,
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S %z"),
        "vault": str(vault_path(config)),
        "runtime_dir": str(run_dir),
        "total_notes": len(notes),
        "total_size_kb": round(sum(item.size_bytes for item in notes) / 1024, 2),
        "by_folder": by_folder(notes),
        "counts": counts,
        "classifications": classifications,
        "safety": {
            "source_notes_modified": False,
            "deletes_notes": False,
            "moves_notes": False,
            "rewrites_existing_notes": False,
            "report_only": True,
        },
        "evolution": {
            "added_internal_obsidian_audit": True,
            "checks": [
                "folder inventory",
                "inbox triage",
                "stub notes",
                "low-link notes",
                "duplicate titles",
                "broken internal links",
                "folder-style links",
                "Codex index coverage",
            ],
            "guardrail": "只新增报告，不删除、不移动、不覆盖源笔记。",
        },
    }


def render_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    lines = [
        "# Obsidian 管理自评与进化报告",
        "",
        f"生成时间：`{summary['generated_at']}`",
        f"Obsidian 库：`{summary['vault']}`",
        "",
        "## 本轮结论",
        "",
        "- 这轮已把助手从“本地文件扫描”升级为“本地文件 + Obsidian 内部结构管理”。",
        "- 本轮只做只读审计和新增报告，不删除、不移动、不覆盖任何源笔记。",
        "- 任何疑似空壳、孤立、断链、待归档内容都只进入建议清单，避免丢失重要信息。",
        "",
        "## Obsidian 概览",
        "",
        f"- 笔记数：`{summary['total_notes']}`",
        f"- Markdown 体量：`{summary['total_size_kb']} KB`",
        f"- 收件箱待整理：`{counts['inbox_triage']}`",
        f"- 空壳或极短笔记：`{counts['empty_or_stub']}`",
        f"- 低连接笔记：`{counts['low_link_notes']}`",
        f"- 断链：`{counts['broken_links']}`",
        f"- 目录式链接：`{counts['folder_links']}`",
        f"- 重名标题：`{counts['duplicate_titles']}`",
        f"- Codex 索引疑似缺口：`{counts['unindexed_codex']}`",
        "",
        "## 按目录统计",
        "",
        table_items(summary["by_folder"], [("目录", "folder"), ("笔记数", "notes"), ("大小 KB", "size_kb")], 20),
        "## 待整理收件箱",
        "",
        table_items(summary["classifications"]["inbox_triage"], [("路径", "path"), ("字数", "words"), ("修改时间", "modified_at")]),
        "## 空壳或极短笔记",
        "",
        table_items(summary["classifications"]["empty_or_stub"], [("路径", "path"), ("字数", "words"), ("反链", "backlinks")]),
        "## 低连接笔记",
        "",
        table_items(summary["classifications"]["low_link_notes"], [("路径", "path"), ("出链", "links"), ("反链", "backlinks")]),
        "## 断链",
        "",
        table_items(summary["classifications"]["broken_links"], [("笔记", "note"), ("断链目标", "link")]),
        "## 目录式链接",
        "",
        "这些链接指向已存在目录，不是内容丢失。建议后续改成目录内的总览页，避免误判为断链。",
        "",
        table_items(summary["classifications"]["folder_links"], [("笔记", "note"), ("目录链接", "link")]),
        "## 重名标题",
        "",
        table_items(summary["classifications"]["duplicate_titles"], [("标题", "title"), ("数量", "count"), ("路径", "paths")]),
        "## Codex 索引疑似缺口",
        "",
        table_items(summary["classifications"]["unindexed_codex"], [("路径", "path"), ("出链", "links"), ("反链", "backlinks")]),
        "## 本轮进化",
        "",
        "- 新增 Obsidian 内部审计：目录统计、收件箱、空壳笔记、低连接笔记、断链、目录式链接、重名标题、Codex 索引覆盖。",
        "- 自查后修正误报：代码块和行内代码里的示例双链不参与断链判断；指向真实目录的链接单独列为目录式链接。",
        "- 新增安全护栏：只生成报告，不改源笔记；所有建议必须人工或后续白名单规则确认后才可执行。",
        "- 通知不作为项目核心能力；本轮只落盘 Markdown、JSON 和 Obsidian 记录。",
        "",
        "## 下一步建议",
        "",
        "1. 先处理 `00 收件箱` 中仍有价值的条目，移动前保留原文或在目标页加来源链接。",
        "2. 对空壳笔记只做补内容或合并建议，不直接删除。",
        "3. 对低连接笔记优先补入口链接，而不是移动文件。",
        "4. 对断链先确认是否是改名、别名或历史归档，不要批量修。",
        "5. 如果未来要自动移动笔记，必须先生成 dry-run manifest，再加白名单。",
        "",
        "## 安全策略",
        "",
        "- source_notes_modified：`false`",
        "- deletes_notes：`false`",
        "- moves_notes：`false`",
        "- rewrites_existing_notes：`false`",
        "- report_only：`true`",
        "",
    ]
    return "\n".join(lines)


def write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_obsidian_report(config: dict[str, Any], markdown: str, generated_at: dt.datetime) -> Path:
    date_part = generated_at.strftime("%Y-%m-%d")
    path = obsidian_run_dir(config) / f"{date_part} Obsidian 管理自评与进化报告.md"
    write_text(path, markdown)
    return path


def run(config_path: Path, mode: str = "Run") -> dict[str, Any]:
    config = load_config(config_path)
    generated_at = now_local()
    run_dir = runtime_root(config) / "runs" / generated_at.strftime("%Y-%m-%d") / generated_at.strftime("%H%M%S-obsidian")
    notes = build_notes(vault_path(config), generated_at)
    summary = build_summary(config, notes, generated_at, run_dir)
    summary["mode"] = mode

    markdown = render_markdown(summary)
    markdown_report = run_dir / "obsidian-management-report.md"
    summary_json = run_dir / "obsidian-management-summary.json"
    obsidian_note = write_obsidian_report(config, markdown, generated_at)

    summary.update(
        {
            "summary_json": str(summary_json),
            "markdown_report": str(markdown_report),
            "obsidian_note": str(obsidian_note),
        }
    )
    write_text(markdown_report, markdown)
    write_json(summary_json, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Obsidian vault manager")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--mode", default="Run", choices=["Run", "Test"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run(Path(args.config), args.mode)
    print(json.dumps({
        "ok": True,
        "summary_json": summary["summary_json"],
        "markdown_report": summary["markdown_report"],
        "obsidian_note": summary["obsidian_note"],
        "total_notes": summary["total_notes"],
        "counts": summary["counts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
