type RecordValue = Record<string, unknown>;

function record(value: unknown): RecordValue {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
}

export type UpdateJob = {
  id: string; kind?: string; status: string; stage?: string;
  created_at?: string | number; updated_at?: string | number;
  input?: unknown; result?: unknown; error?: string;
};
export type UpdateNote = { id: string; title: string };

function jobTime(job: UpdateJob) {
  const value = job.created_at ?? job.updated_at;
  if (typeof value === "number") return value;
  if (typeof value !== "string") return 0;
  return /^\d+$/.test(value) ? Number(value) : Date.parse(value) || 0;
}

export function latestUpdateAttempt(job: UpdateJob, jobs: UpdateJob[]) {
  const all = new Map([...jobs, job].map(item => [item.id, item]));
  const root = (item: UpdateJob) => {
    const seen = new Set<string>();
    let id = item.id;
    while (all.has(id)) {
      if (seen.has(id)) return item.id;
      seen.add(id);
      const parent = record(all.get(id)?.input).retry_of;
      if (typeof parent !== "string" || !parent) break;
      id = parent;
    }
    return id;
  };
  const lineage = root(job);
  return [...all.values()].filter(item => (item.kind || "update") === (job.kind || "update") && root(item) === lineage)
    .reduce((latest, item) => jobTime(item) > jobTime(latest) ? item : latest, job);
}

