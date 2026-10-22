import catalog from "./error-catalog.json" with { type: "json" };

export type UserIssue = { code: string; message: string; action: string; retryable: boolean; help: string; diagnostic: string };
type Options = { context?: string; status?: number };
const records = catalog as Record<string, Omit<UserIssue, "code" | "diagnostic">>;
const issued = new WeakSet<object>();
const local: typeof records = {
  local_offline: { message: "保存资料的电脑尚未连接。", action: "到那台电脑双击“打开工作台.cmd”，保持工作台运行。本页会自动继续，已提交任务无需再提交。", retryable: false, help: "local-start" },
  site_login: { message: "网站登录已失效。", action: "重新打开知识库网址并登录站点所有者账号，再查看原任务。", retryable: false, help: "cloud-connection" },
  file_required: { message: "还没有选择文件。", action: "选择一份 TXT、Markdown、DOCX 或带文字层的 PDF。", retryable: false, help: "" },
  text_required: { message: "资料正文为空。", action: "粘贴需要保留的文字后再收录。", retryable: false, help: "" },
  clipboard_blocked: { message: "浏览器未允许复制。", action: "选中文字手动复制，或下载 Markdown 后打开。", retryable: false, help: "" },
  task_busy: { message: "已有另一项整理正在执行，本次选择尚未提交。", action: "打开“更新记录”查看当前任务；完成后再提交所选内容。", retryable: false, help: "selection" },
  migration_result_unknown: { message: "还未确认导入结果。", action: "点击“检查导入结果”，不要重复导入。已提交的请求会继续处理。", retryable: true, help: "migration" },
  export_progress_unknown: { message: "暂时读不到导出进度。", action: "连接恢复后会继续检查，请保留本页，不要另建重复导出。", retryable: true, help: "migration" },
  task_status_changed: { message: "任务状态已经变化，本次操作未生效。", action: "先查看更新记录，确认任务是否已完成或取消；不要重复提交。", retryable: false, help: "selection" },
  migration_local_required: { message: "导入需要在当前电脑的本机工作台完成。", action: "下载并解压启动包，双击“打开工作台.cmd”，在本机“备份与迁移”选择 ZIP；线上页面不会替换另一台电脑的资料。", retryable: false, help: "migration" },
  file_read_failed: { message: "浏览器没有读到所选文件。", action: "确认文件已下载到本机，重新选择；也可打开文件，复制文字到“粘贴正文”。", retryable: false, help: "source-file" },
  migration_activation_pending: { message: "资料已恢复，尚未确认新知识库已启用。", action: "点击“检查切换状态”确认结果，无需再次上传或导入。", retryable: true, help: "migration" },
  service_unavailable: { message: "网站服务暂时无法处理这个请求。", action: "稍后重新检查。提交任务后出现此提示时，先查看更新记录，避免重复提交；本机已有资料仍可使用。", retryable: true, help: "cloud-connection" },
};
function object(value: unknown): Record<string, unknown> { return value && typeof value === "object" ? value as Record<string, unknown> : {}; }
function rawText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value instanceof Error) return value.message;
  const item = object(value);
  const detail = object(item.error_detail || item.failure || object(item.result).failure);
  return String(detail.message || item.message || item.error || item.reason || "");
}
function legacyCode(text: string, status?: number): string {
  const rules: [RegExp, string][] = [
    [/导入需要在当前电脑|线上不会替换另一台电脑/, "migration_local_required"],
    [/尚未连接|本机(?:未连接|离线)|等待本机|电脑.*离线/, "local_offline"],
    [/已有其他整理任务|已有另一.*任务|本次选择未提交/, "task_busy"],
    [/没有读到文件内容/, "file_read_failed"],
    [/资料已恢复.*还没有切换/, "migration_activation_pending"],
    [/请先选择文件/, "file_required"], [/请填写资料正文|正文为空/, "text_required"],
    [/单个文件最多|文件.*超过.*(?:MB|上限)|内容过大|payload too large/i, "file_too_large"],
    [/支持 TXT|目前支持|不支持.*格式/, "unsupported_format"],
    [/复制失败|clipboard|notallowederror/i, "clipboard_blocked"],
    [/原生.*限制|超出.*读取限制|对话太长|maximum.{0,12}context/i, "native_oversized"],
    [/真实调用线程上下文|当前来源未连接|native_context_missing/i, "native_context_missing"],
    [/原生工具连接已关闭|native_disconnected/i, "native_disconnected"],
    [/原生工具读取超时|native_timeout/i, "native_timeout"],
    [/未找到.*Codex CLI|无法启动模型|尚未准备好 AI/i, "model_unavailable"],
    [/模型执行超时|AI.*超时/i, "model_timeout"],
    [/模型.*失败|模型执行器退出|登录.*(?:失效|过期)|not logged in/i, "model_failed"],
    [/模型未返回完整|第一段须用一句话|笔记标题缺少|没有可交付内容|输出不完整/, "model_incomplete"],
    [/UTF.?8|UTF.?16|解码|decode|codec|unicode|无效字节/i, "invalid_encoding"],
    [/PDF.*(?:密码|加密)/i, "encrypted_pdf"], [/无法读取.*DOCX|invalid.*docx/i, "invalid_docx"],
    [/扫描|文字层|无法读取.*PDF/i, "invalid_pdf"],
    [/目标.*(?:已有|非空)|位置已有内容|目录.*重叠|新目录必须独立|路径冲突|目标运行目录必须为空/, "migration_target_occupied"],
    [/磁盘.*(?:不足|已满)|no space left|enospc/i, "disk_full"],
    [/迁移包.*(?:损坏|格式|版本|兼容|必要)|bad.?zip|解压|zip.*(?:invalid|corrupt)/i, "migration_invalid_bundle"],
    [/下载链接已过期|迁移包尚未准备好|迁移包没有可用下载地址|迁移包.*不完整|导出记录已不可用/, "migration_download_missing"],
    [/上传记录.*(?:不存在|失效)|本机没有这条迁移记录|上传会话不可用/, "migration_upload_missing"],
    [/分片|上传.*未.*完整|上传.*中断/, "migration_upload_incomplete"],
    [/预检|检查新位置/, "migration_precheck_required"],
    [/还未确认结果|请勿重复导入/, "migration_result_unknown"],
    [/当前任务.*执行|迁移.*进行|切换知识库.*任务|执行器.*未停止/, "migration_busy"],
    [/迁移包.*(?:大小上限|128 MB|2 GiB)|迁移.*超过/, "migration_too_large"],
    [/笔记不存在|未找到笔记|未能打开链接笔记|找不到.*笔记/, "note_missing"],
    [/文件.*(?:不存在|已删除|移走)|no such file|file.*not found/i, "file_missing"],
    [/permission denied|拒绝访问|文件.*权限|目录.*权限/i, "file_permission"],
    [/未找到任务|未找到项目|未找到接口|链接.*失效/, "request_not_found"],
    [/此任务不需要重试/, "task_not_retryable"],
    [/请求来源不匹配|跨域/, "request_forbidden"],
    [/所选.*变化|选择范围.*无效|范围.*重新选择/, "selection_changed"],
    [/检查点.*(?:缺少|不存在)|缺少.*增量记录/, "checkpoint_missing"],
    [/检查点.*(?:无效|损坏)|处理记录.*不完整/, "checkpoint_invalid"],
    [/人工修改|已有.*内容不同|目标已有不同内容/, "write_conflict"],
    [/读回.*不一致|保存后.*不一致/, "write_readback_failed"],
    [/限流|too many|rate.limit|429/i, "cloud_rate_limited"],
    [/timeout|timed out|超时/i, "cloud_timeout"],
    [/failed to fetch|networkerror|network request|连接.*(?:断开|失败)|网络.*(?:失败|中断|不可用)|econnrefused/i, "cloud_unavailable"],
    [/json|unexpected token|返回.*数据.*(?:识别|无效)/i, "cloud_response_invalid"],
  ];
  for (const [pattern, code] of rules) if (pattern.test(text)) return code;
  if (status === 401) return "site_login";
  if (status === 403) return "request_forbidden";
  if (status === 400 || status === 405 || status === 422) return "request_invalid";
  if (status === 404) return "request_not_found";
  if (status === 409) return "task_status_changed";
  if (status === 410) return "migration_download_missing";
  if (status === 413) return "file_too_large";
  if (status === 429) return "cloud_rate_limited";
  if (status && status >= 500) return "service_unavailable";
  return "internal_error";
}

