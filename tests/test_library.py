from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from engine.library import Library


# Thread identities and delivery details are synthetic regression fixtures.
THREAD_A = "00000000-0000-4000-8000-000000000101"
THREAD_B = "00000000-0000-4000-8000-000000000102"


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def library(self):
        library = Library(self.root)
        library.refresh()
        return library

    def test_archived_notes_stay_readable_but_do_not_supply_current_search_or_projects(self):
        self.write("10 项目/热血合服/当前记录.md", "# 热血合服\n\n已确认按地区分组，仍需核对候选服务器名单，保留排除原因。\n")
        self.write("90 历史/旧决策.md", "# Hell Asylum\n\n历史验收暗号 XYZZ742：已完成旧版交付并等待当年验收，不能代表最新进度。\n")
        library = self.library()
        overview = library.overview()
        self.assertEqual(1, overview["note_count"])
        self.assertEqual(1, overview["archive_count"])
        self.assertEqual(["热血合服"], [p["title"] for p in library.projects()])
        self.assertFalse(any("90 历史" in note["relative"] for note in overview["recent"]))
        self.assertEqual(0, library.search("Hell Asylum XYZZ742")["total"])
        snapshot = library.export_snapshot()
        self.assertEqual(2, len(snapshot["notes"]))
        archived = next(n for n in snapshot["notes"] if n["archived"])
        self.assertIn("XYZZ742", library.get_note(archived["id"])["markdown"])
        source = next(p for p in snapshot["sources"] if p["note_id"] == archived["id"])
        self.assertTrue(source["archived"])
        self.assertFalse(source["searchable"])
        selected = library.context_sources([source["id"], archived["id"]])
        self.assertEqual([], selected["missing"])
        self.assertTrue(all(item["archived"] for item in selected["items"]))
        refresh = library.refresh()
        self.assertEqual((1, 1), (refresh["note_count"], refresh["archive_count"]))

    def test_layout_alias_redirects_note_ids_only_and_layout_change_refreshes_snapshot(self):
        old = self.write("旧目录/进展.md", "# 热血合服\n\n已确认三天登录人数直接使用，下一步保留合服名单和地区分组依据。\n")
        library = self.library()
        before = library.search("热血合服")["items"][0]
        old_note_id, old_passage_id = before["note_id"], before["id"]
        target = self.root / "10 项目/热血合服/进展.md"
        target.parent.mkdir(parents=True)
        old.rename(target)
        library.refresh()
        with self.assertRaises(KeyError):
            library.get_note(old_note_id)
        revision = library.refreshed_at
        self.write(".obsidian/knowledge-layout.json", json.dumps({
            "version": 1, "path_aliases": {
                "旧目录/进展.md": "10 项目/热血合服/进展.md",
                "越界.md": "../外部资料.md",
            }}, ensure_ascii=False))
        refreshed = library.refresh()
        self.assertTrue(refreshed["changed"])
        self.assertNotEqual(revision, library.refreshed_at)
        self.assertTrue(refreshed["warnings"])
        resolved = library.get_note(old_note_id)
        self.assertEqual("10 项目/热血合服/进展.md", resolved["relative"])
        self.assertNotEqual(old_note_id, resolved["id"])
        self.assertIn("三天登录人数直接使用", resolved["markdown"])
        with self.assertRaisesRegex(KeyError, "段落已变化"):
            library.get_note(old_passage_id)
        selected = library.context_sources([old_note_id, old_passage_id])
        self.assertEqual([old_passage_id], selected["missing"])
        self.assertEqual(resolved["id"], selected["items"][0]["id"])
        self.assertEqual({old_note_id: resolved["id"]}, library.export_snapshot()["note_aliases"])
        self.assertFalse(library.refresh()["changed"])

    def test_entry_directory_and_answer_archive_do_not_become_methods_or_project_progress(self):
        self.write("10 项目/当前.md", "# 热血合服\n\n按地区边界分组的规则已经确认，下一步补充服务器名单和排除原因。\n")
        self.write("00 入口/项目导航.md", "# 热血合服\n\n导航示例法 XYZN111：已完成所有分组并交付，后续可从目录继续阅读项目资料。\n")
        self.write("30 资料/回答留档.md", "---\ntype: answer_archive\n---\n# 热血合服\n\n问答留档法 XYZN222：已完成所有分组并交付，这份回答不能取代真实项目进展。\n")
        self.write("10 项目/热血合服/项目概览.md", "---\ntype: navigation\n---\n# 热血合服\n\n项目导航法 NAVTYPE739：已完成全部检查，打开专题查看具体依据。\n")
        self.write("40 日常/模板/记录.md", "---\ntype: template\n---\n# 工作记录\n\n模板占位法 TMPLTYPE739：在这里填写实际完成结果和下一步。\n")
        library = self.library()
        self.assertEqual(0, library.search("NAVTYPE739")["total"])
        self.assertEqual(0, library.search("TMPLTYPE739")["total"])
        self.assertEqual(0, library.search("XYZN111")["total"])
        self.assertEqual(0, library.search("XYZN222")["total"])
        project = library.projects()[0]
        self.assertEqual(1, project["note_count"])
        self.assertIn("补充服务器名单", project["excerpt"])
        self.assertEqual(1, len(library.overview()["recent"]))
        notes = library.export_snapshot()["notes"]
        entry = next(n for n in notes if n["relative"].startswith("00 入口/"))
        answer = next(n for n in notes if n["type"] == "answer_archive")
        self.assertTrue(entry["navigation"])
        for note in (entry, answer):
            self.assertTrue(note["maintenance"])
            self.assertFalse(note["searchable"])
            self.assertEqual(note["markdown"], library.get_note(note["id"])["markdown"])

    def test_hidden_archive_loads_only_registered_targets_and_old_note_links_remain_readable(self):
        self.write("10 项目/热血合服/排单规则.md", "# 热血合服排单规则\n\n按地区边界核对名单。\n")
        target = ".source-history/早期记录/知识库检查.md"
        self.write(target, "# 知识库检查\n\n仅供原文回查 ARCHIVEONLY739。\n")
        self.write(".source-history/未登记.md", "# 未登记\n\n不可读取 HIDDEN739。\n")
        self.write(".other/资料.md", "# 其他隐藏目录\n\n不可读取。\n")
        old = "90 历史/早期记录/知识库检查.md"
        old_archive = ".source-history/旧位置.md"
        layout = {"version": 1, "path_aliases": {
            old: target, old_archive: target, "无效.md": ".source-history/.private/笔记.md",
            "无效目录.md": ".other/资料.md", "越界.md": ".source-history/../资料.md"}}
        metadata = self.write(".obsidian/knowledge-layout.json", json.dumps(layout, ensure_ascii=False))
        library = self.library()
        self.assertEqual((1, 1), (library.overview()["note_count"], library.overview()["archive_count"]))
        self.assertEqual(0, library.search("ARCHIVEONLY739")["total"])
        encode = lambda relative: "n_" + base64.urlsafe_b64encode(relative.encode()).decode().rstrip("=")
        archived = library.get_note(encode(old))
        self.assertEqual(target, archived["relative"])
        self.assertTrue(archived["archived"])
        self.assertFalse(archived["searchable"])
        self.assertIn("ARCHIVEONLY739", library.get_note(encode(target))["markdown"])
        self.assertEqual(target, library.get_note(encode(old_archive))["relative"])
        with self.assertRaises(KeyError):
            library.get_note(encode(old) + ":s_old-paragraph")
        for relative in (".source-history/未登记.md", ".other/资料.md", ".source-history/.private/笔记.md"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                library.get_note(encode(relative))
        self.assertTrue(library.overview()["warnings"])
        self.assertTrue(next(n for n in library.export_snapshot()["notes"] if n["relative"] == target)["archived"])
        metadata.write_text('{"version":1,"path_aliases":{}}', encoding="utf-8")
        self.assertTrue(library.refresh()["changed"])
        self.assertEqual(0, library.overview()["archive_count"])
        with self.assertRaises(ValueError):
            library.get_note(encode(target))

    def test_declared_project_scope_and_activity_tokens_retrieve_topic_notes_without_repeated_project_names(self):
        self.write("10 项目/热血合服/口径.md", """---
project: 热血合服
---
# 活跃与付费口径
## 当前结论
活跃取“近3天登录用户数”，不除以3；付费另取有付费的玩家登录数。
""")
        self.write("10 项目/TopData/日报.md", """---
project: TopData
---
# 日报与月报口径
## 当前结论
最终要求保留原结构和顺序，两张运营表先展示；AI分析放最后，再列后续关注。
""")
        self.write("20 方法/知识库/迁移.md", """---
project: Obsidian 知识库
---
# 备份与迁移
换电脑时先导出迁移包，再在新电脑导入，保留笔记和增量记录，无需重新总结旧资料。
""")
        self.write("10 项目/洛克计算器/其他项目.md", """---
project: 洛克计算器
---
# 活跃口径
热血合服三天活跃不除以3只是历史参考，本篇采用其他指标，仅记录计算器的其他工作。
""")
        for number in range(4):
            self.write(f"其他主题{number}.md", f"# 其他主题{number}\n\n日报最终顺序已确认，不能据此代替其他项目的真实记录。\n")
        library = self.library()
        questions = {
            "热血合服三天活跃为什么不能除以3": "不除以3",
            "热血合服的三天活跃人数为什么不能直接除以3？": "不除以3",
            "TopData日报排列顺序": "AI分析放最后",
            "TopData日报最终采用什么顺序？": "AI分析放最后",
            "Obsidian换电脑怎么迁移": "新电脑导入",
            "Obsidian怎么迁移到新电脑？": "新电脑导入",
        }
        for question, expected in questions.items():
            with self.subTest(question=question):
                result = library.search(question)
                self.assertTrue(result["items"], result)
                self.assertIn(expected, result["items"][0]["text"])
                self.assertFalse(any("其他项目.md" in item["relative"] for item in result["items"]))
        self.assertEqual(0, library.search("TopData日报 ZXQ739 口径")["total"])
        folder_only = self.write("10 项目/TopData/指标.md", "# 指标说明\n\n复核暗号 SCOPE739：金额范围已经确认，不能混用累计与单日结果。\n")
        library.refresh()
        scoped = library.search("TopData SCOPE739")
        self.assertEqual(folder_only.name, Path(scoped["items"][0]["relative"]).name)

    def test_blank_query_returns_empty_result(self):
        self.write("资料.md", "# 热血合服\n\n已确认三天活跃字段不除以三，按服务器分组。\n")
        library = self.library()
        for query in ("", "   "):
            with self.subTest(query=query):
                result = library.search(query)
                self.assertEqual("empty", result["status"])
                self.assertEqual([], result["items"])
                self.assertEqual(0, result["total"])

    def test_question_returns_actual_project_evidence_not_navigation_or_adjacent_project(self):
        self.write("归档.md", f"""# Codex 归档
## 热血合服任务
- 线程 ID：`{THREAD_A}`
- 具体做法：先排除已合服服务器，再按地区分组；登录用户采用近3天总数，不除以3。

## 洛克计算器
洛克计算器已完成伤害计算和 Windows 安装包，接下来检查皮肤效果。

## 本地化
本地化工作台已完成八种语言翻译，保留原物理行和空中文。
""")
        self.write("使用索引.md", "# 使用索引\n\n找合服相关：搜热血合服、欧美冒险合服。\n")
        self.write("周报.md", "# 每周回顾\n\n洛克计算器已完成发布；本地化交付八语表；热血合服已完成规范。\n")
        result = self.library().search("我上次热血合服怎么做的？")
        self.assertGreater(result["total"], 0)
        self.assertIn("不除以3", result["items"][0]["text"])
        self.assertEqual("evidence_only", result["answer_status"])
        for item in result["items"]:
            self.assertNotIn("皮肤效果", item["text"])
            self.assertNotIn("八种语言", item["text"])
            self.assertNotIn("洛克计算器", item["text"])

    def test_generic_section_is_split_so_unrelated_paragraph_is_not_evidence(self):
        self.write("内容总结.md", f"""# 内容总结
## 游戏运营
合服资料保留分组边界。热血统计使用近3天登录用户数，没有除以3。

TopData已形成8项技术修复清单，仍未实施。

[热血合服](codex://threads/{THREAD_A})。
""")
        result = self.library().search("热血合服")
        self.assertIn("没有除以3", result["items"][0]["text"])
        self.assertFalse(any("TopData" in item["text"] for item in result["items"]))

    def test_thread_links_keep_actual_protocol_and_isolate_threads(self):
        self.write("线程.md", f"""# 线程
## 热血合服
[原对话](codex://thread/{THREAD_A})
已确认先核名单，再按地区做合服方案。

## 本地化
[原对话](codex://threads/{THREAD_B})
八语表已交付，下一步等待需求。
""")
        library = self.library()
        item = library.search("热血合服")["items"][0]
        self.assertEqual([THREAD_A], [link["thread_id"] for link in item["thread_links"]])
        self.assertTrue(item["thread_links"][0]["url"].startswith("codex://thread/"))
        note = library.get_note(item["id"])
        self.assertEqual(2, len(note["thread_links"]))
        self.assertIn("codex://threads/" + THREAD_B, note["markdown"])
        self.assertEqual(item["line_start"], note["focus"]["line_start"])

    def test_selected_sources_accumulate_dedupe_and_missing_are_explicit(self):
        self.write("A.md", "# A\n\n甲项目的实际决定是先验证数据，再进行发布。\n")
        self.write("B.md", "# B\n\n乙项目的实际决定是保留旧结果，等待补充输入。\n")
        library = self.library()
        notes = {note["title"]: note for note in library.overview()["recent"]}
        result = library.context_sources([notes["A"]["id"], notes["B"]["id"], notes["A"]["id"], "missing"])
        self.assertEqual(["A", "B"], [item["title"] for item in result["items"]])
        self.assertEqual(["missing"], result["missing"])
        result = library.context_sources([notes["B"]["id"]])
        self.assertEqual(["B"], [item["title"] for item in result["items"]])

    def test_all_candidates_are_counted_and_can_be_requested(self):
        for index in range(9):
            self.write(f"{index}.md", f"# 飞船项目 {index}\n\n飞船项目确认第{index}项要求，验收后交付。\n")
        library = self.library()
        preview = library.search("飞船项目", limit=4)
        full = library.search("飞船项目", limit=0)
        self.assertEqual(9, preview["total"])
        self.assertEqual(4, preview["returned"])
        self.assertTrue(preview["has_more"])
        self.assertEqual(9, len(full["items"]))
        selected = [item["id"] for item in full["items"]]
        self.assertEqual(selected, [item["id"] for item in library.context_sources(selected)["items"]])

    def test_long_note_keeps_middle_and_end_decisions_and_markdown(self):
        body = "# 火星项目\n\n首要目标：保护原数据。\n\n" + ("背景资料。\n\n" * 2000)
        body += "中段决定：不得删除空行。\n\n" + ("其他资料。\n\n" * 2000)
        body += "## 最终决定\n\n最终决定：只交付审核过的候选；尚未授权发布。\n"
        self.write("长文.md", body)
        library = self.library()
        note_id = library.overview()["recent"][0]["id"]
        source = library.context_sources([note_id], query="最终决定")["items"][0]
        self.assertEqual(body, source["text"])
        self.assertIn("中段决定：不得删除空行", source["text"])
        self.assertIn("尚未授权发布", source["text"])
        self.assertTrue(source["content_complete"])
        self.assertIn("尚未授权发布", library.search("最终决定")["items"][0]["text"])

    def test_safe_ids_excluded_hidden_and_outside_symlink(self):
        self.write("正常.md", "# 正常\n\n可读资料。\n")
        self.write(".obsidian/设置.md", "不可读")
        self.write("excluded/秘密.md", "不可读")
        library = Library(self.root, ["excluded"])
        self.assertEqual(1, library.refresh()["note_count"])
        traversal = "n_" + base64.urlsafe_b64encode(b"../outside.md").decode().rstrip("=")
        with self.assertRaises(ValueError):
            library.get_note(traversal)
        hidden = "n_" + base64.urlsafe_b64encode(".obsidian/设置.md".encode()).decode().rstrip("=")
        with self.assertRaises(ValueError):
            library.get_note(hidden)
        with self.assertRaises(ValueError):
            library.get_note("n_invalid%")

    def test_refresh_exposes_new_notes_and_keeps_source_ids_stable(self):
        self.write("原始.md", "# 原始\n\n旧有内容。\n")
        library = self.library()
        self.assertEqual(library.overview()["refreshed_at"], library.refreshed_at)
        original_id = library.overview()["recent"][0]["id"]
        self.write("新增.md", "# 新增\n\n正文独有句子：黄昏航行指引。\n")
        self.assertEqual(2, library.refresh()["note_count"])
        self.assertEqual(original_id, library.get_note(original_id)["id"])
        self.assertIn("黄昏航行指引", library.search("黄昏航行")["items"][0]["text"])
        self.assertEqual(2, len(library.overview()["recent"]))

    def test_projects_have_evidence_ids_but_no_inferred_progress(self):
        self.write("热血.md", f"""# 热血合服
## 本次方案
已确认分组采用地区边界，仍需要补当前候选服务器名单。

[继续原对话](codex://threads/{THREAD_A})
""")
        self.write("自动总结流程.md", "# 自动总结流程\n\nObsidian更新先读取检查点。\n")
        library = self.library()
        projects = library.projects()
        self.assertEqual(["热血合服"], [item["title"] for item in projects])
        detail = library.get_project(projects[0]["id"])
        self.assertEqual("evidence_only", detail["status"])
        self.assertTrue(detail["items"])
        self.assertEqual(detail["source_ids"], [item["id"] for item in detail["items"]])
        self.assertNotIn("自动总结流程", [item["title"] for item in library.overview()["recent"]])

    def test_resume_references_do_not_replace_project_progress_and_resume_aliases_find_it(self):
        self.write("本地化进展.md", """---
date: 2026-10-01
---
# 本地化
已确认按实体 ID 区分中文重名，保留原物理行和空中文，下一步等待需求确认。
""")
        self.write("计算器发布.md", """---
date: 2026-10-02
---
# 洛克计算器
桌面 1.0.1 同版本安装包已替换并核对下载，旧包保留回滚，尚未验证完整安装卸载。
""")
        self.write("package_resume.md", """---
date: 2026-10-20
---
# package_resume
## 面试材料阅读顺序与口径限制
本地化履历用于面试背景介绍，只能引用已有交付记录，不能写成这次新增项目成果。

## 版本选择与使用决定
示例洛克项目岗位定制稿仅用于对应岗位历史参考，不作为当前通用简历。

## 投递材料
求职投递优先使用单页 PDF，双页 PDF 用于详细阅读，TXT 用于在线表单，个人主页保留材料入口。
""")
        library = self.library()
        projects = {project["title"]: project for project in library.projects()}
        for title, expected in (("本地化", "按实体 ID"), ("洛克计算器", "1.0.1")):
            with self.subTest(project=title):
                detail = library.get_project(projects[title]["id"])
                self.assertFalse(any(item["note_title"] == "package_resume"
                                     for item in detail["items"]))
                self.assertIn(expected, projects[title]["excerpt"])
        with self.subTest(project="简历与求职"):
            self.assertIn("简历与求职", projects)
        for query in ("简历", "求职", "resume", "个人主页", "简历怎么投递"):
            with self.subTest(query=query):
                result = library.search(query)
                self.assertGreater(result["total"], 0)
                self.assertEqual("简历与求职", result["items"][0]["project"])
                self.assertEqual("package_resume", result["items"][0]["note_title"])
                if query == "简历怎么投递":
                    self.assertIn("单页 PDF", result["items"][0]["text"])

    def test_comparison_only_mentions_do_not_become_another_projects_progress(self):
        self.write("真实进展.md", """---
date: 2026-10-01
---
# 项目记录
## Hell Asylum
示例译文已完成校审，修复页保留三项测试记录，仍需人工确认后再发布。

## TopData
已完成数据查询接口的本轮修复，仍需用户确认验收结果。
""")
        self.write("定位线程.md", """---
date: 2026-10-20
---
# 定位示例翻译线程
定位测试翻译对话，避免与相似标题或 Hell Asylum 校审任务混淆。
""")
        self.write("资料校对.md", """---
date: 2026-10-20
---
# 本次资料校对
确认本轮要查的稿件，不要跟 TopData 旧任务混为一谈。
""")
        self.write("实际边界.md", """---
date: 2026-10-02
---
# Hell Asylum
避免与本地化任务混淆，本项目校审已完成，尚未发布。
""")
        self.write("后续安排.md", """---
date: 2026-10-03
---
# 后续安排
避免与 Hell Asylum 旧任务混淆；Hell Asylum 当前交付页已确认，尚未发布，还需用户验收。
""")
        library = self.library()
        projects = {project["title"]: project for project in library.projects()}
        for title in ("Hell Asylum", "TopData"):
            with self.subTest(project=title):
                detail = library.get_project(projects[title]["id"])
                titles = {item["note_title"] for item in detail["items"]}
                self.assertFalse(titles.intersection({"定位示例翻译线程", "本次资料校对"}))
                self.assertIn("项目记录", titles)
                if title == "Hell Asylum":
                    self.assertIn("Hell Asylum", titles)
                    self.assertIn("后续安排", titles)
                    self.assertIn("尚未发布", projects[title]["excerpt"])
        references = library.search("相似标题")["items"]
        self.assertTrue(references)
        note = library.get_note(references[0]["note_id"])
        self.assertEqual("定位示例翻译线程", note["title"])
        self.assertIn("Hell Asylum 校审任务混淆", note["markdown"])

    def test_compound_package_question_keeps_result_table_and_delivery_boundary(self):
        body = """# 整理简历求职资料包：新增进展
### 新增需求
本轮围绕将示例资料包拆成低于 12 MiB、可独立解压的小包，并保存至测试资料库展开。

### 实际结果
据本轮测试交付记录，已生成并上传四个独立 ZIP：

| 内容 | 大小 | 示例附件 ID |
|---|---:|---|
| 简历与面试 | 3.000 MiB | fixture_attachment_a |
| 新主页离线版 | 2.000 MiB | fixture_attachment_b |
| 新主页源码 | 4.000 MiB | fixture_attachment_c |
| 旧简历主页 | 1.000 MiB | fixture_attachment_d |

### 未完成
四个附件已报告保存至测试资料库，但尚待实际发送给测试收件人；材料没有发送完成记录。
"""
        self.write("新增进展.md", body)
        self.write("跨项目归档.md", """# 跨项目归档
## 简历与求职
### 新增需求
资料包拆成小包，并核实是否发送给用户。

### 实际结果
| 项目 | 实际结果 |
|---|---|
| 简历 | 已上传 |
| Hell Asylum | 无关项目秘密材料 |
""")
        library = self.library()
        result = library.search("简历求职资料包拆成了哪些小包？是否已经发送给用户？", 6)
        text = "\n".join(item["text"] for item in result["items"])
        for expected in ("简历与面试", "新主页离线版", "新主页源码", "旧简历主页", "尚待实际发送给测试收件人"):
            self.assertIn(expected, text)
        self.assertNotIn("无关项目秘密材料", text)
        supplements = [item for item in result["items"] if item["kind"] == "note"]
        self.assertEqual(1, len(supplements))
        supplement = supplements[0]
        self.assertNotEqual(supplement["id"], result["items"][0]["id"])
        self.assertEqual("整理简历求职资料包：新增进展", supplement["title"])
        self.assertEqual(body, supplement["text"])
        self.assertEqual(body, library.get_note(supplement["id"])["markdown"])
        self.assertEqual(body, library.context_sources([supplement["id"]])["items"][0]["text"])
        self.write("新增进展.md", body + "\n" + "无关背景资料。" * 2000)
        library.refresh()
        limited = library.search("简历求职资料包拆成了哪些小包？是否已经发送给用户？", 6)
        self.assertFalse(any(item["kind"] == "note" for item in limited["items"]))

    def test_snapshot_preserves_ids_body_and_links_without_reading_link_targets(self):
        body = f"# 火星项目\n\n结尾决定：保留原件。\n\n[原对话](codex://threads/{THREAD_A})\n"
        self.write("资料.md", body)
        library = self.library()
        snapshot = library.export_snapshot()
        self.assertEqual(body, snapshot["notes"][0]["markdown"])
        source_ids = [item["id"] for item in snapshot["sources"]]
        local = library.context_sources(source_ids)
        self.assertEqual(source_ids, [item["id"] for item in local["items"]])
        self.assertEqual([], local["missing"])
        self.assertEqual(THREAD_A, snapshot["notes"][0]["thread_links"][0]["thread_id"])
        self.assertNotIn("passages", snapshot["notes"][0])

    def test_hidden_task_comments_do_not_create_projects_or_search_evidence(self):
        body = f"""# 下批方案接续

热血合服已确认按地区和活跃人数分组，下一步补充当前候选服务器名单。

<!--
## Obsidian 知识库
隐藏资料不能作为项目证据。[错误原对话](codex://threads/{THREAD_B})
-->

已确认名单必须保留排除原因，热血合服执行前还需核对各组服务器明细。

<!-- obsidian-workspace task:{THREAD_A} -->
"""
        self.write("接续.md", body)
        library = self.library()
        self.assertEqual(["热血合服"], [item["title"] for item in library.projects()])
        self.assertEqual(0, library.search("obsidian-workspace")["total"])
        self.assertEqual(0, library.search("隐藏资料")["total"])
        note_id = library.overview()["recent"][0]["id"]
        note = library.get_note(note_id)
        self.assertEqual(body, note["markdown"])
        self.assertEqual(body, library.context_sources([note_id])["items"][0]["text"])
        self.assertEqual([], note["thread_links"])
        self.assertEqual(2, len(note["passages"]))
        expected_line = body.splitlines().index(
            "已确认名单必须保留排除原因，热血合服执行前还需核对各组服务器明细。"
        ) + 1
        self.assertEqual(expected_line, note["passages"][1]["line_start"])
        for passage in note["passages"]:
            self.assertNotIn("<!--", passage["text"])
            self.assertNotIn("Obsidian", passage["section"])
            self.assertNotIn("obsidian-workspace", passage["excerpt"])

    def test_specific_intent_is_required_inside_project_and_unknown_id_stays_empty(self):
        self.write("本地化.md", "# 本地化\n\n工作台已完成翻译交付，ID 保持原值。\n")
        self.write("咖啡.md", "# 咖啡研究\n\n咖啡机发布步骤已经记录，保留历史来源。\n")
        self.write("发布记录.md", "# 其他发布\n\n最近做过多轮发布核查，并保留3.0版本文件。\n")
        library = self.library()
        self.assertEqual(0, library.search("本地化术语重名怎么查，哪些ID需要区分？")["total"])
        self.assertEqual(0, library.search("银杉咖啡机 ZXQ739 项目的发布流程是什么？")["total"])
        self.assertEqual(0, library.search("我之前有没有做过火星农场3.0的发布？")["total"])
        self.write("命名规则.md", "# 本地化\n\n技能名重名需按实体 ID 区分，不能把不同技能合成同一条术语。\n")
        library.refresh()
        self.assertIn("实体 ID", library.search("翻译技能名时，中文撞名要怎么处理？")["items"][0]["text"])

    def test_paraphrase_retrieves_same_merge_evidence_and_common_verb_does_not_change_subject(self):
        self.write("合服.md", "# 热血合服\n\n先核对合服名单，再按地区分组；保留排除原因。\n")
        self.write("无关.md", "# 其他项目\n\n发布前检查网页布局，检查语言，检查窗口大小。\n")
        library = self.library()
        direct = library.search("热血合服先后步骤是什么？")["items"]
        paraphrase = library.search("热血服务器合并按什么顺序操作？")["items"]
        self.assertEqual([x["id"] for x in direct], [x["id"] for x in paraphrase])
        self.assertFalse(any("网页布局" in x["text"] for x in library.search("合服发布前检查什么？")["items"]))

    def test_release_question_prefers_installer_evidence_to_desktop_layout_or_plan(self):
        self.write("发布.md", """# 洛克计算器
## 历史发布
桌面 1.0.1：Release 同版本安装包已替换、下载核对，旧包保留回滚。

## 后续计划
计划构建 Windows 安装包，尚未发布。

## 小程序布局
小程序已完成桌面式布局，交付文件并通过发布门禁，尚未上传。
""")
        items = self.library().search("洛克计算器之前 Windows 发布交付哪些文件？")["items"]
        self.assertIn("1.0.1", items[0]["text"])
        self.assertFalse(any("桌面式布局" in item["text"] for item in items))

    def test_three_day_activity_question_matches_recorded_login_metric(self):
        self.write("合服口径.md", """# 热血合服
活跃取的是原始CSV里的近3天登录用户数，直接使用该字段，没有除以3，
也没有使用战力或付费字段。单服平均活跃为所有入单服务器近3天登录用户数之和除以入单服务器数。
""")
        self.write("其他统计.md", "# 其他统计\n\n人数为已登记总数，不能直接相加。\n")
        library = self.library()
        for question in (
            "热血合服的三天活跃人数为什么不能直接除以3？",
            "热血合服近3天活跃用户数为何不能除以3？",
        ):
            with self.subTest(question=question):
                result = library.search(question)
                self.assertGreater(result["total"], 0)
                self.assertIn("没有除以3", result["items"][0]["text"])

    def test_newly_imported_workspace_guide_answers_incremental_continuation_question(self):
        self.write("新增资料/USER_GUIDE.md", """# USER_GUIDE
已收录用户提供的使用说明。

## 收录原文

# 个人知识工作台：从找回做法到继续工作

## 更新实际做什么

默认只处理原范围里的新增文件、新出现的飞书文档入口，以及已有 Codex 对话中新完成的轮次。
已总结的旧文件跳过；不会因修改时间变化重新总结旧正文。
线程续聊使用原有检查点继续，未完成、读取失败或截断的轮次不登记成完成。
""")
        self.write("历史索引.md", "# Obsidian 知识库\n\n增量整理报告已经汇总，重复文件后续检查。\n")
        result = self.library().search("Obsidian 增量整理怎样避免重复总结，续聊怎么更新？")
        self.assertGreater(result["total"], 0)
        self.assertIn("旧文件跳过", result["items"][0]["text"])
        self.assertIn("原有检查点", result["items"][0]["text"])

    def test_guides_remain_searchable_without_becoming_project_progress(self):
        self.write("进展.md", """---
date: 2026-10-01
---
# 已确认进展
## 热血合服
已确认合服分组采用地区边界，仍需补充下一批服务器名单。

## Obsidian 知识库
### 资料入口
本地：桌面、下载、文档和Obsidian既有笔记，可由这里继续阅读。

### 本次完成边界
Obsidian 已完成本轮文件归档并保留失败原因，未移动或删除原件。
""")
        self.write("新增资料/USER_GUIDE -- imported.md", """# USER_GUIDE
## 准备项目接续
例如“沿用热血合服口径”，从搜索结果中选择资料，再点击准备接续。

# 个人知识工作台
## 更新实际做什么
默认只整理新增文件。已总结的旧文件跳过；线程续聊沿用检查点，未完成轮次不登记成功。
""")
        library = self.library()
        projects = {p["title"]: p for p in library.projects()}
        self.assertIn("分组采用地区边界", projects["热血合服"]["excerpt"])
        self.assertIn("已完成本轮文件归档", projects["Obsidian 知识库"]["excerpt"])
        self.assertEqual("2026-10-01", projects["热血合服"]["latest_at"])
        self.assertEqual("2026-10-01", projects["Obsidian 知识库"]["latest_at"])
        for project in projects.values():
            self.assertFalse(any("USER_GUIDE" in library.get_note(sid)["title"]
                                 for sid in project["source_ids"]))
        result = library.search("Obsidian 增量整理怎样避免重复总结，续聊怎么更新？")
        self.assertIn("旧文件跳过", result["items"][0]["text"])

    def test_subject_catalog_lists_knowledge_without_templates_navigation_or_source_receipts(self):
        self.write("10 项目/热血合服/热血合服排单.md", "# 热血合服排单\n\n按地区分组，保留排除原因。\n\n## 来源\n\n依据另一篇记录。\n")
        self.write("20 方法/知识库/知识库换机迁移.md", "# 知识库换机迁移\n\n先导出，再在新电脑导入。\n")
        self.write("30 资料/个人记录/学历认证材料.md", "# 学历认证材料\n\n成绩单已备份，申请尚未提交。\n")
        self.write("30 资料/待归类/文件登记.md", "# 文件登记\n\n仅收录来源，尚未提取此格式正文。\n")
        self.write("10 项目/热血合服/热血合服.md", "---\ntype: navigation\n---\n# 热血合服\n\n项目入口。\n")
        self.write("40 日常/模板/项目笔记模板.md", "# {{title}}\n\n填入结论。\n")
        self.write("90 历史/旧记录.md", "# 旧记录\n\n过去的记录。\n")
        library = self.library()
        overview = library.overview()
        self.assertEqual(3, overview["knowledge_count"])
        self.assertEqual({"项目", "方法", "资料"}, {n["category"] for n in overview["topics"]})
        topic = next(n for n in overview["topics"] if n["category"] == "项目")
        self.assertEqual("热血合服", topic["group"])
        self.assertEqual("按地区分组，保留排除原因。", topic["excerpt"])
        self.assertIn("排单", library.get_note(topic["id"])["title"])

    def test_compound_question_keeps_distinct_evidence_and_home_skips_placeholders(self):
        self.write("日报.md", "# Codex Daily Review\n\n" + "\n\n".join(
            f"昨日要点：第{i}项交付完成，项目成果已经核实。日报已推送。" for i in range(8)))
        self.write("规则.md", "# 归档边界\n\n自动运行与项目成果分开统计，不能把自动任务当成人工完成。\n")
        self.write("导航.md", "# 视频知识库\n\n继续做事 · 查看主题总结 · 看自动任务怎么跑 · 看本次读到了什么\n")
        self.write("来源占位.md", """# 星河课程第二章实践笔记

本条仅收录元数据，未读取或总结正文。

- 文档更新时间：2025-01-02T03:04:05+00:00

[打开飞书原文](https://example.feishu.cn/docx/fixture-course)
""")
        library = self.library()
        items = library.search("Codex每日自动报告统计哪一天，怎么区分自动运行与项目成果？", 6)["items"]
        self.assertTrue(any("不能把自动任务" in item["text"] for item in items))
        self.assertFalse(any("星河课程" in item["title"] for item in library.overview()["recent"]))
        self.assertFalse(any("继续做事" in item["excerpt"] for item in library.projects()))
        self.assertFalse(any(item["title"] == "视频知识库" for item in library.projects()))
        sources = library.search("星河课程")["items"]
        self.assertTrue(sources)
        note = library.get_note(sources[0]["note_id"])
        self.assertIn("2025-01-02T03:04:05+00:00", note["markdown"])
        self.assertIn("https://example.feishu.cn/docx/fixture-course", note["markdown"])


if __name__ == "__main__":
    unittest.main()
