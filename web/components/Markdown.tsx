"use client";

import { Fragment, type ReactNode } from "react";
import { Copy } from "lucide-react";

export function safeLink(value: string): boolean {
  return /^(https?:\/\/|#)/i.test(value)
    || /^codex:\/\/threads?\/[0-9a-f-]{36}$/i.test(value)
    || /^obsidian:\/\/open\?/i.test(value);
}

type Props = { text: string; onWikiLink?: (name: string) => void; onCopy?: (text: string) => void };

export default function Markdown({ text, onWikiLink, onCopy }: Props) {
  function inline(value: string): ReactNode[] {
    const pattern = /(\[\[[^\]]+\]\]|\[[^\]]+\]\([^)]+\)|`[^`]+`|\*\*[^*]+\*\*|<https?:\/\/[^\s<>]+>|https?:\/\/[^\s<>]+|codex:\/\/threads?\/[a-z0-9-]+)/gi;
    const output: ReactNode[] = [];
    let previous = 0;
    for (const match of value.matchAll(pattern)) {
      if (match.index! > previous) output.push(value.slice(previous, match.index));
      const token = match[0];
      let node: ReactNode = token;
      if (token.startsWith("[[")) {
        const [target, label] = token.slice(2, -2).split("|");
        node = onWikiLink ? <button className="inline-link" onClick={() => onWikiLink(target.split("#")[0])}>{label || target}</button> : label || target;
      } else if (token.startsWith("**")) node = <strong>{token.slice(2, -2)}</strong>;
      else if (token.startsWith("`")) node = <code>{token.slice(1, -1)}</code>;
      else {
        const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        const autolink = token.match(/^<(https?:\/\/[^\s<>]+)>$/i);
        const rawHref = link ? link[2].trim() : autolink ? autolink[1] : token.replace(/[。，；]+$/, "");
        const href = rawHref.startsWith("<") && rawHref.endsWith(">") ? rawHref.slice(1, -1) : rawHref;
        const label = link ? link[1] : href;
        if (safeLink(href)) node = <a href={href} target={/^https?:/i.test(href) ? "_blank" : undefined} rel="noopener noreferrer">{label}</a>;
        else if (/^file:\/\//i.test(href)) node = <span className="local-reference">{label}{onCopy && <button title="复制本机来源地址" aria-label={`复制${label}的来源地址`} onClick={() => onCopy(href)}><Copy size={13} /></button>}</span>;
        else node = label;
      }
      output.push(<Fragment key={`${match.index}-${token}`}>{node}</Fragment>);
      previous = match.index! + token.length;
    }
    if (previous < value.length) output.push(value.slice(previous));
    return output;
  }

  const lines = (text || "").replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "")
    .replace(/<!--\s*obsidian-workspace task:[\s\S]*?-->/g, "")
    .replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const start = i, line = lines[i];
    if (!line.trim()) { i++; continue; }
    const fence = line.match(/^\s*(```|~~~)(.*)$/);
    if (fence) {
      i++; const code: string[] = [];
      while (i < lines.length && !lines[i].trimStart().startsWith(fence[1])) code.push(lines[i++]);
      i++;
      blocks.push(<div className="code-block" key={start}><div className="code-label"><span>{fence[2] || "文本"}</span>{onCopy && <button onClick={() => onCopy(code.join("\n"))}><Copy size={14} />复制</button>}</div><pre><code>{code.join("\n")}</code></pre></div>);
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      blocks.push(heading[1].length <= 2 ? <h2 key={start} id={`line-${start + 1}`}>{inline(heading[2])}</h2> : <h3 key={start} id={`line-${start + 1}`}>{inline(heading[2])}</h3>);
      i++; continue;
    }
    if (/^\s*[-*_]{3,}\s*$/.test(line)) { blocks.push(<hr key={start} />); i++; continue; }
    if (line.trim().startsWith("|") && i + 1 < lines.length && /^[\s|:\-]+$/.test(lines[i + 1])) {
      const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map(cell => cell.trim());
      const header = cells(line); i += 2; const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cells(lines[i++]));
      blocks.push(<div className="table-scroll" key={start}><table><thead><tr>{header.map((cell, index) => <th key={index}>{inline(cell)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, column) => <td key={column}>{inline(cell)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    const list = line.match(/^\s*(?:([-*+])|(\d+)[.)])\s+(.+)$/);
    if (list) {
      const ordered = Boolean(list[2]), items: ReactNode[] = [];
      const expression = ordered ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-*+]\s+(.+)$/;
      while (i < lines.length) { const item = lines[i].match(expression); if (!item) break; items.push(<li key={i}>{inline(item[1])}</li>); i++; }
      blocks.push(ordered ? <ol key={start} start={Number(list[2])}>{items}</ol> : <ul key={start}>{items}</ul>);
      continue;
    }
    if (/^\s*>/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push(<blockquote key={start}>{inline(quote.join("\n"))}</blockquote>); continue;
    }
    const paragraph = [line]; i++;
    while (i < lines.length && lines[i].trim() && !/^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|>|```|~~~|\|)/.test(lines[i])) paragraph.push(lines[i++]);
    blocks.push(<p key={start}>{inline(paragraph.join("\n"))}</p>);
  }
  return <div className="markdown">{blocks}</div>;
}
