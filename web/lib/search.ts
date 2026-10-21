/** Same evidence ranking contract as engine/library.py; no generated claims. */
const aliases:Record<string,string[][]>={
  "热血合服":[["热血","合服"],["hotblood","merge"]],
  "欧美冒险合服":[["冒险","合服"]],
  "本地化":[["本地化"],["localization"],["lqa"],["术语"]],
  "简历与求职":[["简历"],["求职"],["resume"],["个人主页"]],
  "洛克计算器":[["洛克"],["rococalc"],["roco"],["rock-calculator"]],
  "视频知识库":[["视频","总结"],["播客"],["next token"]],
  "Obsidian 知识库":[["obsidian"],["知识行动助手"],["知识整理助手"],["个人知识工作台"]],
  "TopData":[["topdata"],["t后台"]],"Hell Asylum":[["hell asylum"]],
};
const normal=(s:string)=>String(s||"").toLowerCase().replace(/[^a-z0-9\u3400-\u9fff]/g,"");
const withoutComments=(s:string)=>String(s||"").replace(/<!--[\s\S]*?(?:-->|$)/g,m=>"\n".repeat((m.match(/\n/g)||[]).length));
const plain=(s:string)=>withoutComments(s)
  .replace(/\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g,"$1")
  .replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g,(_match,target,label)=>label||target)
  .replace(/^\s*(?:#{1,6}|[-*+]|\d+[.)])\s+/gm,"")
  .replace(/[`*_]/g,"").trim();
const wordAliases:[RegExp,string][]=[
  [/服务器合并|合并服务器|并服/g,"合服"],
  [/名称冲突|名字冲突|中文撞名|撞名|同名/g,"重名"],
  [/每日自动报告|每日自动汇报|每日报告|自动报告|codex\s+daily\s+review/g,"日报"],
  [/自动运行/g,"自动任务"],
  [/先后步骤|先后顺序|顺序操作|操作顺序|流程|做法|方法/g,"步骤"],
  [/windows|桌面版|桌面(?=\s*\d|安装包|包)/g,"windows"],
  [/安装程序|安装文件/g,"安装包"],
  [/github\s+release|release/g,"发布"],
  [/三天/g,"3天"],
  [/活跃人数|活跃用户数|活跃玩家数/g,"登录用户数"],
  [/增量/g,"新增"],
];
const canonical=(s:string)=>wordAliases.reduce((value,[pattern,replacement])=>value.replace(pattern,replacement),String(s||"").toLowerCase());
const roundScore=(score:number)=>{
  const scaled=score*100,lower=Math.floor(scaled);
  if(Number.isInteger(score*8)&&scaled-lower===.5)return (lower+lower%2)/100;
  return Number(score.toFixed(2));
};
const filler=/我(?:们)?(?:上次|之前|以前|以前的|想|想要|需要)?|上次|之前|以前|请问|请|帮我|帮忙|找一下|找回|查一下|为什么|为何|怎么(?:做|处理|用|的)?|怎样|如何|什么|哪些|有没有|是否|做过|处理过|做了|做的|具体|曾经|当时|告诉我|现在|继续|总结一下|(?:做过|处理过|做了|做的|的吗|了吗|呢|吗|的)$/g;
const joiner=/需要|避免|哪一天|哪个|区分|处理|怎么查|从|到|与|和|的|要|是|时|按/g;
const soft=new Set(["步骤","发布","交付","文件","检查","更新","统计","项目","成果","记录","完成","操作","查询","codex","id","没有","日期","总结","知识","使用","采用","分开","不能","直接","整理"]);
const words=new Set([...soft,"合服","重名","安装包","windows","字幕","转写","飞书","归档","新增","重复","旧文件","旧线程","线程","自动任务","日报","登录用户数","用户数","登录","活跃","除以","统计口径","战力","付费","分组","规则","边界","名单","技能名","技能","术语","中文","数据","校验","权限","错误","失败","重试","取消","来源","同步","备份","回滚","报告","维护","测试","结果","版本"]);
const wordPattern=new RegExp([...words].sort((a,b)=>b.length-a.length||(a<b?-1:a>b?1:0)).join("|"),"g");
const sourcePlaceholder=/仅收录来源|仅登记来源|仅收录元数据|未读取或总结正文|未读取正文/;
const searchText=(value:string)=>{
  let text=canonical(plain(value));
  if(/先.{0,50}再/.test(text))text+=" 步骤";
  return normal(text);
};
// Snapshot identity changes on publication; normalized source strings are reused
// across queries without retaining previous snapshots.
const rowCache=new WeakMap<object,Map<string,[string,string]>>();
function supplementResultTable(snapshot:any,items:any[],requested:string[]) {
  // Keep the first lexical match. A complete note is a visible source with its
  // existing note ID, not hidden extra model context or a fabricated table.
  for(let index=0;index<Math.min(items.length,6);index++) {
    const seed=items[index];
    if(!/^(?:新增需求|需求|未完成|待处理|下一步)$/.test(seed.title))continue;
    const note=(snapshot.notes||[]).find((n:any)=>n.id===seed.note_id);
    if(!note||note.archived||note.searchable===false||note.maintenance||String(note.markdown).length>12000)continue;
    const title=normal(canonical(withoutComments(note.title)));
    const projects=Object.keys(aliases).filter(k=>aliases[k].some(parts=>parts.every(p=>title.includes(normal(p)))));
    if(projects.length!==1||!requested.includes(projects[0])||sourcePlaceholder.test(note.markdown))continue;
    const sources=(snapshot.sources||[]).filter((p:any)=>p.note_id===note.id);
    if(sources.some((p:any)=>p.project!==projects[0]))continue;
    const table=sources.filter((p:any)=>/^(?:实际结果|交付结果|本轮结果|完成情况|已完成)$/.test(p.title)&&String(p.text).trim().startsWith("|"));
    if(table.length<3)continue;
    const excerpt=plain(table.map((p:any)=>String(p.text).trim().replace(/^\||\|$/g,"").replace(/\s*\|\s*/g," · ")).join("\n")).replace(/\s+/g," ").trim();
    const {other_sources:unused,...base}=seed;
    const supplement={...base,id:note.id,note_id:note.id,kind:"note",title:note.title,note_title:note.title,section:note.title,
      text:note.markdown,excerpt:excerpt.length<=320?excerpt:excerpt.slice(0,320).trimEnd()+"…",
      line_start:1,line_end:String(note.markdown).split("\n").length,thread_links:note.thread_links||[],content_complete:true,
      score:roundScore(Math.max(seed.score-.01,.1)),retrieval_reason:"same_note_result_table",
      supporting_source_ids:table.map((p:any)=>p.id)};
    const position=Math.min(index+1,5);
    return [...items.slice(0,position),supplement,...items.slice(position)];
  }
  return items;
}
export function searchSnapshot(snapshot:any,query:string,limit=50) {
  query=String(query||"").trim();
  const queryValue=normal(canonical(withoutComments(query)));
  const requested=Object.keys(aliases).filter(k=>aliases[k].some(parts=>parts.every(p=>queryValue.includes(normal(p)))));
  if(query.includes("翻译")&&!requested.includes("本地化"))requested.push("本地化");
  let intent=canonical(query);
  for(const project of requested) {
    intent=intent.split(canonical(project)).join(" ");
    for(const parts of aliases[project])for(const part of parts)intent=intent.split(canonical(part)).join(" ");
  }
  if(requested.includes("本地化"))intent=intent.replace(/翻译/g," ");
  const clean=canonical(intent).replace(filler," ").replace(joiner," ").trim(),focus=normal(clean);
  const separated=clean.replace(wordPattern,m=>" "+m+" ");
  let terms=[...new Set((separated.match(/[a-z0-9][a-z0-9_.+-]*|[\u3400-\u9fff]+/g)||[]).flatMap(t=>{
    t=normal(t);if(t.length<2)return[];
    return /^[\u3400-\u9fff]+$/.test(t)&&t.length>3&&!words.has(t)?Array.from({length:t.length-1},(_,i)=>t.slice(i,i+2)):[t];
  }))];
  const sources=(snapshot.sources||[]).filter((p:any)=>!p.archived&&p.searchable!==false);
  let rows=rowCache.get(snapshot);
  if(!rows){rows=new Map(sources.map((p:any)=>[p.id,[searchText(p.text),searchText(p.section)]]));rowCache.set(snapshot,rows);}
  const counts=new Map(terms.map(term=>[term,[...rows!.values()].reduce((n,[text,heading])=>n+Number((text+heading).includes(term)),0)]));
  if([...counts.values()].some(Boolean)) {
    const boundaryText=intent.replace(filler," ").replace(joiner," ");
    const unknown=new Set<string>();
    for(const token of boundaryText.replace(wordPattern,m=>" "+m+" ").match(/[\u3400-\u9fff]+/g)||[]) {
      if(token.length>3&&!words.has(token)) {
        const pieces=Array.from({length:token.length-1},(_,i)=>token.slice(i,i+2));
        if(!pieces.some(piece=>counts.get(piece)))for(const piece of pieces)unknown.add(piece);
      }
    }
    terms=terms.filter(term=>counts.get(term)||unknown.has(term)||/[a-z0-9]/.test(term)||new RegExp("(?<![\\u3400-\\u9fff])"+term+"(?![\\u3400-\\u9fff])").test(boundaryText));
  }
  const weights=new Map(terms.map(term=>[term,(Math.log(1+rows!.size/(1+counts.get(term)!))+1)*(soft.has(term)?.3:1)]));
  const strong=terms.filter(term=>!soft.has(term));
  const maximum=Math.max(0,...strong.map(term=>weights.get(term)!));
  const anchors=strong.filter(term=>weights.get(term)!>=maximum*.85);
  const missingIds=terms.some(term=>!soft.has(term)&&/[a-z]/.test(term)&&!counts.get(term));
  const weight=[...weights.values()].reduce((a,b)=>a+b,0);
  const ranked=sources.map((p:any)=>{
    if(missingIds||!query||(!requested.length&&!terms.length))return null;
    const [text,heading]=rows!.get(p.id)!,combined=heading+text;
    if(requested.length) {
      const declared=p.scope_projects||[];
      if(declared.length===1) {
        if(!requested.some(k=>declared.includes(k)))return null;
      } else {
        if((p.topic_names||[]).length>1&&!requested.some(k=>(p.heading_projects||[]).includes(k)))return null;
        if(!requested.some(k=>aliases[k].some(parts=>parts.every(t=>combined.includes(normal(canonical(t)))))))return null;
      }
    }
    const matches=terms.filter(t=>combined.includes(t));
    if(anchors.length&&!anchors.some(term=>combined.includes(term)))return null;
    const coverage=weight?matches.reduce((sum,t)=>sum+weights.get(t)!,0)/weight:1;
    if(terms.length&&(anchors.length||!requested.length)&&(!matches.length||coverage<.42))return null;
    let score=coverage*85+(focus&&text.includes(focus)?30:0)+(focus&&heading.includes(focus)?15:0);
    const bodyWeight=matches.filter(t=>text.includes(t)).reduce((sum,t)=>sum+weights.get(t)!,0);
    score+=bodyWeight*6/(1+Math.max(0,text.length-500)/1500);
    score+=Number(p.scorehint||0);
    if(terms.includes("发布")) {
      const body=canonical(p.text),release="发布(?!门禁|验收|检查|步骤|计划|准备|包体|预算)";
      if(!/(?:未|不|未重新)发布/.test(body)&&new RegExp(release+".{0,30}(?:已|完成|成功)|(?:已|完成|成功).{0,20}"+release).test(body))score+=25;
    }
    if(requested.length)score+=20+(requested.some(k=>(p.heading_projects||[]).includes(k))?20:0);
    if(p.thread_links?.length)score+=normal(plain(p.text)).length<18?-106:4;
    if(String(p.text).trimStart().startsWith("|"))score-=15;
    if(/首个需求|最近需求|新增问题/.test(p.text))score-=25;
    if(sourcePlaceholder.test(p.text))score-=90;
    if((p.topic_names||[]).length>1)score-=75;
    return {...p,score:roundScore(Math.max(score,.1))};
  }).filter(Boolean).sort((a:any,b:any)=>b.score-a.score||String(b.source_date||b.modified_at).localeCompare(String(a.source_date||a.modified_at)));
  const unique:any[]=[],seen=new Map<string,any>();
  for(const p of ranked) {
    const key=normal(p.text);
    if(seen.has(key)) {
      const item=seen.get(key);item.other_sources||=[];item.other_sources.push({id:p.id,note_id:p.note_id});
    }else{seen.set(key,p);unique.push(p);}
  }
  let ordered=unique;
  if(anchors.length>1&&unique.length) {
    const remaining=unique.slice(),diversified:any[]=[],covered=new Set<string>();
    while(remaining.length&&diversified.length<6) {
      const priority=(item:any)=>{
        const [text,heading]=rows!.get(item.id)!;
        const novel=terms.filter(t=>!covered.has(t)&&(text+heading).includes(t)).reduce((sum,t)=>sum+weights.get(t)!,0);
        return item.score+(diversified.length?novel*16:0);
      };
      let best=0;
      for(let i=1;i<remaining.length;i++)if(priority(remaining[i])>priority(remaining[best]))best=i;
      const item=remaining.splice(best,1)[0];diversified.push(item);
      const [text,heading]=rows!.get(item.id)!;
      for(const term of terms)if((text+heading).includes(term))covered.add(term);
    }
    ordered=[...diversified,...remaining];
  }
  ordered=supplementResultTable(snapshot,ordered,requested);
  const items=limit<=0?ordered:ordered.slice(0,limit);
  return {query,items,total:ordered.length,returned:items.length,has_more:items.length<ordered.length,status:ordered.length?"found":"empty",answer_status:"evidence_only"};
}
