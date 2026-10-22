import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import {createRequire} from "node:module";
import ts from "typescript";

const source = fs.readFileSync(new URL("../components/Markdown.tsx", import.meta.url), "utf8");
const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}}).outputText;
const module = {exports: {}};
vm.runInNewContext(code, {exports: module.exports, module, require: createRequire(import.meta.url)});
const Markdown = module.exports.default;
const citations = [{id: "p_first", title: "步骤"}, {id: "n_second", title: "活跃与付费计算"}];
function elements(tree) {
  const found = [];
  function visit(node) {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!node || typeof node !== "object") return;
    found.push(node); visit(node.props?.children);
  }
  visit(tree); return found;
}

test("saved answer references open their original evidence and omit repeated adjacent markers", () => {
  const links = elements(Markdown({text: "先排除已合服。[来源 2][来源 2][来源 1]", citations})).filter(node => node.type === "a");
  assert.equal(links.length, 2);
  assert.equal(links[0].props.href, "#note=n_second");
  assert.equal(links[0].props.children, "[2]");
  assert.equal(links[0].props["aria-label"], "查看依据 2：活跃与付费计算");
  assert.equal(links[1].props.href, "#note=p_first");
});

test("numbered references are bounded by saved sources; ordinary notes and code stay unchanged", () => {
  assert.equal(elements(Markdown({text: "普通笔记[来源 1]"})).filter(node => node.type === "a").length, 0);
  const links = elements(Markdown({text: "事实[1]，未知[来源 8]，代码`[来源 2]`。", citations})).filter(node => node.type === "a");
  assert.equal(links.length, 1);
  assert.equal(links[0].props.href, "#note=p_first");
});

test("legacy footer is removed once while factual source text and code remain; exports retain working links", () => {
  const text = "结论[来源 2][来源 2]。\n\n来源记录日期为八月，事件日期未确认。\n\n来源：来源 2《活跃与付费计算》。所给材料未附原文链接。\n\n```txt\n来源：来源 1 示例\n[来源 1]\n```";
  const cleaned = module.exports.cleanAnswer(text);
  assert.ok(!cleaned.includes("所给材料未附原文链接"));
  assert.ok(cleaned.includes("来源记录日期为八月"));
  assert.ok(cleaned.includes("来源：来源 1 示例\n[来源 1]"));
  const exported = module.exports.answerForExport(text, citations, "https://fixture.invalid");
  assert.equal(exported.split("[2](https://fixture.invalid/#note=n_second)").length - 1, 1);
  assert.ok(exported.includes("2. [活跃与付费计算](https://fixture.invalid/#note=n_second)"));
  assert.ok(exported.includes("[来源 1]\n```"));
});

test("repeating a search reads results and an existing answer without submitting a new AI job", async () => {
  const page = fs.readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  const begin = page.indexOf("  const runSearch = useCallback("), end = page.indexOf("  async function requestAnswer", begin);
  const searchCode = ts.transpileModule(page.slice(begin, end) + "\nglobalThis.runSearchTest=runSearch;", {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText;
  const calls = []; let shown, answerId;
  const context = {useCallback: fn => fn, encodeURIComponent, indexVersion: {current: "v1"}, searchSequence: {current: 0},
    currentSearch: {}, currentSearchVersion: {}, answers: {current: {合服: {id: "saved", version: "v1:answer-v2"}}},
    api: async (path, body) => { calls.push([path, body]); return path.startsWith("search?") ? {query: "合服", items: citations} : {id: "saved"}; },
    createJob: () => {throw new Error("Searching must not start AI generation");}, putJob: job => job,
    setQuery() {}, setSearching() {}, setSearch: value => {shown = value;}, setShowAll() {}, setAnswerError() {}, setAnswerId: value => {answerId = value;}, setError() {}};
  vm.createContext(context); vm.runInContext(searchCode, context);
  await context.runSearchTest("合服"); await context.runSearchTest("合服");
  assert.equal(shown.items.length, 2); assert.equal(answerId, "saved");
  assert.equal(calls.length, 4); assert.ok(calls.every(([, body]) => body === undefined));
  assert.ok(!page.includes("runSearch(value, true)"));
});
