from __future__ import annotations

import argparse
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


DEFAULT_CONFIG = ROOT / "config.json"
GUIDEBOOK_DIR = ROOT / "docs" / "guidebook"
GUIDEBOOK_PDF = GUIDEBOOK_DIR / "knowledge-action-assistant-tutorial.pdf"
GUIDEBOOK_SLIDES_DIR = GUIDEBOOK_DIR / "slides"


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def runtime_root(config: dict[str, Any]) -> Path:
    return Path(config.get("runtime_root") or ROOT / ".runtime")


def vault_path(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_vault") or Path.home() / "Documents" / "Obsidian")


def obsidian_run_dir(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_run_dir") or vault_path(config) / "04 例行工作" / "知识行动助手")


def build_guidebook_catalog(repo_root: Path = ROOT) -> dict[str, Any]:
    guidebook_dir = repo_root / "docs" / "guidebook"
    pdf = guidebook_dir / "knowledge-action-assistant-tutorial.pdf"
    slides = sorted((guidebook_dir / "slides").glob("page-*.png"))
    return {
        "ok": pdf.exists() and len(slides) == 7,
        "title": "知识行动助手使用教程",
        "pdf": str(pdf),
        "pdf_size": pdf.stat().st_size if pdf.exists() else 0,
        "page_count": len(slides),
        "slides": [str(path) for path in slides],
        "usage": "先看 7 页教程，再从 GUI 的“今天先干什么”开始试用。",
    }


def build_interaction_model() -> list[dict[str, Any]]:
    return [
        {
            "entry": "今天先干什么",
            "user_input": "可为空",
            "output": "1-3 个今日重点",
            "why_easier": "用户不需要先理解扫描指标，先拿到当天行动。",
        },
        {
            "entry": "记录一个任务",
            "user_input": "任务标题或一句话目标",
            "output": "Action 笔记",
            "why_easier": "把聊天中的任务直接落成可验收笔记。",
        },
        {
            "entry": "这段内容放哪",
            "user_input": "粘贴原文",
            "output": "生活/学习/工作 + 目标位置",
            "why_easier": "先保留来源，不让分类卡住记录动作。",
        },
        {
            "entry": "调用知识索引",
            "user_input": "自然语言查询",
            "output": "可复用的 Action/Card/Time/X-AI 笔记",
            "why_easier": "让沉淀内容能被再次调用，而不是只被归档。",
        },
    ]


def build_initialization_plan(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)
    local_config = config_path.with_name("config.local.json")
    vault = vault_path(config)
    runtime = runtime_root(config)
    steps = [
        "复制 config.example.json 到 config.local.json，并只在本机私有文件里填写真实路径。",
        "运行一键初始化脚本生成 Obsidian 指南和场景报告。",
        "启动 GUI，从“今天先干什么”开始，而不是先看全部扫描指标。",
        "把 guidebook PDF 作为第一份教程资料导入 Obsidian 或 NotebookLM。",
    ]
    commands = [
        "Copy-Item .\\config.example.json .\\config.local.json",
        "powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\init-assistant.ps1",
        "powershell -NoProfile -ExecutionPolicy Bypass -File .\\start-assistant-gui.ps1",
        "python .\\scenario_playbook.py demo --config .\\config.json",
    ]
    return {
        "ok": True,
        "title": "一键初始化与首次启动",
        "config": str(config_path),
        "config_local_exists": local_config.exists(),
        "vault": str(vault),
        "vault_exists": vault.exists(),
        "runtime_root": str(runtime),
        "runtime_exists": runtime.exists(),
        "steps": steps,
        "commands": commands,
        "safety": "初始化默认不删除、不移动、不重命名、不重写源文件；只创建配置副本、报告和明确的新笔记。",
    }


def build_deep_thinking_prompts() -> list[dict[str, Any]]:
    return [
        {
            "mode": "Action",
            "when": "准备推进一个具体任务时",
            "questions": [
                "为什么现在做，而不是放到周复盘？",
                "完成的验收标准是什么？",
                "第一步最小行动是什么？",
                "哪些来源和边界必须保留？",
            ],
        },
        {
            "mode": "Card",
            "when": "发现以后会复用的经验或资料时",
            "questions": [
                "这条内容的复用条件是什么？",
                "什么情况下它不适用？",
                "关键结论能否压缩成一句话？",
                "来源是否足够明确？",
            ],
        },
        {
            "mode": "Time",
            "when": "做日/周/月复盘时",
            "questions": [
                "今天真正推进了什么？",
                "卡点背后的原因是什么？",
                "下一步是否小到可以直接开始？",
                "哪些归档候选应该推迟到周/月处理？",
            ],
        },
        {
            "mode": "X-AI",
            "when": "交给 Codex 或 OpenClaw 继续时",
            "questions": [
                "AI 必须先读哪些真实文件？",
                "安全边界是什么？",
                "输出路径和验收标准是什么？",
                "如果失败，应该保留哪些诊断证据？",
            ],
        },
    ]


def markdown_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip() or fallback
    return fallback


def detect_note_type(text: str, path: Path) -> str:
    lowered = f"{path.as_posix()}\n{text}".lower()
    for name in ["Action", "Card", "Time", "X-AI"]:
        if name.lower() in lowered:
            return name
    return "Note"


def compact_text(text: str, limit: int = 180) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized[: limit - 1] + "…" if len(normalized) > limit else normalized


def lines_from_payload(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def safe_filename(text: str, fallback: str = "AI 对话归档") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\r\n]+', "-", text).strip(" .-")
    return cleaned[:80] or fallback


def build_ai_chat_archive(config: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    generated = now_local()
    title = str(payload.get("title") or "AI 对话归档").strip() or "AI 对话归档"
    source = str(payload.get("source") or "AI 对话").strip()
    background = str(payload.get("background") or payload.get("body") or "").strip()
    conclusions = lines_from_payload(payload.get("conclusions") or payload.get("summary"))
    outputs = lines_from_payload(payload.get("outputs") or payload.get("paths"))
    open_items = lines_from_payload(payload.get("open_items") or payload.get("next"))
    raw_excerpt = str(payload.get("raw") or payload.get("text") or "").strip()

    archive_dir = obsidian_run_dir(config) / "AI 对话归档"
    archive_dir.mkdir(parents=True, exist_ok=True)
    note = archive_dir / f"{generated.strftime('%Y%m%d-%H%M%S')} {safe_filename(title)}.md"
    lines = [
        f"# {title}",
        "",
        "类型：AI 对话归档",
        "用途：已有 AI 对话整理",
        f"生成时间：`{generated.strftime('%Y-%m-%d %H:%M:%S %z')}`",
        f"来源：{source}",
        "",
        "## 任务背景",
        "",
        background or "待补充。",
        "",
        "## 关键结论",
        "",
    ]
    lines.extend(f"- {item}" for item in (conclusions or ["待补充。"]))
    lines.extend(["", "## 产出路径", ""])
    lines.extend(f"- {item}" for item in (outputs or ["待补充。"]))
    lines.extend(["", "## 未完成事项", ""])
    lines.extend(f"- {item}" for item in (open_items or ["待确认。"]))
    if raw_excerpt:
        lines.extend(["", "## 原始片段", "", raw_excerpt])
    lines.extend(
        [
            "",
            "## 边界",
            "",
            "- 这条记录只归档已有 AI 对话，不承担新对话的上下文提取。",
            "- 需要给新的 AI 对话补上下文时，使用“AI 上下文取用”。",
            "",
        ]
    )
    note.write_text("\n".join(lines), encoding="utf-8")
    return {
        "ok": True,
        "action": "archive-ai-chat",
        "title": title,
        "note": str(note),
        "source": source,
        "archive_type": "AI 对话归档",
        "safety": "只写入新的归档笔记，不删除、不移动、不重命名、不重写源文件。",
    }


def build_knowledge_index(config: dict[str, Any], limit: int = 200) -> dict[str, Any]:
    vault = vault_path(config)
    roots = [
        vault / "02 项目" / "知识行动助手",
        vault / "04 例行工作" / "知识行动助手",
        vault / "02 项目" / "Codex",
    ]
    items: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
            if len(items) >= limit:
                break
            try:
                text = path.read_text(encoding="utf-8-sig", errors="ignore")
            except OSError:
                continue
            title = markdown_title(text, path.stem)
            note_type = detect_note_type(text, path)
            items.append(
                {
                    "title": title,
                    "type": note_type,
                    "path": str(path),
                    "modified_at": dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
                    "summary": compact_text(text),
                }
            )
    return {
        "ok": True,
        "vault": str(vault),
        "count": len(items),
        "items": items,
        "usage": "用自然语言查询后，优先复用 Card，再承接到 Action；需要继续交给 AI 时生成 X-AI。",
    }


def score_item(query: str, item: dict[str, Any]) -> int:
    haystack = f"{item.get('title', '')}\n{item.get('type', '')}\n{item.get('summary', '')}".lower()
    tokens = [token for token in re.split(r"\s+|/|\\|，|。|：|:|\||-", query.lower()) if token]
    score = 0
    for token in tokens:
        if token in haystack:
            score += 3 if token in str(item.get("title", "")).lower() else 1
    if item.get("type") == "Card":
        score += 1
    return score


def build_knowledge_call_plan(config: dict[str, Any], query: str) -> dict[str, Any]:
    index = build_knowledge_index(config)
    ranked = sorted(index["items"], key=lambda item: score_item(query, item), reverse=True)
    matches = [item for item in ranked if score_item(query, item) > 0][:5]
    if not matches:
        matches = ranked[:3]
    first_type = matches[0]["type"] if matches else "Note"
    next_action = {
        "Card": "引用这条 Card 的关键结论，再新建 Action 承接当前任务。",
        "Action": "复用这条 Action 的验收标准，并复制可复用步骤到新任务。",
        "Time": "参考这条 Time 复盘里的卡点和下一步，避免重复踩坑。",
        "X-AI": "复用这条 X-AI 的路径、边界和验收标准交给 Codex。",
    }.get(first_type, "先打开匹配笔记，确认来源后再复用。")
    return {
        "ok": bool(matches),
        "query": query,
        "top_matches": matches,
        "next_action": next_action,
        "index": {"count": index["count"], "vault": index["vault"]},
    }


def build_ai_context(config: dict[str, Any], query: str, request: str = "") -> dict[str, Any]:
    query = query.strip() or request.strip() or "当前任务"
    request = request.strip() or query
    call_plan = build_knowledge_call_plan(config, query)
    sources = [
        {
            "title": item.get("title", ""),
            "type": item.get("type", ""),
            "path": item.get("path", ""),
            "why": f"与查询“{query}”在标题、类型或摘要上匹配。",
            "summary": item.get("summary", ""),
        }
        for item in call_plan.get("top_matches", [])
    ]
    compressed_lines = [
        f"- [{source['type']}] {source['title']}：{source['summary']}（来源：{source['path']}）"
        for source in sources
    ]
    compressed_context = "\n".join(compressed_lines) if compressed_lines else "未找到可用上下文，请先补充 Obsidian 笔记或运行知识库体检。"
    next_request = f"请基于以上已整理上下文继续处理：{request}"
    prompt = f"""AI 上下文取用

当前请求：
{request}

可用上下文：
{compressed_context}

使用要求：
- 先引用上述来源路径，再给结论。
- 如果上下文不足，明确指出缺口，不要编造。
- 输出下一步行动，并说明是否需要新建 Action、Card 或复盘记录。

安全边界：
- 不删除、不移动、不重命名、不重写源文件。
- 需要写入时，只写新笔记或追加到明确位置。
"""
    return {
        "ok": True,
        "action": "build-ai-context",
        "query": query,
        "request": request,
        "sources": sources,
        "compressed_context": compressed_context,
        "next_request": next_request,
        "prompt": prompt,
        "safety": "只读取已整理的 Obsidian 笔记、知识卡、项目记录和历史报告；不修改源文件。",
    }


def render_self_evolution_markdown(result: dict[str, Any]) -> str:
    guidebook = result["guidebook"]
    init_plan = result["initialization"]
    lines = [
        "# 知识行动助手自我进化报告",
        "",
        f"生成时间：`{result['generated_at']}`",
        "",
        "## 交互怎么更方便",
        "",
    ]
    for item in result["interaction_model"]:
        lines.append(f"- {item['entry']}：{item['why_easier']} 输出：{item['output']}。")
    lines.extend(
        [
            "",
            "## 安装部署初始化更快捷",
            "",
            f"- 一键初始化入口：`scripts/init-assistant.ps1`",
            f"- 配置状态：`config.local.json` {'已存在' if init_plan['config_local_exists'] else '未创建'}",
            f"- Vault：`{init_plan['vault']}`",
            "- 推荐命令：",
        ]
    )
    lines.extend(f"  - `{command}`" for command in init_plan["commands"])
    lines.extend(["", "## 引领使用者深度思考", ""])
    for prompt in result["deep_thinking_prompts"]:
        lines.append(f"### {prompt['mode']}：{prompt['when']}")
        lines.extend(f"- {question}" for question in prompt["questions"])
        lines.append("")
    lines.extend(["## 归纳内容如何调用", ""])
    index = result["knowledge_index"]
    lines.append(f"- 当前索引笔记数：`{index['count']}`")
    lines.append("- 调用规则：先查 Card 复用结论，再用 Action 承接任务；需要交给 AI 时生成 X-AI。")
    for item in index["items"][:8]:
        lines.append(f"- [{item['type']}] {item['title']}：`{item['path']}`")
    lines.extend(
        [
            "",
            "## Guidebook 入库状态",
            "",
            f"- PDF：`{guidebook['pdf']}`",
            f"- 页数：`{guidebook['page_count']}`",
            "",
            "## 安全边界",
            "",
            "- 本轮进化不删除、不移动、不重命名、不重写源文件。",
            "- 初始化只创建配置副本、报告、新笔记和索引，不批量改写 vault。",
            "",
        ]
    )
    return "\n".join(lines)


def run_self_evolution(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)
    generated = now_local()
    out_dir = runtime_root(config) / "runs" / generated.strftime("%Y-%m-%d") / f"{generated.strftime('%H%M%S')}-evolution"
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "ok": True,
        "generated_at": generated.strftime("%Y-%m-%d %H:%M:%S %z"),
        "guidebook": build_guidebook_catalog(ROOT),
        "interaction_model": build_interaction_model(),
        "initialization": build_initialization_plan(config_path),
        "deep_thinking_prompts": build_deep_thinking_prompts(),
        "knowledge_index": build_knowledge_index(config),
    }
    markdown = render_self_evolution_markdown(result)
    json_report = out_dir / "self-evolution-report.json"
    markdown_report = out_dir / "self-evolution-report.md"
    obsidian_note = obsidian_run_dir(config) / f"{generated.strftime('%Y-%m-%d')} 知识行动助手自我进化报告.md"
    json_report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_report.write_text(markdown, encoding="utf-8")
    obsidian_note.parent.mkdir(parents=True, exist_ok=True)
    obsidian_note.write_text(markdown, encoding="utf-8")
    result.update({"json_report": str(json_report), "markdown_report": str(markdown_report), "obsidian_note": str(obsidian_note)})
    json_report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="知识行动助手自我进化工具")
    parser.add_argument("command", choices=["guidebook", "init", "thinking", "index", "call", "report"])
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--query", default="")
    args = parser.parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)
    if args.command == "guidebook":
        result = build_guidebook_catalog(ROOT)
    elif args.command == "init":
        result = build_initialization_plan(config_path)
    elif args.command == "thinking":
        result = {"ok": True, "prompts": build_deep_thinking_prompts()}
    elif args.command == "index":
        result = build_knowledge_index(config)
    elif args.command == "call":
        result = build_knowledge_call_plan(config, args.query)
    else:
        result = run_self_evolution(config_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
