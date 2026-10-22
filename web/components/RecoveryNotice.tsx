"use client";

import { useMemo, useState } from "react";
import { userIssue } from "@/lib/user-errors";

type Props = { error: unknown; context?: string; onRetry?: () => void; retryLabel?: string; onAdd?: () => void; compact?: boolean };
export default function RecoveryNotice({ error, context, onRetry, retryLabel = "重新检查", onAdd, compact = false }: Props) {
  const issue = useMemo(() => userIssue(error, { context }), [error, context]);
  const [copied, setCopied] = useState(false);
  const canAdd = /^(native_|file_|invalid_encoding|unsupported_format|invalid_pdf|invalid_docx|encrypted_pdf)/.test(issue.code);
  const help = issue.help ? `#help=${encodeURIComponent(issue.help)}` : "";
  return <div className={`recovery-notice${compact ? " compact" : ""}`} role="alert">
    <p className="recovery-problem"><strong>{issue.message}</strong></p>
    {issue.action && <p>{issue.action}</p>}
    <div className="recovery-actions">
      {onRetry && issue.retryable && <button type="button" className="secondary-button" onClick={onRetry}>{retryLabel}</button>}
      {onAdd && canAdd && <button type="button" className="secondary-button" onClick={onAdd}>添加正文</button>}
      {issue.code === "note_missing" && <a className="text-button" href="#projects">返回知识目录</a>}
      {["migration_local_required","local_offline"].includes(issue.code) && <a className="text-button" href={issue.code === "migration_local_required" ? "http://127.0.0.1:5174/#migration" : "http://127.0.0.1:5174/"}>打开本机工作台</a>}
      {["task_busy", "migration_busy", "task_not_retryable", "request_not_found"].includes(issue.code) && <a className="text-button" href="#updates">查看更新记录</a>}
      {help && <a className="text-button" href={help}>查看操作步骤</a>}
    </div>
    <details className="recovery-diagnostic"><summary>诊断信息</summary><pre>{issue.diagnostic}</pre><button type="button" className="text-button" onClick={() => { void navigator.clipboard.writeText(issue.diagnostic).then(() => setCopied(true)).catch(() => setCopied(false)); }}>{copied ? "已复制" : "复制诊断信息"}</button></details>
  </div>;
}
