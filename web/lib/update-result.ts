type RecordValue = Record<string, unknown>;

function record(value: unknown): RecordValue {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
}

export function updateResultView(value: unknown, options: { active?: boolean } = {}) {
  const result = record(value);
  const counts = record(result.counts);
  const checks = Array.isArray(result.source_checks) ? result.source_checks.map(record) : [];
  const errors = Array.isArray(result.errors) ? result.errors : [];
  const groups = new Map<string, number>();
  const registrationWarnings = new Set<string>();
  for (const check of checks) {
    const reason = typeof check.reason === "string" ? check.reason : "";
    const label = check.kind === "feishu" ? "飞书入口（仅元数据）"
      : reason === "空文件，没有可归档正文" ? "空文件"
      : reason === "表格数据，正文分析需使用专项流程" ? "表格数据（需专项分析）"
      : check.body_read === true ? "读后无可积累内容"
      : /凭据|配置文件/.test(reason) ? "敏感或配置文件（不读正文）"
      : /脚本或工程文件/.test(reason) ? "工程文件（不读正文）"
      : /不支持的文件格式/.test(reason) ? "暂不支持的格式（不读正文）"
      : "其他来源登记";
    groups.set(label, (groups.get(label) || 0) + 1);
    if (reason) registrationWarnings.add(reason + "，仅记录来源，未生成知识笔记");
  }
  const warnings = (Array.isArray(result.warnings) ? result.warnings : []).filter(warning =>
    typeof warning !== "string" || (!registrationWarnings.has(warning) &&
      !(checks.some(check => check.kind === "feishu") && /：仅登记飞书入口，未读取或总结正文$/.test(warning))));
  const nativeLimited = errors.some(error => /原生.*限制/.test(String(record(error).error || ""))) ||
    warnings.some(warning => typeof warning === "string" && /接口上限|原生.*限制/.test(warning));
  const noteCount = Array.isArray(result.notes) ? result.notes.length :
    Object.values(counts).reduce<number>((total, count) => total + (typeof count === "number" && count > 0 ? count : 0), 0);
  const noteSources = [["files", "文件"], ["threads", "对话"], ["feishu", "飞书正文"]]
    .filter(([key]) => typeof counts[key] === "number" && Number(counts[key]) > 0)
    .map(([key, label]) => `${label} ${counts[key]} 篇`).join(" · ");
  return {
    noteCount, noteSources, errors, warnings, nativeLimited,
    summary: noteCount ? `本轮累计保存 ${noteCount} 篇知识笔记。` : options.active ? "" : "本轮暂无新增知识笔记。",
    registrationCount: checks.length,
    registrations: Array.from(groups, ([label, count]) => ({ label, count })),
  };
}
