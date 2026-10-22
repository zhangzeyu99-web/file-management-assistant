import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";
import catalog from "../lib/error-catalog.json" with {type: "json"};
import {userIssue, readJsonResponse, RequestFailure} from "../lib/user-errors.ts";

const helpSource = fs.readFileSync(new URL("../components/HelpPanel.tsx", import.meta.url), "utf8");
const presenterSource = fs.readFileSync(new URL("../lib/user-errors.ts", import.meta.url), "utf8");
const syntax = ts.createSourceFile("user-errors.ts", presenterSource, ts.ScriptTarget.Latest, true);
const localDeclaration = syntax.statements.flatMap(statement => ts.isVariableStatement(statement) ? [...statement.declarationList.declarations] : [])
  .find(declaration => declaration.name.getText(syntax) === "local");
const localCodes = localDeclaration.initializer.properties.map(property => property.name.getText(syntax).replace(/^["']|["']$/g, ""));
const secret = "example-secret-token-DO-NOT-RENDER";
const privatePath = "C:\\PrivateAccount\\raw-user-content.txt";
const upstream = `<script>throw new Error('${secret}')</script> ${privatePath}`;
function assertSafe(issue) {
  const publicText = JSON.stringify(issue);
  for (const forbidden of [secret, privatePath, "<script>", "raw-user-content", "traceback-private"]) assert.ok(!publicText.includes(forbidden), `raw upstream data leaked: ${forbidden}`);
  const diagnostic = JSON.parse(issue.diagnostic);
  assert.ok(Object.keys(diagnostic).every(key => ["code", "http_status", "operation", "at"].includes(key)));
  assert.equal(diagnostic.code, issue.code);
  assert.ok(Number.isFinite(Date.parse(diagnostic.at)));
}

test("every catalog and local error has a readable problem, a concrete action and a valid help target", () => {
  for (const code of new Set([...Object.keys(catalog), ...localCodes])) {
    const issue = userIssue({code, message: upstream, action: upstream, diagnostic: upstream}, {context: "故障测试"});
    assert.equal(issue.code, code);
    assert.equal(typeof issue.message, "string"); assert.ok(issue.message.trim(), code);
    assert.equal(typeof issue.action, "string"); assert.ok(issue.action.trim(), code);
    assert.equal(typeof issue.retryable, "boolean");
    assert.equal(typeof issue.help, "string");
    if (issue.help) assert.ok(helpSource.includes(`id="help-${issue.help}"`), `missing help for ${code}`);
    if (catalog[code]) {
      assert.equal(issue.message, catalog[code].message); assert.equal(issue.action, catalog[code].action);
      assert.equal(issue.retryable, catalog[code].retryable); assert.equal(issue.help, catalog[code].help);
    }
    assertSafe(issue);
  }
});

test("unknown exceptions, nested data and forged guidance never escape into public copy or diagnostics", () => {
  for (const error of [new Error(upstream), {code: "unknown-code", message: upstream, action: upstream, stack: "traceback-private"},
    {error: upstream, request: {token: secret, path: privatePath}}, {error_detail: {code: "unknown-code", message: upstream, diagnostic: upstream}}]) {
    const issue = userIssue(error, {context: "读取资料"});
    assert.equal(issue.code, "internal_error"); assertSafe(issue);
    assert.equal(issue.message, catalog.internal_error.message);
  }
});

test("typed backend errors control recovery while backend text and private details remain hidden", async () => {
  const response = Response.json({error: upstream, error_detail: {code: "migration_target_occupied", message: upstream, action: upstream}}, {status: 400});
  let failure;
  try {await readJsonResponse(response);} catch (error) {failure = error;}
  assert.ok(failure instanceof RequestFailure); assert.equal(failure.status, 400);
  const issue = userIssue(failure, {context: "迁移预检"});
  assert.equal(issue.code, "migration_target_occupied");
  assert.equal(issue.action, catalog.migration_target_occupied.action); assertSafe(issue);
});

test("HTTP failures distinguish login, permission, expiry, size, throttling and server errors", async () => {
  for (const [status, expected] of [[401, "site_login"], [403, "request_forbidden"], [410, "migration_download_missing"],
    [413, "file_too_large"], [429, "cloud_rate_limited"], [502, "service_unavailable"]]) {
    let failure;
    try {await readJsonResponse(Response.json({error: upstream}, {status}));} catch (error) {failure = error;}
    const issue = userIssue(failure, {context: "网站请求"});
    assert.equal(issue.code, expected, String(status));
    assert.equal(JSON.parse(issue.diagnostic).http_status, status); assertSafe(issue);
  }
});

test("HTML and invalid JSON responses retain only HTTP classification without displaying server content", async () => {
  for (const [status, expected] of [[200, "cloud_response_invalid"], [401, "site_login"], [502, "service_unavailable"]]) {
    let failure;
    try {await readJsonResponse(new Response(upstream, {status, headers: {"content-type": "text/html"}}));} catch (error) {failure = error;}
    assert.ok(failure instanceof RequestFailure);
    const issue = userIssue(failure, {context: "加载页面"});
    assert.equal(issue.code, expected); assertSafe(issue);
  }
});

test("an issued UserIssue is idempotent, including its first diagnostic time and context", () => {
  const first = userIssue({code: "native_oversized"}, {context: "读取原对话"});
  const copied = userIssue(first, {context: "另一个展示位置", status: 401});
  assert.strictEqual(copied, first);
  assert.equal(copied.diagnostic, first.diagnostic);
  assert.equal(JSON.parse(copied.diagnostic).operation, "读取原对话");
  assert.equal(copied.retryable, false);
});

test("semantic failure guidance stays separate from waiting or incomplete source coverage", () => {
  const long = userIssue({code: "native_oversized"});
  assert.equal(long.retryable, false); assert.match(long.action, /添加资料/);
  const encoding = userIssue({code: "invalid_encoding"});
  assert.equal(encoding.retryable, false); assert.match(encoding.action, /UTF-8/);
  const waiting = userIssue({code: "local_offline"});
  assert.equal(waiting.retryable, false); assert.match(waiting.action, /无需再提交/);
  const server = userIssue({status: 503});
  assert.equal(server.retryable, true); assert.doesNotMatch(server.message, /网络|断网/);
});
