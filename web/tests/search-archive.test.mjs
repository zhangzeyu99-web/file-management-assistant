import test from "node:test";
import assert from "node:assert/strict";
import {searchSnapshot} from "../lib/search.ts";

function source(id, extra = {}) {
  return {
    id, note_id: `note-${id}`, title: "热血合服", section: "热血合服",
    text: "热血合服名单按地区边界分组，已确认保留排除原因。",
    topic_names: ["热血合服"], heading_projects: ["热血合服"],
    thread_links: [], modified_at: "2026-10-01", scorehint: 15, ...extra,
  };
}

test("archive, entry navigation and saved answers do not affect active results or scores", () => {
  const active = source("current");
  const extra = [
    source("historical", {archived: true, text: "热血合服名单 XYZZ742 旧版已全部交付。"}),
    source("entry", {searchable: false, navigation: true, maintenance: true}),
    source("answer", {searchable: false, maintenance: true}),
  ];
  const baseline = {sources: [active], notes: []};
  const full = {sources: [active, ...extra], notes: []};
  for (const query of ["热血合服名单怎么分组？", "热血合服", "XYZZ742"]) {
    assert.deepEqual(searchSnapshot(full, query), searchSnapshot(baseline, query));
  }
  assert.equal(searchSnapshot(full, "XYZZ742").total, 0);
  assert.equal(full.sources.length, 4, "filtering must not delete historical snapshot evidence");
});

test("older snapshots without archive flags remain searchable", () => {
  const result = searchSnapshot({sources: [source("old-format")], notes: []}, "热血合服名单");
  assert.deepEqual(result.items.map(item => item.id), ["old-format"]);
});

test("link-only references do not occupy answer evidence in older snapshots", () => {
  const active = source("order", {title: "最终展示顺序", section: "TopData 日报 / 最终展示顺序",
    scope_projects: ["TopData"], text: "日报最终采用两张运营表、七列新服表，AI分析放最后。"});
  const reference = source("links", {title: "来源", section: "TopData 日报 / 来源", scope_projects: ["TopData"],
    text: "[[90 历史/TopData日报依据#最终顺序|最终结构决定]] · [计算口径](https://example.invalid/report)"});
  const factual = source("prose", {title: "参考来源", section: "TopData 日报 / 参考来源", scope_projects: ["TopData"],
    text: "日报最终数据来自10月20日取数，实际顺序沿用原版。"});
  const snapshot = {sources: [active, reference, factual], notes: []};
  const result = searchSnapshot(snapshot, "TopData日报最终采用什么顺序", 6);
  assert.ok(result.items.some(item => item.id === active.id));
  assert.equal(result.items.some(item => item.id === reference.id), false);
  assert.ok(result.items.some(item => item.id === factual.id));
  assert.equal(snapshot.sources.length, 3, "references remain available for reading");
});

test("topic project scope survives paragraph splitting while specific intent remains required", () => {
  const sources = [
    source("activity", {section: "活跃与付费口径 / 当前结论", topic_names: [], heading_projects: [],
      scope_projects: ["热血合服"], text: "活跃取近3天登录用户数，不除以3，保留原字段。"}),
    source("report", {section: "日报与月报口径 / 当前结论", topic_names: [], heading_projects: [],
      scope_projects: ["TopData"], text: "最终要求保留原结构和顺序，两张运营表先展示；AI分析放最后。"}),
    source("migration", {section: "备份与迁移", topic_names: [], heading_projects: [],
      scope_projects: ["Obsidian 知识库"], text: "换电脑时先导出迁移包，再在新电脑导入，保留笔记和增量记录。"}),
    source("other-project", {section: "其他主题", scope_projects: ["洛克计算器"],
      text: "热血合服三天活跃不除以3只是历史参考，本篇采用其他指标。"}),
    ...Array.from({length: 4}, (_, index) => source(`unrelated-${index}`, {
      section: "其他主题", topic_names: [], heading_projects: [], text: "日报最终顺序已确认，不能代替其他项目记录。",
    })),
  ];
  const snapshot = {sources, notes: []};
  for (const [query, expected] of [
    ["热血合服三天活跃为什么不能除以3", "activity"],
    ["热血合服的三天活跃人数为什么不能直接除以3？", "activity"],
    ["TopData日报排列顺序", "report"],
    ["TopData日报最终采用什么顺序？", "report"],
    ["Obsidian换电脑怎么迁移", "migration"],
    ["Obsidian怎么迁移到新电脑？", "migration"],
  ]) {
    const result = searchSnapshot(snapshot, query);
    assert.equal(result.items[0]?.id, expected, query);
    assert.equal(result.items.some(item => item.id === "other-project"), false, query);
  }
  assert.equal(searchSnapshot(snapshot, "TopData日报 ZXQ739 口径").total, 0);
});

