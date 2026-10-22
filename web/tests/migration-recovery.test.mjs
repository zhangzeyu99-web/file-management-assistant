import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import * as userErrors from "../lib/user-errors.ts";

const source = fs.readFileSync(new URL("../components/MigrationPanel.tsx", import.meta.url), "utf8");
const code = ts.transpileModule(source, {compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
}}).outputText;
const OPERATION_KEY = "obsidian-workspace-migration-operation";
const preview = (destination = "C:/NewLibrary") => ({upload_id: "upload-fixture", destination, ready: true,
  summary: {vault_files: 2, notes: 1, files: 1, threads: 1, feishu: 0}});
const detail = code => ({code, message: "A synthetic failure", action: "A synthetic action", retryable: false, help: "migration"});
const json = (value, status = 200) => Response.json(value, {status});
const settle = async () => { for (let i = 0; i < 12; i++) await new Promise(resolve => setImmediate(resolve)); };

function fixture({fetchImpl, storage = new Map(), mode = "local", online = true} = {}) {
  const state = [], refs = [], callbacks = [], effects = [], pending = [], requests = [], timers = new Map();
  let stateIndex = 0, refIndex = 0, callbackIndex = 0, effectIndex = 0, tree, timerId = 0;
  const Recovery = () => null;
  const create = (type, props) => ({type, props: props || {}});
  const React = {
    useState(initial) { const i = stateIndex++; if (!(i in state)) state[i] = typeof initial === "function" ? initial() : initial;
      return [state[i], value => { state[i] = typeof value === "function" ? value(state[i]) : value; }]; },
    useRef(initial) { const i = refIndex++; return refs[i] ||= {current: initial}; },
    useCallback(value, deps) { const i = callbackIndex++, old = callbacks[i];
      if (!old || deps.some((item, index) => item !== old.deps[index])) callbacks[i] = {value, deps};
      return callbacks[i].value; },
    useEffect(run, deps) { const i = effectIndex++, old = effects[i];
      if (!old || !deps || deps.some((value, index) => value !== old.deps?.[index])) {
        old?.cleanup?.(); effects[i] = {deps, run}; pending.push(i);
      }
    },
  };
  const module = {exports: {}};
  const context = {module, exports: module.exports,
    require(name) {
      if (name === "react") return React;
      if (name === "react/jsx-runtime") return {jsx: create, jsxs: create, Fragment: Symbol.for("fragment")};
      if (name === "lucide-react") return new Proxy({}, {get: (_, key) => String(key)});
      if (name === "./RecoveryNotice") return {__esModule: true, default: Recovery};
      if (name === "../lib/user-errors") return userErrors;
      throw new Error(`Unexpected test import: ${name}`);
    },
    fetch: async (url, options = {}) => { const path = String(url).replace("/api/workspace/", "");
      const body = typeof options.body === "string" ? JSON.parse(options.body) : options.body;
      requests.push({path, body});
      if (path === "migration/status") return json({mode, online, configured: true, can_export: true, default_destination: "C:/OldDirectory"});
      return fetchImpl(path, options, body);
    },
    localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
    window: {location: {origin: "https://fixture.invalid"}},
    document: {}, crypto, AbortController, AbortSignal, URL, Response, Map, Set,
    setTimeout(callback) { const id = ++timerId; timers.set(id, callback); return id; },
    clearTimeout(id) { timers.delete(id); },
  };
  vm.runInNewContext(code, context);
  function render() {
    stateIndex = refIndex = callbackIndex = effectIndex = 0;
    tree = module.exports.default({mode, online, onActivated: async () => {}, onJobsChanged: async () => {}});
    for (const i of pending.splice(0)) effects[i].cleanup = effects[i].run();
    return tree;
  }
  function nodes(value) {
    if (!value || typeof value !== "object") return [];
    if (Array.isArray(value)) return value.flatMap(nodes);
    return [value, ...nodes(value.props?.children)];
  }
  function text(value) {
    if (Array.isArray(value)) return value.map(text).join("");
    if (value && typeof value === "object") return text(value.props?.children);
    return typeof value === "string" || typeof value === "number" ? String(value) : "";
  }
  function button(label) { return nodes(tree).find(node => node.type === "button" && text(node) === label); }
  function input() { return nodes(tree).find(node => node.type === "input" && node.props.type === "file"); }
  function location() { return nodes(tree).find(node => node.props?.id === "migration-destination"); }
  function notices() { return nodes(tree).filter(node => node.type === Recovery); }
  async function ready() { render(); await settle(); render(); await settle(); render(); }
  return {render, ready, button, input, location, notices, requests, storage, text: () => text(tree), exports: module.exports,
    close() { for (const effect of effects) effect?.cleanup?.(); timers.clear(); }};
}

