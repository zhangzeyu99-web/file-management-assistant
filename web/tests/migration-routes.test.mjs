import test from "node:test";
import assert from "node:assert/strict";
import {migrationCloudRoute, MIGRATION_CHUNK_SIZE, MIGRATION_CLOUD_LIMIT} from "../lib/migration-cloud.ts";

const id = "00000000-0000-4000-8000-000000000099";
function fixture() {
  const values = new Map(), objects = new Map();
  const job = {id, kind: "migration_export", owner: "fixture-owner", status: "running", lease_until: Date.now() + 120000};
  const service = {
    getJob: async key => key === id ? {...job} : null,
    getState: async key => structuredClone(values.get(key) || null),
    publishState: async (key, value, expected, jobId, owner) => {
      if (jobId !== id || job.owner !== owner || job.status !== "running" || job.lease_until < Date.now() ||
          JSON.stringify(values.get(key) || null) !== JSON.stringify(expected)) return false;
      values.set(key, structuredClone(value));
      return true;
    },
    bucket: {
      put: async (key, bytes) => { objects.set(key, Uint8Array.from(bytes)); },
      head: async key => objects.has(key) ? {size: objects.get(key).length} : null,
      get: async key => objects.has(key) ? {size: objects.get(key).length, body: new Response(objects.get(key)).body} : null,
      delete: async keys => { for (const key of Array.isArray(keys) ? keys : [keys]) objects.delete(key); },
    },
  };
  const call = (path, data, raw = false) => migrationCloudRoute(
    new Request(`https://fixture.invalid/api/workspace/${path}`, data === undefined ? undefined : {
      method: "POST", body: raw ? data : JSON.stringify(data),
      headers: {"content-type": raw ? "application/octet-stream" : "application/json"},
    }), path.split("?")[0], service,
  );
  const start = size => call("agent/migration/start", {job_id: id, owner: job.owner, size, parts: Math.ceil(size / MIGRATION_CHUNK_SIZE)});
  const chunk = (part, bytes) => call(`agent/migration/chunk?job_id=${id}&part=${part}&owner=${job.owner}`, bytes, true);
  const finish = () => call("agent/migration/complete", {job_id: id, owner: job.owner});
  return {job, values, objects, service, call, start, chunk, finish};
}

test("multi-chunk export downloads exact ZIP bytes only after completion", async () => {
  const f = fixture();
  const first = new Uint8Array(MIGRATION_CHUNK_SIZE).fill(49), last = new Uint8Array([80, 75, 5, 6]);
  assert.equal((await f.start(first.length + last.length)).status, 200);
  assert.equal((await f.chunk(0, first)).status, 200);
  assert.equal((await f.finish()).status, 409, "missing part cannot publish");
  assert.equal((await f.chunk(1, last)).status, 200);
  assert.equal((await f.finish()).status, 200);
  assert.equal((await f.call(`migration/download/${id}`)).status, 409, "running job is not downloadable");
  f.job.status = "completed";
  const response = await f.call(`migration/download/${id}`);
  assert.equal(response.headers.get("content-type"), "application/zip");
  assert.match(response.headers.get("content-disposition"), /^attachment; filename="knowledge-/);
  assert.equal(Number(response.headers.get("content-length")), first.length + last.length);
  const actual = new Uint8Array(await response.arrayBuffer());
  assert.deepEqual(actual.subarray(0, first.length), first);
  assert.deepEqual(actual.subarray(first.length), last);
});

test("wrong owner, cancelled lease, oversize and invalid chunks do not publish", async () => {
  const f = fixture();
  assert.equal((await f.start(MIGRATION_CLOUD_LIMIT + 1)).status, 400);
  assert.equal((await f.start(4)).status, 200);
  assert.equal((await f.call(`agent/migration/chunk?job_id=${id}&part=0&owner=someone-else`, new Uint8Array(4), true)).status, 409);
  assert.equal((await f.chunk(0, new Uint8Array(5))).status, 413);
  assert.equal((await f.chunk(0, new Uint8Array(3))).status, 400);
  assert.equal((await f.chunk(2, new Uint8Array(4))).status, 409);
  assert.equal(f.objects.size, 0);
  f.job.status = "cancelled";
  assert.equal((await f.chunk(0, new Uint8Array(4))).status, 409);
  assert.equal((await f.finish()).status, 409);
});

test("cancellation during completeness checks cannot create a successful package", async () => {
  const f = fixture();
  await f.start(4); await f.chunk(0, new Uint8Array(4));
  const head = f.service.bucket.head;
  f.service.bucket.head = async key => { const result = await head(key); f.job.status = "cancelled"; return result; };
  assert.equal((await f.finish()).status, 409);
  assert.equal(f.values.get(`migration:${id}`).complete, false);
});

test("lease changes during start cannot overwrite or delete a newer upload session", async () => {
  const f = fixture();
  const key = `migration:${id}`;
  const newManifest = {job_id:id,owner:"new-owner",filename:"new.zip",size:4,parts:1,
    prefix:"new-session",complete:false,expires_at:Date.now()+60000};
  f.service.getState = async () => {
    f.job.owner = "new-owner";
    f.values.set(key, newManifest);
    f.objects.set("new-session/0", new Uint8Array([1,2,3,4]));
    return structuredClone(newManifest);
  };
  const response = await f.call("agent/migration/start", {job_id:id,owner:"fixture-owner",size:4,parts:1});
  assert.equal(response.status, 409);
  assert.deepEqual(f.values.get(key), newManifest);
  assert.deepEqual(f.objects.get("new-session/0"), new Uint8Array([1,2,3,4]));
});

test("a long chunk upload losing its owner does not write a part", async () => {
  const f = fixture();
  await f.start(4);
  const body = new ReadableStream({
    pull(controller) {
      f.job.owner = "replacement-owner";
      controller.enqueue(new Uint8Array([1,2,3,4]));
      controller.close();
    },
  });
  const response = await migrationCloudRoute(new Request(
    `https://fixture.invalid/api/workspace/agent/migration/chunk?job_id=${id}&part=0&owner=fixture-owner`,
    {method:"POST",body,duplex:"half"}), "agent/migration/chunk", f.service);
  assert.equal(response.status, 409);
  assert.equal(f.objects.size, 0);
});

test("completed exports are immutable and expired links are explicit", async () => {
  const f = fixture();
  await f.start(4); await f.chunk(0, new Uint8Array(4)); await f.finish();
  assert.equal((await f.start(4)).status, 409);
  assert.equal((await f.chunk(0, new Uint8Array(4))).status, 409);
  f.job.status = "completed";
  f.values.get(`migration:${id}`).expires_at = 1;
  assert.equal((await f.call(`migration/download/${id}`)).status, 410);
  assert.equal((await f.call("migration/download/../../secret")).status, 400);
});

test("cloud import never writes to the connected old machine", async () => {
  const f = fixture();
  const response = await f.call("migration/import/commit", {destination: "C:/anything"});
  assert.equal(response.status, 409);
  assert.match((await response.json()).error, /当前电脑/);
  assert.equal(f.values.size, 0);
});
