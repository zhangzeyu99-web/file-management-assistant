from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config


DEFAULT_CONFIG = ROOT / "config.json"
PRODUCT = {
    "name": "知识行动助手",
    "tagline": "把本地文件、Obsidian 笔记和 AI 对话整理成可归档、可复用、可继续被 AI 取用的上下文资产。",
}
SAFETY_TEXT = "安全边界：不删除源文件，只读取报告和来源，只写明确的新笔记或追加到明确位置；源文件保持原样。"

DOMAIN_BUCKETS = [
    {
        "id": "life",
        "name": "生活",
        "description": "个人事务、证件、学历、财务、健康、账户、家庭材料。",
        "keywords": [
            "cscse",
            "ucsc",
            "degree",
            "certificate",
            "certification",
            "transcript",
            "authorization",
            "学历",
            "认证",
            "证书",
            "授权",
            "个人",
            "财务",
            "健康",
            "账户",
            "家庭",
        ],
    },
    {
        "id": "study",
        "name": "学习",
        "description": "课程、教程、研究资料、NotebookLM、Obsidian 学习、AI 工具学习。",
        "keywords": [
            "notebooklm",
            "obsidian",
            "courseware",
            "tutorial",
            "mindmap",
            "learning",
            "study",
            "课程",
            "教程",
            "学习",
            "思维导图",
            "课件",
            "指南",
        ],
    },
    {
        "id": "work",
        "name": "工作",
        "description": "本地化、游戏项目、客户材料、交付文件、更新公告、自动化项目。",
        "keywords": [
            "codex",
            "file-management-assistant",
            "localization",
            "translation",
            "translate",
            "apk",
            "msix",
            "更新公告",
            "翻译",
            "本地化",
            "巨神",
            "东南亚",
            "欧美",
            "游戏",
            "交付",
            "客户",
            "自动化",
            "语言表",
        ],
    },
]


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def runtime_root(config: dict[str, Any]) -> Path:
    return Path(config.get("runtime_root") or ROOT / ".runtime")


