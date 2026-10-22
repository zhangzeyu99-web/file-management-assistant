import test from "node:test";
import assert from "node:assert/strict";
import {updateResultView} from "../lib/update-result.ts";

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
