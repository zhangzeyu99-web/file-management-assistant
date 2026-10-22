/** Bounded file transfer for the private Site; file bytes never enter D1. */
import { userIssue } from "./user-errors.ts";
export const MIGRATION_CHUNK_SIZE = 4 * 1024 * 1024;
export const MIGRATION_CLOUD_LIMIT = 128 * 1024 * 1024;
const RETENTION_MS = 24 * 60 * 60 * 1000;
const ID = /^[a-zA-Z0-9-]{10,80}$/;
type Manifest = {
  job_id: string; owner: string; filename: string; size: number; parts: number;
  prefix: string; complete: boolean; expires_at: number;
};
type Services = {
  bucket: R2Bucket;
  getJob: (id: string) => Promise<Record<string, any> | null>;
  getState: (key: string) => Promise<any>;
  publishState: (key: string, value: unknown, expected: unknown, jobId: string, owner: string) => Promise<boolean>;
};
const json = (body: unknown, status = 200) => {
  if (status >= 400) {
    const issue = userIssue(body, {status,context:"迁移传输"});
    body = {error:issue.message,error_code:issue.code,error_detail:{code:issue.code,message:issue.message,action:issue.action,retryable:issue.retryable,help:issue.help}};
  }
  return Response.json(body, {status, headers: {"Cache-Control": "no-store"}});
};
const partKey = (m: Manifest, index: number) => `${m.prefix}/${index}`;
const partSize = (m: Manifest, index: number) => Math.min(MIGRATION_CHUNK_SIZE, m.size - index * MIGRATION_CHUNK_SIZE);
const validLease = (job: Record<string, any> | null, owner: unknown) =>
  job?.kind === "migration_export" && job.status === "running" &&
  typeof owner === "string" && !!owner && job.owner === owner && job.lease_until >= Date.now();

