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
  <title>知识行动助手</title>
  <style>
    :root {
      --bg: #f4efe4;
      --ink: #1f2522;
      --muted: #697168;
      --card: #fffaf0;
      --line: #d9cbb0;
      --accent: #b44b2a;
      --accent-2: #245f57;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: "LXGW WenKai", "FangSong", "Songti SC", serif;
      background:
        radial-gradient(circle at top left, rgba(180, 75, 42, .22), transparent 34rem),
        linear-gradient(135deg, #f4efe4 0%, #e7dcc9 100%);
    }
    main { width: min(1160px, calc(100vw - 32px)); margin: 0 auto; padding: 32px 0 56px; }
    header { display: grid; gap: 12px; margin-bottom: 24px; }
    h1 { margin: 0; font-size: clamp(36px, 7vw, 76px); line-height: .92; letter-spacing: -0.05em; }
    p { color: var(--muted); line-height: 1.7; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }
    .card {
      background: rgba(255, 250, 240, .88);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 18px;
      box-shadow: 0 16px 44px rgba(75, 52, 27, .10);
    }
    button {
      width: 100%;
      border: 0;
      border-radius: 16px;
      padding: 14px 16px;
      background: var(--ink);
      color: #fffaf0;
      cursor: pointer;
      font: inherit;
      text-align: left;
    }
    button:hover { background: var(--accent); }
    .secondary { background: var(--accent-2); }
    textarea, input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      background: #fffef8;
      color: var(--ink);
      font: inherit;
      margin: 8px 0;
    }
    pre {
      white-space: pre-wrap;
      overflow: auto;
      background: #1f2522;
      color: #fffaf0;
      border-radius: 18px;
      padding: 16px;
      min-height: 220px;
    }
    .pill { display: inline-block; padding: 6px 10px; border: 1px solid var(--line); border-radius: 999px; margin-right: 8px; }
    .group-title { margin: 22px 0 10px; font-size: 18px; color: var(--accent-2); }
    .value-card strong { display: block; margin-bottom: 6px; font-size: 20px; color: var(--ink); }
  </style>
