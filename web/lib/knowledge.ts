type NoteLink = { id: string; note_id?: string; title: string; relative?: string; archived?: boolean; source_only?: boolean; kind?: string };

const pathId = (path: string) => "n_" + btoa(Array.from(new TextEncoder().encode(path), byte => String.fromCharCode(byte)).join(""))
  .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

export function resolveWikiNote(notes: NoteLink[], aliases: Record<string, string>, target: string, origin = "") {
  const split = target.indexOf("#"), path = (split < 0 ? target : target.slice(0, split)).trim().replace(/\\/g, "/");
  const anchor = split < 0 ? "" : target.slice(split + 1).trim();
  origin = origin.replace(/\\/g, "/");
  if (path.startsWith("/") || path.includes(":") || path.split("/").some(part => part === "." || part === "..")) {
    throw new Error("笔记链接必须使用知识库内的相对路径。");
  }
  const relative = /\.md$/i.test(path) ? path : path + ".md";
  const folder = origin.includes("/") ? origin.slice(0, origin.lastIndexOf("/") + 1) : "";
  const candidates = !path ? (origin ? [origin] : []) : path.includes("/")
    ? [relative, ...(origin ? [folder + relative] : [])]
    : [...(origin ? [folder + relative] : []), relative];
  const byPath = new Map(notes.map(note => [note.relative?.toLowerCase(), note.id]));
  for (const candidate of candidates) {
    const noteId = byPath.get(candidate.toLowerCase()) || aliases[pathId(candidate)];
    if (noteId && notes.some(note => note.id === noteId)) return { note_id: noteId, anchor };
  }
  if (path && !path.includes("/")) {
    const name = relative.slice(0, -3).toLowerCase();
    const matches = notes.filter(note => note.relative?.split("/").at(-1)?.replace(/\.md$/i, "").toLowerCase() === name || note.title.toLowerCase() === name);
    if (matches.length === 1) return { note_id: matches[0].id, anchor };
    if (matches.length > 1) throw new Error("链接有多篇同名笔记，请使用完整路径。");
  }
  throw new Error("未找到链接笔记，请检查路径或最新同步结果。");
}

export function groupJobNotes(saved: (NoteLink | string)[], topics: NoteLink[] | undefined, aliases: Record<string, string> = {}) {
  const current: (NoteLink | string)[] = [], historical: NoteLink[] = [];
  const topicById = new Map(topics?.map(note => [note.note_id || note.id, note]));
  const seenCurrent = new Set<string>(), seenHistory = new Set<string>();
  let unavailable = 0;
  for (const item of saved) {
    if (typeof item === "string") { if (!topics) current.push(item); else unavailable++; continue; }
    if (item.source_only || item.kind === "source_only") continue;
    const originalId = item.note_id || item.id, resolvedId = aliases[originalId] || originalId;
    const topic = topicById.get(resolvedId);
    if (topic || (!topics && !item.archived)) {
      if (!seenCurrent.has(resolvedId)) current.push(topic ? { ...item, ...topic, id: resolvedId } : item);
      seenCurrent.add(resolvedId);
    } else if (item.archived || aliases[originalId]) {
      if (!seenHistory.has(resolvedId)) historical.push({ ...item, id: resolvedId });
      seenHistory.add(resolvedId);
    } else unavailable++;
  }
  return { current, historical, unavailable };
}

export function locateNoteAnchorWhenReady(targetId: string | undefined, anchor: string | undefined,
  note: {id: string; focus?: {id: string}} | null, loading: boolean, aliases: Record<string, string>,
  locate: (anchor: string) => boolean, missing: () => void) {
  if (!targetId || !anchor || loading || !note) return;
  const expectedId = aliases[targetId] || targetId;
  if (note.id !== expectedId && note.focus?.id !== targetId) return;
  let cancelled = false;
  const frame = requestAnimationFrame(() => {
    if (!cancelled && !locate(anchor)) missing();
  });
  return () => { cancelled = true; cancelAnimationFrame(frame); };
}
