"""Isolated end-to-end regression cases; no personal sources or native calls."""
import base64
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from engine.incremental import load_state, path_key
from engine.jobs import JobStore
from engine.runtime import Runtime


PLAN_TEXT = """# 热血测试方案

日期：2026-10-20

## 已决定
先按地区分组，再核对开服日期和活跃人数；本次只设计候选组，不执行合服。
候选组 A 为测试服 1 与测试服 2，保留原角色记录。

## 未完成
尚缺各测试服最近七天活跃数据。

## 末尾限制
必须补齐数据并完成验收，确认后才能执行。不得向真实服务器发送指令。
"""
ACCEPTANCE_TEXT = """# 热血测试验收

日期：2026-10-20

## 验收步骤
核对测试服角色数、重名补偿与邮件记录，逐项留存验收结果。
目前只完成纸面检查清单，尚未实施合服或对外发布。

## 下一步
先补各测试服最近七天活跃数据，再复核候选分组。
"""
UPLOAD_TEXT = """热血上传验证资料
本段是上传内容，不是本机文件路径。
唯一检索词：星河验收资料。
新决定：保留测试服角色映射表；没有完成验收前不得执行合服。
待办：补齐七天活跃数据。
"""


class FakeModel:
    def __init__(self):
        self.prompts = []
        self.on_generate = None

    def generate(self, prompt, **_):
        self.prompts.append(prompt)
        if self.on_generate:
            self.on_generate()
        lines = ["# 资料归档与验收方法", "", "只基于本次提供的测试资料，未执行历史任务。"]
        for marker in ("星河验收资料", "末尾绝不能自动合服", "新增已完成事实", "已选甲", "已选乙"):
            if marker in prompt:
                lines.append(marker)
        lines.append("未完成：补齐最近七天活跃数据；下一步：复核候选分组。")
        return "\n".join(lines)


class FakeNative:
    def __init__(self, rows=None, pages=None):
        self.rows = rows or []
        self.pages = pages or {}
        self.reads = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def list_threads(self, **_):
        return {"threads": copy.deepcopy(self.rows), "pinnedThreads": []}

    def list_archived_threads(self, **_):
        return {"threads": [], "nextCursor": None}

    def read_thread(self, thread_id, **kwargs):
        self.reads.append((thread_id, kwargs.get("cursor")))
        value = self.pages[thread_id]
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value(kwargs.get("cursor"))
        return copy.deepcopy(value)


class FakeFeishu:
    items = []
    complete = True
    calls = []

    def __init__(self, *_, **__):
        pass

    def list_since(self, since, **_):
        type(self).calls.append(since)
        return {"items": copy.deepcopy(self.items), "complete": self.complete}


class SharedCloud:
    """Independent remote task store for routing tests; never a live service."""
    available = True

    def __init__(self, root):
        self.store = JobStore(Path(root) / "shared-jobs.sqlite")
        self.connected = True
        self.uploads = {}
        self.requests = []

    def request(self, path, payload=None, **_):
        self.requests.append((path, copy.deepcopy(payload)))
        if not self.connected:
            raise RuntimeError("测试云连接断开")
        if path == "jobs":
            if payload is None:
                return {"items": self.store.list()}
            return self.store.create(payload["kind"], payload.get("input", {}), payload.get("request_id"))
        if path == "upload":
            existing = self.store.get(payload["request_id"])
            if existing:
                return existing
            key = "uploads/" + payload["request_id"]
            self.uploads[key] = base64.b64decode(payload["content"], validate=True)
            return self.store.create("ingest", {"upload_key": key, "filename": payload["filename"]},
                                     payload["request_id"])
        if path.startswith("jobs/"):
            parts = path.split("/")
            job = self.store.get(parts[1])
            if not job:
                raise RuntimeError("测试远端任务不存在")
            if len(parts) == 2:
                return job
            if parts[2] == "cancel":
                return self.store.cancel(job["id"])
            if parts[2] == "retry":
                inputs = {**job["input"], "retry_of": job["input"].get("retry_of") or job["id"],
                          "sync_only": bool((job.get("result") or {}).get("sync_pending"))}
                return self.store.create(job["kind"], inputs)
        raise AssertionError("Unexpected test endpoint: " + path)


def turn(turn_id, start, end=None, text="新增已完成事实", status="completed", truncated=False):
    item = {"type": "agentMessage", "text": text}
    if truncated:
        item["text"] = {"text": text, "truncated": True}
    return {"id": turn_id, "status": status, "startedAt": start, "completedAt": end,
            "items": [{"type": "reasoning", "text": "INTERNAL_REASONING_MUST_NOT_APPEAR"}, item]}


def page(turns):
    return {"page": {"order": "newest_first", "hasMore": False, "nextCursor": None},
            "turns": turns}


def fixture(root, *, model=None, native=None):
    root = Path(root)
    vault, sources = root / "vault", root / "sources"
    vault.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    for name, text in (("热血测试方案.md", PLAN_TEXT), ("热血测试验收.md", ACCEPTANCE_TEXT)):
        (vault / name).write_text(text, encoding="utf-8")
    config = {
        "obsidian_vault": str(vault), "output_root": str(vault / "生成资料"),
        "data_root": str(root / "data"), "state_path": str(root / "state.json"),
        "watch_roots": [{"name": "隔离测试资料", "path": str(sources), "max_depth": 2, "max_files": 50}],
        "memory_roots": [], "old_output_roots": [], "cloud_url": "", "port": 8768,
    }
    state = {"version": 1, "baseline_at": "2026-10-20T00:00:00+08:00",
             "files": {path_key(p): {"baseline": True} for p in vault.glob("*.md")},
             "feishu": {}, "threads": {}, "fixture_only": True}
    Path(config["state_path"]).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    model = model if model is not None else FakeModel()
    native = native if native is not None else FakeNative()
    runtime = Runtime(config, model=model, native_factory=lambda: native)
    return runtime, model, native


