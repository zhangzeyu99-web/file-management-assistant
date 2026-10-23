"""Stable, actionable user errors; raw exceptions stay in local diagnostics.

This is a presentation boundary. It never changes task status, source identity,
acknowledgements or retry scope. Historical errors use the same catalog.
"""
from __future__ import annotations

import errno
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .privacy import redact_text


# code: (problem, next action, retryable after that action, help topic)
ERRORS = {
    "native_context_missing": ("尚未连接 Codex 对话。", "在 Codex 打开原对话，复制所需正文到“添加资料”粘贴收录。自动读取需要有效桌面会话连接；普通双击启动或重启不会重新建立这种连接。", False, "native-connection"),
    "native_unavailable": ("本机缺少读取 Codex 对话所需的组件。", "更新并重新打开 Codex 桌面，再从当前会话启动工作台；急需收录时用“添加资料”粘贴文字。", False, "native-connection"),
    "native_incompatible": ("当前 Codex 版本不支持读取对话。", "更新 Codex 桌面后重新启动工作台；更新前可用“添加资料”粘贴文字。", False, "native-connection"),
    "native_disconnected": ("与 Codex 桌面的连接已断开。", "保持 Codex 桌面打开，从当前会话重新启动工作台，再重试未完成项。", True, "native-connection"),
    "native_timeout": ("读取 Codex 对话超时。", "确认 Codex 桌面仍在运行后重试本项；再次超时可在“添加资料”粘贴所需文字。", True, "native-connection"),
    "native_oversized": ("这段对话太长，Codex 无法完整返回内容。", "打开原对话，复制所需文字，在“添加资料 → 粘贴正文”分段收录。", False, "native-connection"),
    "native_read_failed": ("未能读取这段 Codex 对话。", "在 Codex 桌面确认能打开该对话，再重新启动工作台并重试；无法打开时，可在“添加资料”粘贴已有文字。", True, "native-connection"),
    "model_unavailable": ("本机尚未准备好 AI 整理程序。", "安装 Codex CLI，在终端运行 codex login 完成登录，再双击“重启工作台.cmd”。阅读和检索仍可使用。", False, "model-login"),
    "model_failed": ("AI 服务没有完成本次整理。", "在终端运行 codex login status 检查登录；未登录时运行 codex login。确认网络可用后重试本项。", True, "model-login"),
    "model_timeout": ("AI 整理超时，没有返回完整结果。", "重试本项；若同一资料再次超时，将内容拆成较短的几段后通过“添加资料”收录。", True, "model-login"),
    "model_incomplete": ("AI 返回的内容不完整，本次未保存为笔记。", "重试本项；再次失败时缩小资料范围，或通过“添加资料”分段收录。", True, "model-login"),
    "model_empty": ("AI 没有返回正文，本次未保存为笔记。", "重试本项；再次失败时缩小资料范围，或通过“添加资料”分段收录。", True, "model-login"),
    "model_invalid_text": ("AI 返回的文字含乱码或无效字符，本次未保存。", "重试本项；再次失败时复制原资料中的正常文字，通过“添加资料”分段收录。", True, "model-login"),
    "model_quality_failed": ("AI 整理结果缺少具体主题或有效正文，本次未保存。", "重试本项；再次失败时只选择同一主题的资料，或通过“添加资料”补充明确标题和正文。", True, "model-login"),
    "model_tool_use": ("AI 返回了不符合整理要求的结果，本次未保存。", "重试本项；再次出现时保存诊断信息并反馈给项目维护者。", True, "model-login"),
    "cloud_not_configured": ("这台电脑尚未连接线上知识库。", "本机阅读可继续使用；需要同步时，按连接说明填写自己的站点并配置该站点的服务令牌。", False, "cloud-connection"),
    "cloud_auth": ("线上连接凭据已失效或不属于当前电脑。", "在当前电脑重新配置该站点的服务令牌，再双击“重启工作台.cmd”；导入迁移包不会转移登录凭据。", False, "cloud-connection"),
    "cloud_forbidden": ("当前账号或服务令牌没有访问这个站点的权限。", "确认登录的是站点所有者账号，并使用同一站点的服务令牌重新连接。", False, "cloud-connection"),
    "cloud_not_found": ("线上地址或接口不存在。", "核对连接的知识库网址；若网址正确，安装并发布同一版本的工作台后再连接。", False, "cloud-connection"),
    "cloud_rate_limited": ("线上请求过于频繁，服务暂时限流。", "稍等一分钟后重试；不要连续点击提交。", True, "cloud-connection"),
    "cloud_timeout": ("连接线上知识库超时。", "确认网络可用并稍后刷新。任务可能已提交，请先查看更新记录，再重试原请求。", True, "cloud-connection"),
    "cloud_unavailable": ("线上知识库暂时无法连接。", "检查网络后刷新；已显示的任务状态可能是上次记录。请先查看更新记录，避免重复提交。", True, "cloud-connection"),
    "cloud_response_invalid": ("线上返回的数据无法识别。", "刷新页面；再次出现时核对本机和线上版本，并向项目维护者提供诊断信息。", False, "cloud-connection"),
    "cloud_request_conflict": ("线上任务状态已变化，本次操作未被接受。", "刷新更新记录并查看最新状态，再决定是否继续；不要重复创建同一任务。", False, "cloud-connection"),
    "cloud_cache_stale": ("当前显示的是上次任务记录，最新状态尚未确认。", "稍后刷新任务记录；确认状态前不要重复提交同一任务。", True, "cloud-connection"),
    "file_missing": ("找不到这份文件。", "确认原文件未被移动或删除；可在“添加资料”重新选择当前文件。", False, "source-file"),
    "source_directory_unavailable": ("一个资料文件夹无法读取，本次未检查该位置。", "确认文件夹或外接磁盘仍可访问；急需收录时，在“添加资料”直接选择当前文件。", False, "source-file"),
    "source_unreadable": ("系统无法读取部分资料，本次未处理这些内容。", "确认文件仍存在且可打开；将所需资料复制到可读写的个人文件夹，再通过“添加资料”选择。", False, "source-file"),
    "file_permission": ("没有读取或写入这个位置的权限。", "关闭占用文件的程序；将资料复制到可读写的个人文件夹，再通过“添加资料”选择。迁移时请换一个可写的空目录。", False, "source-file"),
    "knowledge_write_denied": ("当前知识库目录无法写入，本次保存未完成。", "确认知识库所在磁盘已连接且目录可写，关闭占用笔记的程序，并检查 Windows 文件夹防护是否拦截工作台。恢复写入权限后重试原任务，无需重新添加资料。", True, "knowledge-data"),
    "disk_full": ("磁盘剩余空间不足，当前操作未完成。", "释放目标磁盘空间，或将迁移位置改到空间充足的空目录，再重试。", False, "migration"),
    "invalid_encoding": ("文件的文字编码无法读取。", "用记事本打开文件，另存为 UTF-8 后在“添加资料”重新选择；也可直接粘贴正文。", False, "source-file"),
    "unsupported_format": ("这种文件格式不能直接提取正文。", "将需要保留的内容导出为 TXT、Markdown、DOCX 或带文字层的 PDF，再通过“添加资料”收录。", False, "source-file"),
    "file_too_large": ("文件或文字超过单次处理上限。", "按章节拆分后重新添加。网页上传文件限 12 MB；粘贴文字请分段提交。", False, "source-file"),
    "encrypted_pdf": ("PDF 有密码保护，无法读取正文。", "用 PDF 软件解锁并另存副本后重新添加；也可复制需要的文字。", False, "source-file"),
    "invalid_docx": ("无法读取这份 Word 文档。", "在 Word 中打开并另存为新的 DOCX，再重新添加；打不开时请重新取得原文件。", False, "source-file"),
    "invalid_pdf": ("无法读取这份 PDF 的文字。", "在 PDF 软件中确认文件可打开；扫描件先识别文字，再导出文本或粘贴到“添加资料”。", False, "source-file"),
    "pdf_dependency_missing": ("本机缺少 PDF 文字提取组件。", "连接网络后重新运行“打开工作台.cmd”安装所需依赖；也可先复制 PDF 正文到“添加资料”。", False, "local-start"),
    "migration_invalid_bundle": ("这个迁移包损坏、格式不兼容或缺少必要记录。", "在原电脑用最新版工作台重新导出 ZIP，再到这里选择该 ZIP 并预检。", False, "migration"),
    "migration_target_occupied": ("导入位置已有内容，或与当前知识库目录重叠。", "选择另一个独立的空目录，点击“检查新位置”，通过预检后再导入。", False, "migration"),
    "migration_target_invalid": ("这个导入位置无法使用。", "填写一个可写空文件夹的完整路径，例如 D:\\个人知识库；点击“检查新位置”后再导入。", False, "migration"),
    "migration_busy": ("当前还有任务在执行，暂时不能切换知识库。", "到“更新记录”等待任务结束，或取消该任务；之后回到迁移页重新导入。", False, "migration"),
    "migration_activation_denied": ("资料已恢复，但启用工作台时没有写入权限。", "保留已恢复的目录。检查该目录、工作台项目目录和运行记录目录的写入权限，关闭占用文件的程序或解除 Windows 文件夹防护拦截，再点击“重试启用工作台”；无需重新导入或更改位置。", True, "migration"),
    "migration_activation_failed": ("资料已恢复，但工作台尚未启用。", "保留已恢复的目录，确认本机启动依赖齐全、项目与运行记录目录可用，再点击“重试启用工作台”。仍失败时复制诊断信息反馈；无需重新导入或更改位置。", True, "migration"),
    "migration_upload_incomplete": ("迁移包尚未完整上传。", "保持页面打开并等待上传完成；上传已中断时重新选择同一个 ZIP。", True, "migration"),
    "migration_upload_missing": ("上传记录已失效，可能是本机服务重启所致。", "重新选择迁移包，等待上传完成后再次预检。", False, "migration"),
    "migration_precheck_required": ("导入位置或迁移包已改变，需要重新预检。", "点击“检查新位置”，确认预检显示的目录和内容，再点击导入。", False, "migration"),
    "migration_source_changed": ("打包期间资料发生了变化，迁移包未完成。", "等待整理任务结束，关闭正在编辑笔记的程序，再新建一次导出。", True, "migration"),
    "migration_download_missing": ("迁移包尚未准备好，或原下载文件已失效。", "回到“备份与迁移”重新导出，完成后使用新下载链接。", False, "migration"),
    "migration_too_large": ("迁移包超过当前入口的大小上限。", "线上下载限 128 MB；请在运行工作台的电脑打开本机网页导出。导入 ZIP 限 2 GiB，超出时先减少附件。", False, "migration"),
    "checkpoint_missing": ("缺少原知识库的增量记录，无法安全继续自动总结。", "从原电脑重新导出完整迁移包并导入；不要新建空库覆盖已有资料。现有笔记仍可阅读。", False, "knowledge-data"),
    "checkpoint_invalid": ("知识库的处理记录不完整或无法读取。", "保留当前目录，从最近的完整迁移包导入到另一个空目录；没有备份时请向项目维护者提供诊断信息。", False, "knowledge-data"),
    "write_conflict": ("已有笔记与本次结果不同，程序保留了原内容。", "打开已有笔记核对人工修改；需要另存本次资料时，通过“添加资料”使用不同标题。", False, "knowledge-data"),
    "write_readback_failed": ("保存后的内容与写入结果不一致，未登记成功。", "确认磁盘可写且空间充足，暂停同时修改该文件的同步或编辑程序，再重试本项。", False, "knowledge-data"),
    "selection_changed": ("所选资料已变化，当前选择无法继续使用。", "关闭选择窗口，重新点击“自动总结”读取候选，勾选后再提交。", False, "selection"),
    "note_missing": ("这篇笔记不存在，或页面仍使用旧索引。", "刷新页面后重新搜索；仍找不到时，在本机确认笔记是否被移动或删除。", False, "knowledge-data"),
    "note_too_large": ("这篇笔记超过 8 MB，暂时无法建立阅读索引。", "用 Obsidian 将它按主题拆成小于 8 MB 的几篇笔记，保存后刷新工作台。", False, "knowledge-data"),
    "knowledge_metadata_invalid": ("知识库的链接或图谱配置记录无法读取。", "保留当前目录，先用 Obsidian 阅读笔记；需要恢复网页入口时，将最近的完整迁移包导入另一个空目录。", False, "knowledge-data"),
    "local_busy": ("另一个工作台正在写入同一知识库。", "保留一个工作台执行器，等待另一项整理或迁移结束后再试。不要删除运行锁。", False, "local-start"),
    "setup_required": ("尚未导入或建立知识库。", "已有资料请选择“备份与迁移”导入 ZIP；首次使用可按开始说明建立空库。", False, "local-start"),
    "request_forbidden": ("当前页面无权调用本机接口。", "通过“打开工作台.cmd”进入本机页面；线上使用自己的知识库网址。", False, "local-start"),
    "request_not_found": ("这个链接或操作入口已失效。", "刷新页面并从首页重新进入；旧任务请在“更新记录”中查找。", False, "local-start"),
    "request_invalid": ("提交的内容不符合要求，当前请求无法继续处理。", "刷新页面，重新选择资料或迁移包后提交；标题请使用普通文字。", False, "selection"),
    "task_not_retryable": ("这个任务正在执行或已经完成，无需重试。", "查看该任务的最新结果；需要处理新资料时，从“自动总结”重新选择。", False, "selection"),
    "internal_error": ("程序遇到未识别的问题，暂时无法确认操作结果。", "先查看原任务或原内容，避免重复提交；重新打开工作台后仍失败时，复制诊断信息并通过项目反馈入口提交操作步骤。", False, "knowledge-data"),
}

