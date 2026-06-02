async page => {
  const QUERY = "Obsidian 教程闭环证据";
  const REPORT_FILENAMES = ["gui-context-package-qa-result.json", "gui-context-package-qa-summary.md"];

  const report = {
    ok: true,
    mode: "review-seed-generate",
    report_filenames: REPORT_FILENAMES,
    started_at: new Date().toISOString(),
    page_url: page.url(),
    title: "",
    review: {},
    seeded_context_from_review: {},
    generated: {},
    mechanics_failures: [],
    ux_issues: [],
    console_events: [],
    network_events: [],
  };

  page.on("console", message => {
    if (["error", "warning"].includes(message.type())) {
      report.console_events.push({type: message.type(), text: message.text()});
    }
  });
  page.on("response", response => {
    if (response.url().includes("/api/action")) {
      report.network_events.push({url: response.url(), status: response.status(), method: response.request().method()});
    }
  });

  function fail(message, data = {}) {
    report.ok = false;
    report.mechanics_failures.push({message, ...data});
  }

  async function clickActionAndCapture(buttonLocator, resultSelector) {
    const responsePromise = page.waitForResponse(
      response => response.url().includes("/api/action") && response.request().method() === "POST",
      {timeout: 90000}
    );
    await buttonLocator.click({timeout: 15000});
    const response = await responsePromise;
    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = {ok: false, error: String(error)};
    }
    await page.waitForFunction(
      selector => {
        const element = document.querySelector(selector);
        if (!element) return false;
        const text = element.textContent || "";
        return !text.includes("等待") && !text.includes("正在");
      },
      resultSelector,
      {timeout: 90000}
    );
    const text = await page.locator(resultSelector).innerText({timeout: 15000});
    return {status: response.status(), data, text};
  }

  function artifactPath(data, type) {
    const artifact = (data?.artifacts || []).find(item => item.type === type);
    return artifact?.path || "";
  }

  function artifactContent(data, type) {
    const artifact = (data?.artifacts || []).find(item => item.type === type);
    return artifact?.content || "";
  }

  try {
    await page.waitForSelector("#reviewInput", {timeout: 20000});
    report.title = await page.title();

    await page.locator("#reviewInput").fill(QUERY);
    const reviewAction = await clickActionAndCapture(page.locator("#review .action-buttons .site-button.primary").first(), "#reviewResult");
    const reviewSources = Array.isArray(reviewAction.data?.sources) ? reviewAction.data.sources : [];
    const topSource = reviewSources[0] || {};
    report.review = {
      status: reviewAction.status,
      ok: Boolean(reviewAction.data?.ok),
      source_count: reviewSources.length,
      top_source_title: topSource.title || "",
      top_source_path: topSource.path || "",
      matched_terms: topSource.matched_terms || [],
      ui_has_evidence_card: await page.locator("#reviewResult [data-source-evidence-card='true']").count(),
    };

    if (!reviewAction.data?.ok || !reviewSources.length) {
      fail("review did not find seeded evidence", report.review);
    }
    if (!String(topSource.title || "").includes(QUERY) && !String(topSource.evidence_excerpt || topSource.summary || "").includes(QUERY)) {
      fail("top review source is not the seeded evidence", {topSource});
    }

    const joinButton = page.locator("#reviewResult [data-source-evidence-card='true'] button", {hasText: "加入上下文包"}).first();
    await joinButton.click({timeout: 15000});
    await page.waitForFunction(
      () => {
        const element = document.querySelector("#extractResult");
        return element && (element.textContent || "").includes("已加入上下文包候选");
      },
      null,
      {timeout: 30000}
    );
    report.seeded_context_from_review = {
      ok: true,
      text: (await page.locator("#extractResult").innerText({timeout: 10000})).slice(0, 1000),
    };
    if (!report.seeded_context_from_review.text.includes("确认生成上下文包")) {
      fail("seeded context result does not show confirm action");
    }

    const generateAction = await clickActionAndCapture(
      page.locator("#extractResult button", {hasText: "确认生成上下文包"}).first(),
      "#extractResult"
    );
    const generated = generateAction.data || {};
    const generatedPrompt = artifactContent(generated, "prompt");
    const generatedMarkdown = artifactPath(generated, "markdown");
    const generatedObsidianNote = artifactPath(generated, "obsidian-note");
    report.generated = {
      status: generateAction.status,
      ok: Boolean(generated.ok),
      mode: generated.debug?.mode || "",
      source_count: Array.isArray(generated.sources) ? generated.sources.length : 0,
      artifact_types: (generated.artifacts || []).map(item => item.type),
      generated_prompt: generatedPrompt,
      generated_markdown: generatedMarkdown,
      generated_obsidian_note: generatedObsidianNote,
      ui_text: generateAction.text.slice(0, 1400),
    };

    const isGenerateMode = generated.debug?.mode === "generate";
    if (!generated.ok || !isGenerateMode) {
      fail("extract generate did not return ok generate mode", report.generated);
    }
    if (!generatedPrompt.includes(QUERY) || !generatedPrompt.includes("先引用来源路径")) {
      fail("generated prompt does not include seeded query and source-path instruction");
    }
    if (!generatedMarkdown || !generatedObsidianNote) {
      fail("generated result missing markdown or obsidian-note artifact paths", report.generated);
    }
    if (!generateAction.text.includes("AI 上下文包已生成") || !generateAction.text.includes("复制 prompt")) {
      fail("generated UI does not show readable completion and prompt action");
    }
  } catch (error) {
    fail("uncaught context package GUI QA error", {error: String(error && error.message ? error.message : error)});
  }

  report.finished_at = new Date().toISOString();
  report.summary = {
    ok: report.ok,
    console_events: report.console_events.length,
    network_events: report.network_events.length,
    mechanics_failures: report.mechanics_failures.length,
    ux_issues: report.ux_issues.length,
  };
  return report;
}
