async page => {
  const startedAt = new Date().toISOString();
  const logStep = (step) => console.log(`[gui-e2e] ${step}`);
  logStep("start");
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
    three_operations: {
      anchors_checked: 0,
      has_local_target_input: false,
      obsidian_findability: false,
      organize_recommended_search_terms: false,
      recommended_search_term_review: false,
      extract_findability: false,
      preview_before_generate: false,
      seeded_context_from_review: false,
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
      const output = page.locator("#out");
      if ((await output.count()) === 0) return false;
      return await output.evaluate(el => {
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

  function trimForReport(value, limit = 3000) {
    const text = String(value || "");
    return text.length > limit ? `${text.slice(0, limit)}…[e2e-truncated]` : text;
  }

  function sanitizeForReport(node, key = "") {
    if (node === null || node === undefined) return node;
    if (typeof node === "string") {
      if (key === "content") return trimForReport(node, 800);
      return trimForReport(node, 1800);
    }
    if (Array.isArray(node)) return node.map(item => sanitizeForReport(item));
    if (typeof node === "object") {
      const output = {};
      for (const [childKey, childValue] of Object.entries(node)) {
        output[childKey] = sanitizeForReport(childValue, childKey);
      }
      return output;
    }
    return node;
  }

  function buttonLocator(label, scope = "body") {
    return page
      .locator(scope)
      .getByRole("button", { name: new RegExp(`^\\s*${escapeRegExp(label)}\\s*$`) })
      .first();
  }

  async function clickAndCapture({ label, buttonLabel = label, expectedAction, input = "", scope = "body", renderScope = scope, resultSelector = "", fillInput = true }) {
    const item = {
      label,
      expected_action: expectedAction,
      input,
      duration_ms: null,
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
    const actionStartedAt = Date.now();

    try {
      const actionInput = page.locator(`${scope} textarea[data-action-input]`).first();
      if (fillInput && await actionInput.count()) {
        await actionInput.fill(input);
      }
      const button = buttonLocator(buttonLabel, scope);
      if ((await button.count()) === 0) {
        throw new Error(`button not found: ${buttonLabel}`);
      }
      await button.scrollIntoViewIfNeeded({ timeout: 3000 });
      const responsePromise = page.waitForResponse(
        response => response.url().includes("/api/action") && response.request().method() === "POST",
        { timeout: 12000 },
      );
      await button.evaluate(el => el.click());

      const response = await responsePromise;
      item.http_status = response.status();
      const requestData = response.request().postDataJSON();
      item.request_action = requestData.action || null;
      const responseJson = await response.json();
      item.response = sanitizeForReport(responseJson);
      item.response_ok = Boolean(responseJson && responseJson.ok);
      await page.waitForTimeout(250);
      item.output_visible = await isOutputVisible();
      const outputText = await visibleText("#out");
      item.output_looks_like_json = /^\s*\{[\s\S]*\}\s*$/.test(outputText);
      item.result_text = resultSelector
        ? trimForReport(await visibleText(resultSelector))
        : trimForReport(await visibleText(`${renderScope} .site-action-result`));
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
      if (!/一句话答案|命中证据|生成产物|下一步建议|本地目标|来源可追溯|已完成|未完成/.test(item.result_text)) {
        addIssue("unclear-result-card", "result card does not clearly explain outcome, sources, artifacts, or next steps", {
          label,
          action: expectedAction,
        });
      }
    } catch (error) {
      item.error = String(error && error.message ? error.message : error);
      addFailure("button click failed", { label, expected_action: expectedAction, error: item.error });
    } finally {
      item.duration_ms = Date.now() - actionStartedAt;
    }
  }

  logStep("wait-domcontentloaded");
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(800);
  report.title = await page.title();
  logStep("page-ready");

  logStep("body-copy-check");
  const bodyText = await page.locator("body").innerText();
  const mustHave = [
    "本地知识整理助手",
    "添加资料",
    "搜索回顾",
    "生成 AI 上下文包",
    "本地文件 / 目录目标",
    "拖放文件到这里",
    "检查本地目标",
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

  logStep("anchor-checks");
  for (const target of ["organize", "review", "extract"]) {
    const anchor = page.locator(`.feature-anchor[href="#${target}"]`).first();
    if ((await anchor.count()) === 0) {
      addFailure("feature anchor missing", { target });
      continue;
    }
    await anchor.evaluate(el => el.click());
    await page.waitForTimeout(180);
    const hash = await page.evaluate(() => window.location.hash);
    if (hash !== `#${target}`) {
      addIssue("feature-anchor-did-not-jump", "feature card did not update the location hash", { target, hash });
    }
  }

  report.three_operations.anchors_checked = 3;

  const fileInputCount = await page.locator("input[type=file]").count();
  const localPathInputCount = await page.locator("#localPaths").count();
  const dropZoneCount = await page.locator("#fileDropZone").count();
  report.three_operations.has_local_target_input = fileInputCount > 0 && localPathInputCount > 0 && dropZoneCount > 0;
  if (fileInputCount === 0 || localPathInputCount === 0 || dropZoneCount === 0) {
    addIssue("missing-file-target-section", "organize section has no complete local target input with path input, file picker, and drop zone");
  }
  if (e2eLocalPath && localPathInputCount > 0) {
    await page.locator("#localPaths").fill(e2eLocalPath);
  }

  logStep("inspect-local-targets");
  await clickAndCapture({
    label: "检查本地目标",
    expectedAction: "inspect-local-targets",
    input: "",
    scope: "#organize",
    renderScope: "#organize",
  });

  if (readOnly) {
    logStep("review-readonly");
    await clickAndCapture({
      label: "搜索回顾",
      expectedAction: "review",
      input: "Obsidian 教程",
      scope: "#review",
      renderScope: "#review",
    });
    report.skipped.push({ label: "添加资料", action: "organize", reason: "read-only smoke mode" });
    report.skipped.push({ label: "生成 AI 上下文包", action: "extract", reason: "read-only smoke mode" });
    report.skipped.push({ label: "工具页诊断动作", action: "diagnostics", reason: "read-only smoke mode" });
  } else {
    logStep("organize");
    await clickAndCapture({
      label: "添加资料",
      expectedAction: "organize",
      input: "NotebookLM 和 Obsidian 教程资料，后续要整理为学习资料并给 AI 复用。",
      scope: "#organize",
      renderScope: "#organize",
    });
    const organized = report.actions.find(item => item.label === "添加资料");
    if (organized && organized.response_ok) {
      const resultText = organized.result_text || "";
      const locations = organized.response?.debug?.obsidian_locations || {};
      const recommendedTerms = organized.response?.debug?.recommended_search_terms || [];
      const hasLocationCopy = resultText.includes("在 Obsidian 里怎么找") && resultText.includes("文件索引目录");
      const hasLocationData = Boolean(locations.organize_note && locations.organize_dir && locations.file_index_dir);
      const hasRecommendedTerms = resultText.includes("推荐搜索词") && Array.isArray(recommendedTerms) && recommendedTerms.length > 0;
      report.three_operations.obsidian_findability = hasLocationCopy && hasLocationData;
      report.three_operations.organize_recommended_search_terms = hasRecommendedTerms;
      if (!hasLocationCopy) {
        addIssue("organize-missing-obsidian-findability", "organize result does not tell the user where to find the new Obsidian notes", {
          result_text: resultText,
        });
      }
      if (!hasLocationData) {
        addIssue("organize-missing-obsidian-location-data", "organize response is missing structured Obsidian location data", {
          obsidian_locations: locations,
        });
      }
      if (!hasRecommendedTerms) {
        addIssue("organize-missing-recommended-search-terms", "organize result does not expose recommended_search_terms that can be reused in review", {
          result_text: resultText,
          recommended_search_terms: recommendedTerms,
        });
      }
      if (hasRecommendedTerms) {
        logStep("推荐词一键搜索回顾");
        const term = recommendedTerms.find(item => typeof item === "string" && item.trim());
        const termButton = term ? buttonLocator(term, "#organize") : page.locator("__missing__").first();
        if (!term || (await termButton.count()) === 0) {
          addIssue("runReviewForTerm-missing", "recommended term button is missing or not wired to runReviewForTerm", {
            recommended_search_terms: recommendedTerms,
          });
        } else {
          try {
            const responsePromise = page.waitForResponse(
              response => response.url().includes("/api/action") && response.request().method() === "POST",
              { timeout: 12000 },
            );
            await termButton.scrollIntoViewIfNeeded({ timeout: 3000 });
            await termButton.evaluate(el => el.click());
            const response = await responsePromise;
            const requestData = response.request().postDataJSON();
            const responseJson = await response.json();
            await page.waitForTimeout(250);
            const reviewInputValue = await page.locator("#reviewInput").inputValue();
            const reviewText = await visibleText("#reviewResult");
            const ok = response.status() >= 200
              && response.status() < 400
              && requestData.action === "review"
              && Boolean(responseJson?.ok)
              && reviewInputValue === term
              && reviewText.includes("结果 · 搜索回顾");
            report.three_operations.recommended_search_term_review = ok;
            if (!ok) {
              addIssue("recommended-term-review-failed", "recommended search term did not fill and execute review", {
                term,
                request_action: requestData.action || null,
                http_status: response.status(),
                response_ok: Boolean(responseJson?.ok),
                review_input_value: reviewInputValue,
                result_text: reviewText,
              });
            }
          } catch (error) {
            addIssue("recommended-term-review-failed", "recommended search term click failed", {
              term,
              error: String(error && error.message ? error.message : error),
            });
          }
        }
      }
    }
    logStep("review");
    await clickAndCapture({
      label: "搜索回顾",
      expectedAction: "review",
      input: "Obsidian 教程",
      scope: "#review",
      renderScope: "#review",
    });
    logStep("seed-context-from-review");
    const seedButton = buttonLocator("加入上下文包", "#review");
    if ((await seedButton.count()) === 0) {
      addIssue("review-missing-seed-context-button", "review result does not expose an add-to-context action for matched evidence");
    } else {
      await seedButton.scrollIntoViewIfNeeded({ timeout: 3000 });
      await seedButton.evaluate(el => el.click());
      await page.waitForTimeout(350);
      const seededText = await visibleText("#extractResult");
      report.three_operations.seeded_context_from_review = seededText.includes("已加入上下文包候选") && seededText.includes("确认生成上下文包");
      if (!report.three_operations.seeded_context_from_review) {
        addIssue("review-seed-context-missing", "clicking add-to-context did not make the selected source visible in the extract section", {
          result_text: seededText,
        });
      } else {
        logStep("extract-generate-selected");
        await clickAndCapture({
          label: "确认生成已选上下文包",
          buttonLabel: "确认生成上下文包",
          expectedAction: "extract",
          scope: "#extract",
          renderScope: "#extract",
          fillInput: false,
        });
      }
    }
    logStep("extract-preview");
    await clickAndCapture({
      label: "预览候选来源",
      expectedAction: "extract",
      input: "Obsidian 教程",
      scope: "#extract",
      renderScope: "#extract",
    });
    logStep("extract-generate");
    await clickAndCapture({
      label: "确认生成预览上下文包",
      buttonLabel: "确认生成上下文包",
      expectedAction: "extract",
      scope: "#extract",
      renderScope: "#extract",
      fillInput: false,
    });
    const preview = report.actions.find(item => item.label === "预览候选来源");
    if (preview && preview.response_ok) {
      const identity = preview.response?.debug?.identity || {};
      if ((identity.count || 0) < 1 || !String(preview.response.summary || "").includes("AI 身份文件已可用")) {
        addIssue("extract-preview-missing-identity", "extract preview did not surface the available AI identity files", {
          identity_count: identity.count || 0,
        });
      }
    }
    const generated = report.actions.find(item => item.label === "确认生成预览上下文包");
    report.three_operations.preview_before_generate = Boolean(preview && generated);
    if (generated && generated.response_ok) {
      const resultText = generated.result_text || "";
      const locations = generated.response?.debug?.extract_locations || {};
      const hasExtractLocationCopy = resultText.includes("上下文包在 Obsidian 里怎么找") && resultText.includes("上下文包目录");
      const hasExtractLocationData = Boolean(locations.extract_note && locations.extract_dir && locations.runtime_markdown);
      report.three_operations.extract_findability = hasExtractLocationCopy && hasExtractLocationData;
      if (!hasExtractLocationCopy) {
        addIssue("extract-missing-obsidian-findability", "generated context package does not tell the user where to find it in Obsidian", {
          result_text: resultText,
        });
      }
      if (!hasExtractLocationData) {
        addIssue("extract-missing-location-data", "extract response is missing structured context package location data", {
          extract_locations: locations,
        });
      }
      const joined = collectStrings(generated.response).join("\n");
      for (const phrase of ["AI 身份文件摘要", "本地知识整理助手产品负责人", "严格逐个功能 QA"]) {
        if (!joined.includes(phrase)) {
          addIssue("extract-generate-missing-identity", `generated context package is missing identity phrase: ${phrase}`);
        }
      }
    }
  }
  report.skipped.push({ label: "openers", action: "openers", reason: "non-core openers are not part of GUI E2E" });
  logStep("done");

  const localTargetInspect = report.actions.find(item => item.expected_action === "inspect-local-targets");
  if (e2eLocalPath && localTargetInspect && localTargetInspect.response_ok) {
    if (localTargetInspect.response.mode !== "custom-local-paths" || !localTargetInspect.response.summary || localTargetInspect.response.summary.existing_count < 1) {
      addIssue("local-target-not-recognized", "local target inspection did not recognize the E2E path", {
        action: "inspect-local-targets",
        e2eLocalPath,
      });
    }
  }

  return report;
}