def obsidian_vault(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_vault") or Path.home() / "Documents" / "Obsidian")


def obsidian_run_dir(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_run_dir") or obsidian_vault(config) / "04 例行工作" / "知识行动助手")


def safe_read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        return {"_read_error": f"{path}: {exc}"}


def latest_file_report(config: dict[str, Any]) -> dict[str, Any] | None:
    runs = runtime_root(config) / "runs"
    candidates = sorted(runs.glob("*/*/summary.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for summary_path in candidates:
        if "obsidian" in summary_path.parent.name:
            continue
        html_report = summary_path.with_name("report.html")
        markdown_report = summary_path.with_name("report.md")
        if html_report.exists():
            return {
                "summary_json": str(summary_path),
                "html_report": str(html_report),
                "markdown_report": str(markdown_report) if markdown_report.exists() else "",
                "summary": safe_read_json(summary_path),
            }
    return None


def latest_obsidian_report(config: dict[str, Any]) -> dict[str, Any] | None:
    runs = runtime_root(config) / "runs"
    candidates = sorted(
        runs.glob("*/*-obsidian/obsidian-management-summary.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for summary_path in candidates:
        markdown_report = summary_path.with_name("obsidian-management-report.md")
        if markdown_report.exists():
            return {
                "summary_json": str(summary_path),
                "markdown_report": str(markdown_report),
                "summary": safe_read_json(summary_path),
            }
    return None


def count(summary: dict[str, Any], key: str, default: int = 0) -> int:
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
    value = counts.get(key, summary.get(key, default))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def metric(summary: dict[str, Any], key: str, default: str = "-") -> str:
    value = summary.get(key, default)
    return str(value if value not in (None, "") else default)


def classification_items(summary: dict[str, Any], key: str) -> list[dict[str, Any]]:
    classifications = summary.get("classifications")
    if not isinstance(classifications, dict):
        return []
    items = classifications.get(key)
    return items if isinstance(items, list) else []


def classify_domain(value: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        text = " ".join(str(value.get(key, "")) for key in ("path", "root_name", "extension", "title"))
    else:
        text = str(value)
    lowered = text.lower()
    for bucket in DOMAIN_BUCKETS:
        if any(keyword.lower() in lowered for keyword in bucket["keywords"]):
            return {key: bucket[key] for key in ("id", "name", "description")}
    return {
        "id": "work",
        "name": "工作",
        "description": "未命中生活/学习关键词时，默认先放工作待判断，避免散落在入口目录。",
    }


def build_domain_buckets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = [
        {
            "id": bucket["id"],
            "name": bucket["name"],
            "description": bucket["description"],
            "count": 0,
            "examples": [],
        }
        for bucket in DOMAIN_BUCKETS
    ]
    by_name = {bucket["name"]: bucket for bucket in buckets}
    for item in items:
        domain = classify_domain(item)
        bucket = by_name[domain["name"]]
        bucket["count"] += 1
        if len(bucket["examples"]) < 3:
            bucket["examples"].append(str(item.get("path") or item))
    return buckets


def build_large_file_review(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    for item in items[:3]:
        path = str(item.get("path") or "")
        domain = classify_domain(item)
        review.append(
            {
                "path": path,
                "size_mb": item.get("size_mb", "-"),
                "domain": domain["name"],
                "question": "未来 7 天会不会用？会用就保留在当前任务区，不会用就记录建议归档到对应大类的安装包/交付物目录。",
            }
        )
    return review


def build_act_templates() -> list[dict[str, Any]]:
    return [
        {
            "name": "Action",
            "description": "一任务一笔记，用来承接具体工作。",
            "fields": ["领域", "目标", "来源", "任务背景", "行动过程", "任务成果", "相关资料", "下一步", "验收标准"],
        },
        {
            "name": "Card",
            "description": "把以后会复用的经验、规则、教程、资料沉淀成知识卡。",
            "fields": ["领域", "主题", "来源", "适用场景", "关键结论", "相关链接", "下一步", "验收标准"],
        },
        {
            "name": "Time",
            "description": "日/周/月复盘，按轻重分层处理。",
            "fields": ["周期", "来源", "完成", "卡点", "下一步", "归档候选", "结构调整", "验收标准"],
        },
        {
            "name": "X-AI",
            "description": "AI 上下文取用，让新的 AI 对话能读取已整理的边界、来源和上下文。",
            "fields": ["用户偏好", "工作流", "工具边界", "最近上下文", "来源", "下一步", "验收标准"],
        },
    ]


def build_context(config: dict[str, Any]) -> dict[str, Any]:
    file_report = latest_file_report(config)
    obsidian_report = latest_obsidian_report(config)
    file_summary = file_report.get("summary", {}) if file_report else {}
    obsidian_summary = obsidian_report.get("summary", {}) if obsidian_report else {}
    recent_items = classification_items(file_summary, "recent_review")
    large_items = classification_items(file_summary, "large_files")
    return {
        "product": PRODUCT,
        "vault": str(obsidian_vault(config)),
        "runtime_root": str(runtime_root(config)),
        "file_report": file_report,
        "obsidian_report": obsidian_report,
        "file_summary": file_summary,
        "obsidian_summary": obsidian_summary,
        "file_totals": {
            "total_files": metric(file_summary, "total_files"),
            "archive_candidates": count(file_summary, "archive_candidates"),
            "recent_review": count(file_summary, "recent_review"),
            "installer_cleanup": count(file_summary, "installer_cleanup"),
            "large_files": count(file_summary, "large_files"),
            "duplicate_groups": count(file_summary, "duplicate_groups"),
            "warnings": count(file_summary, "warnings"),
        },
        "obsidian_totals": {
            "total_notes": metric(obsidian_summary, "total_notes"),
            "inbox_triage": count(obsidian_summary, "inbox_triage"),
            "empty_or_stub": count(obsidian_summary, "empty_or_stub"),
            "low_link_notes": count(obsidian_summary, "low_link_notes"),
            "broken_links": count(obsidian_summary, "broken_links"),
        },
        "domain_buckets": build_domain_buckets(recent_items),
        "large_file_review": build_large_file_review(large_items),
        "act_templates": build_act_templates(),
    }


def scenario(
    *,
    sid: str,
    title: str,
    user_phrase: str,
    does: str,
    steps: list[str],
    next_action: str,
    prompt: str,
    outputs: list[str],
    acceptance_checks: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": sid,
        "title": title,
        "user_phrase": user_phrase,
        "does": does,
        "steps": steps,
        "safe_actions": ["只读扫描或生成建议", "写入新报告或明确的新笔记", "保留来源路径和上下文"],
        "outputs": outputs,
        "next_action": next_action,
        "acceptance_checks": acceptance_checks + ["没有自动删除、移动、重命名、重写源文件。"],
        "prompt": prompt,
        "safety": SAFETY_TEXT,
    }
    if extra:
        item.update(extra)
    return item


def build_scenario_catalog(config: dict[str, Any]) -> list[dict[str, Any]]:
    ctx = build_context(config)
    file_totals = ctx["file_totals"]
    obs_totals = ctx["obsidian_totals"]
    return [
        scenario(
            sid="today",
            title="今天先干什么",
            user_phrase="今天先干什么",
            does="读取最新报告，只给最多 3 条今日行动建议；不把全部归档候选变成今日任务。",
            steps=[
                "今日轻量规则：先看今日相关，不要每天处理全部归档候选。",
                "先按生活 / 学习 / 工作分流，再决定具体项目、例行工作或归档建议。",
                f"今日最多收敛到 3 条行动建议；当前收件箱待处理 {obs_totals['inbox_triage']} 条，大文件候选 {file_totals['large_files']} 个。",
                f"当前 {file_totals['archive_candidates']} 个归档候选进入每周或每月批处理，不进入今日清单。",
            ],
            next_action="先看今日相关文件；再清收件箱分类；最后只判断大文件未来 7 天是否会用。",
            prompt="根据最新文件雷达和 Obsidian 体检，只列今日相关事项，并按生活/学习/工作分流；不要让我每天处理全部归档候选。",
            outputs=["今日最多 3 条行动建议", "生活/学习/工作分流", "Codex 继续处理提示词"],
            acceptance_checks=["包含今日轻量规则。", "包含最多 3 条行动建议。", "不要每天处理全部归档候选。"],
            extra={"domain_buckets": ctx["domain_buckets"], "large_file_review": ctx["large_file_review"]},
        ),
        scenario(
            sid="file_radar",
            title="查看文件雷达",
            user_phrase="看看哪些文件要管",
            does="扫描配置目录，列近期、归档候选、大文件、重复文件；默认只报告。",
            steps=[
                "读取 watch_roots 配置。",
                "生成 HTML、Markdown、JSON 报告。",
                "只标出风险和建议，不移动、不删除、不重命名。",
            ],
            next_action="先打开 HTML 报告，只处理今日相关或明确高风险项。",
            prompt="帮我查看文件雷达报告，先列需要我今天关注的 1-3 项，其他归档候选进入周复盘。",
            outputs=["本地 HTML 报告", "Obsidian 文件雷达笔记", "JSON 证据"],
            acceptance_checks=["报告含本地路径。", "大文件和重复文件只给建议。"],
        ),
        scenario(
            sid="inbox_route",
            title="这段内容放哪",
            user_phrase="这段内容放哪",
            does="先分生活/学习/工作，再建议 inbox/daily/project/routine/archive。",
            steps=["保留原文和来源。", "判断领域。", "给目标位置和理由。"],
            next_action="不确定就先放 00 收件箱，并写明来源，周复盘再提升。",
            prompt="帮我判断这段内容放哪：先分生活/学习/工作，再给 inbox/daily/project/routine/archive 建议，保留来源，不覆盖原文。",
            outputs=["归位建议", "可追加到 Obsidian 的笔记片段"],
            acceptance_checks=["每条建议有领域、位置、理由、来源。"],
        ),
        scenario(
            sid="action_note",
            title="记录一个任务",
            user_phrase="记录一个任务",
            does="一任务一笔记：背景、目标、过程、结果、资料、行动清单。",
            steps=["确认领域和目标。", "写 Action 笔记。", "留下下一步和验收标准。"],
            next_action="把正在推进的工作写成 Action，不要散落在聊天记录里。",
            prompt="帮我记录一个任务，按 Action 模板写入 Obsidian：领域、目标、背景、过程、结果、资料、下一步、验收标准。",
            outputs=["Action 任务笔记"],
            acceptance_checks=["笔记包含来源、下一步和验收标准。"],
        ),
        scenario(
            sid="card_capture",
            title="沉淀一张知识卡",
            user_phrase="这个以后会复用",
            does="把经验、规则、教程、资料转成知识卡/索引卡。",
            steps=["提取可复用结论。", "写适用场景。", "链接来源和下一步。"],
            next_action="只沉淀会复用的内容，不强制复杂双链。",
            prompt="把这段经验沉淀成 Card 知识卡：主题、来源、适用场景、关键结论、相关链接、下一步。",
            outputs=["Card 知识卡"],
            acceptance_checks=["有来源、适用场景、关键结论、下一步。"],
        ),
        scenario(
            sid="time_review",
            title="复盘今天/本周",
            user_phrase="复盘今天",
            does="日复盘只轻量，周复盘处理归档 backlog，月复盘优化结构。",
            steps=["记录完成、卡点、下一步。", "只列归档候选，不批量搬文件。", "必要时提出结构调整。"],
            next_action="今天只写轻量 Time；每周再处理收件箱和归档候选。",
            prompt="帮我做 Time 复盘：完成、卡点、下一步、归档候选、结构调整；日复盘保持轻量。",
            outputs=["Time 复盘笔记"],
            acceptance_checks=["日复盘不制造额外整理负担。", "周/月复盘才处理 backlog。"],
        ),
        scenario(
            sid="obsidian_health",
            title="检查知识库",
            user_phrase="知识库乱不乱",
            does="查收件箱、空壳笔记、低链接、断链、重复标题、Codex 索引缺口。",
            steps=[
                f"读取当前笔记数 {obs_totals['total_notes']}。",
                f"聚焦收件箱 {obs_totals['inbox_triage']}、空壳 {obs_totals['empty_or_stub']}、断链 {obs_totals['broken_links']}。",
                "只输出少量可行动建议。",
            ],
            next_action="先修断链和空壳，再处理低链接；每次只处理一小批。",
            prompt="帮我做 Obsidian 体检，只列最重要的问题、风险和下一步，不要批量改写 vault。",
            outputs=["Obsidian 体检报告", "修复优先级"],
            acceptance_checks=["只读审计。", "建议能在 30 分钟内启动。"],
        ),
        scenario(
            sid="ai_chat_archive",
            title="归档 AI 对话",
            user_phrase="整理这段 AI 对话",
            does="把已有 AI 对话保存成可追溯 Obsidian 记录：来源、任务背景、关键结论、产出路径和未完成事项。",
            steps=["保留原始来源和时间。", "提炼背景、结论、产出和未完成事项。", "写入新的归档笔记，不覆盖原文。"],
            next_action="把有价值的 AI 对话先归档；如果要继续问 AI，再使用 AI 上下文取用。",
            prompt="归档这段 AI 对话：保存来源、任务背景、关键结论、产出路径、未完成事项；只做归档，不负责给新对话补上下文。",
            outputs=["AI 对话归档笔记"],
            acceptance_checks=["只写新归档笔记。", "不声称会补充新对话上下文。", "包含来源、背景、结论、产出和未完成事项。"],
        ),
        scenario(
            sid="ai_context_retrieval",
            title="提取 AI 上下文",
            user_phrase="给 AI 补上下文",
            does="从已整理知识库中提取相关笔记、知识卡、项目记录和历史报告，生成可复制给新 AI 对话的上下文 prompt。",
            steps=["收集 vault、runtime、最新报告路径。", "匹配已整理的笔记和知识卡。", "写清来源、边界、下一步请求和验收标准。"],
            next_action="复制上下文 prompt 到新的 AI 对话，让 AI 先引用来源路径再继续处理。",
            prompt="提取 AI 上下文：包含相关来源路径、压缩摘要、当前目标、安全边界、生活/学习/工作分流和验收标准。",
            outputs=["AI 上下文 prompt"],
            acceptance_checks=["包含 vault 和 runtime 路径。", "包含不删除边界。", "包含验收标准。"],
        ),
        scenario(
            sid="assistant_qa",
            title="问答助手",
            user_phrase="我该怎么用",
            does="基于本地结构、报告和规则回答 Obsidian 使用问题。",
            steps=["先读取本地配置。", "结合最新报告回答。", "不编造当前状态。"],
            next_action="用自然语言提问；助手返回可执行步骤和本地路径。",
            prompt="根据我的本地 Obsidian 结构和最新报告，回答我该怎么用；不要编造当前状态。",
            outputs=["自然语言答案", "可执行命令或路径"],
            acceptance_checks=["答案基于本地路径和规则。", "无法确认的状态明确说明。"],
        ),
    ]


def render_markdown(result: dict[str, Any]) -> str:
    ctx = result["context"]
    file_report = ctx.get("file_report") or {}
    obsidian_report = ctx.get("obsidian_report") or {}
    file_totals = ctx["file_totals"]
    obsidian_totals = ctx["obsidian_totals"]
    lines = [
        "# 知识行动助手场景闭环报告",
        "",
        f"生成时间：`{result['generated_at']}`",
        "",
        "## 四层结构",
        "",
        "```text",
        "输入层：本地文件 / Obsidian 笔记 / AI 对话记录 / 手动输入",
        "判断层：生活 / 学习 / 工作 + Action / Card / Time / X-AI",
        "执行层：文件雷达 / Obsidian 体检 / 收件箱归位 / 任务记录 / 知识卡沉淀 / 时间复盘 / AI 对话归档 / AI 上下文取用",
        "输出层：本地报告 / Obsidian 笔记 / GUI 操作入口 / AI 上下文 prompt / 可选通知",
        "```",
        "",
        "## 今日轻量规则",
        "",
        "- 每天不是归档日，只处理：今日相关文件、收件箱分类、大文件保留判断。",
        "- 不要每天处理全部归档候选；归档候选进入每周或每月批处理。",
        "- 先按生活 / 学习 / 工作分流，再决定具体项目、例行工作或归档位置。",
        "- 今天最多收敛到 3 条行动建议，避免被历史积压拖走。",
        "",
        "## 生活 / 学习 / 工作分流",
        "",
    ]
    for bucket in ctx["domain_buckets"]:
        lines.append(f"- {bucket['name']}：{bucket['description']} 当前最近文件命中 `{bucket['count']}` 项。")
        for example in bucket["examples"]:
            lines.append(f"  - 示例：`{example}`")
    if not any(bucket["examples"] for bucket in ctx["domain_buckets"]):
        lines.append("- 当前最新报告没有足够路径样本；仍保留三分法作为默认判断。")
    lines.extend(["", "## Action / Card / Time / X-AI 模板", ""])
    for template in ctx["act_templates"]:
        lines.append(f"- {template['name']}：{template['description']} 字段：{', '.join(template['fields'])}")
    lines.extend(["", "## 大文件保留判断", ""])
    if ctx["large_file_review"]:
        for item in ctx["large_file_review"]:
            lines.append(f"- `{item['path']}`：{item['size_mb']} MB，归类 `{item['domain']}`。判断：{item['question']}")
    else:
        lines.append("- 当前没有大文件样本；今天无需做大文件判断。")
    lines.extend(
        [
            "",
            "## 当前上下文",
            "",
            f"- Obsidian vault：`{ctx['vault']}`",
            f"- 运行目录：`{ctx['runtime_root']}`",
            f"- 最新文件报告：`{file_report.get('html_report') or '暂无'}`",
            f"- 最新 Obsidian 报告：`{obsidian_report.get('markdown_report') or '暂无'}`",
            f"- 扫描文件数：`{file_totals['total_files']}`",
            f"- 建议归档：`{file_totals['archive_candidates']}`",
            f"- 最近回看：`{file_totals['recent_review']}`",
            f"- 大文件：`{file_totals['large_files']}`",
            f"- Obsidian 笔记数：`{obsidian_totals['total_notes']}`",
            f"- 收件箱待处理：`{obsidian_totals['inbox_triage']}`",
            "",
            "## 场景入口",
            "",
        ]
    )
    for index, item in enumerate(result["scenarios"], start=1):
        lines.extend(
            [
                f"### {index}. {item['title']} (`{item['id']}`)",
                "",
                f"- 用户说法：{item['user_phrase']}",
                f"- 实际做什么：{item['does']}",
                f"- 下一步：{item['next_action']}",
                f"- 安全边界：{item['safety']}",
                "",
                "操作步骤：",
            ]
        )
        lines.extend(f"{step_index}. {step}" for step_index, step in enumerate(item["steps"], start=1))
        lines.extend(["", "验收标准："])
        lines.extend(f"- {check}" for check in item["acceptance_checks"])
        lines.extend(["", "可直接复制的请求：", "", f"> {item['prompt']}", ""])
    lines.extend(
        [
            "## 闭环验收",
            "",
            "- 从用户场景开始，而不是从命令开始。",
            "- 每个场景都有安全边界、产物、下一步和验收标准。",
            "- 本轮只生成报告和 Obsidian 笔记，不删除、不移动、不重命名源文件。",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def run_demo(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)
    generated = now_local()
    stamp_date = generated.strftime("%Y-%m-%d")
    stamp_time = generated.strftime("%H%M%S")
    out_dir = runtime_root(config) / "runs" / stamp_date / f"{stamp_time}-scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "ok": True,
        "generated_at": generated.strftime("%Y-%m-%d %H:%M:%S %z"),
        "config": str(config_path),
        "context": build_context(config),
        "scenarios": build_scenario_catalog(config),
    }
    markdown = render_markdown(result)

    json_report = out_dir / "scenario-demo.json"
    markdown_report = out_dir / "scenario-demo.md"
    obsidian_note = obsidian_run_dir(config) / f"{stamp_date} 知识行动助手场景闭环报告.md"

    json_report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_report.write_text(markdown, encoding="utf-8")
    obsidian_note.parent.mkdir(parents=True, exist_ok=True)
    obsidian_note.write_text(markdown, encoding="utf-8")

    result.update(
        {
            "json_report": str(json_report),
            "markdown_report": str(markdown_report),
            "obsidian_note": str(obsidian_note),
        }
    )
    json_report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="知识行动助手场景编排层")
    parser.add_argument("command", choices=["list", "demo"])
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    config_path = Path(args.config)
    if args.command == "list":
        config = load_config(config_path)
        print(json.dumps({"ok": True, "scenarios": build_scenario_catalog(config)}, ensure_ascii=False, indent=2))
        return
    print(json.dumps(run_demo(config_path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
