async page => {
  const startedAt = new Date().toISOString();
  const report = {
    ok: true,
    started_at: startedAt,
    page_url: page.url(),
    title: "",
    include_openers: false,
    read_only: false,
    e2e_local_path: "",
    mechanics_failures: [],
    ux_issues: [],
    skipped: [],
    actions: [],
    knowledge_detail: {
      card_count: 0,
      detail_visible: false,
      has_summary: false,
      has_related: false,
      has_prompts: false,
      has_source: false,
    },
  };

  const includeOpeners = /[?&#;]includeOpeners=1(?:[&;#]|$)/.test(page.url());
  const readOnly = /[?&#;]readOnly=1(?:[&;#]|$)/.test(page.url());
  function queryParam(name) {
    const match = page.url().match(new RegExp(`[?&;]${name}=([^&#;]*)`));
    return match ? decodeURIComponent(match[1].replace(/\+/g, " ")) : "";
  }
  function appPath(path) {
    const match = page.url().match(/^(https?:\/\/[^/]+)/);
    return match ? `${match[1]}${path}` : path;
  }
  const e2eLocalPath = queryParam("e2eLocalPath");
  report.include_openers = includeOpeners;
  report.read_only = readOnly;
  report.e2e_local_path = e2eLocalPath;

  function addFailure(message, data = {}) {
    report.ok = false;
    report.mechanics_failures.push({ message, ...data });
  }

  function addIssue(id, message, data = {}) {
    report.ux_issues.push({ id, message, ...data });
  }

  async function visibleText(selector) {
    try {
      return await page.locator(selector).innerText({ timeout: 1500 });
    } catch {
      return "";
    }
  }

  async function isOutputVisible() {
    try {
      return await page.locator("#out").evaluate(el => {
        const style = window.getComputedStyle(el);
        return style.display !== "none" && style.visibility !== "hidden";
      });
    } catch {
      return false;
    }
  }

  function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function collectStrings(node, values = []) {
    if (node === null || node === undefined) return values;
    if (typeof node === "string") {
      values.push(node);
      return values;
    }
    if (Array.isArray(node)) {
      node.forEach(item => collectStrings(item, values));
      return values;
    }
    if (typeof node === "object") {
      Object.values(node).forEach(item => collectStrings(item, values));
    }
    return values;
  }

  function buttonLocator(label, scope = "body") {
    return page
      .locator(scope)
      .getByRole("button", { name: new RegExp(`^\\s*${escapeRegExp(label)}\\s*$`) })
      .first();
  }

  async function clickAndCapture({ label, expectedAction, input = "", scope = "body", renderScope = scope, resultSelector = "", fillInput = true }) {
    const item = {
      label,
      expected_action: expectedAction,
      input,
      ok: false,
      request_action: null,
      http_status: null,
      response_ok: null,
      response: null,
      output_visible: false,
      output_looks_like_json: false,
      result_text: "",
      opened_popup: false,
      error: null,
    };
    report.actions.push(item);

    try {
      const actionInput = page.locator(`${scope} textarea[data-action-input]`).first();
      if (fillInput && await actionInput.count()) {
        await actionInput.fill(input);
      }
      const responsePromise = page.waitForResponse(
        response => response.url().includes("/api/action") && response.request().method() === "POST",
        { timeout: 25000 },
      );

      const button = buttonLocator(label, scope);
      await button.scrollIntoViewIfNeeded();
      await button.click();

      const response = await responsePromise;
      item.http_status = response.status();
      const requestData = response.request().postDataJSON();
      item.request_action = requestData.action || null;
      item.response = await response.json();
      item.response_ok = Boolean(item.response && item.response.ok);
      await page.waitForTimeout(250);
      item.output_visible = await isOutputVisible();
      const outputText = await visibleText("#out");
      item.output_looks_like_json = /^\s*\{[\s\S]*\}\s*$/.test(outputText);
      item.result_text = resultSelector
        ? await visibleText(resultSelector)
        : await visibleText(`${renderScope} .site-action-result`);
      item.ok = item.http_status >= 200 && item.http_status < 400 && item.response_ok && item.request_action === expectedAction;

      if (!item.ok) {
        addFailure("button action did not complete as expected", {
          label,
          expected_action: expectedAction,
          request_action: item.request_action,
          http_status: item.http_status,
          response_ok: item.response_ok,
        });
      }

      if (item.output_visible && item.output_looks_like_json) {
        addIssue("raw-json-default-output", "action result defaults to a JSON/code box", {
          label,
          action: expectedAction,
        });
      }
      if (item.result_text.includes("[object Object]")) {
        addIssue("object-object-result", "result card rendered an object as [object Object]", {
          label,
          action: expectedAction,
        });
      }
      if (!/完成情况|参考来源|保存位置|下一步建议|本地目标|来源可追溯|已完成/.test(item.result_text)) {
        addIssue("unclear-result-card", "result card does not clearly explain outcome, sources, artifacts, or next steps", {
          label,
          action: expectedAction,
        });
      }
    } catch (error) {
      item.error = String(error && error.message ? error.message : error);
      addFailure("button click failed", { label, expected_action: expectedAction, error: item.error });
    }
  }

  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(800);
  report.title = await page.title();

  const bodyText = await page.locator("body").innerText();
  const mustHave = [
    "本地知识整理助手",
    "知识流",
    "添加资料",
    "搜索回顾",
    "生成 AI 上下文包",
    "本地文件 / 目录目标",
    "拖放文件到这里",
    "检查本地目标",
    "工具维护页",
  ];
  for (const phrase of mustHave) {
    if (!bodyText.includes(phrase)) {
      addIssue("missing-core-copy", `missing required UI copy: ${phrase}`);
    }
  }
  for (const obsolete of ["Codex 文件管理小助手", "可视化上下文入口", "Codex 接手包", "今日操作台", "执行结果", "伪控制台", "本地状态摘要", "站点式知识库", "首屏极简", "默认只读", "不删除、不移动、不重命名、不重写源文件", "四个轻量操作区", "首页不再堆功能", "每次点击后"]) {
    if (bodyText.includes(obsolete)) {
      addIssue("obsolete-positioning-copy", `obsolete UI copy still appears: ${obsolete}`);
    }
  }

  if (await isOutputVisible()) {
    addIssue("json-visible-on-load", "advanced JSON is visible on page load");
  }

  for (const target of ["organize", "review", "extract"]) {
    const anchor = page.locator(`.feature-anchor[href="#${target}"]`).first();
    if ((await anchor.count()) === 0) {
      addFailure("feature anchor missing", { target });
      continue;
    }
    await anchor.click();
    await page.waitForTimeout(180);
    const hash = await page.evaluate(() => window.location.hash);
    if (hash !== `#${target}`) {
      addIssue("feature-anchor-did-not-jump", "feature card did not update the location hash", { target, hash });
    }
  }

  const cardCount = await page.locator("[data-knowledge-card]").count();
  report.knowledge_detail.card_count = cardCount;
  if (cardCount < 1) {
    addIssue("missing-knowledge-feed", "knowledge feed did not render any source-backed card");
  } else {
    await page.locator("[data-knowledge-card]").first().click();
    await page.waitForTimeout(300);
    const detailText = await visibleText("#knowledgeDetail");
    report.knowledge_detail.detail_visible = detailText.length > 0;
    report.knowledge_detail.has_summary = detailText.includes("一句话结论");
    report.knowledge_detail.has_related = detailText.includes("关联内容");
    report.knowledge_detail.has_prompts = detailText.includes("可追问问题");
    report.knowledge_detail.has_source = detailText.includes("来源");
    if (!report.knowledge_detail.detail_visible || !report.knowledge_detail.has_summary || !report.knowledge_detail.has_related || !report.knowledge_detail.has_prompts || !report.knowledge_detail.has_source) {
      addIssue("knowledge-card-detail-missing", "knowledge card click did not expose readable detail, source, related items, and thinking prompts", report.knowledge_detail);
    }
  }

  const fileInputCount = await page.locator("input[type=file]").count();
  const localPathInputCount = await page.locator("#localPaths").count();
  const dropZoneCount = await page.locator("#fileDropZone").count();
  if (fileInputCount === 0 || localPathInputCount === 0 || dropZoneCount === 0) {
    addIssue("missing-file-target-section", "organize section has no complete local target input with path input, file picker, and drop zone");
  }
  if (e2eLocalPath && localPathInputCount > 0) {
    await page.locator("#localPaths").fill(e2eLocalPath);
  }

  await clickAndCapture({
    label: "检查本地目标",
    expectedAction: "inspect-local-targets",
    input: "",
    scope: "#organize",
    renderScope: "#organize",
  });

  if (readOnly) {
    await clickAndCapture({
      label: "搜索回顾",
      expectedAction: "review",
      input: "Obsidian 教程和 AI 上下文包怎么用？",
      scope: "#review",
      renderScope: "#review",
    });
    report.skipped.push({ label: "添加资料", action: "organize", reason: "read-only smoke mode" });
    report.skipped.push({ label: "生成 AI 上下文包", action: "extract", reason: "read-only smoke mode" });
    report.skipped.push({ label: "工具页诊断动作", action: "diagnostics", reason: "read-only smoke mode" });
  } else {
    await clickAndCapture({
      label: "添加资料",
      expectedAction: "organize",
      input: "NotebookLM 和 Obsidian 教程资料，后续要整理为学习资料并给 AI 复用。",
      scope: "#organize",
      renderScope: "#organize",
    });
    await clickAndCapture({
      label: "搜索回顾",
      expectedAction: "review",
      input: "Obsidian 教程",
      scope: "#review",
      renderScope: "#review",
    });
    await clickAndCapture({
      label: "预览候选来源",
      expectedAction: "extract",
      input: "继续优化本地知识整理助手，需要已有 Obsidian 教程和 GUI 测试上下文。",
      scope: "#extract",
      renderScope: "#extract",
    });
    await clickAndCapture({
      label: "确认生成上下文包",
      expectedAction: "extract",
      scope: "#extract",
      renderScope: "#extract",
      fillInput: false,
    });
    await page.goto(appPath("/advanced"));
    await page.waitForLoadState("domcontentloaded");
    await clickAndCapture({
      label: "运行文件雷达",
      expectedAction: "file-radar",
      input: "",
      scope: '[data-tool-card="file-radar"]',
      resultSelector: ".result",
    });
    await clickAndCapture({
      label: "运行知识库体检",
      expectedAction: "obsidian-health",
      input: "",
      scope: '[data-tool-card="obsidian-health"]',
      resultSelector: ".result",
    });
    await clickAndCapture({
      label: "生成旧资料索引",
      expectedAction: "legacy-index",
      input: "",
      scope: '[data-tool-card="legacy-index"]',
      resultSelector: ".result",
    });
  }

  if (includeOpeners) {
    await page.goto(appPath("/advanced"));
    await page.waitForLoadState("domcontentloaded");
    await clickAndCapture({
      label: "打开 Obsidian",
      expectedAction: "open-obsidian",
      input: "",
      scope: '[data-tool-card="open-obsidian"]',
      resultSelector: ".result",
    });
  } else {
    report.skipped.push({ label: "打开 Obsidian", action: "open-obsidian", reason: "external opener; use -IncludeOpeners" });
  }

  const localTargetInspect = report.actions.find(item => item.expected_action === "inspect-local-targets");
  if (e2eLocalPath && localTargetInspect && localTargetInspect.response_ok) {
    if (localTargetInspect.response.mode !== "custom-local-paths" || !localTargetInspect.response.summary || localTargetInspect.response.summary.existing_count < 1) {
      addIssue("local-target-not-recognized", "local target inspection did not recognize the E2E path", {
        action: "inspect-local-targets",
        e2eLocalPath,
      });
    }
  }

  const fileRadar = report.actions.find(item => item.expected_action === "file-radar");
  if (fileRadar && fileRadar.response_ok) {
    const normalizedTarget = e2eLocalPath.toLowerCase();
    const scannedTarget = collectStrings(fileRadar.response)
      .some(value => normalizedTarget && value.toLowerCase().startsWith(normalizedTarget));
    if (e2eLocalPath && !scannedTarget) {
      addIssue("file-radar-did-not-use-local-targets", "file radar did not use pasted local paths as scan targets", {
        action: "file-radar",
      });
    }
    if (!/打开|报告|路径|继续|复制|产物|下一步/.test(fileRadar.result_text)) {
      addIssue("missing-next-action-buttons", "file radar result does not expose clear next action buttons", {
        action: "file-radar",
      });
    }
  }

  return report;
}
