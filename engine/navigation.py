"""Keep the three Obsidian entry notes in step with the readable library."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path


START = "<!-- knowledge-navigation:start -->"
END = "<!-- knowledge-navigation:end -->"
ENTRY = "00 入口"
HOME = "知识库首页"
RECENT = "知识库最近更新"
THEMES = "知识库主题目录"


def _link(relative: str, label: str) -> str:
    target = relative.replace("\\", "/").removesuffix(".md")
    return f"[[{target}|{label.replace('|', '／')}]]"


def _write_owned(path: Path, content: str) -> bool:
    """Replace the owned block; leave user additions and unowned notes alone."""
    old = path.read_bytes() if path.exists() else b""
    encoding = "utf-8-sig" if old.startswith(b"\xef\xbb\xbf") else "utf-8"
    existing = old.decode(encoding)
    first_newline = existing.find("\n")
    newline = "\r\n" if first_newline > 0 and existing[first_newline - 1] == "\r" else "\n"
    block = (START + "\n" + content.rstrip() + "\n" + END).replace("\n", newline)
    if existing and START not in existing:
        return False
    if START in existing:
        first, tail = existing.split(START, 1)
        if END not in tail:
            return False
        _, last = tail.split(END, 1)
        result = first + block + last
    else:
        result = block + newline
    encoded = result.encode(encoding)
    if encoded == old:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_bytes(encoded)
    if temporary.read_bytes() != encoded:
        raise OSError("入口页保存后读回不一致。")
    temporary.replace(path)
    return True


def sync_navigation(library) -> list[str]:
    """Opt in per vault; no side effects for existing unconfigured libraries."""
    root = library.vault_root
    layout_path = root / ".obsidian" / "knowledge-layout.json"
    if not layout_path.is_file():
        return []
    try:
        layout = json.loads(layout_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if layout.get("version") != 1 or not layout.get("navigation"):
        return []
    snapshot = library.export_snapshot()
    notes = [
        n for n in snapshot["notes"]
        if not n.get("archived") and not n["relative"].startswith((ENTRY + "/", "90 历史/"))
    ]
    projects = defaultdict(list)
    methods = defaultdict(list)
    resources = defaultdict(list)
    daily = []
    for note in notes:
        parts = Path(note["relative"]).parts
        if parts[0] == "10 项目" and len(parts) > 2:
            projects[parts[1]].append(note)
        elif parts[0] == "20 方法" and len(parts) > 2:
            methods[parts[1]].append(note)
        elif parts[0] == "30 资料":
            resources[parts[1] if len(parts) > 2 else "其他资料"].append(note)
        elif parts[0] == "40 日常" and "/模板/" not in note["relative"] and not Path(note["relative"]).stem.endswith("模板"):
            daily.append(note)

    def entry(note, *, with_project=False):
        label = note["title"]
        parts = Path(note["relative"]).parts
        if with_project and parts[0] == "10 项目" and len(parts) > 2 and parts[1] not in label:
            label = parts[1] + " · " + label
        return "- " + _link(note["relative"], label)

    home = [
        "# " + HOME, "", "按项目找结论，按方法复用做法。", "",
        "- " + _link(ENTRY + "/" + RECENT + ".md", "最近更新"),
        "- " + _link(ENTRY + "/" + THEMES + ".md", "全部主题"),
        "", "## 项目", "",
    ]
    purposes = {
        "本地化": "需求、术语与验收", "热血合服": "排单与统计口径",
        "欧美冒险合服": "批次、区间与漏服", "洛克计算器": "计算、发布与海外版",
        "阵容叠加器": "直播布局与分发", "TopData": "报表口径与接口",
        "Hell Asylum": "文字修复与实机验收", "简历与求职": "投递、主页与面试",
    }
    for project, group in sorted(projects.items()):
        overview = next((n for n in group if n["title"] == project or Path(n["relative"]).stem == "项目概览"), None)
        if overview:
            suffix = "：" + purposes[project] if project in purposes else ""
            home.append("- " + _link(overview["relative"], project) + suffix)
        else:
            home.append("- **" + project + "**：" + " · ".join(
                _link(n["relative"], n["title"]) for n in sorted(group, key=lambda n: n["title"])[:4]))
    home += ["", "## 常用方法", ""]
    preferred = ("知识库使用入口", "知识库提问与任务接续", "知识库新增资料与续聊处理", "知识库换机迁移", "视频与播客入库流程",
                 "知识库怎么用", "检索与接续", "只整理新增", "备份与迁移", "视频与播客归档")
    method_notes = [n for group in methods.values() for n in group]
    selected = [n for title in preferred for n in method_notes if n["title"] == title]
    if not selected:
        selected = sorted(method_notes, key=lambda n: n["title"])[:5]
    home += [" · ".join(_link(n["relative"], n["title"]) for n in selected)]
    home += ["", "## 继续使用", "",
             "- 记一条新内容：" + _link("40 日常/知识库收件箱.md", "收件箱") + "。",
             "- AI 问答、检查新增和迁移：[打开知识工作台](http://127.0.0.1:5174/#home)。", ""]

    themes = ["# " + THEMES, "", _link(ENTRY + "/" + HOME + ".md", "返回首页"), ""]
    for heading, groups in [("项目", projects), ("方法", methods), ("资料", resources)]:
        themes += ["## " + heading, ""]
        for name, group in sorted(groups.items()):
            overview = next((n for n in group if n.get("navigation") or n["title"] == name or Path(n["relative"]).stem == "项目概览"), None)
            group_label = name + ("方法" if heading == "方法" else "资料") if name == "游戏研究" else name
            themes += ["### " + (_link(overview["relative"], group_label) if overview else group_label), ""]
            themes += [entry(n) for n in sorted(group, key=lambda n: n["title"]) if n is not overview]
            themes += [""]
    if daily:
        themes += ["## 日常", ""] + [entry(n) for n in sorted(daily, key=lambda n: n["title"])] + [""]

    recent_notes = [n for n in notes if not n.get("navigation") and not Path(n["relative"]).stem.endswith(("概览", "模板"))
                    and "/模板/" not in n["relative"] and n["title"] not in {"收件箱", "知识库收件箱"}]
    recent_notes.sort(key=lambda n: (n.get("modified_at", ""), n["relative"]), reverse=True)
    recent = ["# " + RECENT, "", _link(ENTRY + "/" + HOME + ".md", "返回首页"), ""]
    records = []
    other_updates = []
    for note in recent_notes:
        metadata = re.match(r"\A---\s*\n(.*?)\n---", note.get("markdown", ""), re.S)
        recorded = re.search(r"(?m)^date:\s*(\d{4}-\d{2}-\d{2})\s*$", metadata[1]) if metadata else None
        if note["relative"].startswith("10 项目/") and recorded:
            records.append((recorded[1], note))
        else:
            other_updates.append(note)
    if records:
        recent += ["## 项目记录", "", "按记录日期排列；重新整理不会把旧业务排到今天。", ""]
        current_day = None
        for day, note in sorted(records, key=lambda row: (row[0], row[1]["relative"]), reverse=True)[:50]:
            if day != current_day:
                recent += ["### " + day, ""]
                current_day = day
            recent.append(entry(note, with_project=True))
    if other_updates:
        recent += ["", "## 笔记更新", "", "以下按笔记保存时间排列。", ""]
        current_day = None
        for note in other_updates[:50]:
            day = note.get("modified_at", "")[:10] or "日期未记载"
            if day != current_day:
                recent += ["### " + day, ""]
                current_day = day
            recent.append(entry(note, with_project=True))
    if not recent_notes:
        recent += ["还没有可阅读的主题笔记。"]
    changed = []
    for filename, lines in [(HOME + ".md", home), (RECENT + ".md", recent), (THEMES + ".md", themes)]:
        path = root / ENTRY / filename
        if _write_owned(path, "\n".join(lines)):
            changed.append(path.relative_to(root).as_posix())
    return changed
