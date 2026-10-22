"""Read-only, evidence-first index of an existing Obsidian vault.

This module retrieves source text. It does not make model-generated claims.
Source IDs encode relative paths and passage positions; they are not hashes.
"""

from __future__ import annotations

import base64
import copy
import datetime as dt
import json
import math
import os
import re
import threading
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


MAX_NOTE_BYTES = 8 * 1024 * 1024
UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
THREAD_LINK = re.compile(rf"codex://threads?/{UUID}", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
MAINTENANCE = re.compile(
    r"使用索引|来源索引|归档方法|自动总结流程|笔记体检|覆盖范围|"
    r"迭代记录|迭代自查|运行报告|自检|总览|使用说明|工作台$|handoff|自动任务运行归档",
    re.I,
)
NAVIGATION = re.compile(
    r"找.{0,16}(?:搜|搜索)|优先搜索|按关键词检索|归档建议|调用建议|"
    r"仅索引|后续按关键词|未抽取到用户正文|检索命令|原始会话|消息规模|工作目录|"
    r"继续做事.*查看主题|看自动任务怎么跑|看本次读到了什么|先看下表|"
    r"^\s*[-*]?\s*(?:定义文件|运行摘要|配置路径|项目目录|仓库路径|本地路径|文件位置)\s*[：:]"
)
CONTENT_SIGNAL = re.compile(
    r"决定|完成|交付|口径|步骤|规则|边界|指标|名单|分组|采用|保留|"
    r"不能|不得|先.{0,24}再|没有除以|未完成|待处理|下一步|需补|阻塞|原因"
)
SOURCE_PLACEHOLDER = re.compile(r"仅收录来源|仅登记来源|仅收录元数据|未读取或总结正文|未读取正文")
PROJECT_GUIDE_NOTE = re.compile(
    r"(?:^|\s)(?:user[_ -]?guide|readme)(?:$|[\s._-])|"
    r"使用说明|使用指南|用户指南|操作指南|入门指南", re.I,
)
PROJECT_NAVIGATION_HEADING = re.compile(r"^(?:资料入口|资料目录|相关链接|快捷入口|原文入口|来源|索引)$")
EXAMPLE_CUE = re.compile(r"例如|示例|试一次|试着问|这样问")
PROJECT_COMPARISON = re.compile(
    r"(?:避免|防止|不要|不能|不得|不可|切勿|别)"
    r"[^。！？!?；;\n]{0,30}?(?:与|和|跟)"
    r"[^。！？!?；;\n]{1,160}?(?:混淆|混为一谈|混同|搞混|弄混)"
)
# These are project aliases, not answer templates. Unknown projects still use
# explicit frontmatter/folders/headings and the same general text retrieval.
PROJECT_ALIASES: dict[str, tuple[tuple[str, ...], ...]] = {
    "热血合服": (("热血", "合服"), ("hotblood", "merge")),
    "欧美冒险合服": (("冒险", "合服"),),
    "本地化": (("本地化",), ("localization",), ("lqa",), ("术语",)),
    "简历与求职": (("简历",), ("求职",), ("resume",), ("个人主页",)),
    "洛克计算器": (("洛克",), ("rococalc",), ("roco",), ("rock-calculator",)),
    "视频知识库": (("视频", "总结"), ("播客",), ("next token",)),
    "Obsidian 知识库": (("obsidian",), ("知识行动助手",), ("知识整理助手",), ("个人知识工作台",)),
    "TopData": (("topdata",), ("t后台",)),
    "Hell Asylum": (("hell asylum",),),
}
QUESTION_FILLER = re.compile(
    r"我(?:们)?(?:上次|之前|以前|以前的|想|想要|需要)?|"
    r"上次|之前|以前|请问|请|帮我|帮忙|找一下|找回|查一下|"
    r"为什么|为何|怎么(?:做|处理|用|的)?|怎样|如何|什么|哪些|有没有|是否|"
    r"做过|处理过|做了|做的|"
    r"具体|曾经|当时|告诉我|现在|继续|总结一下|"
    r"(?:做过|处理过|做了|做的|的吗|了吗|呢|吗|的)$"
)
# Short vocabulary equivalences, shared with web/lib/search.ts. These do not
# supply facts or answer templates; they only align wording used in sources.
WORD_ALIASES = (
    (r"服务器合并|合并服务器|并服", "合服"),
    (r"名称冲突|名字冲突|中文撞名|撞名|同名", "重名"),
    (r"每日自动报告|每日自动汇报|每日报告|自动报告|codex\s+daily\s+review", "日报"),
    (r"自动运行", "自动任务"),
    (r"先后步骤|先后顺序|顺序操作|操作顺序|流程|做法|方法", "步骤"),
    (r"windows|桌面版|桌面(?=\s*\d|安装包|包)", "windows"),
    (r"安装程序|安装文件", "安装包"),
    (r"github\s+release|release", "发布"),
    (r"三天", "3天"),
    (r"活跃人数|活跃用户数|活跃玩家数", "登录用户数"),
    (r"增量", "新增"),
)
QUERY_JOINER = re.compile(r"需要|避免|哪一天|哪个|区分|处理|怎么查|从|到|与|和|的|要|是|时|按")
SOFT_TERMS = {
    "步骤", "发布", "交付", "文件", "检查", "更新", "统计", "项目",
    "成果", "记录", "完成", "操作", "查询", "codex", "id", "没有",
    "日期", "总结", "知识", "使用", "采用", "分开", "不能", "直接", "整理",
}
QUERY_WORDS = SOFT_TERMS | {
    "合服", "重名", "安装包", "windows", "字幕", "转写", "飞书", "归档",
    "新增", "重复", "旧文件", "旧线程", "线程", "自动任务", "日报",
    "登录用户数", "用户数", "登录", "活跃", "除以", "统计口径", "战力", "付费",
    "分组", "规则", "边界", "名单", "技能名", "技能", "术语", "中文",
    "数据", "校验", "权限", "错误", "失败", "重试", "取消", "来源",
    "同步", "备份", "回滚", "报告", "维护", "测试", "结果", "版本",
}
QUERY_WORD_PATTERN = re.compile("|".join(sorted(QUERY_WORDS, key=lambda word: (-len(word), word))))
METADATA_LINE = re.compile(
    r"^\s*[-*]?\s*(?:线程\s*ID|原始会话|消息规模|工作目录|"
    r"类型|输入类型|生成时间|最近更新时间|本轮更新时间|归档时间|"
    r"来源路径|文件名|扩展名|大小|修改时间|关联整理记录|"
    r"原对话|窗口内最近活动|结果依据)\s*[：:]",
    re.I,
)
DATE_LINE = re.compile(
    r"(?:最近更新时间|本轮更新时间|窗口内最近活动|生成时间|日期|时间)\s*[：:]\s*"
    r"(\d{4}[-/]\d{2}[-/]\d{2}(?:[T ][\d:.+-]+)?)"
)


def _encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _decode(value: str) -> str:
    try:
        return base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        ).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("无效的资料 ID。") from exc


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]", "", text.casefold())


