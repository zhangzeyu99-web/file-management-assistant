import test from "node:test";
import assert from "node:assert/strict";
import {updateResultView, latestUpdateAttempt, updateJobView, updatePendingItem} from "../lib/update-result.ts";
import fs from "node:fs";
import vm from "node:vm";
import {createRequire} from "node:module";
import ts from "typescript";
import * as helpers from "../lib/update-result.ts";
import {groupJobNotes} from "../lib/knowledge.ts";
import * as userErrors from "../lib/user-errors.ts";
import catalog from "../lib/error-catalog.json" with {type: "json"};

const checks = (count, reason, extra = {}) => Array.from({length: count}, (_, i) => ({
  kind: "file", source: `fixture-${reason}-${i}`, reason, body_read: false, ...extra,
}));

test("update results separate saved notes, policy registrations, failures and coverage warnings", () => {
  const source_checks = [
    ...checks(32, "脚本或工程文件，仅记录来源"),
    ...checks(57, "暂不支持的文件格式"),
    ...checks(4, "飞书文档元数据", {kind: "feishu", body_read: undefined}),
    ...checks(4, "只有重复提醒，没有新增知识", {kind: "thread", body_read: true}),
  ];
  const errors = Array.from({length: 5}, (_, i) => ({source: `fixture-${i}`, error: "正文读取失败"}));
  const result = {notes: Array.from({length: 37}, (_, i) => ({id: `note-${i}`})),
    counts: {files: 17, threads: 20, feishu: 0}, source_checks, errors,
    warnings: ["脚本或工程文件，仅记录来源，仅记录来源，未生成知识笔记",
      "暂不支持的文件格式，仅记录来源，未生成知识笔记",
      "测试入口：仅登记飞书入口，未读取或总结正文",
      "只有重复提醒，没有新增知识，仅记录来源，未生成知识笔记",
      "最近对话达到接口上限，活跃线程范围可能不完整",
      "117 个旧线程缺少逐条登记，保留为历史发现缺口，未读取历史正文。"],
    sources: {threads: {status: "partial", listed: 650, historical_gap: 117, pending: 23}}};
  const before = structuredClone(result), view = updateResultView(result);
  assert.equal(view.summary, "本轮累计保存 37 篇知识笔记。");
  assert.equal(view.noteSources, "文件 17 篇 · 对话 20 篇");
  assert.equal(view.registrationCount, 97);
  assert.equal(view.nativeLimited, true);
  assert.deepEqual(view.registrations, [
    {label: "工程文件（不读正文）", count: 32},
    {label: "暂不支持的格式（不读正文）", count: 57},
    {label: "飞书入口（仅元数据）", count: 4},
    {label: "读后无可积累内容", count: 4},
  ]);
  assert.deepEqual(view.errors, errors);
  assert.equal(view.warnings.length, 2, "only repeated registration warnings are folded into policy groups");
  assert.deepEqual(result, before, "display must not rewrite saved receipts or coverage state");
});

test("legacy results keep unknown warnings and never infer registrations as failures", () => {
  const view = updateResultView({counts: {files: 0, threads: 0, feishu: 0},
    source_checks: [{kind: "file", reason: "旧版仅登记"}],
    warnings: ["未知来源限制", {message: "连接待核实"}], partial: true});
  assert.equal(view.summary, "本轮暂无新增知识笔记。");
  assert.equal(view.noteSources, "");
  assert.equal(view.registrationCount, 1);
  assert.deepEqual(view.errors, []);
  assert.equal(view.nativeLimited, false);
  assert.equal(view.warnings.length, 2);
  assert.deepEqual(view.registrations, [{label: "其他来源登记", count: 1}]);
});

test("retry display uses cumulative saved results and counts metadata separately from notes", () => {
  const result = {notes: [{id: "previously-saved"}, {id: "saved-after-retry"}],
    counts: {files: 1, threads: 1, feishu: 0},
    source_checks: checks(3, "飞书文档元数据", {kind: "feishu"})};
  const view = updateResultView(result);
  assert.equal(view.summary, "本轮累计保存 2 篇知识笔记。");
  assert.equal(view.registrationCount, 3);
  assert.equal(view.noteSources.includes("飞书"), false);
});

