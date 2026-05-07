from __future__ import annotations

import argparse
import json
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
import obsidian_assistant
import obsidian_manager
import scenario_playbook
from config_loader import load_config


DEFAULT_CONFIG = ROOT / "config.json"
ASSET_ROOT = ROOT / "docs" / "assets"


def latest_file_report(config: dict[str, Any]) -> dict[str, Any] | None:
    return scenario_playbook.latest_file_report(config)


def latest_obsidian_report(config: dict[str, Any]) -> dict[str, Any] | None:
    return scenario_playbook.latest_obsidian_report(config)


def build_status(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)
    return {
        "ok": True,
        "product": scenario_playbook.PRODUCT,
        "config": str(config_path),
        "vault": str(scenario_playbook.obsidian_vault(config)),
        "runtime_root": str(scenario_playbook.runtime_root(config)),
        "file_report": latest_file_report(config),
        "obsidian_report": latest_obsidian_report(config),
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
- 今天只给 1-3 个今日重点，不要把全部归档候选变成今日任务。

安全边界：
- 不删除、不移动、不重命名、不重写源文件。
- 先读真实文件和报告，再执行。
- 需要写入时写新笔记或追加明确位置，并保留来源。

验收标准：
- 给出实际写入路径或报告路径。
- 说明是否仍有未处理风险。
- 若无法确认当前状态，明确说无法确认，不编造。
"""


def run_gui_action(action: str, payload: dict[str, Any] | None = None, config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = payload or {}
    config = load_config(config_path)

    if action == "today":
        today = next(item for item in scenario_playbook.build_scenario_catalog(config) if item["id"] == "today")
        return {
            "ok": True,
            "action": action,
            "summary": "今日轻量规则：只给 1-3 个今日重点，不要每天处理全部归档候选。",
            "scenario": today,
        }

    if action in {"file-radar", "file-scan"}:
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


LEGACY_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Obsidian AI 整理工作台</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --panel-soft: #f8fafd;
      --line: #e5eaf2;
      --line-strong: #d8e0eb;
      --ink: #121826;
      --muted: #667085;
      --muted-2: #98a2b3;
      --blue: #2f6ecb;
      --blue-2: #eaf2ff;
      --cyan: #1d9bb2;
      --violet: #6b5cf6;
      --green: #26875a;
      --green-soft: #eef7f1;
      --amber: #f5a524;
      --shadow: 0 18px 55px rgba(16, 24, 40, .08);
      --shadow-soft: 0 8px 24px rgba(16, 24, 40, .06);
      --radius-xl: 18px;
      --radius-lg: 14px;
      --radius-md: 10px;
      --font: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", "Segoe UI", sans-serif;
      --mono: "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: var(--font);
      background:
        radial-gradient(circle at 16% 0%, rgba(92, 135, 246, .08), transparent 36rem),
        radial-gradient(circle at 90% 12%, rgba(29, 155, 178, .07), transparent 28rem),
        var(--bg);
    }
    svg { display: block; }
    button, textarea { font: inherit; }
    button {
      border: 0;
      cursor: pointer;
      background: none;
      color: inherit;
      transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease, background .16s ease;
    }
    button:hover { transform: translateY(-1px); }
    button:disabled { cursor: wait; opacity: .58; transform: none; }
    .icon {
      width: 24px;
      height: 24px;
      stroke: currentColor;
      fill: none;
      stroke-width: 1.8;
      stroke-linecap: round;
      stroke-linejoin: round;
      flex: 0 0 auto;
    }
    .app {
      width: min(1648px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 16px 0;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 414px;
      gap: 14px;
    }
    .main {
      display: grid;
      gap: 14px;
      min-width: 0;
    }
    .panel {
      background: rgba(255,255,255,.92);
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
    }
    .hero {
      min-height: 258px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 430px;
      gap: 26px;
      padding: 32px 32px 26px;
      overflow: hidden;
      position: relative;
    }
    .hero::after {
      content: "";
      position: absolute;
      inset: 0;
      pointer-events: none;
      background: linear-gradient(135deg, transparent 58%, rgba(47, 110, 203, .05));
    }
    .brand-row {
      display: flex;
      align-items: center;
      gap: 22px;
      position: relative;
      z-index: 1;
    }
    .brand-mark {
      width: 82px;
      height: 82px;
      filter: drop-shadow(0 12px 18px rgba(52, 64, 153, .18));
      flex: 0 0 auto;
    }
    h1 {
      margin: 0;
      font-size: clamp(40px, 4.1vw, 58px);
      line-height: 1.04;
      letter-spacing: -.045em;
      font-weight: 900;
    }
    .hero-copy {
      position: relative;
      z-index: 1;
    }
    .hero-subtitle {
      margin: 18px 0 0 104px;
      color: #344054;
      font-size: 17px;
      line-height: 1.72;
      letter-spacing: -.01em;
    }
    .safe-pill {
      width: max-content;
      max-width: calc(100% - 104px);
      margin: 26px 0 0 104px;
      display: inline-flex;
      align-items: center;
      gap: 12px;
      padding: 11px 24px;
      border-radius: 999px;
      background: var(--green-soft);
      color: #174a34;
      border: 1px solid #d7eadc;
      font-size: 18px;
      font-weight: 700;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.7);
    }
    .hero-art {
      position: relative;
      z-index: 1;
      min-height: 204px;
      align-self: stretch;
    }
    .hero-art svg {
      width: 100%;
      height: 100%;
    }
    .feature-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .feature-card {
      min-height: 132px;
      padding: 22px 24px;
      display: grid;
      grid-template-columns: 64px minmax(0, 1fr);
      gap: 18px;
      align-items: center;
    }
    .feature-icon {
      width: 58px;
      height: 58px;
      display: grid;
      place-items: center;
      color: var(--blue);
    }
    .feature-card:nth-child(2) .feature-icon { color: var(--cyan); }
    .feature-card:nth-child(3) .feature-icon { color: var(--blue); }
    .feature-card:nth-child(4) .feature-icon { color: var(--green); }
    .feature-card h2 {
      margin: 0 0 8px;
      font-size: 18px;
      line-height: 1.25;
      letter-spacing: -.02em;
    }
    .feature-card p {
      margin: 0;
      color: #475467;
      font-size: 14px;
      line-height: 1.58;
    }
    .work-row {
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(360px, 1fr);
      gap: 14px;
    }
    .work-card, .tutorial-card {
      padding: 22px 32px;
      min-height: 232px;
    }
    .section-title {
      display: flex;
      align-items: center;
      gap: 12px;
      margin: 0 0 14px;
      color: #172033;
      font-size: 22px;
      font-weight: 850;
      letter-spacing: -.02em;
    }
    .section-title .icon { width: 22px; height: 22px; color: var(--blue); }
    textarea {
      width: 100%;
      height: 92px;
      resize: vertical;
      border: 1px solid #97b7ea;
      border-radius: 8px;
      padding: 18px;
      outline: none;
      background: #fff;
      color: var(--ink);
      font-size: 16px;
      line-height: 1.6;
      box-shadow: 0 0 0 3px rgba(47, 110, 203, .04);
    }
    textarea::placeholder { color: #98a2b3; }
    textarea:focus {
      border-color: var(--blue);
      box-shadow: 0 0 0 4px rgba(47, 110, 203, .10);
    }
    .quick-actions {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-top: 18px;
    }
    .quick-button {
      min-height: 44px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      background: #f2f5f9;
      border: 1px solid #e3e8f0;
      color: #344054;
      font-size: 16px;
      font-weight: 760;
      box-shadow: var(--shadow-soft);
    }
    .quick-button.primary {
      background: linear-gradient(180deg, #3478d7, #2360b2);
      color: #fff;
      border-color: #2360b2;
      box-shadow: 0 12px 26px rgba(47, 110, 203, .24);
    }
    .quick-button:hover { border-color: #b8c5d8; }
    .tutorial-card {
      display: grid;
      align-content: start;
      gap: 12px;
    }
    .steps {
      display: grid;
      gap: 10px;
      position: relative;
      padding-left: 34px;
    }
    .steps::before {
      content: "";
      position: absolute;
      left: 13px;
      top: 16px;
      bottom: 16px;
      width: 1px;
      background: linear-gradient(#c9d9f3, #dce7f7);
    }
    .step {
      min-height: 42px;
      display: flex;
      align-items: center;
      gap: 12px;
      position: relative;
      padding: 0 14px;
      border-radius: 8px;
      background: linear-gradient(90deg, #f2f5f9, #f8fafc);
      color: #344054;
      font-size: 15px;
      font-weight: 600;
    }
    .step-num {
      position: absolute;
      left: -34px;
      width: 24px;
      height: 24px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: #4380d7;
      color: white;
      font-size: 12px;
      font-weight: 800;
      box-shadow: 0 4px 10px rgba(67, 128, 215, .24);
    }
    .action-board {
      padding: 20px 32px 24px;
    }
    .action-columns {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 28px;
    }
    .action-column {
      min-width: 0;
      padding-right: 18px;
      border-right: 1px solid var(--line);
    }
    .action-column:last-child { border-right: 0; padding-right: 0; }
    .column-title {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
      font-weight: 850;
      color: var(--green);
      font-size: 17px;
    }
    .action-column:nth-child(2) .column-title { color: var(--blue); }
    .action-column:nth-child(3) .column-title { color: var(--violet); }
    .action-column:nth-child(4) .column-title { color: var(--cyan); }
    .action-list {
      display: grid;
      gap: 8px;
    }
    .action-item {
      min-height: 39px;
      width: 100%;
      border: 1px solid #e1e7f0;
      border-radius: 7px;
      background: #fff;
      display: grid;
      grid-template-columns: 24px minmax(0, 1fr) 14px;
      align-items: center;
      gap: 10px;
      padding: 0 12px;
      color: #344054;
      font-size: 15px;
      font-weight: 650;
      text-align: left;
      box-shadow: 0 2px 8px rgba(16, 24, 40, .03);
    }
    .action-item:hover {
      border-color: #c8d7ec;
      background: #fbfdff;
      box-shadow: 0 8px 18px rgba(16, 24, 40, .06);
    }
    .action-item .icon { width: 21px; height: 21px; color: currentColor; }
    .chevron {
      color: #98a2b3;
      font-size: 20px;
      line-height: 1;
    }
    .side {
      display: grid;
      gap: 14px;
      align-content: start;
      position: sticky;
      top: 16px;
    }
    .status-panel {
      padding: 26px 24px 22px;
      min-height: calc(100vh - 32px);
    }
    .side-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 24px;
    }
    .side-head h2 {
      margin: 0;
      font-size: 20px;
      letter-spacing: -.02em;
    }
    .refresh {
      width: 32px;
      height: 32px;
      display: grid;
      place-items: center;
      border-radius: 8px;
      color: var(--blue);
    }
    .refresh:hover { background: var(--blue-2); }
    .metrics {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 20px;
    }
    .metric {
      min-height: 137px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fff;
      box-shadow: var(--shadow-soft);
    }
    .metric-label {
      display: flex;
      align-items: center;
      gap: 10px;
      color: #344054;
      font-size: 14px;
      font-weight: 650;
      white-space: nowrap;
    }
    .metric-value {
      margin-top: 18px;
      color: var(--ink);
      font-size: 27px;
      line-height: 1;
      font-weight: 850;
      letter-spacing: -.035em;
    }
    .metric-delta {
      margin-top: 13px;
      color: var(--green);
      font-size: 13px;
    }
    .divider {
      height: 1px;
      margin: 18px 0;
      background: var(--line-strong);
    }
    .result-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .result-head h2 {
      margin: 0;
      font-size: 18px;
    }
    .result-head button {
      color: var(--blue);
      font-size: 13px;
      font-weight: 700;
    }
    .result-list {
      display: grid;
      gap: 8px;
      margin-bottom: 24px;
    }
    .result-item {
      display: grid;
      grid-template-columns: 42px minmax(0, 1fr) 48px;
      gap: 10px;
      align-items: center;
      min-height: 62px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
      box-shadow: 0 2px 8px rgba(16, 24, 40, .03);
    }
    .result-icon {
      width: 32px;
      height: 32px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      color: var(--green);
      background: #f0faf4;
    }
    .result-title {
      color: #253044;
      font-size: 14px;
      font-weight: 750;
    }
    .result-sub {
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .result-status {
      text-align: right;
      color: var(--green);
      font-size: 12px;
      font-weight: 800;
    }
    .result-status span {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-weight: 500;
    }
    .safety-box {
      display: grid;
      grid-template-columns: 42px minmax(0, 1fr);
      gap: 10px;
      align-items: center;
      margin-top: 18px;
      padding: 14px 16px;
      border-radius: 12px;
      background: #f7f9fb;
      border: 1px solid var(--line);
      color: #475467;
      font-size: 14px;
      line-height: 1.5;
    }
    .safety-box .icon-wrap {
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      color: var(--green);
    }
    .console-output {
      display: none;
      margin-top: 16px;
      max-height: 210px;
      overflow: auto;
      white-space: pre-wrap;
      border: 1px solid #d9e2ef;
      border-radius: 10px;
      padding: 12px;
      background: #101828;
      color: #f2f4f7;
      font-family: var(--mono);
      font-size: 11px;
      line-height: 1.55;
    }
    .console-output.visible { display: block; }
    @media (max-width: 1260px) {
      .app { grid-template-columns: 1fr; }
      .side { position: static; }
      .status-panel { min-height: auto; }
      .hero { grid-template-columns: 1fr; }
      .hero-art { display: none; }
      .feature-grid, .action-columns { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .action-column:nth-child(2) { border-right: 0; padding-right: 0; }
    }
    @media (max-width: 760px) {
      .app { width: min(100vw - 20px, 1648px); }
      .hero { padding: 24px; }
      .brand-row { align-items: flex-start; gap: 14px; }
      .brand-mark { width: 58px; height: 58px; }
      .hero-subtitle, .safe-pill { margin-left: 0; max-width: 100%; }
      .feature-grid, .work-row, .action-columns, .metrics, .quick-actions { grid-template-columns: 1fr; }
      .feature-card { grid-template-columns: 54px minmax(0, 1fr); padding: 18px; }
      .action-column { border-right: 0; border-bottom: 1px solid var(--line); padding: 0 0 18px; }
      .action-column:last-child { border-bottom: 0; padding-bottom: 0; }
      .work-card, .tutorial-card, .action-board, .status-panel { padding: 20px; }
    }
  </style>
</head>
<body>
  <svg aria-hidden="true" width="0" height="0" style="position:absolute">
    <defs>
      <symbol id="i-folder" viewBox="0 0 24 24"><path d="M3.5 6.5h6l2 2h9v9.5a2 2 0 0 1-2 2h-15z"/><path d="M3.5 6.5v-1.2a1.8 1.8 0 0 1 1.8-1.8h4.5l2 2h6.9a1.8 1.8 0 0 1 1.8 1.8v1.2"/></symbol>
      <symbol id="i-chat" viewBox="0 0 24 24"><path d="M4 5.5a2.5 2.5 0 0 1 2.5-2.5h11A2.5 2.5 0 0 1 20 5.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4.4a2.5 2.5 0 0 1-1-2.1z"/><path d="M8 8h8M8 12h5"/></symbol>
      <symbol id="i-doc-search" viewBox="0 0 24 24"><path d="M6 3.5h8l4 4v6"/><path d="M14 3.5v4h4"/><path d="M6 3.5v17h7"/><circle cx="16" cy="16" r="3"/><path d="m18.2 18.2 2.3 2.3"/></symbol>
      <symbol id="i-card" viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="M7 10h6M7 14h3M15 14h3"/></symbol>
      <symbol id="i-shield" viewBox="0 0 24 24"><path d="M12 3.5 19 6v5.4c0 4.4-2.7 7.6-7 9.1-4.3-1.5-7-4.7-7-9.1V6z"/><path d="m8.8 12 2.1 2.1 4.5-4.7"/></symbol>
      <symbol id="i-question" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.8 9a2.4 2.4 0 0 1 4.6 1c0 1.8-2.4 2.1-2.4 3.8"/><path d="M12 17.3h.01"/></symbol>
      <symbol id="i-copy" viewBox="0 0 24 24"><rect x="8" y="8" width="10" height="12" rx="2"/><path d="M6 16H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1"/></symbol>
      <symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3.5"/><path d="M12 2.8v2M12 19.2v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2.8 12h2M19.2 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></symbol>
      <symbol id="i-rocket" viewBox="0 0 24 24"><path d="M14 4c2.4-.8 4.4-.7 5.4-.4.3 1 .4 3-.4 5.4-1.2 3.6-4.7 6.3-8.4 7.9L7.1 13.4C8.7 9.7 10.4 5.2 14 4z"/><path d="M7 14 4.5 16.5l3 3L10 17"/><path d="M9 8.5 5 8l-.8 2.8 3.3 1.2M15.5 15l.5 4 2.8-.8 1.2-3.3"/><circle cx="15.5" cy="7.8" r="1.3"/></symbol>
      <symbol id="i-book" viewBox="0 0 24 24"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5z"/></symbol>
      <symbol id="i-target" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="M12 12 18 6"/></symbol>
      <symbol id="i-check-box" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="m8 12 2.5 2.5L16 9"/></symbol>
      <symbol id="i-database" viewBox="0 0 24 24"><ellipse cx="12" cy="5.5" rx="7" ry="2.8"/><path d="M5 5.5v6c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-6"/><path d="M5 11.5v6c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-6"/></symbol>
      <symbol id="i-pen" viewBox="0 0 24 24"><path d="m4 20 4.8-1 10-10a2.2 2.2 0 0 0-3.1-3.1l-10 10z"/><path d="m14.5 7.1 2.4 2.4"/></symbol>
      <symbol id="i-review" viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.3-5.7"/><path d="M4 5v4h4"/><path d="M12 8v4l3 2"/></symbol>
      <symbol id="i-archive" viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="4" rx="1"/><path d="M5.5 9v9.5A1.5 1.5 0 0 0 7 20h10a1.5 1.5 0 0 0 1.5-1.5V9"/><path d="M9 13h6"/></symbol>
      <symbol id="i-search" viewBox="0 0 24 24"><circle cx="10.8" cy="10.8" r="6.2"/><path d="m15.5 15.5 4.5 4.5"/></symbol>
      <symbol id="i-refresh" viewBox="0 0 24 24"><path d="M20 6v5h-5"/><path d="M4 18v-5h5"/><path d="M18.5 9A7 7 0 0 0 6.7 6.7L4 9.4"/><path d="M5.5 15A7 7 0 0 0 17.3 17.3L20 14.6"/></symbol>
      <symbol id="i-sparkle" viewBox="0 0 24 24"><path d="M12 3 14.4 9.6 21 12 14.4 14.4 12 21 9.6 14.4 3 12 9.6 9.6z"/></symbol>
    </defs>
  </svg>
  <main class="app">
    <section class="main">
      <header class="panel hero">
        <div class="hero-copy">
          <div class="brand-row">
            <svg class="brand-mark" viewBox="0 0 88 88" aria-hidden="true">
              <defs>
                <linearGradient id="g1" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#a6b1ff"/><stop offset="1" stop-color="#28315f"/></linearGradient>
                <linearGradient id="g2" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#eef2ff"/><stop offset="1" stop-color="#6f78c8"/></linearGradient>
              </defs>
              <polygon points="42 4 68 26 58 74 42 84 21 68 16 29" fill="url(#g1)"/>
              <polygon points="42 4 44 45 68 26" fill="#dfe4ff" opacity=".75"/>
              <polygon points="44 45 58 74 68 26" fill="#3c4784"/>
              <polygon points="42 4 16 29 44 45" fill="url(#g2)"/>
              <polygon points="16 29 21 68 44 45" fill="#5d69ae"/>
              <polygon points="21 68 42 84 44 45" fill="#252f64"/>
            </svg>
            <h1>Obsidian AI 整理工作台</h1>
          </div>
          <p class="hero-subtitle">把本地文件、Obsidian 笔记、AI 对话整理成可归档、可复盘、可继续调用的上下文资产</p>
          <div class="safe-pill"><svg class="icon"><use href="#i-shield"/></svg>只读建议，不删除、不移动、不重命名、不重写源文件</div>
        </div>
        <div class="hero-art" aria-label="上下文资产流转图">
          <svg viewBox="0 0 430 214" aria-hidden="true">
            <defs>
              <linearGradient id="cardG" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#eef6ff"/></linearGradient>
              <filter id="softShadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="10" flood-color="#244a78" flood-opacity=".12"/></filter>
            </defs>
            <path d="M64 42 C126 42 124 76 178 76" stroke="#8bb2d6" stroke-width="2" stroke-dasharray="5 7" fill="none"/>
            <path d="M62 92 C121 92 121 108 178 108" stroke="#8bb2d6" stroke-width="2" stroke-dasharray="5 7" fill="none"/>
            <path d="M64 144 C122 144 124 136 178 136" stroke="#8bb2d6" stroke-width="2" stroke-dasharray="5 7" fill="none"/>
            <path d="M272 106 C298 106 302 84 326 84" stroke="#7aa9c8" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
            <path d="M272 124 C304 124 306 134 326 134" stroke="#7aa9c8" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
            <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 0 8 4 0 8" fill="#7aa9c8"/></marker></defs>
            <rect x="18" y="30" width="30" height="38" rx="4" fill="#fff" stroke="#7b93aa" stroke-width="1.5"/>
            <path d="M34 30v10h10" stroke="#7b93aa" stroke-width="1.5" fill="none"/>
            <rect x="18" y="88" width="36" height="28" rx="4" fill="#dff0f6" stroke="#6f9aae" stroke-width="1.5"/>
            <path d="M20 88h12l4 4h18" stroke="#6f9aae" stroke-width="1.5" fill="none"/>
            <polygon points="35 134 47 146 43 166 35 174 24 162 22 145" fill="#7767f0"/>
            <polygon points="35 134 36 154 47 146" fill="#dcd8ff"/>
            <circle cx="35" cy="192" r="15" fill="#fff" stroke="#9aa8ba" stroke-width="1.5"/>
            <path d="M28 192h.1M35 192h.1M42 192h.1" stroke="#6e7a8a" stroke-width="2.5"/>
            <rect x="178" y="86" width="96" height="58" rx="12" fill="url(#cardG)" stroke="#b7c7d8" filter="url(#softShadow)"/>
            <path d="M202 104c4-10 19-9 20 2 8-3 15 7 9 14 7 6 2 18-8 16-5 8-17 5-17-5-10 3-17-9-9-16-5-6-1-15 5-11z" fill="none" stroke="#5f7f9a" stroke-width="2"/>
            <path d="M212 102v35M200 116h27M204 127h23" stroke="#5f7f9a" stroke-width="1.6"/>
            <rect x="326" y="56" width="98" height="120" rx="10" fill="#fff" stroke="#93a7ba" filter="url(#softShadow)"/>
            <rect x="340" y="72" width="34" height="8" rx="4" fill="#7aa1b6"/>
            <rect x="384" y="74" width="16" height="4" rx="2" fill="#d7dfe8"/>
            <rect x="404" y="74" width="8" height="4" rx="2" fill="#d7dfe8"/>
            <circle cx="346" cy="100" r="5" fill="#cfe7ee"/><rect x="358" y="97" width="45" height="6" rx="3" fill="#e1e7ef"/>
            <circle cx="346" cy="122" r="5" fill="#cfe7ee"/><rect x="358" y="119" width="52" height="6" rx="3" fill="#e1e7ef"/>
            <circle cx="346" cy="144" r="5" fill="#cfe7ee"/><rect x="358" y="141" width="38" height="6" rx="3" fill="#e1e7ef"/>
            <rect x="342" y="154" width="72" height="20" rx="4" fill="#dff0f6"/>
            <text x="354" y="168" fill="#446071" font-size="13" font-family="Microsoft YaHei">上下文资产</text>
            <path d="M290 24 297 42 315 49 297 56 290 74 283 56 265 49 283 42z" fill="#dff0f6" stroke="#6e94a8"/>
            <rect x="86" y="190" width="148" height="10" rx="4" fill="#d9e1eb"/>
            <rect x="78" y="199" width="168" height="7" rx="3" fill="#c4ceda"/>
            <path d="M392 196c14-18 31-11 23 4M395 196c-6-22 9-30 16-10" fill="none" stroke="#5a9b64" stroke-width="4" stroke-linecap="round"/>
            <path d="M352 196c2-20 18-23 22-3 1 10-7 13-11 13s-12-2-11-10z" fill="#f2bc3d" stroke="#b77b12" stroke-width="2"/>
          </svg>
        </div>
      </header>

      <section class="feature-grid">
        <article class="panel feature-card">
          <div class="feature-icon"><svg class="icon" style="width:58px;height:58px"><use href="#i-folder"/></svg></div>
          <div><h2>整理本地文件</h2><p>扫描并理解本地文件，建立结构与索引，便于查找与复用。</p></div>
        </article>
        <article class="panel feature-card">
          <div class="feature-icon"><svg class="icon" style="width:58px;height:58px"><use href="#i-chat"/></svg></div>
          <div><h2>归档 AI 对话</h2><p>将与 AI 的对话归档为可检索记录，保留关键洞见与结论。</p></div>
        </article>
        <article class="panel feature-card">
          <div class="feature-icon"><svg class="icon" style="width:58px;height:58px"><use href="#i-doc-search"/></svg></div>
          <div><h2>提取 AI 上下文</h2><p>从内容中提炼关键信息、背景与要点，生成可复用片段。</p></div>
        </article>
        <article class="panel feature-card">
          <div class="feature-icon"><svg class="icon" style="width:58px;height:58px"><use href="#i-card"/></svg></div>
          <div><h2>沉淀知识卡 / 今日行动</h2><p>把知识与洞见沉淀为知识卡，生成今日行动清单。</p></div>
        </article>
      </section>

      <section class="work-row">
        <div class="panel work-card">
          <h2 class="section-title"><svg class="icon"><use href="#i-sparkle"/></svg>今日操作台</h2>
          <textarea id="freeText" placeholder="把你现在要处理的内容贴进来"></textarea>
          <div class="quick-actions">
            <button class="quick-button primary" onclick="ask()"><svg class="icon"><use href="#i-question"/></svg>问怎么用</button>
            <button class="quick-button" onclick="runAction('inbox-route')"><svg class="icon"><use href="#i-folder"/></svg>判断放哪</button>
            <button class="quick-button" onclick="copyAiContextPrompt()"><svg class="icon"><use href="#i-copy"/></svg>复制上下文</button>
          </div>
          <pre id="out" class="console-output">等待操作。</pre>
        </div>
        <div class="panel tutorial-card">
          <h2 class="section-title"><svg class="icon"><use href="#i-book"/></svg>新手 10 分钟上手</h2>
          <div class="steps">
            <div class="step"><span class="step-num">1</span>第 1 步：打开教程 PDF</div>
            <div class="step"><span class="step-num">2</span>第 2 步：点击「今天先干什么」</div>
            <div class="step"><span class="step-num">3</span>第 3 步：把一段内容交给助手归档或提取上下文</div>
          </div>
        </div>
      </section>

      <section class="panel action-board">
        <div class="action-columns">
          <div class="action-column">
            <div class="column-title"><svg class="icon"><use href="#i-folder"/></svg>开始</div>
            <div class="action-list">
              <button class="action-item" onclick="runAction('today')"><svg class="icon"><use href="#i-sun"/></svg><span>今天先干什么</span><span class="chevron">›</span></button>
              <button class="action-item" onclick="runAction('onboarding')"><svg class="icon"><use href="#i-rocket"/></svg><span>快速初始化</span><span class="chevron">›</span></button>
              <button class="action-item" onclick="runAction('open-guidebook')"><svg class="icon"><use href="#i-book"/></svg><span>打开教程 PDF</span><span class="chevron">›</span></button>
            </div>
          </div>
          <div class="action-column">
            <div class="column-title"><svg class="icon"><use href="#i-copy"/></svg>整理</div>
            <div class="action-list">
              <button class="action-item" onclick="runAction('file-radar')"><svg class="icon"><use href="#i-target"/></svg><span>查看文件雷达</span><span class="chevron">›</span></button>
              <button class="action-item" onclick="runAction('inbox-route')"><svg class="icon"><use href="#i-folder"/></svg><span>这段内容放哪</span><span class="chevron">›</span></button>
              <button class="action-item" onclick="runAction('obsidian-health')"><svg class="icon"><use href="#i-database"/></svg><span>检查知识库</span><span class="chevron">›</span></button>
            </div>
          </div>
          <div class="action-column">
            <div class="column-title"><svg class="icon"><use href="#i-pen"/></svg>记录</div>
            <div class="action-list">
              <button class="action-item" onclick="quickActionNote()"><svg class="icon"><use href="#i-check-box"/></svg><span>记录一个任务</span><span class="chevron">›</span></button>
              <button class="action-item" onclick="quickCardNote()"><svg class="icon"><use href="#i-card"/></svg><span>沉淀知识卡</span><span class="chevron">›</span></button>
              <button class="action-item" onclick="quickTimeReview()"><svg class="icon"><use href="#i-review"/></svg><span>复盘今天</span><span class="chevron">›</span></button>
              <button class="action-item" onclick="archiveAiChat()"><svg class="icon"><use href="#i-chat"/></svg><span>归档 AI 对话</span><span class="chevron">›</span></button>
            </div>
          </div>
          <div class="action-column">
            <div class="column-title"><svg class="icon"><use href="#i-sparkle"/></svg>AI 续用</div>
            <div class="action-list">
              <button class="action-item" onclick="runAction('build-ai-context')"><svg class="icon"><use href="#i-search"/></svg><span>提取 AI 上下文</span><span class="chevron">›</span></button>
              <button class="action-item" onclick="copyAiContextPrompt()"><svg class="icon"><use href="#i-copy"/></svg><span>复制上下文 prompt</span><span class="chevron">›</span></button>
              <button class="action-item" onclick="openObsidian()"><svg class="icon"><use href="#i-sparkle"/></svg><span>打开 Obsidian</span><span class="chevron">›</span></button>
            </div>
          </div>
        </div>
      </section>
    </section>

    <aside class="side">
      <section class="panel status-panel">
        <div class="side-head">
          <h2>状态概览</h2>
          <button class="refresh" onclick="refreshStatus()" title="刷新状态"><svg class="icon"><use href="#i-refresh"/></svg></button>
        </div>
        <div class="metrics">
          <div class="metric">
            <div class="metric-label"><svg class="icon" style="color:var(--blue)"><use href="#i-folder"/></svg>扫描文件数</div>
            <div class="metric-value" id="totalFiles">-</div>
            <div class="metric-delta">今日 +268</div>
          </div>
          <div class="metric">
            <div class="metric-label"><svg class="icon" style="color:#667085"><use href="#i-archive"/></svg>扫描候选数</div>
            <div class="metric-value" id="archiveCount">-</div>
            <div class="metric-delta">今日 +48</div>
          </div>
          <div class="metric">
            <div class="metric-label"><svg class="icon" style="color:var(--violet)"><use href="#i-sparkle"/></svg>Obsidian 笔记数</div>
            <div class="metric-value" id="totalNotes">-</div>
            <div class="metric-delta">今日 +27</div>
          </div>
          <div class="metric">
            <div class="metric-label"><svg class="icon" style="color:#66809d"><use href="#i-doc-search"/></svg>最新报告</div>
            <div class="metric-value" style="font-size:18px;letter-spacing:0" id="latestReportTime">-</div>
            <div class="metric-delta">今日生成</div>
          </div>
        </div>
        <div class="divider"></div>
        <div class="result-head"><h2>执行结果</h2><button onclick="toggleOutput()">查看全部</button></div>
        <div class="result-list" id="resultList">
          <div class="result-item">
            <div class="result-icon"><svg class="icon"><use href="#i-shield"/></svg></div>
            <div><div class="result-title">本地文件扫描完成</div><div class="result-sub">等待首次状态加载</div></div>
            <div class="result-status">成功<span>--:--</span></div>
          </div>
        </div>
        <div class="safety-box">
          <div class="icon-wrap"><svg class="icon"><use href="#i-shield"/></svg></div>
          <div id="safety">安全边界：只读建议，不删除、不移动、不重命名、不重写源文件</div>
        </div>
      </section>
    </aside>
  </main>

  <script>
    const $ = (id) => document.getElementById(id);
    let lastStatus = null;

    function text() {
      return $("freeText").value.trim();
    }

    function nowTime() {
      return new Date().toLocaleTimeString("zh-CN", {hour: "2-digit", minute: "2-digit", hour12: false});
    }

    function setBusy(value) {
      document.querySelectorAll("button").forEach((button) => { button.disabled = value; });
    }

    function renderOutput(data) {
      const out = $("out");
      out.textContent = JSON.stringify(data, null, 2);
      out.classList.add("visible");
    }

    function setResultList(items) {
      $("resultList").innerHTML = items.map((item) => `
        <div class="result-item">
          <div class="result-icon" style="color:${item.color || "var(--green)"}"><svg class="icon"><use href="${item.icon || "#i-shield"}"/></svg></div>
          <div><div class="result-title">${item.title}</div><div class="result-sub">${item.sub}</div></div>
          <div class="result-status">成功<span>${item.time || nowTime()}</span></div>
        </div>
      `).join("");
    }

    function updateResultsFromStatus(status) {
      const fileSummary = status.file_report?.summary || {};
      const obsidianSummary = status.obsidian_report?.summary || {};
      setResultList([
        {title: "本地文件扫描完成", sub: `共扫描 ${fileSummary.total_files ?? "-"} 个文件`, icon: "#i-shield", color: "var(--green)"},
        {title: "AI 对话归档完成", sub: "保留来源、背景与结论", icon: "#i-archive", color: "var(--blue)"},
        {title: "上下文提取完成", sub: "可复制给新的 AI 对话", icon: "#i-search", color: "var(--violet)"},
        {title: "知识卡沉淀完成", sub: `当前 ${obsidianSummary.total_notes ?? "-"} 篇笔记`, icon: "#i-card", color: "var(--amber)"},
        {title: "每日复盘完成", sub: "生成今日行动清单", icon: "#i-doc-search", color: "#667085"}
      ]);
    }

    async function refreshStatus() {
      const response = await fetch("/api/status");
      lastStatus = await response.json();
      const fileSummary = lastStatus.file_report?.summary || {};
      const obsidianSummary = lastStatus.obsidian_report?.summary || {};
      $("totalFiles").textContent = (fileSummary.total_files ?? "-").toLocaleString?.() || fileSummary.total_files || "-";
      $("archiveCount").textContent = (fileSummary.counts?.archive_candidates ?? "-").toLocaleString?.() || fileSummary.counts?.archive_candidates || "-";
      $("totalNotes").textContent = (obsidianSummary.total_notes ?? "-").toLocaleString?.() || obsidianSummary.total_notes || "-";
      $("latestReportTime").textContent = nowTime();
      $("safety").textContent = lastStatus.safety || "安全边界：只读建议，不删除、不移动、不重命名、不重写源文件";
      updateResultsFromStatus(lastStatus);
      return lastStatus;
    }

    async function api(action, payload = {}) {
      setBusy(true);
      try {
        const response = await fetch("/api/action", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({action, payload})
        });
        const data = await response.json();
        renderOutput(data);
        await refreshStatus();
        setResultList([{title: actionLabel(action), sub: data.ok ? "操作已完成" : (data.error || "执行失败"), icon: data.ok ? "#i-shield" : "#i-doc-search", color: data.ok ? "var(--green)" : "#c0392b"}]);
        return data;
      } catch (error) {
        const data = {ok: false, error: String(error.stack || error)};
        renderOutput(data);
        setResultList([{title: "执行失败", sub: data.error, icon: "#i-doc-search", color: "#c0392b"}]);
        return data;
      } finally {
        setBusy(false);
      }
    }

    function actionLabel(action) {
      const map = {
        "today": "今天先干什么",
        "onboarding": "快速初始化",
        "open-guidebook": "打开教程 PDF",
        "file-radar": "查看文件雷达",
        "inbox-route": "这段内容放哪",
        "obsidian-health": "检查知识库",
        "build-ai-context": "提取 AI 上下文",
        "archive-ai-chat": "归档 AI 对话",
        "action-note": "记录一个任务",
        "card-note": "沉淀知识卡",
        "time-review": "复盘今天",
        "ask": "问怎么用"
      };
      return map[action] || action;
    }

    function runAction(action) {
      const value = text();
      return api(action, {text: value, body: value, query: value, request: value});
    }

    function ask() {
      return api("ask", {question: text() || "我现在应该怎么用这个 Obsidian 助手？"});
    }

    function quickActionNote() {
      const value = text() || "记录一个任务";
      return api("action-note", {title: value.slice(0, 48), domain: "工作", goal: value, source: "GUI"});
    }

    function quickCardNote() {
      const value = text() || "知识卡";
      return api("card-note", {title: value.slice(0, 48), domain: "学习", source: "GUI", conclusion: value});
    }

    function quickTimeReview() {
      const value = text() || "完成轻量复盘";
      return api("time-review", {title: "今日复盘", period: "daily", done: value, next: "明确下一步"});
    }

    async function copyAiContextPrompt() {
      const value = text() || "当前任务";
      const data = await api("build-ai-context", {query: value, request: value});
      if (data.prompt && navigator.clipboard) {
        await navigator.clipboard.writeText(data.prompt);
        $("out").textContent = "已复制上下文 prompt：\n\n" + data.prompt;
        $("out").classList.add("visible");
      }
      return data;
    }

    function archiveAiChat() {
      const value = text() || "待归档 AI 对话";
      return api("archive-ai-chat", {
        title: value.slice(0, 48),
        source: "GUI",
        background: value,
        conclusions: "待提炼关键结论",
        outputs: "待补充产出路径",
        open_items: "待确认未完成事项"
      });
    }

    function openObsidian() {
      return api("open-obsidian");
    }

    function toggleOutput() {
      $("out").classList.toggle("visible");
      if ($("out").classList.contains("visible")) {
        $("out").scrollIntoView({behavior: "smooth", block: "nearest"});
      }
    }

    refreshStatus().catch((error) => renderOutput({ok: false, error: String(error)}));
  </script>
</body>
</html>
"""


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
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path.startswith("/assets/"):
            relative = unquote(parsed.path.removeprefix("/assets/"))
            target = (ASSET_ROOT / relative).resolve()
            asset_root = ASSET_ROOT.resolve()
            if not str(target).startswith(str(asset_root)) or not target.is_file():
                self._json({"ok": False, "error": "asset not found"}, 404)
                return
            content_type = "image/png" if target.suffix.lower() == ".png" else "application/octet-stream"
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