</head>
<body>
  <main>
    <header>
      <span class="pill">Obsidian + AI</span>
      <span class="pill">本地优先</span>
      <span class="pill">文件 / 笔记 / AI 对话</span>
      <h1>Obsidian AI 整理工作台</h1>
      <p>把文件、笔记和 AI 对话整理进 Obsidian；需要继续问 AI 时，自动提取已整理上下文。默认不会删除、移动、重命名或重写你的源文件。</p>
    </header>

    <section class="grid">
      <div class="card value-card"><strong>整理本地文件</strong><p>用文件雷达看近期、大文件、重复文件和归档候选，先给建议，不直接搬动源文件。</p></div>
      <div class="card value-card"><strong>归档 AI 对话</strong><p>把已有 AI 对话整理成可追溯记录：来源、背景、结论、产出路径和未完成事项。</p></div>
      <div class="card value-card"><strong>提取 AI 上下文</strong><p>从已整理知识库中提取相关笔记和报告，生成可复制给新 AI 对话的上下文 prompt。</p></div>
      <div class="card value-card"><strong>沉淀知识卡/今日行动</strong><p>把零散内容转成知识卡、今日行动和轻量复盘，减少 Obsidian 新手的结构负担。</p></div>
    </section>

    <h2 class="group-title">开始</h2>
    <section class="grid">
      <div class="card"><button onclick="runAction('today')">今天先干什么</button><p>只给 1-3 个今日重点。</p></div>
      <div class="card"><button onclick="runAction('onboarding')">快速初始化</button><p>检查配置、教程、启动命令。</p></div>
      <div class="card"><button onclick="runAction('open-guidebook')">打开教程 PDF</button><p>查看 7 页使用教程。</p></div>
    </section>

    <h2 class="group-title">整理</h2>
    <section class="grid">
      <div class="card"><button onclick="runAction('file-radar')">查看文件雷达</button><p>查看近期、大文件、重复文件。</p></div>
      <div class="card"><button onclick="runAction('inbox-route')">这段内容放哪</button><p>先分生活/学习/工作，再建议位置。</p></div>
      <div class="card"><button onclick="runAction('obsidian-health')">检查知识库</button><p>查看收件箱、断链、空壳笔记。</p></div>
    </section>

    <h2 class="group-title">记录</h2>
    <section class="grid">
      <div class="card"><button onclick="quickActionNote()">记录一个任务</button><p>生成 Action 任务笔记。</p></div>
      <div class="card"><button onclick="runAction('knowledge-index')">调用知识索引</button><p>查可复用笔记与下一步。</p></div>
      <div class="card"><button onclick="quickTimeReview()">复盘今天</button><p>生成轻量 Time 复盘。</p></div>
      <div class="card"><button onclick="archiveAiChat()">归档 AI 对话</button><p>整理已有 AI 对话，不负责给新对话补上下文。</p></div>
    </section>

    <h2 class="group-title">AI 续用</h2>
    <section class="grid">
      <div class="card"><button onclick="runAction('build-ai-context')">提取 AI 上下文</button><p>从已整理知识库提取来源和摘要。</p></div>
      <div class="card"><button onclick="copyAiContextPrompt()">复制上下文 prompt</button><p>复制可直接给 AI 使用的上下文。</p></div>
      <div class="card"><button onclick="openObsidian()">打开 Obsidian</button><p>打开配置里的 vault。</p></div>
    </section>

    <section class="card" style="margin-top:16px">
      <h2>自然语言输入</h2>
      <textarea id="freeText" rows="4" placeholder="例如：我今天怎么记录工作？"></textarea>
      <div class="grid">
        <button class="secondary" onclick="ask()">问答助手</button>
        <button class="secondary" onclick="quickCardNote()">沉淀知识卡</button>
        <button class="secondary" onclick="runAction('deep-thinking')">深度思考引导</button>
        <button class="secondary" onclick="runAction('scenario-demo')">跑场景演示</button>
        <button class="secondary" onclick="runAction('self-evolution')">生成进化报告</button>
        <button class="secondary" onclick="runAction('full-scan')">高级：完整扫描</button>
      </div>
    </section>

    <section class="card" style="margin-top:16px">
      <h2>输出</h2>
      <pre id="out">等待操作。</pre>
    </section>
  </main>
  <script>
    async function api(action, payload = {}) {
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({action, payload})
      });
      const data = await res.json();
      document.getElementById('out').textContent = JSON.stringify(data, null, 2);
      return data;
    }
    function text() { return document.getElementById('freeText').value.trim(); }
    function runAction(action) { return api(action, {text: text(), body: text()}); }
    function ask() { return api('ask', {question: text() || '我该怎么用？'}); }
    function quickActionNote() {
      const value = text() || '记录一个任务';
      return api('action-note', {title: value, domain: '工作', goal: value, source: 'GUI'});
    }
    function quickCardNote() {
      const value = text() || '知识卡';
      return api('card-note', {title: value, domain: '学习', source: 'GUI', conclusion: value});
    }
    function quickTimeReview() {
      const value = text() || '完成轻量复盘';
      return api('time-review', {title: '今日复盘', period: 'daily', done: value, next: '明确下一步'});
    }
    async function copyCodexPrompt() {
      const data = await api('codex-prompt', {request: text() || '继续优化知识行动助手'});
      if (data.prompt && navigator.clipboard) await navigator.clipboard.writeText(data.prompt);
    }
    async function copyAiContextPrompt() {
      const data = await api('build-ai-context', {query: text() || '当前任务', request: text() || '继续当前任务'});
      if (data.prompt && navigator.clipboard) await navigator.clipboard.writeText(data.prompt);
    }
    function archiveAiChat() {
      const value = text() || '待归档 AI 对话';
      return api('archive-ai-chat', {
        title: value,
        source: 'GUI',
        background: value,
        conclusions: '待提炼关键结论',
        outputs: '待补充产出路径',
        open_items: '待确认未完成事项'
      });
    }
    function openObsidian() { return api('open-obsidian'); }
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