export async function migrationCloudRoute(req: Request, path: string, s: Services): Promise<Response | null> {
  const url = new URL(req.url);
  if (path.startsWith("migration/import/") || path.startsWith("migration/operations/")) {
    return json({error: "导入需要在当前电脑的本机工作台完成，线上不会替换另一台电脑的资料。"}, 409);
  }
  if (path.startsWith("migration/download/") && req.method === "GET") {
    const id = path.slice("migration/download/".length);
    if (!ID.test(id)) return json({error: "迁移包标识无效"}, 400);
    const job = await s.getJob(id);
    const m = await s.getState(`migration:${id}`) as Manifest | null;
    if (!m?.complete || job?.kind !== "migration_export" || job.status !== "completed") {
      return json({error: "迁移包尚未准备好，请等待导出完成"}, 409);
    }
    if (m.expires_at <= Date.now()) return json({error: "下载链接已过期，请重新导出迁移包"}, 410);
    // Pull one stored chunk at a time. A large ZIP never becomes an ArrayBuffer.
    let index = 0;
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
    const stream = new ReadableStream<Uint8Array>({
      async pull(controller) {
        try {
          while (true) {
            if (!reader) {
              if (index === m.parts) { controller.close(); return; }
              const object = await s.bucket.get(partKey(m, index));
              if (!object || object.size !== partSize(m, index)) throw new Error("迁移包文件不完整，请重新导出");
              reader = object.body.getReader();
              index += 1;
            }
            const next = await reader.read();
            if (next.done) { reader.releaseLock(); reader = null; continue; }
            controller.enqueue(next.value);
            return;
          }
        } catch (error) { controller.error(error); }
      },
      async cancel() { await reader?.cancel(); reader = null; },
    });
    return new Response(stream, {headers: {
      "Content-Type": "application/zip", "Content-Length": String(m.size),
      "Content-Disposition": `attachment; filename="${m.filename}"`,
      "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    }});
  }
  if (!path.startsWith("agent/migration/")) return null;
  if (req.method !== "POST") return json({error: "不支持的请求方式"}, 405);

  if (path === "agent/migration/start") {
    const data = await req.json() as any;
    if (!ID.test(data.job_id || "") || !Number.isSafeInteger(data.size) || data.size <= 0 ||
        data.size > MIGRATION_CLOUD_LIMIT || data.parts !== Math.ceil(data.size / MIGRATION_CHUNK_SIZE)) {
      return json({error: "线上迁移包须不超过 128 MB，且分片信息完整"}, 400);
    }
    if (!validLease(await s.getJob(data.job_id), data.owner)) return json({error: "任务租约已失效或任务已取消"}, 409);
    const existing = await s.getState(`migration:${data.job_id}`) as Manifest | null;
    if (existing?.complete) return json({error: "此迁移包已完成，不能覆盖"}, 409);
    const manifest: Manifest = {
      job_id: data.job_id, owner: data.owner,
      filename: `knowledge-${new Date().toISOString().slice(0, 10)}.zip`,
      size: data.size, parts: data.parts, prefix: `migration/${data.job_id}/${crypto.randomUUID()}`,
      complete: false, expires_at: Date.now() + RETENTION_MS,
    };
    // Publish only if both the lease and the observed manifest still match.
    // An old request must neither replace a new session nor delete its objects.
    if (!await s.publishState(`migration:${data.job_id}`, manifest, existing, data.job_id, data.owner)) {
      return json({error: "任务租约或上传会话已变化，请重试"}, 409);
    }
    if (existing) {
      try {
        await s.bucket.delete(Array.from({length: existing.parts}, (_, i) => partKey(existing, i)));
      } catch { /* The new session is usable even if orphan cleanup is delayed. */ }
    }
    return json({ok: true, chunk_size: MIGRATION_CHUNK_SIZE});
  }
  if (path === "agent/migration/chunk") {
    const id = url.searchParams.get("job_id") || "";
    const owner = url.searchParams.get("owner");
    const partValue = url.searchParams.get("part");
    const part = partValue === null ? NaN : Number(partValue);
    if (!ID.test(id) || !Number.isSafeInteger(part) || part < 0) return json({error: "分片标识无效"}, 400);
    if (!validLease(await s.getJob(id), owner)) return json({error: "任务租约已失效或任务已取消"}, 409);
    const m = await s.getState(`migration:${id}`) as Manifest | null;
    if (!m || m.owner !== owner || m.complete || part >= m.parts) return json({error: "上传会话不可用"}, 409);
    const expected = partSize(m, part);
    const declaredLength = req.headers.get("content-length");
    if (declaredLength !== null && Number(declaredLength) !== expected) return json({error: "分片大小不匹配"}, 400);
    // Hard cap even when a malicious caller omits Content-Length.
    const chunks: Uint8Array[] = [];
    let size = 0;
    const reader = req.body?.getReader();
    if (!reader) return json({error: "分片内容为空"}, 400);
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      size += next.value.byteLength;
      if (size > expected) { await reader.cancel(); return json({error: "分片超过允许大小"}, 413); }
      chunks.push(next.value);
    }
    if (size !== expected) return json({error: "分片大小不匹配"}, 400);
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const current = await s.getState(`migration:${id}`) as Manifest | null;
    if (!validLease(await s.getJob(id), owner) || current?.prefix !== m.prefix ||
        current.owner !== owner || current.complete) {
      return json({error: "任务租约或上传会话已变化，请重试"}, 409);
    }
    await s.bucket.put(partKey(m, part), bytes, {httpMetadata: {contentType: "application/octet-stream"}});
    const after = await s.getState(`migration:${id}`) as Manifest | null;
    if (!validLease(await s.getJob(id), owner) || after?.prefix !== m.prefix || after.complete) {
      return json({error: "任务租约或上传会话已变化，请重试"}, 409);
    }
    return json({ok: true, part, received: size});
  }
  if (path === "agent/migration/complete") {
    const data = await req.json() as any;
    if (!ID.test(data.job_id || "")) return json({error: "迁移包标识无效"}, 400);
    if (!validLease(await s.getJob(data.job_id), data.owner)) return json({error: "任务租约已失效或任务已取消"}, 409);
    const m = await s.getState(`migration:${data.job_id}`) as Manifest | null;
    if (!m || m.owner !== data.owner) return json({error: "上传会话不可用"}, 409);
    for (let i = 0; i < m.parts; i++) {
      const object = await s.bucket.head(partKey(m, i));
      if (!object || object.size !== partSize(m, i)) return json({error: "迁移包分片不完整，尚未发布下载"}, 409);
    }
    // D1 atomically checks ownership and the session after all object I/O.
    if (!await s.publishState(`migration:${data.job_id}`, {...m, complete: true}, m, data.job_id, data.owner)) {
      return json({error: "任务租约或上传会话已变化，请重试"}, 409);
    }
    return json({download_url: `/api/workspace/migration/download/${data.job_id}`,
      filename: m.filename, size: m.size, expires_at: m.expires_at});
  }
  return json({error: "未找到迁移接口"}, 404);
}
