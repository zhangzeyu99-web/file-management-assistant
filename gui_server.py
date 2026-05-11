from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import file_assistant
import assistant_evolution
import knowledge_assistant
import obsidian_assistant
import obsidian_manager
import scenario_playbook
from config_loader import load_config


DEFAULT_CONFIG = ROOT / "config.json"
ASSET_ROOT = ROOT / "docs" / "assets"

PUBLIC_COPY_REPLACEMENTS = {
    "默认只读": "安全检查",
    "不删除、不移动、不重命名、不重写源文件": "源文件保持原样",
    "站点式知识库": "知识整理首页",
    "首屏极简": "首页聚焦",
    "首页不再堆功能": "首页聚焦三项操作",
    "每次点击后": "操作完成后",
}


def sanitize_public_copy(value: Any) -> str:
    text = str(value or "")
    for old, new in PUBLIC_COPY_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def latest_file_report(config: dict[str, Any]) -> dict[str, Any] | None:
    return scenario_playbook.latest_file_report(config)


def latest_obsidian_report(config: dict[str, Any]) -> dict[str, Any] | None:
    return scenario_playbook.latest_obsidian_report(config)


def clean_feed_description(summary: Any, fallback: str, title: str = "") -> str:
    text = sanitize_public_copy(summary)
    for marker in ["## 来源清单", "## 本次结果", "## 报告路径", "## Obsidian 概览", "## 按目录统计"]:
        if marker in text:
            text = text.split(marker, 1)[0]
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    if title:
        text = text.replace(title, " ", 1)
    text = text.replace(fallback, " ", 1)
    text = re.sub(r"#{1,6}\s*", " ", text)
    text = re.sub(r"\b[A-Za-z]:\\[^\s，。；、]+", "本地来源", text)
    text = re.sub(r"(生成时间|创建时间)：`?\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?\s*[+]\d{4}`?", " ", text)
    text = re.sub(r"(类型|用途|来源|Obsidian 库|报告路径|Markdown|HTML|JSON)：[^。；#\n]{0,100}", " ", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?\s*[+]\d{4}", " ", text)
    text = re.sub(r"\s*[|]\s*", " ", text)
    text = re.sub(r"\s+-\s+", "；", text)
    text = re.sub(r"\s+", " ", text).strip(" -，。；：")
    if "待提炼结论" in text and "AI 对话归档" in title:
        text = fallback
    if not text:
        text = fallback
    return knowledge_assistant.compact_text(sanitize_public_copy(text), 118)


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text.strip()


def markdown_sections(text: str) -> dict[str, str]:
    body = strip_frontmatter(text)
    sections: dict[str, list[str]] = {}
    current = "正文"
    for raw in body.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", raw)
        if match:
            current = match.group(1).strip()
            sections.setdefault(current, [])
            continue
        if raw.startswith("# "):
            continue
        sections.setdefault(current, []).append(raw)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def section_value(sections: dict[str, str], names: list[str]) -> str:
    for name in names:
        if name in sections and sections[name].strip():
            return sections[name].strip()
    return ""


def markdown_list_items(text: str, limit: int = 5) -> list[str]:
    items: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        match = re.match(r"^(?:[-*]|\d+[.、])\s+(.+)$", line)
        if match:
            item = re.sub(r"`([^`]+)`", r"\1", match.group(1)).strip()
            if item:
                items.append(item)
        if len(items) >= limit:
            break
    if items:
        return items
    paragraphs = [re.sub(r"\s+", " ", item).strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    return paragraphs[:limit]


def section_summary(text: str, fallback: str, limit: int = 180) -> str:
    items = markdown_list_items(text, limit=3) if text else []
    if items:
        cleaned = "；".join(items)
    else:
        cleaned = str(text or fallback)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -，。；：")
    return knowledge_assistant.compact_text(sanitize_public_copy(cleaned or fallback), limit)


def source_items_from_markdown(text: str, fallback_path: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-* ").strip()
        if not line:
            continue
        path_match = re.search(r"`([^`]+)`", line)
        path = path_match.group(1).strip() if path_match else ""
        if not path:
            windows_match = re.search(r"[A-Za-z]:\\[^\s，。；、]+", line)
            path = windows_match.group(0) if windows_match else ""
        label = line.split(":", 1)[0].strip() if ":" in line else "来源"
        if path:
            items.append({"label": label[:40], "path": path})
        if len(items) >= 4:
            break
    if not items and fallback_path:
        items.append({"label": "当前笔记", "path": fallback_path})
    return items


def detail_section(title: str, items: list[str] | None = None, body: str = "") -> dict[str, Any]:
    clean_items = [
        knowledge_assistant.compact_text(sanitize_public_copy(item), 150)
        for item in (items or [])
        if str(item).strip()
    ]
    return {
        "title": title,
        "items": clean_items[:4],
        "body": knowledge_assistant.compact_text(sanitize_public_copy(body), 220) if body else "",
    }


def thinking_prompts_for(item_type: str, title: str) -> list[str]:
    if item_type == "session-index" or "会话标题索引" in title:
        return [
            "哪些近期会话值得沉淀成知识卡？",
            "哪个原始会话路径应该交给 Codex 继续读取？",
            "有没有重复问题可以合并成一条复用规则？",
        ]
    if item_type == "knowledge-card":
        return [
            "这条规则能复用到哪个当前任务？",
            "是否需要补充反例、边界或来源？",
            "是否应该加入下一次 AI 上下文包？",
        ]
    return [
        "这条记录应该升级为知识卡还是保留为归档？",
        "它和哪些项目、会话或报告有关？",
        "下一步应该补来源、补结论还是生成上下文包？",
    ]


def build_detail_sections(
    item_type: str,
    title: str,
    sections: dict[str, str],
    scenario: str,
    conclusions: list[str],
    next_steps: list[str],
    fallback: str,
) -> tuple[str, list[dict[str, Any]]]:
    if item_type == "session-index" or "会话标题索引" in title:
        usage = markdown_list_items(section_value(sections, ["用法"]), limit=4)
        return (
            "session-index",
            [
                detail_section("怎么使用这个索引", usage, scenario or fallback),
                detail_section("主题分布", conclusions, "当前索引还没有主题统计。"),
                detail_section("近期会话入口", next_steps, "当前索引还没有近期会话入口。"),
            ],
        )
    if item_type == "knowledge-card":
        return (
            "knowledge-card",
            [
                detail_section("适用场景", markdown_list_items(scenario, limit=4), scenario or fallback),
                detail_section("关键结论", conclusions, "这张卡还没有提炼出关键结论。"),
                detail_section("下次怎么用", next_steps, "打开来源补充下次用法。"),
            ],
        )
    return (
        "note",
        [
            detail_section("阅读摘要", markdown_list_items(scenario, limit=4), scenario or fallback),
            detail_section("关键信息", conclusions, fallback),
            detail_section("下一步", next_steps, "打开来源补充下一步。"),
        ],
    )


def structured_feed_summary(text: str, fallback: str, title: str, source_path: str, item_type: str = "") -> dict[str, Any]:
    sections = markdown_sections(text)
    scenario = section_value(sections, ["适用场景", "使用场景", "场景", "用法", "背景", "目标", "正文"])
    explicit_conclusions_text = section_value(sections, ["关键结论", "结论"])
    overview_text = section_value(sections, ["主题概览"])
    conclusions_text = explicit_conclusions_text or overview_text
    next_text = section_value(sections, ["下次怎么用", "下一步", "行动建议", "近期标题速览"])
    sources_text = section_value(sections, ["来源", "来源路径", "证据"])

    conclusions = [sanitize_public_copy(item) for item in markdown_list_items(conclusions_text, limit=4)] if conclusions_text else []
    next_steps = [sanitize_public_copy(item) for item in markdown_list_items(next_text, limit=4)] if next_text else []
    source_items = source_items_from_markdown(sources_text, source_path)

    cleaned = clean_feed_description(strip_frontmatter(text), fallback, title)
    if "会话标题索引" in title:
        takeaway = "Codex 会话已按主题和近期标题建立索引，可按标题回到原始会话。"
    elif explicit_conclusions_text and conclusions:
        takeaway = conclusions[0]
    else:
        takeaway = cleaned
    takeaway = sanitize_public_copy(takeaway)
    scenario_summary = section_summary(scenario, fallback)
    if scenario_summary and takeaway:
        description = knowledge_assistant.compact_text(sanitize_public_copy(f"{takeaway} 适用：{scenario_summary}"), 118)
    else:
        description = sanitize_public_copy(cleaned)
    detail_kind, detail_sections = build_detail_sections(item_type, title, sections, scenario, conclusions, next_steps, fallback)

    return {
        "description": description,
        "takeaway": knowledge_assistant.compact_text(takeaway, 120),
        "scenario": scenario_summary,
        "conclusions": conclusions,
        "next_steps": next_steps,
        "source_items": source_items,
        "detail_kind": detail_kind,
        "detail_sections": detail_sections,
        "thinking_prompts": thinking_prompts_for(item_type, title),
    }


def feed_fallback(title: str, item_type: str) -> str:
    if "Obsidian 管理" in title:
        return "知识库体检结果已记录，可查看收件箱、空壳笔记、低连接笔记和断链状态。"
    if "文件雷达" in title or "文件管理助手复盘" in title:
        return "本地文件扫描结果已记录，可查看近期复盘、归档候选、大文件和重复文件。"
    if "AI 对话归档" in title:
        return "AI 对话已归档，保留任务背景、关键结论、产出路径和未完成事项。"
    if item_type == "legacy-codex":
        return "历史项目上下文已收录，可作为后续 AI 对话和知识回顾的来源。"
    return f"{title} 已记录，可点击查看摘要、来源和下一步。"


def compact_feed_time(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", text)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return text[:16] if text else "最近更新"


def feed_dedupe_key(title: str, description: str) -> str:
    normalized_title = re.sub(r"\s+", " ", title).strip().lower()
    normalized_title = re.sub(r"[\-_/\\]+", " ", normalized_title)
    normalized_description = re.sub(r"\s+", " ", description).strip().lower()[:48]
    return normalized_title or normalized_description


TOPIC_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("codex-session", "Codex 会话", ("codex", "会话", "session", "jsonl")),
    ("ai-context", "AI 上下文", ("上下文", "prompt", "ai 对话", "ai上下文", "context")),
    ("obsidian", "Obsidian 知识库", ("obsidian", "vault", "笔记", "知识库", "双链")),
    ("local-file", "本地文件", ("本地文件", "文件", "目录", "路径", "扫描", "大文件")),
    ("knowledge-card", "知识卡片", ("知识卡", "卡片", "card", "规则", "复用")),
    ("workflow", "整理工作流", ("工作流", "流程", "闭环", "归档", "复盘", "行动建议")),
    ("learning", "学习资料", ("学习", "教程", "notebooklm", "课程", "指南")),
    ("translation", "本地化翻译", ("翻译", "术语", "本地化", "glossary", "excel")),
    ("life", "生活资料", ("生活", "证件", "收纳", "日用品", "衣柜")),
]


def feed_relation_text(item: dict[str, Any]) -> str:
    text = " ".join(
        str(item.get(key) or "")
        for key in ["title", "description", "takeaway", "scenario", "source_path", "action_hint"]
    )
    text += " " + " ".join(str(tag) for tag in item.get("tags") or [])
    text += " " + " ".join(str(value) for value in item.get("conclusions") or [])
    text += " " + " ".join(str(value) for value in item.get("next_steps") or [])
    return text


def feed_topic_keys(item: dict[str, Any]) -> set[str]:
    topic_text = " ".join(
        str(item.get(key) or "")
        for key in ["title", "description", "takeaway", "scenario", "action_hint"]
    )
    topic_text += " " + " ".join(str(value) for value in item.get("conclusions") or [])
    topic_text += " " + " ".join(str(value) for value in item.get("next_steps") or [])
    lowered = topic_text.lower()
    topics = {key for key, _label, needles in TOPIC_RULES if any(needle.lower() in lowered for needle in needles)}
    if not topics:
        topics.add("general-note")
    return topics


def topic_label(key: str) -> str:
    for candidate, label, _needles in TOPIC_RULES:
        if candidate == key:
            return label
    return "通用笔记"


def feed_relation_terms(item: dict[str, Any]) -> set[str]:
    text = feed_relation_text(item)
    terms: set[str] = set()
    curated_terms = [
        "codex",
        "obsidian",
        "ai",
        "上下文",
        "会话",
        "知识",
        "卡片",
        "索引",
        "报告",
        "文件",
        "归档",
        "整理",
        "搜索",
        "提取",
        "复盘",
    ]
    lowered = text.lower()
    for term in curated_terms:
        if term in lowered:
            terms.add(term)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", lowered):
        if len(token) >= 3:
            terms.add(token)
    return terms


def attach_related_feed_items(feed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    topic_cache = [feed_topic_keys(item) for item in feed]
    term_cache = [feed_relation_terms(item) for item in feed]
    for index, item in enumerate(feed):
        item["topic_keys"] = sorted(topic_cache[index])
        scored: list[tuple[int, list[str], list[str], dict[str, Any]]] = []
        for other_index, other in enumerate(feed):
            if index == other_index:
                continue
            topic_overlap = sorted((topic_cache[index] & topic_cache[other_index]) - {"general-note"})
            overlap = sorted(term_cache[index] & term_cache[other_index])
            if topic_overlap:
                scored.append((100 + len(topic_overlap) * 10 + len(overlap), topic_overlap, overlap, other))
        scored.sort(key=lambda value: (-value[0], str(value[3].get("title") or "")))
        item["related_items"] = [
            {
                "title": str(other.get("title") or "未命名知识"),
                "type": str(other.get("type") or "笔记"),
                "source_path": str(other.get("source_path") or ""),
                "why": (
                    f"同属主题：{'、'.join(topic_label(key) for key in topic_overlap[:3])}"
                    if topic_overlap
                    else f"相关线索：{'、'.join(overlap[:3])}"
                ),
            }
            for _, topic_overlap, overlap, other in scored[:3]
        ]
    return feed


def is_home_feed_noise(title: str) -> bool:
    text = re.sub(r"\s+", " ", title).strip()
    transitional_terms = ["文件管理助手", "Codex 文件管理小助手", "今日" + "操作台", "伪控制台", "Codex 接手包"]
    demoted_actions = {"今天先干什么", "判断放哪", "记录一个任务", "沉淀知识卡", "复盘今天", "快速初始化"}
    return any(term in text for term in transitional_terms) or text in demoted_actions


def project_codex_feed_items(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Prioritize curated Codex project notes before noisy runtime reports."""
    vault = knowledge_assistant.vault_path(config)
    codex_dir = vault / "02 项目" / "Codex"
    candidates: list[tuple[Path, str]] = [
        (codex_dir / "13 Codex 会话标题索引.md", "session-index"),
    ]
    cards_dir = codex_dir / "知识卡片"
    if cards_dir.exists():
        candidates.extend((path, "knowledge-card") for path in sorted(cards_dir.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True))

    items: list[dict[str, Any]] = []
    for path, item_type in candidates:
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            modified_at = path.stat().st_mtime
        except OSError:
            continue
        items.append(
            {
                "title": knowledge_assistant.markdown_title(text, path.stem),
                "path": str(path),
                "summary": knowledge_assistant.compact_text(text, 260),
                "raw_markdown": text,
                "type": item_type,
                "modified_at": dt.datetime.fromtimestamp(modified_at).astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
            }
        )
    return items


def build_knowledge_feed(config: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    type_labels = {
        "organize": "整理",
        "extract": "提取",
        "remind": "今日行动",
        "legacy-codex": "历史",
        "knowledge-card": "知识卡片",
        "session-index": "会话索引",
        "note": "笔记",
    }
    action_hints = {
        "organize": "可继续回顾或提取为 AI 上下文包",
        "extract": "可复制给新的 AI 对话继续使用",
        "remind": "可作为今日行动建议参考",
        "legacy-codex": "可作为历史项目上下文",
        "knowledge-card": "可作为下次任务的复用规则",
        "session-index": "可按标题回到原始 Codex 会话",
        "note": "可打开来源继续阅读",
    }
    feed: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    source_items = project_codex_feed_items(config)
    source_items.extend(knowledge_assistant.build_review_index(config, limit=max(limit * 6, limit)))
    for item in source_items:
        item_type = str(item.get("type") or "note")
        title = str(item.get("title") or "未命名知识")
        if is_home_feed_noise(title):
            continue
        fallback = feed_fallback(title, item_type)
        raw_text = str(item.get("raw_markdown") or item.get("summary") or "")
        structured = structured_feed_summary(raw_text, fallback, title, str(item.get("path") or ""), item_type)
        description = structured["description"]
        key = feed_dedupe_key(title, description)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        feed.append(
            {
                "title": title,
                "description": description,
                "type": type_labels.get(item_type, item_type),
                "source_path": str(item.get("path") or ""),
                "updated_at": compact_feed_time(item.get("modified_at")),
                "tags": [type_labels.get(item_type, item_type), "来源可追溯"],
                "action_hint": action_hints.get(item_type, "可打开来源继续阅读"),
                "takeaway": structured["takeaway"],
                "scenario": structured["scenario"],
                "conclusions": structured["conclusions"],
                "next_steps": structured["next_steps"],
                "source_items": structured["source_items"],
                "detail_kind": structured["detail_kind"],
                "detail_sections": structured["detail_sections"],
                "thinking_prompts": structured["thinking_prompts"],
                "topic_keys": [],
                "related_items": [],
            }
        )
        if len(feed) >= limit:
            break
    return attach_related_feed_items(feed)


def build_status(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)
    return {
        "ok": True,
        "product": knowledge_assistant.PRODUCT,
        "config": str(config_path),
        "vault": str(scenario_playbook.obsidian_vault(config)),
        "runtime_root": str(scenario_playbook.runtime_root(config)),
        "file_report": latest_file_report(config),
        "obsidian_report": latest_obsidian_report(config),
        "knowledge_feed": build_knowledge_feed(config),
        "scenarios": scenario_playbook.build_scenario_catalog(config),
        "guidebook": assistant_evolution.build_guidebook_catalog(ROOT),
        "safety": scenario_playbook.SAFETY_TEXT,
    }


def split_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.splitlines() if item.strip()]


def build_codex_prompt(user_request: str, config: dict[str, Any]) -> str:
    file_report = latest_file_report(config) or {}
    obsidian_report = latest_obsidian_report(config) or {}
    ai_context = assistant_evolution.build_ai_context(config, user_request, user_request)
    return f"""请基于真实本地文件继续执行知识行动助手任务。

用户请求：
{user_request}

能力说明：
- 这是 AI 上下文取用，不是一次性移交单。
- 先从已整理的 Obsidian 笔记、知识卡、项目记录和历史报告中取用上下文，再继续对话。
- AI 对话归档用于保存已有对话；AI 上下文取用用于给新的 AI 对话补充上下文。

本地上下文：
- Obsidian vault：{scenario_playbook.obsidian_vault(config)}
- 运行目录：{scenario_playbook.runtime_root(config)}
- 最新文件雷达报告：{file_report.get("html_report") or "暂无"}
- 最新 Obsidian 体检报告：{obsidian_report.get("markdown_report") or "暂无"}

已整理上下文：
{ai_context["compressed_context"]}

判断规则：
- 先按生活 / 学习 / 工作分流。
- 再按 Action / Card / Time / X-AI 判断产物类型。
- 今日行动只给最多 3 条建议，不要把全部归档候选变成今日任务。

安全边界：
- 不删除源文件；源文件保持原样，只在明确位置写新笔记或追加内容。
- 先读真实文件和报告，再执行。
- 需要写入时写新笔记或追加明确位置，并保留来源。

验收标准：
- 给出实际写入路径或报告路径。
- 说明是否仍有未处理风险。
- 若无法确认当前状态，明确说无法确认，不编造。
"""


def split_local_paths(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif value is None:
        raw_items = []
    else:
        raw_items = str(value).replace(";", "\n").splitlines()
    paths: list[str] = []
    for item in raw_items:
        cleaned = str(item).strip().strip('"').strip("'")
        if cleaned:
            paths.append(cleaned)
    return list(dict.fromkeys(paths))


def extract_local_target_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("local_paths", "target_paths", "paths", "path_text", "target_path"):
        paths.extend(split_local_paths(payload.get(key)))
    return list(dict.fromkeys(paths))


def selected_file_metadata(payload: dict[str, Any]) -> list[dict[str, Any]]:
    selected = payload.get("selected_files") or []
    if not isinstance(selected, list):
        return []
    files: list[dict[str, Any]] = []
    for item in selected[:50]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        files.append(
            {
                "name": name,
                "size": int(item.get("size") or 0),
                "type": str(item.get("type") or ""),
                "relative_path": str(item.get("relative_path") or ""),
            }
        )
    return files


def inspect_local_targets(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    paths = extract_local_target_paths(payload)
    selected_files = selected_file_metadata(payload)
    if not paths:
        defaults = [
            {
                "name": str(root.get("name") or Path(str(root.get("path") or "")).name),
                "path": str(root.get("path") or ""),
                "max_depth": int(root.get("max_depth", 2)),
                "max_files": int(root.get("max_files", 2000)),
            }
            for root in config.get("watch_roots", [])
        ]
        return {
            "ok": True,
            "action": "inspect-local-targets",
            "mode": "configured-defaults",
            "summary": {
                "target_count": len(defaults),
                "existing_count": sum(1 for item in defaults if Path(item["path"]).exists()),
                "selected_file_count": len(selected_files),
            },
            "targets": defaults,
            "selected_files": selected_files,
            "safety": "安全检查：未粘贴路径时使用 config.json / config.local.json 的扫描目录；不改动源文件。",
        }

    targets: list[dict[str, Any]] = []
    for raw_path in paths:
        target = Path(raw_path).expanduser()
        exists = target.exists()
        is_dir = target.is_dir() if exists else False
        is_file = target.is_file() if exists else False
        item: dict[str, Any] = {
            "path": str(target),
            "exists": exists,
            "is_dir": is_dir,
            "is_file": is_file,
            "kind": "directory" if is_dir else "file" if is_file else "missing",
        }
        if is_file:
            stat = target.stat()
            item.update({"size_bytes": int(stat.st_size), "extension": file_assistant.normalize_extension(target)})
        elif is_dir:
            files = file_assistant.iter_files(
                target,
                max_depth=int(payload.get("max_depth") or 2),
                max_files=int(payload.get("max_files") or 100),
                excluded_dirs={str(name).lower() for name in config.get("exclude_dir_names", [])},
            )
            item.update({"preview_file_count": len(files), "preview_files": [str(path) for path in files[:8]]})
        targets.append(item)

    return {
        "ok": True,
        "action": "inspect-local-targets",
        "mode": "custom-local-paths",
        "summary": {
            "target_count": len(targets),
            "existing_count": sum(1 for item in targets if item["exists"]),
            "directory_count": sum(1 for item in targets if item["is_dir"]),
            "file_count": sum(1 for item in targets if item["is_file"]),
            "selected_file_count": len(selected_files),
        },
        "targets": targets,
        "selected_files": selected_files,
        "safety": "只读检查；不会删除、移动、重命名或重写源文件。",
    }


def make_file_record(root_name: str, path: Path, reference: Any) -> file_assistant.FileRecord | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    modified = file_assistant.dt.datetime.fromtimestamp(stat.st_mtime, tz=reference.tzinfo)
    age_days = max(0.0, (reference - modified).total_seconds() / 86400)
    return file_assistant.FileRecord(
        root_name=root_name,
        path=str(path),
        extension=file_assistant.normalize_extension(path),
        size_bytes=int(stat.st_size),
        modified_at=modified.strftime("%Y-%m-%d %H:%M:%S %z"),
        age_days=round(age_days, 2),
    )


def build_target_records(config: dict[str, Any], payload: dict[str, Any], reference: Any) -> tuple[list[file_assistant.FileRecord], list[str]]:
    excluded = {str(item).lower() for item in config.get("exclude_dir_names", [])}
    records: list[file_assistant.FileRecord] = []
    warnings: list[str] = []
    for raw_path in extract_local_target_paths(payload):
        target = Path(raw_path).expanduser()
        if not target.exists():
            warnings.append(f"路径不存在：{target}")
            continue
        if target.is_file():
            record = make_file_record(target.parent.name or "SelectedFile", target, reference)
            if record:
                records.append(record)
            continue
        if target.is_dir():
            root_name = target.name or str(target)
            files = file_assistant.iter_files(
                target,
                max_depth=int(payload.get("max_depth") or 3),
                max_files=int(payload.get("max_files") or 2000),
                excluded_dirs=excluded,
            )
            for file_path in files:
                record = make_file_record(root_name, file_path, reference)
                if record:
                    records.append(record)
            continue
        warnings.append(f"暂不支持的路径类型：{target}")
    return records, warnings


def run_target_file_radar(config_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config(config_path)
    generated_at = file_assistant.now_local()
    run_dir = (
        Path(config["runtime_root"])
        / "runs"
        / generated_at.strftime("%Y-%m-%d")
        / f"{generated_at.strftime('%H%M%S')}-gui-targets"
    )
    records, warnings = build_target_records(config, payload, generated_at)
    classifications = file_assistant.classify_records(records, config)
    duplicates = file_assistant.detect_duplicates(records, config)
    summary = file_assistant.build_summary(config, records, warnings, classifications, duplicates, "GUI", run_dir, generated_at)
    scan_targets = inspect_local_targets(config, payload)
    summary.update({"target_mode": scan_targets["mode"], "scan_targets": scan_targets})

    summary_json = run_dir / "summary.json"
    markdown_report = run_dir / "report.md"
    html_report = run_dir / "report.html"
    file_assistant.write_json(summary_json, summary)
    file_assistant.write_text(markdown_report, file_assistant.render_markdown(summary))
    file_assistant.write_text(html_report, file_assistant.render_html(summary))
    obsidian_note = file_assistant.write_obsidian_run_note(config, summary, markdown_report, html_report)
    summary.update(
        {
            "summary_json": str(summary_json),
            "markdown_report": str(markdown_report),
            "html_report": str(html_report),
            "obsidian_note": str(obsidian_note),
        }
    )
    file_assistant.write_json(summary_json, summary)
    return summary


def run_gui_action(action: str, payload: dict[str, Any] | None = None, config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = payload or {}
    config = load_config(config_path)

    if action in {"organize", "review", "extract", "remind", "legacy-index"}:
        return knowledge_assistant.run_action(action, payload, config_path)

    if action == "today":
        today = next(item for item in scenario_playbook.build_scenario_catalog(config) if item["id"] == "today")
        return {
            "ok": True,
            "action": action,
            "summary": "今日行动规则：只给最多 3 条建议，不要每天处理全部归档候选。",
            "scenario": today,
        }

    if action == "inspect-local-targets":
        return inspect_local_targets(config, payload)

    if action in {"file-radar", "file-scan"}:
        if extract_local_target_paths(payload):
            report = run_target_file_radar(config_path, payload)
            return {"ok": True, "action": action, **report}
        report = latest_file_report(config)
        if report is None:
            report = file_assistant.run(config_path, "GUI")
        return {"ok": True, "action": action, **report}

    if action in {"obsidian-health", "obsidian-audit"}:
        report = latest_obsidian_report(config)
        if report is None:
            report = obsidian_manager.run(config_path, "GUI")
        return {"ok": True, "action": action, **report}

    if action == "full-scan":
        file_result = run_gui_action("file-radar", payload, config_path)
        obsidian_result = run_gui_action("obsidian-health", payload, config_path)
        return {"ok": file_result["ok"] and obsidian_result["ok"], "file": file_result, "obsidian": obsidian_result}

    if action == "guide":
        return obsidian_assistant.command_guide(config)

    if action == "scenarios":
        return {"ok": True, "scenarios": scenario_playbook.build_scenario_catalog(config)}

    if action == "scenario-demo":
        return scenario_playbook.run_demo(config_path)

    if action == "guidebook":
        return assistant_evolution.build_guidebook_catalog(ROOT)

    if action == "onboarding":
        return assistant_evolution.build_initialization_plan(config_path)

    if action == "deep-thinking":
        return {"ok": True, "prompts": assistant_evolution.build_deep_thinking_prompts()}

    if action == "knowledge-index":
        query = str(payload.get("query") or payload.get("text") or "")
        return {
            "ok": True,
            "index": assistant_evolution.build_knowledge_index(config),
            "call_plan": assistant_evolution.build_knowledge_call_plan(config, query) if query else None,
        }

    if action == "archive-ai-chat":
        return assistant_evolution.build_ai_chat_archive(config, payload)

    if action == "build-ai-context":
        query = str(payload.get("query") or payload.get("text") or payload.get("request") or "")
        request = str(payload.get("request") or payload.get("text") or query)
        return assistant_evolution.build_ai_context(config, query, request)

    if action == "self-evolution":
        return assistant_evolution.run_self_evolution(config_path)

    if action == "ask":
        return obsidian_assistant.command_ask(config, str(payload.get("question") or ""), bool(payload.get("write_note")))

    if action == "capture":
        return obsidian_assistant.command_capture(
            config,
            str(payload.get("title") or "未命名"),
            str(payload.get("body") or ""),
            split_lines(payload.get("tags")) or ["inbox"],
        )

    if action == "daily":
        return obsidian_assistant.command_daily(
            config,
            split_lines(payload.get("done")),
            split_lines(payload.get("next")),
            split_lines(payload.get("blocker")),
        )

    if action == "action-note":
        return obsidian_assistant.command_action_note(
            config,
            str(payload.get("title") or "未命名任务"),
            str(payload.get("domain") or "工作"),
            str(payload.get("goal") or "待明确目标"),
            str(payload.get("source") or "GUI"),
        )

    if action == "card-note":
        return obsidian_assistant.command_card_note(
            config,
            str(payload.get("title") or "未命名知识卡"),
            str(payload.get("domain") or "学习"),
            str(payload.get("source") or "GUI"),
            str(payload.get("conclusion") or "待补充关键结论"),
        )

    if action == "time-review":
        return obsidian_assistant.command_time_review(
            config,
            str(payload.get("title") or "今日复盘"),
            str(payload.get("period") or "daily"),
            split_lines(payload.get("done")),
            split_lines(payload.get("next")),
        )

    if action == "inbox-route":
        text = str(payload.get("text") or payload.get("body") or "")
        domain = scenario_playbook.classify_domain(text)
        return {
            "ok": True,
            "domain": domain,
            "route": "不确定时先放 00 收件箱；若是今日过程放 01 今日日志；持续任务写 Action；复用经验写 Card。",
            "safety": scenario_playbook.SAFETY_TEXT,
        }

    if action == "codex-prompt":
        request = str(payload.get("request") or payload.get("text") or "")
        result = assistant_evolution.build_ai_context(config, request, request)
        result["legacy_action"] = "codex-prompt"
        return result

    if action == "open-obsidian":
        vault = scenario_playbook.obsidian_vault(config)
        webbrowser.open(str(vault))
        return {"ok": True, "opened": str(vault)}

    if action == "open-guidebook":
        catalog = assistant_evolution.build_guidebook_catalog(ROOT)
        if not catalog["ok"]:
            return {"ok": False, "error": "guidebook assets are missing"}
        webbrowser.open(catalog["pdf"])
        return {"ok": True, "opened": catalog["pdf"]}

    if action == "open-interaction-guide":
        guide = ROOT / "docs" / "assets" / "gui" / "interaction-guide.html"
        if not guide.exists():
            return {"ok": False, "error": f"interaction guide not found: {guide}"}
        return {
            "ok": True,
            "opened": str(guide),
            "url": "/assets/gui/interaction-guide.html",
            "assets": [
                str(ROOT / "docs" / "assets" / "gui" / "interaction-map.png"),
                str(ROOT / "docs" / "assets" / "gui" / "interaction-states.png"),
            ],
        }

    if action == "open-codex":
        subprocess.Popen(["cmd", "/c", "start", "", str(ROOT)], shell=False)
        return {"ok": True, "opened": str(ROOT)}

    if action == "open-path":
        target = Path(str(payload.get("path") or ""))
        if not target.exists():
            return {"ok": False, "error": f"path not found: {target}"}
        webbrowser.open(str(target))
        return {"ok": True, "opened": str(target)}

    return {"ok": False, "error": f"unsupported action: {action}"}


HTML = (ROOT / "docs" / "assets" / "gui" / "workspace.html").read_text(encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    config_path = DEFAULT_CONFIG

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path in {"/advanced", "/advanced/"}:
            advanced = ROOT / "docs" / "assets" / "gui" / "advanced.html"
            body = advanced.read_bytes()
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.send_header("content-length", "0")
            self.end_headers()
            return
        if parsed.path.startswith("/assets/"):
            relative = unquote(parsed.path.removeprefix("/assets/"))
            target = (ASSET_ROOT / relative).resolve()
            asset_root = ASSET_ROOT.resolve()
            if not str(target).startswith(str(asset_root)) or not target.is_file():
                self._json({"ok": False, "error": "asset not found"}, 404)
                return
            content_types = {
                ".html": "text/html; charset=utf-8",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }
            content_type = content_types.get(target.suffix.lower(), "application/octet-stream")
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("content-type", content_type)
            self.send_header("cache-control", "no-cache")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/status":
            self._json(build_status(self.config_path))
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/action":
            self._json({"ok": False, "error": "not found"}, 404)
            return
        length = int(self.headers.get("content-length") or "0")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            result = run_gui_action(str(data.get("action") or ""), data.get("payload") or {}, self.config_path)
            self._json(result, 200 if result.get("ok") else 400)
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._json({"ok": False, "error": str(exc)}, 500)


def main() -> None:
    parser = argparse.ArgumentParser(description="知识行动助手 GUI")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    Handler.config_path = Path(args.config)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        webbrowser.open(url)
    print(json.dumps({"ok": True, "url": url}, ensure_ascii=False))
    server.serve_forever()


if __name__ == "__main__":
    main()
