from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


REQUIRED_DOCS = [
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "MAINTENANCE.md",
    "docs/GETTING_STARTED.md",
    "docs/CONFIGURATION.md",
    "docs/OBSIDIAN_WORKFLOW_TUTORIAL.md",
    "docs/GUI_INTERACTION_GUIDE.md",
    "docs/GUI_E2E_TESTING.md",
    "docs/USER_SCENARIOS.md",
    "docs/CLOSED_LOOP_USAGE.md",
    "docs/ARCHITECTURE.md",
    "docs/PROJECT_PRINCIPLES.md",
    "docs/SELF_EVOLUTION.md",
    "docs/guidebook/README.md",
]

PRINCIPLES = {
    "local-first": ["local-first", "local first"],
    "report-only safety": ["report-only", "report only", "does not delete", "不删除"],
    "private local configuration": ["config.local.json", "private local configuration"],
    "knowledge action assistant": ["知识行动助手", "knowledge action assistant"],
    "four-layer architecture": ["四层结构", "输入层", "判断层", "执行层", "输出层"],
    "act workflow": ["Action / Card / Time / X-AI", "ACT workflow"],
    "obsidian workflow": ["00 收件箱", "01 今日日志", "obsidian workflow"],
    "scenario-based workflow": ["scenario-based workflow", "scenario-first", "场景入口"],
    "closed loop": ["closed loop", "acceptance checks", "闭环验收"],
    "lightweight daily triage": ["lightweight daily triage", "今日轻量规则", "不要每天处理全部归档候选"],
    "life study work separation": ["life / study / work", "生活 / 学习 / 工作"],
    "thin gui": ["thin gui", "same underlying modules", "薄 GUI"],
    "validation harness": ["validation harness", "verify-harness"],
    "optional integrations": ["optional integrations", "notification hooks", "可选通知"],
    "ai chat archive": ["AI 对话归档", "archive-ai-chat"],
    "ai context retrieval": ["AI 上下文取用", "build-ai-context"],
}

FORBIDDEN_PUBLIC_PATHS = [
    "C:\\Users\\Administrator",
    "D:\\codex",
    "D:\\Obsidian-Work",
]

PRODUCTION_GLOBS = ["*.py", "*.ps1", "*.js"]
DESTRUCTIVE_CODE_PATTERNS = [
    "Remove-Item",
    ".unlink(",
    ".rmdir(",
    "shutil.rmtree",
    "shutil.move",
    ".rename(",
    "fs.unlink",
    "fs.rm(",
]
MOJIBAKE_PATTERNS = ["鏂", "绠", "鍏", "浠婃", "瀛︿", "宸ヤ", "閺", "鐎", "瀹搞"]
TEXT_SUFFIXES = {".md", ".py", ".json", ".ps1", ".js", ".yml", ".yaml", ".txt"}
MOJIBAKE_PATTERNS.extend(["\u9435", "\u6d60\u5a09", "\u701b\ufe3f", "\u5b80\u30e4", "\u923f", "\u9354\u256a", "\u93c0\u6735", "\u8930\u6385", "\u6d93\u20ac", "\ufffd"])
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", "tests"}
SKIP_FILES = {"config.local.json", "gui-server.err.log", "gui-server.out.log", "project_quality.py"}


