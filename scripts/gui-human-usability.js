async page => {
  const report = {
    ok: true,
    started_at: new Date().toISOString(),
    page_url: page.url(),
    title: "",
    read_only: /[?&#;]readOnly=1(?:[&;#]|$)/.test(page.url()),
    timeline: [],
    actions: [],
    ux_issues: [],
    mechanics_failures: [],
    console_events: [],
    network_events: [],
    skipped: [],
  };

  const requiredResultLabels = ["result-section", "result-actions"];

  function step(label, data = {}) {
    report.timeline.push({ at: new Date().toISOString(), label, ...data });
  }

  function issue(id, message, data = {}) {
    report.ux_issues.push({ id, message, ...data });
  }

  function failure(message, data = {}) {
    report.ok = false;
    report.mechanics_failures.push({ message, ...data });
  }

  function param(name) {
    const match = page.url().match(new RegExp(`[?&;]${name}=([^&#;]*)`));
    return match ? decodeURIComponent(match[1].replace(/\+/g, " ")) : "";
  }

  async function delay(ms = 120) {
    await page.waitForTimeout(ms);
  }

  async function visible(selector) {
    try {
      return await page.locator(selector).first().isVisible({ timeout: 1500 });
    } catch {
      return false;
    }
  }

  async function text(selector, timeout = 1500) {
    try {
      return await page.locator(selector).first().innerText({ timeout });
    } catch {
      return "";
    }
  }

  async function humanClick(selector, label) {
    const locator = page.locator(selector).first();
    step(`hover:${label}`);
    await locator.scrollIntoViewIfNeeded({ timeout: 10000 });
    await delay(80);
    const box = await locator.boundingBox();
    if (box) {
      await page.mouse.move(box.x + box.width * 0.52, box.y + box.height * 0.58, { steps: 10 });
      await delay(60);
    }
    step(`click:${label}`);
    await locator.click({ timeout: 10000 });
    await delay(120);
  }

  async function humanFill(selector, value, label) {
    const locator = page.locator(selector).first();
    step(`fill:${label}`, { value: value.slice(0, 100) });
    await locator.scrollIntoViewIfNeeded({ timeout: 10000 });
    await locator.click({ timeout: 10000 });
    await locator.fill(value);
    await delay(100);
  }

  async function runAction(action, buttonSelector, resultSelector, label) {
    const item = {
      action,
      label,
      ok: false,
      request_action: null,
      status: null,
      response_ok: null,
      result_text: "",
      error: null,
    };
    report.actions.push(item);
    try {
      const responsePromise = page.waitForResponse(
        response => response.url().includes("/api/action") && response.request().method() === "POST",
        { timeout: 12000 },
      );
      await humanClick(buttonSelector, label);
      const response = await responsePromise;
      const payload = response.request().postDataJSON();
      const data = await response.json();
      item.request_action = payload.action || null;
      item.status = response.status();
      item.response_ok = Boolean(data && data.ok);
      item.result_text = await text(resultSelector, 4000);
      item.ok = item.status >= 200 && item.status < 400 && item.response_ok && item.request_action === action;
      if (!item.ok) {
        failure("action did not complete", { action, label, status: item.status, request_action: item.request_action, response_ok: item.response_ok });
      }
      if (item.result_text.includes("[object Object]") || /^\s*\{[\s\S]*\}\s*$/.test(item.result_text)) {
        issue("debug-output-as-result", "result area looks like raw debug output", { action, label });
      }
      const isToolsResult = resultSelector === ".result";
      if (isToolsResult) {
        if ((await page.locator(`${resultSelector} .result-grid`).count()) < 1) {
          issue("result-card-missing-section", "tools result card missing .result-grid", { action, label });
        }
      } else {
        for (const className of requiredResultLabels) {
          if ((await page.locator(`${resultSelector} .${className}`).count()) < 1) {
            issue("result-card-missing-section", `result card missing .${className}`, { action, label });
          }
        }
      }
    } catch (error) {
      item.error = String(error && error.message ? error.message : error);
      failure("action click failed", { action, label, error: item.error });
    }
  }

  page.on("console", msg => {
    if (["error", "warning"].includes(msg.type())) {
      report.console_events.push({ type: msg.type(), text: msg.text() });
    }
  });
  page.on("pageerror", error => {
    failure("page runtime error", { error: String(error && error.message ? error.message : error) });
  });
  page.on("response", response => {
    const status = response.status();
    const url = response.url();
    if (status >= 400 || url.includes("/api/")) {
      report.network_events.push({ status, method: response.request().method(), url });
    }
  });

  try {
    const localPath = param("humanLocalPath") || "D:\\codex\\file-management-assistant";
    const fixtureFile = param("humanFile");

    await page.waitForLoadState("domcontentloaded");
    await page.waitForLoadState("networkidle").catch(() => null);
    await delay(250);
    report.title = await page.title();

    step("read hero");
    if (!(await visible(".site-hero"))) issue("hero-not-visible", "hero is not visible on first load");
    if ((await page.locator(".feature-anchor").count()) !== 3) issue("wrong-feature-count", "home should expose exactly three main feature anchors");
    if (await visible("#out")) issue("json-visible-on-load", "advanced JSON is visible by default");

    step("jump to knowledge feed");
    await humanClick('a[href="#knowledge"]', "hero knowledge CTA");
    const cardCount = await page.locator("[data-knowledge-card]").count();
    if (cardCount < 1) {
      issue("knowledge-feed-empty", "knowledge feed rendered no cards");
    } else {
      await humanClick("[data-knowledge-card]", "first knowledge card");
      const detailText = await text("#knowledgeDetail", 2500);
      if (!detailText || detailText.length < 80) issue("knowledge-detail-too-thin", "knowledge card detail is too thin");
      if (!(await visible("#knowledgeDetail .result-button"))) issue("knowledge-detail-no-action", "knowledge detail has no obvious action button");
    }

    step("organize section with local target");
    await humanClick('.feature-anchor[href="#organize"]', "feature organize");
    await humanFill("#organize textarea[data-action-input]", "Human usability test input: add Obsidian notes and AI context material.", "organize text");
    await humanFill("#localPaths", localPath, "local path");
    if (fixtureFile) {
      step("fixture file available", { fixtureFile });
    }
    await runAction("inspect-local-targets", "#organize .path-actions .site-button:nth-of-type(3)", "#organizeResult", "inspect local target");
    if (report.read_only) {
      report.skipped.push({ action: "organize", reason: "read-only mode" });
    } else {
      await runAction("organize", "#organize .action-buttons .site-button.primary", "#organizeResult", "organize");
    }

    step("review section");
    await humanClick('.feature-anchor[href="#review"]', "feature review");
    await humanFill("#review textarea[data-action-input]", "How should an Obsidian beginner organize existing notes?", "review query");
    await runAction("review", "#review .action-buttons .site-button.primary", "#reviewResult", "review");

    step("review no-match behavior");
    await humanFill("#review textarea[data-action-input]", "__no_such_topic_20260508__", "review no-match query");
    await runAction("review", "#review .action-buttons .site-button.primary", "#reviewResult", "review no-match");
    const noMatchText = await text("#reviewResult", 2500);
    if (!noMatchText.includes("没有找到相关内容") || noMatchText.includes("打开匹配来源")) {
      issue("review-no-match-fallback", "review should not pretend unrelated notes are matches", { result_text: noMatchText.slice(0, 500) });
    }

    step("extract section");
    await humanClick('.feature-anchor[href="#extract"]', "feature extract");
    await humanFill("#extract textarea[data-action-input]", "Package existing Obsidian knowledge into AI context for the next conversation.", "extract request");
    if (report.read_only) {
      report.skipped.push({ action: "extract", reason: "read-only mode" });
    } else {
      await runAction("extract", "#extract .action-buttons .site-button.primary", "#extractResult", "extract preview");
      const previewText = await text("#extractResult", 2500);
      if (!previewText.includes("找到候选") || !previewText.includes("确认生成上下文包")) {
        issue("extract-preview-missing", "extract should preview candidate sources before writing a package", { result_text: previewText.slice(0, 500) });
      }
      await runAction("extract", "#extractResult .result-button.primary", "#extractResult", "extract generate");
      if (await visible("#extractResult .result-button.primary")) {
        await humanClick("#extractResult .result-button.primary", "copy prompt");
        const afterCopy = await text("#extractResult", 1500);
        if (!afterCopy.toLowerCase().includes("prompt")) issue("copy-prompt-no-feedback", "copy prompt has no visible feedback");
      } else {
        issue("extract-no-copy-prompt", "extract result has no primary copy prompt action");
      }
    }

    step("tools page discoverability");
    await humanClick('a[href="/advanced"]', "open tools page");
    await page.waitForLoadState("domcontentloaded");
    await delay(300);
    if (!page.url().includes("/advanced")) issue("tools-page-not-opened", "tools page link did not navigate to /advanced");
    if ((await page.locator("[data-tool-card]").count()) !== 6) issue("tool-card-count", "tools page should expose exactly six verified tool cards");
    for (const textNeedle of ["诊断与维护", "打开资料", "运行文件雷达", "运行知识库体检", "生成旧资料索引"]) {
      if (!(await page.locator(`text=${textNeedle}`).count())) issue("tools-page-copy-missing", `missing tools page copy: ${textNeedle}`);
    }
    if (!report.read_only) {
      await runAction("obsidian-health", '[data-tool-card="obsidian-health"] button', ".result", "tools obsidian health");
    } else {
      report.skipped.push({ action: "obsidian-health", reason: "read-only mode" });
    }

    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    await delay(150);
  } catch (error) {
    failure("uncaught human flow error", { error: String(error && error.message ? error.message : error) });
  }

  report.finished_at = new Date().toISOString();
  report.ok = report.ok && report.mechanics_failures.length === 0;
  return report;
}
