from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import knowledge_assistant


MISSING_QUERY_PREFIX = "__no_such_topic_"


def default_cases() -> list[dict[str, Any]]:
    missing_query = f"{MISSING_QUERY_PREFIX}{dt.datetime.now().strftime('%Y%m%d%H%M%S%f')}__"
    return [
        {
            "name": "opex_sop",
            "query": "运营sop",
            "expect_match": True,
            "must_match_terms": ["运营", "sop"],
            "must_not_match_top": ["OpenClaw", "简历"],
        },
        {
            "name": "github_repo",
            "query": "github仓库",
            "expect_match": True,
            "must_match_any": ["github", "仓库"],
        },
        {
            "name": "resume_thread",
            "query": "简历线程",
            "expect_match": True,
            "must_match_terms": ["简历", "线程"],
        },
        {
            "name": "obsidian_assistant",
            "query": "Obsidian助手",
            "expect_match": True,
            "must_match_terms": ["obsidian", "助手"],
            "must_not_match_top": ["真人式 GUI QA", "迭代记录"],
        },
        {
            "name": "missing_topic",
            "query": missing_query,
            "expect_match": False,
        },
    ]


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def terms_lower(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).lower() for item in values]


def text_contains_any(text: str, needles: list[str]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def first_source(result: dict[str, Any]) -> dict[str, Any]:
    sources = result.get("sources") or []
    return sources[0] if sources else {}


def source_fingerprint(source: dict[str, Any]) -> str:
    return "\n".join(
        str(source.get(key) or "")
        for key in ["title", "path", "summary", "direct_evidence", "evidence_excerpt"]
    )


def evaluate_review(case: dict[str, Any], review: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    expect_match = bool(case.get("expect_match"))
    has_sources = bool(review.get("sources"))
    if expect_match and (not review.get("ok") or not has_sources):
        reasons.append("expected a reliable review match")
    if not expect_match and (review.get("ok") or has_sources):
        reasons.append("expected no review match")

    source = first_source(review)
    matched_terms = terms_lower(source.get("matched_terms"))
    evidence = str(source.get("evidence_excerpt") or source.get("direct_evidence") or "")
    if expect_match:
        if not evidence:
            reasons.append("missing evidence_excerpt")
        for term in [str(item).lower() for item in case.get("must_match_terms", [])]:
            if term not in matched_terms:
                reasons.append(f"missing matched term: {term}")
        must_match_any = [str(item).lower() for item in case.get("must_match_any", [])]
        if must_match_any and not any(term in matched_terms for term in must_match_any):
            reasons.append(f"missing any matched term from: {', '.join(must_match_any)}")
        forbidden = [str(item) for item in case.get("must_not_match_top", [])]
        if forbidden and text_contains_any(source_fingerprint(source), forbidden):
            reasons.append(f"top source contains forbidden topic: {', '.join(forbidden)}")
    return not reasons, reasons


def evaluate_extract_preview(case: dict[str, Any], review: dict[str, Any], preview: dict[str, Any]) -> tuple[bool, list[str]]:
    if not case.get("expect_match"):
        if preview.get("ok") or preview.get("sources"):
            return False, ["extract preview should not find sources for a missing topic"]
        return True, []

    reasons: list[str] = []
    if not preview.get("ok") or not preview.get("sources"):
        reasons.append("expected extract preview candidates")
    if preview.get("artifacts"):
        reasons.append("preview mode must not write artifacts")
    review_path = str(first_source(review).get("path") or "")
    preview_paths = {str(item.get("path") or "") for item in preview.get("sources") or []}
    if review_path and review_path not in preview_paths:
        reasons.append("extract preview does not reuse the top review source")
    return not reasons, reasons


def compact_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": source.get("title") or "",
        "path": source.get("path") or "",
        "type": source.get("type") or "",
        "matched_terms": source.get("matched_terms") or [],
        "evidence_excerpt": source.get("evidence_excerpt") or source.get("direct_evidence") or "",
    }


def run_case(config_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    query = str(case["query"])
    review = knowledge_assistant.run_action("review", {"query": query}, config_path)
    preview = knowledge_assistant.run_action("extract", {"query": query, "request": f"为“{query}”生成 AI 上下文包", "mode": "preview"}, config_path)
    review_ok, review_reasons = evaluate_review(case, review)
    preview_ok, preview_reasons = evaluate_extract_preview(case, review, preview)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "name": case["name"],
        "query": query,
        "passed": review_ok and preview_ok,
        "elapsed_ms": elapsed_ms,
        "review": {
            "ok": bool(review.get("ok")),
            "status": review.get("status") or "",
            "answer": review.get("answer") or "",
            "summary": review.get("summary") or "",
            "sources": [compact_source(item) for item in (review.get("sources") or [])[:4]],
            "reasons": review_reasons,
        },
        "extract": {
            "ok": bool(preview.get("ok")),
            "status": preview.get("status") or "",
            "summary": preview.get("summary") or "",
            "sources": [compact_source(item) for item in (preview.get("sources") or [])[:4]],
            "artifact_count": len(preview.get("artifacts") or []),
            "reasons": preview_reasons,
        },
    }


def run_qa(config_path: Path) -> dict[str, Any]:
    knowledge_assistant.clear_review_index_cache()
    cases = [run_case(config_path, case) for case in default_cases()]
    passed = [case for case in cases if case["passed"]]
    failed = [case for case in cases if not case["passed"]]
    return {
        "ok": not failed,
        "generated_at": dt.datetime.now().astimezone().isoformat(),
        "config_path": str(config_path),
        "summary": {"total": len(cases), "passed": len(passed), "failed": len(failed)},
        "cases": cases,
        "safety": "review and extract preview only; no context package is generated and no source file is modified",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Real Query QA",
        "",
        f"Generated: {report['generated_at']}",
        f"Config: `{report['config_path']}`",
        f"Result: {'PASS' if report['ok'] else 'FAIL'}",
        f"Cases: {report['summary']['passed']}/{report['summary']['total']} passed",
        "",
        "Safety: review + extract preview only. The script writes this QA report, but does not generate an AI context package or modify source files.",
        "",
        "| Query | Pass | Review top source | Matched terms | Extract preview | Time |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in report["cases"]:
        review_source = (case["review"]["sources"] or [{}])[0]
        extract_count = len(case["extract"]["sources"])
        lines.append(
            "| {query} | {passed} | {title} | {terms} | {extract_count} candidates | {elapsed} ms |".format(
                query=case["query"],
                passed="yes" if case["passed"] else "no",
                title=str(review_source.get("title") or "-").replace("|", "/"),
                terms=", ".join(str(item) for item in review_source.get("matched_terms") or []) or "-",
                extract_count=extract_count,
                elapsed=case["elapsed_ms"],
            )
        )
    lines.append("")
    for case in report["cases"]:
        lines.extend(
            [
                f"## {case['query']}",
                "",
                f"- Pass: {'yes' if case['passed'] else 'no'}",
                f"- Review answer: {case['review']['answer'] or case['review']['summary']}",
                f"- Review issues: {'; '.join(case['review']['reasons']) if case['review']['reasons'] else 'none'}",
                f"- Extract issues: {'; '.join(case['extract']['reasons']) if case['extract']['reasons'] else 'none'}",
                "",
                "### Sources",
            ]
        )
        for source in case["review"]["sources"][:4]:
            lines.extend(
                [
                    f"- {source['title']}",
                    f"  - matched_terms: {', '.join(str(item) for item in source['matched_terms']) or '-'}",
                    f"  - evidence_excerpt: {source['evidence_excerpt'] or '-'}",
                    f"  - source_path: `{source['path']}`",
                ]
            )
        if not case["review"]["sources"]:
            lines.append("- none")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-query QA for review and extract preview.")
    parser.add_argument("--config", default=str(ROOT / "config.local.json"), help="Path to config.local.json or config.json")
    parser.add_argument("--output-dir", default="", help="Optional output directory")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        config_path = ROOT / "config.json"
    run_dir = Path(args.output_dir) if args.output_dir else ROOT / "output" / "real-query-qa" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    report = run_qa(config_path)
    json_path = write_json(run_dir / "real-query-qa-result.json", report)
    md_path = run_dir / "summary.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "json": str(json_path), "markdown": str(md_path), "summary": report["summary"]}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
