import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import {DatabaseSync} from "node:sqlite";
import ts from "typescript";
import {migrationCloudRoute, MIGRATION_CLOUD_LIMIT} from "../lib/migration-cloud.ts";

const routeSource = fs.readFileSync(new URL("../app/api/workspace/[...path]/route.ts", import.meta.url), "utf8")
  .replace(/^import .*$/gm, "").replace(/^export /gm, "") + "\nglobalThis.handleTest=handler;";
const code = ts.transpileModule(routeSource, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText;
function fixture(local = false) {
  const db = new DatabaseSync(":memory:");
  db.exec(fs.readFileSync(new URL("../drizzle/0000_certain_photon.sql", import.meta.url), "utf8"));
  const hooks = {}, objects = new Map();
  const DB = {prepare(sql) {
    let args = [];
    return {
      bind(...values) { args = values; return this; },
      async first() {
        await hooks.beforeFirst?.(sql);
        return db.prepare(sql).get(...args) || null;
      },
      async all() { return {results: db.prepare(sql).all(...args)}; },
      async run() { return db.prepare(sql).run(...args); },
    };
  }};
  const bucket = {
    put: async (key, bytes) => { objects.set(key, Uint8Array.from(bytes)); },
    head: async key => objects.has(key) ? {size: objects.get(key).length} : null,
    get: async key => objects.has(key) ? {size: objects.get(key).length, body: new Response(objects.get(key)).body} : null,
    delete: async keys => { for (const key of Array.isArray(keys) ? keys : [keys]) objects.delete(key); },
  };
  const observed = [];
  const context = {
    env: {DB, BUCKET: bucket, ...(local ? {OW_LOCAL_API: "http://127.0.0.1:8767"} : {})},
    migrationCloudRoute, MIGRATION_CLOUD_LIMIT, searchSnapshot: () => ({}),
    Response, Request, URL, Headers, crypto, atob, Uint8Array, Date,
    fetch: async (url, options) => {
      observed.push({url, options});
      return new Response(new Uint8Array([80, 75]), {headers: {
        "content-type": "application/zip", "content-length": "2",
        "content-disposition": 'attachment; filename="knowledge.zip"',
      }});
    },
  };
  vm.runInNewContext(code, context);
  const call = (path, data, origin) => context.handleTest(new Request(`https://fixture.invalid/api/workspace/${path}`, {
    method: data === undefined ? "GET" : "POST",
    headers: {"content-type": "application/json", ...(origin ? {origin} : {})},
    ...(data === undefined ? {} : {body: JSON.stringify(data)}),
  }));
  const raw = (path, body) => context.handleTest(new Request(`https://fixture.invalid/api/workspace/${path}`, {
    method:"POST",headers:{"content-type":"application/octet-stream"},body,
  }));
  return {db, observed, call, raw, objects, hooks};
}

test("real SQL queue reuses an active export and supports an independent next export", async () => {
  const f = fixture();
  try {
    const [a, b] = await Promise.all([
      f.call("jobs", {kind: "migration_export", input: {}, request_id: crypto.randomUUID()}),
      f.call("jobs", {kind: "migration_export", input: {}, request_id: crypto.randomUUID()}),
    ]);
    assert.equal(a.status, 202); assert.equal(b.status, 202);
    const first = await a.json();
    assert.equal((await b.json()).id, first.id);
    f.db.prepare("UPDATE jobs SET status='completed',active_key=NULL WHERE id=?").run(first.id);
    const next = await (await f.call("jobs", {kind: "migration_export", input: {}})).json();
    assert.notEqual(next.id, first.id);
    assert.equal(f.db.prepare("SELECT count(*) AS n FROM jobs").get().n, 2);
  } finally { f.db.close(); }
});

test("cloud migration status reflects offline executor and refuses remote import", async () => {
  const f = fixture();
  try {
    const status = await (await f.call("migration/status")).json();
    assert.equal(status.mode, "cloud"); assert.equal(status.online, false);
    assert.equal(status.export_limit_bytes, MIGRATION_CLOUD_LIMIT);
    assert.equal((await f.call("migration/import/start", {filename: "x.zip", size: 4})).status, 409);
  } finally { f.db.close(); }
});

test("local proxy keeps attachment headers and rejects cross-origin mutations before forwarding", async () => {
  const f = fixture(true);
  try {
    const download = await f.call("migration/download/00000000-0000-4000-8000-000000000001");
    assert.equal(download.headers.get("content-disposition"), 'attachment; filename="knowledge.zip"');
    assert.equal(download.headers.get("content-length"), "2");
    assert.equal((await f.call("migration/import/commit", {}, "https://foreign.invalid")).status, 403);
    assert.equal(f.observed.length, 1);
  } finally { f.db.close(); }
});

test("real SQL export publishes and downloads only after both package and job complete", async () => {
  const f = fixture();
  try {
    const job = await (await f.call("jobs", {kind:"migration_export",input:{}})).json();
    await f.call("agent/claim", {owner:"owner-a"});
    const payload = {job_id:job.id,owner:"owner-a",filename:"local-export.zip",size:4,parts:1};
    assert.equal((await f.call("agent/migration/start", payload)).status, 200);
    const bytes = new Uint8Array([80,75,5,6]);
    assert.equal((await f.raw(`agent/migration/chunk?job_id=${job.id}&part=0&owner=owner-a`, bytes)).status, 200);
    const complete = await f.call("agent/migration/complete", payload);
    assert.equal(complete.status, 200);
    const metadata = await complete.json();
    assert.match(metadata.filename, /^knowledge-\d{4}-\d{2}-\d{2}\.zip$/);
    assert.equal((await f.call(`migration/download/${job.id}`)).status, 409);
    assert.equal((await f.call(`agent/jobs/${job.id}`, {owner:"owner-a",status:"completed",result:metadata})).status, 200);
    const downloaded = await f.call(`migration/download/${job.id}`);
    assert.equal(downloaded.status, 200);
    assert.deepEqual(new Uint8Array(await downloaded.arrayBuffer()), bytes);
  } finally { f.db.close(); }
});

test("real SQL lease fence stops old start and completion immediately before publication", async () => {
  for (const stage of ["start","complete"]) {
    const f = fixture();
    try {
      const job = await (await f.call("jobs", {kind:"migration_export",input:{}})).json();
      await f.call("agent/claim", {owner:"owner-a"});
      const payload = {job_id:job.id,owner:"owner-a",size:4,parts:1};
      if (stage === "complete") {
        await f.call("agent/migration/start", payload);
        await f.raw(`agent/migration/chunk?job_id=${job.id}&part=0&owner=owner-a`, new Uint8Array(4));
      }
      const newer = {job_id:job.id,owner:"owner-b",filename:"new.zip",size:4,parts:1,
        prefix:"new-prefix",complete:false,expires_at:Date.now()+60000};
      f.hooks.beforeFirst = sql => {
        if (!sql.startsWith("INSERT INTO workspace_state(key,value) SELECT")) return;
        f.hooks.beforeFirst = null;
        f.db.prepare("UPDATE jobs SET owner=? WHERE id=?").run("owner-b",job.id);
        f.db.prepare("INSERT INTO workspace_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value")
          .run(`migration:${job.id}`,JSON.stringify(newer));
        f.objects.set("new-prefix/0",new Uint8Array([1,2,3,4]));
      };
      assert.equal((await f.call(`agent/migration/${stage}`,payload)).status,409,stage);
      const saved = JSON.parse(f.db.prepare("SELECT value FROM workspace_state WHERE key=?").get(`migration:${job.id}`).value);
      assert.deepEqual(saved,newer,stage);
      assert.deepEqual(f.objects.get("new-prefix/0"),new Uint8Array([1,2,3,4]),stage);
    } finally { f.db.close(); }
  }
});