function uploadResponder({badPackage = false} = {}) {
  let checks = 0;
  return (path, options, body) => {
    if (path === "migration/import/start") return json({upload_id: "upload-fixture", chunk_size: 4});
    if (path.startsWith("migration/import/chunk")) return json({received: 4});
    if (path === "migration/import/preview") {
      checks++;
      if (badPackage || checks === 1) return json({error: "private technical failure", error_detail: detail(badPackage ? "migration_invalid_bundle" : "migration_target_occupied")}, 400);
      return json(preview(body.destination));
    }
    if (path === "migration/import/cancel") return json({ok: true});
    throw new Error(`Unexpected route ${path}`);
  };
}
const zip = {name: "fixture.zip", size: 4, slice: () => new Blob(["test"])};
async function choose(f) { f.input().props.onChange({target: {files: [zip], value: "fixture.zip"}}); await settle(); f.render(); }

test("rejected destination can be changed and rechecked without uploading the package again", async () => {
  const f = fixture({fetchImpl: uploadResponder()});
  try {
    await f.ready(); await choose(f);
    assert.ok(f.location(), "the target remains editable after precheck rejection");
    assert.equal(f.notices().at(-1).props.error.detail?.code || f.notices().at(-1).props.error.error_detail?.code, "migration_target_occupied");
    f.location().props.onChange({target: {value: "C:/EmptyDestination"}}); f.render();
    f.button("检查存放位置").props.onClick(); await settle(); f.render();
    assert.ok(f.button("导入并使用"));
    assert.equal(f.requests.filter(row => row.path === "migration/import/start").length, 1);
    const checks = f.requests.filter(row => row.path === "migration/import/preview");
    assert.equal(checks.length, 2); assert.equal(checks[1].body.upload_id, checks[0].body.upload_id);
    assert.equal(checks[1].body.destination, "C:/EmptyDestination");
    assert.equal(f.requests.filter(row => row.path === "migration/import/commit").length, 0);
  } finally { f.close(); }
});

test("a broken package asks for a new package rather than retrying the same bytes or changing directories", async () => {
  const f = fixture({fetchImpl: uploadResponder({badPackage: true})});
  try {
    await f.ready(); await choose(f);
    assert.ok(f.input(), "the user can choose a fresh export");
    assert.equal(f.button("重新上传迁移包"), undefined);
    assert.equal(f.button("检查存放位置"), undefined);
    assert.equal(f.button("导入并使用"), undefined);
  } finally { f.close(); }
});

