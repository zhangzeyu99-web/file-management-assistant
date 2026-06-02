from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from config_loader import load_config

import assistant_evolution
import file_assistant
import scenario_playbook


PRODUCT = {
    "name": "本地知识整理助手",
    "tagline": "添加资料、搜索回顾、生成 AI 上下文包",
    "description": "把本地文件、Obsidian 笔记和 AI 对话整理成可归档、可回顾、可提取给 AI 续用的个人知识系统。",
}

SAFETY_TEXT = "安全边界：不删除源文件，只读取来源，只写新记录和运行证据；源文件保持原样。"
CORE_ACTIONS = ["organize", "review", "extract"]
DEPRECATED_ACTIONS = {"remind", "legacy-index"}
MAX_REVIEW_ITEMS = 1200
AI_IDENTITY_FILENAMES = [
    "AI_IDENTITY.md",
    "AI_COLLABORATION_RULES.md",
    "AI_CONTEXT_BOUNDARY.md",
]
READABLE_FILE_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".conf",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".log",
    ".md",
    ".ps1",
    ".py",
    ".rst",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
FILE_INDEX_EXCERPT_LIMIT = 12000
SEARCH_STOP_WORDS = {
    "找到",
    "我用",
    "用来",
    "这个",
    "那个",
    "一下",
    "什么",
    "怎么",
    "如何",
    "需要",
    "帮我",
    "继续",
    "当前",
    "任务",
    "资料",
    "内容",
    "问题",
    "哪里",
    "在哪里",
    "是什么",
}


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def runtime_root(config: dict[str, Any]) -> Path:
    return Path(config.get("runtime_root") or ".runtime").expanduser()