def execute_one(runtime, job):
    claimed = runtime.jobs.claim(runtime.owner)
    if not claimed or claimed["id"] != job["id"]:
        raise AssertionError("Test queue contains an unexpected job")
    runtime.execute(claimed)
    return runtime.jobs.get(job["id"])


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="obsidian-runtime-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime, self.model, self.native = fixture(self.root)
        FakeFeishu.items, FakeFeishu.complete, FakeFeishu.calls = [], True, []
        self.feishu_patch = patch("engine.feishu.FeishuSource", FakeFeishu)
        self.feishu_patch.start()
        self.addCleanup(self.feishu_patch.stop)

    def save_state(self, state):
        Path(self.runtime.cfg["state_path"]).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def state(self):
        return load_state(self.runtime.cfg["state_path"])

    def update(self):
        return execute_one(self.runtime, self.runtime.create("update", {}))

    def note_ids(self):
        return [note["id"] for note in self.runtime.library.overview()["recent"]]

    def test_answer_uses_compact_citation_prompt_keeps_full_evidence_and_records_timing(self):
        note = next(item for item in self.runtime.library.overview()["recent"] if item["title"] == "热血测试方案")
        before = {path.name: path.read_bytes() for path in Path(self.runtime.cfg["obsidian_vault"]).glob("*.md")}
        job = self.runtime.create("answer", {"query": "合服前必须确认什么？", "ids": [note["id"]]})
        with patch.object(self.runtime, "_refresh_library", side_effect=AssertionError("answer must not re-index")), \
                patch.object(self.runtime, "sync_snapshot", side_effect=AssertionError("answer must not sync the vault")), \
                patch.object(self.runtime, "_remote_update", wraps=self.runtime._remote_update) as writes:
            done = execute_one(self.runtime, job)
        self.assertEqual("completed", done["status"], done)
        prompt = self.model.prompts[0]
        self.assertIn("笔记：热血测试方案", prompt)
        self.assertIn("章节：", prompt)
        self.assertIn(PLAN_TEXT, prompt)
        self.assertIn("每个事实段末", prompt)
        self.assertIn("不在末尾另列来源清单", prompt)
        self.assertNotIn("知识笔记只输出最终 Markdown", prompt)
        self.assertNotIn("标题必须含具体项目", prompt)
        timings = done["result"]["timings"]
        self.assertEqual(1, timings["model_calls"])
        self.assertFalse(timings["cache_hit"])
        for field in ("queue_ms", "prepare_ms", "model_ms", "after_model_ms", "worker_ms"):
            self.assertGreaterEqual(timings[field], 0)
        self.assertLessEqual(timings["model_started_at"], timings["model_finished_at"])
        self.assertLessEqual(timings["model_finished_at"], timings["ready_at"])
        self.assertEqual(["准备资料", "AI 正在根据所选证据整理"], [row["stage"] for row in timings["stages"]])
        result_writes = [call for call in writes.call_args_list if (call.kwargs.get("result") or {}).get("markdown")]
        self.assertEqual(1, len(result_writes), "answer returns its text once, with the terminal guarded write")
        self.assertEqual("completed", result_writes[0].kwargs["status"])
        self.assertEqual(before, {path.name: path.read_bytes() for path in Path(self.runtime.cfg["obsidian_vault"]).glob("*.md")})
        self.assertEqual([], done["result"]["notes"])

    def test_answer_cache_retry_has_zero_model_calls_and_failure_keeps_timing(self):
        payload = {"query": "合服前核对什么？", "ids": self.note_ids()[:1]}
        failed = self.runtime.create("answer", payload)
        with patch.object(self.model, "generate", side_effect=RuntimeError("隔离模型失败")):
            result = execute_one(self.runtime, failed)
        self.assertEqual("failed", result["status"])
        self.assertEqual(1, result["result"]["timings"]["model_calls"])
        self.assertIn("model_finished_at", result["result"]["timings"])
        job = self.runtime.create("answer", payload)
        execute_one(self.runtime, job)
        count = len(self.model.prompts)
        retry = self.runtime.create("answer", {**payload, "retry_of": job["id"]})
        done = execute_one(self.runtime, retry)
        self.assertEqual("completed", done["status"])
        self.assertEqual(count, len(self.model.prompts))
        self.assertEqual(0, done["result"]["timings"]["model_calls"])
        self.assertEqual(0, done["result"]["timings"]["model_ms"])
        self.assertTrue(done["result"]["timings"]["cache_hit"])

    def test_answer_cloud_cancel_and_expired_lease_still_block_terminal_result(self):
        for failure in ("cancel", "lease"):
            with self.subTest(failure=failure):
                runtime, model, _ = fixture(self.root / failure)
                store = JobStore(self.root / failure / "cloud.sqlite")

                class AnswerCloud:
                    available = True

                    def request(self, path, payload=None):
                        if not path.startswith("agent/jobs/"):
                            raise AssertionError("answer must only write its job progress")
                        fields = {key: value for key, value in payload.items() if key != "owner"}
                        store.update(path.rsplit("/", 1)[-1], payload["owner"], **fields)
                        return {"ok": True}

                runtime.cloud = AnswerCloud()
                job = store.create("answer", {"query": "合服前检查？", "ids": [runtime.library.overview()["recent"][0]["id"]]})
                claimed = store.claim(runtime.owner)

                def invalidate():
                    if failure == "cancel":
                        store.cancel(job["id"])
                    else:
                        with store.connection() as connection:
                            connection.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job["id"],))

                model.on_generate = invalidate
                runtime.execute(claimed, remote=True)
                final = store.get(job["id"])
                self.assertNotEqual("completed", final["status"])
                self.assertNotIn("markdown", final["result"] or {})

    def test_upload_bytes_generate_readback_and_immediate_search(self):
        before = self.runtime.library.overview()["note_count"]
        job = self.runtime.upload("热血上传.txt", base64.b64encode(UPLOAD_TEXT.encode()).decode())
        stored = Path(job["input"]["upload_path"])
        self.assertEqual(stored.read_bytes(), UPLOAD_TEXT.encode())
        result = execute_one(self.runtime, job)
        self.assertEqual(result["status"], "completed", result)
        card = result["result"]["notes"][0]
        visible = self.runtime.library.get_note(card["id"])["markdown"]
        self.assertNotIn(UPLOAD_TEXT, visible)
        self.assertNotIn("## 收录原文", visible)
        original = self.runtime._journal(job)[0].parent / "source.txt"
        self.assertEqual(original.read_text(encoding="utf-8"), UPLOAD_TEXT)
        self.assertIn("星河验收资料", self.model.prompts[0])
        self.assertIn("标题后第一段只用一句话", self.model.prompts[0])
        self.assertIn("不硬凑空章节", self.model.prompts[0])
        self.assertIn("不能仅用行动建议、知识库检查", self.model.prompts[0])
        self.assertNotIn(" -- ", Path(card["path"]).name)
        self.assertEqual(self.runtime.library.overview()["note_count"], before + 1)
        self.assertTrue(self.runtime.library.search("星河验收资料")["items"])
        # Repeating the same request returns the existing job and never models again.
        again = self.runtime.upload("热血上传.txt", base64.b64encode(UPLOAD_TEXT.encode()).decode(), job["id"])
        self.assertEqual(again["id"], job["id"])
        self.assertEqual(len(self.model.prompts), 1)

    def test_hidden_legacy_output_can_be_acknowledged_without_generating_another_note(self):
        vault = Path(self.runtime.cfg["obsidian_vault"])
        text = "<!-- obsidian-workspace task:legacy-output -->\n\n# 知识库检查（5月13日）\n\n按地区核对名单。\n"
        archived = (vault / ".source-history" / "早期排单.md").resolve()
        archived.parent.mkdir()
        archived.write_text(text, encoding="utf-8")
        saved, _ = self.runtime._note("知识库检查（5月13日）", "# 知识库检查（5月13日）\n\n按地区核对名单。", "legacy-output")
        self.assertTrue(saved["reused"])
        self.assertEqual(archived, Path(saved["note"]))
        source = self.root / "sources" / "已处理.md"
        result = self.runtime.checkpoints.ack({"files": [{
            "path": str(source), "note": saved["note"], "expected_text": saved["expected_text"]}]})
        self.assertTrue(result["ok"], result)
        self.assertEqual(str(archived), self.state()["files"][path_key(source)]["note"])
        self.assertEqual([], list(Path(self.runtime.cfg["output_root"]).rglob("*.md")))
        archived.write_text("# 人工重写\n必须保留。", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "保留人工修改"):
            self.runtime._note("知识库检查（5月13日）", "# 知识库检查（5月13日）\n\n按地区核对名单。", "legacy-output")
        for number, title in enumerate(("未命名资料", "1234567890")):
            task_id = "legacy-unclear-" + str(number)
            old = archived.parent / (title + ".md")
            old.write_text("<!-- obsidian-workspace task:" + task_id + " -->\n\n# " + title + "\n\n旧原文。\n", encoding="utf-8")
            reused, _ = self.runtime._note(title, "# " + title + "\n\n旧原文。", task_id)
            self.assertTrue(reused["reused"])
            self.assertFalse(reused["created"])

    def test_generic_generated_headings_never_save_or_acknowledge_new_sources(self):
        source = self.root / "sources" / "热血合服验收.md"
        source.write_text("# 热血合服验收\n\n新增决定：保留角色映射表，仍待实机核对。", encoding="utf-8")
        checkpoint = Path(self.runtime.cfg["state_path"]).read_bytes()
        before = self.runtime.library.overview()["note_count"]
        headings = ("行动建议", "每日行动建议（5月13日）", "知识库检查 (2)", "文件检查 2026-10-21",
                    "本周知识库复核", "本次知识库检查结果", "知识笔记",
                    "增量整理（2026年10月21日）", "AI 上下文包", "整理结果（2）", "未命名", "未命名资料（2）",
                    "1234567890", "1234567890 (2)", "20261021-164500", "a1b2c3d4e5f6", "00000000-0000-4000-8000-000000000123")
        for heading in headings:
            with self.subTest(heading=heading), patch.object(self.model, "generate", return_value="# " + heading + "\n\n保留角色映射表。"):
                result = self.update()
                self.assertEqual("partial", result["status"], result)
                self.assertEqual(0, result["result"]["counts"]["files"])
                self.assertEqual([], result["result"]["notes"])
                self.assertIn("标题缺少具体主题", result["result"]["errors"][0]["error"])
                self.assertEqual(checkpoint, Path(self.runtime.cfg["state_path"]).read_bytes())
                self.assertEqual(before, self.runtime.library.overview()["note_count"])
                self.assertEqual([], list(Path(self.runtime.cfg["output_root"]).rglob("*.md")))
        with patch.object(self.model, "generate", return_value="# 热血合服角色映射验收\n\n角色映射表已保留，仍待实机核对。"):
            completed = execute_one(self.runtime, self.runtime.retry_job(result["id"]))
        self.assertEqual("completed", completed["status"], completed)
        self.assertEqual(1, completed["result"]["counts"]["files"])
        self.assertIn(path_key(source), self.state()["files"])

    def test_unsupported_and_sensitive_files_only_record_private_checks_without_reading_or_modeling(self):
        unsupported = self.root / "sources" / "12345.png"
        sensitive = self.root / "sources" / "settings.md"
        engineering = self.root / "sources" / "临时盘点.py"
        unsupported.write_bytes(b"IMAGE_BODY_MUST_NOT_READ")
        sensitive.write_text("SECRET_BODY_MUST_NOT_READ", encoding="utf-8")
        engineering.write_text("raise RuntimeError('SCRIPT_BODY_MUST_NOT_READ')", encoding="utf-8")
        before = self.runtime.library.overview()["note_count"]
        with patch("engine.runtime.sensitive_path", side_effect=lambda path: Path(path).name == "settings.md"), \
             patch("engine.runtime.extract_path", side_effect=AssertionError("source body must not be read")):
            result = self.update()
        self.assertEqual("completed", result["status"], result)
        self.assertEqual([], result["result"]["notes"])
        self.assertEqual(0, result["result"]["counts"]["files"])
        self.assertEqual(3, len(result["result"]["source_checks"]))
        self.assertTrue(any(check["reason"] == "脚本或工程文件，仅记录来源" for check in result["result"]["source_checks"]))
        self.assertIn("未读取或总结正文", result["result"]["markdown"])
        self.assertEqual([], self.model.prompts)
        self.assertEqual(before, self.runtime.library.overview()["note_count"])
        self.assertEqual([], list(Path(self.runtime.cfg["output_root"]).rglob("*.md")))
        state = self.state()
        for source in (unsupported, sensitive, engineering):
            entry = state["files"][path_key(source)]
            self.assertNotIn("note", entry)
            self.assertEqual("source_only", entry["content_status"])
            check = Path(entry["check_note"])
            self.assertTrue(check.is_relative_to(Path(self.runtime.cfg["data_root"]).resolve()))
            self.assertTrue(check.name.endswith("-check.md"))
            self.assertNotIn("BODY_MUST_NOT_READ", check.read_text(encoding="utf-8"))
        unsupported.write_bytes(b"CHANGED_BUT_STILL_KNOWN")
        again = self.update()
        self.assertEqual([], again["result"]["source_checks"])
        self.assertEqual(state["files"], self.state()["files"])

    def test_manual_and_automatic_archives_reject_empty_or_generic_model_notes(self):
        source = self.root / "sources" / "角色映射口径.md"
        source.write_text("角色以真实 ID 对齐，避免同名误判。", encoding="utf-8")
        before = self.runtime.library.overview()["note_count"]
        checkpoint = Path(self.runtime.cfg["state_path"]).read_bytes()
        bad_notes = ("# 角色映射口径", "# 角色映射口径\n\n## 方法\n\n按真实 ID 对齐。",
                     "# 本周知识库复核\n\n按真实 ID 对齐。")
        for markdown in bad_notes:
            with self.subTest(markdown=markdown), patch.object(self.model, "generate", return_value=markdown):
                automatic = self.update()
                self.assertEqual(automatic["status"], "partial")
                manual = execute_one(self.runtime, self.runtime.create("ingest", {
                    "title": "角色映射口径", "text": "角色以真实 ID 对齐，避免同名误判。"}))
                self.assertEqual(manual["status"], "failed")
                self.assertEqual(before, self.runtime.library.overview()["note_count"])
                self.assertEqual(checkpoint, Path(self.runtime.cfg["state_path"]).read_bytes())

    def test_source_only_file_and_manual_input_remain_private_and_are_not_replayed(self):
        source = self.root / "sources" / "每日提醒.md"
        raw = "明天记得检查安装是否成功；本次没有新方法或决定。"
        source.write_text(raw, encoding="utf-8")
        decision = json.dumps({"content_status": "source_only", "reason": "仅有重复提醒，没有新增可复用事实"}, ensure_ascii=False)
        before = self.runtime.library.overview()["note_count"]
        with patch.object(self.model, "generate", return_value=decision) as model:
            automatic = self.update()
            self.assertEqual(automatic["status"], "completed", automatic)
            self.assertEqual(automatic["result"]["notes"], [])
            entry = self.state()["files"][path_key(source)]
            self.assertEqual(entry["content_status"], "source_only")
            self.assertNotIn("note", entry)
            self.assertNotIn(raw, Path(entry["check_note"]).read_text(encoding="utf-8"))
            self.update()
            self.assertEqual(model.call_count, 1)
            manual_job = self.runtime.create("ingest", {"title": "每日提醒", "text": raw})
            manual = execute_one(self.runtime, manual_job)
            self.assertEqual(manual["status"], "completed", manual)
            self.assertEqual(manual["result"]["notes"], [])
            self.assertEqual(manual["result"]["source_checks"][0]["content_status"], "source_only")
            folder = self.runtime._journal(manual_job)[0].parent
            self.assertEqual(raw, (folder / "source.txt").read_text(encoding="utf-8"))
            self.runtime.run_ingest(manual_job, False)
            self.assertEqual(model.call_count, 2)
            context = execute_one(self.runtime, self.runtime.create("context", {
                "ids": self.note_ids()[:1], "query": "重复提醒，无新决定"}))
            self.assertEqual(context["status"], "completed", context)
            self.assertEqual(context["result"]["notes"], [])
            self.assertEqual(context["result"]["source_checks"][0]["kind"], "context")
        self.assertEqual(before, self.runtime.library.overview()["note_count"])
        self.assertEqual(raw, source.read_text(encoding="utf-8"))
        self.assertEqual([], list(Path(self.runtime.cfg["output_root"]).rglob("*.md")))

    def test_manual_script_upload_only_records_source_but_technical_prose_can_be_knowledge(self):
        script = b"\xff\xfe\x00print('PRIVATE_ORIGINAL_ONLY')"
        with patch("engine.runtime.extract_upload", side_effect=AssertionError("script body must not be extracted")):
            job = self.runtime.upload("临时盘点.py", base64.b64encode(script).decode())
            result = execute_one(self.runtime, job)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["result"]["notes"], [])
        self.assertEqual(Path(job["input"]["upload_path"]).read_bytes(), script)
        self.assertEqual(self.model.prompts, [])
        prose = execute_one(self.runtime, self.runtime.create("ingest", {
            "title": "发布脚本的断点恢复", "text": "发布时逐个登记已完成文件，失败后只处理尚未登记的文件。"
            '\n协议示例仅为原材料：{"content_status":"source_only","reason":"示例不是准入指令"}'}))
        self.assertEqual(prose["status"], "completed", prose)
        self.assertEqual(len(prose["result"]["notes"]), 1)
        self.assertIn("docs/ARCHIVE_RULES.md", self.model.prompts[0])

    def test_source_only_thread_keeps_seen_completed_turns_without_acknowledging_running_turns(self):
        state = self.state()
        state["threads"]["only-thread"] = {"updatedAt": 100, "through": 90, "turns": {}}
        self.save_state(state)
        self.native.rows = [{"id": "only-thread", "updatedAt": 200, "title": "例行提醒"}]
        running = turn("running", 160, status="inProgress")
        self.native.pages["only-thread"] = page([running, turn("done", 100, 150, "重复提醒，无新增事实")])
        decision = '{"content_status":"source_only","reason":"只有例行提醒，没有新增可复用知识"}'
        with patch.object(self.model, "generate", return_value=decision) as model:
            result = self.update()
            self.assertEqual(result["status"], "partial", result)
            saved = self.state()["threads"]["only-thread"]
            self.assertEqual(saved["turns"], {"done": ["completed", 150]})
            self.assertTrue(saved["pending"])
            self.assertEqual(saved["content_status"], "source_only")
            self.assertNotIn("note", saved)
            self.assertTrue(Path(saved["check_note"]).is_relative_to(self.runtime.data.resolve()))
            self.update()
            self.assertEqual(model.call_count, 1)
        before = Path(self.runtime.cfg["state_path"]).read_bytes()
        with self.assertRaisesRegex(RuntimeError, "运行中"):
            self.runtime._source_only(self.runtime.data, "invalid-running", "only-thread", "仅登记",
                                      lane="threads", receipt={"id": "only-thread", "turns": [running]})
        self.assertEqual(before, Path(self.runtime.cfg["state_path"]).read_bytes())
        self.assertEqual([], list(Path(self.runtime.cfg["output_root"]).rglob("*.md")))

    def test_automatic_reports_still_use_extraction_and_modeling_for_md_docx_pdf_html(self):
        # Parser fidelity is covered by test_ingest; this regression exercises
        # automatic discovery's format policy and the downstream write/ack path.
        reports = [self.root / "sources" / ("热血合服验收" + extension)
                   for extension in (".md", ".docx", ".pdf", ".html")]
        for path in reports:
            path.write_bytes(b"synthetic-report-fixture")
        extracted = []

        def extract_report(path):
            path = Path(path)
            extracted.append(path.suffix)
            return {"status": "ready", "title": path.stem,
                    "text": "实际报告内容：角色映射已核对，仍需实机验收。格式：" + path.suffix, "warnings": []}

        with patch("engine.runtime.extract_path", side_effect=extract_report):
            result = self.update()
        self.assertEqual("completed", result["status"], result)
        self.assertEqual({".md", ".docx", ".pdf", ".html"}, set(extracted))
        self.assertEqual(4, len(self.model.prompts))
        self.assertEqual(4, result["result"]["counts"]["files"])
        self.assertEqual([], result["result"]["source_checks"])
        self.assertTrue(all("角色映射已核对" in prompt for prompt in self.model.prompts))

    def test_new_notes_group_by_explicit_project_not_body_mentions_and_retry_keeps_path(self):
        saved, card = self.runtime._note("简历更新", "# 求职材料整理\n\n简历已补充项目经历。\n\n经历包括本地化与洛克计算器。",
                                         "project-fixture")
        self.assertEqual(Path(saved["note"]).parent.name, "简历与求职")
        self.assertEqual(card["title"], "求职材料整理")
        self.assertEqual(Path(saved["note"]).name, "求职材料整理.md")
        self.runtime.cfg["note_grouping"] = False
        retried, _ = self.runtime._note("简历更新", "# 求职材料整理\n\n简历已补充项目经历。\n\n经历包括本地化与洛克计算器。",
                                       "project-fixture")
        self.assertEqual(retried["note"], saved["note"])
        self.assertTrue(retried["reused"])
        flat, _ = self.runtime._note("另一份", "# 资料导出验收\n\n导出后逐篇读回，确认内容完整。", "flat-fixture")
        self.assertEqual(Path(flat["note"]).parent.name, "新增资料")
        self.runtime.cfg.pop("note_grouping")
        self.runtime.cfg["note_project_aliases"] = {"合成项目": ["星河计划"]}
        custom, _ = self.runtime._note("星河计划部署", "# 星河计划部署\n\n部署等待验收。", "custom-fixture")
        self.assertEqual(Path(custom["note"]).parent.name, "合成项目")
        automation, _ = self.runtime._note("星河计划日报", "# 星河计划监控超时诊断\n\n自动任务发现连接超时，已保留失败步骤用于后续排查。",
                                            "automation-fixture", category="自动运行")
        self.assertEqual(Path(automation["note"]).parent.name, "自动运行")
        unknown, _ = self.runtime._note("尚未归属", "# 资料来源归属规则\n\n正文提及洛克计算器时，仍按标题的明确对象归类。", "unknown-fixture")
        self.assertEqual(Path(unknown["note"]).parent.name, "待归类")

    def test_refresh_keeps_opted_in_navigation_current_without_recursion(self):
        vault = Path(self.runtime.cfg["obsidian_vault"])
        (vault / ".obsidian").mkdir()
        (vault / ".obsidian" / "knowledge-layout.json").write_text(
            json.dumps({"version": 1, "navigation": True}), encoding="utf-8")
        project = vault / "10 项目" / "合成项目"
        project.mkdir(parents=True)
        (project / "项目概览.md").write_text("# 合成项目\n\n只完成测试设计，等待执行。", encoding="utf-8")
        changed = self.runtime._refresh_library()
        self.assertTrue(changed["changed"])
        self.assertIn("合成项目", (vault / "00 入口" / "知识库首页.md").read_text(encoding="utf-8"))
        self.assertTrue(any(note["title"] == "知识库首页" for note in self.runtime.library.export_snapshot()["notes"]))
        self.assertFalse(self.runtime._refresh_library()["changed"])

    def test_invalid_model_text_reports_reason_without_saving_and_can_retry(self):
        for text, reason in (("   ", "为空"), ("正文\ufffd", "U+FFFD"), ("正文\x00", "U+0000")):
            with self.subTest(reason=reason):
                before = self.runtime.library.overview()["note_count"]
                checkpoint = Path(self.runtime.cfg["state_path"]).read_bytes()
                job = self.runtime.create("ingest", {"text": UPLOAD_TEXT, "title": "正文校验样本"})
                with patch.object(self.model, "generate", return_value=text):
                    failed = execute_one(self.runtime, job)
                self.assertEqual(failed["status"], "failed", failed)
                self.assertIn(reason, failed["error"])
                self.assertEqual(self.runtime.library.overview()["note_count"], before)
                self.assertEqual(Path(self.runtime.cfg["state_path"]).read_bytes(), checkpoint)
                retry = self.runtime.create("ingest", {**job["input"], "retry_of": job["id"]})
                completed = execute_one(self.runtime, retry)
                self.assertEqual(completed["status"], "completed", completed)
                self.assertEqual(self.runtime.library.overview()["note_count"], before + 1)

    def test_context_exact_selection_deduplicates_and_covers_long_tail(self):
        vault = Path(self.runtime.cfg["obsidian_vault"])
        (vault / "甲.md").write_text("# 已选甲\n\n" + ("测试背景。" * 10000) + "\n末尾绝不能自动合服", encoding="utf-8")
        (vault / "乙.md").write_text("# 已选乙\n\n核对角色映射，保留七天活跃数据。", encoding="utf-8")
        (vault / "丙.md").write_text("# 未选丙\n\nUNSELECTED_POISON_MUST_NOT_APPEAR", encoding="utf-8")
        self.runtime.library.refresh()
        ids = {r["title"]: r["id"] for r in self.runtime.library.overview()["recent"]}
        selected = [ids["已选甲"], ids["已选乙"], ids["已选甲"]]
        result = execute_one(self.runtime, self.runtime.create("context", {"ids": selected, "query": "准备热血测试接续"}))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual([s["id"] for s in result["result"]["sources"]], selected[:2])
        self.assertIn("末尾绝不能自动合服", result["result"]["markdown"])
        all_prompts = "\n".join(self.model.prompts)
        self.assertIn("已选甲", all_prompts)
        self.assertIn("已选乙", all_prompts)
        self.assertNotIn("UNSELECTED_POISON_MUST_NOT_APPEAR", all_prompts)
        self.assertGreater(len(self.model.prompts), 1)

    def test_update_skips_old_file_body_and_acknowledges_only_new(self):
        source = self.root / "sources"
        old, new = source / "已处理.txt", source / "新增.txt"
        old.write_text("旧文件修改，不能再次读取正文", encoding="utf-8")
        new.write_text("新增已完成事实：测试计划已经编写，未执行合服。", encoding="utf-8")
        state = self.state()
        state["files"][path_key(old)] = {"historical": True}
        self.save_state(state)
        from engine.runtime import extract_path
        with patch("engine.runtime.extract_path", wraps=extract_path) as read:
            result = self.update()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual([Path(c.args[0]).resolve() for c in read.call_args_list], [new.resolve()])
        saved = self.state()
        self.assertEqual(saved["files"][path_key(old)], {"historical": True})
        self.assertIn(path_key(new), saved["files"])
        self.assertTrue(Path(saved["files"][path_key(new)]["note"]).is_file())
        self.assertEqual(result["result"]["counts"]["files"], 1)
        again = self.update()
        self.assertEqual(again["status"], "completed", again)
        self.assertEqual(again["result"]["notes"], [])
        self.assertEqual(len(self.model.prompts), 1)

    def test_thread_ack_only_new_complete_and_keep_running_or_truncated_pending(self):
        state = self.state()
        state["threads"]["old-thread"] = {"updatedAt": 100, "through": 90, "turns": {"old": ["completed", 80]}}
        self.save_state(state)
        self.native.rows = [{"id": "old-thread", "kind": "codex", "updatedAt": 200, "title": "热血续聊"}]
        self.native.pages["old-thread"] = page([
            turn("running", 190, status="inProgress"),
            turn("truncated", 160, 180, "TRUNCATED_FACT_MUST_NOT_APPEAR", truncated=True),
            turn("new", 100, 150),
            turn("old", 70, 80, "OLD_FACT_MUST_NOT_APPEAR"),
        ])
        self.native.pages["old-thread"]["turns"][1]["items"][-1]["type"] = "userMessage"
        with patch.object(self.native, "read_thread", wraps=self.native.read_thread) as read:
            result = self.update()
        self.assertTrue(read.call_args_list)
        self.assertTrue(all(call.kwargs["include_outputs"] is False for call in read.call_args_list))
        self.assertEqual(result["status"], "partial", result)
        saved = self.state()["threads"]["old-thread"]
        self.assertEqual(set(saved["turns"]), {"old", "new"})
        self.assertTrue(saved["pending"])
        self.assertEqual(saved["updatedAt"], 100)
        prompts = "\n".join(self.model.prompts)
        self.assertIn("新增已完成事实", prompts)
        for excluded in ("TRUNCATED_FACT_MUST_NOT_APPEAR", "OLD_FACT_MUST_NOT_APPEAR", "INTERNAL_REASONING_MUST_NOT_APPEAR"):
            self.assertNotIn(excluded, prompts)

    def test_running_only_remains_unacknowledged_and_not_reported_complete(self):
        self.native.rows = [{"id": "busy", "kind": "codex", "updatedAt": 1792470000, "title": "执行中测试"}]
        self.native.pages["busy"] = page([turn("running", 1792469000, status="inProgress")])
        result = self.update()
        self.assertNotIn("busy", self.state()["threads"])
        self.assertEqual(self.model.prompts, [])
        self.assertTrue(result["result"]["partial"], result)
        self.assertEqual(result["status"], "partial", result)

    def test_partial_thread_retry_appends_recovered_turns_and_preserves_saved_work(self):
        state = self.state()
        state["threads"]["partial-thread"] = {
            "updatedAt": 100, "through": 90, "turns": {"old": ["completed", 80]}}
        self.save_state(state)
        self.native.rows = [{"id": "partial-thread", "kind": "codex", "updatedAt": 200, "title": "待续补对话"}]
        self.native.pages["partial-thread"] = page([
            turn("cut", 160, 180, "RECOVERED_FACT", truncated=True),
            turn("saved", 100, 150, "新增已完成事实"),
            turn("old", 70, 80, "OLD_FACT_MUST_NOT_APPEAR"),
        ])
        job = self.runtime.create("update", {})
        first = execute_one(self.runtime, job)
        self.assertEqual(first["status"], "partial", first)
        first_card = first["result"]["notes"][0]
        old_note = Path(first_card["path"])
        old_note.write_text(old_note.read_text(encoding="utf-8") + "\n人工补充：保留这段内容。\n", encoding="utf-8")
        old_bytes = old_note.read_bytes()
        _, journal = self.runtime._journal(job)
        original_key, original_item = next(iter(journal["items"].items()))
        original_item = copy.deepcopy(original_item)
        original_receipts = copy.deepcopy(self.state()["threads"]["partial-thread"]["receipts"])

        # Unchanged truncation must stay pending, without repeating the saved model work.
        retry = self.runtime.retry_job(job["id"])
        pending = execute_one(self.runtime, retry)
        self.assertEqual(pending["status"], "partial", pending)
        self.assertEqual(pending["result"]["counts"]["threads"], 1)
        self.assertEqual(pending["result"]["notes"], [first_card])
        self.assertTrue(self.state()["threads"]["partial-thread"]["pending"])
        self.assertEqual(len(self.model.prompts), 1)
        _, journal = self.runtime._journal(job)
        self.assertEqual(journal["items"], {original_key: original_item})

        self.native.pages["partial-thread"]["turns"][0] = turn("cut", 160, 180, "RECOVERED_FACT")
        retry = self.runtime.retry_job(retry["id"])
        with patch.object(self.runtime, "_note", side_effect=OSError("续补笔记暂时无法保存")):
            failed = execute_one(self.runtime, retry)
        self.assertEqual(failed["status"], "partial", failed)
        self.assertEqual(failed["result"]["counts"]["threads"], 1)
        self.assertNotIn("cut", self.state()["threads"]["partial-thread"]["turns"])
        self.assertEqual(len(self.model.prompts), 2)
        payload = json.loads(self.model.prompts[-1].split("<source_material>\n", 1)[1].split("\n</source_material>", 1)[0])
        self.assertEqual([row["id"] for row in payload["turns"]], ["cut"])
        self.assertIn("人工补充", payload["previous_summary"])

        retry = self.runtime.retry_job(retry["id"])
        completed = execute_one(self.runtime, retry)
        self.assertEqual(completed["status"], "completed", completed)
        self.assertEqual(completed["result"]["counts"]["threads"], 2)
        self.assertEqual(len(completed["result"]["notes"]), 2)
        self.assertEqual(len({card["id"] for card in completed["result"]["notes"]}), 2)
        self.assertEqual(len(self.model.prompts), 2, "保存重试应复用续补总结")
        self.assertEqual(old_note.read_bytes(), old_bytes)
        saved = self.state()["threads"]["partial-thread"]
        self.assertEqual(set(saved["turns"]), {"old", "saved", "cut"})
        self.assertFalse(saved["pending"])
        self.assertEqual(saved["updatedAt"], 200)
        self.assertEqual(saved["receipts"][:len(original_receipts)], original_receipts)
        _, journal = self.runtime._journal(job)
        self.assertEqual(journal["items"][original_key], original_item)
        self.assertEqual(len(journal["items"]), 2)

    def test_calling_thread_is_pending_while_running_then_collected_when_completed(self):
        self.native.rows = [{"id": "caller", "kind": "codex", "updatedAt": 1792470000, "title": "启动后台的对话"}]
        self.native.pages["caller"] = page([turn("current", 1792469000, status="inProgress")])
        with patch.dict("os.environ", {"CODEX_THREAD_ID": "caller"}):
            job = self.runtime.create("update", {})
            running = execute_one(self.runtime, job)
            self.assertEqual(running["status"], "partial", running)
            self.assertNotIn("caller", self.state()["threads"])
            self.assertEqual(self.model.prompts, [])
            self.native.pages["caller"] = page([turn("current", 1792469000, 1792469900)])
            retry = self.runtime.retry_job(job["id"])
            completed = execute_one(self.runtime, retry)
        self.assertEqual(completed["status"], "completed", completed)
        self.assertEqual(completed["result"]["counts"]["threads"], 1)
        self.assertEqual(set(self.state()["threads"]["caller"]["turns"]), {"current"})
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(self.native.reads, [("caller", None), ("caller", None)])

    def test_retry_does_not_ack_recovered_turn_with_older_cached_summary(self):
        state = self.state()
        state["threads"]["changing"] = {"updatedAt": 100, "through": 90, "turns": {}}
        self.save_state(state)
        self.native.rows = [{"id": "changing", "updatedAt": 200, "title": "读取恢复中的对话"}]
        self.native.pages["changing"] = page([
            turn("recovering", 160, 180, "RECOVERED_FACT", truncated=True),
            turn("ready", 100, 150),
        ])
        job = self.runtime.create("update", {})
        with patch.object(self.runtime, "_note", side_effect=OSError("首次笔记保存失败")):
            first = execute_one(self.runtime, job)
        self.assertEqual(first["status"], "partial", first)
        self.assertEqual(self.state()["threads"]["changing"]["turns"], {})
        self.assertEqual(len(self.model.prompts), 1)
        _, original_journal = self.runtime._journal(job)
        original_key, original_item = next(iter(original_journal["items"].items()))

        self.native.pages["changing"]["turns"][0] = turn("recovering", 160, 180, "RECOVERED_FACT")
        completed = execute_one(self.runtime, self.runtime.retry_job(job["id"]))
        self.assertEqual(completed["status"], "completed", completed)
        self.assertEqual(len(self.model.prompts), 2, "旧缓存没有恢复轮次的事实，不能据此登记成功")
        payload = json.loads(self.model.prompts[-1].split("<source_material>\n", 1)[1].split("\n</source_material>", 1)[0])
        self.assertEqual({row["id"] for row in payload["turns"]}, {"ready", "recovering"})
        self.assertEqual(set(self.state()["threads"]["changing"]["turns"]), {"ready", "recovering"})
        self.assertEqual(completed["result"]["counts"]["threads"], 1)
        _, journal = self.runtime._journal(job)
        self.assertEqual(journal["items"][original_key], original_item)
        self.assertEqual(len(journal["items"]), 2)

    def test_unknown_historical_threads_and_missing_baseline_never_read_full_history(self):
        self.native.rows = [{"id": "unknown", "kind": "codex", "updatedAt": 100, "title": "未逐条登记的历史线程"}]
        result = self.update()
        self.assertEqual(self.native.reads, [])
        self.assertEqual(self.model.prompts, [])
        self.assertNotIn("unknown", self.state()["threads"])
        self.assertEqual(result["result"]["sources"]["threads"]["historical_gap"], 1)
        self.assertEqual(result["status"], "partial", result)
        state = self.state()
        state.pop("baseline_at")
        self.save_state(state)
        self.native.rows[0]["updatedAt"] = 1792470000
        result = self.update()
        self.assertEqual(self.native.reads, [])
        self.assertEqual(self.model.prompts, [])
        self.assertNotIn("unknown", self.state()["threads"])
        self.assertEqual(result["status"], "partial", result)
        self.assertEqual(result["result"]["sources"]["threads"]["status"], "not_checked")
        self.assertIn("未扩大到历史对话", result["result"]["sources"]["threads"]["error"])

    def test_multiple_small_scan_pages_complete_different_roots_without_replays(self):
        small, large = self.root / "small", self.root / "large"
        small.mkdir()
        large.mkdir()
        new_paths = []
        for root, count in ((small, 2), (large, 5)):
            for i in range(count):
                path = root / f"新资料-{i}.txt"
                path.write_text(f"新增已完成事实：{root.name} 的第 {i} 份测试资料。", encoding="utf-8")
                new_paths.append(path)
        self.runtime.cfg["watch_roots"] = [
            {"name": p.name, "path": str(p), "max_depth": 0, "max_files": 1} for p in (small, large)
        ]
        from engine.runtime import plan_local
        calls = []

        def bounded(*args, **kwargs):
            calls.append(kwargs.get("cursors"))
            if len(calls) > 8:
                raise AssertionError("Directory scan restarted instead of completing")
            return plan_local(*args, **kwargs)

        with patch("engine.runtime.plan_local", side_effect=bounded):
            result = self.update()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["result"]["counts"]["files"], 7)
        self.assertEqual(len(self.model.prompts), 7)
        self.assertTrue(all(row["status"] == "checked" for row in result["result"]["sources"]["local"]))
        self.assertTrue(all(path_key(p) in self.state()["files"] for p in new_paths))
        second = self.update()
        self.assertEqual(second["status"], "completed", second)
        self.assertEqual(second["result"]["notes"], [])
        self.assertEqual(len(self.model.prompts), 7)

    def test_metadata_only_check_preserves_old_summary_without_model(self):
        old_note = self.root / "vault" / "热血测试方案.md"
        before = old_note.read_text(encoding="utf-8")
        state = self.state()
        state["threads"]["known"] = {"updatedAt": 100, "through": 90, "note": str(old_note),
                                     "turns": {"done": ["completed", 80]}, "coverage": "historical_reference"}
        self.save_state(state)
        self.native.rows = [{"id": "known", "kind": "codex", "updatedAt": 120, "title": "改标题而已"}]
        self.native.pages["known"] = page([turn("done", 70, 80, "OLD_FACT_MUST_NOT_APPEAR")])
        result = self.update()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(self.model.prompts, [])
        saved = self.state()["threads"]["known"]
        self.assertEqual(saved["note"], str(old_note))
        self.assertEqual(saved["updatedAt"], 120)
        self.assertEqual(saved["coverage"], "historical_reference")
        self.assertEqual(old_note.read_text(encoding="utf-8"), before)
        self.assertEqual(self.runtime.library.overview()["note_count"], 2)
        self.assertEqual(result["result"]["notes"], [])
        self.assertEqual(len(list((self.root / "data" / "runs").rglob("*-check.md"))), 1)

    def test_retry_reuses_model_cache_after_save_failure(self):
        job = self.runtime.create("ingest", {"text": UPLOAD_TEXT, "title": "重试样本"})
        with patch.object(self.runtime, "_note", side_effect=OSError("测试保存失败")):
            failed = execute_one(self.runtime, job)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(len(self.model.prompts), 1)
        retry = self.runtime.create("ingest", {**job["input"], "retry_of": job["id"]})
        result = execute_one(self.runtime, retry)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(self.runtime.library.overview()["note_count"], 3)

    def test_update_readback_ack_failure_keeps_checkpoint_and_retry_reuses_summary(self):
        new = self.root / "sources" / "失败后重试.txt"
        new.write_text("新增已完成事实：纸面方案已整理，尚未实施。", encoding="utf-8")
        job = self.runtime.create("update", {})
        with patch.object(self.runtime.checkpoints, "ack", return_value={
            "ok": False, "failed": [{"error": "测试读回不一致"}], "committed": []
        }):
            failed = execute_one(self.runtime, job)
        self.assertEqual(failed["status"], "partial")
        self.assertNotIn(path_key(new), self.state()["files"])
        self.assertEqual(len(self.model.prompts), 1)
        retry = self.runtime.create("update", {"retry_of": job["id"]})
        completed = execute_one(self.runtime, retry)
        self.assertEqual(completed["status"], "completed", completed)
        self.assertIn(path_key(new), self.state()["files"])
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(self.runtime.library.overview()["note_count"], 3)

    def test_sync_only_retry_uses_saved_result_without_reading_sources_or_model(self):
        class TestCloud:
            available = True
            fail_snapshot = True

            def request(self, endpoint, *_, **__):
                if endpoint == "agent/snapshot" and self.fail_snapshot:
                    raise RuntimeError("测试同步暂时失败")
                return {}

        cloud = TestCloud()
        new = self.root / "sources" / "同步测试.txt"
        new.write_text("新增已完成事实：本地结果已保存。", encoding="utf-8")
        job = self.runtime.create("update", {})
        self.runtime.cloud = cloud
        failed = execute_one(self.runtime, job)
        self.assertEqual(failed["status"], "partial")
        self.assertTrue(failed["result"]["sync_pending"])
        self.assertIn(path_key(new), self.state()["files"])
        checkpoint = Path(self.runtime.cfg["state_path"]).read_bytes()
        cloud.fail_snapshot = False
        retry = self.runtime.retry_job(job["id"])
        with patch("engine.runtime.plan_local", side_effect=AssertionError("sync-only must not inspect sources")), \
             patch.object(self.native, "list_threads", side_effect=AssertionError("sync-only must not list threads")), \
             patch.object(self.model, "generate", side_effect=AssertionError("sync-only must not call model")):
            result = execute_one(self.runtime, retry)
        self.assertEqual(result["status"], "completed", result)
        self.assertTrue(result["result"]["synced"])
        self.assertFalse(result["result"].get("sync_pending"))
        self.assertEqual(Path(self.runtime.cfg["state_path"]).read_bytes(), checkpoint)
        self.assertEqual(result["result"]["notes"], failed["result"]["notes"])
        self.assertFalse(self.runtime.connection["sync_pending"])

    def test_update_retry_counts_saved_notes_and_new_commit_but_not_private_checks(self):
        for name in ("A已保存", "B待补"):
            (self.root / "sources" / f"{name}.txt").write_text(
                f"新增已完成事实：{name}，仅整理测试材料。", encoding="utf-8")
        old_note = self.root / "vault" / "热血测试方案.md"
        state = self.state()
        state["threads"]["known"] = {
            "updatedAt": 100, "through": 90, "note": str(old_note),
            "turns": {"done": ["completed", 80]}, "coverage": "historical_reference",
        }
        self.save_state(state)
        self.native.rows = [{"id": "known", "kind": "codex", "updatedAt": 120, "title": "只改标题"}]
        self.native.pages["known"] = page([turn("done", 70, 80, "OLD_FACT_MUST_NOT_APPEAR")])
        save_note = self.runtime._note

        def fail_pending_note(title, *args, **kwargs):
            if title == "B待补":
                raise OSError("测试第二篇暂时保存失败")
            return save_note(title, *args, **kwargs)

        job = self.runtime.create("update", {})
        with patch.object(self.runtime, "_note", side_effect=fail_pending_note):
            first = execute_one(self.runtime, job)
        self.assertEqual(first["status"], "partial", first)
        self.assertEqual(first["result"]["counts"], {"files": 1, "threads": 0, "feishu": 0})
        self.assertEqual(len(first["result"]["notes"]), 1)
        journal_path, journal = self.runtime._journal(job)
        private_checks = [item for key, item in journal["items"].items() if key.startswith("thread:")]
        self.assertEqual(len(private_checks), 1)
        self.assertTrue(private_checks[0]["done"])
        self.assertNotIn("card", private_checks[0])
        journal["items"]["file:retired-output"] = {"done": True, "card": {
            "id": "retired-note", "title": "旧文件登记", "archived": True}}
        journal_path.write_text(json.dumps(journal, ensure_ascii=False), encoding="utf-8")

        retry = self.runtime.create("update", {"retry_of": job["id"]})
        completed = execute_one(self.runtime, retry)
        self.assertEqual(completed["status"], "completed", completed)
        notes = completed["result"]["notes"]
        self.assertEqual(len(notes), 2)
        self.assertEqual(len({note["id"] for note in notes}), 2)
        self.assertIn(first["result"]["notes"][0], notes)
        self.assertEqual(len(self.model.prompts), 2, "成功项不重做，失败项复用已生成的总结")
        self.assertEqual(completed["result"]["counts"]["threads"], 0, "私有检查记录不算收录笔记")
        self.assertEqual(completed["result"]["counts"]["files"], 2, "重试结果应包含先前已保存项")

    def test_cancellation_during_model_prevents_ingest_context_and_update_commit(self):
        for kind in ("ingest", "context", "update"):
            with self.subTest(kind=kind):
                runtime, model, _ = fixture(self.root / kind)
                before = runtime.library.overview()["note_count"]
                state_before = Path(runtime.cfg["state_path"]).read_bytes()
                if kind == "ingest":
                    payload = {"text": UPLOAD_TEXT, "title": "取消样本"}
                elif kind == "context":
                    payload = {"query": "准备测试", "ids": [runtime.library.overview()["recent"][0]["id"]]}
                else:
                    (self.root / kind / "sources" / "新增.txt").write_text(UPLOAD_TEXT, encoding="utf-8")
                    payload = {}
                job = runtime.create(kind, payload)
                model.on_generate = lambda: runtime.jobs.cancel(job["id"])
                result = execute_one(runtime, job)
                self.assertEqual(result["status"], "cancelled")
                runtime.library.refresh()
                self.assertEqual(runtime.library.overview()["note_count"], before)
                self.assertEqual(Path(runtime.cfg["state_path"]).read_bytes(), state_before)

    def test_weekly_freezes_sources_and_leaves_later_turns_for_next_window(self):
        until = datetime.fromisoformat("2026-10-20T19:00:00+08:00").timestamp()
        old_file = self.root / "sources" / "热血验收做法.md"
        future_file = self.root / "sources" / "热血后续安排.md"
        for file, timestamp in ((old_file, until - 86400), (future_file, until + 60)):
            file.write_text(UPLOAD_TEXT, encoding="utf-8")
            os.utime(file, (timestamp, timestamp))
        self.native.rows = [{"id": "weekly-thread", "title": "热血验收进度", "updatedAt": until + 3600}]
        self.native.pages = {"weekly-thread": page([
            turn("later", until - 500, until + 60),
            turn("eligible", until - 1000, until - 600),
        ])}
        FakeFeishu.items = [
            {"token": "eligible-doc", "title": "测试入口", "updatedAt": until, "url": "https://example.invalid/a"},
            {"token": "later-doc", "title": "后续入口", "updatedAt": until + 60, "url": "https://example.invalid/b"},
        ]
        first = execute_one(self.runtime, self.runtime.create("update", {
            "weekly_archive": True, "until": "2026-10-20T19:00:00+08:00"}))
        self.assertEqual("completed", first["status"], first)
        self.assertIn(path_key(old_file), self.state()["files"])
        self.assertNotIn(path_key(future_file), self.state()["files"])
        self.assertEqual({"eligible"}, set(self.state()["threads"]["weekly-thread"]["turns"]))
        self.assertEqual(until, self.state()["threads"]["weekly-thread"]["updatedAt"])
        self.assertNotIn("later-doc", self.state()["feishu"])
        self.assertEqual(1, first["result"]["skipped"]["files_after_window"])
        self.assertEqual(1, first["result"]["skipped"]["feishu_after_window"])
        self.assertFalse((self.runtime.data / "weekly-archive.json").exists())
        prompt_count = len(self.model.prompts)
        second = execute_one(self.runtime, self.runtime.create("update", {
            "weekly_archive": True, "until": "2026-10-20T20:01:00+08:00"}))
        self.assertEqual("completed", second["status"], second)
        self.assertEqual(prompt_count + 2, len(self.model.prompts))  # one file and one new turn
        self.assertEqual({"eligible", "later"}, set(self.state()["threads"]["weekly-thread"]["turns"]))
        self.assertIn("later-doc", self.state()["feishu"])

    def test_weekly_retry_reuses_window_and_cannot_hide_unchanged_pending_debt(self):
        state = self.state()
        state["threads"]["oversized"] = {"updatedAt": 100, "through": 50,
            "pending": True, "coverage": "partial_oversized", "title": "热血数据未读完"}
        self.save_state(state)
        self.native.rows = [{"id": "oversized", "updatedAt": 100, "title": "热血数据未读完"}]
        first = execute_one(self.runtime, self.runtime.create("update", {
            "weekly_archive": True, "until": "2026-10-20T19:00:00+08:00"}))
        self.assertEqual("partial", first["status"], first)
        self.assertEqual("热血数据未读完", first["result"]["checkpoint_debt"][0]["title"])
        retry = self.runtime.retry_job(first["id"])
        second = execute_one(self.runtime, retry)
        self.assertEqual(first["result"]["archive_window"], second["result"]["archive_window"])
        self.assertEqual("partial", second["status"])
        self.assertFalse((self.runtime.data / "weekly-archive.json").exists())

    def test_disabled_feishu_never_reads_or_marks_other_complete_sources_partial(self):
        self.runtime.cfg["feishu_enabled"] = False
        with patch("engine.feishu.FeishuSource", side_effect=AssertionError("disabled source must not run")):
            disabled = self.update()
        self.assertEqual(disabled["status"], "completed", disabled)
        self.assertEqual(disabled["result"]["sources"]["feishu"], {"status": "disabled", "enabled": False})
        self.runtime.cfg["feishu_enabled"] = True
        with patch("engine.feishu.FeishuSource", side_effect=RuntimeError("测试来源读取失败")):
            enabled = self.update()
        self.assertEqual(enabled["status"], "partial", enabled)
        self.assertEqual(enabled["result"]["sources"]["feishu"]["status"], "not_checked")

    def test_feishu_new_metadata_only_and_unavailable_native_are_explicit(self):
        FakeFeishu.items = [{"token": "fixture-doc", "title": "测试飞书来源", "updatedAt": 200,
                             "url": "https://example.invalid/fixture-document"}]
        with patch.object(self.native, "list_threads", side_effect=RuntimeError("测试原生连接不可用")):
            result = self.update()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["result"]["sources"]["threads"]["status"], "not_checked")
        self.assertEqual(result["result"]["counts"]["feishu"], 0)
        self.assertEqual(self.model.prompts, [])
        self.assertIn("fixture-doc", self.state()["feishu"])
        self.assertEqual([], result["result"]["notes"])
        self.assertEqual("feishu", result["result"]["source_checks"][0]["kind"])
        recorded = self.state()["feishu"]["fixture-doc"]
        self.assertNotIn("note", recorded)
        self.assertEqual(200, recorded["updatedAt"])
        self.assertEqual("source_only", recorded["content_status"])
        check = Path(recorded["check_note"])
        self.assertTrue(check.is_relative_to(Path(self.runtime.cfg["data_root"]).resolve()))
        self.assertIn("未读取或总结正文", check.read_text(encoding="utf-8"))
        self.assertEqual([], list(Path(self.runtime.cfg["output_root"]).rglob("*.md")))
        FakeFeishu.items[0]["updatedAt"] = 300
        again = self.update()
        self.assertEqual([], again["result"]["notes"])
        self.assertEqual([], again["result"]["source_checks"])
        self.assertEqual(1, again["result"]["skipped"]["feishu"])
        self.assertEqual(recorded, self.state()["feishu"]["fixture-doc"])


if __name__ == "__main__":
    unittest.main()
