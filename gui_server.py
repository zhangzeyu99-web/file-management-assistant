from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import file_assistant
import obsidian_assistant
import obsidian_manager
import scenario_playbook


DEFAULT_CONFIG = ROOT / "config.json"


def load_config(config_path: Path) -> dict[str, Any]:
    return file_assistant.load_config(config_path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def runtime_root(config: dict[str, Any]) -> Path:
    return Path(config.get("runtime_root") or ROOT / ".runtime")


def obsidian_vault(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_vault") or Path.home() / "Documents" / "Obsidian")


def codex_executable(config: dict[str, Any]) -> Path:
    raw = config.get("codex_executable") or os.environ.get("CODEX_DESKTOP_EXE")
    if raw:
        return Path(str(raw))
    return Path.home() / "AppData" / "Local" / "Programs" / "OpenAI" / "CodexDesktop" / "Codex.exe"


def latest_file_report(config: dict[str, Any]) -> dict[str, Any] | None:
    runs = runtime_root(config) / "runs"
    candidates = sorted(runs.glob("*/*/summary.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for summary_path in candidates:
        report = summary_path.with_name("report.html")
        markdown = summary_path.with_name("report.md")
        if report.exists():
            return {
                "summary_json": str(summary_path),
                "html_report": str(report),
                "markdown_report": str(markdown) if markdown.exists() else "",
                "summary": read_json(summary_path),
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
        markdown = summary_path.with_name("obsidian-management-report.md")
        if markdown.exists():
            return {
                "summary_json": str(summary_path),
                "markdown_report": str(markdown),
                "summary": read_json(summary_path),
            }
    return None


def build_status(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)
    return {
        "ok": True,
        "repo": str(ROOT),
        "config": str(config_path),
        "runtime_root": str(runtime_root(config)),
        "obsidian_vault": str(obsidian_vault(config)),
        "file_report": latest_file_report(config),
        "obsidian_report": latest_obsidian_report(config),
        "scenarios": scenario_playbook.build_scenario_catalog(config),
        "safety": "只生成报告和写入明确指定的 Obsidian 笔记；不删除、不移动、不重命名源文件。",
    }


def text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def build_codex_prompt(request: str, config: dict[str, Any] | None = None) -> str:
    config = config or load_config(DEFAULT_CONFIG)
    request = request.strip() or "帮我继续处理 Obsidian / 文件管理助手相关任务。"
    vault = obsidian_vault(config)
    runtime = runtime_root(config) / "runs"
    return "\n".join(
        [
            "请回到当前 Codex 会话，按我的真实本机环境处理这个任务：",
            "",
            request,
            "",
            "上下文：",
            f"- Obsidian vault：{vault}",
            f"- 文件管理助手仓库：{ROOT}",
            f"- 运行产物：{runtime}",
            "- 安全边界：不要删除、移动、重命名源文件；涉及外发、删除、权限变更先确认。",
            "",
            "请先查真实文件和最新报告，再执行或给结论。",
        ]
    )


def allowed_open_path(path: Path, config: dict[str, Any]) -> bool:
    resolved = path.resolve()
    roots = [
        ROOT.resolve(),
        runtime_root(config).resolve(),
        obsidian_vault(config).resolve(),
    ]
    roots.extend(Path(item).resolve() for item in config.get("allowed_open_roots", []))
    return any(resolved == root or root in resolved.parents for root in roots)


def open_local_path(path_text: str, config: dict[str, Any]) -> dict[str, Any]:
    path = Path(path_text)
    if not path.exists():
        return {"ok": False, "error": f"path not found: {path_text}"}
    if not allowed_open_path(path, config):
        return {"ok": False, "error": "path outside allowed assistant roots"}
    webbrowser.open(path.as_uri() if path.is_file() else str(path))
    return {"ok": True, "opened": str(path)}


def open_obsidian(config: dict[str, Any], file_path: str | None = None) -> dict[str, Any]:
    vault = obsidian_vault(config)
    if file_path:
        target = file_path.replace("\\", "/")
        uri = f"obsidian://open?vault={vault.name}&file={target}"
    else:
        uri = f"obsidian://open?vault={vault.name}"
    webbrowser.open(uri)
    return {"ok": True, "opened": uri}


def open_codex(config: dict[str, Any]) -> dict[str, Any]:
    executable = codex_executable(config)
    if executable.exists():
        subprocess.Popen([str(executable)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "opened": str(executable)}
    return {"ok": False, "error": f"Codex executable not found: {executable}"}


def run_gui_action(action: str, payload: dict[str, Any], config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)

    if action == "status":
        return build_status(config_path)
    if action == "file-scan":
        result = file_assistant.run(config_path, "Test")
        return {"ok": True, "action": action, **result}
    if action == "obsidian-audit":
        result = obsidian_manager.run(config_path, "Test")
        return {"ok": True, "action": action, **result}
    if action == "full-scan":
        file_result = file_assistant.run(config_path, "Test")
        obsidian_result = obsidian_manager.run(config_path, "Test")
        return {"ok": True, "action": action, "file": file_result, "obsidian": obsidian_result}
    if action == "guide":
        return obsidian_assistant.command_guide(config)
    if action == "scenarios":
        return {"ok": True, "action": action, "scenarios": scenario_playbook.build_scenario_catalog(config)}
    if action == "scenario-demo":
        return {"action": action, **scenario_playbook.run_demo(config_path)}
    if action == "ask":
        question = str(payload.get("question") or payload.get("text") or "").strip()
        return obsidian_assistant.command_ask(config, question, bool(payload.get("write_note")))
    if action == "capture":
        title = str(payload.get("title") or "GUI 快速记录").strip()
        body = str(payload.get("body") or payload.get("text") or "").strip()
        tags = text_list(payload.get("tags") or ["gui", "inbox"])
        return obsidian_assistant.command_capture(config, title, body, tags)
    if action == "daily":
        return obsidian_assistant.command_daily(
            config,
            done=text_list(payload.get("done") or payload.get("text")),
            next_items=text_list(payload.get("next") or payload.get("next_items")),
            blockers=text_list(payload.get("blocker") or payload.get("blockers")),
        )
    if action == "codex-prompt":
        return {"ok": True, "prompt": build_codex_prompt(str(payload.get("text") or ""), config)}
    if action == "open-path":
        return open_local_path(str(payload.get("path") or ""), config)
    if action == "open-obsidian":
        return open_obsidian(config, str(payload.get("file") or "") or None)
    if action == "open-codex":
        return open_codex(config)

    return {"ok": False, "error": f"unsupported action: {action}"}


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Codex 文件管理小助手</title>
  <style>
    :root {
      --ink: #18201c;
      --muted: #66736c;
      --paper: #f3ead8;
      --panel: rgba(255, 252, 244, .92);
      --line: #dbc9a5;
      --green: #0f6b56;
      --blue: #214d6b;
      --gold: #b4822c;
      --red: #b14f3a;
      --shadow: 0 22px 70px rgba(38, 33, 24, .16);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: "Microsoft YaHei", "Noto Sans SC", sans-serif;
      background:
        radial-gradient(circle at 15% 12%, rgba(255, 215, 130, .45), transparent 28rem),
        radial-gradient(circle at 88% 8%, rgba(85, 138, 118, .28), transparent 24rem),
        linear-gradient(135deg, #f8f0df 0%, #e9f0e7 100%);
    }
    header {
      padding: 34px clamp(20px, 4vw, 56px) 18px;
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-start;
    }
    h1 { margin: 0; font-size: clamp(30px, 4vw, 54px); letter-spacing: -1.5px; }
    .sub { margin-top: 10px; color: var(--muted); font-size: 15px; line-height: 1.7; max-width: 760px; }
    .badge {
      border: 1px solid var(--line);
      background: rgba(255,255,255,.65);
      border-radius: 999px;
      padding: 10px 14px;
      font-size: 13px;
      white-space: nowrap;
    }
    main { padding: 0 clamp(20px, 4vw, 56px) 44px; }
    .grid {
      display: grid;
      grid-template-columns: 1.08fr .92fr;
      gap: 22px;
      align-items: start;
    }
    .panel {
      background: var(--panel);
      border: 1px solid rgba(178, 150, 102, .42);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 22px;
      backdrop-filter: blur(10px);
    }
    .panel h2 { margin: 0 0 14px; font-size: 22px; }
    .cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .metric {
      border: 1px solid rgba(178, 150, 102, .42);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255,255,255,.55);
    }
    .metric strong { display:block; font-size: 30px; color: var(--green); margin-top: 6px; }
    .actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    button, a.button {
      border: 0;
      border-radius: 16px;
      padding: 13px 15px;
      background: var(--ink);
      color: #fff;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      justify-content: center;
      align-items: center;
      min-height: 46px;
    }
    button.secondary { background: var(--green); }
    button.ghost, a.button.ghost { background: rgba(255,255,255,.7); color: var(--ink); border: 1px solid var(--line); }
    button.warn { background: var(--gold); }
    button.danger { background: var(--red); }
    button:disabled { opacity: .55; cursor: wait; }
    textarea, input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,.75);
      padding: 13px 14px;
      font: inherit;
      color: var(--ink);
    }
    textarea { min-height: 118px; resize: vertical; }
    label { display:block; font-size: 13px; color: var(--muted); margin: 12px 0 6px; }
    .result {
      white-space: pre-wrap;
      font-family: "Cascadia Mono", Consolas, monospace;
      font-size: 12px;
      background: #17211d;
      color: #e8f2e8;
      border-radius: 18px;
      padding: 14px;
      max-height: 320px;
      overflow: auto;
    }
    .path { font-family: "Cascadia Mono", Consolas, monospace; font-size: 12px; color: var(--muted); word-break: break-all; }
    .stack { display: grid; gap: 12px; }
    .row { display: flex; gap: 10px; flex-wrap: wrap; }
    .row > * { flex: 1; min-width: 180px; }
    .safety {
      border-left: 5px solid var(--red);
      background: rgba(255,255,255,.62);
      border-radius: 16px;
      padding: 12px 14px;
      line-height: 1.65;
      color: #3a3026;
    }
    .subtle {
      color: var(--muted);
      line-height: 1.7;
      font-size: 14px;
    }
    .scenario-list {
      display: grid;
      gap: 12px;
    }
    .scenario-card {
      border: 1px solid rgba(219, 201, 165, .9);
      background: rgba(255, 255, 255, .58);
      border-radius: 18px;
      padding: 14px;
      line-height: 1.6;
    }
    .scenario-card strong {
      display: block;
      color: var(--blue);
      margin-bottom: 4px;
    }
    .scenario-card code {
      color: var(--green);
      font-family: "Cascadia Mono", Consolas, monospace;
      font-size: 12px;
    }
    @media (max-width: 980px) {
      .grid, .cards, .actions { grid-template-columns: 1fr; }
      header { flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Codex 文件管理小助手</h1>
      <div class="sub">本地 GUI 控制台。调用现有文件扫描、Obsidian 审计、收件箱写入、今日日志和问答能力。默认只生成报告，不删除、不移动、不改名源文件。</div>
    </div>
    <div class="badge" id="serverStatus">本地服务运行中</div>
  </header>
  <main>
    <div class="grid">
      <section class="panel stack">
        <h2>当前状态</h2>
        <div class="cards">
          <div class="metric">扫描文件<strong id="totalFiles">-</strong></div>
          <div class="metric">建议归档<strong id="archiveCount">-</strong></div>
          <div class="metric">Obsidian 笔记<strong id="totalNotes">-</strong></div>
        </div>
        <div class="safety" id="safety">加载中...</div>
        <div class="actions">
          <button onclick="runAction('full-scan')" class="secondary">跑完整检查</button>
          <button onclick="runAction('file-scan')">只跑文件扫描</button>
          <button onclick="runAction('obsidian-audit')">只跑 Obsidian 审计</button>
          <button onclick="runAction('guide')" class="warn">生成 Obsidian 指南</button>
          <button onclick="loadScenarios()" class="secondary">查看使用场景</button>
          <button onclick="runScenarioDemo()" class="warn">跑使用场景示例</button>
          <button onclick="openLatestReport()" class="ghost">打开最新 HTML 报告</button>
          <button onclick="openObsidian()" class="ghost">打开 Obsidian</button>
        </div>
        <div>
          <div class="path" id="latestFileReport"></div>
          <div class="path" id="latestObsidianReport"></div>
        </div>
      </section>

      <section class="panel stack">
        <h2>自然语言入口</h2>
        <label>你想让助手处理什么</label>
        <textarea id="nlText" placeholder="例如：帮我把这个想法放到收件箱；今天完成了 NotebookLM 课件，下一步整理收件箱；这个内容应该放哪里？"></textarea>
        <div class="row">
          <button onclick="askAssistant()" class="secondary">问小助手</button>
          <button onclick="captureText()">记到收件箱</button>
        </div>
        <div class="row">
          <button onclick="dailyText()" class="warn">追加今日日志</button>
          <button onclick="copyCodexPrompt()" class="ghost">复制给 Codex 会话</button>
        </div>
        <button onclick="openCodex()" class="danger">打开 Codex 桌面</button>
      </section>

      <section class="panel stack">
        <h2>明确写入</h2>
        <div class="row">
          <div>
            <label>收件箱标题</label>
            <input id="captureTitle" value="GUI 快速记录" />
          </div>
          <div>
            <label>标签，逗号分隔</label>
            <input id="captureTags" value="gui,inbox" />
          </div>
        </div>
        <label>收件箱内容</label>
        <textarea id="captureBody"></textarea>
        <button onclick="captureForm()">写入收件箱</button>
      </section>

      <section class="panel stack">
        <h2>场景化入口</h2>
        <div class="subtle">成熟用法不是先记命令，而是先选场景：今天先看什么、收件箱整理、知识库健康检查、交给 Codex 继续做。每个场景都带安全边界、下一步和验收标准。</div>
        <div class="scenario-list" id="scenarioCards"></div>
      </section>

      <section class="panel stack">
        <h2>输出</h2>
        <div class="result" id="result">等待操作。</div>
      </section>
    </div>
  </main>

  <script>
    let lastStatus = null;
    const $ = (id) => document.getElementById(id);

    async function post(action, payload = {}) {
      setBusy(true);
      try {
        const response = await fetch('/api/action', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({action, ...payload})
        });
        const data = await response.json();
        $('result').textContent = JSON.stringify(data, null, 2);
        await refreshStatus();
        return data;
      } catch (err) {
        $('result').textContent = String(err.stack || err);
        return {ok: false, error: String(err)};
      } finally {
        setBusy(false);
      }
    }

    function setBusy(value) {
      document.querySelectorAll('button').forEach(btn => btn.disabled = value);
      $('serverStatus').textContent = value ? '正在执行...' : '本地服务运行中';
    }

    async function refreshStatus() {
      const response = await fetch('/api/status');
      lastStatus = await response.json();
      const fileSummary = lastStatus.file_report?.summary || {};
      const obsSummary = lastStatus.obsidian_report?.summary || {};
      $('totalFiles').textContent = fileSummary.total_files ?? '-';
      $('archiveCount').textContent = fileSummary.counts?.archive_candidates ?? '-';
      $('totalNotes').textContent = obsSummary.total_notes ?? '-';
      $('safety').textContent = lastStatus.safety;
      $('latestFileReport').textContent = 'HTML 报告：' + (lastStatus.file_report?.html_report || '暂无');
      $('latestObsidianReport').textContent = 'Obsidian 审计：' + (lastStatus.obsidian_report?.markdown_report || '暂无');
      renderScenarios(lastStatus.scenarios || []);
    }

    async function runAction(action) { await post(action); }

    function renderScenarios(scenarios) {
      const box = $('scenarioCards');
      if (!box) return;
      if (!scenarios.length) {
        box.innerHTML = '<div class="scenario-card">暂无场景数据。点击“查看使用场景”刷新。</div>';
        return;
      }
      box.innerHTML = scenarios.map(item => `
        <div class="scenario-card">
          <strong>${item.title} <code>${item.id}</code></strong>
          <div>${item.user_need}</div>
          <div class="subtle">下一步：${item.next_action}</div>
        </div>
      `).join('');
    }

    async function loadScenarios() {
      const data = await post('scenarios');
      if (data.ok) renderScenarios(data.scenarios || []);
    }

    async function runScenarioDemo() {
      const data = await post('scenario-demo');
      if (data.ok) {
        $('result').textContent =
          '使用场景示例已跑完：\n' +
          'Markdown：' + data.markdown_report + '\n' +
          'JSON：' + data.json_report + '\n' +
          'Obsidian：' + data.obsidian_note + '\n\n' +
          JSON.stringify(data.scenarios.map(item => ({id: item.id, title: item.title, next: item.next_action})), null, 2);
      }
    }

    async function openLatestReport() {
      const path = lastStatus?.file_report?.html_report;
      if (!path) return $('result').textContent = '暂无 HTML 报告。';
      await post('open-path', {path});
    }

    async function openObsidian() { await post('open-obsidian'); }
    async function openCodex() { await post('open-codex'); }

    async function askAssistant() {
      const text = $('nlText').value.trim();
      await post('ask', {question: text || '我现在应该怎么用 Obsidian 助手？'});
    }

    async function captureText() {
      const text = $('nlText').value.trim();
      await post('capture', {title: text.slice(0, 36) || 'GUI 快速记录', body: text, tags: ['gui', 'inbox']});
    }

    async function dailyText() {
      const text = $('nlText').value.trim();
      await post('daily', {done: text || '从 GUI 追加今日日志', next: '继续整理 Obsidian 助手工作流', blocker: '暂无'});
    }

    async function captureForm() {
      const tags = $('captureTags').value.split(',').map(s => s.trim()).filter(Boolean);
      await post('capture', {title: $('captureTitle').value, body: $('captureBody').value, tags});
    }

    async function copyCodexPrompt() {
      const text = $('nlText').value.trim();
      const data = await post('codex-prompt', {text});
      if (data.ok && data.prompt) {
        await navigator.clipboard.writeText(data.prompt);
        $('result').textContent = '已复制给 Codex 的指令：\n\n' + data.prompt;
      }
    }

    refreshStatus();
  </script>
</body>
</html>
"""


class AssistantGuiHandler(BaseHTTPRequestHandler):
    config_path = DEFAULT_CONFIG

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("[assistant-gui] " + format % args + "\n")

    def send_json(self, value: dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_html(self, value: str) -> None:
        payload = value.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_html(HTML)
            return
        if parsed.path == "/api/status":
            self.send_json(build_status(self.config_path))
            return
        if parsed.path == "/api/open":
            query = parse_qs(parsed.query)
            result = run_gui_action("open-path", {"path": query.get("path", [""])[0]}, self.config_path)
            self.send_json(result, 200 if result.get("ok") else 400)
            return
        self.send_json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/action":
            self.send_json({"ok": False, "error": "not found"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            action = str(payload.pop("action", ""))
            result = run_gui_action(action, payload, self.config_path)
            self.send_json(result, 200 if result.get("ok") else 400)
        except Exception as exc:  # pragma: no cover - defensive handler boundary
            self.send_json({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}, 500)


def run_server(host: str, port: int, config_path: Path) -> None:
    AssistantGuiHandler.config_path = config_path
    server = ThreadingHTTPServer((host, port), AssistantGuiHandler)
    url = f"http://{host}:{port}/"
    print(json.dumps({"ok": True, "url": url, "config": str(config_path)}, ensure_ascii=False))
    webbrowser.open(url)
    server.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local GUI for the file management assistant")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_server(args.host, args.port, Path(args.config))


if __name__ == "__main__":
    main()
