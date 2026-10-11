// Pure helpers behind the message previews (no React, no network): template placeholders and the
// two platforms' text formats. Keep these in step with what the bot really sends:
//  * Telegram "Markdown" (legacy parse mode) - https://core.telegram.org/bots/api#markdown-style
//  * Discord Markdown                         - https://discord.com/developers/docs/reference#message-formatting

// ── Limits (official docs; checked when this was written) ─────────────────────
export const TELEGRAM_LIMITS = { text: 4096, caption: 1024 };   // after entity parsing
export const DISCORD_LIMITS = { content: 2000, embedDescription: 4096, embedTotal: 6000 };

// ── Sample values ─────────────────────────────────────────────────────────────
// Every sample value is invented. The preview labels them as samples; nothing here is real member data.
export const SAMPLE_VALUES = {
  name: 'Alex',
  first_name: 'Alex',
  last_name: 'Morgan',
  username: '@alex_m',
  full_name: 'Alex Morgan',
  user_id: '123456789',
  user: '@alex_m',
  mention: '@alex_m',
  group_name: 'Sample Community',
  group: 'Sample Community',
  server: 'Sample Server',
  server_name: 'Sample Server',
  member_count: '1,234',
  campaign_title: 'Sample Campaign',
  title: 'Sample Campaign',
  deadline: 'Oct 31, 18:00 UTC',
  reward: '100 XP',
  level: '5',
  xp: '1,250',
  rank: '3',
};

const pick = (names) => Object.fromEntries(names.map((n) => [n, SAMPLE_VALUES[n]]));
// Exactly the names the bot passes to str.format (backend/bot_features/welcome.py), so anything else is flagged.
export const WELCOME_VARS = pick(['name', 'first_name', 'last_name', 'username', 'full_name', 'group_name', 'member_count', 'user_id']);
// Discord welcome/leave placeholders (discord-board/backend/settings.py render_message): plain replacement, unknown names stay as written.
export const DISCORD_VARS = {
  user: '<@123456789012345678>',
  server: SAMPLE_VALUES.server,
  member_count: SAMPLE_VALUES.member_count,
};
export const WELCOME_DM_VARS = pick(['name', 'first_name', 'last_name', 'username', 'group_name']);

/**
 * Split a template into text / variable / unknown-variable segments.
 * syntax 'python' = the bot uses str.format: {name}, with {{ and }} as literal braces. An unknown
 *   name makes str.format raise, so the real message would not be sent - flagged as `unknown`.
 * syntax 'single' = simple {name} replacement where unknown names are left as written.
 */
export function fillTemplate(template, vars = SAMPLE_VALUES, syntax = 'python') {
  const src = String(template ?? '');
  const segments = [];
  const unknown = [];
  let buf = '';
  const flush = () => { if (buf) { segments.push({ type: 'text', text: buf }); buf = ''; } };
  for (let i = 0; i < src.length; i += 1) {
    const ch = src[i];
    if (syntax === 'python' && (ch === '{' || ch === '}') && src[i + 1] === ch) { buf += ch; i += 1; continue; }
    if (ch === '{') {
      const end = src.indexOf('}', i + 1);
      const name = end > i ? src.slice(i + 1, end) : null;
      if (name !== null && /^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
        flush();
        if (Object.prototype.hasOwnProperty.call(vars, name)) segments.push({ type: 'var', name, text: String(vars[name]) });
        else { segments.push({ type: 'unknown', name, text: `{${name}}` }); if (!unknown.includes(name)) unknown.push(name); }
        i = end;
        continue;
      }
    }
    buf += ch;
  }
  flush();
  return { segments, unknown, text: segments.map((s) => s.text).join('') };
}

