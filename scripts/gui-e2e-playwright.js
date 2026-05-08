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
  };

  const includeOpeners = /[?&#;]includeOpeners=1(?:[&;#]|$)/.test(page.url());
  const readOnly = /[?&#;]readOnly=1(?:[&;#]|$)/.test(page.url());
  function queryParam(name) {
    const match = page.url().match(new RegExp(`[?&]${name}=([^&#]*)`));
    return match ? decodeURIComponent(match[1].replace(/\+/g, " ")) : "";
  }
  const e2eLocalPath = queryParam("e2eLocalPath");
  report.include_openers = includeOpeners;
  report.read_only = readOnly;
  report.e2e_local_path = e2eLocalPath;

  const textInput = page.locator("#freeText");
  const localPathInput = page.locator("#localPaths");
  const output = page.locator("#out");

  function addFailure(message, data = {}) {
    report.ok = false;
    report.mechanics_failures.push({ message, ...data });
  }

  function addIssue(id, message, data = {}) {
    report.ux_issues.push({ id, message, ...data });
  }

  async function visibleText(selector) {
    try {
      return await page.locator(selector).innerText({ timeout: 1000 });
    } catch {
      return "";
    }
  }

  async function isOutputVisible() {
    try {
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

  function buttonLocator(label, scope = "body") {
    return page
      .locator(scope)
      .getByRole("button", { name: new RegExp(`^\\s*${escapeRegExp(label)}\\s*$`) })
      .first();
  }

  async function clickAndCapture({ label, expectedAction, input = "", scope = "body", expectPopup = false }) {
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
      await textInput.fill(input);
      const responsePromise = page.waitForResponse(
        response => response.url().includes("/api/action") && response.request().method() === "POST",
        { timeout: 20000 },
      );
      const popupPromise = expectPopup
        ? page.waitForEvent("popup", { timeout: 5000 }).catch(() => null)
        : Promise.resolve(null);

      const button = buttonLocator(label, scope);
      await button.scrollIntoViewIfNeeded();
      await button.click();

      const response = await responsePromise;
      const popup = await popupPromise;
      item.opened_popup = Boolean(popup);
      if (popup) {
        await popup.close().catch(() => {});
      }

      item.http_status = response.status();
      const requestData = response.request().postDataJSON();
      item.request_action = requestData.action || null;
      item.response = await response.json();
      item.response_ok = Boolean(item.response && item.response.ok);
      await page.waitForTimeout(250);
      item.output_visible = await isOutputVisible();
      const outputText = await visibleText("#out");
      item.output_looks_like_json = /^\s*\{[\s\S]*\}\s*$/.test(outputText);
      item.result_text = `${await visibleText("#workbenchResult")}\n${await visibleText("#resultList")}`;
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
        addIssue("raw-json-default-output", "action result defaults to a black JSON/code box", {
          label,
          action: expectedAction,
        });
      }
      if (!/做了什么|来源|产物|下一步|结果|已生成|已写入|匹配|提醒|本地摘要/.test(item.result_text)) {
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
  report.title = await page.title();

  const bodyText = await page.locator("body").innerText();
  const mustHave = [
    "本地知识整理助手",
    "整理资料",
    "回顾知识",
    "提取上下文",
    "今日提醒",
    "本地文件 / 目录目标",
    "拖放文件到这里",
    "检查本地目标",
    "高级/诊断",
  ];
  for (const phrase of mustHave) {
    if (!bodyText.includes(phrase)) {
      addIssue("missing-core-copy", `missing required UI copy: ${phrase}`);
    }
  }
  for (const obsolete of ["Codex 文件管理小助手", "可视化上下文入口", "Codex 接手包", "今日操作台", "执行结果", "伪控制台"]) {
    if (bodyText.includes(obsolete)) {
      addIssue("obsolete-positioning-copy", `obsolete UI copy still appears: ${obsolete}`);
    }
  }

  const fileInputCount = await page.locator("input[type=file]").count();
  const localPathInputCount = await page.locator("#localPaths").count();
  const dropZoneCount = await page.locator("#fileDropZone").count();
  const hasFileDropText = /拖放|选择文件|选择目录|本地路径|本地文件 \/ 目录目标/.test(bodyText);
  if (fileInputCount === 0 || localPathInputCount === 0 || dropZoneCount === 0 || !hasFileDropText) {
    addIssue("missing-file-target-workbench", "file scanning has no complete local target workbench with path input, file picker, and drop zone");
  }
  if (e2eLocalPath && localPathInputCount > 0) {
    await localPathInput.fill(e2eLocalPath);
  }

  await clickAndCapture({
    label: "检查本地目标",
    expectedAction: "inspect-local-targets",
    input: "",
    scope: ".path-actions",
  });

  if (readOnly) {
    await clickAndCapture({
      label: "回顾知识",
      expectedAction: "review",
      input: "Obsidian 教程和 AI 上下文包怎么用？",
      scope: ".primary-actions",
    });
    report.skipped.push({ label: "整理资料", action: "organize", reason: "read-only smoke mode" });
    report.skipped.push({ label: "提取上下文", action: "extract", reason: "read-only smoke mode" });
    report.skipped.push({ label: "今日提醒", action: "remind", reason: "read-only smoke mode" });
    report.skipped.push({ label: "查看文件雷达", action: "file-radar", reason: "read-only smoke mode" });
    report.skipped.push({ label: "检查知识库", action: "obsidian-health", reason: "read-only smoke mode" });
  } else {
    await clickAndCapture({
      label: "整理资料",
      expectedAction: "organize",
      input: "NotebookLM 和 Obsidian 教程资料，后续要整理为学习资料并给 AI 复用。",
      scope: ".primary-actions",
    });
    await clickAndCapture({
      label: "回顾知识",
      expectedAction: "review",
      input: "Obsidian 教程",
      scope: ".primary-actions",
    });
    await clickAndCapture({
      label: "提取上下文",
      expectedAction: "extract",
      input: "继续优化本地知识整理助手，需要已有 Obsidian 教程和 GUI 测试上下文。",
      scope: ".primary-actions",
    });
    await clickAndCapture({
      label: "今日提醒",
      expectedAction: "remind",
      input: "今天只做 1-3 个重点，不处理全部 backlog。",
      scope: ".primary-actions",
    });

    await page.locator("details").first().evaluate(el => { el.open = true; });
    await clickAndCapture({
      label: "查看文件雷达",
      expectedAction: "file-radar",
      input: "",
      scope: ".advanced-card",
    });
    await clickAndCapture({
      label: "检查知识库",
      expectedAction: "obsidian-health",
      input: "",
      scope: ".advanced-card",
    });
    await clickAndCapture({
      label: "二次整理旧资料",
      expectedAction: "legacy-index",
      input: "",
      scope: ".advanced-card",
    });
  }

  if (includeOpeners) {
    await page.locator("details").first().evaluate(el => { el.open = true; });
    await clickAndCapture({
      label: "打开 Obsidian",
      expectedAction: "open-obsidian",
      input: "",
      scope: ".advanced-card",
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
    if (e2eLocalPath && fileRadar.response.target_mode !== "custom-local-paths") {
      addIssue("file-radar-did-not-use-local-targets", "file radar did not use pasted local paths as scan targets", {
        action: "file-radar",
        target_mode: fileRadar.response.target_mode,
      });
    }
    const resultText = `${fileRadar.result_text}\n${await visibleText("#out")}`;
    if (!/打开|报告|路径|继续|复制|产物|下一步/.test(resultText)) {
      addIssue("missing-next-action-buttons", "file radar result does not expose clear next action buttons in the main workbench", {
        action: "file-radar",
      });
    }
  }

  return report;
}
