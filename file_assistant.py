from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import html
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config


DOCUMENT_EXTENSIONS = {
    ".doc",
    ".docx",
    ".md",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rtf",
    ".txt",
    ".xls",
    ".xlsx",
    ".csv",
}
INSTALLER_EXTENSIONS = {".exe", ".msi", ".dmg", ".pkg", ".iso", ".apk"}
ARCHIVE_EXTENSIONS = {".zip", ".7z", ".rar", ".tar", ".gz"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
PROTECTED_EXTENSIONS = {".lnk", ".url", ".ini", ".json", ".toml", ".yaml", ".yml"}


@dataclasses.dataclass(frozen=True)
class FileRecord:
    root_name: str
    path: str
    extension: str
    size_bytes: int
    modified_at: str
    age_days: float

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / 1024 / 1024, 3)


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def normalize_extension(path: Path) -> str:
    return path.suffix.lower()


def is_excluded_dir(dirname: str, excluded: set[str]) -> bool:
    lowered = dirname.lower()
    return lowered in excluded or lowered.endswith(".tmp") or lowered.endswith(".temp")


def iter_files(root: Path, max_depth: int, max_files: int, excluded_dirs: set[str]) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []

    found: list[Path] = []
    base_depth = len(root.parts)
    for current_dir, dirnames, filenames in os.walk(root):
        current = Path(current_dir)
        depth = len(current.parts) - base_depth
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if depth < max_depth and not is_excluded_dir(dirname, excluded_dirs)
        ]

        for filename in filenames:
            if filename.startswith("~$"):
                continue
            found.append(current / filename)
            if len(found) >= max_files:
                return found
    return found


def build_records(config: dict[str, Any], reference_time: dt.datetime | None = None) -> tuple[list[FileRecord], list[str]]:
    reference = reference_time or now_local()
    excluded = {str(item).lower() for item in config.get("exclude_dir_names", [])}
    records: list[FileRecord] = []
    warnings: list[str] = []

    for root_config in config.get("watch_roots", []):
        root = Path(root_config["path"])
        root_name = str(root_config.get("name") or root.name)
        files = iter_files(
            root=root,
            max_depth=int(root_config.get("max_depth", 2)),
            max_files=int(root_config.get("max_files", 2000)),
            excluded_dirs=excluded,
        )
        if not root.exists():
            warnings.append(f"路径不存在：{root}")
            continue

        for file_path in files:
            try:
                stat = file_path.stat()
            except OSError as exc:
                warnings.append(f"读取失败：{file_path} | {exc}")
                continue

            modified = dt.datetime.fromtimestamp(stat.st_mtime, tz=reference.tzinfo)
            age_days = max(0.0, (reference - modified).total_seconds() / 86400)
            records.append(
                FileRecord(
                    root_name=root_name,
                    path=str(file_path),
                    extension=normalize_extension(file_path),
                    size_bytes=int(stat.st_size),
                    modified_at=modified.strftime("%Y-%m-%d %H:%M:%S %z"),
                    age_days=round(age_days, 2),
                )
            )

    return records, warnings


def has_review_keyword(path: str, keywords: list[str]) -> bool:
    lowered = path.lower()
    return any(str(keyword).lower() in lowered for keyword in keywords)


