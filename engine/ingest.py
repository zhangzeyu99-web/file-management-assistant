"""Actual uploaded bytes/text extraction and append-only Markdown delivery."""
from __future__ import annotations

import io
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from .incremental import IncrementalError, atomic_json, writer_lock


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


def semantic_title(value, markdown=""):
    """A readable title; operational identifiers belong in hidden metadata."""
    fallback = safe_title(value)
    heading = _markdown_title(markdown, fallback) if markdown else fallback
    if heading in {"总结", "整理结果", "知识笔记", "新资料", "测试整理结果"}:
        heading = fallback
    heading = re.sub(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", "", heading)
    heading = re.sub(r"(?<![A-Za-z0-9])[A-Za-z0-9_-]{24,}(?![A-Za-z0-9])", "", heading)
    heading = re.sub(r"^\d{8}[-_ ]\d{6}(?:[-_ ]+|$)", "", heading)
    heading = re.sub(r"[\s_-]{2,}", " ", heading).strip(" -_—·：:")
    return safe_title(heading or "未命名资料")[:48].rstrip()


def source_link(value, label=None):
    """Keep the source target, while showing a name rather than an encoded path."""
    if re.fullmatch(r"\[[^\n]+\]\([^\n]+\)", value):
        return value
    if re.match(r"^(?:https?://|codex://|file:)", value, re.I):
        return f"[{label or '打开来源'}](<{value}>)"
    if re.match(r"^(?:[A-Za-z]:[\\/]|/|\\\\)", value):
        target = Path(value)
        name = label or semantic_title(target.stem)
        return f"[{name}](<{target.as_uri()}>)"
    if re.fullmatch(r"[A-Za-z0-9_-]{24,}", value):
        hidden = json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
        return (label or "来源记录") + "<!-- source-ref:" + hidden + " -->"
    if re.search(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
        hidden = json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
        return (label or semantic_title(Path(value).stem)) + "<!-- source-ref:" + hidden + " -->"
    return value


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


def _note_matches(root, task_id):
    marker = "<!-- obsidian-workspace task:" + task_id + " -->"
    matches = []
    for directory, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if (not name.startswith(".") or
                          Path(directory) == root and name == ".source-history") and
                          not (Path(directory) / name).is_symlink() and
                          not bool(getattr((Path(directory) / name).stat(), "st_file_attributes", 0) & 0x400)]
        for name in files:
            if not name.endswith(".md"):
                continue
            path = Path(directory) / name
            if path.is_symlink():
                continue
            legacy = name.endswith(" -- " + task_id + ".md")
            with path.open(encoding="utf-8-sig", errors="replace") as handle:
                header = handle.read(4096)
            if legacy or marker in header:
                matches.append(path)
    return matches


def _note_text(title, markdown, task_id, refs, *, readable):
    body = markdown.rstrip() + "\n"
    if body.lstrip().startswith("# "):
        if readable:
            body = re.sub(r"^\s*#[ \t]+[^\n]+", "# " + title, body, count=1)
    else:
        body = "# " + title + "\n\n" + body
    if refs:
        body += "\n## 来源\n\n" + "\n".join(
            "- " + (source_link(ref) if readable else ref) for ref in dict.fromkeys(refs)) + "\n"
    return "<!-- obsidian-workspace task:" + task_id + " -->\n\n" + body


def write_note(output_root, title, markdown, task_id, source_refs=(), *, folder=None, identity_root=None):
    """Write one new Markdown note; exact retries reuse it, edits never overwrite."""
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", task_id):
        raise IngestError("任务 ID 不能包含路径。", "unsafe_task_id")
    original_title = safe_title(title)
    # Normalize only the generated note; extraction retains original upload bytes/text.
    markdown = _check_text(markdown).replace("\r\n", "\n").replace("\r", "\n")
    title = semantic_title(original_title, markdown)
    if not markdown.strip():
        raise IngestError("没有可交付内容，不写空笔记。", "empty_output")
    refs = list(source_refs)
    if any(not isinstance(ref, str) or not ref.strip() or "\n" in ref or "\r" in ref or "\x00" in ref for ref in refs):
        raise IngestError("来源引用必须是非空单行文字。", "invalid_source")
    legacy_text = _note_text(original_title, markdown, task_id, refs, readable=False)
    root = Path(output_root).resolve()
    identities = Path(identity_root or root).resolve()
    if not root.is_relative_to(identities):
        raise IngestError("生成目录不在知识库内。", "unsafe_output")
    destination = root / safe_title(folder) if folder else root
    root.mkdir(parents=True, exist_ok=True)
    with writer_lock(root / ".write.lock"):
        index_path = root / ".note-index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"version": 1, "tasks": {}}
            if index.get("version") != 1 or not isinstance(index.get("tasks"), dict):
                raise ValueError("invalid index")
            saved = index["tasks"].get(task_id)
            if saved and (not isinstance(saved, dict) or saved.get("status") not in {"reserved", "written"} or
                          not isinstance(saved.get("path"), str)):
                raise ValueError("invalid entry")
            if saved:
                relative = saved["path"]
                pure = PurePosixPath(relative)
                if (not relative or pure.is_absolute() or "\\" in relative or ":" in relative
                        or pure.as_posix() != relative or pure.suffix.lower() != ".md"
                        or any(part.startswith(".") and not (index == 0 and part == ".source-history")
                               for index, part in enumerate(pure.parts))):
                    raise ValueError("invalid note path")
        except (OSError, ValueError, TypeError, AttributeError) as error:
            raise IngestError("笔记身份记录异常，未另建副本。", "invalid_note_index") from error
        target = identities / saved["path"] if saved else None
        # Scanning also recovers the identity after a directory move or a legacy save.
        matches = _note_matches(identities, task_id) if not target or not target.exists() else [target]
        if len(matches) > 1:
            raise IngestError("同一任务存在多个输出，需要核对后再登记。", "duplicate_output")
        if matches:
            target = matches[0]
        elif saved and saved["status"] == "written":
            raise IngestError("已保存笔记被移走或删除，未重复生成。", "missing_output")
        elif not target:
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / (title + ".md")
            number = 2
            reserved = {os.path.normcase(entry.get("path", "")) for entry in index["tasks"].values() if isinstance(entry, dict)}
            while target.exists() or os.path.normcase(target.relative_to(identities).as_posix()) in reserved:
                target = destination / f"{title}（{number}）.md"
                number += 1
        if not target.resolve().is_relative_to(identities) or target.is_symlink() or any(
                parent.is_symlink() or bool(getattr(parent.stat(), "st_file_attributes", 0) & 0x400)
                for parent in [target.parent, *target.parent.parents] if parent.is_relative_to(identities)):
            raise IngestError("笔记路径超出生成目录。", "unsafe_output")
        if saved:
            title = safe_title(saved.get("title") or title)
        text = _note_text(title, markdown, task_id, refs, readable=True)
        reused = target.exists()
        if reused:
            existing = target.read_text(encoding="utf-8")
            if existing not in (text, legacy_text):
                raise IngestError("已有笔记内容不同；保留人工修改，未覆盖。", "output_conflict")
            text = existing
            title = _markdown_title(existing, title)
        else:
            if not target.resolve().is_relative_to(root):
                raise IngestError("历史笔记只能读回复用，不能在历史目录中新建。", "unsafe_output")
            # Reserve before publishing: a failed save keeps its name on retry, even
            # if another task has the same title or the user removes the HTML marker.
            index["tasks"][task_id] = {"path": target.relative_to(identities).as_posix(), "title": title, "status": "reserved"}
            atomic_json(index_path, index)
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".note-", suffix=".tmp", dir=target.parent)
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
        index["tasks"][task_id] = {"path": target.relative_to(identities).as_posix(), "title": title, "status": "written"}
        atomic_json(index_path, index)
        return {"note": str(target), "title": title, "expected_text": text, "created": not reused, "reused": reused}