def read_text(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8-sig")


def ok_check(name: str, evidence: Any) -> dict[str, Any]:
    return {"name": name, "ok": True, "evidence": evidence}


def fail_check(name: str, evidence: Any) -> dict[str, Any]:
    return {"name": name, "ok": False, "evidence": evidence}


def check_required_docs(root: Path) -> dict[str, Any]:
    missing = [item for item in REQUIRED_DOCS if not (root / item).exists()]
    if missing:
        return fail_check("required_docs", {"missing": missing})
    return ok_check("required_docs", REQUIRED_DOCS)


def check_public_config_is_portable(root: Path) -> dict[str, Any]:
    public_files = ["config.json", "config.example.json", "README.md", "docs/CONFIGURATION.md"]
    hits: list[str] = []
    for relative in public_files:
        text = read_text(root, relative)
        for forbidden in FORBIDDEN_PUBLIC_PATHS:
            if forbidden in text:
                hits.append(f"{relative}: {forbidden}")
    if hits:
        return fail_check("portable_public_config", hits)
    return ok_check("portable_public_config", public_files)


def check_local_config_is_private(root: Path) -> dict[str, Any]:
    ignore_text = read_text(root, ".gitignore")
    tracked = subprocess.run(
        ["git", "ls-files", "config.local.json"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    evidence = {
        "gitignore_contains_config_local": "config.local.json" in ignore_text,
        "tracked_config_local": tracked.stdout.strip(),
    }
    if evidence["gitignore_contains_config_local"] and not evidence["tracked_config_local"]:
        return ok_check("private_local_config", evidence)
    return fail_check("private_local_config", evidence)


def check_safety_policy(root: Path) -> dict[str, Any]:
    docs = ["README.md", "SECURITY.md", "docs/ARCHITECTURE.md"]
    required = ["delete", "move", "rename", "rewrite"]
    missing: list[str] = []
    for relative in docs:
        lowered = read_text(root, relative).lower()
        for term in required:
            if term not in lowered:
                missing.append(f"{relative}: {term}")
    if missing:
        return fail_check("report_only_safety", missing)
    return ok_check("report_only_safety", docs)


def check_project_principles(root: Path) -> dict[str, Any]:
    text = read_text(root, "docs/PROJECT_PRINCIPLES.md").lower()
    found: list[str] = []
    missing: list[str] = []
    for principle, needles in PRINCIPLES.items():
        if any(needle.lower() in text for needle in needles):
            found.append(principle)
        else:
            missing.append(principle)
    if missing:
        return fail_check("project_principles", {"found": found, "missing": missing})
    return ok_check("project_principles", found)


def check_optional_notification_positioning(root: Path) -> dict[str, Any]:
    readme = read_text(root, "README.md")
    discouraged = ["Feishu / Lark Delivery", "Feishu/Lark notification", "Feishu/Lark card"]
    hits = [item for item in discouraged if item in readme]
    evidence = "README uses generic optional notification wording"
    if hits:
        return fail_check("optional_notification_positioning", {"discouraged": hits, "evidence": readme})
    return ok_check("optional_notification_positioning", evidence)


def check_thin_gui_and_non_destructive_code(root: Path) -> dict[str, Any]:
    gui = read_text(root, "gui_server.py")
    required_imports = ["import file_assistant", "import obsidian_assistant", "import obsidian_manager"]
    missing_imports = [item for item in required_imports if item not in gui]
    destructive_hits: list[str] = []
    for pattern in PRODUCTION_GLOBS:
        for path in root.glob(pattern):
            if path.name == "project_quality.py":
                continue
            text = path.read_text(encoding="utf-8-sig")
            for needle in DESTRUCTIVE_CODE_PATTERNS:
                if needle in text:
                    destructive_hits.append(f"{path.name}: {needle}")
    if missing_imports or destructive_hits:
        return fail_check(
            "thin_gui_and_non_destructive_code",
            {"missing_imports": missing_imports, "destructive_hits": destructive_hits},
        )
    return ok_check("thin_gui_and_non_destructive_code", required_imports)


def check_validation_harness(root: Path) -> dict[str, Any]:
    harness = read_text(root, "scripts/verify-harness.ps1")
    required = [
        "test_assistant_evolution.py",
        "test_scenario_playbook.py",
        "test_project_quality.py",
        "secret_scan",
        "dry_run",
        "obsidian_manager_dry_run",
    ]
    missing = [item for item in required if item not in harness]
    if missing:
        return fail_check("validation_harness", {"missing": missing})
    return ok_check("validation_harness", required)


def check_guidebook_assets(root: Path) -> dict[str, Any]:
    pdf = root / "docs" / "guidebook" / "knowledge-action-assistant-tutorial.pdf"
    slides = sorted((root / "docs" / "guidebook" / "slides").glob("page-*.png"))
    evidence = {
        "pdf": str(pdf.relative_to(root)),
        "pdf_exists": pdf.exists(),
        "pdf_size": pdf.stat().st_size if pdf.exists() else 0,
        "slide_count": len(slides),
        "slides": [str(path.relative_to(root)) for path in slides],
    }
    if not pdf.exists() or evidence["pdf_size"] < 100_000 or len(slides) != 7:
        return fail_check("guidebook_assets", evidence)
    return ok_check("guidebook_assets", evidence)


def check_scenario_workflow(root: Path) -> dict[str, Any]:
    playbook = read_text(root, "scenario_playbook.py")
    gui = read_text(root, "gui_server.py")
    docs = read_text(root, "docs/USER_SCENARIOS.md") + "\n" + read_text(root, "docs/CLOSED_LOOP_USAGE.md")
    required = [
        "today",
        "file_radar",
        "inbox_route",
        "action_note",
        "card_capture",
        "time_review",
        "obsidian_health",
        "ai_chat_archive",
        "ai_context_retrieval",
        "archive-ai-chat",
        "build-ai-context",
        "assistant_qa",
        "build_act_templates",
        "今日轻量规则",
        "生活 / 学习 / 工作",
        "Action / Card / Time / X-AI",
        "scenario-demo",
        "acceptance_checks",
    ]
    haystack = "\n".join([playbook, gui, docs])
    missing = [item for item in required if item not in haystack]
    if missing:
        return fail_check("scenario_workflow", {"missing": missing})
    return ok_check("scenario_workflow", required)


def iter_public_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {".gitignore", "LICENSE"}:
            files.append(path)
    return files


def check_mojibake_scan(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    for path in iter_public_text_files(root):
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        for pattern in MOJIBAKE_PATTERNS:
            if pattern in text:
                hits.append(f"{path.relative_to(root)}: {pattern}")
                break
        if len(hits) >= 20:
            break
    if hits:
        return fail_check("mojibake_scan", hits)
    return ok_check("mojibake_scan", f"checked {len(iter_public_text_files(root))} text files")


def run_checks(root: Path) -> dict[str, Any]:
    checks = [
        check_required_docs(root),
        check_public_config_is_portable(root),
        check_local_config_is_private(root),
        check_safety_policy(root),
        check_project_principles(root),
        check_optional_notification_positioning(root),
        check_thin_gui_and_non_destructive_code(root),
        check_scenario_workflow(root),
        check_validation_harness(root),
        check_guidebook_assets(root),
        check_mojibake_scan(root),
    ]
    return {
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate open-source project quality gates")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    result = run_checks(Path(args.repo))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