def classify_records(records: list[FileRecord], config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    recent_days = int(config.get("recent_days", 7))
    archive_after_days = int(config.get("archive_after_days", 30))
    installer_after_days = int(config.get("installer_after_days", 14))
    large_file_mb = float(config.get("large_file_mb", 200))
    top_limit = int(config.get("top_limit", 25))
    keywords = [str(item) for item in config.get("review_keywords", [])]

    buckets: dict[str, list[FileRecord]] = {
        "recent_review": [],
        "archive_candidates": [],
        "installer_cleanup": [],
        "large_files": [],
        "screenshots": [],
    }

    for record in records:
        ext = record.extension
        path_obj = Path(record.path)
        lower_name = path_obj.name.lower()
        in_landing_zone = record.root_name in {"Desktop", "Downloads", "Documents"}

        if record.age_days <= recent_days and (ext in DOCUMENT_EXTENSIONS or has_review_keyword(record.path, keywords)):
            buckets["recent_review"].append(record)

        if in_landing_zone and record.age_days >= archive_after_days and ext not in PROTECTED_EXTENSIONS:
            buckets["archive_candidates"].append(record)

        if in_landing_zone and record.age_days >= installer_after_days and (ext in INSTALLER_EXTENSIONS or ext in ARCHIVE_EXTENSIONS):
            buckets["installer_cleanup"].append(record)

        if record.size_mb >= large_file_mb:
            buckets["large_files"].append(record)

        if ext in IMAGE_EXTENSIONS and ("screenshot" in lower_name or "截图" in lower_name or "屏幕截图" in lower_name):
            buckets["screenshots"].append(record)

    return {
        name: [record_to_dict(item) for item in sort_records(items)[:top_limit]]
        for name, items in buckets.items()
    }


def sort_records(records: list[FileRecord]) -> list[FileRecord]:
    return sorted(records, key=lambda item: (item.age_days, -item.size_bytes), reverse=True)


def record_to_dict(record: FileRecord) -> dict[str, Any]:
    return {
        "root_name": record.root_name,
        "path": record.path,
        "extension": record.extension,
        "size_bytes": record.size_bytes,
        "size_mb": record.size_mb,
        "modified_at": record.modified_at,
        "age_days": record.age_days,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_duplicates(records: list[FileRecord], config: dict[str, Any]) -> list[dict[str, Any]]:
    min_bytes = int(float(config.get("hash_duplicate_min_mb", 1)) * 1024 * 1024)
    hash_limit = int(config.get("hash_duplicate_limit", 80))
    by_size: dict[int, list[FileRecord]] = {}
    for record in records:
        if record.size_bytes >= min_bytes:
            by_size.setdefault(record.size_bytes, []).append(record)

    candidates = [items for items in by_size.values() if len(items) > 1]
    hashed = 0
    by_hash: dict[str, list[FileRecord]] = {}
    for items in candidates:
        for record in items:
            if hashed >= hash_limit:
                break
            try:
                file_hash = sha256_file(Path(record.path))
            except OSError:
                continue
            by_hash.setdefault(file_hash, []).append(record)
            hashed += 1

    duplicate_groups = []
    for file_hash, items in by_hash.items():
        if len(items) < 2:
            continue
        duplicate_groups.append(
            {
                "sha256": file_hash,
                "size_mb": items[0].size_mb,
                "count": len(items),
                "paths": [item.path for item in items],
            }
        )

    return sorted(duplicate_groups, key=lambda item: (item["count"], item["size_mb"]), reverse=True)[:15]


def summarize_by_root(records: list[FileRecord]) -> list[dict[str, Any]]:
    groups: dict[str, list[FileRecord]] = {}
    for record in records:
        groups.setdefault(record.root_name, []).append(record)
    return [
        {
            "root_name": root_name,
            "files": len(items),
            "size_mb": round(sum(item.size_bytes for item in items) / 1024 / 1024, 3),
        }
        for root_name, items in sorted(groups.items())
    ]


def build_summary(
    config: dict[str, Any],
    records: list[FileRecord],
    warnings: list[str],
    classifications: dict[str, list[dict[str, Any]]],
    duplicates: list[dict[str, Any]],
    mode: str,
    run_dir: Path,
    generated_at: dt.datetime,
) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": mode,
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S %z"),
        "runtime_dir": str(run_dir),
        "total_files": len(records),
        "total_size_mb": round(sum(item.size_bytes for item in records) / 1024 / 1024, 3),
        "by_root": summarize_by_root(records),
        "counts": {
            "recent_review": len(classifications["recent_review"]),
            "archive_candidates": len(classifications["archive_candidates"]),
            "installer_cleanup": len(classifications["installer_cleanup"]),
            "large_files": len(classifications["large_files"]),
            "screenshots": len(classifications["screenshots"]),
            "duplicate_groups": len(duplicates),
            "warnings": len(warnings),
        },
        "classifications": classifications,
        "duplicates": duplicates,
        "warnings": warnings[:20],
        "policy": {
            "source_files_modified": False,
            "deletes_files": False,
            "moves_files": False,
            "archives_by_manifest_only": True,
        },
        "config": {
            "recent_days": config.get("recent_days"),
            "archive_after_days": config.get("archive_after_days"),
            "installer_after_days": config.get("installer_after_days"),
            "large_file_mb": config.get("large_file_mb"),
        },
    }


def markdown_table(items: list[dict[str, Any]], columns: list[tuple[str, str]], limit: int = 10) -> str:
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


def render_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    lines = [
        "# 知识行动助手 · 文件雷达复盘",
        "",
        f"生成时间：`{summary['generated_at']}`",
        f"运行模式：`{summary['mode']}`",
        "",
        "## 总览",
        "",
        f"- 扫描文件：`{summary['total_files']}`",
        f"- 扫描体量：`{summary['total_size_mb']} MB`",
        f"- 近期复盘项：`{counts['recent_review']}`",
        f"- 建议归档项：`{counts['archive_candidates']}`",
        f"- 安装包 / 压缩包清理提醒：`{counts['installer_cleanup']}`",
        f"- 大文件提醒：`{counts['large_files']}`",
        f"- 重复文件组：`{counts['duplicate_groups']}`",
        "",
        "## 按目录统计",
        "",
        markdown_table(summary["by_root"], [("目录", "root_name"), ("文件数", "files"), ("大小 MB", "size_mb")], 20),
        "## 近期需要复盘",
        "",
        markdown_table(
            summary["classifications"]["recent_review"],
            [("目录", "root_name"), ("大小 MB", "size_mb"), ("修改时间", "modified_at"), ("路径", "path")],
            12,
        ),
        "## 建议归档清单",
        "",
        markdown_table(
            summary["classifications"]["archive_candidates"],
            [("目录", "root_name"), ("天数", "age_days"), ("大小 MB", "size_mb"), ("路径", "path")],
            12,
        ),
        "## 提醒",
        "",
        "### 安装包 / 压缩包",
        "",
        markdown_table(
            summary["classifications"]["installer_cleanup"],
            [("目录", "root_name"), ("天数", "age_days"), ("大小 MB", "size_mb"), ("路径", "path")],
            12,
        ),
        "### 大文件",
        "",
        markdown_table(
            summary["classifications"]["large_files"],
            [("目录", "root_name"), ("大小 MB", "size_mb"), ("路径", "path")],
            12,
        ),
        "### 重复文件",
        "",
    ]

    if summary["duplicates"]:
        for group in summary["duplicates"]:
            lines.append(f"- `{group['size_mb']} MB` x `{group['count']}`，SHA256 `{group['sha256'][:16]}`")
            for path in group["paths"][:5]:
                lines.append(f"  - `{path}`")
    else:
        lines.append("暂无。")

    lines.extend(
        [
            "",
            "## 安全策略",
            "",
            "- 本助手当前不删除、不移动、不改名源文件。",
            "- 归档先以清单、复盘和提醒形式落盘。",
            "- 需要物理搬迁文件时，必须另建白名单规则后再启用。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(summary: dict[str, Any]) -> str:
    counts = summary["counts"]

    def esc(value: Any) -> str:
        return html.escape(str(value))

    def cards() -> str:
        items = [
            ("扫描文件", summary["total_files"]),
            ("近期复盘", counts["recent_review"]),
            ("建议归档", counts["archive_candidates"]),
            ("清理提醒", counts["installer_cleanup"]),
            ("大文件", counts["large_files"]),
            ("重复组", counts["duplicate_groups"]),
        ]
        return "\n".join(
            f"<div class=\"metric\"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>"
            for label, value in items
        )

    def table(title: str, items: list[dict[str, Any]], columns: list[tuple[str, str]], limit: int = 12) -> str:
        if not items:
            body = "<p class=\"empty\">暂无。</p>"
        else:
            header = "".join(f"<th>{esc(label)}</th>" for label, _ in columns)
            rows = []
            for item in items[:limit]:
                cells = "".join(f"<td>{esc(item.get(key, ''))}</td>" for _, key in columns)
                rows.append(f"<tr>{cells}</tr>")
            body = f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        return f"<section><h2>{esc(title)}</h2>{body}</section>"

    duplicate_html = "<p class=\"empty\">暂无。</p>"
    if summary["duplicates"]:
        groups = []
        for group in summary["duplicates"]:
            paths = "".join(f"<li>{esc(path)}</li>" for path in group["paths"][:5])
            groups.append(
                f"<div class=\"dup\"><b>{esc(group['size_mb'])} MB x {esc(group['count'])}</b>"
                f"<code>{esc(group['sha256'][:24])}</code><ul>{paths}</ul></div>"
            )
        duplicate_html = "".join(groups)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>知识行动助手 · 文件雷达复盘</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --panel: #fffaf0;
      --ink: #27231d;
      --muted: #6c6254;
      --line: #decfb8;
      --accent: #0f6a5f;
      --warn: #a84d1d;
    }}
    body {{
      margin: 0;
      background: radial-gradient(circle at top left, #fff7d6 0, transparent 34rem), var(--bg);
      color: var(--ink);
      font-family: "LXGW WenKai", "Microsoft YaHei", "Noto Serif SC", serif;
      line-height: 1.55;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 42px 26px 72px;
    }}
    header {{
      border: 1px solid var(--line);
      background: linear-gradient(135deg, rgba(255,250,240,.95), rgba(235,244,239,.92));
      border-radius: 28px;
      padding: 34px;
      box-shadow: 0 20px 45px rgba(82, 66, 42, .12);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(30px, 4vw, 52px);
      letter-spacing: -.04em;
    }}
    .sub {{
      color: var(--muted);
      margin: 0;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
      gap: 14px;
      margin: 24px 0 10px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 16px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
    }}
    .metric strong {{
      display: block;
      margin-top: 4px;
      font-size: 28px;
      color: var(--accent);
    }}
    section {{
      margin-top: 22px;
      background: rgba(255,250,240,.88);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 22px;
      overflow-x: auto;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 22px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      white-space: nowrap;
    }}
    td:last-child {{
      word-break: break-all;
    }}
    code {{
      display: inline-block;
      margin: 6px 0;
      color: var(--warn);
      font-family: "Cascadia Mono", Consolas, monospace;
    }}
    .empty {{
      color: var(--muted);
    }}
    .dup {{
      padding: 12px 0;
      border-bottom: 1px solid var(--line);
    }}
    footer {{
      margin-top: 22px;
      color: var(--muted);
      font-size: 13px;
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>知识行动助手 · 文件雷达复盘</h1>
    <p class="sub">生成时间：{esc(summary["generated_at"])} | 模式：{esc(summary["mode"])} | 只做清单归档，不改源文件</p>
    <div class="metrics">{cards()}</div>
  </header>
  {table("按目录统计", summary["by_root"], [("目录", "root_name"), ("文件数", "files"), ("大小 MB", "size_mb")], 20)}
  {table("近期需要复盘", summary["classifications"]["recent_review"], [("目录", "root_name"), ("大小 MB", "size_mb"), ("修改时间", "modified_at"), ("路径", "path")])}
  {table("建议归档清单", summary["classifications"]["archive_candidates"], [("目录", "root_name"), ("天数", "age_days"), ("大小 MB", "size_mb"), ("路径", "path")])}
  {table("安装包 / 压缩包清理提醒", summary["classifications"]["installer_cleanup"], [("目录", "root_name"), ("天数", "age_days"), ("大小 MB", "size_mb"), ("路径", "path")])}
  {table("大文件提醒", summary["classifications"]["large_files"], [("目录", "root_name"), ("大小 MB", "size_mb"), ("路径", "path")])}
  <section><h2>重复文件组</h2>{duplicate_html}</section>
  <section><h2>安全策略</h2><p>本助手当前不删除、不移动、不改名源文件。它自动生成归档清单、复盘报告和提醒；物理搬迁文件需要后续单独启用白名单规则。</p></section>
  <footer>运行目录：{esc(summary["runtime_dir"])}</footer>
</main>
</body>
</html>
"""


def write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_obsidian_run_note(config: dict[str, Any], summary: dict[str, Any], markdown_report: Path, html_report: Path) -> Path:
    run_dir = Path(config["obsidian_run_dir"])
    date_part = summary["generated_at"][:10]
    note_path = run_dir / f"{date_part} 知识行动助手 文件雷达复盘.md"
    counts = summary["counts"]
    contents = "\n".join(
        [
            "# 知识行动助手 · 文件雷达复盘",
            "",
            f"生成时间：`{summary['generated_at']}`",
            "",
            "## 本次结果",
            "",
            f"- 扫描文件：`{summary['total_files']}`",
            f"- 近期复盘：`{counts['recent_review']}`",
            f"- 建议归档：`{counts['archive_candidates']}`",
            f"- 清理提醒：`{counts['installer_cleanup']}`",
            f"- 大文件：`{counts['large_files']}`",
            f"- 重复文件组：`{counts['duplicate_groups']}`",
            "",
            "## 报告路径",
            "",
            f"- Markdown：`{markdown_report}`",
            f"- HTML：`{html_report}`",
            "",
            "## 当前策略",
            "",
            "- 自动扫描、分类、生成清单。",
            "- 自动写 Obsidian 复盘。",
            "- 自动推送飞书卡片。",
            "- 不删除、不移动、不改名源文件。",
            "",
        ]
    )
    write_text(note_path, contents)
    return note_path


def run(config_path: Path, mode: str) -> dict[str, Any]:
    config = load_config(config_path)
    generated_at = now_local()
    run_dir = Path(config["runtime_root"]) / "runs" / generated_at.strftime("%Y-%m-%d") / generated_at.strftime("%H%M%S")
    records, warnings = build_records(config, generated_at)
    classifications = classify_records(records, config)
    duplicates = detect_duplicates(records, config)
    summary = build_summary(config, records, warnings, classifications, duplicates, mode, run_dir, generated_at)

    summary_json = run_dir / "summary.json"
    markdown_report = run_dir / "report.md"
    html_report = run_dir / "report.html"
    write_json(summary_json, summary)
    write_text(markdown_report, render_markdown(summary))
    write_text(html_report, render_html(summary))
    obsidian_note = write_obsidian_run_note(config, summary, markdown_report, html_report)

    summary.update(
        {
            "summary_json": str(summary_json),
            "markdown_report": str(markdown_report),
            "html_report": str(html_report),
            "obsidian_note": str(obsidian_note),
        }
    )
    write_json(summary_json, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="知识行动助手文件雷达")
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
        "html_report": summary["html_report"],
        "obsidian_note": summary["obsidian_note"],
        "total_files": summary["total_files"],
        "counts": summary["counts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
