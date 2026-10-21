import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from engine.ingest import IngestError, extract_path, extract_text, extract_upload, safe_title, write_note


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_upload_extracts_real_bytes_and_retains_long_tail(self):
        text = "开头\n" + "中段决定必须保留。\n" * 200 + "末尾最终决定：保持原权限。"
        result = extract_upload("资料.md", text.encode("utf-8-sig"))
        self.assertEqual(result["text"], text)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["source"]["kind"], "upload")
        with self.assertRaises(IngestError):
            extract_upload("only-name.md", {"name": "only-name.md", "size": 20})
        with self.assertRaises(IngestError):
            extract_upload("unknown.txt", b"\x81\x82\x83")

    def test_previous_text_source_extensions_still_extract_actual_content(self):
        for extension in ("rst", "csv", "html", "xml", "py", "js", "ts", "ps1", "css", "bat", "cmd"):
            with self.subTest(extension=extension):
                path = self.root / ("source." + extension)
                path.write_text("具体决定与结尾条件", encoding="utf-8")
                result = extract_path(path)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["text"], "具体决定与结尾条件")

    def test_markdown_upload_uses_first_h1_and_retains_original_source(self):
        text = "说明\n\n## 二级标题\n\n# 个人知识工作台使用指南 ###\n\n# 后续章节\n"
        for extension in ("md", "markdown"):
            with self.subTest(extension=extension):
                filename = "USER_GUIDE." + extension
                result = extract_upload(filename, text.encode("utf-8"))
                self.assertEqual(result["title"], "个人知识工作台使用指南")
                self.assertEqual(result["source"]["name"], filename)
                self.assertEqual(result["text"], text)

    def test_markdown_title_ignores_fenced_examples_and_falls_back_safely(self):
        for fence in ("```", "~~~~"):
            with self.subTest(fence=fence):
                text = f"{fence}markdown\n# 示例里的假标题\n{fence}\n\n# 实际使用指南\n"
                self.assertEqual(extract_upload("USER_GUIDE.md", text.encode("utf-8"))["title"], "实际使用指南")
        for text in ("没有一级标题", "## 只有二级标题", "```\n# 未闭合的代码\n", "# ../../outside\n", "# C:\\outside\n"):
            with self.subTest(text=text):
                self.assertEqual(extract_upload("USER_GUIDE.md", text.encode("utf-8"))["title"], "USER_GUIDE")
        self.assertEqual(extract_upload("USER_GUIDE.txt", b"# Different title")["title"], "USER_GUIDE")

    def test_docx_main_text_and_table_content_are_in_document_order(self):
        stream = io.BytesIO()
        xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>首段</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格关键决定</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:p><w:r><w:t>末尾条件</w:t></w:r></w:p></w:body></w:document>'
        with zipfile.ZipFile(stream, "w") as package:
            package.writestr("word/document.xml", xml)
        result = extract_upload("方案.docx", stream.getvalue())
        self.assertEqual(result["text"], "首段\n表格关键决定\n末尾条件")
        self.assertEqual(result["status"], "ready")

    def pdf(self, *, blank=False):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        writer = PdfWriter()
        page = writer.add_blank_page(width=400, height=400)
        if not blank:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            content = DecodedStreamObject()
            content.set_data(b"BT /F1 12 Tf 20 200 Td (Decision at the final page.) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(content)
        stream = io.BytesIO()
        writer.write(stream)
        return stream.getvalue()

    def test_text_pdf_is_extracted_and_scans_are_not_claimed_complete(self):
        result = extract_upload("text.pdf", self.pdf())
        self.assertIn("Decision at the final page.", result["text"])
        self.assertEqual(result["status"], "ready")
        blank = extract_upload("scan.pdf", self.pdf(blank=True))
        self.assertEqual(blank["status"], "no_text_layer")
        self.assertEqual(blank["text"], "")
        self.assertEqual(extract_upload("table.xlsx", b"real bytes")["status"], "unsupported")

    def test_sources_cannot_escape_scope_or_use_metadata_as_text(self):
        source = self.root / "input.txt"
        source.write_text("真实文字", encoding="utf-8")
        self.assertEqual(extract_path(source, allowed_roots=[self.root])["text"], "真实文字")
        with self.assertRaises(IngestError):
            extract_path(source, allowed_roots=[self.root / "different"])
        for filename in ("../secret.txt", "C:\\secret.txt", "nested/file.txt"):
            with self.assertRaises(IngestError):
                extract_upload(filename, b"bytes")
        with self.assertRaises(IngestError):
            extract_text({"filename": "wrong"})

    def test_safe_new_note_atomic_readback_and_retry_do_not_overwrite(self):
        args = (self.root / "notes", "方案: A/B", "# 已完成\n\n正文和结论。", "task-123", ["file:source.md"])
        first = write_note(*args)
        second = write_note(*args)
        self.assertTrue(first["created"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["note"], second["note"])
        self.assertEqual(Path(first["note"]).read_text(encoding="utf-8"), first["expected_text"])
        self.assertIn("file:source.md", first["expected_text"])
        Path(first["note"]).write_text("# 人工补充\n不要覆盖", encoding="utf-8")
        with self.assertRaises(IngestError):
            write_note(*args)
        self.assertIn("人工补充", Path(first["note"]).read_text(encoding="utf-8"))
        self.assertEqual(len(list((self.root / "notes").glob("*.md"))), 1)

    def test_crlf_upload_creates_lf_note_and_preserves_original_bytes(self):
        original = "首段：保留原文件。\r\n\r\n末尾决定：只整理新增内容。\r\n".encode("utf-8")
        upload = self.root / "upload.txt"
        upload.write_bytes(original)
        source = extract_upload(upload.name, upload.read_bytes())
        self.assertEqual(source["text"], original.decode("utf-8"))
        markdown = "# 已整理\n\n摘要使用 LF。\r旧式换行也保留为段落。\n\n## 收录原文\n\n" + source["text"]
        first = write_note(self.root / "notes", "CRLF 上传", markdown, "crlf-task", [upload.name])
        saved = Path(first["note"]).read_bytes()
        self.assertNotIn(b"\r", saved)
        self.assertEqual(saved.decode("utf-8"), first["expected_text"])
        self.assertIn("末尾决定：只整理新增内容。\n", first["expected_text"])
        self.assertEqual(upload.read_bytes(), original)
        retry = write_note(self.root / "notes", "CRLF 上传", markdown, "crlf-task", [upload.name])
        self.assertTrue(retry["reused"])
        self.assertEqual(retry["note"], first["note"])

    def test_traversal_empty_and_failed_publish_never_produce_note(self):
        for title in ("../../outside", "C:\\outside", "/outside"):
            with self.assertRaises(IngestError):
                write_note(self.root / "notes", title, "正文", "task")
        with self.assertRaises(IngestError):
            write_note(self.root / "notes", "标题", "正文", "../task")
        with self.assertRaises(IngestError):
            write_note(self.root / "notes", "标题", "   ", "task")
        with patch("engine.ingest.os.link", side_effect=OSError("injected publish failure")):
            with self.assertRaises(OSError):
                write_note(self.root / "notes", "标题", "正文", "task")
        self.assertEqual(list((self.root / "notes").glob("*.md")), [])
        self.assertEqual(list((self.root / "notes").glob("*.tmp")), [])
        self.assertEqual(safe_title("CON"), "资料 CON")

    def test_semantic_names_collide_safely_and_title_or_folder_change_reuses_identity(self):
        notes = self.root / "notes"
        task_id = "11111111-2222-4333-8444-555555555555"
        markdown = "# 热血合服验收 " + task_id + "\n\n验收需要先补齐七天活跃数据。"
        first = write_note(notes, "归档资料", markdown, task_id, folder="热血合服")
        second = write_note(notes, "归档资料", markdown, "different-task", folder="热血合服")
        self.assertEqual(Path(first["note"]).name, "热血合服验收.md")
        self.assertEqual(Path(second["note"]).name, "热血合服验收（2）.md")
        self.assertIn("<!-- obsidian-workspace task:" + task_id, first["expected_text"])
        self.assertNotIn(task_id, first["expected_text"].split("-->\n\n", 1)[1])
        retried = write_note(notes, "另一个原名", markdown, task_id, folder="待归类")
        self.assertEqual(retried["note"], first["note"])
        self.assertTrue(retried["reused"])

    def test_reserved_filename_survives_failed_publish_and_other_same_title_task(self):
        notes = self.root / "notes"
        with patch("engine.ingest.os.link", side_effect=OSError("publication interrupted")):
            with self.assertRaises(OSError):
                write_note(notes, "具体方法", "正文", "original-task")
        other = write_note(notes, "具体方法", "不同正文", "another-task")
        retry = write_note(notes, "具体方法", "正文", "original-task")
        self.assertEqual(Path(other["note"]).name, "具体方法（2）.md")
        self.assertEqual(Path(retry["note"]).name, "具体方法.md")

    def test_moved_legacy_note_is_read_only_reused_without_visible_identity(self):
        vault = self.root / "vault"
        history = vault / ".source-history"
        history.mkdir(parents=True)
        original = history / "早期验收.md"
        text = "<!-- obsidian-workspace task:legacy-task -->\n\n# 早期验收\n\n等待实际验收。\n\n## 来源\n\n- file:original.md\n"
        original.write_text(text, encoding="utf-8")
        unrelated = vault / ".other" / "不可恢复.md"
        unrelated.parent.mkdir()
        unrelated.write_text(text, encoding="utf-8")
        result = write_note(vault / "30 资料", "早期验收", "# 早期验收\n\n等待实际验收。",
                            "legacy-task", ["file:original.md"], folder="待归类", identity_root=vault)
        self.assertEqual(Path(result["note"]), original.resolve())
        self.assertEqual(result["expected_text"], text)
        self.assertTrue(result["reused"])
        self.assertEqual(list((vault / "30 资料").rglob("*.md")), [])
        original.write_text("# 人工重写\n必须保留。", encoding="utf-8")
        with self.assertRaises(IngestError) as error:
            write_note(vault / "30 资料", "早期验收", "# 早期验收\n\n等待实际验收。",
                       "legacy-task", ["file:original.md"], identity_root=vault)
        self.assertEqual(error.exception.code, "output_conflict")
        index = vault / "30 资料" / ".note-index.json"
        saved = json.loads(index.read_text(encoding="utf-8"))
        for unsafe in (".other/不可恢复.md", ".source-history/.private/笔记.md", ".source-history/../其他.md"):
            saved["tasks"]["legacy-task"]["path"] = unsafe
            index.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
            with self.subTest(path=unsafe), self.assertRaises(IngestError) as error:
                write_note(vault / "30 资料", "早期验收", "正文", "legacy-task", identity_root=vault)
            self.assertEqual(error.exception.code, "invalid_note_index")

    def test_sources_keep_targets_behind_readable_labels_and_deleted_notes_are_not_regenerated(self):
        source = self.root / "验收数据.txt"
        result = write_note(self.root / "notes", "验收方法", "验收需要补齐数据。", "sources-task", [str(source)])
        self.assertIn("[验收数据](<", result["expected_text"])
        self.assertIn(source.as_uri(), result["expected_text"])
        self.assertNotIn("- " + str(source), result["expected_text"])
        Path(result["note"]).unlink()
        with self.assertRaises(IngestError) as error:
            write_note(self.root / "notes", "验收方法", "验收需要补齐数据。", "sources-task", [str(source)])
        self.assertEqual(error.exception.code, "missing_output")


if __name__ == "__main__":
    unittest.main()
