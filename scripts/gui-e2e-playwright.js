async page => {
  const startedAt = new Date().toISOString();
  const report = {
    ok: true,
    started_at: startedAt,
    page_url: page.url(),
    title: "",
    mechanics_failures: [],
    ux_issues: [],
    skipped: [],
    actions: [],
  };

  const textInput = page.locator("#freeText");
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

  async function clickAndCapture({ label, expectedAction, input = "", expectPopup = false }) {
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

      const button = page.getByRole("button", { name: new RegExp(escapeRegExp(label)) }).first();
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
      item.result_text = await visibleText("#resultList");
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
    } catch (error) {
      item.error = String(error && error.message ? error.message : error);
      addFailure("button click failed", { label, expected_action: expectedAction, error: item.error });
    }
  }

  await page.waitForLoadState("domcontentloaded");
  report.title = await page.title();

  const bodyText = await page.locator("body").innerText();
  const fileInputCount = await page.locator("input[type=file]").count();
  const hasFileDropText = /拖放|选择文件|选择目录|选择文件夹|本地路径|扫描范围/.test(bodyText);
  if (fileInputCount === 0 && !hasFileDropText) {
    addIssue("missing-file-input", "file scanning has no file picker, directory picker, drag-drop area, or explicit local path input");
  }

  await clickAndCapture({
    label: "问怎么用",
    expectedAction: "ask",
    input: "我应该如何处理今天下载的一批报告？",
  });
  await clickAndCapture({
    label: "判断放哪",
    expectedAction: "inbox-route",
    input: "NotebookLM 和 Obsidian 教程资料，后续要复用。",
  });
  await clickAndCapture({
    label: "查看文件雷达",
    expectedAction: "file-radar",
    input: "",
  });
  await clickAndCapture({
    label: "检查知识库",
    expectedAction: "obsidian-health",
    input: "",
  });
  await clickAndCapture({
    label: "记录一个任务",
    expectedAction: "action-note",
    input: "E2E 测试：记录一个真实任务，并确认生成 Action 笔记。",
  });
  await clickAndCapture({
    label: "沉淀知识卡",
    expectedAction: "card-note",
    input: "E2E 发现：GUI 结果不能默认展示 JSON，要展示人能读懂的结果卡。",
  });
  await clickAndCapture({
    label: "复盘今天",
    expectedAction: "time-review",
    input: "完成 GUI E2E 真实点击测试，下一步修复输入与结果闭环。",
  });
  await clickAndCapture({
    label: "归档 AI 对话",
    expectedAction: "archive-ai-chat",
    input: "用户反馈：操作台只显示黑框，文件扫描没有文件输入框。",
  });
  await clickAndCapture({
    label: "提取 AI 上下文",
    expectedAction: "build-ai-context",
    input: "继续优化 GUI：文件输入框、人类可读结果卡、隐藏高级 JSON。",
  });
  await clickAndCapture({
    label: "复制上下文 prompt",
    expectedAction: "build-ai-context",
    input: "把 GUI E2E 结果交给下一轮实现。",
  });
  await clickAndCapture({
    label: "查看交互说明",
    expectedAction: "open-interaction-guide",
    input: "",
    expectPopup: true,
  });

  const fileRadar = report.actions.find(item => item.expected_action === "file-radar");
  if (fileRadar && fileRadar.response_ok) {
    const resultText = `${fileRadar.result_text}\n${await visibleText("#out")}`;
    if (!/打开|报告|路径|继续|复制/.test(resultText)) {
      addIssue("missing-next-action-buttons", "file radar result does not expose clear next action buttons in the main workbench", {
        action: "file-radar",
      });
    }
  }

  return report;
}