test("empty files and spreadsheet intake have their own policy categories", () => {
  const view = updateResultView({source_checks: [
    ...checks(2, "空文件，没有可归档正文", {body_read: true}),
    ...checks(2, "表格数据，正文分析需使用专项流程"),
  ]});
  assert.deepEqual(view.registrations, [
    {label: "空文件", count: 2}, {label: "表格数据（需专项分析）", count: 2},
  ]);
  assert.deepEqual(view.errors, []);
});

test("running updates never report no additions before checking is complete", () => {
  assert.equal(updateResultView({}, {active: true}).summary, "");
  assert.equal(updateResultView({notes: [], source_checks: checks(1, "暂不支持的文件格式")}, {active: true}).summary, "");
  assert.equal(updateResultView({notes: [{id: "saved"}]}, {active: true}).summary, "本轮累计保存 1 篇知识笔记。");
});

test("old attempts link only to their own later retry, including running retries and missing ancestors", () => {
  const original = {id: "original", kind: "update", status: "partial", created_at: 10, result: {errors: [{source: "旧失败", error: "读取失败"}]}};
  const retry = {id: "retry", kind: "update", status: "partial", created_at: 20, input: {retry_of: original.id}};
  const unrelated = {id: "unrelated", kind: "update", status: "completed", created_at: 30};
  assert.equal(latestUpdateAttempt(original, [retry, unrelated]).id, retry.id);
  assert.equal(updateJobView(original, [retry, unrelated]).superseded, true);
  assert.equal(updateJobView(retry, [unrelated]).superseded, false);
  assert.equal(latestUpdateAttempt({...retry, input: {retry_of: "missing-root"}}, [
    {id: "next", status: "running", created_at: 40, input: {retry_of: "missing-root"}},
  ]).id, "next");
});

test("pending objects are readable while original technical errors and coverage remain separate", () => {
  const native = {source: "知识库总线程", error: "原生轮次分页读取失败：该线程超过原生读取限制；保留部分覆盖及续读边界。"};
  const encoding = {source: "D:\\private\\archive\\账目说明.txt", error: "UnicodeDecodeError: utf-8 codec cannot decode byte 0xff"};
  const result = {notes: [{id: "n_saved", title: "项目甲的排期规则"}], errors: [native, encoding],
    sources: {threads: {status: "partial", historical_gap: 117, pending: 23}},
    source_checks: checks(104, "暂不支持的文件格式")};
  const before = structuredClone(result), view = updateJobView({id: "latest", status: "partial", result}, []);
  assert.equal(view.summary, "已保存成果，另有 2 项待补。");
  assert.equal(view.pending[0].source, "知识库总线程");
  assert.equal(view.pending[0].reason, catalog.native_oversized.message);
  assert.equal(view.pending[1].source, "账目说明");
  assert.equal(view.pending[1].reason, catalog.invalid_encoding.message);
  assert.equal(view.coverage.length, 2);
  assert.equal(view.registrationCount, 104);
  assert.equal(view.canRetry, false, "length and encoding failures require the displayed recovery actions before another attempt");
  assert.deepEqual(result, before);
  assert.equal(updatePendingItem({source: "https://fixture.invalid/docx/encoded-id", error: "403 Forbidden"}).source, "在线文档");
});

test("retry outcomes put newly saved topics first and never turn a partial receipt into full completion", () => {
  const oldNotes = Array.from({length: 6}, (_, i) => ({id: `n_${i}`, title: `项目甲方法${i}`}));
  const old = {id: "original", status: "partial", created_at: 1, result: {notes: oldNotes}};
  const job = {id: "retry", status: "partial", created_at: 2, input: {retry_of: old.id},
    result: {notes: [...oldNotes, {id: "new", title: "项目乙的新结论"}], sources: {threads: {pending: 23}}}};
  const view = updateJobView(job, [old]);
  assert.equal(view.notes[0].id, "new");
  assert.equal(view.summary, "已保存成果，23 个对话轮次待补。");
  assert.equal(view.pending.length, 0, "unread rounds are not processing failures");
  assert.equal(updateJobView({...job, result:{...job.result, warnings:["最近对话达到接口上限，活跃线程范围可能不完整"]}},[old]).retryHint, "已保存和仅登记项会跳过。", "list range warnings are not a failed conversation read");
});