def _without_comments(text: str) -> str:
    """Exclude hidden metadata while preserving original source line numbers."""
    return HTML_COMMENT.sub(lambda match: "\n" * match.group().count("\n"), text)


def _plain(text: str) -> str:
    text = _without_comments(text)
    text = LINK.sub(lambda match: match.group(1), text)
    text = re.sub(r"\[\[([^]|]+)(?:\|([^]]+))?\]\]", lambda m: m[2] or m[1], text)
    text = re.sub(r"^\s*(?:#{1,6}|[-*+]|\d+[.)])\s+", "", text, flags=re.M)
    return re.sub(r"[`*_]", "", text).strip()


def _reference_only(title: str, text: str) -> bool:
    if not re.fullmatch(r"来源|相关链接|参考来源|参考资料|原文|出处|依据", title.strip()):
        return False
    body = _without_comments(text)
    remainder = re.sub(r"\[\[[^\]]+\]\]|\[[^\]]+\]\([^\n]*?\)|(?:https?://|codex://)[^\s<>]+", "", body)
    return remainder != body and not re.sub(r"[\s\d\-*+.)·、，,；;|/]", "", remainder)


def _display(text: str, limit: int = 320) -> str:
    """A labeled display excerpt, never the text sent to a model."""
    lines = [line for line in text.splitlines() if not METADATA_LINE.match(line)]
    lines = [re.sub(r"\s*\|\s*", " · ", line.strip().strip("|")).strip()
             if line.strip().startswith("|") and line.strip().endswith("|")
             else line for line in lines]
    value = re.sub(r"\s+", " ", _plain("\n".join(lines))).strip()
    return value if len(value) <= limit else value[:limit].rstrip() + "…"