ALIASES = {"native_read": "native_read_failed", "native_call_failed": "native_read_failed",
           "protocol_error": "native_read_failed", "thread_processing": "internal_error",
           "too_large": "file_too_large", "outside_scope": "selection_changed",
           "missing_file": "file_missing", "missing_output": "note_missing",
           "output_conflict": "write_conflict", "duplicate_output": "write_conflict",
           "readback_failed": "write_readback_failed", "dependency_missing": "pdf_dependency_missing",
           "invalid_note_index": "checkpoint_invalid", "empty_output": "model_incomplete"}


def _code(error, hint=None, context=""):
    code = hint or getattr(error, "code", None)
    code = ALIASES.get(code, code)
    if code in ERRORS and code != "internal_error":
        return code
    text = str(error)
    lower = text.casefold()
    if isinstance(error, PermissionError) or any(p in lower for p in ("permission denied", "access denied", "[errno 13]", "[winerror 5]")) or "拒绝访问" in text:
        return "file_permission"
    if isinstance(error, OSError) and error.errno == errno.ENOSPC or any(p in lower for p in ("no space left", "磁盘空间不足", "磁盘剩余空间")):
        return "disk_full"
    if isinstance(error, FileNotFoundError) or any(p in lower for p in ("no such file", "[errno 2]", "[winerror 2]")):
        return "file_missing"
    # Historical records have no typed code. Match specific failures before broad categories.
    rules = (
        (("知识库目标目录无法写入", "当前知识库目录无法写入"), "knowledge_write_denied"),
        (("超过原生读取限制", "超出原生读取限制", "native_oversized"), "native_oversized"),
        (("真实调用线程上下文", "当前来源未连接", "native_context_missing"), "native_context_missing"),
        (("未找到已安装的 Codex 原生", "原生工具需要的 Node", "无法启动 Codex 原生", "工具服务不存在"), "native_unavailable"),
        (("缺少所需的只读接口",), "native_incompatible"),
        (("原生工具连接已关闭",), "native_disconnected"),
        (("原生工具读取超时",), "native_timeout"),
        (("原生来源读取失败", "Codex 拒绝原生", "原生轮次分页读取失败", "原生来源返回内容截断", "未能继续读取到已总结边界"), "native_read_failed"),
        (("未找到可执行的 Codex CLI", "无法启动模型执行器", "安装 Codex CLI"), "model_unavailable"),
        (("模型执行超时",), "model_timeout"),
        (("模型返回正文为空",), "model_empty"),
        (("模型正文含 U+FFFD", "模型正文含 U+0000"), "model_invalid_text"),
        (("正文没有可复用内容", "第一段须用一句话", "笔记标题缺少", "知识笔记必须", "知识笔记只有标题"), "model_quality_failed"),
        (("模型未返回完整", "没有可交付内容"), "model_incomplete"),
        (("模型尝试调用工具",), "model_tool_use"),
        (("模型执行失败", "模型执行器退出失败"), "model_failed"),
        (("UTF-8", "UTF-16", "编码异常", "解码"), "invalid_encoding"),
        (("PDF 已加密",), "encrypted_pdf"),
        (("无法读取 DOCX", "DOCX 正文含"), "invalid_docx"),
        (("无法读取 PDF",), "invalid_pdf"),
        (("pypdf",), "pdf_dependency_missing"),
        (("来源文件不存在",), "file_missing"),
        (("来源目录不可用", "知识库目录不存在"), "source_directory_unavailable"),
        (("不支持的文件格式", "此格式尚未自动提取"), "unsupported_format"),
        (("目标已有不同内容", "目标目录已有内容", "目标运行目录必须为空", "目标配置或检查点已存在", "新目录必须独立", "路径冲突", "目标目录不能通过链接", "必须保存到运行数据目录和笔记库之外"), "migration_target_occupied"),
        (("目标目录必须是完整路径", "无法找到空迁移目录", "新笔记输出目录必须"), "migration_target_invalid"),
        (("当前任务正在执行", "另一项迁移正在进行", "正在导入并切换", "当前任务仍在执行", "执行器尚未停止"), "migration_busy"),
        (("上传记录不存在", "服务已重启", "迁移任务不存在"), "migration_upload_missing"),
        (("尚未上传完整", "上传分块不完整", "上传偏移不连续", "重传分块与已上传内容不一致", "待导入文件已达到暂存上限"), "migration_upload_incomplete"),
        (("请先预检", "已经预检", "此迁移包已提交", "已提交的导入不能删除"), "migration_precheck_required"),
        (("导出期间变化", "导出期间发生变化", "上传期间变化", "导入期间发生变化"), "migration_source_changed"),
        (("迁移包尚未准备好", "迁移包已不存在", "已生成迁移包缺失", "迁移包下载标识", "线上未确认完整迁移包"), "migration_download_missing"),
        (("线上128 MB", "迁移包大小必须", "迁移包解压内容超过"), "migration_too_large"),
        (("缺少已验收基线时间", "缺少已确认的迁移时间"), "checkpoint_missing"),
        (("迁移包", "迁移后的检查点引用", "知识库管理元数据无效", "缺少显式路径映射"), "migration_invalid_bundle"),
        (("检查点不存在", "缺少已验收基线时间"), "checkpoint_missing"),
        (("检查点不是", "检查点欠账", "周归档验收记录", "周归档水位", "笔记身份记录异常"), "checkpoint_invalid"),
        (("另一个写入者", "独占锁", "运行锁", "导出必须由", "任务租约失效"), "local_busy"),
        (("已有笔记内容不同", "同一任务存在多个输出"), "write_conflict"),
        (("读回不一致",), "write_readback_failed"),
        (("所选", "所选择", "来源文件不在已配置范围"), "selection_changed"),
        (("笔记超过 8 MB",), "note_too_large"),
        (("笔记不存在", "未找到链接笔记", "项目不存在", "已保存笔记被移走", "资料 ID", "笔记 ID"), "note_missing"),
        (("单次处理上限", "不超过 12 MB", "文件过大", "上传分块不能超过"), "file_too_large"),
        (("此任务不需要重试",), "task_not_retryable"),
        (("尚未启用知识库", "请先在迁移页面", "未找到配置"), "setup_required"),
        (("仅接受本机请求", "请求来源不匹配"), "request_forbidden"),
        (("未找到接口", "未找到任务"), "request_not_found"),
    )
    for phrases, result in rules:
        if any(phrase in text for phrase in phrases):
            return result
    if "线上" in text or context == "cloud":
        status = re.search(r"(?:返回|HTTP)\s*(\d{3})", text, re.I)
        if status:
            return {401: "cloud_auth", 403: "cloud_forbidden", 404: "cloud_not_found",
                    409: "cloud_request_conflict", 429: "cloud_rate_limited"}.get(int(status[1]), "cloud_unavailable")
        if "尚未配置" in text:
            return "cloud_not_configured"
        if "当前电脑保存的线上服务凭据" in text:
            return "cloud_auth"
        if "尚未刷新线上任务" in text or "线上任务缓存不可读" in text:
            return "cloud_cache_stale"
        if "格式无效" in text or "有效任务记录" in text or "数据无法识别" in text:
            return "cloud_response_invalid"
        if "timed out" in lower or "超时" in text:
            return "cloud_timeout"
        return "cloud_unavailable"
    if isinstance(error, (ValueError, KeyError)) or any(p in text for p in ("必须", "无效", "不能包含", "不支持的任务", "需要 application/", "请求内容")):
        return "request_invalid"
    return "internal_error"


