import { env } from "cloudflare:workers";
import { searchSnapshot } from "../../../../lib/search";
import { resolveWikiNote } from "../../../../lib/knowledge";
import { migrationCloudRoute, MIGRATION_CLOUD_LIMIT } from "../../../../lib/migration-cloud";
import { userIssue } from "../../../../lib/user-errors";

export const dynamic = "force-dynamic";
type Job = Record<string, any>;
const json = (body: unknown, status = 200) => {
  if (status >= 400) {
    const issue = userIssue(body, {status,context:"网站请求"});
    body = {error:issue.message,error_code:issue.code,error_detail:{code:issue.code,message:issue.message,action:issue.action,retryable:issue.retryable,help:issue.help}};
  }
  return Response.json(body, {status, headers: {"Cache-Control": "no-store"}});
};
const bindings = () => env as unknown as {DB: D1Database; BUCKET: R2Bucket; OW_LOCAL_API?: string};
const terminal = new Set(["completed", "partial", "failed", "cancelled"]);
function unpack(row: Job) {
  return {...row, input: JSON.parse(row.input || "{}"), result: row.result ? JSON.parse(row.result) : null};
}
async function snapshot() {
  const current=await state("snapshot");
  const object = await bindings().BUCKET.get(current?.object_key||"snapshot/current.json");
  return object ? await object.json<any>() : {overview:{projects:[],recent:[],note_count:0},projects:[],notes:[],sources:[]};
}
async function state(key: string) {
  const row = await bindings().DB.prepare("SELECT value FROM workspace_state WHERE key=?").bind(key).first<{value:string}>();
  return row ? JSON.parse(row.value) : null;
}
async function setState(key: string,value: unknown) {
  await bindings().DB.prepare("INSERT INTO workspace_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(key,JSON.stringify(value)).run();
}
async function publishMigration(key: string,value: unknown,expected: unknown,jobId: string,owner: string) {
  const changed=await bindings().DB.prepare(
    "INSERT INTO workspace_state(key,value) SELECT ?,? WHERE EXISTS(SELECT 1 FROM jobs WHERE id=? AND kind='migration_export' AND owner=? AND status='running' AND lease_until>=?) AND (SELECT value FROM workspace_state WHERE key=?) IS ? ON CONFLICT(key) DO UPDATE SET value=excluded.value RETURNING key"
  ).bind(key,JSON.stringify(value),jobId,owner,Date.now(),key,expected===null?null:JSON.stringify(expected)).first();
  return !!changed;
}
async function createJob(kind: string,input: any,id?: string) {
  const db=bindings().DB, now=Date.now(), activeKey=["update","migration_export"].includes(kind) ? kind : null;
  if(activeKey) {
    const active = await db.prepare("SELECT * FROM jobs WHERE active_key=?").bind(activeKey).first<Job>();
    if(active) return unpack(active);
  }
  const jobId=id||crypto.randomUUID();
  const existing=await db.prepare("SELECT * FROM jobs WHERE id=?").bind(jobId).first<Job>();
  if(existing) return unpack(existing);
  try {
    await db.prepare("INSERT INTO jobs(id,kind,input,status,stage,active_key,created_at,updated_at) VALUES(?,?,?,'queued','等待本机领取',?,?,?)").bind(jobId,kind,JSON.stringify(input),activeKey,now,now).run();
  } catch(e) {
    const same=await db.prepare("SELECT * FROM jobs WHERE id=?").bind(jobId).first<Job>();
    if(same)return unpack(same);
    if(activeKey) {
      const active=await db.prepare("SELECT * FROM jobs WHERE active_key=?").bind(activeKey).first<Job>();
      if(active)return unpack(active);
    }
    throw e;
  }
  return unpack((await db.prepare("SELECT * FROM jobs WHERE id=?").bind(jobId).first<Job>())!);
}

async function handler(req:Request) {
  try {
    const url=new URL(req.url), path=url.pathname.split("/api/workspace/")[1]||"";
    const b=bindings();
    if(req.method!=="GET") {
      const origin=req.headers.get("origin");
      if(origin && origin!==url.origin)return json({error:"请求来源不匹配"},403);
    }
    // Only the ignored local development binding activates the local endpoint.
    if(b.OW_LOCAL_API) {
      const local=new URL(b.OW_LOCAL_API);
      if(!["127.0.0.1","localhost"].includes(local.hostname))return json({error:"本机接口配置无效"},500);
      const headers=new Headers({"Content-Type":req.headers.get("content-type")||"application/json"});
      const result=await fetch(`${local.origin}/api/workspace/${path}${url.search}`,{method:req.method,headers,body:req.method==="GET"?undefined:await req.arrayBuffer()});
      return new Response(result.body,{status:result.status,headers:Object.fromEntries([...["content-type","content-length","content-disposition","x-content-type-options"].flatMap(key=>result.headers.has(key)?[[key,result.headers.get(key)!]]:[]),["Cache-Control","no-store"]])});
    }
    // The Site remains owner-private. Sites authenticates browser and service requests
    // before dispatch; browser identity and service identity intentionally differ.
    if(req.method!=="GET") {
      const origin=req.headers.get("origin");
      if(origin && origin!==url.origin)return json({error:"请求来源不匹配"},403);
    }
    if(path==="migration/status" && req.method==="GET") {
      const heartbeat=await state("heartbeat");
      const online=!!heartbeat && Date.now()-heartbeat.at<90000;
      return json({mode:"cloud",configured:true,online,can_export:true,device:heartbeat?.device||"本机",export_limit_bytes:MIGRATION_CLOUD_LIMIT});
    }
    const migrationResponse=await migrationCloudRoute(req,path,{
      bucket:b.BUCKET,getState:state,publishState:publishMigration,
      getJob:async id=>b.DB.prepare("SELECT * FROM jobs WHERE id=?").bind(id).first<Job>(),
    });
    if(migrationResponse)return migrationResponse;
    if(path==="health") {
      const heartbeat=await state("heartbeat");
      return json({mode:"cloud",online:!!heartbeat && Date.now()-heartbeat.at<90000,heartbeat,synced_at:(await state("snapshot"))?.at||null});
    }
    if(path==="overview") {
      const s=await snapshot();
      return json({...s.overview,note_aliases:s.note_aliases||s.overview.note_aliases||{},synced_at:s.generated_at,mode:"cloud"});
    }
    if(path==="projects") return json({items:(await snapshot()).projects});
    if(path.startsWith("projects/")) {
      const s=await snapshot(),id=decodeURIComponent(path.slice(9));
      const project=s.projects.find((p:any)=>p.id===id);
      if(!project)return json({error:"未找到项目"},404);
      const byId=new Map(s.sources.map((item:any)=>[item.id,item]));
      const items=Array.isArray(project.source_ids)
        ? project.source_ids.map((sourceId:string)=>byId.get(sourceId)).filter(Boolean)
        : s.sources.filter((item:any)=>item.project===project.title);
      return json({...project,items});
    }
    if(path==="search") {
      const s=await snapshot(),query=url.searchParams.get("q")||"";
      return json(searchSnapshot(s,query,Math.max(0,Math.min(5000,Number(url.searchParams.get("limit")??50)))));
    }
    if(path==="notes/resolve") {
      const s=await snapshot();
      try { return json(resolveWikiNote(s.notes,s.note_aliases||{},url.searchParams.get("target")||"",url.searchParams.get("from")||"")); }
      catch(error) { return json({error:error instanceof Error?error.message:"未找到链接笔记"},404); }
    }
    if(path.startsWith("notes/")) {
      const s=await snapshot(),id=decodeURIComponent(path.slice(6));
      const source=s.sources.find((i:any)=>i.id===id);
      const noteId=source?.note_id||(!id.includes(":")&&s.note_aliases?.[id])||id;
      const note=s.notes.find((i:any)=>i.id===noteId);
      return note?json({...note,focus:source}):json({error:"未找到笔记，请检查最新同步结果"},404);
    }
    if(path==="jobs"&&req.method==="GET") {
      const rows=await b.DB.prepare("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 80").all<Job>();
      return json({items:rows.results.map(unpack)});
    }
    if(path==="jobs"&&req.method==="POST") {
      const data=await req.json() as any;
      if(!["update","update_preview","answer","context","ingest","migration_export"].includes(data.kind))return json({error:"不支持的操作"},400);
      if(data.kind==="migration_export" && data.request_id && !/^[a-zA-Z0-9-]{10,80}$/.test(data.request_id))return json({error:"请求标识无效"},400);
      if(JSON.stringify(data).length>180000)return json({error:"文字过长，请通过文件上传"},413);
      return json(await createJob(data.kind,data.input||{},data.request_id),202);
    }
    if(path==="upload"&&req.method==="POST") {
      const data=await req.json() as any;
      if(!data.filename||typeof data.content!=="string"||data.content.length>16*1024*1024)return json({error:"请选择不超过 12 MB 的文件"},400);
      const bytes=Uint8Array.from(atob(data.content),(c)=>c.charCodeAt(0));
      const id=typeof data.request_id==="string"?data.request_id:crypto.randomUUID();
      if(!/^[a-zA-Z0-9-]{10,80}$/.test(id))return json({error:"请求标识无效"},400);
      const prior=await b.DB.prepare("SELECT * FROM jobs WHERE id=?").bind(id).first<Job>();
      if(prior)return json(unpack(prior),202);
      // Immutable object per attempt: racing retries cannot replace a queued job's bytes.
      const key=`uploads/${crypto.randomUUID()}`;
      await b.BUCKET.put(key,bytes);
      return json(await createJob("ingest",{upload_key:key,filename:String(data.filename).split(/[\\/]/).pop()},id),202);
    }
    if(path.startsWith("jobs/")) {
      const [,id,action]=path.split("/");
      const row=await b.DB.prepare("SELECT * FROM jobs WHERE id=?").bind(id).first<Job>();
      if(!row)return json({error:"未找到任务"},404);
      if(action==="retry"&&req.method==="POST") {
        if(!["failed","partial","cancelled"].includes(row.status))return json({error:"此任务不需要重试"},409);
        const input=JSON.parse(row.input);
        return json(await createJob(row.kind,{...input,retry_of:input.retry_of||id,
          sync_only:!!(row.result&&JSON.parse(row.result).sync_pending)}));
      }
      if(action==="cancel"&&req.method==="POST") {
        if(terminal.has(row.status))return json(unpack(row));
        await b.DB.prepare("UPDATE jobs SET status='cancelled',stage='已取消后续处理',active_key=NULL,owner=NULL,updated_at=? WHERE id=? AND status IN ('queued','running')").bind(Date.now(),id).run();
        return json(unpack((await b.DB.prepare("SELECT * FROM jobs WHERE id=?").bind(id).first<Job>())!));
      }
      return json(unpack(row));
    }
    if(path==="agent/heartbeat"&&req.method==="POST") {
      const data=await req.json() as any;
      await setState("heartbeat",{at:Date.now(),device:data.device||"本机",capabilities:data.capabilities||{}});
      return json({ok:true});
    }
    if(path==="agent/claim"&&req.method==="POST") {
      const {owner}=await req.json() as any;
      if(typeof owner!=="string"||owner.length>100)return json({error:"执行器标识无效"},400);
      const now=Date.now();
      const row=await b.DB.prepare("UPDATE jobs SET status='running',stage='本机已领取',owner=?,lease_until=?,updated_at=? WHERE id=(SELECT id FROM jobs WHERE status='queued' OR (status='running' AND lease_until<?) ORDER BY created_at LIMIT 1) RETURNING *").bind(owner,now+120000,now,now).first<Job>();
      return json({job:row?unpack(row):null});
    }
    if(path.startsWith("agent/jobs/")&&req.method==="POST") {
      const id=path.slice(11), data=await req.json() as any;
      const row=await b.DB.prepare("SELECT * FROM jobs WHERE id=?").bind(id).first<Job>();
      if(!row||row.owner!==data.owner||row.status!=="running"||row.lease_until<Date.now())return json({error:"任务租约已失效或任务已取消"},409);
      const status=["running","completed","partial","failed"].includes(data.status)?data.status:"running";
      const result=data.result===undefined?row.result:JSON.stringify(data.result);
      if(result && result.length>750000)return json({error:"结果过大，请分批同步"},413);
      const changed=await b.DB.prepare("UPDATE jobs SET status=?,stage=CASE WHEN ? THEN ? ELSE stage END,result=CASE WHEN ? THEN ? ELSE result END,error=CASE WHEN ? THEN ? ELSE error END,lease_until=?,active_key=CASE WHEN ? THEN NULL ELSE active_key END,updated_at=? WHERE id=? AND owner=? AND status='running' AND lease_until>=? RETURNING id").bind(
        status,data.stage!==undefined?1:0,data.stage||null,data.result!=null?1:0,data.result==null?null:result,
        data.error!==undefined?1:0,data.error||null,Date.now()+120000,terminal.has(status)?1:0,Date.now(),id,data.owner,Date.now()).first();
      if(!changed)return json({error:"任务租约已失效或任务已取消"},409);
      return json({ok:true});
    }
    if(path==="agent/snapshot"&&req.method==="POST") {
      const data=await req.json() as any;
      if(!Array.isArray(data.notes)||!Array.isArray(data.sources)||!data.overview)return json({error:"知识快照格式无效"},400);
      const sourceAt=Date.parse(data.generated_at);
      if(!Number.isFinite(sourceAt))return json({error:"知识副本时间无效"},400);
      const prior=await state("snapshot");
      if(prior?.source_at>=sourceAt)return json({ok:true,unchanged:true,notes:prior.notes});
      const objectKey=`snapshots/${sourceAt}-${crypto.randomUUID()}.json`;
      await b.BUCKET.put(objectKey,JSON.stringify(data),{httpMetadata:{contentType:"application/json"}});
      const value=JSON.stringify({at:Date.now(),source_at:sourceAt,object_key:objectKey,generated_at:data.generated_at,notes:data.notes.length});
      const committed=await b.DB.prepare("INSERT INTO workspace_state(key,value) VALUES('snapshot',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE COALESCE(CAST(json_extract(workspace_state.value,'$.source_at') AS REAL),0)<? RETURNING key").bind(value,sourceAt).first();
      return json({ok:true,unchanged:!committed,notes:data.notes.length});
    }
    if(path==="agent/upload"&&req.method==="GET") {
      const key=url.searchParams.get("key")||"";
      if(!/^uploads\/[a-zA-Z0-9-]{10,80}$/.test(key))return json({error:"文件标识无效"},400);
      const obj=await b.BUCKET.get(key);
      return obj?new Response(obj.body,{headers:{"Content-Type":"application/octet-stream"}}):json({error:"上传文件已不存在"},404);
    }
    return json({error:"未找到接口"},404);
  } catch(e) { return json({error:e instanceof Error?e.message:"操作失败"},500); }
}
export const GET=handler;
export const POST=handler;
