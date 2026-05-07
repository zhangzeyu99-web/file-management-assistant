from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Obsidian AI 整理工作台</title>
  <style>
    :root {
      --paper: #efe6d4;
      --paper-2: #fbf7ed;
      --paper-3: #fffaf0;
      --ink: #17211d;
      --muted: #687267;
      --line: #d6c39d;
      --line-strong: #bfa77a;
      --moss: #0f6b56;
      --moss-dark: #0b3b31;
      --rust: #b14f33;
      --gold: #b9852f;
      --blue: #244f6c;
      --shadow: 0 22px 70px rgba(47, 38, 24, .14);
      --radius-xl: 30px;
      --radius-lg: 22px;
      --radius-md: 16px;
      --mono: "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
      --serif: "LXGW WenKai", "FangSong", "Songti SC", "Noto Serif SC", serif;
      --sans: "Microsoft YaHei", "Noto Sans SC", sans-serif;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: var(--serif);
      background:
        radial-gradient(circle at 14% 8%, rgba(255, 207, 120, .38), transparent 31rem),
        radial-gradient(circle at 90% 12%, rgba(15, 107, 86, .20), transparent 26rem),
        linear-gradient(135deg, #f5eddc 0%, #e7ddc8 48%, #efe6d4 100%);
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .36;
      background-image:
        linear-gradient(rgba(23, 33, 29, .035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(23, 33, 29, .025) 1px, transparent 1px);
      background-size: 44px 44px;
      mask-image: linear-gradient(to bottom, black, transparent 78%);
    }
    button, textarea, input { font: inherit; }
    button {
      border: 0;
      cursor: pointer;
      transition: transform .18s ease, box-shadow .18s ease, background .18s ease;
    }
    button:hover { transform: translateY(-1px); }
    button:disabled { cursor: wait; opacity: .58; transform: none; }
    .shell {
      width: min(1180px, calc(100vw - 36px));
      margin: 0 auto;
      padding: 22px 0 56px;
    }
    .top-lines {
      display: grid;
      gap: 10px;
      margin: 0 0 22px;
    }
    .line-pill {
      height: 29px;
      display: flex;
      align-items: center;
      padding: 0 12px;
      border: 1px solid rgba(191, 167, 122, .75);
      border-radius: 999px;
      color: var(--ink);
      background: rgba(251, 247, 237, .45);
      font-family: var(--mono);
      font-size: 12px;
      letter-spacing: .02em;
    }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) 330px;
      gap: 26px;
      align-items: end;
      margin-bottom: 28px;
    }
    h1 {
      margin: 0;
      font-size: clamp(46px, 7.2vw, 88px);
      line-height: .94;
      letter-spacing: -0.07em;
      font-weight: 700;
    }
    .lead {
      margin: 18px 0 0;
      max-width: 850px;
      color: #36413b;
      font-size: 16px;
      line-height: 1.9;
    }
    .hero-note {
      background: rgba(255, 250, 240, .74);
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      padding: 20px;
      box-shadow: var(--shadow);
    }
    .hero-note strong {
      display: block;
      margin-bottom: 10px;
      color: var(--moss-dark);
      font-size: 18px;
    }
    .hero-note p, .card p, .tiny {
      color: var(--muted);
      line-height: 1.75;
    }
    .section-label {
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 28px 0 12px;
      color: var(--moss);
      font-weight: 800;
      letter-spacing: .08em;
    }
    .section-label::after {
      content: "";
      flex: 1;
      height: 1px;
      background: linear-gradient(90deg, var(--line), transparent);
    }
    .grid {
      display: grid;
      gap: 14px;
    }
    .value-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .action-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .record-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .workspace-grid {
      grid-template-columns: minmax(0, 1.25fr) minmax(320px, .75fr);
      align-items: start;
    }
    .card {
      background: rgba(255, 250, 240, .78);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      padding: 18px;
      box-shadow: 0 14px 40px rgba(47, 38, 24, .09);
    }
    .value-card {
      min-height: 150px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .value-card strong {
      display: block;
      margin-bottom: 12px;
      color: var(--ink);
      font-size: 20px;
      letter-spacing: -.02em;
    }
    .action-card {
      display: grid;
      gap: 12px;
      min-height: 128px;
    }
    .action-card button {
      width: 100%;
      min-height: 48px;
      padding: 13px 16px;
      border-radius: var(--radius-md);
      background: var(--ink);
      color: var(--paper-3);
      text-align: left;
      font-weight: 800;
      box-shadow: inset 0 -1px rgba(255,255,255,.08);
    }
    .action-card button:hover { background: var(--moss-dark); }
    .action-card button.secondary { background: var(--moss); }
    .action-card button.rust { background: var(--rust); }
    .action-card button.gold { background: var(--gold); color: #17130d; }
    .action-card p {
      margin: 0;
      font-size: 13px;
    }
    .console {
      display: grid;
      gap: 14px;
    }
    .textarea-wrap label {
      display: block;
      margin-bottom: 8px;
      color: var(--moss-dark);
      font-weight: 800;
    }
    textarea, input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 15px;
      background: rgba(255, 254, 248, .86);
      color: var(--ink);
      outline: none;
      resize: vertical;
    }
    textarea:focus, input:focus {
      border-color: var(--moss);
      box-shadow: 0 0 0 4px rgba(15, 107, 86, .10);
    }
    .quick-row {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .quick-row button {
      min-height: 44px;
      border-radius: 999px;
      background: rgba(255, 250, 240, .78);
      border: 1px solid var(--line);
      color: var(--ink);
      font-weight: 800;
    }
    .quick-row button:hover {
      background: var(--paper-3);
      box-shadow: 0 10px 24px rgba(47, 38, 24, .10);
    }
    .status-card {
      display: grid;
      gap: 14px;
      position: sticky;
      top: 16px;
    }
    .status-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
    }
    .status-dot {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 10px;
      border-radius: 999px;
      color: var(--moss-dark);
      background: rgba(15, 107, 86, .10);
      font-size: 12px;
      font-family: var(--sans);
    }
    .status-dot::before {
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--moss);
    }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .metric {
      border: 1px solid rgba(214, 195, 157, .9);
      border-radius: 18px;
      padding: 12px;
      background: rgba(255,255,255,.34);
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-family: var(--sans);
    }
    .metric strong {
      display: block;
      margin-top: 3px;
      color: var(--moss);
      font-size: 25px;
      line-height: 1;
      font-family: var(--mono);
    }
    .safe-box {
      border-left: 5px solid var(--rust);
      border-radius: 16px;
      padding: 12px 14px;
      background: rgba(255,255,255,.38);
      color: #41362a;
      line-height: 1.75;
      font-size: 13px;
    }
    .path {
      word-break: break-all;
      color: var(--muted);
      font-family: var(--mono);
      font-size: 11px;
      line-height: 1.65;
    }
    .output {
      min-height: 260px;
      max-height: 520px;
      margin: 0;
      overflow: auto;
      white-space: pre-wrap;
      border-radius: 22px;
      padding: 18px;
      background: #121b17;
      color: #e9f2ea;
      font-family: var(--mono);
      font-size: 12px;
      line-height: 1.65;
    }
    .footer-note {
      margin: 18px 0 0;
      color: var(--muted);
      text-align: center;
      font-size: 12px;
      font-family: var(--sans);
    }
    @media (max-width: 1020px) {
      .hero, .workspace-grid { grid-template-columns: 1fr; }
      .status-card { position: static; }
      .value-grid, .record-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .action-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 640px) {
      .shell { width: min(100vw - 24px, 1180px); padding-top: 14px; }
      .value-grid, .record-grid, .quick-row, .metric-grid { grid-template-columns: 1fr; }
      .card { padding: 15px; }
      .hero-note { padding: 16px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="top-lines" aria-label="产品关键词">
      <div class="line-pill">Obsidian + AI</div>
      <div class="line-pill">本地优先 · 默认只读 · 可追溯</div>
      <div class="line-pill">文件 / 笔记 / AI 对话 / 可复用上下文</div>
    </div>

    <header class="hero">
      <div>
        <h1>Obsidian AI 整理工作台</h1>
        <p class="lead">把文件、笔记和 AI 对话整理进 Obsidian；需要继续问 AI 时，自动提取已整理上下文。默认不会删除、移动、重命名或重写你的源文件。</p>
      </div>
      <aside class="hero-note">
        <strong>先别整理一切，先完成今天该做的。</strong>
        <p>这个工作台的目标不是制造更多待办，而是把零散材料变成可归档、可复盘、可继续被 AI 调用的上下文资产。</p>
      </aside>
    </header>

    <section class="grid value-grid" aria-label="核心价值">
      <article class="card value-card"><strong>整理本地文件</strong><p>查看近期、大文件、重复文件和归档候选。先给建议，不直接搬动源文件。</p></article>
      <article class="card value-card"><strong>归档 AI 对话</strong><p>把已有 AI 对话整理成可追溯记录：来源、背景、结论、产出路径和未完成事项。</p></article>
      <article class="card value-card"><strong>提取 AI 上下文</strong><p>从已整理知识库提取相关笔记和报告，生成可复制给新 AI 对话的上下文 prompt。</p></article>
      <article class="card value-card"><strong>沉淀知识卡/今日行动</strong><p>把零散内容转成知识卡、今日行动和轻量复盘，减少 Obsidian 新手的结构负担。</p></article>
    </section>

    <div class="section-label">今日操作台</div>
    <section class="grid workspace-grid">
      <div class="card console">
        <div class="textarea-wrap">
          <label for="freeText">告诉助手你现在要处理什么</label>
          <textarea id="freeText" rows="6" placeholder="例如：把今天和 NotebookLM 课件相关的 Codex 对话归档，并提取下次继续优化课件时需要给 AI 的上下文。"></textarea>
        </div>
        <div class="quick-row">
          <button onclick="ask()">问怎么用</button>
          <button onclick="runAction('inbox-route')">判断放哪</button>
          <button onclick="copyAiContextPrompt()">复制上下文</button>
        </div>
        <pre class="output" id="out">等待操作。先输入一段内容，或直接点击下面的场景卡片。</pre>
      </div>

      <aside class="card status-card">
        <div class="status-head">
          <strong>本地状态</strong>
          <span class="status-dot" id="serverStatus">运行中</span>
        </div>
        <div class="metric-grid">
          <div class="metric"><span>扫描文件</span><strong id="totalFiles">-</strong></div>
          <div class="metric"><span>归档候选</span><strong id="archiveCount">-</strong></div>
          <div class="metric"><span>Obsidian 笔记</span><strong id="totalNotes">-</strong></div>
        </div>
        <div class="safe-box" id="safety">默认安全边界：只生成报告和新笔记，不删除、不移动、不重命名、不重写源文件。</div>
        <div class="path" id="latestFileReport">HTML 报告：加载中...</div>
        <div class="path" id="latestObsidianReport">Obsidian 体检：加载中...</div>
      </aside>
    </section>

    <div class="section-label">开始</div>
    <section class="grid action-grid">
      <article class="card action-card"><button onclick="runAction('today')">今天先干什么</button><p>只给 1-3 个今日重点，避免一上来处理全部归档候选。</p></article>
      <article class="card action-card"><button onclick="runAction('onboarding')">快速初始化</button><p>检查配置、教程、启动命令和本地工作目录。</p></article>
      <article class="card action-card"><button onclick="runAction('open-guidebook')">打开教程 PDF</button><p>查看 7 页入门教程，用 NotebookLM 或 Obsidian 继续学习。</p></article>
    </section>

    <div class="section-label">整理</div>
    <section class="grid action-grid">
      <article class="card action-card"><button onclick="runAction('file-radar')">查看文件雷达</button><p>查看近期、大文件、重复文件和归档候选，只报告不移动。</p></article>
      <article class="card action-card"><button onclick="runAction('inbox-route')">这段内容放哪</button><p>先分生活 / 学习 / 工作，再建议 inbox、daily、project、routine 或 archive。</p></article>
      <article class="card action-card"><button onclick="runAction('obsidian-health')">检查知识库</button><p>查看收件箱、断链、空壳笔记、低链接笔记和索引缺口。</p></article>
    </section>

    <div class="section-label">记录</div>
    <section class="grid record-grid">
      <article class="card action-card"><button onclick="quickActionNote()">记录一个任务</button><p>生成 Action 任务笔记：背景、目标、过程、结果、资料、下一步。</p></article>
      <article class="card action-card"><button onclick="quickCardNote()">沉淀知识卡</button><p>把可复用经验、规则、教程和资料变成 Card 知识卡。</p></article>
      <article class="card action-card"><button onclick="quickTimeReview()">复盘今天</button><p>生成轻量 Time 复盘，只处理完成、卡点和下一步。</p></article>
      <article class="card action-card"><button onclick="archiveAiChat()">归档 AI 对话</button><p>保存已有 AI 对话，不负责给新对话补上下文。</p></article>
    </section>

    <div class="section-label">AI 续用</div>
    <section class="grid action-grid">
      <article class="card action-card"><button class="secondary" onclick="runAction('build-ai-context')">提取 AI 上下文</button><p>从已整理知识库提取匹配来源、相关原因、压缩摘要和下一步请求。</p></article>
      <article class="card action-card"><button class="secondary" onclick="copyAiContextPrompt()">复制上下文 prompt</button><p>复制可直接给 Codex、NotebookLM 或其他 AI 使用的上下文。</p></article>
      <article class="card action-card"><button class="secondary" onclick="openObsidian()">打开 Obsidian</button><p>打开配置里的 vault，查看刚写入的笔记和报告。</p></article>
    </section>

    <div class="section-label">高级诊断</div>
    <section class="grid action-grid">
      <article class="card action-card"><button class="gold" onclick="runAction('knowledge-index')">调用知识索引</button><p>查看可复用笔记、知识卡和下一步调用建议。</p></article>
      <article class="card action-card"><button class="gold" onclick="runAction('deep-thinking')">深度思考引导</button><p>按 Action、Card、Time、X-AI 四种模式拆解当前问题。</p></article>
      <article class="card action-card"><button class="gold" onclick="runAction('scenario-demo')">跑场景演示</button><p>生成一份场景示例报告，用于验证闭环流程。</p></article>
      <article class="card action-card"><button class="rust" onclick="runAction('full-scan')">完整扫描</button><p>同时运行文件雷达和 Obsidian 体检。仍然默认只读。</p></article>
    </section>

    <p class="footer-note">本地优先 · 默认只读 · 所有写入都落到新笔记或明确报告路径</p>
  </main>

  <script>
    const $ = (id) => document.getElementById(id);
    let lastStatus = null;

    function text() {
      return $("freeText").value.trim();
    }

    function setBusy(value) {
      document.querySelectorAll("button").forEach((button) => { button.disabled = value; });
      $("serverStatus").textContent = value ? "执行中" : "运行中";
    }

    function renderResult(data) {
      $("out").textContent = JSON.stringify(data, null, 2);
    }

    async function refreshStatus() {
      const response = await fetch("/api/status");
      lastStatus = await response.json();
      const fileSummary = lastStatus.file_report?.summary || {};
      const obsidianSummary = lastStatus.obsidian_report?.summary || {};
      $("totalFiles").textContent = fileSummary.total_files ?? "-";
      $("archiveCount").textContent = fileSummary.counts?.archive_candidates ?? "-";
      $("totalNotes").textContent = obsidianSummary.total_notes ?? "-";
      $("safety").textContent = lastStatus.safety || "默认只读，不移动、不删除、不重命名源文件。";
      $("latestFileReport").textContent = "HTML 报告：" + (lastStatus.file_report?.html_report || "暂无");
      $("latestObsidianReport").textContent = "Obsidian 体检：" + (lastStatus.obsidian_report?.markdown_report || "暂无");
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
        renderResult(data);
        await refreshStatus();
        return data;
      } catch (error) {
        const data = {ok: false, error: String(error.stack || error)};
        renderResult(data);
        return data;
      } finally {
        setBusy(false);
      }
    }

    function runAction(action) {
      return api(action, {text: text(), body: text(), query: text(), request: text()});
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

    refreshStatus().catch((error) => renderResult({ok: false, error: String(error)}));
  </script>
</body>
</html>
"""


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