def _links(text: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    labels = {url: label for label, url in LINK.findall(text)}
    for match in THREAD_LINK.finditer(text):
        url = match.group()
        if url in seen:
            continue
        seen.add(url)
        result.append({"url": url, "label": labels.get(url) or "打开原对话",
                       "thread_id": url.rsplit("/", 1)[-1], "origin": "markdown"})
    for match in re.finditer(rf"线程\s*ID\s*[：:]\s*`?({UUID})", text, re.I):
        thread_id = match[1]
        if any(item["thread_id"].casefold() == thread_id.casefold() for item in result):
            continue
        result.append({"url": "codex://threads/" + thread_id, "label": "打开原对话",
                       "thread_id": thread_id, "origin": "recorded_thread_id"})
    return result


def _unique_links(items: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for item in items:
        result.setdefault(item["url"], item)
    return list(result.values())


def _projects_in(text: str) -> list[str]:
    value = _normal(_canonical(_without_comments(text)))
    return [
        name for name, aliases in PROJECT_ALIASES.items()
        if any(all(_normal(part) in value for part in alias) for alias in aliases)
    ]


def _comparison_only_reference(passage: dict[str, Any]) -> bool:
    project = passage["project"]
    if passage["project_origin"] != "alias" or project in passage["heading_projects"]:
        return False
    # A warning against confusing projects can name a comparison target without
    # reporting its progress. Keep direct context and any mention outside that
    # warning; ordinary negative statuses such as "未发布" remain evidence.
    remaining = PROJECT_COMPARISON.sub("", passage["text"])
    return remaining != passage["text"] and project not in _projects_in(remaining)


def _example_for_another_subject(passage: dict[str, Any], plan: dict[str, Any]) -> bool:
    if not EXAMPLE_CUE.search(passage["section"] + "\n" + passage["text"]):
        return False
    declared = passage.get("scope_projects", [])
    owned = passage.get("project_origin") in {"explicit", "folder"}
    if not (declared or owned or PROJECT_GUIDE_NOTE.search(passage["note_title"])):
        return False
    if set(plan["requested"]).intersection(declared):
        return False
    guide = (PROJECT_GUIDE_NOTE.search(passage["note_title"] + " " + passage.get("relative", ""))
             or re.match(r"^20\s*方法/知识库/", passage.get("relative", "")))
    foreign = set(passage.get("topic_names", [])) - set(declared)
    foreign_query = (set(plan["requested"]).intersection(foreign)
                     or any(term not in SOFT_TERMS and term in _search_text(project)
                            for project in foreign for term in plan["terms"]))
    if not guide and not foreign_query:
        return False
    subject = _search_text(passage["note_title"] + (" " + passage["project"] if owned else ""))
    return not ((plan["focus"] and plan["focus"] in subject)
                or any(term not in SOFT_TERMS and term in subject for term in plan["terms"]))


def _canonical(text: str) -> str:
    text = text.casefold()
    for pattern, replacement in WORD_ALIASES:
        text = re.sub(pattern, replacement, text)
    return text


def _requested_projects(query: str) -> list[str]:
    projects = _projects_in(query)
    if "翻译" in query and "本地化" not in projects:
        projects.append("本地化")
    return projects


def _query_terms(query: str) -> tuple[str, list[str]]:
    cleaned = QUERY_JOINER.sub(" ", QUESTION_FILLER.sub(" ", _canonical(query))).strip()
    focus = _normal(cleaned)
    terms: list[str] = []
    separated = QUERY_WORD_PATTERN.sub(lambda match: " " + match.group() + " ", cleaned)
    for token in re.findall(r"[a-z0-9][a-z0-9_.+-]*|[\u3400-\u9fff]+", separated):
        token = _normal(token)
        if len(token) < 2:
            continue
        if (re.fullmatch(r"[\u3400-\u9fff]+", token) and len(token) > 3
                and token not in QUERY_WORDS):
            terms.extend(token[index:index + 2] for index in range(len(token) - 1))
        else:
            terms.append(token)
    return focus, list(dict.fromkeys(terms))


@lru_cache(maxsize=32768)
def _search_text(text: str) -> str:
    text = _canonical(_plain(text))
    if re.search(r"先.{0,50}再", text):
        text += " 步骤"
    return _normal(text)


def _query_plan(query: str, passages: Iterable[dict[str, Any]]) -> dict[str, Any]:
    requested = _requested_projects(query)
    intent = _canonical(query)
    # Project names constrain scope; they are not evidence for the user's
    # specific question inside that scope.
    for project in requested:
        intent = intent.replace(_canonical(project), " ")
        for alias in PROJECT_ALIASES[project]:
            for part in alias:
                intent = intent.replace(_canonical(part), " ")
    if "本地化" in requested:
        intent = intent.replace("翻译", " ")
    focus, terms = _query_terms(intent)
    rows = {p["id"]: (_search_text(p["text"]), _search_text(p["section"])) for p in passages}
    counts = {term: sum(term in text + heading for text, heading in rows.values()) for term in terms}
    # Adjacent Chinese bigrams spanning two words usually do not occur anywhere.
    # Ignore only those bridges in a run with actual vocabulary matches. An
    # unknown whole phrase or alphanumeric identifier must still fail closed.
    if any(counts.values()):
        clean = QUERY_JOINER.sub(" ", QUESTION_FILLER.sub(" ", intent))
        separated = QUERY_WORD_PATTERN.sub(lambda match: " " + match.group() + " ", clean)
        unknown: set[str] = set()
        for token in re.findall(r"[\u3400-\u9fff]+", separated):
            if len(token) > 3 and token not in QUERY_WORDS:
                pieces = [token[i:i + 2] for i in range(len(token) - 1)]
                if not any(counts.get(piece, 0) for piece in pieces):
                    unknown.update(pieces)
        terms = [term for term in terms if counts[term] or term in unknown or re.search(r"[a-z0-9]", term)
                 or re.search(rf"(?<![\u3400-\u9fff]){re.escape(term)}(?![\u3400-\u9fff])",
                              QUERY_JOINER.sub(" ", QUESTION_FILLER.sub(" ", intent)))]
    weights = {term: (math.log(1 + len(rows) / (1 + counts[term])) + 1)
               * (0.3 if term in SOFT_TERMS else 1) for term in terms}
    strong = [term for term in terms if term not in SOFT_TERMS]
    maximum = max((weights[term] for term in strong), default=0)
    anchors = [term for term in strong if weights[term] >= maximum * 0.85]
    missing_ids = [term for term in terms
                   if term not in SOFT_TERMS and re.search(r"[a-z]", term) and not counts[term]]
    return {"requested": requested, "focus": focus, "terms": terms, "weights": weights,
            "anchors": anchors, "rows": rows, "missing_ids": missing_ids}


def _blocks(lines: list[str], start_line: int) -> list[tuple[int, int, str]]:
    """Split paragraphs and individual table rows; keep fenced code intact."""
    result: list[tuple[int, int, str]] = []
    pending: list[str] = []
    first = start_line
    fence = ""

    def flush(end: int) -> None:
        nonlocal pending
        text = "\n".join(pending).strip()
        if text:
            result.append((first, end, text))
        pending = []

    for offset, line in enumerate(lines):
        number = start_line + offset
        if line.lstrip().startswith(("```", "~~~")):
            marker = line.lstrip()[:3]
            fence = "" if fence == marker else marker
        if not fence and not line.strip():
            flush(number - 1)
            continue
        if not fence and re.match(r"^\s*[-*+]\s+", line) and pending:
            flush(number - 1)
        if not pending:
            first = number
        if not fence and line.strip().startswith("|") and line.strip().endswith("|"):
            flush(number - 1)
            first = number
            if not re.fullmatch(r"[\s|:\-]+", line):
                result.append((number, number, line))
            continue
        pending.append(line)
    flush(start_line + len(lines) - 1)
    return result


class Library:
    """Thread-safe in-memory index. Only refresh() reads source Markdown."""

    def __init__(self, vault_root: Path, exclude_roots: Iterable[Path | str] = ()):
        self.vault_root = Path(vault_root).expanduser().resolve()
        self.exclude_roots = [
            (Path(root) if Path(root).is_absolute() else self.vault_root / root).resolve()
            for root in exclude_roots
        ]
        self._notes: dict[str, dict[str, Any]] = {}
        self._passages: dict[str, dict[str, Any]] = {}
        self._signatures: dict[str, tuple[int, int]] = {}
        self._note_aliases: dict[str, str] = {}
        self._archive_paths: set[str] = set()
        self._warnings: list[dict[str, str]] = []
        self._lock = threading.RLock()
        self._refreshed_at: str | None = None

    @property
    def refreshed_at(self) -> str | None:
        with self._lock:
            return self._refreshed_at

    def _safe_path(self, relative: str, *, allow_archive: bool = False) -> Path:
        pure = PurePosixPath(relative)
        archive = len(pure.parts) > 1 and pure.parts[0] == ".source-history"
        registered = archive and (allow_archive or relative in self._archive_paths)
        if (pure.is_absolute() or not pure.parts or "\\" in relative or ":" in relative
                or pure.as_posix() != relative
                or any(part in {"", ".", ".."} or part.startswith(".")
                       and not (index == 0 and registered) for index, part in enumerate(pure.parts))
                or pure.suffix.lower() != ".md"):
            raise ValueError("只允许读取知识库内的 Markdown 笔记。")
        candidate = self.vault_root / Path(*pure.parts)
        if archive and any(parent.exists() and (parent.is_symlink() or
                bool(getattr(parent.lstat(), "st_file_attributes", 0) & 0x400))
                for parent in (candidate, *candidate.parents) if parent.is_relative_to(self.vault_root)):
            raise ValueError("原文存档不允许链接或重解析路径。")
        path = candidate.resolve()
        if not path.is_relative_to(self.vault_root):
            raise ValueError("资料路径不在知识库内。")
        if any(path.is_relative_to(root) for root in self.exclude_roots):
            raise ValueError("此资料位于排除目录。")
        return path

    def _read(self, path: Path, relative: str) -> dict[str, Any]:
        if path.stat().st_size > MAX_NOTE_BYTES:
            raise ValueError("笔记超过 8 MB，请拆分后建立索引；未截断正文。")
        markdown = path.read_text(encoding="utf-8-sig")
        indexed_markdown = _without_comments(markdown)
        lines = indexed_markdown.splitlines()
        metadata: dict[str, str] = {}
        body_start = 0
        if lines and lines[0].strip() == "---":
            for index, line in enumerate(lines[1:], 1):
                if line.strip() == "---":
                    body_start = index + 1
                    break
                match = re.match(r"^(title|project|项目|date|updated|type)\s*:\s*(.+?)\s*$", line)
                if match:
                    metadata[match[1]] = match[2].strip("'\"")
        title = metadata.get("title") or next(
            (match[2] for line in lines[body_start:] if (match := HEADING.match(line))
             and len(match[1]) == 1), path.stem
        )
        stat = path.stat()
        modified_at = dt.datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat()
        note_id = "n_" + _encode(relative)
        root_folder = PurePosixPath(relative).parts[0]
        archived = root_folder == ".source-history" or bool(re.fullmatch(r"90\s*历史", root_folder))
        note_type = metadata.get("type", "").casefold()
        navigation = bool(re.fullmatch(r"00\s*入口", root_folder)) or note_type == "navigation"
        non_evidence = note_type in {"navigation", "template", "answer_archive"}
        note = {
            "id": note_id, "note_id": note_id, "title": title, "relative": relative,
            "path": str(path), "source_path": str(path), "markdown": markdown,
            "modified_at": modified_at, "date": modified_at[:10],
            "source_date": metadata.get("date"),
            "thread_links": _links(indexed_markdown),
            "archived": archived, "navigation": navigation, "type": note_type,
            "searchable": not (archived or navigation or non_evidence),
            "maintenance": navigation or non_evidence
                or bool(MAINTENANCE.search(title + "/" + relative)),
            "passages": [],
        }
        stack: list[tuple[int, str]] = []
        section_lines: list[str] = []
        section_start = body_start + 1
        fence = ""
        sections: list[tuple[list[str], int, list[str]]] = []
        for index in range(body_start, len(lines)):
            line = lines[index]
            if line.lstrip().startswith(("```", "~~~")):
                marker = line.lstrip()[:3]
                fence = "" if fence == marker else marker
            heading = None if fence else HEADING.match(line)
            if heading:
                if section_lines:
                    sections.append(([item[1] for item in stack], section_start, section_lines))
                level = len(heading[1])
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, heading[2]))
                section_start = index + 2
                section_lines = []
            else:
                section_lines.append(line)
        if section_lines:
            sections.append(([item[1] for item in stack], section_start, section_lines))

        explicit_project = metadata.get("project") or metadata.get("项目")
        path_parts = PurePosixPath(relative).parts
        folder_project = next(
            (path_parts[i + 1] for i, part in enumerate(path_parts[:-2])
             if re.fullmatch(r"(?:\d+\s*)?项目", part)), None
        )
        if folder_project in {"Codex", "知识行动助手", "知识整理助手"}:
            folder_project = None
        declared_project = explicit_project or folder_project or ""
        scope_projects = ([declared_project] if declared_project in PROJECT_ALIASES
                          else _projects_in(declared_project))

        for headings, start, content_lines in sections:
            section_title = headings[-1] if headings else title
            scope = "\n".join(content_lines).strip()
            scope_links = _links(scope)
            heading_text = " / ".join(headings) or title
            specific_heading = _projects_in(heading_text)
            date_match = DATE_LINE.search(scope)
            source_date = (date_match[1] if date_match else metadata.get("date"))
            for first, last, text in _blocks(content_lines, start):
                if all(METADATA_LINE.match(line) for line in text.splitlines() if line.strip()):
                    continue
                projects = _projects_in(heading_text + "\n" + text)
                project = explicit_project or (projects[0] if len(projects) == 1 else None)
                project = project or (specific_heading[0] if len(specific_heading) == 1 else None)
                project = project or folder_project
                project_origin = ("explicit" if explicit_project else "alias" if project in PROJECT_ALIASES
                                  else "folder" if folder_project else "section")
                if not project:
                    project = section_title if len(headings) > 1 and not MAINTENANCE.search(section_title) else "其他资料"
                own_links = _links(text)
                if not own_links and len(scope_links) == 1:
                    own_links = scope_links
                passage_id = note_id + ":s_" + _encode(f"{heading_text}\n{first}:{last}")
                reference_only = _reference_only(section_title, text)
                note["passages"].append({
                    "id": passage_id, "note_id": note_id, "title": section_title,
                    "note_title": title, "section": heading_text, "headings": headings,
                    "text": text, "excerpt": _display(text), "line_start": first,
                    "line_end": last, "project": project, "project_id": "p_" + _encode(project),
                    "project_origin": project_origin, "topic_names": projects,
                    "heading_projects": specific_heading, "scope_projects": scope_projects,
                    "relative": relative, "path": str(path), "source_path": str(path),
                    "thread_links": own_links, "modified_at": modified_at,
                    "source_date": source_date, "date_basis": "recorded" if source_date else "file_modified",
                    "archived": note["archived"], "searchable": note["searchable"] and not reference_only,
                    "maintenance": note["maintenance"],
                    "navigation": note["navigation"] or reference_only or bool(NAVIGATION.search(text)),
                    "kind": ("historical_request" if re.search(r"首个需求|最近需求|新增问题", text)
                             else "evidence"), "answer_status": "evidence_only",
                })
        return note

    def _read_alias_paths(self, warnings: list[dict[str, str]]) -> dict[str, str]:
        relative = ".obsidian/knowledge-layout.json"
        path = self.vault_root / relative
        if not path.exists():
            return {}
        try:
            if not path.resolve().is_relative_to(self.vault_root):
                raise ValueError("路径映射文件不在知识库内。")
            if path.stat().st_size > MAX_NOTE_BYTES:
                raise ValueError("路径映射文件超过读取上限。")
            layout = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(layout, dict) or layout.get("version") != 1:
                raise ValueError("不支持的路径映射版本。")
            rows = layout.get("path_aliases", {})
            if not isinstance(rows, dict):
                raise ValueError("路径映射必须是旧路径到新路径的对象。")
            validated: dict[str, str] = {}
            for old, new in rows.items():
                try:
                    if not isinstance(old, str) or not isinstance(new, str):
                        raise ValueError("路径映射必须使用相对 Markdown 路径。")
                    self._safe_path(old, allow_archive=True)
                    self._safe_path(new, allow_archive=True)
                    validated[old] = new
                except ValueError as exc:
                    warnings.append({"path": relative, "reason": str(exc)})
            return validated
        except (OSError, UnicodeError, ValueError) as exc:
            warnings.append({"path": relative, "reason": str(exc)})
            return {}

    @staticmethod
    def _read_note_aliases(notes: dict[str, dict[str, Any]],
                           validated: dict[str, str]) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for old in validated:
            old_id = "n_" + _encode(old)
            if old_id in notes:
                continue
            target, seen = old, set()
            while target in validated and target not in seen:
                seen.add(target)
                target = validated[target]
                target_id = "n_" + _encode(target)
                if target_id in notes:
                    aliases[old_id] = target_id
                    break
        return aliases

    def refresh(self) -> dict[str, Any]:
        """Refresh only changed note files; do not read original source archives."""
        notes: dict[str, dict[str, Any]] = {}
        signatures: dict[str, tuple[int, int]] = {}
        warnings: list[dict[str, str]] = []
        with self._lock:
            if not self.vault_root.is_dir():
                self._notes, self._passages, self._signatures, self._note_aliases = {}, {}, {}, {}
                self._archive_paths = set()
                self._warnings = [{"path": str(self.vault_root), "reason": "知识库目录不存在。"}]
                return {"ok": False, "note_count": 0, "warnings": copy.deepcopy(self._warnings)}
            alias_paths = self._read_alias_paths(warnings)
            self._archive_paths = {path for path in alias_paths.values()
                                   if path.startswith(".source-history/")}

            def read_candidate(candidate: Path, relative: str):
                try:
                    path = self._safe_path(relative)
                    if candidate.is_symlink():
                        return
                    stat = path.stat()
                    signature = (stat.st_mtime_ns, stat.st_size)
                    note_id = "n_" + _encode(relative)
                    note = self._notes.get(note_id)
                    if self._signatures.get(relative) != signature or note is None:
                        note = self._read(path, relative)
                    notes[note_id] = note
                    signatures[relative] = signature
                except (OSError, UnicodeError, ValueError) as exc:
                    warnings.append({"path": relative, "reason": str(exc)})

            for directory, subdirs, filenames in os.walk(self.vault_root, followlinks=False):
                subdirs[:] = sorted([
                    name for name in subdirs if not name.startswith(".")
                    and not (Path(directory) / name).is_symlink()
                    and not any((Path(directory) / name).resolve().is_relative_to(root)
                                for root in self.exclude_roots)
                ])
                for filename in sorted(filenames):
                    if filename.startswith(".") or not filename.lower().endswith(".md"):
                        continue
                    candidate = Path(directory) / filename
                    relative = candidate.relative_to(self.vault_root).as_posix()
                    read_candidate(candidate, relative)
            # Hidden archives are not ordinary notes. Load only exact targets
            # registered by the portable layout, for old-link readback.
            for relative in sorted(self._archive_paths):
                read_candidate(self.vault_root / relative, relative)
            aliases = self._read_note_aliases(notes, alias_paths)
            changed = signatures != self._signatures or aliases != self._note_aliases
            self._note_aliases = aliases
            self._notes = notes
            self._signatures = signatures
            self._passages = {
                passage["id"]: passage for note in notes.values() for passage in note["passages"]
            }
            self._warnings = warnings
            if changed or not self._refreshed_at:
                self._refreshed_at = dt.datetime.now().astimezone().isoformat()
            return {"ok": True, "note_count": sum(not note["archived"] for note in notes.values()),
                    "archive_count": sum(note["archived"] for note in notes.values()),
                    "source_count": sum(not p["archived"] for p in self._passages.values()),
                    "changed": changed, "refreshed_at": self._refreshed_at, "warnings": copy.deepcopy(warnings)}

    @staticmethod
    def _score(passage: dict[str, Any], query: str, plan: dict[str, Any] | None = None) -> float:
        if passage.get("archived") or passage.get("searchable") is False:
            return 0
        plan = plan or _query_plan(query, [passage])
        focus, terms = plan["focus"], plan["terms"]
        requested_projects = plan["requested"]
        if plan["missing_ids"] or not query.strip() or (not requested_projects and not terms):
            return 0
        if _example_for_another_subject(passage, plan):
            return 0
        text, heading = plan["rows"][passage["id"]]
        combined = heading + text
        if requested_projects:
            # A dedicated topic note can declare its project once in metadata
            # or its project folder; each factual paragraph need not repeat it.
            declared = passage.get("scope_projects", [])
            if len(declared) == 1:
                if not set(requested_projects).intersection(declared):
                    return 0
            else:
                # Mixed digests still require a focused section or direct text.
                if (len(passage["topic_names"]) > 1
                        and not set(requested_projects).intersection(passage["heading_projects"])):
                    return 0
                allowed = any(
                    any(all(_normal(_canonical(part)) in combined for part in alias)
                        for alias in PROJECT_ALIASES[project])
                    for project in requested_projects
                )
                if not allowed:
                    return 0
        matches = [term for term in terms if term in combined]
        if plan["anchors"] and not any(term in combined for term in plan["anchors"]):
            return 0
        weight = sum(plan["weights"].values())
        matched_weight = sum(plan["weights"][term] for term in matches)
        coverage = matched_weight / weight if weight else 1
        if terms and (plan["anchors"] or not requested_projects) and (not matches or coverage < 0.42):
            return 0
        score = coverage * 85
        if focus and focus in text:
            score += 30
        if focus and focus in heading:
            score += 15
        body_weight = sum(plan["weights"][term] for term in matches if term in text)
        score += body_weight * 6 / (1 + max(0, len(text) - 500) / 1500)
        score += min(len(CONTENT_SIGNAL.findall(passage["text"])) * 5, 35)
        if "发布" in terms:
            body = _canonical(passage["text"])
            release = r"发布(?!门禁|验收|检查|步骤|计划|准备|包体|预算)"
            if (not re.search(r"(?:未|不|未重新)发布", body)
                    and re.search(release + r".{0,30}(?:已|完成|成功)|(?:已|完成|成功).{0,20}" + release, body)):
                score += 25
        if requested_projects:
            score += 20
            if set(requested_projects).intersection(passage["heading_projects"]):
                score += 20
        if passage["thread_links"]:
            score += 4
        if len(_normal(_plain(passage["text"]))) < 18 and passage["thread_links"]:
            score -= 110
        if passage["navigation"]:
            score -= 55
        if passage["maintenance"]:
            score -= 35
        if passage["text"].lstrip().startswith("|"):
            score -= 15
        if re.search(r"首个需求|最近需求|新增问题", passage["text"]):
            score -= 25
        if SOURCE_PLACEHOLDER.search(passage["text"]):
            score -= 90
        if len(passage["topic_names"]) > 1:
            score -= 75
        return max(score, 0.1)

    def _supplement_result_table(self, items: list[dict[str, Any]],
                                 requested: list[str]) -> list[dict[str, Any]]:
        # Request/status wording can match while a nearby result table only
        # contains names and numbers. Add one bounded, directly citable note;
        # do not lower lexical thresholds or silently append model-only context.
        for index, seed in enumerate(items[:6]):
            if not re.fullmatch(r"新增需求|需求|未完成|待处理|下一步", seed["title"]):
                continue
            note = self._notes.get(seed["note_id"])
            if not note or note["maintenance"] or len(note["markdown"]) > 12000:
                continue
            projects = _projects_in(note["title"])
            if (len(projects) != 1 or projects[0] not in requested
                    or SOURCE_PLACEHOLDER.search(note["markdown"])):
                continue
            sources = [p for p in self._passages.values() if p["note_id"] == note["id"]]
            if any(p["project"] != projects[0] for p in sources):
                continue
            table = [p for p in sources
                     if re.fullmatch(r"实际结果|交付结果|本轮结果|完成情况|已完成", p["title"])
                     and p["text"].strip().startswith("|")]
            if len(table) < 3:
                continue
            supplement = {
                **seed, "id": note["id"], "note_id": note["id"], "kind": "note",
                "title": note["title"], "note_title": note["title"], "section": note["title"],
                "text": note["markdown"], "excerpt": _display("\n".join(p["text"] for p in table)),
                "line_start": 1, "line_end": len(note["markdown"].split("\n")),
                "thread_links": note["thread_links"], "content_complete": True,
                "score": round(max(seed["score"] - 0.01, 0.1), 2),
                "retrieval_reason": "same_note_result_table",
                "supporting_source_ids": [p["id"] for p in table],
            }
            supplement.pop("other_sources", None)
            position = min(index + 1, 5)
            return items[:position] + [supplement] + items[position:]
        return items

    def _complete_short_topics(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result, completed = [], set()
        matched: dict[str, list[str]] = {}
        for item in items:
            matched.setdefault(item["note_id"], []).append(item["id"])
        for seed in items:
            if seed["note_id"] in completed:
                continue
            note = self._notes.get(seed["note_id"])
            eligible = (note and re.match(r"^(?:10\s*项目|20\s*方法|30\s*资料)/", note["relative"])
                        and note["searchable"] and not note["maintenance"]
                        and len(note["markdown"]) <= 12000
                        and len(re.findall(r"^#\s+", _without_comments(note["markdown"]), re.M)) == 1
                        and len({p["project"] for p in note["passages"]}) == 1
                        and not SOURCE_PLACEHOLDER.search(note["markdown"]))
            if not eligible:
                result.append(seed)
                continue
            completed.add(note["id"])
            source_date = note.get("source_date") or seed.get("source_date")
            whole = {**seed, "id": note["id"], "note_id": note["id"], "kind": "note",
                     "title": note["title"], "note_title": note["title"], "section": note["title"],
                     "text": note["markdown"], "line_start": 1, "line_end": len(note["markdown"].split("\n")),
                     "thread_links": note["thread_links"], "content_complete": True,
                     "source_date": source_date, "date_basis": "recorded" if source_date else "file_modified",
                     "retrieval_reason": "complete_short_topic",
                     "supporting_source_ids": matched[note["id"]]}
            whole.pop("other_sources", None)
            result.append(whole)
        return result

    def search(self, query: str, limit: int = 30) -> dict[str, Any]:
        query = str(query or "").strip()
        with self._lock:
            ranked = []
            passages = [p for p in self._passages.values() if p["searchable"] and not p["archived"]]
            plan = _query_plan(query, passages) if query else None
            for passage in passages:
                score = self._score(passage, query, plan) if query else 0
                if score:
                    ranked.append({**passage, "score": round(score, 2)})
            ranked.sort(key=lambda item: (item["score"], item["source_date"] or item["modified_at"]),
                        reverse=True)
            # Identical active text is still kept as alternate provenance.
            deduped: list[dict[str, Any]] = []
            seen: dict[str, dict[str, Any]] = {}
            for item in ranked:
                key = _normal(item["text"])
                if key in seen:
                    seen[key].setdefault("other_sources", []).append({
                        "id": item["id"], "note_id": item["note_id"], "relative": item["relative"]
                    })
                else:
                    seen[key] = item
                    deduped.append(item)
            # A compound question needs evidence for its different terms, not
            # six near-identical daily reports. Keep the best first result and
            # reward still-uncovered query terms for the next five positions.
            if plan and len(plan["anchors"]) > 1 and deduped:
                remaining, diversified = deduped[:], []
                covered: set[str] = set()
                while remaining and len(diversified) < 6:
                    def priority(item: dict[str, Any]) -> float:
                        text, heading = plan["rows"][item["id"]]
                        novel = sum(plan["weights"][term] for term in plan["terms"]
                                    if term not in covered and term in text + heading)
                        return item["score"] + (novel * 16 if diversified else 0)
                    best = max(range(len(remaining)), key=lambda index: priority(remaining[index]))
                    item = remaining.pop(best)
                    diversified.append(item)
                    text, heading = plan["rows"][item["id"]]
                    covered.update(term for term in plan["terms"] if term in text + heading)
                deduped = diversified + remaining
            if plan:
                deduped = self._complete_short_topics(deduped)
                deduped = self._supplement_result_table(deduped, plan["requested"])
            selected = deduped if limit <= 0 else deduped[:limit]
            return copy.deepcopy({
                "query": query, "items": selected, "total": len(deduped),
                "returned": len(selected), "has_more": len(selected) < len(deduped),
                "status": "found" if deduped else "empty", "answer_status": "evidence_only",
            })

    def get_note(self, source_id: str) -> dict[str, Any]:
        with self._lock:
            note_id = source_id.split(":s_", 1)[0]
            if not note_id.startswith("n_"):
                raise ValueError("无效的笔记 ID。")
            self._safe_path(_decode(note_id[2:]), allow_archive=note_id in self._note_aliases)
            if source_id != note_id and source_id not in self._passages:
                raise KeyError("所选段落已变化，请重新搜索。")
            resolved_id = self._note_aliases.get(note_id, note_id) if source_id == note_id else note_id
            if resolved_id not in self._notes:
                raise KeyError("笔记不存在或尚未建立索引。")
            note = copy.deepcopy(self._notes[resolved_id])
            note["selected_source_id"] = source_id
            note["focus"] = copy.deepcopy(self._passages.get(source_id))
            return note

    def resolve_wiki_note(self, target: str, origin: str = "") -> dict[str, str]:
        """Resolve a reading link against indexed notes, including registered history."""
        path, _, anchor = str(target).partition("#")
        path, origin = path.strip().replace("\\", "/"), str(origin).replace("\\", "/")
        if any(part in {".", ".."} for part in path.split("/")) or ":" in path or path.startswith("/"):
            raise ValueError("笔记链接必须使用知识库内的相对路径。")
        with self._lock:
            relative = path if path.lower().endswith(".md") else path + ".md"
            candidates = []
            if not path:
                candidates = [origin] if origin else []
            else:
                if origin and "/" not in path:
                    candidates.append(str(PurePosixPath(origin).parent / relative))
                candidates.append(relative)
                if origin and "/" in path:
                    candidates.append(str(PurePosixPath(origin).parent / relative))
            by_path = {note["relative"].casefold(): note["id"] for note in self._notes.values()}
            for candidate in candidates:
                note_id = by_path.get(candidate.casefold()) or self._note_aliases.get("n_" + _encode(candidate))
                if note_id in self._notes:
                    return {"note_id": note_id, "anchor": anchor.strip()}
            if path and "/" not in path:
                name = PurePosixPath(relative).stem.casefold()
                matches = [note for note in self._notes.values()
                           if PurePosixPath(note["relative"]).stem.casefold() == name
                           or note["title"].casefold() == name]
                if len(matches) == 1:
                    return {"note_id": matches[0]["id"], "anchor": anchor.strip()}
                if len(matches) > 1:
                    raise ValueError("链接有多篇同名笔记，请使用完整路径。")
            raise KeyError("未找到链接笔记，请检查路径或最新同步结果。")

    def context_sources(self, ids: Iterable[str], query: str = "") -> dict[str, Any]:
        """Return exactly the selected sources, complete and in selection order."""
        if isinstance(ids, str):
            ids = [ids]
        with self._lock:
            result: list[dict[str, Any]] = []
            missing: list[str] = []
            for source_id in dict.fromkeys(ids):
                if source_id in self._passages:
                    source = copy.deepcopy(self._passages[source_id])
                    source["content_complete"] = True
                    result.append(source)
                elif source_id in self._notes or source_id in self._note_aliases:
                    note = self._notes[self._note_aliases.get(source_id, source_id)]
                    passages = copy.deepcopy(note["passages"])
                    if query:
                        plan = _query_plan(query, self._passages.values())
                        passages.sort(key=lambda item: self._score(item, query, plan), reverse=True)
                    result.append({
                        "id": note["id"], "note_id": note["id"], "title": note["title"],
                        "text": note["markdown"], "markdown": note["markdown"],
                        "relative": note["relative"], "path": note["path"],
                        "source_path": note["path"], "thread_links": copy.deepcopy(note["thread_links"]),
                        "passages": passages, "content_complete": True, "kind": "note",
                        "modified_at": note["modified_at"], "archived": note["archived"],
                        "source_date": note.get("source_date"),
                        "date_basis": "recorded" if note.get("source_date") else "file_modified",
                        "searchable": note["searchable"], "answer_status": "evidence_only",
                    })
                else:
                    missing.append(source_id)
            return {"items": result, "missing": missing, "query": query,
                    "selected_count": len(result), "answer_status": "evidence_only"}

    def projects(self) -> list[dict[str, Any]]:
        with self._lock:
            source_only_notes = {
                note["id"] for note in self._notes.values()
                if SOURCE_PLACEHOLDER.search(note["markdown"])
            }
            grouped: dict[str, list[dict[str, Any]]] = {}
            for passage in self._passages.values():
                note = self._notes[passage["note_id"]]
                # A guide may mention projects in examples and still be useful
                # search evidence. It does not establish those projects' latest
                # progress or date on the home page.
                guidance = PROJECT_GUIDE_NOTE.search(
                    note["title"] + " " + PurePosixPath(note["relative"]).stem
                )
                if (passage["archived"] or passage["maintenance"] or passage["navigation"]
                        or guidance or PROJECT_NAVIGATION_HEADING.search(passage["title"])
                        or passage["note_id"] in source_only_notes
                        or passage["project"] == "其他资料"
                        or passage["project_origin"] == "section"
                        or _comparison_only_reference(passage)
                        or len(_plain(passage["text"])) < 25):
                    continue
                grouped.setdefault(passage["project"], []).append(passage)
            result: list[dict[str, Any]] = []
            for name, passages in grouped.items():
                passages.sort(key=lambda item: (
                    item["source_date"] or item["modified_at"],
                    len(CONTENT_SIGNAL.findall(item["text"])),
                ), reverse=True)
                latest = passages[0]
                result.append({
                    "id": "p_" + _encode(name), "title": name, "name": name, "query": name,
                    "note_count": len({item["note_id"] for item in passages}),
                    "source_count": len(passages), "source_ids": [item["id"] for item in passages],
                    "latest_at": latest["source_date"] or latest["modified_at"],
                    "date_basis": latest["date_basis"], "excerpt": latest["excerpt"],
                    "thread_links": _unique_links(link for item in passages for link in item["thread_links"]),
                    "status": "evidence_only",
                })
            result.sort(key=lambda item: (item["latest_at"], item["source_count"]), reverse=True)
            return copy.deepcopy(result)

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self._lock:
            project = next((item for item in self.projects() if item["id"] == project_id), None)
            if not project:
                raise KeyError("项目不存在或尚无可用证据。")
            project["items"] = [copy.deepcopy(self._passages[source_id])
                                for source_id in project["source_ids"]]
            return project

    def topics(self) -> list[dict[str, Any]]:
        """Readable knowledge by subject, without navigation or file receipts."""
        with self._lock:
            result = []
            categories = {"10 项目": "项目", "20 方法": "方法", "30 资料": "资料"}
            for note in self._notes.values():
                parts = Path(note["relative"]).parts
                if (note["archived"] or note["maintenance"] or note["navigation"]
                        or not parts or parts[0] not in categories
                        or SOURCE_PLACEHOLDER.search(note["markdown"])):
                    continue
                body = _without_comments(note["markdown"]).strip()
                body = re.sub(r"\A---\s*\n.*?\n---\s*", "", body, count=1, flags=re.S)
                paragraphs = [block.strip() for block in re.split(r"\n\s*\n", body)]
                intro = next((block for block in paragraphs if block and not block.startswith(("#", "|", "[["))), "")
                passages = note.get("passages", [])
                project = next((p["project"] for p in passages if p.get("project") and p["project"] != "其他资料"), "")
                group = parts[1] if len(parts) > 2 else project or "其他资料"
                result.append({**{key: copy.deepcopy(note[key]) for key in
                    ("id", "note_id", "title", "relative", "date", "modified_at")},
                    "category": categories[parts[0]], "group": group, "project": project or group,
                    "excerpt": _display(intro, 140)})
            result.sort(key=lambda item: (item["category"], item["group"].casefold(), item["title"].casefold()))
            return result

    def overview(self) -> dict[str, Any]:
        with self._lock:
            notes = sorted((n for n in self._notes.values() if not n["archived"]),
                           key=lambda item: item["modified_at"], reverse=True)
            recent = [{
                key: copy.deepcopy(note[key]) for key in (
                    "id", "note_id", "title", "relative", "modified_at", "date", "thread_links"
                )
            } for note in notes if not note["maintenance"]
                and not SOURCE_PLACEHOLDER.search(note["markdown"])][:12]
            topics = self.topics()
            return {
                "projects": self.projects()[:8], "recent": recent, "note_count": len(notes),
                "topics": topics, "knowledge_count": len(topics),
                "note_aliases": copy.deepcopy(self._note_aliases),
                "archive_count": len(self._notes) - len(notes),
                "source_count": sum(not p["archived"] for p in self._passages.values()),
                "refreshed_at": self._refreshed_at,
                "warnings": copy.deepcopy(self._warnings), "vault_name": self.vault_root.name,
            }

    def export_snapshot(self) -> dict[str, Any]:
        """Export only this vault index; never follow original-source links.

        Full Markdown appears once in notes. Passage text appears in sources so
        the online reader can use exactly the same selection IDs and citations.
        The caller is responsible for authenticated transport and storage.
        """
        with self._lock:
            notes = [
                {key: copy.deepcopy(value) for key, value in note.items() if key != "passages"}
                for note in self._notes.values()
            ]
            sources = [
                {**{key: copy.deepcopy(passage[key]) for key in (
                    "id", "note_id", "note_title", "title", "section", "relative", "text", "excerpt",
                    "line_start", "line_end", "project", "project_id", "thread_links",
                    "topic_names", "heading_projects", "scope_projects", "project_origin", "maintenance", "navigation", "archived", "searchable",
                    "modified_at", "source_date", "date_basis", "kind",
                )},
                 "scorehint": (-35 if passage["maintenance"] else 0)
                 + (-55 if passage["navigation"] else 0)
                 + min(len(CONTENT_SIGNAL.findall(passage["text"])) * 5, 35)}
                for passage in self._passages.values()
            ]
            return {
                "schema_version": 1, "generated_at": self._refreshed_at,
                "overview": self.overview(), "projects": self.projects(),
                "notes": notes, "sources": sources, "note_aliases": copy.deepcopy(self._note_aliases),
                "answer_status": "evidence_only",
            }