const componentSource = fs.readFileSync(new URL("../components/UpdateResult.tsx", import.meta.url), "utf8");
const componentCode = ts.transpileModule(componentSource, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}}).outputText;
const componentModule = {exports: {}}, require = createRequire(import.meta.url);
const recoverySource = fs.readFileSync(new URL("../components/RecoveryNotice.tsx", import.meta.url), "utf8");
const recoveryCode = ts.transpileModule(recoverySource, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}}).outputText;
const recoveryModule = {exports: {}};
vm.runInNewContext(recoveryCode, {module: recoveryModule, exports: recoveryModule.exports,
  require: name => name === "@/lib/user-errors" ? userErrors : name === "react" ? {
    ...require("react"), useMemo: fn => fn(), useState: initial => [typeof initial === "function" ? initial() : initial, () => {}],
  } : require(name)});
vm.runInNewContext(componentCode, {module: componentModule, exports: componentModule.exports,
  require: name => name === "@/lib/update-result" ? helpers : name === "./RecoveryNotice" ? recoveryModule.exports : require(name)});
const UpdateResult = componentModule.exports.default;
function renderedText(node, includeDetails = false) {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(item => renderedText(item, includeDetails)).join("");
  if (!node || typeof node !== "object") return "";
  if (typeof node.type === "function") return renderedText(node.type(node.props), includeDetails);
  const children = node.props?.children;
  if (node.type === "details" && !includeDetails) return renderedText((Array.isArray(children) ? children : [children]).find(child => child?.type === "summary"));
  return renderedText(children, includeDetails);
}

test("saved outcomes keep outstanding unread rounds visible in the main result", () => {
  const job = {id: "rounds", status: "partial", result: {notes: [{id: "note", title: "项目甲方法"}], sources: {threads: {pending: 23}}}};
  const text = renderedText(UpdateResult({job, jobs: [], onOpenJob() {}, onRetry() {}, onOpenNote() {}}));
  assert.match(text, /已保存成果，23 个对话轮次待补/);
});

test("named unfinished conversations show the real cause without an ineffective retry", () => {
  const job = {id: "named", status: "partial", result: {notes:[{id:"saved",title:"项目甲方法"}], outstanding:[
    {thread_id:"thread-a",title:"项目甲讨论",reason:"1 个轮次已中断。",turns:[{reason_code:"interrupted",status:"interrupted"}]}
  ]}};
  const view = updateJobView(job,[]);
  assert.equal(view.errors.length,0);
  assert.equal(view.canRetry,false);
  assert.deepEqual(view.pending,[{source:"项目甲讨论",reason:"1 个轮次已中断。",action:"继续原对话后再补充，已完成内容保留。"}]);
  const text = renderedText(UpdateResult({job,jobs:[],onOpenJob(){},onRetry(){},onOpenNote(){}}));
  assert.match(text,/待补 · 1 项项目甲讨论：1 个轮次已中断/);
  assert.doesNotMatch(text,/重试未完成来源/);
  const page = {...job,result:{...job.result,outstanding:[{thread_id:"thread-a",title:"项目甲讨论",reason:"分页读取中断。",reasons:[{reason_code:"pagination_incomplete"}]}]}};
  assert.equal(updateJobView(page,[]).canRetry,true);
  const running = {...job,result:{...job.result,outstanding:[{thread_id:"thread-a",title:"项目甲讨论",reason:"轮次仍在执行中，完成后再整理",turns:[{reason_code:"running"}]}]}};
  const runningText=renderedText(UpdateResult({job:running,jobs:[],onOpenJob(){},onRetry(){},onOpenNote(){}}));
  assert.equal((runningText.match(/完成后再整理/g)||[]).length,1);
  assert.doesNotMatch(runningText,/原对话完成后再补充/);
});
function elements(node, type) {
  if (Array.isArray(node)) return node.flatMap(item => elements(item, type));
  if (!node || typeof node !== "object") return [];
  if (typeof node.type === "function") return elements(node.type(node.props), type);
  return [...(node.type === type ? [node] : []), ...elements(node.props?.children, type)];
}

