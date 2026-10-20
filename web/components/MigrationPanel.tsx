"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowRight, CheckCircle2, Clock3, FileArchive, Loader2, Monitor, Upload, X } from "lucide-react";

const API = "/api/workspace";
const EXPORT_KEY = "obsidian-workspace-migration-export";
const OPERATION_KEY = "obsidian-workspace-migration-operation";
const WINDOWS_PACKAGE = "https://github.com/zhangzeyu99-web/file-management-assistant/releases/download/v0.3.0/Obsidian-Workspace-Windows.zip";
const LOCAL_WORKSPACE = "http://127.0.0.1:5174/#migration";
const TERMINAL = new Set(["completed", "partial", "failed", "cancelled"]);
const CHUNK_SIZE = 4 * 1024 * 1024;

type MigrationStatus = {
  mode: string; configured: boolean; default_destination?: string; device?: string;
  can_export: boolean; online: boolean; import_limit_bytes?: number; export_limit_bytes?: number;
};
type ExportJob = {
  id: string; kind?: string; status: string; stage?: string; error?: string;
  result?: { download_url?: string; filename?: string; message?: string };
};
type Preview = {
  upload_id: string; destination: string; ready: boolean; warnings?: string[];
  summary: { vault_files: number; notes: number; files: number; threads: number; feishu: number };
};
type Operation = {
  status: string; stage?: string; error?: string;
  result?: { activated?: boolean; config_path?: string; vault?: string; note_count?: number };
};
type Props = {
  mode?: string; online?: boolean; setupRequired?: boolean; exportJobId?: string;
  onActivated: (noteCount?: number) => Promise<void>;
  onJobsChanged: () => Promise<unknown>;
};

class ResponseError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function readResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  let data: unknown;
  try { data = JSON.parse(text); }
  catch { throw new Error(`连接未完成（${response.status}），请重试。`); }
  if (!response.ok) {
    const message = data && typeof data === "object" && "error" in data ? String(data.error) : "";
    throw new ResponseError(message || `操作未完成（${response.status}）`, response.status);
  }
  return data as T;
}

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  return readResponse<T>(await fetch(`${API}/${path}`, {
    method: body === undefined ? "GET" : "POST", cache: "no-store", signal,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }));
}

