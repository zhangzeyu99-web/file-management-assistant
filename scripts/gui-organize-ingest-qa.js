async page => {
  const QUERY = "GuiOrganizeIngestEvidence-20260602";
  const REPORT_FILENAMES = ["gui-organize-ingest-qa-result.json", "gui-organize-ingest-qa-summary.md"];

  const report = {
    ok: true,
    mode: "organize-ingest-review",
    report_filenames: REPORT_FILENAMES,
    started_at: new Date().toISOString(),
    page_url: page.url(),
    source_path: "",
    inspect: {},
    organize: {},
    review: {},
    mechanics_failures: [],
    ux_issues: [],
    console_events: [],
    network_events: [],
  };

  function queryParam(name) {
    const match = page.url().match(new RegExp(`[?&;]${name}=([^&#;]*)`));
    return match ? decodeURIComponent(match[1].replace(/\+/g, " ")) : "";
  }

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

  function buttonLocator(label, scope = "body") {
    return page.locator(scope).getByRole("button", {name: new RegExp(`^\\s*${label}\\s*$`)}).first();
  }

  async function clickActionAndCapture(button, resultSelector) {
    const responsePromise = page.waitForResponse(
      response => response.url().includes("/api/action") && response.request().method() === "POST",
      {timeout: 90000}
    );
    await button.click({timeout: 15000});
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
    const evidenceCardCount = await page.locator(`${resultSelector} [data-source-evidence-card="true"]`).count();
    return {status: response.status(), data, text, evidenceCardCount};
  }

  function artifactTypes(data) {
    return (data?.artifacts || []).map(item => item.type);
  }

  try {
    const sourcePath = queryParam("sourcePath");
    const organizeScreenshotPath = queryParam("organizeScreenshotPath");
    report.source_path = sourcePath;
    if (!sourcePath) {
      fail("sourcePath query parameter is missing");
      return report;
    }

    await page.waitForSelector("#organizeInput", {timeout: 20000});
    await page.locator("#localPaths").fill(sourcePath);
    await page.locator("#organizeInput").fill("GUI organize ingest QA: scan a real local directory and index every readable file.");

    const inspectAction = await clickActionAndCapture(buttonLocator("检查本地目标", "#organize"), "#organizeResult");
    report.inspect = {
      status: inspectAction.status,
      ok: Boolean(inspectAction.data?.ok),
      mode: inspectAction.data?.mode || "",
      existing_count: inspectAction.data?.summary?.existing_count || 0,
      ui_text: inspectAction.text.slice(0, 800),
    };
    if (!inspectAction.data?.ok || inspectAction.data?.mode !== "custom-local-paths" || (inspectAction.data?.summary?.existing_count || 0) < 1) {
      fail("检查本地目标 did not recognize the pasted real directory", report.inspect);
    }

    const organizeAction = await clickActionAndCapture(buttonLocator("添加资料", "#organize"), "#organizeResult");
    const fileIndexNotes = organizeAction.data?.debug?.file_index_notes || [];
    report.organize = {
      status: organizeAction.status,
      ok: Boolean(organizeAction.data?.ok),
      total_files: organizeAction.data?.debug?.scan?.total_files || 0,
      file_index_count: organizeAction.data?.debug?.file_index_count || 0,
      file_index_notes: fileIndexNotes,
      generated_file_index_notes: fileIndexNotes,
      artifact_types: artifactTypes(organizeAction.data),
      obsidian_locations: organizeAction.data?.debug?.obsidian_locations || {},
      ui_text: organizeAction.text.slice(0, 1600),
      screenshot: organizeScreenshotPath || "",
    };
    if (!organizeAction.data?.ok) {
      fail("添加资料 did not return ok", report.organize);
    }
    if ((organizeAction.data?.debug?.scan?.total_files || 0) < 2) {
      fail("添加资料 did not scan the demo directory files", report.organize);
    }
    if ((organizeAction.data?.debug?.file_index_count || 0) < 2 || fileIndexNotes.length < 2) {
      fail("添加资料 did not create independent file index notes", report.organize);
    }
    for (const requiredType of ["obsidian-note", "markdown", "json", "file-index", "file-index-directory"]) {
      if (!report.organize.artifact_types.includes(requiredType)) {
        fail("添加资料 missing required artifact type", {requiredType, artifact_types: report.organize.artifact_types});
      }
    }
    for (const requiredText of ["已扫描", "本次入库结果", "独立文件索引", "源文件改动", "在 Obsidian 里怎么找", "文件索引目录", "推荐搜索词", "入库来源", "入库产物"]) {
      if (!organizeAction.text.includes(requiredText)) {
        fail("添加资料 result missing readable UI text", {requiredText});
      }
    }
    if (organizeScreenshotPath) {
      await page.locator("#organizeResult").scrollIntoViewIfNeeded({timeout: 10000});
      await page.screenshot({path: organizeScreenshotPath, fullPage: false});
    }

    await page.locator("#reviewInput").fill(QUERY);
    const reviewAction = await clickActionAndCapture(buttonLocator("搜索回顾", "#review"), "#reviewResult");
    const sources = Array.isArray(reviewAction.data?.sources) ? reviewAction.data.sources : [];
    const topSource = sources[0] || {};
    const evidence = String(topSource.evidence_excerpt || topSource.direct_evidence || "");
    report.review = {
      status: reviewAction.status,
      ok: Boolean(reviewAction.data?.ok),
      source_count: sources.length,
      evidence_card_count: reviewAction.evidenceCardCount,
      review_top_source_path: topSource.path || "",
      top_source_title: topSource.title || "",
      matched_terms: topSource.matched_terms || [],
      evidence_excerpt: evidence,
      ui_text: reviewAction.text.slice(0, 1600),
    };
    if (!reviewAction.data?.ok || !sources.length) {
      fail("搜索回顾 could not find the evidence that was just ingested", report.review);
    }
    if (!evidence.includes(QUERY) && !String(topSource.summary || "").includes(QUERY)) {
      fail("搜索回顾 top source does not include the ingested evidence token", report.review);
    }
    if (!fileIndexNotes.includes(topSource.path)) {
      fail("搜索回顾 top source is not one of the generated file index notes", {
        review_top_source_path: topSource.path || "",
        generated_file_index_notes: fileIndexNotes,
      });
    }
    for (const requiredText of ["一句话答案", "命中证据", "证据摘录", "来源路径"]) {
      if (!reviewAction.text.includes(requiredText)) {
        fail("搜索回顾 result missing readable evidence section", {requiredText});
      }
    }
    if (reviewAction.evidenceCardCount < 1) {
      fail("搜索回顾 did not render data-source-evidence-card", report.review);
    }
  } catch (error) {
    fail("uncaught organize ingest GUI QA error", {error: String(error && error.message ? error.message : error)});
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
