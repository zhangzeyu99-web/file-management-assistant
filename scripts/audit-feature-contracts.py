from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import knowledge_assistant


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def make_config(base: Path) -> tuple[Path, dict[str, Any]]:
    runtime = base / "runtime"
    vault = base / "vault"
    fixture = base / "fixture"
    knowledge_root = vault / "routine" / "knowledge-assistant"
    for path in [runtime, fixture, knowledge_root, vault / "projects"]:
        path.mkdir(parents=True, exist_ok=True)
    config = {
        "runtime_root": str(runtime),
        "obsidian_vault": str(vault),
        "obsidian_run_dir": str(knowledge_root),
        "knowledge_root": str(knowledge_root),
        "allowed_open_roots": [str(runtime), str(vault), str(fixture)],
        "obsidian_folders": {
            "inbox": "inbox",
            "daily": "daily",
            "projects": "projects",
            "routine": "routine",
            "archive": "archive",
            "codex_project": "codex",
        },
        "watch_roots": [
            {
                "name": "fixture",
                "path": str(fixture),
                "max_depth": 2,
                "max_files": 100,
            }
        ],
    }
    config_path = base / "config.json"
    write_json(config_path, config)
    return config_path, config


def artifact_paths_exist(result: dict[str, Any], artifact_type: str | None = None) -> bool:
    artifacts = result.get("artifacts") or []
    if artifact_type:
        artifacts = [item for item in artifacts if item.get("type") == artifact_type]
    return bool(artifacts) and all(Path(item["path"]).exists() for item in artifacts if item.get("path"))


def record(name: str, result: dict[str, Any], passed: bool, evidence: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "ok": result.get("ok"),
        "action": result.get("action"),
        "summary": result.get("summary") or result.get("error") or result.get("next_request") or "",
        "sources": len(result.get("sources") or []),
        "artifacts": len(result.get("artifacts") or []),
        "evidence": evidence,
    }


def run_audit() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        config_path, config = make_config(base)
        fixture = base / "fixture"
        source_dir = fixture / "source-dir"
        source_dir.mkdir()
        (source_dir / "alpha-note.md").write_text("# Audit Alpha\n\nReusable alpha context.", encoding="utf-8")
        (source_dir / "alpha-data.txt").write_text("alpha data for directory scan", encoding="utf-8")
        cases: list[dict[str, Any]] = []

        result = knowledge_assistant.run_action("organize", {}, config_path)
        cases.append(record("organize_empty_refused", result, not result["ok"] and not result["artifacts"], "no placeholder organize note"))

        result = knowledge_assistant.run_action(
            "organize",
            {"text": "audit-alpha onboarding note for review and context extraction", "source": "contract-audit"},
            config_path,
        )
        cases.append(record("organize_text_writes_note", result, result["ok"] and artifact_paths_exist(result, "obsidian-note"), "writes a real Obsidian note"))

        result = knowledge_assistant.run_action("organize", {"local_paths": str(source_dir)}, config_path)
        scan_count = result.get("debug", {}).get("scan", {}).get("total_files", 0)
        cases.append(record("organize_directory_scans_files", result, result["ok"] and scan_count >= 2 and artifact_paths_exist(result, "markdown"), f"scanned_files={scan_count}"))

        result = knowledge_assistant.run_action("review", {"query": "audit-alpha"}, config_path)
        cases.append(record("review_match_returns_sources", result, result["ok"] and bool(result["sources"]), "matched the organized note"))

        result = knowledge_assistant.run_action("review", {"query": "zzzxxyyqwerty"}, config_path)
        cases.append(record("review_no_match_refused", result, not result["ok"] and not result["sources"], "no unrelated fallback"))

        result = knowledge_assistant.run_action("extract", {"query": "audit-alpha", "request": "Build a concise AI context pack."}, config_path)
        has_prompt = any(item.get("type") == "prompt" and item.get("content") for item in result.get("artifacts", []))
        cases.append(record("extract_match_generates_prompt", result, result["ok"] and has_prompt and bool(result["sources"]), "prompt includes matched sources"))

        result = knowledge_assistant.run_action("extract", {"query": "zzzxxyyqwerty"}, config_path)
        has_prompt = any(item.get("type") == "prompt" for item in result.get("artifacts", []))
        cases.append(record("extract_no_match_refused", result, not result["ok"] and not has_prompt, "no fake prompt"))

        for deprecated_action in ["remind", "legacy-index"]:
            result = knowledge_assistant.run_action(deprecated_action, {}, config_path)
            cases.append(record(f"{deprecated_action}_deprecated", result, not result["ok"] and result.get("status") == "deprecated" and not result["artifacts"], "non-core action is not executed"))

    passed = [case for case in cases if case["passed"]]
    failed = [case for case in cases if not case["passed"]]
    return {
        "ok": not failed,
        "generated_at": dt.datetime.now().astimezone().isoformat(),
        "summary": {"total": len(cases), "passed": len(passed), "failed": len(failed)},
        "cases": cases,
    }


def render_markdown(report: dict[str, Any]) -> str:
    rows = ["| Feature contract | Pass | Evidence |", "| --- | --- | --- |"]
    for case in report["cases"]:
        rows.append(f"| {case['name']} | {'yes' if case['passed'] else 'no'} | {case['evidence']} |")
    return "\n".join(
        [
            "# Feature Contract Audit",
            "",
            f"Generated: {report['generated_at']}",
            f"Result: {'PASS' if report['ok'] else 'FAIL'}",
            f"Cases: {report['summary']['passed']}/{report['summary']['total']} passed",
            "",
            *rows,
            "",
            "Safety: the audit uses a temporary vault and does not touch user source files.",
            "",
        ]
    )


def main() -> int:
    report = run_audit()
    run_dir = ROOT / "output" / "product-audit" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = write_json(run_dir / "feature-contracts.json", report)
    md_path = run_dir / "feature-contracts.md"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "json": str(json_path), "markdown": str(md_path), "summary": report["summary"]}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