def user_error(error, *, code=None, context="", diagnostic_id=None):
    key = _code(error, code, context)
    message, action, retryable, help_topic = ERRORS[key]
    result = {"code": key, "message": message, "action": action, "retryable": retryable, "help": help_topic}
    if diagnostic_id:
        result["diagnostic_id"] = diagnostic_id
    return result


def catalog():
    """Portable catalog for the web client; no private runtime data."""
    return {code: {"code": code, "message": row[0], "action": row[1],
                   "retryable": row[2], "help": row[3]} for code, row in ERRORS.items()}


def _known_detail(value):
    if not isinstance(value, dict) or value.get("code") not in ERRORS:
        return None
    reference = value.get("diagnostic_id")
    if not isinstance(reference, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", reference):
        reference = None
    return user_error("", code=value["code"], diagnostic_id=reference)


def public_payload(value, *, context=""):
    """Copy API/job output, replacing raw error strings without changing facts."""
    if isinstance(value, list):
        return [public_payload(item, context=context) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: public_payload(item, context="cloud" if key in {"cloud_cache", "jobs_cache"} else context)
              for key, item in value.items()}
    for field in ("error", "cache_error", "setup_error"):
        original = value.get(field)
        if not isinstance(original, str) or not original:
            continue
        detail_key = "error_detail" if field == "error" else field + "_detail"
        existing = value.get(detail_key)
        if field == "error" and not existing and isinstance(value.get("result"), dict):
            existing = value["result"].get("failure")
        detail = _known_detail(existing) or user_error(original, code=value.get("error_code"), context=context)
        result[field], result[detail_key] = detail["message"], detail
        if field == "error":
            result.setdefault("error_code", detail["code"])
    warnings = value.get("warnings")
    if isinstance(warnings, list):
        details = list(result.get("warning_details") or [])
        public_warnings = []
        for warning in warnings:
            failure_warning = isinstance(warning, str) and (
                warning.startswith(("Codex 对话尚未检查：", "来源目录不可用：")) or
                any(marker in warning.casefold() for marker in
                    ("[errno ", "[winerror ", "permission denied", "access denied", "no such file")))
            if failure_warning:
                detail = user_error(warning)
                if detail["code"] == "internal_error":
                    detail = user_error(warning, code="source_unreadable")
                public_warnings.append(detail["message"])
                if not any(row.get("code") == detail["code"] for row in details if isinstance(row, dict)):
                    details.append(detail)
            elif isinstance(warning, dict) and isinstance(warning.get("reason"), str):
                prior = _known_detail(warning.get("error_detail"))
                detail = prior or user_error(warning["reason"])
                if not prior and detail["code"] in {"internal_error", "request_invalid"}:
                    detail = user_error(warning["reason"], code=("knowledge_metadata_invalid"
                        if str(warning.get("path", "")).endswith(".json") else "source_unreadable"))
                public_warnings.append({**public_payload(warning, context=context),
                                        "reason": detail["message"], "error_detail": detail})
            else:
                public_warnings.append(public_payload(warning, context=context))
        result["warnings"] = public_warnings
        if details:
            result["warning_details"] = details
    if result.get("status") == "failed" and result.get("error_detail"):
        result["result"] = {**(result.get("result") or {}), "failure": result["error_detail"]}
    return result


_diagnostic_lock = threading.Lock()


def record_diagnostic(directory, error, *, context=""):
    """Best-effort private bounded log. Logging must never hide the real failure."""
    diagnostic_id = uuid.uuid4().hex[:12]
    if directory is None:
        return None
    row = {"id": diagnostic_id, "at": datetime.now(timezone.utc).isoformat(),
           "context": context, "type": type(error).__name__,
           "detail": redact_text(str(error))[:8000]}
    try:
        folder = Path(directory) / "diagnostics"
        with _diagnostic_lock:
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / "errors.jsonl"
            if target.exists() and target.stat().st_size > 1024 * 1024:
                target.replace(folder / "errors.previous.jsonl")
            with target.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        return None
    return diagnostic_id
