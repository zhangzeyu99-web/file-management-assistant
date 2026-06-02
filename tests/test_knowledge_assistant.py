from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODULE_PATH = ROOT / "knowledge_assistant.py"
SPEC = importlib.util.spec_from_file_location("knowledge_assistant", MODULE_PATH)
assert SPEC and SPEC.loader
knowledge_assistant = importlib.util.module_from_spec(SPEC)
sys.modules["knowledge_assistant"] = knowledge_assistant
SPEC.loader.exec_module(knowledge_assistant)


class KnowledgeAssistantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_root = ROOT / ".tmp-tests"
        self.tmp_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=self.tmp_root)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.vault = self.root / "vault"
        self.fixture = self.root / "fixture"
        self.config_path = self.root / "config.json"
        for path in [
            self.runtime,
            self.fixture,
            self.vault / "00 收件箱",
            self.vault / "01 今日日志",
            self.vault / "02 项目" / "Codex",
            self.vault / "04 例行工作" / "知识行动助手",
            self.vault / "04 例行工作" / "知识整理助手",
        ]:
            path.mkdir(parents=True, exist_ok=True)
        (self.fixture / "NotebookLM Obsidian 教程.txt").write_text(
            "NotebookLM 和 Obsidian 学习资料，适合沉淀成知识卡。",
            encoding="utf-8",
        )
        (self.vault / "04 例行工作" / "知识行动助手" / "旧流程复盘.md").write_text(
            "# 旧流程复盘\n\n文件雷达、知识库体检和 Codex 接手包曾经是主流程。",
            encoding="utf-8",
        )
        (self.vault / "02 项目" / "Codex" / "00 Codex 总览.md").write_text(
            "# Codex 总览\n\n记录 Codex 会话、OpenClaw 记忆和 Obsidian 使用习惯。",
            encoding="utf-8",
        )
        self.config_path.write_text(
            json.dumps(
                {
                    "runtime_root": str(self.runtime),
                    "obsidian_vault": str(self.vault),
                    "obsidian_run_dir": str(self.vault / "04 例行工作" / "知识整理助手"),
                    "allowed_open_roots": [str(self.runtime), str(self.vault), str(self.fixture)],
                    "obsidian_folders": {
                        "inbox": "00 收件箱",
                        "daily": "01 今日日志",
                        "projects": "02 项目",
                        "routine": "04 例行工作",
                        "archive": "99 归档",
                        "codex_project": "Codex",
                    },
                    "watch_roots": [
                        {
                            "name": "Fixture",
                            "path": str(self.fixture),
                            "max_depth": 2,
                            "max_files": 100,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def assertUnifiedResult(self, result: dict, action: str) -> None:
        for key in ["ok", "action", "summary", "sources", "artifacts", "next_actions", "safety", "debug"]:
            self.assertIn(key, result, result)
        self.assertTrue(result["ok"], result)
        self.assertEqual(action, result["action"])
        self.assertIn("不删除", result["safety"])
        self.assertIsInstance(result["sources"], list)
        self.assertIsInstance(result["artifacts"], list)
        self.assertIsInstance(result["next_actions"], list)
        self.assertIsInstance(result["debug"], dict)

    def write_codex_output_index_note(self) -> Path:
        codex_note = self.vault / "02 项目" / "Codex" / "02 Codex 产出索引.md"
        codex_note.write_text(
            "# Codex 产出索引\n\n"
            "## A. 记忆仓\n"
            "- 仓库目录：`D:\\codex\\codex`\n"
            "- GitHub：`https://github.com/zhangzeyu99-web/codex`\n\n"
            "## D. 桌面版 Codex 安装产物\n"
            "- 可执行体：`C:\\Users\\Administrator\\AppData\\Local\\Programs\\OpenAI\\CodexDesktop\\Codex.exe`\n"
            "- 桌面启动脚本：`C:\\Users\\Administrator\\Desktop\\start-codex-desktop.cmd`\n",
            encoding="utf-8",
        )
        return codex_note

    def test_three_core_actions_return_unified_schema(self) -> None:
        self.assertEqual(["organize", "review", "extract"], knowledge_assistant.CORE_ACTIONS)

        organize = knowledge_assistant.run_action(
            "organize",
            {
                "kind": "text",
                "text": "NotebookLM Obsidian 教程需要整理，后续给 AI 复用。",
                "source": "unit-test",
            },
            self.config_path,
        )
        review = knowledge_assistant.run_action("review", {"query": "NotebookLM Obsidian"}, self.config_path)
        extract = knowledge_assistant.run_action(
            "extract",
            {"query": "NotebookLM Obsidian", "request": "帮我继续学习 Obsidian"},
            self.config_path,
        )

        self.assertUnifiedResult(organize, "organize")
        self.assertUnifiedResult(review, "review")
        self.assertUnifiedResult(extract, "extract")
        note_paths = [Path(item["path"]) for item in organize["artifacts"] if item.get("type") == "obsidian-note"]
        self.assertTrue(note_paths, organize)
        self.assertTrue(note_paths[0].exists())
        self.assertIn("生活 / 学习 / 工作", note_paths[0].read_text(encoding="utf-8"))

        self.assertIn("找到的是", review["summary"])
        self.assertEqual("found_answer", review["status"])
        self.assertIn("answer", review)
        self.assertTrue(any("NotebookLM" in item.get("title", "") or "NotebookLM" in item.get("summary", "") for item in review["sources"]))

        self.assertIn("AI 上下文包", extract["summary"])
        self.assertTrue(any(item.get("type") == "prompt" for item in extract["artifacts"]))
        markdown_paths = [Path(item["path"]) for item in extract["artifacts"] if item.get("type") == "markdown"]
        self.assertTrue(markdown_paths, extract)
        self.assertTrue(markdown_paths[0].exists())
        self.assertIn("AI 上下文包", markdown_paths[0].read_text(encoding="utf-8"))

    def test_core_loop_ingests_real_path_reviews_evidence_and_generates_prompt(self) -> None:
        evidence_dir = self.root / "真实入库资料"
        evidence_dir.mkdir()
        evidence_file = evidence_dir / "core-loop-evidence.md"
        evidence_file.write_text(
            "# CoreLoopEvidence-20260525\n\n"
            "添加资料必须真实入库，搜索回顾必须找到已沉淀证据，AI 上下文包必须基于证据生成 prompt。",
            encoding="utf-8",
        )

        organize = knowledge_assistant.run_action(
            "organize",
            {
                "kind": "file",
                "title": "CoreLoopEvidence-20260525 三主闭环资料",
                "text": "CoreLoopEvidence-20260525 是三主闭环真实测试资料。",
                "local_paths": str(evidence_dir),
                "source": "unit-test-real-filesystem",
            },
            self.config_path,
        )
        self.assertUnifiedResult(organize, "organize")
        self.assertIn("已扫描 1 个文件", organize["summary"])
        self.assertTrue(any(item["type"] == "obsidian-note" and Path(item["path"]).exists() for item in organize["artifacts"]))
        self.assertTrue(any(item["type"] == "markdown" and Path(item["path"]).exists() for item in organize["artifacts"]))
        self.assertTrue(any(item["type"] == "json" and Path(item["path"]).exists() for item in organize["artifacts"]))

        review = knowledge_assistant.run_action("review", {"query": "CoreLoopEvidence-20260525"}, self.config_path)
        self.assertUnifiedResult(review, "review")
        self.assertTrue(review["sources"], review)
        joined_sources = "\n".join(str(item) for item in review["sources"])
        self.assertIn("CoreLoopEvidence-20260525", joined_sources)
        self.assertTrue(any(Path(item["path"]).exists() for item in review["sources"] if item.get("path")), review)

        preview = knowledge_assistant.run_action(
            "extract",
            {"query": "CoreLoopEvidence-20260525", "request": "把三主闭环测试资料交给新的 AI 对话", "mode": "preview"},
            self.config_path,
        )
        self.assertUnifiedResult(preview, "extract")
        self.assertIn("候选来源", preview["summary"])
        self.assertFalse(preview["artifacts"], preview)

        source_path = preview["sources"][0]["path"]
        generated = knowledge_assistant.run_action(
            "extract",
            {
                "query": "CoreLoopEvidence-20260525",
                "request": "把三主闭环测试资料交给新的 AI 对话",
                "mode": "generate",
                "source_paths": [source_path],
            },
            self.config_path,
        )
        self.assertUnifiedResult(generated, "extract")
        prompt_artifacts = [item for item in generated["artifacts"] if item["type"] == "prompt"]
        self.assertEqual(1, len(prompt_artifacts), generated)
        prompt = prompt_artifacts[0]["content"]
        self.assertIn("CoreLoopEvidence-20260525", prompt)
        self.assertIn(source_path, prompt)
        self.assertIn("先引用来源路径", prompt)
        self.assertTrue(any(item["type"] == "obsidian-note" and Path(item["path"]).exists() for item in generated["artifacts"]))

    def test_review_requires_keyword_or_question(self) -> None:
        result = knowledge_assistant.run_action("review", {}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("review", result["action"])
        self.assertEqual([], result["sources"])
        self.assertEqual([], result["artifacts"])
        self.assertIn("请输入关键词或问题", result["summary"])

    def test_review_sources_include_direct_evidence_when_available(self) -> None:
        self.write_codex_output_index_note()

        result = knowledge_assistant.run_action(
            "review",
            {"query": "找到我用来启动codex的流程的github仓库"},
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        self.assertIn("github.com/zhangzeyu99-web/codex", result["summary"])
        self.assertIn("direct_evidence", result["sources"][0])
        self.assertIn("github.com/zhangzeyu99-web/codex", result["sources"][0]["direct_evidence"])

    def test_direct_evidence_keeps_windows_paths_openable(self) -> None:
        path = str(self.fixture / "AI_Repo")
        item = {
            "title": "本地路径整理清单",
            "path": str(self.fixture / "整理清单.md"),
            "raw_markdown": f"# 本地路径整理清单\n\n- {path}：directory，4 个文件\n",
            "summary": f"# 本地路径整理清单 - {path}：directory，4 个文件",
            "type": "note",
        }

        evidence = knowledge_assistant.direct_evidence_for_item("AI_Repo 本地路径", item, limit=1)

        self.assertEqual([path], evidence)

        source = knowledge_assistant.source_item_from_review_match("AI_Repo 本地路径", item)
        self.assertIn(path, source["summary"])
        self.assertNotIn(f"{path}：directory", source["summary"])
        self.assertEqual(path, source["direct_evidence"])

    def test_direct_evidence_does_not_return_truncated_or_metadata_paths_from_file_index(self) -> None:
        source = self.fixture / "very-long-source-folder-name-for-evidence-check" / "notebooklm-obsidian-tutorial.txt"
        source.parent.mkdir(parents=True)
        source.write_text("NotebookLM Obsidian 教程原文", encoding="utf-8")
        organizer = self.vault / "04 例行工作" / "知识整理助手" / "整理" / (
            "20260526-101306 NotebookLM 和 Obsidian 教程资料，后续要整理为学习资料并给 AI 复用.md"
        )
        item = {
            "title": "notebooklm-obsidian-tutorial",
            "path": str(self.vault / "04 例行工作" / "知识整理助手" / "文件索引" / "notebooklm-obsidian-tutorial.md"),
            "raw_markdown": "\n".join(
                [
                    "# notebooklm-obsidian-tutorial",
                    f"关联整理记录：`{organizer}`",
                    f"来源路径：`{source}`",
                    "NotebookLM Obsidian 教程原文",
                ]
            ),
            "summary": "",
            "type": "file-index",
        }

        evidence = knowledge_assistant.direct_evidence_for_item("Obsidian 教程", item, limit=2)

        self.assertTrue(evidence, item)
        self.assertFalse(any("…" in value for value in evidence), evidence)
        self.assertFalse(any(str(organizer) in value for value in evidence), evidence)

    def test_review_does_not_fallback_to_unrelated_recent_notes(self) -> None:
        result = knowledge_assistant.run_action("review", {"query": "b站"}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("review", result["action"])
        self.assertEqual([], result["sources"])
        self.assertIn("没有找到", result["summary"])
        self.assertNotIn("找到 5 条", result["summary"])

    def test_review_requires_all_meaningful_terms_for_mixed_chinese_english_query(self) -> None:
        (self.vault / "02 项目" / "Codex" / "简历 SOP.md").write_text(
            "# 简历 SOP\n\n这里只记录简历主线，没有运营内容。",
            encoding="utf-8",
        )
        (self.vault / "02 项目" / "Codex" / "运营公告.md").write_text(
            "# 运营公告\n\n这里只记录运营更新，没有 SOP 内容。",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action("review", {"query": "运营sop"}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("not_found", result["status"])
        self.assertEqual([], result["sources"])
        self.assertIn("没有找到", result["answer"])

    def test_review_returns_answer_and_evidence_cards_for_opex_sop_query(self) -> None:
        good = self.vault / "02 项目" / "Codex" / "08 运营SOP主库.md"
        good.write_text(
            "# 运营SOP主库\n\n"
            "线程 ID：019da997-deca-7870-a059-b24ee8e005e1\n"
            "线程名：运营SOP主库\n"
            "关键结论：根据运营 SOP 为知识库投喂训练 AI 智能体，抓取 162 个 SOP 页面。\n"
            "产物路径：D:\\codex\\output\\doc\\sop_rag_delivery_20260420\\README.md\n",
            encoding="utf-8",
        )
        noise = self.vault / "02 项目" / "Codex" / "OpenClaw 飞书腾讯知识归档.md"
        noise.write_text(
            "# OpenClaw 飞书腾讯知识归档\n\n"
            "这里提到 SOP 派生交付包，但不是运营 SOP 主线程。",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action("review", {"query": "运营sop"}, self.config_path)

        self.assertTrue(result["ok"], result)
        self.assertEqual("found_answer", result["status"])
        self.assertIn("运营SOP主库", result["answer"])
        self.assertIn("运营SOP主库", result["summary"])
        self.assertEqual("运营SOP主库", result["sources"][0]["title"])
        self.assertIn("运营", result["sources"][0]["matched_terms"])
        self.assertIn("sop", [term.lower() for term in result["sources"][0]["matched_terms"]])
        self.assertIn("162", result["sources"][0]["evidence_excerpt"])
        self.assertIn(str(good), result["sources"][0]["path"])
        self.assertIn("reading_order", result["debug"])
        self.assertNotEqual("OpenClaw 飞书腾讯知识归档", result["sources"][0]["title"])

    def test_review_no_match_is_not_reported_as_completed(self) -> None:
        result = knowledge_assistant.run_action("review", {"query": "zzzxxyyqwerty"}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("review", result["action"])
        self.assertEqual([], result["sources"])
        self.assertEqual([], result["artifacts"])

    def test_watch_root_index_uses_extension_specific_globs(self) -> None:
        config = knowledge_assistant.load_config(self.config_path)
        calls: list[str] = []

        def fake_rglob(path: Path, pattern: str):
            calls.append(pattern)
            return iter([])

        with patch.object(Path, "rglob", fake_rglob):
            notes = knowledge_assistant.iter_watch_markdown_notes(config)

        self.assertEqual([], notes)
        self.assertNotIn("*", calls)
        self.assertEqual(["*.md", "*.txt"], calls)

    def test_review_index_cache_reuses_index_and_organize_invalidates_it(self) -> None:
        config = knowledge_assistant.load_config(self.config_path)
        knowledge_assistant.clear_review_index_cache()
        first = knowledge_assistant.build_review_index(config)
        second = knowledge_assistant.build_review_index(config)

        self.assertEqual(first, second)
        self.assertEqual(1, knowledge_assistant.review_index_cache_stats()["misses"])
        self.assertEqual(1, knowledge_assistant.review_index_cache_stats()["hits"])

        knowledge_assistant.run_action(
            "organize",
            {"text": "CacheInvalidationEvidence-20260602", "source": "cache-test"},
            self.config_path,
        )
        knowledge_assistant.build_review_index(config)

        self.assertEqual(1, knowledge_assistant.review_index_cache_stats()["misses"])
        self.assertEqual(0, knowledge_assistant.review_index_cache_stats()["hits"])

    def test_review_finds_codex_startup_github_note_despite_recent_noise(self) -> None:
        self.write_codex_output_index_note()
        noise_root = self.vault / "04 例行工作" / "知识整理助手" / "噪音"
        noise_root.mkdir(parents=True, exist_ok=True)
        for index in range(knowledge_assistant.MAX_REVIEW_ITEMS + 20):
            (noise_root / f"recent-noise-{index:03d}.md").write_text(
                f"# Recent Noise {index}\n\nThis unrelated recent note should not hide Codex project indexes.\n",
                encoding="utf-8",
            )

        result = knowledge_assistant.run_action(
            "review",
            {"query": "找到我用来启动codex的流程的github仓库"},
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        self.assertTrue(any("Codex" in item.get("title", "") for item in result["sources"]), result)
        joined = "\n".join(item.get("summary", "") + "\n" + item.get("path", "") for item in result["sources"])
        self.assertIn("github.com/zhangzeyu99-web/codex", joined)
        self.assertIn("github.com/zhangzeyu99-web/codex", result["summary"])

    def test_review_extracts_direct_answers_for_similar_codex_questions(self) -> None:
        self.write_codex_output_index_note()
        cases = [
            ("codex 记忆仓 github 地址是什么", "github.com/zhangzeyu99-web/codex"),
            ("启动 Codex 的脚本在哪里", "start-codex-desktop.cmd"),
            ("Codex 可执行文件路径是什么", "Codex.exe"),
        ]

        for query, expected in cases:
            with self.subTest(query=query):
                result = knowledge_assistant.run_action("review", {"query": query}, self.config_path)

                self.assertTrue(result["ok"], result)
                self.assertIn(expected, result["summary"])
                self.assertTrue(any("Codex 产出索引" in item.get("title", "") for item in result["sources"]), result)

    def test_review_prioritizes_github_url_over_generic_paths(self) -> None:
        project_note = self.vault / "02 项目" / "Codex" / "09 文件管理助手流程归档.md"
        project_note.write_text(
            "# 文件管理助手流程归档\n\n"
            "## 入口\n"
            "- GitHub 仓库：`https://github.com/zhangzeyu99-web/file-management-assistant`\n"
            "- 本地维护仓库：`D:\\codex\\file-management-assistant`\n"
            "- Obsidian 复盘：`D:\\Obsidian-Work\\04 例行工作\\文件管理助手\\2026-04-24 文件管理助手复盘.md`\n",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action(
            "review",
            {"query": "文件管理助手的 github 仓库在哪里"},
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        self.assertIn("github.com/zhangzeyu99-web/file-management-assistant", result["summary"])
        local_path_index = result["summary"].find("D:\\codex\\file-management-assistant")
        if local_path_index != -1:
            self.assertLess(
                result["summary"].find("github.com/zhangzeyu99-web/file-management-assistant"),
                local_path_index,
                result["summary"],
            )

    def test_direct_answers_prioritize_specific_repo_url_over_generic_github_lines(self) -> None:
        matches = [
            {
                "title": "Codex 工作区文件与对话历史整理",
                "raw_markdown": "\n".join(
                    [
                        "| codex_sessions | 2026-05-09 | Obsidian/知识助手, Codex/运行时, Git/GitHub/发布 | C:\\Users\\Administrator\\.codex\\worktrees\\a6ea\\codex |",
                        "| openclaw_main_sessions | 2026-05-09 | Git/GitHub/发布 | C:\\Users\\Administrator\\.openclaw\\workspace |",
                        "| file-management-assistant | main | 49 | https://github.com/zhangzeyu99-web/file-management-assistant.git |",
                    ]
                ),
            },
            {
                "title": "文件管理助手流程归档",
                "raw_markdown": "GitHub 仓库：https://github.com/zhangzeyu99-web/file-management-assistant\n",
            },
        ]

        answers = knowledge_assistant.extract_direct_answers("文件管理助手的 github 仓库在哪里", matches, limit=1)

        self.assertEqual(1, len(answers))
        self.assertIn("github.com/zhangzeyu99-web/file-management-assistant", answers[0])
        self.assertNotIn("codex_sessions", answers[0])

    def test_direct_answers_prefer_atomic_lines_over_truncated_summary_lines(self) -> None:
        long_summary = (
            "摘要：# 文件管理助手流程归档 ## 结论 文件管理助手已经做成低风险自动化："
            "自动扫描、归档清单、复盘、提醒、写 Obsidian，并通过 OpenClaw 飞书机器人通道发送汇报。"
            "当前版本不删除、不移动、不改名源文件，先保证稳定和可追溯。"
            "## 入口 - GitHub 仓库：https://github.com/zhangzeyu99-web/file-management-assistant"
        )
        matches = [
            {"title": "旧资料二次整理索引", "raw_markdown": long_summary},
            {
                "title": "文件管理助手流程归档",
                "raw_markdown": "GitHub 仓库：https://github.com/zhangzeyu99-web/file-management-assistant\n",
            },
        ]

        answers = knowledge_assistant.extract_direct_answers("文件管理助手的 github 仓库在哪里", matches, limit=1)

        self.assertEqual(
            ["文件管理助手流程归档：GitHub 仓库：https://github.com/zhangzeyu99-web/file-management-assistant"],
            answers,
        )

    def test_direct_answers_prioritize_urls_when_query_asks_for_github_repo(self) -> None:
        matches = [
            {
                "title": "文件管理助手流程归档",
                "raw_markdown": "\n".join(
                    [
                        "Obsidian 复盘：D:\\Obsidian-Work\\04 例行工作\\文件管理助手\\2026-04-24 文件管理助手复盘.md",
                        "每日复盘：D:\\Obsidian-Work\\04 例行工作\\文件管理助手",
                        "仓库：https://github.com/zhangzeyu99-web/file-management-assistant",
                    ]
                ),
            }
        ]

        answers = knowledge_assistant.extract_direct_answers("文件管理助手的 github 仓库在哪里", matches, limit=1)

        self.assertEqual(
            ["文件管理助手流程归档：仓库：https://github.com/zhangzeyu99-web/file-management-assistant"],
            answers,
        )

    def test_direct_answers_do_not_mix_unrelated_project_repos(self) -> None:
        matches = [
            {
                "title": "Codex 产出索引",
                "raw_markdown": "\n".join(
                    [
                        "GitHub：https://github.com/zhangzeyu99-web/codex",
                        "桌面启动脚本：C:\\Users\\Administrator\\Desktop\\start-codex-desktop.cmd",
                    ]
                ),
            },
            {
                "title": "文件管理助手流程归档",
                "raw_markdown": "GitHub 仓库：https://github.com/zhangzeyu99-web/file-management-assistant\n",
            },
        ]

        answers = knowledge_assistant.extract_direct_answers("找到我用来启动codex的流程的github仓库", matches, limit=4)
        joined = "\n".join(answers)

        self.assertIn("github.com/zhangzeyu99-web/codex", joined)
        self.assertNotIn("file-management-assistant", joined)

    def test_extract_preview_surfaces_direct_evidence_in_candidate_sources(self) -> None:
        project_note = self.vault / "02 项目" / "Codex" / "09 文件管理助手流程归档.md"
        project_note.write_text(
            "# 文件管理助手流程归档\n\n"
            "## 结论\n"
            "文件管理助手已经做成低风险自动化：自动扫描、归档清单、复盘、提醒、写 Obsidian。"
            "这里先写足够长的说明文字，模拟真实知识卡摘要把关键入口挤到后面，避免测试只覆盖短笔记。"
            "当前版本不删除、不移动、不改名源文件，先保证稳定和可追溯。\n\n"
            "## 入口\n"
            "- 本地维护仓库：`D:\\codex\\file-management-assistant`\n"
            "- GitHub 仓库：`https://github.com/zhangzeyu99-web/file-management-assistant`\n",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action(
            "extract",
            {"query": "文件管理助手的 github 仓库在哪里", "request": "给 AI 继续处理这个仓库", "mode": "preview"},
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        joined = json.dumps(
            [
                {
                    "summary": item.get("summary", ""),
                    "direct_evidence": item.get("direct_evidence", ""),
                    "why": item.get("why", ""),
                }
                for item in result["sources"]
            ],
            ensure_ascii=False,
        )
        self.assertIn("github.com/zhangzeyu99-web/file-management-assistant", joined)
        local_path_index = joined.find("D:\\codex\\file-management-assistant")
        if local_path_index != -1:
            self.assertLess(joined.find("github.com/zhangzeyu99-web/file-management-assistant"), local_path_index, joined)

    def test_extract_preview_reuses_strict_review_evidence_for_sop_context(self) -> None:
        good = self.vault / "02 项目" / "Codex" / "08 运营SOP主库.md"
        good.write_text(
            "# 运营SOP主库\n\n"
            "线程 ID：019da997-deca-7870-a059-b24ee8e005e1\n"
            "关键结论：运营 SOP 知识库智能体抓取 162 个 SOP 页面。\n"
            "产物路径：D:\\codex\\output\\doc\\sop_rag_delivery_20260420\\README.md\n",
            encoding="utf-8",
        )
        (self.vault / "02 项目" / "Codex" / "简历 SOP.md").write_text(
            "# 简历 SOP\n\n这里只记录简历项目。",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action(
            "extract",
            {"query": "运营sop", "request": "把运营 SOP 项目打包给新的 AI 对话", "mode": "preview"},
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual("candidate_only", result["status"])
        self.assertEqual("运营SOP主库", result["sources"][0]["title"])
        self.assertIn("evidence_excerpt", result["sources"][0])
        self.assertIn("matched_terms", result["sources"][0])
        self.assertNotIn("简历 SOP", json.dumps(result["sources"], ensure_ascii=False))

    def test_extract_preview_reports_available_ai_identity_files(self) -> None:
        identity_root = self.vault / "04 例行工作" / "知识整理助手" / "AI 身份文件"
        identity_root.mkdir(parents=True)
        (identity_root / "AI_IDENTITY.md").write_text(
            "# AI 身份文件\n\n来源：unit-test\n\n## 使用者画像\n\n- 常见任务：产品化知识管理库。\n\n## 下一步\n\n- 生成上下文包时引用本偏好。\n",
            encoding="utf-8",
        )
        source = self.vault / "02 项目" / "Codex" / "AI 上下文包规则.md"
        source.write_text(
            "# AI 上下文包规则\n\n关键结论：上下文包必须先引用来源路径，再给结论。\n",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action(
            "extract",
            {"query": "AI 上下文包规则", "request": "继续优化上下文包", "mode": "preview"},
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual("candidate_only", result["status"])
        self.assertEqual(1, result["debug"]["identity"]["count"])
        self.assertIn("AI_IDENTITY.md", result["debug"]["identity"]["files"][0]["path"])
        self.assertIn("AI 身份文件已可用", result["summary"])

    def test_extract_generate_keeps_direct_evidence_for_confirmed_sources(self) -> None:
        project_note = self.vault / "02 项目" / "Codex" / "09 文件管理助手流程归档.md"
        project_note.write_text(
            "# 文件管理助手流程归档\n\n"
            "## 结论\n"
            "这是一段很长的背景说明，用来模拟真实 Obsidian 笔记。"
            "如果上下文包只复制摘要，GitHub URL 会被截断，AI 拿不到真正可用的仓库地址。"
            "默认安全边界是不删除、不移动、不重命名源文件。\n\n"
            "## 入口\n"
            "- GitHub 仓库：`https://github.com/zhangzeyu99-web/file-management-assistant`\n"
            "- 本地维护仓库：`D:\\codex\\file-management-assistant`\n",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action(
            "extract",
            {
                "query": "文件管理助手的 github 仓库在哪里",
                "request": "请基于仓库继续优化 AI 上下文包",
                "mode": "generate",
                "source_paths": [str(project_note)],
            },
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        prompt = next(item["content"] for item in result["artifacts"] if item.get("type") == "prompt")
        markdown_path = next(Path(item["path"]) for item in result["artifacts"] if item.get("type") == "markdown")
        markdown = markdown_path.read_text(encoding="utf-8")
        self.assertIn("github.com/zhangzeyu99-web/file-management-assistant", prompt)
        self.assertIn("github.com/zhangzeyu99-web/file-management-assistant", markdown)

    def test_extract_generate_includes_ai_identity_summary_in_prompt_and_markdown(self) -> None:
        identity_root = self.vault / "04 例行工作" / "知识整理助手" / "AI 身份文件"
        identity_root.mkdir(parents=True)
        (identity_root / "AI_IDENTITY.md").write_text(
            "# AI 身份文件\n\n"
            "来源：unit-test\n\n"
            "## 使用者画像\n\n"
            "- 角色：本地知识整理助手产品负责人。\n"
            "- 常见任务：严格逐个功能 QA。\n"
            "## 下一步\n\n"
            "- 上下文包要保留用户偏好。\n",
            encoding="utf-8",
        )
        (identity_root / "AI_CONTEXT_BOUNDARY.md").write_text(
            "# AI 上下文边界\n\n"
            "来源：unit-test\n\n"
            "## 默认不提供给 AI\n\n"
            "- 私有 token、账号、邮箱密码。\n"
            "## 下一步\n\n"
            "- 生成前确认来源。\n",
            encoding="utf-8",
        )
        source = self.vault / "02 项目" / "Codex" / "AI 上下文包规则.md"
        source.write_text(
            "# AI 上下文包规则\n\n关键结论：上下文包必须先引用来源路径，再给结论。\n",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action(
            "extract",
            {"query": "AI 上下文包规则", "request": "继续优化上下文包", "mode": "generate", "source_paths": [str(source)]},
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        prompt = next(item["content"] for item in result["artifacts"] if item.get("type") == "prompt")
        markdown_path = next(Path(item["path"]) for item in result["artifacts"] if item.get("type") == "markdown")
        markdown = markdown_path.read_text(encoding="utf-8")
        self.assertIn("AI 身份文件摘要", prompt)
        self.assertIn("本地知识整理助手产品负责人", prompt)
        self.assertIn("严格逐个功能 QA", prompt)
        self.assertIn("私有 token", prompt)
        self.assertIn("## AI 身份文件摘要", markdown)
        self.assertIn("AI_CONTEXT_BOUNDARY.md", markdown)
        self.assertEqual(2, result["debug"]["identity"]["count"])

    def test_extract_generate_exposes_obsidian_context_package_locations(self) -> None:
        source = self.vault / "02 项目" / "Codex" / "AI 上下文包找回规则.md"
        source.write_text(
            "# AI 上下文包找回规则\n\n关键结论：生成上下文包后，用户必须知道 Obsidian 笔记和上下文包目录在哪里。\n",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action(
            "extract",
            {
                "query": "AI 上下文包找回规则",
                "request": "继续优化上下文包找回体验",
                "mode": "generate",
                "source_paths": [str(source)],
            },
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        locations = result["debug"].get("extract_locations")
        self.assertIsInstance(locations, dict, result)
        for key in ["vault", "knowledge_root", "extract_note", "extract_dir", "runtime_markdown", "search_hint"]:
            self.assertIn(key, locations, locations)
            self.assertTrue(locations[key], locations)
        self.assertTrue(Path(locations["extract_note"]).exists(), locations)
        self.assertTrue(Path(locations["extract_dir"]).exists(), locations)
        self.assertTrue(Path(locations["runtime_markdown"]).exists(), locations)
        self.assertIn("AI 上下文包", locations["search_hint"])

    def test_extract_context_package_does_not_mix_unrelated_project_repo_evidence(self) -> None:
        self.write_codex_output_index_note()
        file_assistant_note = self.vault / "02 项目" / "Codex" / "09 文件管理助手流程归档.md"
        file_assistant_note.write_text(
            "# 文件管理助手流程归档\n\n"
            "- GitHub 仓库：`https://github.com/zhangzeyu99-web/file-management-assistant`\n"
            "- PowerShell 入口：`D:\\codex\\file-management-assistant\\run-obsidian-manager.ps1`\n"
            "- PowerShell 入口：`D:\\codex\\file-management-assistant\\run-obsidian-assistant.ps1`\n",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action(
            "extract",
            {"query": "找到我用来启动codex的流程的github仓库", "request": "打包给新的 AI 对话", "mode": "preview"},
            self.config_path,
        )
        joined = json.dumps(
            [
                {
                    "summary": item.get("summary", ""),
                    "direct_evidence": item.get("direct_evidence", ""),
                    "why": item.get("why", ""),
                }
                for item in result["sources"]
            ],
            ensure_ascii=False,
        )

        self.assertTrue(result["ok"], result)
        self.assertIn("github.com/zhangzeyu99-web/codex", joined)
        self.assertNotIn("file-management-assistant", joined)

    def test_extract_preview_prioritizes_exact_executable_evidence(self) -> None:
        self.write_codex_output_index_note()
        weak_note = self.vault / "02 项目" / "Codex" / "12 Codex 线程行为画像与帮助策略.md"
        weak_note.write_text(
            "# Codex 线程行为画像与帮助策略\n\n"
            "Codex 可执行文件路径相关问题先给最短可执行步骤，但这里没有真实 exe 路径。\n"
            "| “怎么用” | 给最短可执行步骤，不从理论讲起 |\n"
            "| “复盘” | 输出可执行改进、失败原因、下次规则 |\n",
            encoding="utf-8",
        )

        result = knowledge_assistant.run_action(
            "extract",
            {"query": "Codex 可执行文件路径是什么", "request": "给 AI 可执行路径上下文", "mode": "preview"},
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(len(result["sources"]), 1)
        self.assertEqual("Codex 产出索引", result["sources"][0]["title"])
        self.assertIn("Codex.exe", result["sources"][0].get("direct_evidence", ""))

    def test_extract_refuses_to_fake_context_when_no_sources_match(self) -> None:
        result = knowledge_assistant.run_action("extract", {"request": "完全不存在的火星资料主题"}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("extract", result["action"])
        self.assertEqual([], result["sources"])
        self.assertEqual([], [item for item in result["artifacts"] if item.get("type") == "prompt"])
        self.assertIn("没有找到可用上下文", result["summary"])

    def test_extract_preview_returns_candidates_without_writing_files(self) -> None:
        extract_dir = self.vault / "04 例行工作" / "知识整理助手" / "提取"

        result = knowledge_assistant.run_action(
            "extract",
            {"request": "继续学习 Obsidian", "mode": "preview"},
            self.config_path,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual("extract", result["action"])
        self.assertGreaterEqual(len(result["sources"]), 1)
        self.assertEqual([], result["artifacts"])
        self.assertIn("候选来源", result["summary"])
        self.assertEqual("preview", result["debug"]["mode"])
        self.assertFalse(extract_dir.exists(), "preview mode must not write an Obsidian package")

    def test_extract_generate_uses_confirmed_source_paths(self) -> None:
        preview = knowledge_assistant.run_action(
            "extract",
            {"request": "继续优化 Codex 记录", "mode": "preview"},
            self.config_path,
        )
        source_path = preview["sources"][0]["path"]

        result = knowledge_assistant.run_action(
            "extract",
            {"request": "继续优化 Codex 记录", "mode": "generate", "source_paths": [source_path]},
            self.config_path,
        )

        self.assertUnifiedResult(result, "extract")
        self.assertEqual([source_path], [item["path"] for item in result["sources"]])
        self.assertTrue(any(item.get("type") == "prompt" for item in result["artifacts"]))
        self.assertTrue(any(item.get("type") == "markdown" for item in result["artifacts"]))
        self.assertEqual("generate", result["debug"]["mode"])

    def test_organize_local_directory_scans_contents_and_writes_manifest(self) -> None:
        source_dir = self.fixture / "AI_Repo"
        source_dir.mkdir()
        (source_dir / "AI_Decision.html").write_text("<h1>AI decision</h1>", encoding="utf-8")
        (source_dir / "AI 调研报告.pdf").write_bytes(b"%PDF-1.4\nfake")

        result = knowledge_assistant.run_action("organize", {"local_paths": str(source_dir)}, self.config_path)

        self.assertUnifiedResult(result, "organize")
        self.assertIn("扫描 2 个文件", result["summary"])
        self.assertEqual(2, result["debug"]["scan"]["total_files"])
        self.assertTrue(any(item.get("type") == "markdown" and "整理清单" in item.get("label", "") for item in result["artifacts"]))
        note_path = next(Path(item["path"]) for item in result["artifacts"] if item.get("type") == "obsidian-note")
        note_text = note_path.read_text(encoding="utf-8")
        self.assertIn("## 路径扫描结果", note_text)
        self.assertIn("AI_Decision.html", note_text)
        self.assertIn("AI 调研报告.pdf", note_text)
        self.assertIn("不会移动源文件", note_text)

    def test_organize_creates_independent_index_notes_for_each_readable_file(self) -> None:
        source_dir = self.fixture / "独立索引资料"
        source_dir.mkdir()
        alpha = source_dir / "Alpha Spec.md"
        beta = source_dir / "Beta Notes.txt"
        binary = source_dir / "raw-data.bin"
        alpha.write_text(
            "# Alpha Spec\n\nPerFileIndexAlpha-20260526：添加资料时必须为每个可读文件生成独立索引条目。",
            encoding="utf-8",
        )
        beta.write_text(
            "PerFileIndexBeta-20260526：搜索回顾应该能直接命中 Beta Notes 的独立文件索引。",
            encoding="utf-8",
        )
        binary.write_bytes(b"\x00\x01\x02not-readable")

        result = knowledge_assistant.run_action("organize", {"local_paths": str(source_dir)}, self.config_path)

        self.assertUnifiedResult(result, "organize")
        self.assertIn("生成 2 条文件索引", result["summary"])
        index_dir = self.vault / "04 例行工作" / "知识整理助手" / "文件索引"
        index_notes = sorted(index_dir.glob("*.md"))
        self.assertEqual(2, len(index_notes), [str(path) for path in index_notes])
        joined = "\n".join(path.read_text(encoding="utf-8") for path in index_notes)
        self.assertIn(str(alpha), joined)
        self.assertIn(str(beta), joined)
        self.assertIn("PerFileIndexAlpha-20260526", joined)
        self.assertIn("PerFileIndexBeta-20260526", joined)
        self.assertNotIn("raw-data.bin\n\n## 原文摘录", joined)

        review = knowledge_assistant.run_action("review", {"query": "PerFileIndexBeta-20260526"}, self.config_path)

        self.assertUnifiedResult(review, "review")
        self.assertTrue(any("文件索引" in item.get("path", "") for item in review["sources"]), review)
        self.assertTrue(any("Beta Notes" in item.get("title", "") for item in review["sources"]), review)

    def test_organize_exposes_obsidian_findability_locations(self) -> None:
        source_dir = self.fixture / "Obsidian找回资料"
        source_dir.mkdir()
        source_file = source_dir / "Findability Note.md"
        source_file.write_text("FindabilityEvidence-20260602：入库后要能在 Obsidian 找回。", encoding="utf-8")

        result = knowledge_assistant.run_action("organize", {"local_paths": str(source_dir)}, self.config_path)

        self.assertUnifiedResult(result, "organize")
        locations = result["debug"].get("obsidian_locations")
        self.assertIsInstance(locations, dict, result)
        for key in ["vault", "organize_note", "organize_dir", "file_index_dir", "search_hint"]:
            self.assertIn(key, locations, locations)
        self.assertTrue(Path(locations["organize_note"]).exists())
        self.assertTrue(Path(locations["organize_dir"]).is_dir())
        self.assertTrue(Path(locations["file_index_dir"]).is_dir())
        self.assertIn("知识整理助手", locations["search_hint"])
        artifact_types = {item["type"] for item in result["artifacts"]}
        self.assertIn("obsidian-directory", artifact_types)
        self.assertIn("file-index-directory", artifact_types)

    def test_organize_refuses_missing_local_path_without_text(self) -> None:
        missing = self.fixture / "missing-folder"

        result = knowledge_assistant.run_action("organize", {"local_paths": str(missing)}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("organize", result["action"])
        self.assertEqual([], result["artifacts"])
        self.assertIn("路径不存在", result["summary"])
        self.assertEqual("no_existing_local_paths", result["debug"]["reason"])

    def test_organize_selected_files_only_is_metadata_not_scan(self) -> None:
        result = knowledge_assistant.run_action(
            "organize",
            {"selected_files": [{"name": "report.pdf", "size": 1234, "relative_path": "docs/report.pdf"}]},
            self.config_path,
        )

        self.assertFalse(result["ok"], result)
        self.assertEqual("organize", result["action"])
        self.assertEqual([], result["artifacts"])
        self.assertIn("浏览器选择", result["summary"])
        self.assertEqual("metadata_only", result["debug"]["reason"])

    def test_organize_refuses_empty_input_instead_of_writing_placeholder_note(self) -> None:
        result = knowledge_assistant.run_action("organize", {}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("organize", result["action"])
        self.assertEqual([], result["artifacts"])
        self.assertIn("没有提供", result["summary"])

    def test_non_core_actions_are_deprecated_at_action_layer(self) -> None:
        for action in ["remind", "legacy-index"]:
            with self.subTest(action=action):
                result = knowledge_assistant.run_action(action, {"query": "GUI"}, self.config_path)

                self.assertFalse(result["ok"], result)
                self.assertEqual(action, result["action"])
                self.assertEqual("deprecated", result["status"])
                self.assertEqual([], result["sources"])
                self.assertEqual([], result["artifacts"])
                self.assertEqual(["添加资料", "搜索回顾", "生成 AI 上下文包"], result["next_actions"])

    def test_legacy_second_pass_indexes_existing_notes_without_moving_them(self) -> None:
        old_paths = [
            self.vault / "04 例行工作" / "知识行动助手" / "旧流程复盘.md",
            self.vault / "02 项目" / "Codex" / "00 Codex 总览.md",
        ]

        result = knowledge_assistant.build_legacy_index(knowledge_assistant.load_config(self.config_path))

        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(result["count"], 2)
        self.assertTrue(Path(result["index_note"]).exists())
        index_text = Path(result["index_note"]).read_text(encoding="utf-8")
        self.assertIn("旧流程复盘", index_text)
        self.assertIn("Codex 总览", index_text)
        for path in old_paths:
            self.assertTrue(path.exists(), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
