// BotFather tokens look like "123456789:AAH...": a numeric bot id, a colon, then ~35 URL-safe characters.
// This only gives a hint before a network call; the server's check is the real one, so it never blocks.
export function tokenFormatHint(token) {
  const t = (token || '').trim();
  if (!t) return '';
  if (/\s/.test(t)) return 'A token has no spaces. Copy it again from BotFather.';
  if (!t.includes(':')) return 'This does not look like a bot token. It should look like 123456789:AA… (copy it from @BotFather).';
  if (!/^\d{5,}:[A-Za-z0-9_-]{30,}$/.test(t)) return 'This token looks incomplete or has extra characters. Copy the whole line BotFather sent.';
  return '';
}