// ── Telegram legacy Markdown ──────────────────────────────────────────────────
// Entities: *bold*, _italic_, `code`, ```pre```, [text](url). They cannot nest. A backslash escapes
// _ * ` [ . An opening mark with no closing mark makes Telegram reject the whole message
// ("can't parse entities"), so it is reported as a warning and shown literally.
export function parseTelegramMarkdown(input) {
  const s = String(input ?? '');
  const out = [];
  const warnings = [];
  let text = '';
  const push = () => { if (text) { out.push({ t: 'text', v: text }); text = ''; } };
  let i = 0;
  while (i < s.length) {
    const ch = s[i];
    if (ch === '\\' && '_*`['.includes(s[i + 1] || '')) { text += s[i + 1]; i += 2; continue; }
    if (ch === '`' && s.startsWith('```', i)) {
      const end = s.indexOf('```', i + 3);
      if (end > -1) { push(); out.push({ t: 'pre', v: s.slice(i + 3, end).replace(/^[A-Za-z0-9_+-]*\n/, '') }); i = end + 3; continue; }
    }
    if (ch === '`') {
      const end = s.indexOf('`', i + 1);
      if (end > -1) { push(); out.push({ t: 'code', v: s.slice(i + 1, end) }); i = end + 1; continue; }
      warnings.push('A ` (code) mark is never closed.');
    } else if (ch === '*' || ch === '_') {
      const end = s.indexOf(ch, i + 1);
      if (end > i + 1) { push(); out.push({ t: ch === '*' ? 'bold' : 'italic', v: s.slice(i + 1, end) }); i = end + 1; continue; }
      warnings.push(`A ${ch} mark is never closed.`);
    } else if (ch === '[') {
      const m = /^\[([^\]]+)\]\(([^)\s]+)\)/.exec(s.slice(i));
      if (m) { push(); out.push({ t: 'link', v: m[1], href: m[2] }); i += m[0].length; continue; }
    }
    text += ch; i += 1;
  }
  push();
  const uniq = [...new Set(warnings)];
  if (uniq.length) uniq.unshift('Telegram would reject this text as written ("can\'t parse entities"). Close the marks, or escape them with a backslash (\\_ \\* \\`).');
  return { nodes: out, warnings: uniq };
}

// ── Discord Markdown ──────────────────────────────────────────────────────────
const DISCORD_INLINE = [
  { t: 'bolditalic', re: /^\*\*\*([\s\S]+?)\*\*\*/ },
  { t: 'bold', re: /^\*\*([\s\S]+?)\*\*/ },
  { t: 'underline', re: /^__([\s\S]+?)__/ },
  { t: 'strike', re: /^~~([\s\S]+?)~~/ },
  { t: 'spoiler', re: /^\|\|([\s\S]+?)\|\|/ },
  { t: 'italic', re: /^\*(?!\s)([^*\n]+?)\*/ },
  { t: 'italic', re: /^_(?!\s)([^_\n]+?)_(?![A-Za-z0-9])/ },
];

export function parseDiscordInline(input) {
  const s = String(input ?? '');
  const out = [];
  let text = '';
  const push = () => { if (text) { out.push({ t: 'text', v: text }); text = ''; } };
  let i = 0;
  while (i < s.length) {
    const rest = s.slice(i);
    if (rest[0] === '\\' && rest.length > 1) { text += rest[1]; i += 2; continue; }
    let m;
    if ((m = /^`([^`\n]+)`/.exec(rest))) { push(); out.push({ t: 'code', v: m[1] }); i += m[0].length; continue; }
    if ((m = /^<@!?(\d+)>/.exec(rest))) { push(); out.push({ t: 'mention', v: `@user-${m[1].slice(-4)}`, kind: 'user' }); i += m[0].length; continue; }
    if ((m = /^<@&(\d+)>/.exec(rest))) { push(); out.push({ t: 'mention', v: `@role-${m[1].slice(-4)}`, kind: 'role' }); i += m[0].length; continue; }
    if ((m = /^<#(\d+)>/.exec(rest))) { push(); out.push({ t: 'mention', v: `#channel-${m[1].slice(-4)}`, kind: 'channel' }); i += m[0].length; continue; }
    if ((m = /^(@everyone|@here)\b/.exec(rest))) { push(); out.push({ t: 'mention', v: m[1], kind: 'broadcast' }); i += m[0].length; continue; }
    if ((m = /^<a?:(\w+):\d+>/.exec(rest))) { push(); out.push({ t: 'emoji', v: `:${m[1]}:` }); i += m[0].length; continue; }
    if ((m = /^<t:(-?\d+)(?::[tTdDfFR])?>/.exec(rest))) { push(); out.push({ t: 'timestamp', v: 'a date/time shown in each reader\'s local time' }); i += m[0].length; continue; }
    if ((m = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/.exec(rest))) { push(); out.push({ t: 'link', v: m[1], href: m[2] }); i += m[0].length; continue; }
    if ((m = /^https?:\/\/[^\s<>]+/.exec(rest))) { push(); out.push({ t: 'link', v: m[0], href: m[0] }); i += m[0].length; continue; }
    let hit = false;
    for (const rule of DISCORD_INLINE) {
      if ((m = rule.re.exec(rest))) { push(); out.push({ t: rule.t, children: parseDiscordInline(m[1]) }); i += m[0].length; hit = true; break; }
    }
    if (hit) continue;
    text += rest[0]; i += 1;
  }
  push();
  return out;
}

