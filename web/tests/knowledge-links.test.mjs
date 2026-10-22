import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import {createRequire} from "node:module";
import ts from "typescript";
import {resolveWikiNote, groupJobNotes, locateNoteAnchorWhenReady} from "../lib/knowledge.ts";

const pathId = path => "n_" + Buffer.from(path).toString("base64url");
const current = {id: "n_current", title: "当前结论", relative: "10 项目/甲/当前结论.md"};
const archived = {id: "n_archived", title: "原始依据", relative: "90 历史/甲/原始依据.md", archived: true};

test("wiki paths preserve headings and resolve archived and renamed notes", () => {
  const notes = [current, archived], aliases = {[pathId("旧目录/旧结论.md")]: current.id};
  assert.deepEqual(resolveWikiNote(notes, aliases, "90 历史/甲/原始依据#三日口径"), {note_id: archived.id, anchor: "三日口径"});
  assert.deepEqual(resolveWikiNote(notes, aliases, "旧目录/旧结论#计算方式"), {note_id: current.id, anchor: "计算方式"});
  assert.deepEqual(resolveWikiNote(notes, aliases, "#计算方式", current.relative), {note_id: current.id, anchor: "计算方式"});
  assert.throws(() => resolveWikiNote(notes, aliases, "../库外#口径"), /相对路径/);
  assert.throws(() => resolveWikiNote(notes, aliases, "不存在/原始依据"), /未找到/);
  const other = {...current, id: "n_other", relative: "10 项目/乙/当前结论.md"};
  assert.throws(() => resolveWikiNote([...notes, other], aliases, "当前结论"), /同名/);
  assert.equal(resolveWikiNote([...notes, other], aliases, "当前结论", current.relative).note_id, current.id);
});

test("job results show current alias targets once and keep history separate", () => {
  const saved = [{id: "n_old1", title: "旧标题一"}, {id: "n_old2", title: "旧标题二"},
    {id: "n_oldarchive", title: "旧原文"}, {id: "n_unknown", title: "未定位"},
    {id: "n_receipt", title: "仅登记", source_only: true}];
  const grouped = groupJobNotes(saved, [current], {n_old1: current.id, n_old2: current.id, n_oldarchive: archived.id});
  assert.deepEqual(grouped.current, [current]);
  assert.deepEqual(grouped.historical.map(note => [note.id, note.title]), [[archived.id, "旧原文"]]);
  assert.equal(grouped.unavailable, 1);
  assert.equal(saved[0].title, "旧标题一", "rendering must not rewrite saved results");
});

test("heading lookup waits for the destination body and ignores a cancelled navigation frame", () => {
  const originalRequest = globalThis.requestAnimationFrame, originalCancel = globalThis.cancelAnimationFrame;
  const frames = new Map(); let nextFrame = 0, lookups = 0, missing = 0;
  globalThis.requestAnimationFrame = callback => { frames.set(++nextFrame, callback); return nextFrame; };
  globalThis.cancelAnimationFrame = id => { frames.delete(id); };
  const locate = anchor => { lookups++; assert.equal(anchor, "三日口径"); return true; };
  const notFound = () => { missing++; };
  try {
    assert.equal(locateNoteAnchorWhenReady(archived.id, "三日口径", current, false, {}, locate, notFound), undefined,
      "the old note can remain in state for the first render after navigation");
    assert.equal(locateNoteAnchorWhenReady(archived.id, "三日口径", null, true, {}, locate, notFound), undefined);
    assert.equal(locateNoteAnchorWhenReady(archived.id, "三日口径", archived, true, {}, locate, notFound), undefined,
      "receiving note data alone is insufficient while the reader still shows loading");
    assert.equal(frames.size, 0); assert.equal(lookups, 0); assert.equal(missing, 0);
    const cleanup = locateNoteAnchorWhenReady(archived.id, "三日口径", archived, false, {}, locate, notFound);
    assert.equal(lookups, 0, "the loaded body must commit before heading lookup");
    frames.get(nextFrame)(); cleanup();
    assert.equal(lookups, 1); assert.equal(missing, 0);
    const cancel = locateNoteAnchorWhenReady(archived.id, "三日口径", archived, false, {}, () => false, notFound);
    const staleFrame = frames.get(nextFrame); cancel(); staleFrame();
    assert.equal(missing, 0, "a stale frame must not report a missing heading after navigation");
    const absent = locateNoteAnchorWhenReady("n_old", "三日口径", archived, false, {n_old: archived.id}, () => false, notFound);
    frames.get(nextFrame)(); absent();
    assert.equal(missing, 1, "a genuinely absent heading is reported only after its target note is ready");
  } finally {
    globalThis.requestAnimationFrame = originalRequest; globalThis.cancelAnimationFrame = originalCancel;
  }
});

test("Markdown dispatches the full wiki target and exposes destination headings", () => {
  const source = fs.readFileSync(new URL("../components/Markdown.tsx", import.meta.url), "utf8");
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}}).outputText;
  const module = {exports: {}};
  vm.runInNewContext(code, {exports: module.exports, module, require: createRequire(import.meta.url)});
  let target;
  const tree = module.exports.default({text: "## 三日口径\n\n[[90 历史/甲/原始依据#三日口径|查看依据]]", onWikiLink: value => {target = value;}});
  const elements = [];
  function visit(node) {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!node || typeof node !== "object") return;
    elements.push(node); visit(node.props?.children);
  }
  visit(tree);
  elements.find(node => node.type === "button").props.onClick();
  assert.equal(target, "90 历史/甲/原始依据#三日口径");
  assert.equal(elements.find(node => node.type === "h2").props["data-heading"], "三日口径");
});

test("cloud reading resolver uses the same snapshot paths without invoking jobs", async () => {
  const source = fs.readFileSync(new URL("../app/api/workspace/[...path]/route.ts", import.meta.url), "utf8")
    .replace(/^import .*$/gm, "").replace(/^export /gm, "") + "\nglobalThis.handleTest=handler;";
  const code = ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText;
  const context = {env: {DB: {prepare: () => ({bind() {return this;}, first: async () => null})},
    BUCKET: {get: async () => ({json: async () => ({notes: [current, archived], note_aliases: {}})})}},
    resolveWikiNote, migrationCloudRoute: async () => null, Response, Request, URL, Headers};
  vm.createContext(context); vm.runInContext(code, context);
  const response = await context.handleTest(new Request("https://fixture.invalid/api/workspace/notes/resolve?target=" + encodeURIComponent("90 历史/甲/原始依据#三日口径")));
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {note_id: archived.id, anchor: "三日口径"});
});