test("old receipt defaults to the newer result, hides old failures and never retries the superseded attempt", () => {
  const old = {id: "original", status: "partial", created_at: 1, result: {notes: [], errors: [{source: "旧来源", error: "旧技术错误"}]}};
  const retry = {id: "retry", status: "partial", created_at: 2, input: {retry_of: old.id}};
  let opened;
  const tree = UpdateResult({job: old, jobs: [retry], onOpenJob: id => {opened = id;}, onRetry: () => {throw new Error("must not retry an obsolete attempt");}, onOpenNote() {}});
  assert.ok(renderedText(tree).includes("已有更新结果"));
  assert.ok(!renderedText(tree).includes("旧技术错误"));
  const buttons = elements(tree, "button");
  assert.equal(buttons.length, 1); buttons[0].props.onClick(); assert.equal(opened, retry.id);
  assert.ok(!renderedText(tree, true).includes("旧技术错误"), "historical details keep safe error meaning without re-exposing raw exceptions");
  assert.ok(renderedText(tree, true).includes(catalog.internal_error.message));
});

test("latest receipt shows named outcomes and a direct repair action without exposing paths or raw exceptions", () => {
  const job = {id: "latest", status: "partial", result: {notes: Array.from({length: 7}, (_, i) => ({id: `n_${i}`, title: `项目甲规则${i}`})),
    errors: [{source: "D:\\private\\source\\说明.txt", error: "UnicodeDecodeError: utf-8 codec cannot decode byte 0xff"}], source_checks: checks(104, "暂不支持的文件格式")}};
  let opened, added;
  const tree = UpdateResult({job, jobs: [], onOpenJob() {}, onRetry() {throw new Error("encoding cannot be fixed by replaying the same source");}, onAdd: () => {added = true;}, onOpenNote: id => {opened = id;}});
  const text = renderedText(tree);
  assert.ok(text.includes("已完成")); assert.ok(text.includes("待补")); assert.ok(text.includes("说明"));
  assert.ok(text.includes(catalog.invalid_encoding.action));
  assert.ok(!text.includes("D:\\private")); assert.ok(!text.includes("UnicodeDecodeError"));
  assert.ok(text.includes("已跳过总结 · 104 项"));
  assert.ok(!text.includes("项目甲规则5"), "only five named note entrances are expanded");
  assert.ok(renderedText(tree, true).includes("项目甲规则6"));
  const buttons = elements(tree, "button");buttons[0].props.onClick();assert.equal(opened, "n_0");
  buttons.find(button => renderedText(button) === "添加正文").props.onClick(); assert.equal(added, true);
  assert.ok(!buttons.some(button => renderedText(button).includes("重试")));
  assert.ok(!renderedText(tree, true).includes("D:\\private"));
  assert.ok(!renderedText(tree, true).includes("UnicodeDecodeError"));
});