test("an unconfirmed commit survives reload and checks the same upload instead of starting a second import", async () => {
  const storage = new Map();
  const first = fixture({storage, fetchImpl: (path, options, body) => {
    if (path === "migration/import/start") return json({upload_id: "upload-fixture", chunk_size: 4});
    if (path.startsWith("migration/import/chunk")) return json({received: 4});
    if (path === "migration/import/preview") return json(preview(body.destination));
    if (path === "migration/import/commit") throw new TypeError("Failed to fetch");
    throw new Error(`Unexpected route ${path}`);
  }});
  try {
    await first.ready(); await choose(first);
    first.button("导入并使用").props.onClick(); await settle(); first.render();
    assert.equal(JSON.parse(storage.get(OPERATION_KEY)).committed, true);
    assert.ok(first.button("检查本次导入请求")); assert.equal(first.input(), undefined);
  } finally { first.close(); }
  const f = fixture({storage, fetchImpl: (path, options, body) => {
    if (path === "migration/import/commit") {
      assert.equal(body.upload_id, "upload-fixture"); return json({operation_id: "operation-fixture"});
    }
    if (path === "migration/operations/operation-fixture") return json({status: "running"});
    throw new Error(`Unexpected route ${path}`);
  }});
  try {
    await f.ready(); assert.equal(f.input(), undefined);
    assert.match(f.text(), /尚未确认本次导入结果/);
    f.button("检查本次导入请求").props.onClick(); await settle(); f.render();
    assert.equal(f.requests.filter(row => row.path === "migration/import/commit").length, 1);
    assert.equal(f.requests.filter(row => row.path === "migration/import/start").length, 0);
    assert.equal(JSON.parse(storage.get(OPERATION_KEY)).operation_id, "operation-fixture");
  } finally { f.close(); }
});

test("failed import keeps typed diagnostics but cannot recommit its stale directory plan", async () => {
  const storage = new Map([[OPERATION_KEY, JSON.stringify({operation_id: "operation-fixture", upload_id: "upload-fixture", destination: "C:/NewLibrary", preview: preview()})]]);
  const issue = detail("disk_full");
  const f = fixture({storage, fetchImpl: path => {
    if (path === "migration/operations/operation-fixture") return json({status: "failed", error: "raw disk traceback", error_detail: issue});
    throw new Error(`Unexpected route ${path}`);
  }});
  try {
    await f.ready();
    assert.ok(f.input()); assert.equal(f.button("导入并使用"), undefined); assert.equal(f.location(), undefined);
    assert.equal(f.notices().at(-1).props.error.code, "disk_full");
    assert.doesNotMatch(f.text(), /raw disk traceback/);
  } finally { f.close(); }
});

test("restored data retries activation with its original upload rather than offering a second import", async () => {
  const storage = new Map([[OPERATION_KEY, JSON.stringify({operation_id: "failed-activation", upload_id: "upload-fixture", destination: "C:/NewLibrary", preview: preview()})]]);
  const f = fixture({storage, fetchImpl: (path, options, body) => {
    if (path === "migration/operations/failed-activation") return json({status: "failed", error_detail: detail("file_permission"), result: {activated: false}});
    if (path === "migration/import/commit") { assert.equal(body.upload_id, "upload-fixture"); return json({operation_id: "activation-retry"}); }
    throw new Error(`Unexpected route ${path}`);
  }});
  try {
    await f.ready(); assert.equal(f.input(), undefined);
    f.button("重试启用工作台").props.onClick(); await settle();
    assert.equal(f.requests.filter(row => row.path === "migration/import/commit").length, 1);
    assert.equal(f.requests.filter(row => row.path === "migration/import/start").length, 0);
  } finally { f.close(); }
});

test("download checks reject expired links in-page and cancel ZIP streams without buffering", async () => {
  const f = fixture();
  let cancelled = false;
  try {
    const check = f.exports.checkMigrationDownload;
    await assert.rejects(check("https://fixture.invalid/expired", async () => json({error: "下载链接已过期，请重新导出迁移包", error_detail: detail("migration_download_missing")}, 410)), error => error.status === 410);
    await check("https://fixture.invalid/file", async () => ({ok: true, headers: new Headers({"content-type": "application/zip"}),
      body: {async cancel() {cancelled = true;}}, arrayBuffer() {throw new Error("ZIP must remain streamed");}, blob() {throw new Error("ZIP must not enter a Blob");}}));
    assert.equal(cancelled, true);
    await assert.rejects(check("https://fixture.invalid/html", async () => new Response("login form", {headers: {"content-type": "text/html"}})), /重新导出/);
  } finally { f.close(); }
});
