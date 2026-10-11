import cases from './fixtures/format_cases.json';
import {
  fillTemplate, parseTelegramMarkdown, parseTelegramHtml, parseDiscordMarkdown, parseDiscordInline, lengthNotes,
} from './previewText';

describe('fillTemplate matches Python str.format for the welcome template', () => {
  cases.cases.forEach(({ template, expected }) => {
    it(`renders ${JSON.stringify(template).slice(0, 40)}`, () => {
      const r = fillTemplate(template, cases.vars, 'python');
      expect(r.unknown).toEqual([]);
      expect(r.text).toBe(expected);
    });
  });
  cases.failing.forEach((template) => {
    it(`flags the placeholder str.format would reject: ${template}`, () => {
      const r = fillTemplate(template, cases.vars, 'python');
      expect(r.unknown).toEqual(['nickname']);
    });
  });
  it('leaves unknown names as written in single-brace mode', () => {
    expect(fillTemplate('Hi {who}', {}, 'single').text).toBe('Hi {who}');
  });
});

describe('Telegram legacy Markdown', () => {
  it('parses bold, italic, code and links', () => {
    const { nodes, warnings } = parseTelegramMarkdown('*b* _i_ `c` [t](https://x.y)');
    expect(warnings).toEqual([]);
    expect(nodes.filter((n) => n.t !== 'text').map((n) => n.t)).toEqual(['bold', 'italic', 'code', 'link']);
  });
  it('warns when a mark is never closed (Telegram rejects the whole message)', () => {
    expect(parseTelegramMarkdown('hello *world').warnings.length).toBeGreaterThan(0);
    expect(parseTelegramMarkdown('user_name is here').warnings.length).toBeGreaterThan(0);
  });
  it('honours backslash escapes', () => {
    const { nodes, warnings } = parseTelegramMarkdown(String.raw`snake\_case`);
    expect(warnings).toEqual([]);
    expect(nodes.map((n) => n.v).join('')).toBe('snake_case');
  });
  it('never turns raw HTML into markup (it stays literal text)', () => {
    const { nodes } = parseTelegramMarkdown('<img src=x onerror=alert(1)>');
    expect(nodes).toEqual([{ t: 'text', v: '<img src=x onerror=alert(1)>' }]);
  });
});

describe('Discord Markdown', () => {
  it('parses emphasis and mentions', () => {
    const kinds = parseDiscordInline('**b** *i* __u__ ~~s~~ <@123456> @everyone').map((n) => n.t).filter((t) => t !== 'text');
    expect(kinds).toEqual(['bold', 'italic', 'underline', 'strike', 'mention', 'mention']);
  });
  it('parses block elements', () => {
    const kinds = parseDiscordMarkdown('# Title\n> quote\n- item\n```\ncode\n```').map((b) => b.t);
    expect(kinds).toEqual(['heading', 'quote', 'li', 'pre']);
  });
});

describe('length notes', () => {
  it('warns over Telegram 4096 / caption 1024 and Discord 2000', () => {
    expect(lengthNotes('telegram', 'x'.repeat(4097)).notes).toHaveLength(1);
    expect(lengthNotes('telegram', 'x'.repeat(1025), { hasMedia: true }).notes).toHaveLength(1);
    expect(lengthNotes('telegram', 'x'.repeat(4096)).notes).toHaveLength(0);
    expect(lengthNotes('discord', 'x'.repeat(2001)).notes).toHaveLength(1);
  });
});

describe('Telegram HTML (Echo replies)', () => {
  it('parses supported tags and keeps text as text', () => {
    const { nodes, warnings } = parseTelegramHtml('<b>Hi</b> &lt;script&gt; <a href="https://x.y">link</a>');
    expect(warnings).toEqual([]);
    expect(nodes[0].t).toBe('bold');
    expect(nodes.filter((n) => n.t === 'text').map((n) => n.v).join('')).toContain('<script>');
    expect(nodes.some((n) => n.t === 'link' && n.href === 'https://x.y')).toBe(true);
  });
  it('warns on unsupported or unclosed tags (Telegram would reject the message)', () => {
    expect(parseTelegramHtml('<div>x</div>').warnings.length).toBeGreaterThan(0);
    expect(parseTelegramHtml('<b>open').warnings.length).toBeGreaterThan(0);
  });
});
