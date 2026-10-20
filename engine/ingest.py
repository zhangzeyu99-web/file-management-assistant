"""Actual uploaded bytes/text extraction and append-only Markdown delivery."""
from __future__ import annotations

import io
import os
import re
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from .incremental import IncrementalError, writer_lock


class IngestError(ValueError):
    def __init__(self, message, code="invalid_input"):
        super().__init__(message)
        self.code = code


MAX_BYTES = 32 * 1024 * 1024
MAX_CHARS = 2_000_000
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".csv", ".html", ".xml",
                   ".py", ".js", ".ts", ".ps1", ".css", ".bat", ".cmd"}
SUPPORTED = {**{extension: "text" for extension in TEXT_EXTENSIONS},
             ".md": "markdown", ".markdown": "markdown", ".docx": "docx", ".pdf": "pdf"}


def _filename(value):
    if not isinstance(value, str) or not value or value in (".", "..") or re.search(r"[\\/:\x00-\x1f]", value):
        raise IngestError("上传必须提供文件名，不能包含目录或路径穿越。", "unsafe_filename")
    return value


def safe_title(value):
    value = str(value or "新资料").strip()
    if re.search(r"(^|[\\/])\.\.([\\/]|$)", value) or re.match(r"^(?:[A-Za-z]:|[\\/])", value):
        raise IngestError("标题不能是路径。", "unsafe_title")
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")[:80] or "新资料"
    if re.fullmatch(r"(?i)(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", value):
        value = "资料 " + value
    return value


def _check_text(text):
    if not isinstance(text, str):
        raise IngestError("必须提供实际文字。")
    if len(text) > MAX_CHARS:
        raise IngestError("文本超过单次处理上限，未截断、未登记。", "too_large")
    if "\x00" in text or "\ufffd" in text:
        raise IngestError("文本包含编码异常，请提供有效 UTF-8/UTF-16 文本。", "invalid_encoding")
    return text


def _markdown_title(text, fallback):
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker and (marker[1][0] != "`" or "`" not in marker[2]):
            fence = marker[1]
            continue
        heading = re.match(r"^ {0,3}#[ \t]+(.+?)\s*$", line)
        if not heading:
            continue
        title = re.sub(r"[ \t]+#+[ \t]*$", "", heading[1]).strip()
        if not title:
            continue
        try:
            return safe_title(title)
        except IngestError:
            return fallback
    return fallback


def extract_text(text, title="新资料"):
    text = _check_text(text)
    return {"text": text, "title": safe_title(title), "format": "text", "status": "ready" if text.strip() else "empty",
            "warnings": [], "source": {"kind": "text"}}


def _docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            if sum(row.file_size for row in package.infolist()) > 64 * 1024 * 1024:
                raise IngestError("DOCX 解压内容超过单次处理上限。", "too_large")
            xml = package.read("word/document.xml")
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise IngestError("DOCX 正文含不支持的实体定义。", "invalid_docx")
        root = ElementTree.fromstring(xml)
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        lines = []
        for paragraph in root.iter(ns + "p"):
            parts = []
            for node in paragraph.iter():
                if node.tag == ns + "t":
                    parts.append(node.text or "")
                elif node.tag == ns + "tab":
                    parts.append("\t")
                elif node.tag in (ns + "br", ns + "cr"):
                    parts.append("\n")
            lines.append("".join(parts))
        return "\n".join(lines), ["已提取正文与表格文字；图片、批注和附件未识别。"]
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, RuntimeError) as error:
        raise IngestError("无法读取 DOCX 正文。", "invalid_docx") from error


def _pdf(data):
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise IngestError("尚未安装 PDF 文本提取依赖 pypdf。", "dependency_missing") from error
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise IngestError("PDF 已加密，未提取正文。", "encrypted_pdf")
        if len(reader.pages) > 500:
            raise IngestError("PDF 页数超过单次处理上限，未截断。", "too_large")
        pages = [page.extract_text() or "" for page in reader.pages]
    except IngestError:
        raise
    except Exception as error:
        raise IngestError("无法读取 PDF 文本层。", "invalid_pdf") from error
    missing = [str(i + 1) for i, text in enumerate(pages) if not text.strip()]
    warnings = ["仅提取 PDF 文本层，未识别图片和扫描页。"]
    if missing:
        warnings.append("无可提取文字的页：" + "、".join(missing))
    text = "\n\n".join(pages)
    status = "no_text_layer" if not text.strip() else "partial" if missing else "ready"
    return text, warnings, status