test("update outcomes retain folded archived and unresolved records with their real note targets", () => {
  const saved = [{id: "current", title: "现行主题"}, {id: "original", title: "旧成果原文"}, {id: "missing", title: "未定位旧成果"}];
  const grouped = groupJobNotes(saved, [{id: "current", title: "现行主题"}], {original: "hidden-original"});
  let opened;
  const tree = UpdateResult({job: {id: "latest", status: "completed", result: {notes: saved}}, jobs: [],
    notes: grouped.current, historical: grouped.historical, unavailable: grouped.unavailable,
    onOpenJob() {}, onRetry() {}, onOpenNote: id => {opened = id;}});
  const visible = renderedText(tree);
  assert.ok(visible.includes("现行主题"));
  assert.ok(visible.includes("已归档或合并 · 1 条"));
  assert.ok(visible.includes("未定位记录 · 1 条"));
  assert.ok(!visible.includes("旧成果原文"), "archived titles stay folded outside current outcomes");
  assert.ok(renderedText(tree, true).includes("原处理记录仍保留"));
  const archive = elements(tree, "details").find(node => renderedText(node).includes("已归档或合并"));
  assert.equal(archive.props.open, undefined, "archive history is closed by default");
  elements(archive, "button")[0].props.onClick();
  assert.equal(opened, "hidden-original", "open the resolved original, never the obsolete ID");
});

test("superseded update receipts keep original archived records inside their folded history", () => {
  const old = {id: "old", status: "partial", created_at: 1, result: {notes: [{id: "original", title: "当时成果"}]}};
  const retry = {id: "retry", status: "completed", created_at: 2, input: {retry_of: old.id}};
  let opened;
  const tree = UpdateResult({job: old, jobs: [retry], notes: [], historical: [{id: "hidden-original", title: "当时成果"}], unavailable: 2,
    onOpenJob() {}, onRetry() {throw new Error("must not retry an old receipt");}, onOpenNote: id => {opened = id;}});
  assert.ok(renderedText(tree).includes("已有更新结果"));
  assert.ok(!renderedText(tree).includes("当时成果"));
  assert.ok(renderedText(tree, true).includes("未定位记录 · 2 条"));
  const archived = elements(tree, "button").find(button => renderedText(button).includes("当时成果"));
  assert.ok(archived, "original history remains reachable behind the latest-result prompt");
  archived.props.onClick(); assert.equal(opened, "hidden-original");
});


test("selection submission keeps its identity after a lost response and rejects another active update", async () => {
  const identity = {key: "", id: ""}, seen = [];
  const selection = {threads: ["thread-b", "thread-a"], files: []};
  let first = true;
  const create = async (kind, input, id) => { seen.push({kind, input, id}); if (first) {first = false; throw new Error("connection lost");} return {id}; };
  await assert.rejects(helpers.submitSummarySelection(selection, identity, create, () => "request-one"), /connection lost/);
  const job = await helpers.submitSummarySelection({threads: ["thread-a", "thread-b"], files: []}, identity, create, () => {throw new Error("must reuse request ID");});
  assert.equal(job.id, "request-one"); assert.equal(seen[0].id, seen[1].id);
  await assert.rejects(helpers.submitSummarySelection(selection, identity, async () => ({id: "other-active-task"})), /本次选择未提交/);
});


test("a known unreadable long conversation is explicit and does not offer an ineffective retry", () => {
  const job = {id: "long", status: "partial", result: {notes: [{id: "saved", title: "已有主题"}], errors: [{source: "项目长对话", error: "该线程超过原生读取限制"}]}};
  const view = helpers.updateJobView(job, []);
  assert.equal(view.canRetry, false);
  assert.equal(helpers.updateStatusText(job), "1 项待补");
  assert.equal(helpers.updateStatusText({id: "done", status: "completed"}), "已完成");
});


test("mixed failures retain retry only when a temporary failure remains, without conflating discovery coverage", () => {
  const result = {notes: [{id: "saved", title: "已有结论"}], errors: [
    {source: "长对话", error_detail: {code: "native_oversized"}},
    {source: "线上同步", error_detail: {code: "cloud_timeout"}},
  ], sources: {threads: {status: "partial", historical_gap: 5}}};
  const before = structuredClone(result);
  const view = updateJobView({id: "mixed", status: "partial", result}, []);
  assert.equal(view.canRetry, true);
  assert.equal(view.pending[0].issue.retryable, false);
  assert.equal(view.pending[1].issue.retryable, true);
  assert.equal(view.coverage.length, 1);
  assert.equal(view.errors.length, 2);
  assert.deepEqual(result, before);
});
