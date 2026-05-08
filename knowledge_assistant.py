from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from config_loader import load_config

import assistant_evolution
import scenario_playbook


PRODUCT = {
    "name": "本地知识整理助手",
    "tagline": "整理、回顾、提取、提醒",
    "description": "把本地文件、Obsidian 笔记和 AI 对话整理成可归档、可回顾、可提取给 AI 续用、可定时提醒的个人知识系统。",
}

SAFETY_TEXT = "默认只读建议；不删除、不移动、不重命名、不重写源文件；只写新的 Obsidian 记录和本地运行证据。"
CORE_ACTIONS = ["organize", "review", "extract", "remind"]
MAX_REVIEW_ITEMS = 300


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


def write_text(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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
            sources.append(source_item(str(item.get("name") or "选择文件"), str(item.get("relative_path") or ""), f"选择/拖放文件，大小 {item.get('size', 0)} bytes", "file"))
    if not sources:
        sources.append(source_item("空输入整理记录", "", "用户触发整理，但未提供正文或路径。", kind))

    suggestion = {
        "text": "先保留来源，写入知识整理助手；后续复盘时再决定是否提升到项目、学习资料或归档。",
        "target": "04 例行工作\\知识整理助手\\整理",
        "domain": domain["name"],
        "reason": domain["reason"],
    }
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
    result = unified_result(
        "organize",
        f"整理记录已写入 Obsidian：{title}。建议领域：{domain['name']}。",
        sources=sources,
        artifacts=[artifact("obsidian-note", note_path, "打开整理记录")],
        next_actions=["回顾相关知识", "提取 AI 上下文包", "需要时在 Obsidian 中手动归位"],
        debug={"kind": kind, "domain": domain, "suggestion": suggestion},
    )
    return result


def iter_markdown_notes(config: dict[str, Any]) -> list[Path]:
    roots = [
        knowledge_root(config),
        vault_path(config) / folder_name(config, "routine", "04 例行工作") / "知识行动助手",
        vault_path(config) / folder_name(config, "projects", "02 项目") / "知识行动助手",
        vault_path(config) / folder_name(config, "projects", "02 项目") / folder_name(config, "codex_project", "Codex"),
        Path(config.get("obsidian_run_dir") or knowledge_root(config)),
        runtime_root(config) / "runs",
        runtime_root(config) / "knowledge-assistant",
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
            if len(notes) >= MAX_REVIEW_ITEMS:
                return notes
    return notes


def build_review_index(config: dict[str, Any], limit: int = MAX_REVIEW_ITEMS) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in iter_markdown_notes(config)[:limit]:
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
        kind = "note"
        parts = set(path.parts)
        if "整理" in parts:
            kind = "organize"
        elif "提取" in parts:
            kind = "extract"
        elif "提醒" in parts:
            kind = "remind"
        elif "Codex" in parts:
            kind = "legacy-codex"
        items.append(
            {
                "title": markdown_title(text, path.stem),
                "path": str(path),
                "summary": compact_text(text, 260),
                "type": kind,
                "modified_at": dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
            }
        )
    return items


def score_item(query: str, item: dict[str, Any]) -> int:
    if not query.strip():
        return 1
    haystack = "\n".join(str(item.get(key, "")) for key in ("title", "path", "summary", "type")).lower()
    tokens = [token for token in re.split(r"\s+|/|\\|，|。|：|:|\||-", query.lower()) if token]
    score = 0
    for token in tokens:
        if token in haystack:
            score += 5 if token in str(item.get("title", "")).lower() else 2
    return score


def review(config: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    query = str(payload.get("query") or payload.get("text") or payload.get("question") or "").strip()
    index = build_review_index(config)
    ranked = sorted(index, key=lambda item: (score_item(query, item), item.get("modified_at", "")), reverse=True)
    matches = [item for item in ranked if score_item(query, item) > 0][:8]
    if not matches and ranked:
        matches = ranked[:5]
    sources = [
        source_item(
            str(item["title"]),
            str(item["path"]),
            str(item["summary"]),
            str(item["type"]),
            f"与“{query or '最近内容'}”在标题、路径或正文片段上匹配。",
        )
        for item in matches
    ]
    if sources:
        lead = "；".join(f"{item['title']}（{item['type']}）" for item in sources[:3])
        summary = f"本地摘要：找到 {len(sources)} 条相关内容。优先查看：{lead}。"
    else:
        summary = "本地摘要：没有找到已整理内容。建议先使用“整理资料”写入一条记录。"
    return unified_result(
        "review",
        summary,
        sources=sources,
        artifacts=[],
        next_actions=["打开匹配来源", "提取 AI 上下文包", "整理新的补充资料"],
        debug={"query": query, "index_count": len(index)},
    )


def render_context_markdown(request: str, sources: list[dict[str, Any]], prompt: str, generated_at: dt.datetime) -> str:
    source_lines = "\n".join(
        f"- [{item.get('type', 'note')}] {item.get('title', '')}：{item.get('summary', '')}\n  来源：{item.get('path', '')}"
        for item in sources
    )
    return f"""# AI 上下文包

生成时间：{generated_at.strftime("%Y-%m-%d %H:%M:%S %z")}
当前需求：{request}

## 来源摘要

{source_lines or "- 暂无匹配来源。"}

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
    query = str(payload.get("query") or payload.get("text") or payload.get("request") or "当前任务").strip()
    request = str(payload.get("request") or payload.get("text") or query).strip()
    review_result = review(config, {"query": query})
    sources = review_result["sources"][:8]
    compressed = "\n".join(f"- {item['title']}：{item['summary']}（来源：{item['path']}）" for item in sources) or "- 暂无匹配来源。"
    prompt = f"""AI 上下文包

当前需求：
{request}

已整理上下文：
{compressed}

使用要求：
- 先引用来源路径，再给结论。
- 如果上下文不足，明确指出缺口，不要编造。
- 输出下一步行动，并说明是否需要继续整理、回顾、提取或提醒。

安全边界：
{SAFETY_TEXT}
"""
    filename = f"{generated_at.strftime('%Y%m%d-%H%M%S')} {safe_filename(query, 'AI 上下文包')}.md"
    markdown = render_context_markdown(request, sources, prompt, generated_at)
    runtime_md = write_text(run_dir(config, "extract", generated_at) / filename, markdown)
    obsidian_md = write_text(section_dir(config, "提取") / filename, markdown)
    write_json(run_dir(config, "extract", generated_at) / "context-package.json", {"request": request, "sources": sources, "prompt": prompt})
    return unified_result(
        "extract",
        f"AI 上下文包已生成：{safe_filename(query, '当前任务')}。",
        sources=sources,
        artifacts=[
            artifact("prompt", None, "复制 AI 上下文包 prompt", prompt),
            artifact("markdown", runtime_md, "打开 runtime Markdown"),
            artifact("obsidian-note", obsidian_md, "打开 Obsidian 上下文包"),
        ],
        next_actions=["复制 prompt 给 AI", "打开 Markdown 包", "继续整理缺失来源"],
        debug={"query": query, "request": request},
    )


def remind(config: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    generated_at = now_local()
    review_result = review(config, {"query": payload.get("query") or ""})
    sources = review_result["sources"][:3]
    next_actions = [
        "先处理 1 个今天最相关的整理项",
        "需要继续问 AI 时，先提取 AI 上下文包",
        "晚上只做轻量复盘，不处理全部 backlog",
    ]
    note = f"""# 今日提醒

生成时间：{generated_at.strftime("%Y-%m-%d %H:%M:%S %z")}

## 今日 1-3 个重点

{chr(10).join(f"- {item}" for item in next_actions)}

## 参考来源

{chr(10).join(f"- {item['title']}：{item.get('path', '')}" for item in sources) or "- 暂无已整理来源，建议先整理一条资料。"}

## 安全边界

{SAFETY_TEXT}
"""
    filename = f"{generated_at.strftime('%Y-%m-%d')} 今日提醒.md"
    obsidian_note = write_text(section_dir(config, "提醒") / filename, note)
    runtime_md = write_text(run_dir(config, "remind", generated_at) / filename, note)
    write_json(run_dir(config, "remind", generated_at) / "remind.json", {"next_actions": next_actions, "sources": sources})
    return unified_result(
        "remind",
        "今日提醒已生成：只列 1-3 个重点，不做定时整理。",
        sources=sources,
        artifacts=[
            artifact("obsidian-note", obsidian_note, "打开今日提醒"),
            artifact("markdown", runtime_md, "打开 runtime 提醒"),
        ],
        next_actions=next_actions,
        debug={"scheduled_time": "09:00", "auto_organize": False},
    )


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
    if action == "remind":
        return remind(config, payload)
    if action == "legacy-index":
        legacy = build_legacy_index(config)
        return unified_result(
            "legacy-index",
            f"旧资料二次整理索引已生成，共 {legacy['count']} 条。",
            sources=[source_item(item["title"], item["path"], item["summary"], "legacy") for item in legacy["sources"]],
            artifacts=[artifact("obsidian-note", Path(legacy["index_note"]), "打开旧资料索引")],
            next_actions=["回顾旧资料", "提取 AI 上下文包"],
            debug={"count": legacy["count"]},
        )
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
    if args.title:
        payload["title"] = args.title
    payload["source"] = "CLI"
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="本地知识整理助手四功能入口")
    parser.add_argument("action", choices=[*CORE_ACTIONS, "legacy-index"])
    parser.add_argument("--config", default=str(Path(__file__).resolve().with_name("config.json")))
    parser.add_argument("--text", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--request", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--kind", choices=["text", "file", "ai"], default="")
    parser.add_argument("--local-path", action="append", default=[])
    args = parser.parse_args()
    result = run_action(args.action, cli_payload(args), Path(args.config))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
