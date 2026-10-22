"use client";

import { ArrowRight, RefreshCw } from "lucide-react";
import { updateJobView, type UpdateJob, type UpdateNote } from "@/lib/update-result";
import RecoveryNotice from "./RecoveryNotice";

export type { UpdateJob, UpdateNote } from "@/lib/update-result";
type Props = {
  job: UpdateJob; jobs: UpdateJob[]; notes?: readonly (UpdateNote | string)[];
  historical?: readonly UpdateNote[]; unavailable?: number;
  onAdd?: () => void;
  onOpenJob: (id: string) => void; onRetry: (job: UpdateJob) => void; onOpenNote: (id: string) => void;
};

export default function UpdateResult({ job, jobs, notes, historical = [], unavailable = 0, onOpenJob, onRetry, onOpenNote, onAdd }: Props) {
  const view = updateJobView(job, jobs, notes);
  const noteLinks = (items: readonly UpdateNote[]) => items.map((note, index) => note.id
    ? <button className="note-link" key={note.id} onClick={() => onOpenNote(note.id)}><span>{note.title || "查看原记录"}</span><ArrowRight size={16} /></button>
    : <p key={`${note.title}-${index}`}>{note.title}</p>);
  const history = <>
    {historical.length > 0 && <details className="scope-details"><summary>已归档或合并 · {historical.length} 条</summary>{noteLinks(historical)}</details>}
    {unavailable > 0 && <details className="scope-details"><summary>未定位记录 · {unavailable} 条</summary><p className="muted">这些旧成果尚未定位到当前笔记，原处理记录仍保留。</p></details>}
  </>;
  const technical = <details className="scope-details"><summary>技术详情</summary><div className="markdown"><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}><code>{JSON.stringify({
    status: job.status, problems: view.pending.map(item => ({source:item.source,reason:item.reason})),
    counts: (job.result as Record<string, unknown> | null)?.counts,
    coverage: view.coverage,
  }, null, 2)}</code></pre></div></details>;
  if (view.superseded) {
    const nextActive = !["completed", "partial", "failed", "cancelled"].includes(view.latest.status);
    return <div className="update-result"><p><strong>{nextActive ? "后续补跑正在进行" : "已有更新结果"}</strong></p>
      <div className="result-actions"><button className="primary-button" onClick={() => onOpenJob(view.latest.id)}>{nextActive ? "查看当前进度" : "查看最新结果"}<ArrowRight size={16} /></button></div>
      <details className="scope-details"><summary>查看当时记录</summary><p className="muted">当时保存 {view.noteCount} 篇笔记、{view.errors.length} 项未完成；当前情况请查看最新结果。</p>{history}{technical}</details>
    </div>;
  }
  return <div className="update-result">{(view.active || (!view.pending.length && (!view.notes.length || job.status !== "completed"))) && <p role="status">{view.summary}</p>}
    {view.notes.length > 0 && <section className="written-notes"><h3>已完成</h3>{noteLinks(view.notes.slice(0, 5))}
      {view.notes.length > 5 && <details><summary>查看全部 {view.notes.length} 篇成果</summary>{noteLinks(view.notes.slice(5))}</details>}
    </section>}
    {view.pending.length > 0 && <section className="written-notes"><h3>待补 · {view.pending.length} 项</h3>{view.pending.map((item, index) => <div key={index}>{item.issue ? <><h4>{item.source}</h4><RecoveryNotice error={item.issue} context="整理来源" onAdd={onAdd} compact /></> : <><div><strong>{item.source}</strong>：{item.reason}</div>{item.action && <div className="muted">{item.action}</div>}</>}</div>)}</section>}
    {view.canRetry && <><div className="result-actions"><button className="primary-button" onClick={() => onRetry(job)}><RefreshCw size={16} />{view.retryLabel}</button></div><p className="muted">{view.retryHint}</p></>}
    {view.registrationCount > 0 && <details className="scope-details"><summary>已跳过总结 · {view.registrationCount} 项</summary><p className="muted">已按规则登记，不生成知识笔记。</p><ul>{view.registrations.map(group => <li key={group.label}>{group.label} · {group.count} 项</li>)}</ul></details>}
    {view.coverage.length > 0 && <details className="scope-details"><summary>覆盖范围</summary><ul>{view.coverage.map(item => <li key={item}>{item}</li>)}</ul></details>}
    {history}
    {technical}
  </div>;
}