def vault_path(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_vault") or "demo-vault").expanduser()


def folder_name(config: dict[str, Any], key: str, default: str) -> str:
    return str(config.get("obsidian_folders", {}).get(key) or default)


def knowledge_root(config: dict[str, Any]) -> Path:
    configured = config.get("knowledge_root")
    if configured:
        return Path(str(configured)).expanduser()
    return vault_path(config) / folder_name(config, "routine", "04 例行工作") / "知识整理助手"


def section_dir(config: dict[str, Any], section: str) -> Path:
    path = knowledge_root(config) / section
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_dir(config: dict[str, Any], action: str, generated_at: dt.datetime | None = None) -> Path:
    stamp = (generated_at or now_local()).strftime("%Y-%m-%d/%H%M%S")
    path = runtime_root(config) / "knowledge-assistant" / stamp / action
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(value: str, fallback: str = "未命名") -> str:
    text = re.sub(r"[\\/:*?\"<>|\r\n]+", " ", value).strip()
    text = re.sub(r"\s+", " ", text)
    return (text or fallback)[:70]


def compact_text(text: str, limit: int = 180) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def strip_markdown_noise(text: str) -> str:
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        cleaned_lines.append(line)
    return " ".join(cleaned_lines)


def ai_identity_context(config: dict[str, Any]) -> dict[str, Any]:
    root = knowledge_root(config) / "AI 身份文件"
    files: list[dict[str, str]] = []
    for filename in AI_IDENTITY_FILENAMES:
        path = root / filename
        if not path.exists() or path.suffix.lower() != ".md":
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
        summary = compact_text(strip_markdown_noise(text), 260)
        if not summary:
            continue
        files.append({"title": path.stem, "path": str(path), "summary": summary})
    combined = "\n".join(f"- {item['title']}：{item['summary']}（来源：{item['path']}）" for item in files)
    return {"count": len(files), "files": files, "summary": combined}


def write_text(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def readable_file_excerpt(path: Path, limit: int = FILE_INDEX_EXCERPT_LIMIT) -> str:
    if path.suffix.lower() not in READABLE_FILE_EXTENSIONS:
        return ""
    try:
        raw = path.read_bytes()[: limit + 1024]
    except OSError:
        return ""
    if b"\x00" in raw:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="ignore")
    text = text.replace("\x00", "").strip()
    if not text:
        return ""
    clipped = text[:limit].rstrip()
    if len(text) > limit:
        clipped += "\n\n……（索引摘录已截断，源文件未改动）"
    return clipped


def is_readable_record(record: file_assistant.FileRecord) -> bool:
    return bool(readable_file_excerpt(Path(record.path), limit=512))


def split_local_paths(value: Any) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else str(value).replace(";", "\n").splitlines()
    paths: list[str] = []
    for item in raw:
        cleaned = str(item).strip().strip('"').strip("'")
        if cleaned:
            paths.append(cleaned)
    return list(dict.fromkeys(paths))


def split_source_paths(value: Any) -> list[str]:
    return split_local_paths(value)


def payload_text(payload: dict[str, Any]) -> str:
    for key in ("text", "body", "conversation", "content", "request", "query"):
        value = payload.get(key)
        if value:
            return str(value).strip()
    return ""


def infer_kind(payload: dict[str, Any]) -> str:
    kind = str(payload.get("kind") or payload.get("input_type") or "").strip().lower()
    if kind in {"text", "file", "files", "path", "ai", "chat", "conversation"}:
        return {"files": "file", "path": "file", "chat": "ai", "conversation": "ai"}.get(kind, kind)
    if split_local_paths(payload.get("local_paths") or payload.get("paths")):
        return "file"
    text = payload_text(payload)
    if any(token in text.lower() for token in ("assistant:", "user:", "codex", "openclaw", "chatgpt")):
        return "ai"
    return "text"


def classify_domain(value: str) -> dict[str, str]:
    domain = scenario_playbook.classify_domain(value)
    reason = "根据标题、正文或路径关键词自动建议领域；不确定时先按工作处理，后续可在 Obsidian 复盘时调整。"
    return {"id": str(domain["id"]), "name": str(domain["name"]), "description": str(domain["description"]), "reason": reason}


def markdown_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def artifact(kind: str, path: Path | None = None, label: str = "", content: str = "") -> dict[str, Any]:
    item: dict[str, Any] = {"type": kind, "label": label or kind}
    if path is not None:
        item["path"] = str(path)
    if content:
        item["content"] = content
    return item


def source_item(title: str, path: str = "", summary: str = "", kind: str = "note", why: str = "") -> dict[str, str]:
    return {
        "title": title,
        "path": path,
        "summary": compact_text(summary),
        "type": kind,
        "why": why or "与当前动作的关键词或来源匹配。",
    }


def comparable_path(value: str) -> str:
    path = Path(value).expanduser()
    try:
        return str(path.resolve()).lower()
    except OSError:
        return str(path.absolute()).lower()


def local_file_record(root_name: str, path: Path, reference: dt.datetime) -> file_assistant.FileRecord | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    modified = dt.datetime.fromtimestamp(stat.st_mtime, tz=reference.tzinfo)
    age_days = max(0.0, (reference - modified).total_seconds() / 86400)
    return file_assistant.FileRecord(
        root_name=root_name,
        path=str(path),
        extension=file_assistant.normalize_extension(path),
        size_bytes=int(stat.st_size),
        modified_at=modified.strftime("%Y-%m-%d %H:%M:%S %z"),
        age_days=round(age_days, 2),
    )


def scan_local_paths(config: dict[str, Any], local_paths: list[str], payload: dict[str, Any], generated_at: dt.datetime) -> dict[str, Any]:
    excluded = {str(name).lower() for name in config.get("exclude_dir_names", [])}
    max_depth = int(payload.get("max_depth") or 3)
    max_files = int(payload.get("max_files") or 2000)
    records: list[file_assistant.FileRecord] = []
    targets: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for raw_path in local_paths:
        target = Path(raw_path).expanduser()
        item: dict[str, Any] = {"path": str(target), "exists": target.exists(), "kind": "missing", "file_count": 0}
        if not target.exists():
            warnings.append(f"路径不存在：{target}")
            targets.append(item)
            continue
        if target.is_file():
            item.update({"kind": "file", "file_count": 1})
            candidates = [target]
        elif target.is_dir():
            candidates = file_assistant.iter_files(target, max_depth=max_depth, max_files=max_files, excluded_dirs=excluded)
            item.update({"kind": "directory", "file_count": len(candidates), "preview_files": [str(path) for path in candidates[:12]]})
        else:
            warnings.append(f"暂不支持的路径类型：{target}")
            targets.append(item)
            continue

        root_name = target.name or str(target)
        for file_path in candidates:
            key = str(file_path.resolve())
            if key in seen:
                continue
            seen.add(key)
            record = local_file_record(root_name, file_path, generated_at)
            if record:
                records.append(record)
        targets.append(item)

    classifications = file_assistant.classify_records(records, config)
    duplicates = file_assistant.detect_duplicates(records, config)
    counts = {
        "total_files": len(records),
        "total_size_mb": round(sum(item.size_bytes for item in records) / 1024 / 1024, 3),
        "recent_review": len(classifications["recent_review"]),
        "archive_candidates": len(classifications["archive_candidates"]),
        "installer_cleanup": len(classifications["installer_cleanup"]),
        "large_files": len(classifications["large_files"]),
        "screenshots": len(classifications["screenshots"]),
        "duplicate_groups": len(duplicates),
        "warnings": len(warnings),
    }
    return {
        "targets": targets,
        "records": records,
        "classifications": classifications,
        "duplicates": duplicates,
        "warnings": warnings,
        "counts": counts,
        "max_depth": max_depth,
        "max_files": max_files,
    }


def render_organize_scan_markdown(scan: dict[str, Any]) -> str:
    counts = scan["counts"]
    records: list[file_assistant.FileRecord] = scan["records"]
    lines = [
        "# 本地路径整理清单",
        "",
        "## 扫描概览",
        "",
        f"- 扫描文件：`{counts['total_files']}`",
        f"- 总大小：`{counts['total_size_mb']}` MB",
        f"- 近期需看：`{counts['recent_review']}`",
        f"- 建议归档：`{counts['archive_candidates']}`",
        f"- 安装包/压缩包清理候选：`{counts['installer_cleanup']}`",
        f"- 大文件：`{counts['large_files']}`",
        f"- 重复文件组：`{counts['duplicate_groups']}`",
        "",
        "## 扫描目标",
        "",
    ]
    for target in scan["targets"]:
        lines.append(f"- {target['path']}：{target['kind']}，{target['file_count']} 个文件")
    lines.extend(["", "## 文件清单（前 30 个）", ""])
    if records:
        lines.extend(["| 文件 | 类型 | 大小 MB | 修改时间 |", "| --- | --- | ---: | --- |"])
        for record in records[:30]:
            lines.append(f"| {Path(record.path).name} | {record.extension or '无'} | {record.size_mb} | {record.modified_at} |")
    else:
        lines.append("暂无可扫描文件。")
    lines.extend(["", "## 安全边界", "", "只生成整理建议和新记录，不会移动源文件、删除源文件、重命名源文件或重写源文件。"])
    if scan["warnings"]:
        lines.extend(["", "## 提示", ""])
        lines.extend(f"- {item}" for item in scan["warnings"])
    return "\n".join(lines) + "\n"


def render_file_index_markdown(
    record: file_assistant.FileRecord,
    excerpt: str,
    organize_note: Path,
    generated_at: dt.datetime,
) -> str:
    source_path = Path(record.path)
    return f"""# {source_path.stem}

类型：文件索引
生成时间：{generated_at.strftime("%Y-%m-%d %H:%M:%S %z")}
来源路径：`{record.path}`
关联整理记录：`{organize_note}`

## 文件信息

- 文件名：{source_path.name}
- 扩展名：{record.extension or "无"}
- 大小：{record.size_mb} MB
- 修改时间：{record.modified_at}

## 文件摘要

{compact_text(excerpt, 360)}

## 原文摘录

```text
{excerpt}
```

## 下次怎么用

- 搜索回顾时可以直接用文件名、路径或摘录里的关键词找到这条索引。
- 生成 AI 上下文包时优先引用这条索引，再决定是否需要读取源文件全文。

## 安全边界

{SAFETY_TEXT}
"""


def write_file_index_notes(
    config: dict[str, Any],
    scan: dict[str, Any],
    organize_note: Path,
    generated_at: dt.datetime,
) -> list[Path]:
    index_dir = section_dir(config, "文件索引")
    created: list[Path] = []
    for index, record in enumerate(scan["records"], start=1):
        source_path = Path(record.path)
        excerpt = readable_file_excerpt(source_path)
        if not excerpt:
            continue
        filename = f"{generated_at.strftime('%Y%m%d-%H%M%S')}-{index:03d} {safe_filename(source_path.stem, '文件索引')}.md"
        note_path = index_dir / filename
        write_text(note_path, render_file_index_markdown(record, excerpt, organize_note, generated_at))
        created.append(note_path)
    return created


def unified_result(
    action: str,
    summary: str,
    sources: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    next_actions: list[str] | None = None,
    debug: dict[str, Any] | None = None,
    ok: bool = True,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "action": action,
        "summary": summary,
        "sources": sources or [],
        "artifacts": artifacts or [],
        "next_actions": next_actions or [],
        "safety": SAFETY_TEXT,
        "debug": debug or {},
    }


def organize(config: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    generated_at = now_local()
    kind = infer_kind(payload)
    text = payload_text(payload)
    local_paths = split_local_paths(payload.get("local_paths") or payload.get("paths") or payload.get("target_path"))
    selected_files = payload.get("selected_files") if isinstance(payload.get("selected_files"), list) else []
    if not text and not local_paths and not selected_files:
        return unified_result(
            "organize",
            "没有提供可整理的内容。请粘贴资料、AI 对话摘要，或提供本地文件/目录路径。",
            sources=[],
            artifacts=[],
            next_actions=["粘贴一段资料", "输入本地文件或目录路径", "先用回顾知识查已有内容"],
            debug={"reason": "empty_input"},
            ok=False,
        )
    combined = "\n".join([text, *local_paths, *(str(item.get("name", "")) for item in selected_files if isinstance(item, dict))])
    domain = classify_domain(combined)
    title = safe_filename(str(payload.get("title") or text or (local_paths[0] if local_paths else "整理记录")), "整理记录")
    note_path = section_dir(config, "整理") / f"{generated_at.strftime('%Y%m%d-%H%M%S')} {title}.md"
    sources: list[dict[str, Any]] = []
    if text:
        sources.append(source_item("输入文本", str(payload.get("source") or "手动输入"), text, kind))
    for raw_path in local_paths:
        path = Path(raw_path)
        exists = path.exists()
        sources.append(source_item(path.name or str(path), str(path), "本地路径存在" if exists else "本地路径暂未找到", "file", "整理入口提供的本地文件或目录。"))
    for item in selected_files[:20]:
        if isinstance(item, dict):
            sources.append(
                source_item(
                    str(item.get("name") or "选择文件"),
                    str(item.get("relative_path") or ""),
                    f"浏览器选择/拖放文件元数据，大小 {item.get('size', 0)} bytes；未获得可扫描的本机完整路径。",
                    "file-metadata",
                    "浏览器文件选择只提供元数据，不等于已扫描本机目录。",
                )
            )
    if selected_files and not text and not local_paths:
        return unified_result(
            "organize",
            "浏览器选择/拖放只提供文件名、大小和相对路径，不能代表已扫描本机目录。请粘贴完整本地路径，或补充要整理的文本内容。",
            sources=sources,
            artifacts=[],
            next_actions=["粘贴完整本地路径", "补充资料正文", "点击检查本地目标确认路径是否存在"],
            debug={"reason": "metadata_only", "selected_file_count": len(selected_files)},
            ok=False,
        )
    scan: dict[str, Any] | None = None
    scan_report: Path | None = None
    scan_manifest: Path | None = None
    file_index_notes: list[Path] = []
    if local_paths:
        scan = scan_local_paths(config, local_paths, payload, generated_at)
        existing_targets = [item for item in scan["targets"] if item.get("exists")]
        if not text and not existing_targets:
            return unified_result(
                "organize",
                "路径不存在，无法生成真实整理清单。请检查路径是否完整，或先粘贴资料正文。",
                sources=sources,
                artifacts=[],
                next_actions=["重新粘贴完整本地路径", "点击检查本地目标", "确认路径没有被转义或截断"],
                debug={"reason": "no_existing_local_paths", "scan": scan["counts"], "warnings": scan["warnings"]},
                ok=False,
            )
        scan_dir = run_dir(config, "organize", generated_at)
        scan_report = write_text(scan_dir / "整理清单.md", render_organize_scan_markdown(scan))
        scan_manifest = write_json(
            scan_dir / "整理清单.json",
            {
                "targets": scan["targets"],
                "counts": scan["counts"],
                "classifications": scan["classifications"],
                "duplicates": scan["duplicates"],
                "warnings": scan["warnings"],
            },
        )
        for record in scan["records"][:8]:
            sources.append(
                source_item(
                    Path(record.path).name,
                    record.path,
                    f"{record.extension or '无扩展名'}，{record.size_mb} MB，修改时间 {record.modified_at}",
                    "file",
                    "来自本地路径扫描；只记录来源和整理建议，不改动源文件。",
                )
            )

    suggestion = {
        "text": "先保留来源，写入知识整理助手；后续复盘时再决定是否提升到项目、学习资料或归档。",
        "target": "04 例行工作\\知识整理助手\\整理",
        "domain": domain["name"],
        "reason": domain["reason"],
    }
    scan_section = ""
    if scan:
        counts = scan["counts"]
        target_lines = "\n".join(f"- {item['path']}：{item['kind']}，{item['file_count']} 个文件" for item in scan["targets"])
        scanned_files = "\n".join(f"- {Path(record.path).name}：{record.path}" for record in scan["records"][:30]) or "- 暂无可扫描文件。"
        scan_section = f"""
## 路径扫描结果

- 扫描文件：`{counts["total_files"]}`
- 总大小：`{counts["total_size_mb"]}` MB
- 近期需看：`{counts["recent_review"]}`
- 建议归档：`{counts["archive_candidates"]}`
- 大文件：`{counts["large_files"]}`
- 重复文件组：`{counts["duplicate_groups"]}`

### 扫描目标

{target_lines}

### 文件清单（前 30 个）

{scanned_files}

### 本轮边界

本轮只生成整理建议和新记录，不会移动源文件、删除源文件、重命名源文件或重写源文件。
"""
    note = f"""# {title}

类型：整理
输入类型：{kind}
领域：{domain["name"]}
来源：{payload.get("source") or "GUI / CLI"}
生成时间：{generated_at.strftime("%Y-%m-%d %H:%M:%S %z")}

## 生活 / 学习 / 工作 判断

- 建议领域：{domain["name"]}
- 理由：{domain["reason"]}

## 来源

{chr(10).join(f"- {item['title']}：{item.get('path') or item.get('summary')}" for item in sources)}

## 原始内容

{text or "见来源路径。"}

{scan_section}

## 归档建议

- 建议位置：{suggestion["target"]}
- 建议动作：{suggestion["text"]}

## 下一步

- 如果这是一项具体任务，继续写 Action。
- 如果这是可复用经验，继续沉淀为 Card。
- 如果要交给 AI 继续处理，使用“提取上下文”生成 AI 上下文包。

## 安全边界

{SAFETY_TEXT}
"""
    write_text(note_path, note)
    if scan:
        file_index_notes = write_file_index_notes(config, scan, note_path, generated_at)
        if scan_manifest:
            write_json(
                scan_manifest,
                {
                    "targets": scan["targets"],
                    "counts": scan["counts"],
                    "classifications": scan["classifications"],
                    "duplicates": scan["duplicates"],
                    "warnings": scan["warnings"],
                    "file_index_notes": [str(path) for path in file_index_notes],
                },
            )
    summary = f"整理记录已写入 Obsidian：{title}；建议领域：{domain['name']}。"
    artifacts = [artifact("obsidian-note", note_path, "打开整理记录")]
    debug: dict[str, Any] = {"kind": kind, "domain": domain, "suggestion": suggestion}
    next_actions = ["回顾相关知识", "提取 AI 上下文包", "需要时在 Obsidian 中手动归位"]
    if scan:
        total_files = scan["counts"]["total_files"]
        index_summary = f"生成 {len(file_index_notes)} 条文件索引；" if file_index_notes else ""
        summary = f"整理记录已写入 Obsidian：{title}；已扫描 {total_files} 个文件，生成整理清单；{index_summary}默认只建议，不移动源文件。"
        if scan_report:
            artifacts.append(artifact("markdown", scan_report, "打开路径整理清单"))
        if scan_manifest:
            artifacts.append(artifact("json", scan_manifest, "打开路径整理 manifest"))
        if file_index_notes:
            artifacts.append(artifact("file-index", file_index_notes[0], "打开首条文件索引"))
            artifacts.append(artifact("file-index-directory", file_index_notes[0].parent, "打开文件索引目录"))
        debug["scan"] = {key: value for key, value in scan["counts"].items()}
        debug["file_index_count"] = len(file_index_notes)
        debug["file_index_notes"] = [str(path) for path in file_index_notes]
        next_actions = ["打开路径整理清单", "按建议归档到生活/学习/工作", "需要继续问 AI 时提取上下文包"]
    result = unified_result(
        "organize",
        summary,
        sources=sources,
        artifacts=artifacts,
        next_actions=next_actions,
        debug=debug,
    )
    return result


def iter_markdown_notes(config: dict[str, Any]) -> list[Path]:
    project_root = vault_path(config) / folder_name(config, "projects", "02 项目")
    codex_root = project_root / folder_name(config, "codex_project", "Codex")
    roots = [
        codex_root,
        project_root / "知识行动助手",
        knowledge_root(config),
        vault_path(config) / folder_name(config, "routine", "04 例行工作") / "知识行动助手",
        Path(config.get("obsidian_run_dir") or knowledge_root(config)),
        runtime_root(config) / "runs",
        runtime_root(config) / "knowledge-assistant",
        vault_path(config),
    ]
    seen: set[str] = set()
    notes: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            notes.append(path)
    return notes


def iter_watch_markdown_notes(config: dict[str, Any]) -> list[Path]:
    notes: list[Path] = []
    seen: set[str] = set()
    for root_config in config.get("watch_roots", []):
        root = Path(str(root_config.get("path") or "")).expanduser()
        if not root.exists() or not root.is_dir():
            continue
        max_depth = int(root_config.get("max_depth") or 3)
        max_files = int(root_config.get("max_files") or 500)
        count = 0
        base_depth = len(root.parts)
        for path in sorted(root.rglob("*"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
            if count >= max_files:
                break
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
                continue
            if len(path.parts) - base_depth > max_depth:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            notes.append(path)
            count += 1
    return notes


def build_review_index(config: dict[str, Any], limit: int = MAX_REVIEW_ITEMS) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in [*iter_markdown_notes(config), *iter_watch_markdown_notes(config)]:
        if len(items) >= limit:
            break
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
        kind = "note"
        parts = set(path.parts)
        if "文件索引" in parts:
            kind = "file-index"
        elif "整理" in parts:
            kind = "organize"
        elif "提取" in parts:
            kind = "extract"
        elif "Codex" in parts:
            kind = "legacy-codex"
        elif any(str(path).startswith(str(Path(str(root.get("path") or "")).expanduser())) for root in config.get("watch_roots", [])):
            kind = "external-file"
        items.append(
            {
                "title": markdown_title(text, path.stem),
                "path": str(path),
                "summary": compact_text(text, 260),
                "raw_markdown": text,
                "type": kind,
                "modified_at": dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
            }
        )
    return items


def query_tokens(query: str) -> list[str]:
    normalized = query.lower()
    tokens: list[str] = []

    def add(token: str) -> None:
        cleaned = token.strip().lower()
        if not cleaned or cleaned in SEARCH_STOP_WORDS or cleaned in tokens:
            return
        if re.fullmatch(r"[a-z0-9_.#@+-]+", cleaned) and len(cleaned) < 2:
            return
        tokens.append(cleaned)

    for token in re.findall(r"[a-z0-9_.#@+-]+[一-鿿]+|[一-鿿]+[a-z0-9_.#@+-]+", normalized):
        add(token)
    for token in re.findall(r"[a-z0-9_.#@+-]{2,}", normalized):
        add(token)
    concept_aliases = {
        "文件管理助手": ["file-management-assistant"],
        "知识整理助手": ["file-management-assistant"],
        "知识行动助手": ["file-management-assistant"],
    }
    for phrase, aliases in concept_aliases.items():
        if phrase in normalized:
            for alias in aliases:
                add(alias)
    for segment in re.findall(r"[一-鿿]{2,}", normalized):
        for keyword in ["启动", "流程", "仓库", "脚本", "安装", "桌面", "归档", "会话", "记忆", "项目", "索引", "报告", "教程", "路径", "文件", "地址", "位置", "可执行"]:
            if keyword in segment:
                add(keyword)
        if len(segment) <= 8:
            add(segment)
        for size in (4, 3, 2):
            for index in range(0, max(0, len(segment) - size + 1)):
                add(segment[index : index + size])
    return tokens


def normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", "", value.lower())


def split_mixed_token(token: str) -> list[str]:
    parts: list[str] = []
    parts.extend(re.findall(r"[一-鿿]{2,}", token))
    parts.extend(re.findall(r"[a-z0-9_.#@+-]{2,}", token.lower()))
    return parts or [token.lower()]


def compact_query_text(query: str) -> str:
    return normalize_match_text(re.sub(r"[？?。！!，,；;：:（）()【】\\[\\]\"'`]+", "", query))


def is_short_mixed_query(query: str) -> bool:
    compacted = compact_query_text(query)
    return bool(re.fullmatch(r"[一-鿿]{2,}[a-z0-9_.#@+-]{2,}|[a-z0-9_.#@+-]{2,}[一-鿿]{2,}", compacted))


def important_query_terms(query: str) -> list[str]:
    tokens = query_tokens(query)
    query_lower = query.lower()
    keep_keywords = {
        "github",
        "codex",
        "obsidian",
        "notebooklm",
        "sop",
        "启动",
        "脚本",
        "仓库",
        "可执行",
        "路径",
        "简历",
        "线程",
        "运营",
        "助手",
        "上下文",
        "入库",
        "记忆仓",
        "学习",
        "教程",
    }
    terms: list[str] = []
    def add_term(raw: str) -> None:
        lowered = raw.lower().strip()
        lowered = re.sub(r"(是什么|在哪里|在哪|哪里|怎么用|如何用)$", "", lowered)
        lowered = re.sub(r"^(继续|帮我|请|找到|搜索|回顾|查找)", "", lowered)
        lowered = lowered.strip("的了吗呢啊")
        if lowered in SEARCH_STOP_WORDS:
            return
        if lowered in {"地址", "位置", "流程", "文件", "记录"}:
            return
        if re.fullmatch(r"[a-z0-9_.#@+-]{2,}", lowered):
            terms.append(lowered)
            return
        if "文件管理助手" in lowered:
            terms.append("文件管理助手")
            terms.append("file-management-assistant")
            return
        found_keyword = False
        for keyword in sorted(keep_keywords, key=len, reverse=True):
            if keyword in lowered:
                terms.append(keyword)
                found_keyword = True
        if found_keyword:
            return
        return

    source_tokens = split_mixed_token(compact_query_text(query)) if is_short_mixed_query(query) else tokens
    for token in source_tokens:
        lowered = token.lower()
        if re.search(r"[一-鿿]", lowered) and re.search(r"[a-z0-9_.#@+-]", lowered):
            for part in split_mixed_token(lowered):
                add_term(part)
            continue
        add_term(lowered)
    for phrase, aliases in {
        "文件管理助手": ["文件管理助手", "file-management-assistant"],
        "知识整理助手": ["文件管理助手", "file-management-assistant"],
        "知识行动助手": ["文件管理助手", "file-management-assistant"],
    }.items():
        if phrase in query_lower:
            terms.extend(aliases)
    reduced: list[str] = []
    for term in sorted(dict.fromkeys(terms), key=len, reverse=True):
        if any(term != other and term in other for other in reduced):
            continue
        reduced.append(term)
    return sorted(reduced, key=lambda item: tokens.index(item) if item in tokens else 999)


def text_contains_term(text: str, term: str) -> bool:
    lowered_text = text.lower()
    if term in {"路径", "地址", "位置"} and (re.search(r"[A-Za-z]:\\", text) or re.search(r"https?://", lowered_text)):
        return True
    if term == "可执行" and ".exe" in lowered_text:
        return True
    if term == "教程" and re.search(r"\b(tutorial|guide|getting-started)\b", lowered_text):
        return True
    if re.fullmatch(r"[a-z0-9_.#@+-]+", term):
        return term in lowered_text
    return normalize_match_text(term) in normalize_match_text(text)


def matched_terms_in_text(terms: list[str], text: str) -> list[str]:
    return [term for term in terms if text_contains_term(text, term)]


def query_wants_path_evidence(terms: list[str]) -> bool:
    return any(term in {"路径", "地址", "位置", "仓库", "github", "可执行", "启动", "脚本"} for term in terms)


def evidence_units(item: dict[str, Any]) -> list[tuple[str, str, int]]:
    units: list[tuple[str, str, int]] = [
        ("标题", str(item.get("title") or ""), 35),
        ("路径", str(item.get("path") or ""), 22),
    ]
    raw = str(item.get("raw_markdown") or item.get("summary") or "")
    for line in raw.splitlines():
        cleaned = clean_evidence_line(line)
        if not cleaned or cleaned.startswith("#") or is_evidence_metadata_line(cleaned):
            continue
        units.append(("正文", cleaned, 16))
    summary = str(item.get("summary") or "")
    if summary:
        units.append(("摘要", summary, 8))
    return units


def is_negated_evidence(text: str, terms: list[str]) -> bool:
    normalized = normalize_match_text(text)
    for term in terms:
        term_text = normalize_match_text(term)
        if f"没有{term_text}" in normalized or f"无{term_text}" in normalized or f"不是{term_text}" in normalized:
            return True
    return False


def source_priority(item: dict[str, Any]) -> int:
    path = str(item.get("path") or "").lower()
    kind = str(item.get("type") or "")
    score = {
        "file-index": 28,
        "legacy-codex": 22,
        "organize": 18,
        "extract": 14,
        "external-file": 12,
        "note": 10,
    }.get(kind, 8)
    if "\\runs\\" in path or "/runs/" in path:
        score -= 18
    if "旧资料二次整理索引" in path or "report.md" in path:
        score -= 8
    if "\\文件索引\\" in path or "/文件索引/" in path:
        score += 10
    if "\\02 项目\\codex\\" in path or "/02 项目/codex/" in path:
        score += 8
    return score


def strict_match_for_item(query: str, item: dict[str, Any]) -> dict[str, Any] | None:
    terms = important_query_terms(query)
    if not terms:
        return None
    full_text = "\n".join(str(item.get(key, "")) for key in ("title", "path", "summary", "raw_markdown"))
    document_terms = matched_terms_in_text(terms, full_text)
    if set(document_terms) != set(terms):
        return None
    short_mixed = is_short_mixed_query(query)
    query_phrase = compact_query_text(query) if short_mixed else ""
    wants_path_evidence = query_wants_path_evidence(terms)
    candidates: list[dict[str, Any]] = []
    for field, text, base_score in evidence_units(item):
        if short_mixed and field == "摘要":
            continue
        if not wants_path_evidence and (field == "路径" or re.search(r"[A-Za-z]:\\", text)):
            continue
        unit_terms = matched_terms_in_text(terms, text)
        if not unit_terms:
            continue
        if is_negated_evidence(text, terms):
            continue
        normalized_unit = normalize_match_text(text)
        has_exact_phrase = bool(query_phrase and query_phrase in normalized_unit)
        has_all_terms_in_unit = set(unit_terms) == set(terms)
        if short_mixed and not (has_exact_phrase or has_all_terms_in_unit):
            continue
        score = base_score + source_priority(item) + len(unit_terms) * 12
        if has_exact_phrase:
            score += 80
        if has_all_terms_in_unit:
            score += 45
        if field == "正文" and len(text) >= 18:
            score += 70
        if field == "正文" and (re.search(r"\d", text) or re.search(r"[A-Za-z]:\\", text)):
            score += 18
        wants_executable_path = "可执行" in terms or "exe" in terms or ("codex" in terms and "路径" in terms)
        if wants_executable_path and ".exe" in text.lower():
            score += 180
        elif wants_executable_path and field == "正文" and "真实 exe" in text.lower():
            score -= 90
        elif wants_executable_path and field == "正文" and ".exe" not in text.lower() and not re.search(r"[A-Za-z]:\\", text):
            score -= 45
        if field == "标题" and len(text) <= 24:
            score -= 30
        score += evidence_line_score(query, text)
        candidates.append(
            {
                "score": score,
                "field": field,
                "text": format_direct_evidence(text),
                "matched_terms": unit_terms,
                "has_exact_phrase": has_exact_phrase,
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda value: (value["score"], -len(value["text"])), reverse=True)
    best = candidates[0]
    return {
        "score": int(best["score"]),
        "matched_terms": document_terms,
        "evidence_terms": best["matched_terms"],
        "evidence_excerpt": best["text"],
        "evidence_field": best["field"],
        "has_exact_phrase": bool(best["has_exact_phrase"]),
    }


def score_item(query: str, item: dict[str, Any]) -> int:
    match = strict_match_for_item(query, item)
    return int(match["score"]) if match else 0


def evidence_line_score(query: str, line: str) -> int:
    lowered = line.lower()
    tokens = query_tokens(query)
    score = sum(2 for token in tokens if token in lowered)
    has_url = bool(re.search(r"https?://\S+", line))
    has_windows_path = bool(re.search(r"[A-Za-z]:\\[^\s`，。；）)]+", line))
    has_executable = bool(re.search(r"\.(?:cmd|exe|ps1|bat|md)\b", lowered))
    if has_url:
        score += 5
    if has_windows_path:
        score += 4
    if has_executable:
        score += 3
    wants_repo_url = "github" in tokens or "仓库" in tokens or "地址" in tokens
    if wants_repo_url and ("github" in lowered or has_url):
        score += 8
    if wants_repo_url and has_url:
        score += 20
    if wants_repo_url and has_windows_path and not has_url:
        score -= 18
    if "github" in tokens and "github" not in lowered and not has_url:
        score -= 10
    wants_script = "启动" in tokens or "脚本" in tokens
    if wants_script and ("启动" in line or "脚本" in line or ".cmd" in lowered or ".ps1" in lowered):
        score += 8
    if wants_script and (".cmd" in lowered or ".ps1" in lowered):
        score += 30
    wants_executable_path = "可执行" in tokens or ("文件" in tokens and "路径" in tokens)
    if wants_executable_path and (".exe" in lowered or "可执行" in line):
        score += 8
    if wants_executable_path and ".exe" in lowered:
        score += 40
    # Aggregated index summaries are useful fallbacks, but they often bury the
    # concrete URL/path after enough prose that the result card truncates it.
    if lowered.startswith("摘要："):
        score -= 30
    if len(line) > 240:
        score -= 4
    return score


def query_entity_tokens(query: str) -> list[str]:
    generic = {"github", "http", "https", "www", "com"}
    entities: list[str] = []
    for token in query_tokens(query):
        if token in generic:
            continue
        if re.fullmatch(r"[a-z0-9_.#@+-]{4,}", token):
            entities.append(token)
    return entities


def entity_token_matches(token: str, text: str) -> bool:
    lowered = text.lower()
    if token == "codex":
        if "codexdesktop" in lowered or "codex.exe" in lowered or "start-codex" in lowered:
            return True
        return bool(re.search(r"(?<![a-z0-9_\\/-])codex(?![a-z0-9_\\/-])", lowered))
    return token in lowered


def clean_evidence_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"^[-*]\s*", "", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    path_match = re.search(r"[A-Za-z]:\\[^`，。；\r\n]+", cleaned)
    if path_match:
        path_text = re.split(r"[：，。；]", path_match.group(0), maxsplit=1)[0].strip()
        if path_text:
            return path_text
    return cleaned


def is_evidence_metadata_line(line: str) -> bool:
    stripped = re.sub(r"^[-*]\s*", "", line.strip())
    return stripped.startswith(("关联整理记录", "生成时间：", "类型："))


def format_direct_evidence(line: str) -> str:
    if re.fullmatch(r"[A-Za-z]:\\.+", line):
        return line
    return compact_text(line, 140)


def normalize_openable_paths_in_text(text: str) -> str:
    def replace_path(match: re.Match[str]) -> str:
        return re.split(r"[：，。；]", match.group(0), maxsplit=1)[0].strip()

    return re.sub(r"[A-Za-z]:\\[^`，。；\r\n]+", replace_path, text)


def extract_direct_answers(query: str, matches: list[dict[str, Any]], limit: int = 4) -> list[str]:
    if not query.strip():
        return []
    candidates: list[tuple[int, int, str, str]] = []
    seen: set[str] = set()
    entity_tokens = query_entity_tokens(query)
    for item in matches:
        title = str(item.get("title") or "来源")
        raw = str(item.get("raw_markdown") or item.get("summary") or "")
        for line in raw.splitlines():
            if is_evidence_metadata_line(line):
                continue
            cleaned = clean_evidence_line(line)
            if not cleaned or cleaned.startswith("#") or len(cleaned) < 6:
                continue
            combined = f"{title}\n{cleaned}".lower()
            if entity_tokens and not any(entity_token_matches(token, combined) for token in entity_tokens):
                continue
            score = evidence_line_score(query, cleaned)
            if score < 6:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append((score, -len(cleaned), title, format_direct_evidence(cleaned)))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [f"{title}：{format_direct_evidence(line)}" for _, _, title, line in candidates[:limit]]


def direct_evidence_for_item(query: str, item: dict[str, Any], limit: int = 2) -> list[str]:
    strict = strict_match_for_item(query, item)
    if strict and strict.get("evidence_excerpt"):
        return [str(strict["evidence_excerpt"])]
    title = str(item.get("title") or "来源")
    prefix = f"{title}："
    evidence: list[str] = []
    for answer in extract_direct_answers(query, [item], limit=limit):
        evidence.append(answer[len(prefix) :] if answer.startswith(prefix) else answer)
    return evidence


def best_evidence_score_for_item(query: str, item: dict[str, Any]) -> int:
    strict = strict_match_for_item(query, item)
    if strict:
        return int(strict["score"])
    title = str(item.get("title") or "来源")
    raw = str(item.get("raw_markdown") or item.get("summary") or "")
    entity_tokens = query_entity_tokens(query)
    best = 0
    for line in raw.splitlines():
        if is_evidence_metadata_line(line):
            continue
        cleaned = clean_evidence_line(line)
        if not cleaned or cleaned.startswith("#") or len(cleaned) < 6:
            continue
        combined = f"{title}\n{cleaned}".lower()
        if entity_tokens and not any(entity_token_matches(token, combined) for token in entity_tokens):
            continue
        best = max(best, evidence_line_score(query, cleaned))
    return best


def source_item_from_review_match(query: str, item: dict[str, Any], why: str = "") -> dict[str, str]:
    strict = strict_match_for_item(query, item) or {}
    evidence = direct_evidence_for_item(query, item)
    summary = normalize_openable_paths_in_text(str(item.get("summary") or ""))
    if evidence:
        summary = f"直接线索：{'；'.join(evidence)}。{summary}"
    source = source_item(
        str(item["title"]),
        str(item["path"]),
        summary,
        str(item["type"]),
        why or (f"直接线索：{'；'.join(evidence)}" if evidence else f"与“{query}”在标题、路径或正文片段上匹配。"),
    )
    if evidence:
        source["direct_evidence"] = evidence[0]
    if strict:
        source["matched_terms"] = list(strict.get("matched_terms") or [])
        source["evidence_excerpt"] = str(strict.get("evidence_excerpt") or evidence[0] if evidence else "")
        source["evidence_field"] = str(strict.get("evidence_field") or "")
        source["match_score"] = str(strict.get("score") or "")
    return source


def context_matches_for_query(config: dict[str, Any], query: str, limit: int = 8) -> tuple[list[dict[str, Any]], int]:
    index = build_review_index(config)
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for item in index:
        score = score_item(query, item)
        if score <= 0:
            continue
        scored.append((score, str(item.get("modified_at", "")), item))
    ranked = [item for _, _, item in sorted(scored, key=lambda value: (value[0], value[1]), reverse=True)]
    return dedupe_review_items(ranked, limit), len(index)


def dedupe_review_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        title = re.sub(r"\s+", " ", str(item.get("title", "")).strip().lower())
        path = str(item.get("path", "")).lower()
        key = title or path
        if not key or key in seen:
            continue
        seen.add(key)
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


def sources_from_confirmed_paths(config: dict[str, Any], source_paths: list[str], query: str = "") -> list[dict[str, Any]]:
    if not source_paths:
        return []
    index = build_review_index(config)
    by_path = {comparable_path(str(item.get("path", ""))): item for item in index if item.get("path")}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_path in source_paths:
        key = comparable_path(raw_path)
        if key in seen:
            continue
        seen.add(key)
        item = by_path.get(key)
        if not item:
            continue
        selected.append(source_item_from_review_match(query, item, "用户确认用于生成本次 AI 上下文包的来源。"))
    return selected


def review(config: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    query = str(payload.get("query") or payload.get("text") or payload.get("question") or "").strip()
    if not query:
        result = unified_result(
            "review",
            "请输入关键词或问题。搜索回顾只做证据检索，不会用最近内容伪装成答案。",
            sources=[],
            artifacts=[],
            next_actions=["输入一个关键词", "先添加资料", "描述要生成的 AI 上下文包"],
            debug={"reason": "empty_query"},
            ok=False,
        )
        result["status"] = "not_found"
        result["answer"] = "没有找到：请输入关键词或问题。"
        return result

    matches, index_count = context_matches_for_query(config, query, 8)
    sources = [source_item_from_review_match(query, item) for item in matches]
    if sources:
        first = sources[0]
        evidence = first.get("evidence_excerpt") or first.get("direct_evidence") or first.get("summary", "")
        answer = f"找到的是：{first['title']}。关键依据：{compact_text(evidence, 180)}"
        lead = "；".join(f"{index + 1}. {item['title']}" for index, item in enumerate(sources[:5]))
        matched = "、".join(str(term) for term in first.get("matched_terms", []))
        summary = f"{answer}。命中词：{matched or query}。推荐阅读顺序：{lead}。"
        next_actions = ["基于这些证据生成 AI 上下文包", "打开首条来源核对", "添加补充资料"]
        status = "found_answer"
    else:
        answer = f"没有找到：已整理资料中没有命中“{query}”的可靠证据。"
        summary = f"{answer} 建议先添加相关资料，或换一个更具体的关键词。"
        next_actions = ["换一个更具体的关键词", "添加一条相关资料", "检查 Obsidian 是否已有对应笔记"]
        status = "not_found"
    result = unified_result(
        "review",
        summary,
        sources=sources,
        artifacts=[],
        next_actions=next_actions,
        debug={
            "query": query,
            "index_count": index_count,
            "tokens": query_tokens(query),
            "important_terms": important_query_terms(query),
            "reading_order": [item.get("path", "") for item in sources],
            "direct_answers": extract_direct_answers(query, matches) if sources else [],
        },
        ok=bool(sources),
    )
    result["status"] = status
    result["answer"] = answer
    return result


def render_context_markdown(
    request: str,
    sources: list[dict[str, Any]],
    prompt: str,
    generated_at: dt.datetime,
    identity: dict[str, Any] | None = None,
) -> str:
    source_lines = "\n".join(
        f"- [{item.get('type', 'note')}] {item.get('title', '')}\n"
        f"  直接线索：{item.get('direct_evidence') or item.get('summary', '')}\n"
        f"  摘要：{item.get('summary', '')}\n"
        f"  来源：{item.get('path', '')}"
        for item in sources
    )
    identity = identity or {"count": 0, "summary": ""}
    identity_summary = str(identity.get("summary") or "").strip()
    identity_section = identity_summary or "- 未发现 AI 身份文件；仅使用本次确认来源。"
    return f"""# AI 上下文包

生成时间：{generated_at.strftime("%Y-%m-%d %H:%M:%S %z")}
当前需求：{request}

## 来源摘要

{source_lines or "- 暂无匹配来源。"}

## AI 身份文件摘要

{identity_section}

## 可复制 Prompt

```text
{prompt}
```

## 安全边界

{SAFETY_TEXT}
"""


def extract(config: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    generated_at = now_local()
    identity = ai_identity_context(config)
    mode = str(payload.get("mode") or "generate").strip().lower()
    if mode not in {"preview", "generate"}:
        mode = "generate"
    query = str(payload.get("query") or payload.get("text") or payload.get("request") or "当前任务").strip()
    request = str(payload.get("request") or payload.get("text") or query).strip()
    source_paths = split_source_paths(payload.get("source_paths") or payload.get("confirmed_source_paths"))
    if source_paths:
        sources = sources_from_confirmed_paths(config, source_paths, query)
        if not sources:
            result = unified_result(
                "extract",
                "没有找到已确认来源。请重新预览来源，或确认传入的来源路径仍在知识库中。",
                sources=[],
                artifacts=[],
                next_actions=["重新预览候选来源", "复制有效来源路径", "先搜索回顾确认来源存在"],
                debug={"query": query, "request": request, "mode": mode, "source_paths": source_paths, "reason": "confirmed_sources_not_found"},
                ok=False,
            )
            result["status"] = "not_found"
            result["answer"] = "没有找到已确认来源，不能生成 AI 上下文包。"
            return result
    else:
        matches, _index_count = context_matches_for_query(config, query, 8)
        sources = [
            source_item_from_review_match(query, item, f"与“{query}”在标题、路径或正文片段上匹配。")
            for item in matches
        ]
    if not sources:
        result = unified_result(
            "extract",
            f"没有找到可用上下文：{safe_filename(query, '当前任务')}。请先整理相关资料、换更具体的关键词，或在回顾结果中确认来源。",
            sources=[],
            artifacts=[],
            next_actions=["先整理相关资料", "换更具体的关键词回顾知识", "确认 Obsidian 中是否已有对应笔记"],
            debug={"query": query, "request": request, "mode": mode, "reason": "no_matching_sources"},
            ok=False,
        )
        result["status"] = "not_found"
        result["answer"] = f"没有找到可用于“{safe_filename(query, '当前任务')}”的证据来源。"
        return result
    if mode == "preview":
        first = sources[0]
        identity_hint = "AI 身份文件已可用，将在确认生成时作为偏好和边界摘要写入上下文包。" if identity["count"] else "未发现 AI 身份文件；确认生成时只使用证据来源。"
        result = unified_result(
            "extract",
            f"找到 {len(sources)} 条候选来源。首选来源：{first.get('title', '未命名来源')}。{identity_hint} 请先检查来源是否相关，再确认生成 AI 上下文包。",
            sources=sources,
            artifacts=[],
            next_actions=["确认生成上下文包", "调整关键词重新预览", "先打开来源核对内容"],
            debug={
                "query": query,
                "request": request,
                "mode": "preview",
                "candidate_count": len(sources),
                "identity": identity,
                "direct_answers": [item.get("direct_evidence") for item in sources if item.get("direct_evidence")],
            },
        )
        result["status"] = "candidate_only"
        result["answer"] = f"候选来源已找到：{first.get('title', '未命名来源')}。"
        return result
    compressed = "\n".join(
        f"- {item['title']}："
        f"{('直接线索：' + item['direct_evidence'] + '。') if item.get('direct_evidence') else ''}"
        f"{item['summary']}（来源：{item['path']}）"
        for item in sources
    ) or "- 暂无匹配来源。"
    identity_summary = str(identity.get("summary") or "").strip() or "- 未发现 AI 身份文件；仅使用本次确认来源。"
    prompt = f"""AI 上下文包

当前需求：
{request}

已整理上下文：
{compressed}

AI 身份文件摘要：
{identity_summary}

使用要求：
- 先引用来源路径，再给结论。
- 如果上下文不足，明确指出缺口，不要编造。
- 遵守 AI 身份文件中的协作偏好和上下文边界；如果身份文件缺失，明确说明只依据本次来源。
- 输出下一步行动，并说明是否需要继续添加资料、搜索回顾或生成新的上下文包。

安全边界：
{SAFETY_TEXT}
"""
    filename = f"{generated_at.strftime('%Y%m%d-%H%M%S')} {safe_filename(query, 'AI 上下文包')}.md"
    markdown = render_context_markdown(request, sources, prompt, generated_at, identity)
    runtime_md = write_text(run_dir(config, "extract", generated_at) / filename, markdown)
    obsidian_md = write_text(section_dir(config, "提取") / filename, markdown)
    write_json(run_dir(config, "extract", generated_at) / "context-package.json", {"request": request, "sources": sources, "identity": identity, "prompt": prompt, "mode": "generate"})
    identity_note = f"已写入 AI 身份文件摘要 {identity['count']} 条。" if identity["count"] else "未发现 AI 身份文件摘要。"
    result = unified_result(
        "extract",
        f"AI 上下文包已生成：{safe_filename(query, '当前任务')}。{identity_note}",
        sources=sources,
        artifacts=[
            artifact("prompt", None, "复制 AI 上下文包 prompt", prompt),
            artifact("markdown", runtime_md, "打开 runtime Markdown"),
            artifact("obsidian-note", obsidian_md, "打开 Obsidian 上下文包"),
        ],
        next_actions=["复制 prompt 给 AI", "打开 Markdown 包", "继续整理缺失来源"],
        debug={
            "query": query,
            "request": request,
            "mode": "generate",
            "source_paths": source_paths,
            "identity": identity,
            "direct_answers": [item.get("direct_evidence") for item in sources if item.get("direct_evidence")],
        },
    )
    result["status"] = "generated"
    result["answer"] = f"AI 上下文包已生成，已引用 {len(sources)} 条证据来源；{identity_note}"
    return result


def build_legacy_index(config: dict[str, Any]) -> dict[str, Any]:
    roots = [
        vault_path(config) / folder_name(config, "routine", "04 例行工作") / "知识行动助手",
        vault_path(config) / folder_name(config, "projects", "02 项目") / "知识行动助手",
        vault_path(config) / folder_name(config, "projects", "02 项目") / folder_name(config, "codex_project", "Codex"),
    ]
    items: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8-sig", errors="ignore")
            except OSError:
                continue
            items.append(
                {
                    "title": markdown_title(text, path.stem),
                    "path": str(path),
                    "summary": compact_text(text, 220),
                    "suggestion": "保留旧文件不动；纳入回顾检索，必要时再提炼为新的整理记录。",
                }
            )
    generated_at = now_local()
    lines = [
        "# 旧资料二次整理索引",
        "",
        f"生成时间：{generated_at.strftime('%Y-%m-%d %H:%M:%S %z')}",
        "",
        "说明：本索引只整理旧知识行动助手 / Codex 内容，不移动、不改写旧文件。",
        "",
        "## 来源清单",
        "",
    ]
    for item in items:
        lines.append(f"- {item['title']}")
        lines.append(f"  来源：{item['path']}")
        lines.append(f"  摘要：{item['summary']}")
        lines.append("")
    index_note = write_text(section_dir(config, "回顾") / "旧资料二次整理索引.md", "\n".join(lines))
    return {
        "ok": True,
        "count": len(items),
        "index_note": str(index_note),
        "sources": items,
        "safety": SAFETY_TEXT,
    }


def run_action(action: str, payload: dict[str, Any] | None, config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    if action == "organize":
        return organize(config, payload)
    if action == "review":
        return review(config, payload)
    if action == "extract":
        return extract(config, payload)
    if action in DEPRECATED_ACTIONS:
        result = unified_result(
            action,
            "这个命令已降级，不再作为产品闭环执行。当前只保留三件事：添加资料、搜索回顾、生成 AI 上下文包。",
            sources=[],
            artifacts=[],
            next_actions=["添加资料", "搜索回顾", "生成 AI 上下文包"],
            debug={"status": "deprecated", "reason": "core_loop_only"},
            ok=False,
        )
        result["status"] = "deprecated"
        return result
    return unified_result(action, f"unsupported action: {action}", ok=False)


def cli_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if args.text:
        payload["text"] = args.text
    if args.query:
        payload["query"] = args.query
    if args.request:
        payload["request"] = args.request
    if args.kind:
        payload["kind"] = args.kind
    if args.local_path:
        payload["local_paths"] = args.local_path
    if args.source_path:
        payload["source_paths"] = args.source_path
    if args.mode:
        payload["mode"] = args.mode
    if args.title:
        payload["title"] = args.title
    payload["source"] = "CLI"
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="本地知识整理助手三主操作入口")
    parser.add_argument("action", choices=CORE_ACTIONS)
    parser.add_argument("--config", default=str(Path(__file__).resolve().with_name("config.json")))
    parser.add_argument("--text", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--request", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--kind", choices=["text", "file", "ai"], default="")
    parser.add_argument("--local-path", action="append", default=[])
    parser.add_argument("--source-path", action="append", default=[])
    parser.add_argument("--mode", choices=["preview", "generate"], default="")
    args = parser.parse_args()
    result = run_action(args.action, cli_payload(args), Path(args.config))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