function mergeSnapshot() {
  const notes = [], sources = [];
  function add(id, title, relative, project, rows, markdown) {
    notes.push({id, note_id: id, title, relative, markdown: markdown || `# ${title}\n\n${rows.map(row => row[1]).join("\n\n")}`,
      modified_at: "2026-10-21", source_date: "2026-08-21", archived: false, searchable: true});
    for (const [index, [heading, text]] of rows.entries()) sources.push(source(`${id}-p${index}`, {
      note_id: id, note_title: title, relative, title: heading, section: `${title} / ${heading}`, project,
      scope_projects: [project], project_origin: "explicit", topic_names: text.includes("热血合服") ? ["热血合服"] : [],
      heading_projects: title.includes("热血合服") ? ["热血合服"] : [], text,
    }));
  }
  add("guide-write", "知识笔记写作与去重", "20 方法/知识库/知识笔记写作与去重.md", "Obsidian 知识库", [
    ["写什么", "一句结论直接回答问题，例如“热血合服使用近三天登录人数，不除以三”；保留方法、口径和决定。"],
    ["提问示例", "例如问“热血合服的名单怎么分组”，再找来源继续做。"],
  ]);
  add("guide-use", "知识库使用入口", "20 方法/知识库/知识库使用入口.md", "Obsidian 知识库", [
    ["知识库使用入口", "**试一次：**搜索“热血合服的三天活跃人数为什么不能直接除以3？”，打开来源核对。"],
  ]);
  add("guide-ask", "知识库提问与接续", "20 方法/知识库/知识库提问与接续.md", "Obsidian 知识库", [
    ["这样问更容易找到", "- “热血合服的三天活跃人数为什么不能直接除以3？”"],
    ["找到以后继续做", "写本次目标，例如“沿用原统计口径，整理下一批合服名单”。"],
  ]);
  add("merge-plan", "热血合服排单规则", "10 项目/热血合服/热血合服排单规则.md", "热血合服", [
    ["排单步骤", "1. 排除已合服务器，按地区和允许区间分组，确定优先级。\n2. 对照当期规则检查候选服，保留合服方案与实际执行状态。"],
  ]);
  const calculation = `# 热血合服活跃与付费计算

热血合服三日活跃直接使用原始字段，单服与每组均值使用不同分母。

## 当前结论

活跃取近3天登录用户数，不除以3；付费取近3天有付费的玩家登录数。

## 关键做法

| 指标 | 计算方式 | 示例 |
|---|---|---|
| 单服平均活跃 | 三日活跃合计÷入单服数 | 120÷10＝12人 |
| 每组平均活跃 | 主从服活跃合计÷组数 | 120÷5＝24人 |
| 单服平均付费 | 付费登录人数合计÷入单服数 | 30÷10＝3人 |
| 每组平均付费 | 主从服付费登录人数合计÷组数 | 30÷5＝6人 |`;
  add("merge-metric", "热血合服活跃与付费计算", "10 项目/热血合服/热血合服活跃与付费计算.md", "热血合服", [
    ["热血合服活跃与付费计算", "热血合服三日活跃直接使用原始字段，单服与每组均值使用不同分母。"],
    ["当前结论", "活跃取近3天登录用户数，不除以3；付费取近3天有付费的玩家登录数。"],
    ...calculation.split("\n").filter(line => line.startsWith("|") && !line.startsWith("|---")).map(line => ["关键做法", line]),
  ], calculation);
  add("merge-eu", "欧美冒险合服批次", "10 项目/欧美冒险合服/欧美冒险合服批次.md", "欧美冒险合服", [
    ["欧美冒险合服批次", "第8批已形成共12服的名单，后台执行结果待核对。"],
    ["排下一批", "先取得合服候选表，再核对允许区间与历史安排，分别登记名单和执行结果。"],
  ]);
  return {notes, sources};
}

test("generic merge answers prefer business topics over cross-project tutorial examples", () => {
  const snapshot = mergeSnapshot(), result = searchSnapshot(snapshot, "合服", 6);
  assert.equal(result.items.some(item => item.project === "Obsidian 知识库"), false);
  assert.deepEqual(new Set(result.items.map(item => item.project)), new Set(["热血合服", "欧美冒险合服"]));
  assert.equal(new Set(result.items.map(item => item.note_id)).size, result.items.length);
  assert.ok(searchSnapshot(snapshot, "Obsidian怎么提问", 6).items.some(item => item.text.includes("热血合服")));
});

test("selected short topic evidence contains the whole formula table instead of its introductory sentence", () => {
  const snapshot = mergeSnapshot(), result = searchSnapshot(snapshot, "合服", 6);
  const selected = result.items.find(item => item.note_id === "merge-metric");
  for (const text of ["| 指标 | 计算方式 | 示例 |", "120÷10＝12人", "120÷5＝24人", "30÷10＝3人", "30÷5＝6人", "不除以3"]) {
    assert.ok(selected?.text.includes(text), text);
  }
  assert.equal(selected.id, "merge-metric");
  assert.equal(selected.kind, "note");
  const precise = searchSnapshot(snapshot, "热血合服活跃计算", 6).items;
  assert.ok(precise.length);
  assert.ok(precise.every(item => item.project === "热血合服"));
});

test("long and mixed documents retain their selected passage scope", () => {
  for (const markdown of ["# 热血合服长资料\n\n" + "旧背景。".repeat(3500), "# 第一主题\n\n另一内容。\n\n# 第二主题\n\n更多内容。\n"]) {
    const note = {id: "long-note", title: "热血合服资料", relative: "10 项目/热血合服/资料.md", markdown};
    const selected = source("focused", {note_id: note.id, note_title: note.title, project: "热血合服",
      scope_projects: ["热血合服"], text: "SCOPEPKG739：按候选名单核对区间。"});
    const result = searchSnapshot({notes: [note], sources: [selected]}, "热血合服 SCOPEPKG739", 6);
    assert.equal(result.items[0].id, selected.id);
    assert.equal(result.items[0].text, selected.text);
  }
});

test("business examples remain evidence for their actual rule", () => {
  const rule = source("rule", {note_title: "TopData 报表口径", title: "当前口径", section: "TopData 报表口径 / 当前口径",
    project: "TopData", project_origin: "explicit", scope_projects: ["TopData"], topic_names: ["TopData"], heading_projects: ["TopData"],
    relative: "10 项目/TopData/报表口径.md", text: "人数采用去重统计，例如同一用户跨服只算一次，保留统计范围和计算步骤。"});
  const result = searchSnapshot({notes: [], sources: [rule]}, "人数去重", 6);
  assert.ok(result.items.length);
  assert.ok(result.items[0].text.includes("同一用户跨服只算一次"));
});
