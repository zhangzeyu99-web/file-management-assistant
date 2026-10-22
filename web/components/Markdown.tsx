"use client";

import { Fragment, type ReactNode } from "react";
import { Copy } from "lucide-react";

export function safeLink(value: string): boolean {
  return /^(https?:\/\/|#)/i.test(value)
    || /^codex:\/\/threads?\/[0-9a-f-]{36}$/i.test(value)
    || /^obsidian:\/\/open\?/i.test(value);
}

export type Citation = { id?: string; note_id?: string; title: string; note_title?: string; section?: string };
const citationPattern = /^\[(?:来源\s*)?(\d+)\]$/;
export function citationTitle(item: Citation) {
  return item.note_title && item.note_title !== item.title ? `${item.note_title} · ${item.title}` : item.title;
}
export function citationHref(item: Citation) {
  return item.id || item.note_id ? `#note=${encodeURIComponent(item.id || item.note_id || "")}` : "";
}
export function cleanAnswer(text: string) {
  let fence = "";
  return text.replace(/\r\n/g, "\n").split("\n").filter(line => {
    const marker = line.match(/^\s*(```|~~~)/)?.[1];
    if (marker) { if (!fence) fence = marker; else if (fence === marker) fence = ""; return true; }
    // Older model replies duplicated the UI's reference list in a final paragraph.
    return Boolean(fence) || !/^\s*(?:\*\*)?来源[：:]\s*(?:来源\s*\d+|\[来源\s*\d+\])/.test(line);
  }).join("\n").trim();
}
export function answerForExport(text: string, citations: Citation[], origin: string) {
  const used = new Set<number>(); let fence = "";
  const formatted = cleanAnswer(text).split("\n").map(line => {
    const marker = line.match(/^\s*(```|~~~)/)?.[1];
    if (marker) { if (!fence) fence = marker; else if (fence === marker) fence = ""; return line; }
    if (fence) return line;
    const adjacent = new Set<number>(); let previousEnd = 0;
    return line.replace(/`[^`]+`|\[[^\]]+\]\([^)]+\)|\[(?:来源\s*)?\d+\]/g, (token, offset: number) => {
      const number = Number(token.match(citationPattern)?.[1]), item = citations[number - 1];
      if (line.slice(previousEnd, offset).trim() || !item) adjacent.clear();
      previousEnd = offset + token.length;
      if (!item || !citationHref(item)) return token;
      if (adjacent.has(number)) return "";
      adjacent.add(number);
      used.add(number); return `[${number}](${origin}/${citationHref(item)})`;
    });
  }).join("\n");
  const references = [...used].sort((a, b) => a - b).map(number => `${number}. [${citationTitle(citations[number - 1])}](${origin}/${citationHref(citations[number - 1])})`);
  return formatted + (references.length ? `\n\n参考资料\n\n${references.join("\n")}` : "");
}

type Props = { text: string; onWikiLink?: (name: string) => void; onCopy?: (text: string) => void; citations?: Citation[] };

export default function Markdown({ text, onWikiLink, onCopy, citations }: Props) {
  function inline(value: string): ReactNode[] {
    const pattern = /(\[\[[^\]]+\]\]|\[[^\]]+\]\([^)]+\)|`[^`]+`|\*\*[^*]+\*\*|\[(?:来源\s*)?\d+\]|<https?:\/\/[^\s<>]+>|https?:\/\/[^\s<>]+|codex:\/\/threads?\/[a-z0-9-]+)/gi;
    const output: ReactNode[] = [];
    let previous = 0;
    const adjacentCitations = new Set<number>();
    for (const match of value.matchAll(pattern)) {
      const gap = value.slice(previous, match.index);
      if (gap) output.push(gap);
      const token = match[0];
      const number = Number(token.match(citationPattern)?.[1]), citation = citations?.[number - 1];
      if (gap.trim() || !citation) adjacentCitations.clear();
      if (citation && citationHref(citation) && adjacentCitations.has(number)) { previous = match.index! + token.length; continue; }
      let node: ReactNode = token;
      if (citation && citationHref(citation)) {
        node = <a className="answer-citation" href={citationHref(citation)} title={citationTitle(citation)} aria-label={`查看依据 ${number}：${citationTitle(citation)}`}>{`[${number}]`}</a>;
        adjacentCitations.add(number);
      } else if (token.startsWith("[[")) {
        const [target, label] = token.slice(2, -2).split("|");
        node = onWikiLink ? <button className="inline-link" onClick={() => onWikiLink(target)}>{label || target}</button> : label || target;
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

  const lines = (citations?.length ? cleanAnswer(text || "") : text || "").replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "")
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
      blocks.push(heading[1].length <= 2 ? <h2 key={start} id={`line-${start + 1}`} data-heading={heading[2]}>{inline(heading[2])}</h2> : <h3 key={start} id={`line-${start + 1}`} data-heading={heading[2]}>{inline(heading[2])}</h3>);
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