/** Block level: fenced code, quotes, headings, subtext, lists; everything else is a paragraph of inline text. */
export function parseDiscordMarkdown(input) {
  const lines = String(input ?? '').split('\n');
  const blocks = [];
  for (let n = 0; n < lines.length; n += 1) {
    const line = lines[n];
    if (line.startsWith('```')) {
      const close = lines.findIndex((l, k) => k > n && l.includes('```'));
      if (close > -1) {
        const body = lines.slice(n + 1, close).join('\n');
        blocks.push({ t: 'pre', v: body });
        n = close; continue;
      }
    }
    let m;
    if ((m = /^(#{1,3})\s+(.+)/.exec(line))) { blocks.push({ t: 'heading', level: m[1].length, children: parseDiscordInline(m[2]) }); continue; }
    if ((m = /^-#\s+(.+)/.exec(line))) { blocks.push({ t: 'subtext', children: parseDiscordInline(m[1]) }); continue; }
    if ((m = /^>\s?(.*)/.exec(line))) { blocks.push({ t: 'quote', children: parseDiscordInline(m[1]) }); continue; }
    if ((m = /^\s*[-*]\s+(.+)/.exec(line))) { blocks.push({ t: 'li', children: parseDiscordInline(m[1]) }); continue; }
    blocks.push({ t: 'p', children: parseDiscordInline(line) });
  }
  return blocks;
}

// ── Length checks ─────────────────────────────────────────────────────────────
export function lengthNotes(platform, text, { hasMedia = false, kind = 'message', limit: limitOverride } = {}) {
  const len = [...String(text ?? '')].length;
  const notes = [];
  if (platform === 'telegram') {
    const limit = hasMedia ? TELEGRAM_LIMITS.caption : TELEGRAM_LIMITS.text;
    if (len > limit) {
      notes.push(`${len.toLocaleString()} characters: over Telegram's ${limit.toLocaleString()}-character limit for a ${hasMedia ? 'caption' : 'message'}. The bot does not split ${kind}s, so Telegram would reject this one.`);
    }
  } else {
    const limit = limitOverride || DISCORD_LIMITS.content;
    if (len > limit) notes.push(`${len.toLocaleString()} characters: over Discord's ${limit.toLocaleString()}-character limit${limitOverride ? ' for an embed description' : ' for a message'}. Discord would reject this ${kind}.`);
  }
  return { length: len, notes };
}

/** Same join as backend/automation/forwarding_runtime._build_text: non-empty parts, one per line. */
export function buildForwardText(prefix, body, suffix) {
  return [prefix, body, suffix].filter(Boolean).join('\n');
}

// ── Telegram HTML ────────────────────────────────────────────────────────────
// Used by sends with parse_mode=HTML (Echo's replies). Supported tags per the Bot API; anything else
// (or an unclosed tag) makes Telegram reject the message. Returns a tree; text stays text, never markup.
const TG_HTML_TAGS = {
  b: 'bold', strong: 'bold', i: 'italic', em: 'italic', u: 'underline', ins: 'underline',
  s: 'strike', strike: 'strike', del: 'strike', code: 'code', pre: 'pre', a: 'link',
  'tg-spoiler': 'spoiler', blockquote: 'quote',
};
const ENTITIES = { lt: '<', gt: '>', amp: '&', quot: '"' };

export function parseTelegramHtml(input) {
  const src = String(input ?? '');
  const root = { t: 'root', children: [] };
  const stack = [root];
  const warnings = [];
  const re = /<(\/?)([A-Za-z][A-Za-z0-9-]*)([^>]*)>|&(lt|gt|amp|quot);/g;
  let last = 0; let m;
  const top = () => stack[stack.length - 1];
  const addText = (v) => { if (v) top().children.push({ t: 'text', v }); };
  // eslint-disable-next-line no-cond-assign
  while ((m = re.exec(src))) {
    addText(src.slice(last, m.index));
    last = m.index + m[0].length;
    if (m[4]) { addText(ENTITIES[m[4]]); continue; }
    const closing = m[1] === '/'; const name = m[2].toLowerCase();
    const kind = TG_HTML_TAGS[name];
    if (!kind) { warnings.push(`<${name}> is not a tag Telegram supports.`); addText(m[0]); continue; }
    if (!closing) {
      const href = kind === 'link' ? ((/href\s*=\s*["']([^"']+)["']/i.exec(m[3]) || [])[1]) : undefined;
      const node = { t: kind, children: [], name, href };
      top().children.push(node); stack.push(node);
    } else if (stack.length > 1 && top().name === name) {
      stack.pop();
    } else {
      warnings.push(`</${name}> does not match an open tag.`); addText(m[0]);
    }
  }
  addText(src.slice(last));
  if (stack.length > 1) warnings.push(`<${top().name}> is never closed.`);
  const uniq = [...new Set(warnings)];
  if (uniq.length) uniq.unshift("Telegram would reject this text as written (can't parse entities).");
  return { nodes: root.children, warnings: uniq };
}
