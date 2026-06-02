async page => {
  const MISSING_QUERY_PREFIX = "__no_such_topic_";
  const EXTRACT_MODE = "preview-only";
  const REPORT_FILENAMES = ["gui-real-query-qa-result.json", "gui-real-query-qa-summary.md"];
  const missingQuery = `${MISSING_QUERY_PREFIX}${Date.now()}__`;
  const cases = [
    {
      name: "opex_sop",
      query: "运营sop",
      expectMatch: true,
      mustMatchTerms: ["运营", "sop"],
      mustNotMatchTop: ["OpenClaw", "简历"],
    },
    {
      name: "github_repo",
      query: "github仓库",
      expectMatch: true,
      mustMatchAny: ["github", "仓库"],
    },
    {
      name: "resume_thread",
      query: "简历线程",
      expectMatch: true,
      mustMatchTerms: ["简历", "线程"],
    },
    {
      name: "obsidian_assistant",
      query: "Obsidian助手",
      expectMatch: true,
      mustMatchTerms: ["obsidian", "助手"],
      mustNotMatchTop: ["真人式 GUI QA", "迭代记录"],
    },
    {
      name: "missing_topic",
      query: missingQuery,
      expectMatch: false,
    },
  ];

  const report = {
    ok: true,
    mode: EXTRACT_MODE,
    report_filenames: REPORT_FILENAMES,
    started_at: new Date().toISOString(),
    page_url: page.url(),
    title: "",
    cases: [],
    mechanics_failures: [],
    ux_issues: [],
    console_events: [],
    network_events: [],
  };

  page.on("console", message => {
    if (["error", "warning"].includes(message.type())) {
      report.console_events.push({ type: message.type(), text: message.text() });
    }
  });
  page.on("response", response => {
    const url = response.url();
    if (url.includes("/api/action")) {
      report.network_events.push({ url, status: response.status(), method: response.request().method() });
    }
  });

  function failCase(result, message, data = {}) {
    result.passed = false;
    result.reasons.push({ message, ...data });
  }

  function sourceFingerprint(source) {
    return ["title", "path", "summary", "direct_evidence", "evidence_excerpt"]
      .map(key => String(source?.[key] || ""))
      .join("\n");
  }

  function lowerList(values) {
    return Array.isArray(values) ? values.map(value => String(value).toLowerCase()) : [];
  }

  function hasAny(text, values) {
    const lowered = String(text || "").toLowerCase();
    return values.some(value => lowered.includes(String(value).toLowerCase()));
  }

  async function fill(selector, value) {
    const locator = page.locator(selector).first();
    await locator.scrollIntoViewIfNeeded({ timeout: 10000 });
    await locator.fill(value, { timeout: 10000 });
  }

  async function clickAndCapture(buttonSelector, resultSelector) {
    const responsePromise = page.waitForResponse(
      response => response.url().includes("/api/action") && response.request().method() === "POST",
      { timeout: 90000 }
    );
    await page.locator(buttonSelector).first().click({ timeout: 10000 });
    const response = await responsePromise;
    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = { ok: false, error: String(error) };
    }
    await page.waitForFunction(
      selector => {
        const element = document.querySelector(selector);
        if (!element) return false;
        const text = element.textContent || "";
        return !text.includes("等待") && !text.includes("正在");
      },
      resultSelector,
      { timeout: 90000 }
    );
    const text = await page.locator(resultSelector).innerText({ timeout: 10000 });
    const evidenceCardCount = await page.locator(`${resultSelector} [data-source-evidence-card="true"]`).count();
    return { status: response.status(), data, text, evidenceCardCount };
  }

  function evaluateReview(caseDef, result, action) {
    const data = action.data || {};
    const sources = Array.isArray(data.sources) ? data.sources : [];
    const source = sources[0] || {};
    const matchedTerms = lowerList(source.matched_terms);
    const evidence = String(source.evidence_excerpt || source.direct_evidence || "");

    result.review = {
      status: action.status,
      ok: Boolean(data.ok),
      ui_text: action.text.slice(0, 1200),
      source_count: sources.length,
      evidence_card_count: action.evidenceCardCount,
      top_source: {
        title: source.title || "",
        path: source.path || "",
        matched_terms: source.matched_terms || [],
        evidence_excerpt: evidence,
      },
    };

    if (caseDef.expectMatch) {
      if (!data.ok || !sources.length) {
        failCase(result, "review expected a reliable match");
      }
      if (!action.text.includes("一句话答案") || !action.text.includes("命中证据")) {
        failCase(result, "review result is missing readable document sections");
      }
      if (action.evidenceCardCount < 1) {
        failCase(result, "review UI did not render data-source-evidence-card");
      }
      if (!evidence) {
        failCase(result, "review source missing evidence_excerpt");
      }
      for (const term of caseDef.mustMatchTerms || []) {
        if (!matchedTerms.includes(String(term).toLowerCase())) {
          failCase(result, "review source missing required matched_terms", { term });
        }
      }
      if (caseDef.mustMatchAny && !caseDef.mustMatchAny.some(term => matchedTerms.includes(String(term).toLowerCase()))) {
        failCase(result, "review source missing any required matched_terms", { terms: caseDef.mustMatchAny });
      }
      if (caseDef.mustNotMatchTop && hasAny(sourceFingerprint(source), caseDef.mustNotMatchTop)) {
        failCase(result, "review top source matched forbidden unrelated topic", { forbidden: caseDef.mustNotMatchTop });
      }
    } else {
      if (data.ok || sources.length) {
        failCase(result, "review should not return matches for missing topic");
      }
      if (!action.text.includes("未完成")) {
        failCase(result, "review missing topic did not show 未完成 state");
      }
      if (action.evidenceCardCount > 0) {
        failCase(result, "review missing topic still rendered evidence cards");
      }
    }
  }

  function evaluateExtractPreview(caseDef, result, action) {
    const data = action.data || {};
    const sources = Array.isArray(data.sources) ? data.sources : [];
    const artifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
    result.extract = {
      status: action.status,
      ok: Boolean(data.ok),
      mode: data.debug?.mode || "",
      source_count: sources.length,
      artifact_count: artifacts.length,
      ui_text: action.text.slice(0, 1000),
      top_source_path: sources[0]?.path || "",
    };

    if (caseDef.expectMatch) {
      if (!data.ok || !sources.length) {
        failCase(result, "extract preview expected candidate sources");
      }
      if (data.debug?.mode !== "preview") {
        failCase(result, "extract did not run in preview mode");
      }
      if (artifacts.length) {
        failCase(result, "extract preview wrote artifacts");
      }
      if (!action.text.includes("找到候选") || !action.text.includes("确认生成上下文包")) {
        failCase(result, "extract preview UI did not show candidate confirmation");
      }
      const reviewPath = result.review?.top_source?.path || "";
      const previewPaths = new Set(sources.map(source => source.path).filter(Boolean));
      if (reviewPath && !previewPaths.has(reviewPath)) {
        failCase(result, "extract preview did not reuse top review source", { reviewPath });
      }
    } else {
      if (data.ok || sources.length) {
        failCase(result, "extract preview should not find sources for missing topic");
      }
      if (!action.text.includes("未完成")) {
        failCase(result, "extract preview missing topic did not show 未完成 state");
      }
    }
  }

  try {
    await page.waitForSelector("#reviewInput", { timeout: 20000 });
    report.title = await page.title();
    const featureCount = await page.locator(".feature-anchor").count();
    if (featureCount !== 3) {
      report.ux_issues.push({ id: "wrong-feature-count", message: "home should expose exactly three operations", feature_count: featureCount });
    }

    for (const caseDef of cases) {
      const result = {
        name: caseDef.name,
        query: caseDef.query,
        expected_match: caseDef.expectMatch,
        passed: true,
        reasons: [],
      };

      await fill("#reviewInput", caseDef.query);
      const reviewAction = await clickAndCapture("#review .action-buttons .site-button.primary", "#reviewResult");
      evaluateReview(caseDef, result, reviewAction);

      await fill("#extractInput", `为“${caseDef.query}”生成 AI 上下文包`);
      const extractAction = await clickAndCapture("#extract .action-buttons .site-button.primary", "#extractResult");
      evaluateExtractPreview(caseDef, result, extractAction);

      report.cases.push(result);
    }
  } catch (error) {
    report.mechanics_failures.push({ message: "uncaught real query GUI QA error", error: String(error && error.message ? error.message : error) });
  }

  report.finished_at = new Date().toISOString();
  const failedCases = report.cases.filter(item => !item.passed);
  report.ok = report.mechanics_failures.length === 0 && report.ux_issues.length === 0 && failedCases.length === 0;
  report.summary = {
    total: report.cases.length,
    passed: report.cases.filter(item => item.passed).length,
    failed: failedCases.length,
    extract_mode: EXTRACT_MODE,
  };
  return report;
}