function sourceLabel(value: unknown) {
  const source = typeof value === "string" ? value : String(record(value).title || record(value).name || record(value).path || "");
  if (/^https?:\/\//i.test(source)) return "在线文档";
  if (/^codex:\/\//i.test(source)) return "对话";
  const label = source.split(/[\\/]/).at(-1)?.replace(/\.[a-z0-9]{1,8}$/i, "")
    .replace(/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}|\b[0-9a-f]{24,}\b/gi, "")
    .replace(/[_\s-]+/g, " ").trim() || "来源资料";
  return label.length > 56 ? label.slice(0, 54) + "…" : label;
}

function errorMessage(value: unknown): string {
  if (typeof value === "string") return value;
  const item = record(value);
  const body = item.error || item.message || item.reason;
  return typeof body === "string" ? body : body ? errorMessage(body) : "";
}

function nativeReadLimit(value: unknown) {
  return /原生.*限制|超过.{0,16}(?:读取|阅读)限制|内容截断|maximum.{0,12}context/i.test(errorMessage(value));
}

export function updatePendingItem(value: unknown) {
  const item = record(value), message = errorMessage(value);
  const source = sourceLabel(item.title || item.source || "整理任务");
  if (nativeReadLimit(value)) {
    return { source, reason: "对话太长，当前无法完整读取。", action: "当前无法自动补齐；可通过“添加资料”收录所需内容。" };
  }
  if (/编码|utf.?8|decode|codec|unicode|gbk|无效字节/i.test(message)) {
    return { source, reason: "这份文件暂时读不开。", action: "可导出为文本或 Markdown 后重新收录。" };
  }
  if (/权限|403|unauthori[sz]|permission|forbidden/i.test(message)) {
    return { source, reason: "当前没有读取权限。", action: "补充来源授权后重试。" };
  }
  if (/不存在|找不到|已删除|not found|no such file|404/i.test(message)) {
    return { source, reason: "来源已移走或无法找到。", action: "确认原文件或链接仍可打开，再重试。" };
  }
  if (/线上同步/.test(source)) {
    return { source, reason: "成果已保存在本机，线上尚未更新。", action: "连接恢复后重试同步。" };
  }
  if (/网络|超时|timeout|timed out|connection|暂不可用|断开|failed to fetch/i.test(message)) {
    return { source, reason: "读取暂时中断。", action: "连接恢复后重试。" };
  }
  return { source, reason: "本次未能完成读取。", action: "核对来源后重试。" };
}

function savedNotes(values: unknown): UpdateNote[] {
  if (!Array.isArray(values)) return [];
  const notes: UpdateNote[] = [], seen = new Set<string>();
  for (const value of values) {
    const item = record(value);
    if (item.source_only || item.kind === "source_only") continue;
    const id = String(item.note_id || item.id || ""), title = typeof value === "string" ? sourceLabel(value) : String(item.title || "已保存笔记");
    const identity = id || title;
    if (!seen.has(identity)) notes.push({ id, title });
    seen.add(identity);
  }
  return notes;
}

export function updateJobView(job: UpdateJob, jobs: UpdateJob[], notes?: readonly (UpdateNote | string)[]) {
  const active = !["completed", "partial", "failed", "cancelled"].includes(job.status);
  const result = record(job.result), view = updateResultView(result, { active });
  const latest = latestUpdateAttempt(job, jobs);
  const errors = view.errors.length ? view.errors : job.error ? [{ source: "整理任务", error: job.error }] : [];
  const outstanding = (Array.isArray(result.outstanding) ? result.outstanding : []).map(record);
  const codes = (item: RecordValue) => [...(Array.isArray(item.turns) ? item.turns : []), ...(Array.isArray(item.reasons) ? item.reasons : [])]
    .map(value => String(record(value).reason_code || ""));
  const waitForSource = new Set(["running", "queued", "interrupted", "cancelled", "failed_turn", "read_limit"]);
  const nonRetryable = (item: RecordValue) => codes(item).length > 0 && codes(item).every(code => waitForSource.has(code));
  const pending = [...errors.map(updatePendingItem), ...outstanding.filter(item => !errors.some(error => {
    const failed = record(error);
    return item.thread_id && failed.thread_id ? item.thread_id === failed.thread_id : sourceLabel(item.title) === sourceLabel(failed.source);
  })).map(item => {
    const reasons = codes(item);
    const reason = typeof item.reason === "string" ? item.reason : "还有未完成的对话内容。";
    const action = reasons.every(code => waitForSource.has(code)) && /(?:完成后|继续原对话后)再整理/.test(reason) ? ""
      : reasons.includes("read_limit") ? "当前无法自动补齐；可通过“添加资料”收录所需内容。"
      : reasons.some(code => ["pagination_incomplete", "truncated_page", "truncated", "invalid_metadata"].includes(code)) ? "重新读取后补充，已完成内容保留。"
      : reasons.some(code => ["interrupted", "cancelled", "failed_turn"].includes(code)) ? "继续原对话后再补充，已完成内容保留。"
      : "原对话完成后再补充，已完成内容保留。";
    return {source: sourceLabel(item.title), reason, action};
  })];
  const scopes = record(result.sources), threads = record(scopes.threads);
  const coverage: string[] = [];
  if (typeof threads.historical_gap === "number" && threads.historical_gap > 0) coverage.push(`${threads.historical_gap} 条基线前历史对话未纳入本轮，仍保留历史缺口。`);
  if (typeof threads.pending === "number" && threads.pending > 0) coverage.push(`${threads.pending} 个轮次仍在执行或未读完，留待后续补充。`);
  if (typeof threads.metadata_gap === "number" && threads.metadata_gap > 0) coverage.push(`${threads.metadata_gap} 条对话的来源信息不完整，仍待核实。`);
  if (threads.status && !["checked", "disabled", "not_selected"].includes(String(threads.status)) && !coverage.length) coverage.push("对话来源尚未完整覆盖。");
  const previous = jobs.filter(item => item.id !== job.id && jobTime(item) < jobTime(job) && latestUpdateAttempt(item, [...jobs, job]).id === latest.id)
    .sort((a, b) => jobTime(b) - jobTime(a))[0];
  const previousIds = new Set(savedNotes(record(previous?.result).notes).map(note => note.id).filter(Boolean));
  const newIds = new Set(previous ? savedNotes(result.notes).filter(note => !previousIds.has(note.id)).map(note => note.id) : []);
  const current = savedNotes(notes === undefined ? result.notes : notes)
    .sort((a, b) => Number(newIds.has(b.id)) - Number(newIds.has(a.id)));
  const hasSaved = view.noteCount > 0 || current.length > 0;
  const unfinished = ["partial", "failed", "cancelled"].includes(job.status) || result.partial === true;
  const summary = active ? "正在整理，已保存的成果可先查看。"
    : pending.length ? `${hasSaved ? "已保存成果" : "本次整理未完成"}，另有 ${pending.length} 项待补。`
    : unfinished ? typeof threads.pending === "number" && threads.pending > 0
      ? `${hasSaved ? "已保存成果" : "尚未生成笔记"}，${threads.pending} 个对话轮次待补。`
      : coverage.length ? "本次可读内容已处理，来源列表尚未完整覆盖。" : "本次未取得完整结果，请查看待补原因。"
    : hasSaved ? "整理完成，成果已保存。" : "检查完成，本次没有新增知识。";
  const onlyNativeErrors = errors.length > 0 && errors.every(nativeReadLimit);
  const retryBlocked = (onlyNativeErrors && !outstanding.some(item => !nonRetryable(item))) ||
    (!errors.length && outstanding.length > 0 && outstanding.every(nonRetryable));
  return { ...view, errors, latest, superseded: latest.id !== job.id, active, pending, coverage, notes: current,
    summary, canRetry: !active && ["partial", "failed", "cancelled"].includes(job.status) && (!retryBlocked || result.sync_pending === true),
    retryLabel: result.sync_pending ? "重试同步" : "重试未完成来源",
    retryHint: errors.some(nativeReadLimit) ? "已保存和仅登记项会跳过；重试不会解除原生读取限制。" : "已保存和仅登记项会跳过。" };
}

export function updateResultView(value: unknown, options: { active?: boolean } = {}) {
  const result = record(value);
  const counts = record(result.counts);
  const checks = Array.isArray(result.source_checks) ? result.source_checks.map(record) : [];
  const errors = Array.isArray(result.errors) ? result.errors : [];
  const groups = new Map<string, number>();
  const registrationWarnings = new Set<string>();
  for (const check of checks) {
    const reason = typeof check.reason === "string" ? check.reason : "";
    const label = check.kind === "feishu" ? "飞书入口（仅元数据）"
      : reason === "空文件，没有可归档正文" ? "空文件"
      : reason === "表格数据，正文分析需使用专项流程" ? "表格数据（需专项分析）"
      : check.body_read === true ? "读后无可积累内容"
      : /凭据|配置文件/.test(reason) ? "敏感或配置文件（不读正文）"
      : /脚本或工程文件/.test(reason) ? "工程文件（不读正文）"
      : /不支持的文件格式/.test(reason) ? "暂不支持的格式（不读正文）"
      : "其他来源登记";
    groups.set(label, (groups.get(label) || 0) + 1);
    if (reason) registrationWarnings.add(reason + "，仅记录来源，未生成知识笔记");
  }
  const warnings = (Array.isArray(result.warnings) ? result.warnings : []).filter(warning =>
    typeof warning !== "string" || (!registrationWarnings.has(warning) &&
      !(checks.some(check => check.kind === "feishu") && /：仅登记飞书入口，未读取或总结正文$/.test(warning))));
  const nativeLimited = errors.some(error => /原生.*限制/.test(String(record(error).error || ""))) ||
    warnings.some(warning => typeof warning === "string" && /接口上限|原生.*限制/.test(warning));
  const noteCount = Array.isArray(result.notes) ? result.notes.length :
    Object.values(counts).reduce<number>((total, count) => total + (typeof count === "number" && count > 0 ? count : 0), 0);
  const noteSources = [["files", "文件"], ["threads", "对话"], ["feishu", "飞书正文"]]
    .filter(([key]) => typeof counts[key] === "number" && Number(counts[key]) > 0)
    .map(([key, label]) => `${label} ${counts[key]} 篇`).join(" · ");
  return {
    noteCount, noteSources, errors, warnings, nativeLimited,
    summary: noteCount ? `本轮累计保存 ${noteCount} 篇知识笔记。` : options.active ? "" : "本轮暂无新增知识笔记。",
    registrationCount: checks.length,
    registrations: Array.from(groups, ([label, count]) => ({ label, count })),
  };
}

export type SummarySelection = { threads: string[]; files: string[] };
export type SummaryRequest = { key: string; id: string };

export async function submitSummarySelection<T extends { id: string }>(
  selection: SummarySelection, identity: SummaryRequest,
  create: (kind: string, input: Record<string, unknown>, id: string) => Promise<T>,
  newId: () => string = () => crypto.randomUUID(),
): Promise<T> {
  const key = JSON.stringify({ threads: [...selection.threads].sort(), files: [...selection.files].sort() });
  if (identity.key !== key || !identity.id) { identity.key = key; identity.id = newId(); }
  const job = await create("update", { selection }, identity.id);
  if (job.id !== identity.id) throw new Error("已有其他整理任务在执行，本次选择未提交。完成后可再次确认。");
  return job;
}

export function updateStatusText(job: UpdateJob, jobs: UpdateJob[] = []): string {
  const view = updateJobView(job, jobs);
  if (view.superseded) return "已补跑";
  if (view.active) return job.status === "queued" ? "等待执行" : "正在整理";
  if (view.pending.length) return `${view.pending.length} 项待补`;
  if (job.status === "completed") return "已完成";
  if (job.status === "cancelled") return "已取消";
  if (job.status === "failed") return "执行失败";
  const rounds = record(record(record(job.result).sources).threads).pending;
  return typeof rounds === "number" && rounds > 0 ? `${rounds} 个轮次待补` : "来源覆盖待补";
}
