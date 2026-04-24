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
    markdownFile: '',
    accountId: 'bot-xiaoxia',
    openId: '',
    dryRun: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--config') args.configPath = argv[index + 1] || args.configPath;
    if (arg === '--summary-json') args.summaryJson = argv[index + 1] || '';
    if (arg === '--markdown-file') args.markdownFile = argv[index + 1] || '';
    if (arg === '--account-id') args.accountId = argv[index + 1] || args.accountId;
    if (arg === '--open-id') args.openId = argv[index + 1] || '';
    if (arg === '--dry-run') args.dryRun = true;
  }

  return args;
}

function compact(value, max = 90) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function topItems(items, key, limit = 3) {
  return (items || []).slice(0, limit).map((item, index) => `${index + 1}. ${compact(item[key] || item.path || item.note || item.title, 70)}`);
}

function buildCard(summary, markdownFile) {
  const counts = summary.counts || {};
  const generatedAt = summary.generated_at || new Date().toISOString();
  const markdownPath = markdownFile || summary.markdown_report || '';
  const obsidianNote = summary.obsidian_note || '';
  const classifications = summary.classifications || {};

  const overview = [
    `**笔记数**：${summary.total_notes || 0} | **体量**：${summary.total_size_kb || 0} KB`,
    `**收件箱**：${counts.inbox_triage || 0} | **空壳**：${counts.empty_or_stub || 0} | **低连接**：${counts.low_link_notes || 0}`,
    `**断链**：${counts.broken_links || 0} | **目录式链接**：${counts.folder_links || 0} | **重名**：${counts.duplicate_titles || 0} | **索引缺口**：${counts.unindexed_codex || 0}`,
    `**策略**：只读审计，不删除、不移动、不覆盖源笔记`,
  ];

  const elements = [
    {
      tag: 'div',
      text: {
        tag: 'lark_md',
        content: overview.join('\n'),
      },
    },
    { tag: 'hr' },
    {
      tag: 'div',
      text: {
        tag: 'lark_md',
        content: `**Markdown 报告**\n${markdownPath}\n\n**Obsidian 落地**\n${obsidianNote}`,
      },
    },
  ];

  const inbox = topItems(classifications.inbox_triage, 'path');
  if (inbox.length > 0) {
    elements.push(
      { tag: 'hr' },
      {
        tag: 'div',
        text: {
          tag: 'lark_md',
          content: `**待整理收件箱 Top 3**\n${inbox.join('\n')}`,
        },
      },
    );
  }

  const broken = topItems(classifications.broken_links, 'link');
  if (broken.length > 0) {
    elements.push(
      { tag: 'hr' },
      {
        tag: 'div',
        text: {
          tag: 'lark_md',
          content: `**断链 Top 3**\n${broken.join('\n')}`,
        },
      },
    );
  }

  elements.push({
    tag: 'note',
    elements: [
      {
        tag: 'plain_text',
        content: `生成：${generatedAt} | 编码：UTF-8 | 本轮不改源笔记`,
      },
    ],
  });

  return {
    config: {
      wide_screen_mode: true,
    },
    header: {
      template: 'green',
      title: {
        tag: 'plain_text',
        content: `Obsidian 管理自评与进化 | ${String(generatedAt).slice(0, 10)}`,
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
  const card = buildCard(summary, args.markdownFile);

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