export function userIssue(input: unknown, options: Options = {}): UserIssue {
  const value = object(input);
  if (issued.has(value)) return input as UserIssue;
  const detail = object(value.error_detail || value.failure || object(value.result).failure);
  const status = options.status || (typeof value.status === "number" ? value.status : undefined);
  const hinted = String(detail.code || value.code || value.error_code || "");
  const code = records[hinted] || local[hinted] ? hinted : legacyCode(rawText(input), status);
  const item = local[code] || records[code] || records.internal_error;
  // Only catalog text is public. Upstream HTML, paths and exception text never enter the notice or copied diagnostics.
  const issue = { code, ...item, diagnostic: JSON.stringify({ code, ...(status ? { http_status: status } : {}), operation: (options.context || "操作").replace(/[^\p{Script=Han}a-zA-Z0-9 _-]/gu, "").slice(0, 40), at: new Date().toISOString() }, null, 2) };
  issued.add(issue);
  return issue;
}

export class RequestFailure extends Error {
  readonly status: number;
  readonly error_detail: unknown;
  constructor(status: number, data: unknown) {
    const item = object(data);
    super(typeof item.error === "string" ? item.error : "");
    this.name = "RequestFailure";
    this.status = status;
    this.error_detail = item.error_detail || (item.error_code ? {code:item.error_code} : undefined);
  }
}

export async function readJsonResponse<T>(response: Response): Promise<T> {
  let data: unknown;
  try { data = await response.json(); }
  catch { throw new RequestFailure(response.status || 502, { error_detail: { code: response.ok ? "cloud_response_invalid" : undefined } }); }
  if (!response.ok) throw new RequestFailure(response.status, data);
  return data as T;
}
