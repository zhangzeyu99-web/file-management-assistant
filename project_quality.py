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
    "docs/ARCHITECTURE.md",
    "docs/PROJECT_PRINCIPLES.md",
]

PRINCIPLES = {
    "local-first": ["local-first", "local first"],
    "report-only safety": ["report-only", "report only", "does not delete"],
    "private local configuration": ["config.local.json", "private local configuration"],
    "obsidian workflow": ["00 收件箱", "01 今日日志", "obsidian workflow"],
    "thin gui": ["thin gui", "same underlying modules"],
    "validation harness": ["validation harness", "verify-harness"],
    "optional integrations": ["optional integrations", "notification hooks"],
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
        "test_project_quality.py",
        "secret_scan",
        "dry_run",
        "obsidian_manager_dry_run",
    ]
    missing = [item for item in required if item not in harness]
    if missing:
        return fail_check("validation_harness", {"missing": missing})
    return ok_check("validation_harness", required)


def run_checks(root: Path) -> dict[str, Any]:
    checks = [
        check_required_docs(root),
        check_public_config_is_portable(root),
        check_local_config_is_private(root),
        check_safety_policy(root),
        check_project_principles(root),
        check_optional_notification_positioning(root),
        check_thin_gui_and_non_destructive_code(root),
        check_validation_harness(root),
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