function message(cause: unknown, fallback: string) {
  return cause instanceof Error ? cause.message : fallback;
}
function sizeLabel(bytes: number) {
  return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB` : `${Math.max(0.1, bytes / 1024 ** 2).toFixed(1)} MB`;
}
function remember(key: string, value: string) {
  try { if (value) localStorage.setItem(key, value); else localStorage.removeItem(key); }
  catch { /* Transfer does not depend on browser storage. */ }
}
function recalled(key: string) {
  try { return localStorage.getItem(key) || ""; } catch { return ""; }
}
function downloadUrl(value?: string) {
  if (!value || typeof window === "undefined") return "";
  try {
    const url = new URL(value.startsWith("/") ? value : `${API}/${value}`, window.location.origin);
    return url.origin === window.location.origin && url.pathname.startsWith(`${API}/`) ? url.href : "";
  } catch { return ""; }
}

export default function MigrationPanel({ mode, online, setupRequired, exportJobId, onActivated, onJobsChanged }: Props) {
  const [status, setStatus] = useState<MigrationStatus | null>(null);
  const [statusError, setStatusError] = useState("");
  const [exportJob, setExportJob] = useState<ExportJob | null>(null);
  const [exportId, setExportId] = useState("");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploadId, setUploadId] = useState("");
  const [uploaded, setUploaded] = useState(0);
  const [phase, setPhase] = useState<"idle" | "uploading" | "checking" | "ready" | "committing" | "importing" | "done" | "cancelled">("idle");
  const [destination, setDestination] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [importError, setImportError] = useState("");
  const [operationId, setOperationId] = useState("");
  const [operation, setOperation] = useState<Operation | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [commitUncertain, setCommitUncertain] = useState(false);
  const uploadController = useRef<AbortController | null>(null);
  const uploadSequence = useRef(0);
  const currentUpload = useRef({ id: "", committed: false });
  const cleanups = useRef(new Map<string, Promise<void>>());
  const exportRequest = useRef("");
  const activated = useRef("");
  const callbacks = useRef({ onActivated, onJobsChanged });
  callbacks.current = { onActivated, onJobsChanged };

  const releaseUpload = useCallback((id: string) => {
    const existing = cleanups.current.get(id);
    if (existing) return existing;
    const pending = request("migration/import/cancel", { upload_id: id }).then(() => {
      if (currentUpload.current.id === id) currentUpload.current = { id: "", committed: false };
    }).catch(cause => { cleanups.current.delete(id); throw cause; });
    cleanups.current.set(id, pending);
    return pending;
  }, []);

  const refreshStatus = useCallback(async () => {
    const next = await request<MigrationStatus>("migration/status");
    setStatus(next);
    setStatusError("");
    setDestination(current => current || next.default_destination || "");
    return next;
  }, []);

  useEffect(() => {
    let active = true;
    void refreshStatus().then(next => {
      if (active && !next.configured && next.mode === "local") {
        setExportId(""); setExportJob(null); remember(EXPORT_KEY, "");
      }
    }).catch(cause => { if (active) setStatusError(message(cause, "暂时无法读取迁移状态。")); });
    setExportId(exportJobId || recalled(EXPORT_KEY));
    if (mode !== "cloud") {
      const saved = recalled(OPERATION_KEY);
      if (saved) {
        try {
          const previous = JSON.parse(saved);
          if (typeof previous.operation_id === "string") {
            setOperationId(previous.operation_id); setPhase("importing");
            if (typeof previous.upload_id === "string") setUploadId(previous.upload_id);
            if (typeof previous.destination === "string") setDestination(previous.destination);
            if (previous.preview?.ready && previous.preview.summary) setPreview(previous.preview);
            currentUpload.current = { id: previous.upload_id || "", committed: true };
          }
        } catch { setOperationId(saved); }
      }
    }
    return () => { active = false; };
  }, [refreshStatus, exportJobId, mode]);

  useEffect(() => () => {
    uploadSequence.current++;
    uploadController.current?.abort();
    const current = currentUpload.current;
    if (current.id && !current.committed) void releaseUpload(current.id).catch(() => undefined);
  }, [releaseUpload]);

  useEffect(() => {
    if (!exportId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      let terminal = false;
      try {
        const job = await request<ExportJob>(`jobs/${encodeURIComponent(exportId)}`, undefined, controller.signal);
        if (controller.signal.aborted) return;
        setExportJob(job);
        setExportError("");
        terminal = TERMINAL.has(job.status);
      } catch (cause) {
        if (!controller.signal.aborted) {
          if (cause instanceof ResponseError && cause.status === 404) {
            setExportId(""); setExportJob(null); remember(EXPORT_KEY, "");
            setExportError("以前的导出记录已不可用，可以重新导出迁移包。");
            terminal = true;
          } else {
            setExportError(`${message(cause, "暂时无法读取导出进度。")} 已保留本次请求，连接恢复后继续检查。`);
          }
        }
      }
      if (!controller.signal.aborted && !terminal) timer = setTimeout(poll, 3000);
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [exportId, refreshKey]);

  useEffect(() => {
    if (!operationId || (status?.mode || mode) === "cloud") return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      let terminal = false;
      try {
        const next = await request<Operation>(`migration/operations/${encodeURIComponent(operationId)}`, undefined, controller.signal);
        if (controller.signal.aborted) return;
        setOperation(next);
        setImportError("");
        terminal = TERMINAL.has(next.status);
        if (next.status === "completed") {
          setPhase("done");
          if (next.result?.activated && activated.current !== operationId) {
            await callbacks.current.onActivated(next.result.note_count);
            activated.current = operationId;
            remember(OPERATION_KEY, "");
            remember(EXPORT_KEY, "");
          } else if (!next.result?.activated) {
            setImportError("资料已恢复，但还没有切换到新知识库。请重新检查连接。");
          }
        } else if (terminal) {
          setPhase(next.status === "cancelled" ? "cancelled" : "ready");
          setImportError(next.error || (next.status === "cancelled" ? "" : "导入未完成，现有知识库没有切换。"));
          if (next.status === "cancelled") remember(OPERATION_KEY, "");
        } else {
          setPhase("importing");
        }
      } catch (cause) {
        if (!controller.signal.aborted) {
          if (cause instanceof ResponseError && (cause.status === 400 || cause.status === 404)) {
            setPhase("idle"); setOperationId(""); setPreview(null); setUploadId(""); remember(OPERATION_KEY, "");
            setImportError("本机没有这条迁移记录，请重新选择迁移包；已有资料不会被覆盖。");
            terminal = true;
          } else {
            setImportError(`${message(cause, "暂时无法读取导入进度。")} 还未确认结果，请勿重复导入。`);
            terminal = false;
          }
        }
      }
      if (!controller.signal.aborted && !terminal) timer = setTimeout(poll, 2000);
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [operationId, refreshKey, mode, status?.mode]);

  const cloud = (status?.mode || mode) === "cloud";
  const connected = online ?? status?.online ?? false;
  const exportActive = Boolean(exportId && (!exportJob || !TERMINAL.has(exportJob.status)));
  const exportLink = exportJob?.status === "completed" ? downloadUrl(exportJob.result?.download_url) : "";
  const importing = phase === "committing" || phase === "importing";
  const activationPending = operation?.status === "failed" && operation.result?.activated === false;
  const transferring = phase === "uploading" || phase === "checking";
  const destinationChanged = Boolean(preview && destination.trim() !== preview.destination);
  const sourceCount = preview ? preview.summary.files + preview.summary.threads + preview.summary.feishu : 0;

  async function beginExport() {
    setExportBusy(true); setExportError("");
    try {
      exportRequest.current ||= crypto.randomUUID();
      const job = await request<ExportJob>("jobs", { kind: "migration_export", input: {}, request_id: exportRequest.current });
      exportRequest.current = "";
      setExportJob(job); setExportId(job.id); remember(EXPORT_KEY, job.id);
      await callbacks.current.onJobsChanged().catch(() => undefined);
    } catch (cause) { setExportError(message(cause, "导出请求尚未确认，请重试。")); }
    finally { setExportBusy(false); }
  }

  async function cancelExport() {
    if (!exportId) return;
    setExportBusy(true);
    try {
      const job = await request<ExportJob>(`jobs/${encodeURIComponent(exportId)}/cancel`, {});
      setExportJob(job);
      setRefreshKey(value => value + 1);
      await callbacks.current.onJobsChanged().catch(() => undefined);
    } catch (cause) { setExportError(message(cause, "取消未确认，请重试。")); }
    finally { setExportBusy(false); }
  }

  async function checkPreview(id: string, target: string, signal?: AbortSignal) {
    const checked = await request<Preview>("migration/import/preview", {
      upload_id: id, ...(target.trim() ? { destination: target.trim() } : {}),
    }, signal);
    if (!checked.ready) throw new Error("迁移包还不能导入，请检查文件与存放位置。");
    return checked;
  }

  async function uploadFile(chosen: File) {
    uploadController.current?.abort();
    const controller = new AbortController();
    uploadController.current = controller;
    const sequence = ++uploadSequence.current;
    if (uploadId && !operationId && !commitUncertain) {
      setPhase("checking");
      try { await releaseUpload(uploadId); }
      catch (cause) {
        if (sequence !== uploadSequence.current) return;
        setPhase("idle"); setImportError(message(cause, "上一份暂存文件未清理，请重试。")); return;
      }
    }
    if (sequence !== uploadSequence.current) return;
    setFile(chosen); setPreview(null); setUploadId(""); setUploaded(0); setImportError("");
    setOperation(null); setOperationId(""); setCommitUncertain(false); remember(OPERATION_KEY, "");
    if (!/\.zip$/i.test(chosen.name) || !chosen.size) {
      setPhase("idle"); setImportError("请选择工作台导出的 ZIP 迁移包。"); return;
    }
    if (status?.import_limit_bytes && chosen.size > status.import_limit_bytes) {
      setPhase("idle"); setImportError(`迁移包超过本机接收上限（${sizeLabel(status.import_limit_bytes)}）。`); return;
    }
    setPhase("uploading");
    try {
      const started = await request<{ upload_id: string; chunk_size: number }>("migration/import/start", {
        filename: chosen.name, size: chosen.size,
      }, controller.signal);
      if (sequence !== uploadSequence.current) return;
      setUploadId(started.upload_id);
      currentUpload.current = { id: started.upload_id, committed: false };
      const chunkSize = Math.min(CHUNK_SIZE, started.chunk_size > 0 ? started.chunk_size : CHUNK_SIZE);
      for (let offset = 0; offset < chosen.size; offset += chunkSize) {
        const end = Math.min(offset + chunkSize, chosen.size);
        await readResponse(await fetch(`${API}/migration/import/chunk?upload_id=${encodeURIComponent(started.upload_id)}&offset=${offset}`, {
          method: "POST", headers: { "Content-Type": "application/octet-stream" },
          body: chosen.slice(offset, end), signal: controller.signal,
        }));
        if (sequence !== uploadSequence.current) return;
        setUploaded(end);
      }
      setPhase("checking");
      const checked = await checkPreview(started.upload_id, destination, controller.signal);
      if (sequence !== uploadSequence.current) return;
      setPreview(checked); setDestination(checked.destination); setPhase("ready");
    } catch (cause) {
      if (sequence !== uploadSequence.current) return;
      if (controller.signal.aborted) { setPhase("cancelled"); return; }
      setPhase("idle"); setImportError(message(cause, "没有完整收到迁移包，请重新选择文件。"));
    }
  }

  function cancelUpload() {
    const sequence = ++uploadSequence.current;
    uploadController.current?.abort();
    setPhase("cancelled"); setPreview(null); setImportError("");
    if (uploadId) {
      void releaseUpload(uploadId).then(() => {
        if (sequence === uploadSequence.current) setUploadId("");
      }).catch(cause => {
        if (sequence === uploadSequence.current) setImportError(`${message(cause, "暂存清理未完成。")} 上传已停止，尚未导入。`);
      });
    }
  }

  async function refreshPreview() {
    if (!uploadId || !destination.trim()) return;
    const controller = new AbortController();
    uploadController.current = controller;
    const sequence = ++uploadSequence.current;
    setPhase("checking"); setImportError("");
    try {
      const checked = await checkPreview(uploadId, destination, controller.signal);
      if (sequence !== uploadSequence.current) return;
      setPreview(checked); setDestination(checked.destination); setPhase("ready");
    } catch (cause) {
      if (sequence !== uploadSequence.current) return;
      setPhase("ready"); setImportError(message(cause, "存放位置未通过检查。"));
    }
  }

  async function commitImport() {
    if (!uploadId || !preview || destinationChanged || !destination.trim()) return;
    setPhase("committing"); setImportError("");
    currentUpload.current.committed = true;
    try {
      const next = await request<{ operation_id: string }>("migration/import/commit", {
        upload_id: uploadId, destination: preview.destination,
      });
      setCommitUncertain(false); setOperationId(next.operation_id); setPhase("importing");
      remember(OPERATION_KEY, JSON.stringify({ operation_id: next.operation_id, upload_id: uploadId, destination: preview.destination, preview }));
    } catch (cause) {
      const uncertain = !(cause instanceof ResponseError && cause.status < 500);
      if (!uncertain) currentUpload.current.committed = false;
      setPhase("ready"); setCommitUncertain(uncertain);
      setImportError(`${message(cause, "导入请求尚未确认。")}${uncertain ? " 请用下方按钮确认本次请求。" : ""}`);
    }
  }

  return <div className={`migration-page ${setupRequired ? "migration-setup" : ""}`}>
    <div className="page-heading"><span className="eyebrow">{setupRequired ? "在这台电脑继续使用" : "把积累带到下一台电脑"}</span><h1>备份与迁移</h1><p>带走笔记和整理记录，换电脑后接着用。</p></div>
    {statusError && <div className="inline-error" role="alert">{statusError}<button className="text-button" onClick={() => void refreshStatus().catch(cause => setStatusError(message(cause, "连接未完成。")))}>重新连接</button></div>}
    {!status && !statusError && <div className="waiting-state"><Loader2 size={18} className="spin" />正在读取迁移状态…</div>}
    <div className="migration-columns">
      <section className="migration-section" aria-labelledby="migration-export-title">
        <div className="migration-section-title"><ArrowDownToLine size={22} /><h2 id="migration-export-title">导出迁移包</h2></div>
        <p className="migration-description">保存笔记、附件和已整理记录。导入后跳过已处理资料。</p>
        {!status?.configured && status && <p className="migration-hint">这台电脑尚未导入知识库，导入后即可备份。</p>}
        {status?.configured && !connected && <p className="migration-waiting"><Clock3 size={16} />{cloud ? "旧电脑暂未连接，导出请求会等待它上线。" : "本机执行器暂未连接，导出请求将等待恢复。"}</p>}
        {!exportActive && <button className={exportLink ? "secondary-button" : "primary-button"} disabled={!status || !status.can_export || exportBusy || importing} onClick={() => void beginExport()}>{exportBusy ? <Loader2 size={16} className="spin" /> : <ArrowDownToLine size={16} />}{exportLink ? "重新导出" : exportJob?.status === "failed" || exportJob?.status === "partial" ? "重新导出迁移包" : "导出迁移包"}</button>}
        {exportActive && <div className="migration-progress" role="status"><div><Loader2 size={18} className="spin" /><strong>{!connected || exportJob?.status === "queued" ? "等待本机准备迁移包" : exportJob?.stage || "正在准备迁移包"}</strong></div><p>完成后会在这里出现下载按钮。</p><button className="text-button" disabled={exportBusy} onClick={() => void cancelExport()}>取消导出</button></div>}
        {exportLink && <div className="migration-success" role="status"><div><CheckCircle2 size={20} /><strong>迁移包已准备好</strong></div><a className="primary-button" href={exportLink} download={exportJob?.result?.filename || "知识工作台迁移包.zip"}><ArrowDownToLine size={17} />下载迁移包</a></div>}
        {exportJob?.status === "completed" && !exportLink && <div className="inline-error" role="alert">迁移包没有可用下载地址，请重新导出。</div>}
        {["failed", "partial"].includes(exportJob?.status || "") && <div className="inline-error" role="alert">{exportJob?.error || exportJob?.result?.message || "迁移包未生成完成，请重新导出。"}</div>}
        {exportJob?.status === "cancelled" && <p className="migration-hint" role="status">导出已取消。</p>}
        {exportError && <div className="inline-error" role="alert">{exportError}<button className="text-button" onClick={() => setRefreshKey(value => value + 1)}>重新检查</button></div>}
        <p className="migration-footnote">不包含登录凭据或待执行任务。资料包含个人内容，请自行保管。</p>
        {cloud && <p className="migration-hint">线上导出上限 {sizeLabel(status?.export_limit_bytes || 128 * 1024 * 1024)}，下载链接 24 小时内有效。</p>}
      </section>
      <section className="migration-section" aria-labelledby="migration-import-title">
        <div className="migration-section-title"><Upload size={22} /><h2 id="migration-import-title">导入迁移包</h2></div>
        {cloud ? <>
          <p className="migration-description">导入到你正在使用的电脑。请在这台电脑打开本机工作台。</p>
          <a className="primary-button" href={LOCAL_WORKSPACE} target="_blank" rel="noopener noreferrer"><Monitor size={17} />在这台电脑打开工作台 <ArrowRight size={16} /></a>
          <div className="migration-install"><h3>新电脑还没有工作台？</h3><a className="secondary-button" href={WINDOWS_PACKAGE}><ArrowDownToLine size={16} />下载 Windows 启动包</a><p>解压后双击「打开工作台.cmd」。已安装 Python 和 Node.js 时会自动准备依赖。</p></div>
        </> : <>
          <p className="migration-description">选择旧电脑导出的 ZIP，在独立目录恢复。现有知识库会保留。</p>
          {!importing && phase !== "done" && !commitUncertain && !activationPending && <label className={`migration-file ${transferring ? "disabled" : ""}`}>
            <FileArchive size={24} /><span><strong>{file?.name || "选择迁移包"}</strong><small>{file ? `${sizeLabel(file.size)} · 点击重新选择` : "工作台导出的 ZIP 文件"}</small></span>
            <input type="file" accept=".zip,application/zip" aria-label="选择迁移包" disabled={!status || transferring} onChange={event => { const chosen = event.target.files?.[0]; if (chosen) void uploadFile(chosen); event.target.value = ""; }} />
          </label>}
          {transferring && <div className="migration-progress" role="status"><div><Loader2 size={17} className="spin" /><strong>{phase === "uploading" ? `正在传到本机 · ${file ? Math.floor(uploaded / file.size * 100) : 0}%` : "正在检查迁移包"}</strong><button className="icon-button" aria-label="取消上传" onClick={cancelUpload}><X size={17} /></button></div><progress max={file?.size || 1} value={uploaded} aria-label="迁移包上传进度" /><p>{sizeLabel(uploaded)} / {sizeLabel(file?.size || 0)}</p></div>}
          {phase === "cancelled" && <p className="migration-hint" role="status">已取消，迁移包没有导入。</p>}
          {preview && !importing && phase !== "done" && <>
            <dl className="migration-summary"><div><dt>知识笔记</dt><dd>{preview.summary.notes}<span>篇</span></dd></div><div><dt>已处理来源</dt><dd>{sourceCount}<span>条</span></dd></div></dl>
            <p className="migration-hint">文件 {preview.summary.files} · 对话 {preview.summary.threads} · 飞书 {preview.summary.feishu}，沿用已有整理记录。</p>
            <label className="field-label" htmlFor="migration-destination">存放位置</label>
            <input id="migration-destination" value={destination} disabled={transferring || commitUncertain || activationPending} onChange={event => { setDestination(event.target.value); setImportError(""); }} autoComplete="off" spellCheck={false} />
            {(preview.warnings || []).length > 0 && <ul className="migration-warnings">{preview.warnings?.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
            <div className="migration-commit"><button className="primary-button" disabled={transferring || !destination.trim()} onClick={() => void (destinationChanged ? refreshPreview() : commitImport())}>{destinationChanged ? "检查新位置" : commitUncertain ? "确认本次导入请求" : activationPending ? "重试启用工作台" : "导入并使用"}{!destinationChanged && <ArrowRight size={16} />}</button><p>{activationPending ? "资料已经恢复，重试只会继续启用，不会重复导入。" : "恢复完成后切换到新库，不覆盖原有资料。"}</p></div>
          </>}
          {importing && <div className="migration-progress" role="status"><div><Loader2 size={20} className="spin" /><strong>{operation?.stage || (phase === "committing" ? "正在提交导入" : "正在恢复资料")}</strong></div><p>请保持本机工作台运行，完成后自动打开知识库。</p></div>}
          {phase === "done" && <div className="migration-success" role="status"><div><CheckCircle2 size={21} /><strong>{operation?.result?.activated ? "资料已恢复，正在打开知识库" : "资料已恢复"}</strong></div>{!operation?.result?.activated && <button className="secondary-button" onClick={() => setRefreshKey(value => value + 1)}>检查切换状态</button>}</div>}
          {importError && <div className="inline-error" role="alert">{importError}{operationId && <button className="text-button" onClick={() => setRefreshKey(value => value + 1)}>重新检查进度</button>}</div>}
          {importError && !preview && !importing && file && !operationId && <button className="secondary-button" onClick={() => void uploadFile(file)}>重新上传这个文件</button>}
        </>}
      </section>
    </div>
  </div>;
}
