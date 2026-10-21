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
