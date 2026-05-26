from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


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

        self.assertIn("本地摘要", review["summary"])
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

    def test_review_does_not_fallback_to_unrelated_recent_notes(self) -> None:
        result = knowledge_assistant.run_action("review", {"query": "b站"}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("review", result["action"])
        self.assertEqual([], result["sources"])
        self.assertIn("没有找到", result["summary"])
        self.assertNotIn("找到 5 条", result["summary"])

    def test_review_no_match_is_not_reported_as_completed(self) -> None:
        result = knowledge_assistant.run_action("review", {"query": "zzzxxyyqwerty"}, self.config_path)

        self.assertFalse(result["ok"], result)
        self.assertEqual("review", result["action"])
        self.assertEqual([], result["sources"])
        self.assertEqual([], result["artifacts"])

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
