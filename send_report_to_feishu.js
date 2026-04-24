'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  readJsonFile,
  resolveFeishuBotTarget,
  sendBotInteractiveCard,
} = require('C:/Users/Administrator/.openclaw/scripts/lib/feishu_bot_card.js');

const DEFAULT_CONFIG_PATH = path.join(process.env.USERPROFILE || os.homedir(), '.openclaw', 'openclaw.json');

function parseArgs(argv) {
  const args = {
    configPath: DEFAULT_CONFIG_PATH,
    summaryJson: '',
    htmlFile: '',
    accountId: 'bot-xiaoxia',
    openId: '',
    dryRun: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--config') args.configPath = argv[index + 1] || args.configPath;
    if (arg === '--summary-json') args.summaryJson = argv[index + 1] || '';
    if (arg === '--html-file') args.htmlFile = argv[index + 1] || '';
    if (arg === '--account-id') args.accountId = argv[index + 1] || args.accountId;
    if (arg === '--open-id') args.openId = argv[index + 1] || '';
    if (arg === '--dry-run') args.dryRun = true;
  }

  return args;
}

function compact(value, max = 80) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function buildCard(summary, htmlFile) {
  const counts = summary.counts || {};
  const generatedAt = summary.generated_at || new Date().toISOString();
  const htmlPath = htmlFile || summary.html_report || '';
  const markdownPath = summary.markdown_report || '';

  const lines = [
    `**扫描文件**：${summary.total_files || 0} 个，约 ${summary.total_size_mb || 0} MB`,
    `**近期复盘**：${counts.recent_review || 0} | **建议归档**：${counts.archive_candidates || 0}`,
    `**清理提醒**：${counts.installer_cleanup || 0} | **大文件**：${counts.large_files || 0} | **重复组**：${counts.duplicate_groups || 0}`,
  ];

  const topReview = ((summary.classifications || {}).recent_review || [])
    .slice(0, 3)
    .map((item, index) => `${index + 1}. ${compact(item.path, 64)}`);

  const topArchive = ((summary.classifications || {}).archive_candidates || [])
    .slice(0, 3)
    .map((item, index) => `${index + 1}. ${compact(item.path, 64)}`);

  const elements = [
    {
      tag: 'div',
      text: {
        tag: 'lark_md',
        content: lines.join('\n'),
      },
    },
    { tag: 'hr' },
    {
      tag: 'div',
      text: {
        tag: 'lark_md',
        content: `**HTML 汇报**\n${htmlPath}\n\n**Markdown 备份**\n${markdownPath}`,
      },
    },
  ];

  if (topReview.length > 0) {
    elements.push(
      { tag: 'hr' },
      {
        tag: 'div',
        text: {
          tag: 'lark_md',
          content: `**近期复盘 Top 3**\n${topReview.join('\n')}`,
        },
      },
    );
  }

  if (topArchive.length > 0) {
    elements.push(
      { tag: 'hr' },
      {
        tag: 'div',
        text: {
          tag: 'lark_md',
          content: `**建议归档 Top 3**\n${topArchive.join('\n')}`,
        },
      },
    );
  }

  elements.push({
    tag: 'note',
    elements: [
      {
        tag: 'plain_text',
        content: `生成：${generatedAt} | 策略：不删除、不移动、不改名源文件`,
      },
    ],
  });

  return {
    config: {
      wide_screen_mode: true,
    },
    header: {
      template: 'turquoise',
      title: {
        tag: 'plain_text',
        content: `文件管理助手汇报 | ${String(generatedAt).slice(0, 10)}`,
      },
    },
    elements,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.summaryJson) throw new Error('Missing --summary-json');
  if (!fs.existsSync(args.summaryJson)) throw new Error(`summary_json not found: ${args.summaryJson}`);

  const config = readJsonFile(args.configPath);
  const summary = readJsonFile(args.summaryJson);
  const target = resolveFeishuBotTarget(config, {
    accountId: args.accountId,
    openId: args.openId,
  });
  const card = buildCard(summary, args.htmlFile);

  if (args.dryRun) {
    process.stdout.write(`${JSON.stringify({ ok: true, dryRun: true, accountId: target.accountId, openId: target.openId })}\n`);
    return;
  }

  const result = await sendBotInteractiveCard({
    appId: target.appId,
    appSecret: target.appSecret,
    openId: target.openId,
    card,
  });

  process.stdout.write(`${JSON.stringify({
    ok: true,
    accountId: target.accountId,
    openId: target.openId,
    messageId: result.messageId,
    chatId: result.chatId,
    createTime: result.createTime,
  })}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || String(error)}\n`);
  process.exit(1);
});