def extract_upload(filename, data, *, max_bytes=MAX_BYTES):
    filename = _filename(filename)
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise IngestError("上传必须包含真实文件字节，文件名和元数据不能代替内容。", "missing_bytes")
    data = bytes(data)
    if len(data) > max_bytes:
        raise IngestError("文件超过单次处理上限，未读取、未登记。", "too_large")
    suffix = Path(filename).suffix.lower()
    result = {"text": "", "title": safe_title(Path(filename).stem), "format": SUPPORTED.get(suffix, "unsupported"),
              "status": "ready", "warnings": [], "source": {"kind": "upload", "name": filename, "size": len(data)}}
    if suffix not in SUPPORTED:
        return {**result, "status": "unsupported", "warnings": ["此格式尚未自动提取正文，可保留来源或使用对应专项流程。"]}
    if suffix in TEXT_EXTENSIONS:
        encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        try:
            result["text"] = data.decode(encoding)
        except UnicodeError as error:
            raise IngestError("无法按 UTF-8/带 BOM 的 UTF-16 解码；未猜测转码。", "invalid_encoding") from error
    elif suffix == ".docx":
        result["text"], result["warnings"] = _docx(data)
    else:
        result["text"], result["warnings"], result["status"] = _pdf(data)
    _check_text(result["text"])
    if result["format"] == "markdown":
        result["title"] = _markdown_title(result["text"], result["title"])
    if not result["text"].strip() and result["status"] == "ready":
        result["status"] = "empty"
    return result


def extract_path(path, *, allowed_roots=None, max_bytes=MAX_BYTES):
    target = Path(path).resolve()
    if allowed_roots is not None and not any(target.is_relative_to(Path(root).resolve()) for root in allowed_roots):
        raise IngestError("来源文件不在已配置范围内。", "outside_scope")
    if not target.is_file():
        raise IngestError("来源文件不存在。", "missing_file")
    if target.stat().st_size > max_bytes:
        raise IngestError("文件超过单次处理上限。", "too_large")
    with target.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    result = extract_upload(target.name, data, max_bytes=max_bytes)
    result["source"] = {"kind": "local_file", "path": str(target), "name": target.name, "size": len(data)}
    return result


def write_note(output_root, title, markdown, task_id, source_refs=()):
    """Write one new Markdown note; exact retries reuse it, edits never overwrite."""
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", task_id):
        raise IngestError("任务 ID 不能包含路径。", "unsafe_task_id")
    title = safe_title(title)
    # Normalize only the generated note; extraction retains original upload bytes/text.
    markdown = _check_text(markdown).replace("\r\n", "\n").replace("\r", "\n")
    if not markdown.strip():
        raise IngestError("没有可交付内容，不写空笔记。", "empty_output")
    refs = list(source_refs)
    if any(not isinstance(ref, str) or not ref.strip() or "\n" in ref or "\r" in ref or "\x00" in ref for ref in refs):
        raise IngestError("来源引用必须是非空单行文字。", "invalid_source")
    body = markdown.rstrip() + "\n"
    if not body.lstrip().startswith("# "):
        body = "# " + title + "\n\n" + body
    if refs:
        body += "\n## 来源\n\n" + "\n".join("- " + ref for ref in dict.fromkeys(refs)) + "\n"
    text = "<!-- obsidian-workspace task:" + task_id + " -->\n\n" + body
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with writer_lock(root / ".write.lock"):
        matches = list(root.glob("* -- " + task_id + ".md"))
        if len(matches) > 1:
            raise IngestError("同一任务存在多个输出，需要核对后再登记。", "duplicate_output")
        target = matches[0] if matches else root / f"{title} -- {task_id}.md"
        if not target.resolve().is_relative_to(root) or target.is_symlink():
            raise IngestError("笔记路径超出生成目录。", "unsafe_output")
        reused = target.exists()
        if reused:
            if target.read_text(encoding="utf-8") != text:
                raise IngestError("已有笔记内容不同；保留人工修改，未覆盖。", "output_conflict")
        else:
            descriptor, temporary = tempfile.mkstemp(prefix=".note-", suffix=".tmp", dir=root)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(text)
                    handle.flush()
                    os.fsync(handle.fileno())
                if Path(temporary).read_text(encoding="utf-8") != text:
                    raise IngestError("写入临时笔记后读回不一致。", "readback_failed")
                # Hard-link creation publishes atomically and refuses to replace an existing file.
                os.link(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
        if target.read_text(encoding="utf-8") != text:
            raise IngestError("笔记读回不一致，不得登记成功。", "readback_failed")
        return {"note": str(target), "expected_text": text, "created": not reused, "reused": reused}
