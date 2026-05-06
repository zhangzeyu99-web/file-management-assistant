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
SAFETY_TEXT = "默认不删除、不移动、不重命名源文件；只读取报告、生成建议、写入明确的 Obsidian 笔记。"


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def runtime_root(config: dict[str, Any]) -> Path:
    return Path(config.get("runtime_root") or ROOT / ".runtime")


def obsidian_vault(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_vault") or Path.home() / "Documents" / "Obsidian")


def obsidian_run_dir(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_run_dir") or obsidian_vault(config) / "04 例行工作" / "文件管理助手")


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


def build_context(config: dict[str, Any]) -> dict[str, Any]:
    file_report = latest_file_report(config)
    obsidian_report = latest_obsidian_report(config)
    file_summary = file_report.get("summary", {}) if file_report else {}
    obsidian_summary = obsidian_report.get("summary", {}) if obsidian_report else {}
    return {
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
    }


def build_scenario_catalog(config: dict[str, Any]) -> list[dict[str, Any]]:
    ctx = build_context(config)
    file_totals = ctx["file_totals"]
    obs_totals = ctx["obsidian_totals"]

    return [
        {
            "id": "daily_review",
            "title": "今天先看什么",
            "user_need": "用户打开助手后，不需要先理解命令，直接得到今天最该看的文件和笔记入口。",
            "when_to_use": "每天开始或结束工作时使用。",
            "steps": [
                "读取最新文件扫描报告和 Obsidian 审计报告。",
                f"优先处理最近回看 {file_totals['recent_review']} 项、建议归档 {file_totals['archive_candidates']} 项。",
                "把下一步写成当天可执行清单，而不是只给统计数字。",
            ],
            "safe_actions": [
                "打开最新 HTML 报告供人工查看。",
                "写入一份 Obsidian 例行工作报告。",
                "生成给 Codex 继续处理的提示词。",
            ],
            "outputs": [
                "场景演示 Markdown 报告",
                "场景演示 JSON 证据",
                "Obsidian 例行工作笔记",
            ],
            "next_action": "先看最新 HTML 报告中的 recent_review 和 archive_candidates，再决定是否让 Codex 继续整理。",
            "acceptance_checks": [
                "能看到最新报告路径。",
                "能看到今天最优先的 1-3 个动作。",
                "没有自动删除、移动、重命名源文件。",
            ],
            "prompt": "帮我根据最新文件扫描和 Obsidian 审计，列出今天最该处理的 3 件事，并把结果归档。",
            "safety": SAFETY_TEXT,
        },
        {
            "id": "inbox_triage",
            "title": "收件箱整理",
            "user_need": "用户只想把临时想法、材料、会话记录放对位置，不想先研究 Obsidian 分类法。",
            "when_to_use": "收件箱堆积、刚结束一段 Codex/OpenClaw 工作、或不知道一段内容该放哪时使用。",
            "steps": [
                f"读取 Obsidian 收件箱待处理数量：{obs_totals['inbox_triage']}。",
                "按 inbox、daily、project、routine、archive 五类给出建议。",
                "保留源路径和上下文，避免把重要信息整理丢。",
            ],
            "safe_actions": [
                "只生成分类建议。",
                "需要写入时只写新的归档笔记。",
                "不改原始笔记内容。",
            ],
            "outputs": [
                "收件箱处理建议",
                "可复制到 Codex 的归档提示词",
                "Obsidian 例行工作记录",
            ],
            "next_action": "把不确定的内容先放收件箱，等每周复盘时再归到项目或例行工作。",
            "acceptance_checks": [
                "每条建议都有目标位置。",
                "保留原始来源或报告路径。",
                "没有覆盖原笔记。",
            ],
            "prompt": "帮我整理 Obsidian 收件箱，按 inbox/daily/project/routine/archive 给出建议，保留来源，不要删除原文。",
            "safety": SAFETY_TEXT,
        },
        {
            "id": "obsidian_health",
            "title": "知识库健康检查",
            "user_need": "用户想知道知识库哪里乱了、哪里需要补链接或补正文，但不想被大量指标淹没。",
            "when_to_use": "每周复盘、NotebookLM 导入前、或准备长期整理知识库时使用。",
            "steps": [
                f"读取当前笔记数：{obs_totals['total_notes']}。",
                f"聚焦空/短笔记 {obs_totals['empty_or_stub']}、低链接笔记 {obs_totals['low_link_notes']}、坏链 {obs_totals['broken_links']}。",
                "只输出少量可行动建议，避免把整理变成额外负担。",
            ],
            "safe_actions": [
                "读取审计报告。",
                "生成修复顺序。",
                "写入健康检查复盘。",
            ],
            "outputs": [
                "知识库健康摘要",
                "修复优先级",
                "复盘记录",
            ],
            "next_action": "先处理坏链和空笔记，再考虑低链接笔记；每次只处理一小批。",
            "acceptance_checks": [
                "风险项有数量和优先级。",
                "建议能在 30 分钟内启动。",
                "不批量改写知识库。",
            ],
            "prompt": "帮我做 Obsidian 知识库健康检查，只列最重要的问题、风险和下一步，不要批量改写笔记。",
            "safety": SAFETY_TEXT,
        },
        {
            "id": "codex_handoff",
            "title": "交给 Codex 继续做",
            "user_need": "用户卡在下一步时，可以一键生成带路径、边界、目标的 Codex 提示词。",
            "when_to_use": "需要从 GUI 跳回当前 Codex 会话、继续长任务、或让 Codex 根据报告继续执行时使用。",
            "steps": [
                "收集 vault、runtime、最新报告路径。",
                "写清楚安全边界：不删除、不移动、不重命名源文件。",
                "把目标改写成可执行任务，而不是泛泛提问。",
            ],
            "safe_actions": [
                "生成提示词。",
                "把提示词复制给 Codex。",
                "把执行结果再写回 Obsidian。",
            ],
            "outputs": [
                "Codex handoff prompt",
                "执行上下文路径",
                "闭环验收清单",
            ],
            "next_action": "复制提示词到 Codex 当前会话，让 Codex 先读真实报告再继续处理。",
            "acceptance_checks": [
                "提示词包含 vault 和 runtime 路径。",
                "提示词包含最新报告入口。",
                "提示词包含安全边界和验收要求。",
            ],
            "prompt": "根据最新报告继续处理这个文件管理助手任务，先读真实文件和报告，再执行并归档。",
            "safety": SAFETY_TEXT,
        },
    ]


def render_markdown(result: dict[str, Any]) -> str:
    ctx = result["context"]
    file_report = ctx.get("file_report") or {}
    obsidian_report = ctx.get("obsidian_report") or {}
    file_totals = ctx["file_totals"]
    obsidian_totals = ctx["obsidian_totals"]
    lines = [
        "# 使用场景示例闭环报告",
        "",
        f"生成时间：`{result['generated_at']}`",
        "",
        "## 闭环验收",
        "",
        "- 从用户场景开始，而不是从命令开始。",
        "- 每个场景都有安全边界、产物、下一步和验收标准。",
        "- 本次演示只生成报告和 Obsidian 笔记，不删除、不移动、不重命名源文件。",
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
        f"- Obsidian 笔记数：`{obsidian_totals['total_notes']}`",
        f"- 收件箱待处理：`{obsidian_totals['inbox_triage']}`",
        "",
        "## 使用场景示例",
        "",
    ]
    for index, scenario in enumerate(result["scenarios"], start=1):
        lines.extend(
            [
                f"### {index}. {scenario['title']} (`{scenario['id']}`)",
                "",
                f"- 用户需求：{scenario['user_need']}",
                f"- 什么时候用：{scenario['when_to_use']}",
                f"- 下一步：{scenario['next_action']}",
                f"- 安全边界：{scenario['safety']}",
                "",
                "操作步骤：",
            ]
        )
        lines.extend(f"{step_index}. {step}" for step_index, step in enumerate(scenario["steps"], start=1))
        lines.extend(["", "安全动作："])
        lines.extend(f"- {item}" for item in scenario["safe_actions"])
        lines.extend(["", "验收标准："])
        lines.extend(f"- {item}" for item in scenario["acceptance_checks"])
        lines.extend(["", "可直接复制的请求：", "", f"> {scenario['prompt']}", ""])
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
    obsidian_note = obsidian_run_dir(config) / f"{stamp_date} 使用场景示例闭环报告.md"

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
    parser = argparse.ArgumentParser(description="Scenario-first playbook for the file management assistant")
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
