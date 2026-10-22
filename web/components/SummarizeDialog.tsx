"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";

type Candidate = { id: string; kind: "thread" | "file"; title: string; group?: string; selected?: boolean; path?: string };
type Preview = { candidates: Candidate[]; warnings?: string[]; excluded?: { reason: string; count: number }[] };
type Task = { id: string; status: string; stage?: string; error?: string; result?: Preview };
type Props = {
  online: boolean;
  request: <T>(path: string, body?: unknown) => Promise<T>;
  onClose: () => void;
  onStart: (selection: { threads: string[]; files: string[] }) => Promise<void>;
};
const TERMINAL = new Set(["completed", "partial", "failed", "cancelled"]);

export default function SummarizeDialog({ online, request, onClose, onStart }: Props) {
  const [includeFiles, setIncludeFiles] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [stage, setStage] = useState("正在查找新增对话…");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const dialog = useRef<HTMLDivElement>(null);
  const choices = useRef(new Map<string, boolean>());

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.querySelector<HTMLElement>("button")?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape" && !submitting) onClose();
      if (event.key !== "Tab") return;
      const nodes = Array.from(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled),input:not(:disabled),summary,[href]") || []);
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", keydown);
    return () => { document.body.style.overflow = overflow; document.removeEventListener("keydown", keydown); previous?.focus(); };
  }, [onClose, submitting]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setPreview(null); setError(""); setStage(online ? "正在查找新增内容…" : "等待本机连接后读取候选内容");
    const requestId = crypto.randomUUID();
    let owned: Task | null = null;
    const cancelOwned = (id: string) => { void request(`jobs/${id}/cancel`, {}).catch(() => undefined); };
    async function read(task: Task) {
      owned = task;
      if (cancelled) { if (!TERMINAL.has(task.status)) cancelOwned(task.id); return; }
      if (!TERMINAL.has(task.status)) {
        setStage(task.status === "queued" ? "等待本机读取候选内容…" : /文件/.test(task.stage || "") ? "正在筛选本机资料…" : "正在查找新增对话…");
        timer = setTimeout(() => { void request<Task>(`jobs/${task.id}`).then(read).catch(fail); }, 1500);
        return;
      }
      if (!task.result || !Array.isArray(task.result.candidates)) throw new Error(task.error || "未取得候选内容，请重试。");
      setPreview(task.result);
      setSelected(new Set(task.result.candidates.filter(item => choices.current.get(item.id) ?? item.selected).map(item => item.id)));
      setStage("");
    }
    function fail(cause: unknown) { if (!cancelled) { setError(cause instanceof Error ? cause.message : "读取候选内容失败。"); setStage(""); } }
    void request<Task>("jobs", { kind: "update_preview", input: { include_files: includeFiles, refresh: attempt > 0 }, request_id: requestId }).then(read).catch(fail);
    return () => { cancelled = true; if (timer) clearTimeout(timer); if (!owned || !TERMINAL.has(owned.status)) cancelOwned(owned?.id || requestId); };
  }, [includeFiles, attempt, request]);

  function toggle(id: string) { setSelected(previous => { const next = new Set(previous); if (next.has(id)) { next.delete(id); choices.current.set(id, false); } else { next.add(id); choices.current.set(id, true); } return next; }); }
  async function start() {
    if (!preview || !selected.size) return;
    setSubmitting(true); setError("");
    try {
      const rows = preview.candidates.filter(item => selected.has(item.id));
      await onStart({ threads: rows.filter(item => item.kind === "thread").map(item => item.id), files: rows.filter(item => item.kind === "file").map(item => item.path || item.id) });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "总结未启动。"); setSubmitting(false); }
  }

  return <div className="modal-overlay summary-overlay" onMouseDown={event => { if (event.target === event.currentTarget && !submitting) onClose(); }}>
    <div className="upload-modal summary-modal" role="dialog" aria-modal="true" aria-labelledby="summary-title" ref={dialog}>
      <div className="drawer-heading"><div><h2 id="summary-title">选择总结内容</h2><p>默认检查新增对话和续聊，已有笔记跳过。</p></div><button className="icon-button" aria-label="关闭内容选择" disabled={submitting} onClick={onClose}><X size={20} /></button></div>
      <div className="summary-content">
        <label className="summary-file-option"><input type="checkbox" checked={includeFiles} disabled={submitting} onChange={event => setIncludeFiles(event.target.checked)} /><span>加入本机资料<span className="muted">仅查已配置的资料目录，文件需手动勾选。</span></span></label>
        {stage && <div className="waiting-state" role="status"><Loader2 size={18} className="spin" />{stage}</div>}
        {error && <div className="inline-error" role="alert">{error}<button className="text-button" onClick={() => setAttempt(value => value + 1)}>重新读取</button></div>}
        {preview && <>
          {(["thread", "file"] as const).map(kind => {
            const rows = preview.candidates.filter(item => item.kind === kind);
            if (!rows.length) return null;
            const all = rows.every(item => selected.has(item.id));
            return <section className="summary-group" key={kind}><div className="section-heading"><h3>{kind === "thread" ? "对话" : "本机资料"} · {rows.length}</h3><button className="text-button" disabled={submitting} onClick={() => setSelected(previous => { const next = new Set(previous); for (const item of rows) { choices.current.set(item.id, !all); if (all) next.delete(item.id); else next.add(item.id); } return next; })}>{all ? "取消全选" : "全选"}</button></div>
              <div className="summary-candidates">{rows.map(item => <label key={item.id} className="summary-candidate"><input type="checkbox" checked={selected.has(item.id)} disabled={submitting} onChange={() => toggle(item.id)} /><span><strong>{item.title}</strong>{item.group && <small>{item.group}</small>}</span></label>)}</div>
            </section>;
          })}
          {!preview.candidates.length && <p className="summary-empty">{preview.warnings?.length ? "当前未取得可选内容，请查看未覆盖来源。" : "没有需要总结的新增内容。"}</p>}
          {Boolean(preview.excluded?.length) && <details className="summary-exclusions"><summary>已筛除的内容</summary><ul>{preview.excluded!.map(item => <li key={item.reason}>{item.reason} · {item.count}</li>)}</ul></details>}
          {Boolean(preview.warnings?.length) && <details className="summary-exclusions"><summary>来源范围有未覆盖项</summary><ul>{preview.warnings!.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
        </>}
      </div>
      <div className="drawer-footer summary-footer"><span>{preview ? `已选 ${selected.size} 项` : "读取候选内容后再开始"}</span><button className="primary-button" disabled={!preview || !selected.size || submitting} onClick={() => void start()}>{submitting ? <Loader2 size={16} className="spin" /> : null}{submitting ? "正在启动" : "总结所选内容"}</button></div>
    </div>
  </div>;
}
