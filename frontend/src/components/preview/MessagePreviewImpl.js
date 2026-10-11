import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert, Avatar, Box, Button, Chip, Stack, Typography,
} from '@mui/material';
import {
  SAMPLE_VALUES, fillTemplate, lengthNotes, parseDiscordInline, parseDiscordMarkdown, parseTelegramHtml, parseTelegramMarkdown,
} from './previewText';

// Lightweight "what will members see" preview. Everything here is local: it renders the text the
// editor already holds, with sample values. It never calls a delivery endpoint, never fetches
// media, and nothing in it is clickable (buttons, links and mentions are inert).

const MARK = { varOpen: '', varMid: '', varClose: '', unkOpen: '', unkClose: '' };
const MARK_RE = /([^]*)([^]*)|([^]*)/g;
const stripMarks = (s) => s.replace(MARK_RE, (_m, _n, val, unk) => (unk !== undefined ? `{${unk}}` : val));

function useDebounced(value, ms = 250) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Text with sample values (and unresolved placeholders) visibly marked. */
function Marked({ text }) {
  const parts = [];
  let last = 0; let m; let k = 0;
  MARK_RE.lastIndex = 0;
  // eslint-disable-next-line no-cond-assign
  while ((m = MARK_RE.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[3] !== undefined) {
      parts.push(<Box key={k++} component="span" title={`Unknown placeholder {${m[3]}}`} sx={{ color: 'warning.main', textDecoration: 'underline wavy', textUnderlineOffset: 3 }}>{`{${m[3]}}`}</Box>);
    } else {
      parts.push(<Box key={k++} component="span" title={`Sample value for {${m[1]}}`} sx={{ borderBottom: '1px dotted currentColor' }}>{m[2]}</Box>);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

// ── Telegram ──────────────────────────────────────────────────────────────────
function TelegramText({ nodes }) {
  return nodes.map((n, i) => {
    const key = `n${i}`;
    switch (n.t) {
      case 'bold': return <strong key={key}><Marked text={n.v} /></strong>;
      case 'italic': return <em key={key}><Marked text={n.v} /></em>;
      case 'code': return <Box key={key} component="code" sx={{ fontFamily: 'monospace', bgcolor: 'rgba(255,255,255,0.08)', px: 0.5, borderRadius: 0.5 }}><Marked text={n.v} /></Box>;
      case 'pre': return <Box key={key} component="pre" sx={{ m: 0, my: 0.5, p: 1, fontFamily: 'monospace', fontSize: 13, bgcolor: 'rgba(0,0,0,0.25)', borderRadius: 1, whiteSpace: 'pre-wrap' }}><Marked text={n.v} /></Box>;
      case 'link': return <Box key={key} component="span" title={n.href} sx={{ color: '#6ab3f3' }}><Marked text={n.v} /></Box>;
      default: return <Marked key={key} text={n.v} />;
    }
  });
}

function TelegramHtml({ nodes }) {
  return nodes.map((n, i) => {
    const key = `h${i}`;
    if (n.t === 'text') return <Marked key={key} text={n.v} />;
    const kids = <TelegramHtml nodes={n.children || []} />;
    switch (n.t) {
      case 'bold': return <strong key={key}>{kids}</strong>;
      case 'italic': return <em key={key}>{kids}</em>;
      case 'underline': return <u key={key}>{kids}</u>;
      case 'strike': return <s key={key}>{kids}</s>;
      case 'code': return <Box key={key} component="code" sx={{ fontFamily: 'monospace', bgcolor: 'rgba(255,255,255,0.08)', px: 0.5, borderRadius: 0.5 }}>{kids}</Box>;
      case 'pre': return <Box key={key} component="pre" sx={{ m: 0, my: 0.5, p: 1, fontFamily: 'monospace', fontSize: 13, bgcolor: 'rgba(0,0,0,0.25)', borderRadius: 1, whiteSpace: 'pre-wrap' }}>{kids}</Box>;
      case 'link': return <Box key={key} component="span" title={n.href} sx={{ color: '#6ab3f3' }}>{kids}</Box>;
      case 'spoiler': return <Box key={key} component="span" title="Spoiler" sx={{ bgcolor: '#3a4a5c', color: '#3a4a5c', borderRadius: 0.5 }}>{kids}</Box>;
      case 'quote': return <Box key={key} sx={{ borderLeft: '3px solid #6ab3f3', pl: 1, my: 0.25 }}>{kids}</Box>;
      default: return kids;
    }
  });
}

function TelegramBubble({ text, plain, html, buttons, media, botName, linkPreview, replyTo }) {
  const parsed = useMemo(() => (plain ? { nodes: [{ t: 'text', v: text }], warnings: [] } : html ? parseTelegramHtml(text) : parseTelegramMarkdown(text)), [text, plain, html]);
  return (
    <Box sx={{ bgcolor: '#0e1621', borderRadius: 2, p: 1.5 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
        <Avatar sx={{ width: 30, height: 30, bgcolor: 'primary.main', fontSize: 13 }}>{(botName || 'B')[0].toUpperCase()}</Avatar>
        <Box sx={{ maxWidth: 440, width: '100%', bgcolor: '#182533', color: '#e8edf5', borderRadius: '14px 14px 14px 4px', overflow: 'hidden' }}>
          {media && (
            <Box sx={{ bgcolor: '#223347', color: '#9fb3c8', px: 1.5, py: 3, textAlign: 'center', fontSize: 13 }}>
              {media.kind || 'Media'} attached{media.label ? `: ${media.label}` : ''} (not loaded in this preview)
            </Box>
          )}
          <Box sx={{ px: 1.75, py: 1.25 }}>
            <Typography variant="caption" sx={{ color: '#6ab3f3', fontWeight: 700, display: 'block' }}>{botName || 'Bot'}</Typography>
            {replyTo && (
              <Box sx={{ borderLeft: '2px solid #6ab3f3', pl: 1, mb: 0.5, fontSize: 12.5, color: '#9fb3c8' }}>
                <strong>{replyTo.author}</strong><br />{replyTo.text}
              </Box>
            )}
            <Box sx={{ fontSize: 14.5, lineHeight: 1.45, wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>
              {text ? (html && !plain ? <TelegramHtml nodes={parsed.nodes} /> : <TelegramText nodes={parsed.nodes} />) : <Box component="span" sx={{ color: '#7f91a4' }}>Nothing to show yet.</Box>}
            </Box>
            {linkPreview === false && <Typography variant="caption" sx={{ color: '#7f91a4', display: 'block', mt: 0.5 }}>Link previews are turned off for this message.</Typography>}
          </Box>
        </Box>
      </Box>
      {buttons?.length > 0 && (
        <Box sx={{ mt: 0.75, ml: 5, display: 'grid', gap: 0.5, maxWidth: 440 }} aria-hidden="true">
          {buttons.map((row, ri) => (
            <Box key={ri} sx={{ display: 'flex', gap: 0.5 }}>
              {row.map((b, bi) => (
                <Box key={bi} sx={{ flex: 1, textAlign: 'center', bgcolor: 'rgba(106,179,243,0.18)', color: '#6ab3f3', borderRadius: 1.5, py: 0.6, fontSize: 13, pointerEvents: 'none', userSelect: 'none' }}>{b.text}</Box>
              ))}
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}

// ── Discord ───────────────────────────────────────────────────────────────────
function DiscordInline({ nodes }) {
  return nodes.map((n, i) => {
    const key = `d${i}`;
    const kids = n.children ? <DiscordInline nodes={n.children} /> : null;
    switch (n.t) {
      case 'bold': return <strong key={key}>{kids}</strong>;
      case 'italic': return <em key={key}>{kids}</em>;
      case 'bolditalic': return <strong key={key}><em>{kids}</em></strong>;
      case 'underline': return <u key={key}>{kids}</u>;
      case 'strike': return <s key={key}>{kids}</s>;
      case 'spoiler': return <Box key={key} component="span" title="Spoiler (hidden until clicked in Discord)" sx={{ bgcolor: '#1e1f22', color: '#1e1f22', borderRadius: 0.5, px: 0.25 }}>{kids}</Box>;
      case 'code': return <Box key={key} component="code" sx={{ fontFamily: 'monospace', bgcolor: '#2b2d31', px: 0.5, borderRadius: 0.5, fontSize: 13 }}><Marked text={n.v} /></Box>;
      case 'mention': return <Box key={key} component="span" sx={{ bgcolor: 'rgba(88,101,242,0.3)', color: '#c9cdfb', borderRadius: 0.5, px: 0.5 }}>{n.v}</Box>;
      case 'emoji': return <Box key={key} component="span" title="Custom emoji">{n.v}</Box>;
      case 'timestamp': return <Box key={key} component="span" sx={{ bgcolor: '#2b2d31', borderRadius: 0.5, px: 0.5 }}>{n.v}</Box>;
      case 'link': return <Box key={key} component="span" title={n.href} sx={{ color: '#00a8fc' }}><Marked text={n.v} /></Box>;
      default: return <Marked key={key} text={n.v} />;
    }
  });
}

function DiscordBubble({ text, buttons, embed, botName, replyTo }) {
  const blocks = useMemo(() => parseDiscordMarkdown(text), [text]);
  return (
    <Box sx={{ bgcolor: '#313338', color: '#dbdee1', borderRadius: 2, p: 1.5, display: 'flex', gap: 1.5 }}>
      <Avatar sx={{ width: 36, height: 36, bgcolor: '#5865f2', fontSize: 15 }}>{(botName || 'B')[0].toUpperCase()}</Avatar>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        {replyTo && (
          <Box sx={{ fontSize: 12.5, color: '#949ba4', mb: 0.25, borderLeft: '2px solid #4e5058', pl: 1 }}>
            Replying to <strong>{replyTo.author}</strong>: {replyTo.text}
          </Box>
        )}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.25 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, color: '#f2f3f5' }}>{botName || 'Bot'}</Typography>
          <Box component="span" sx={{ bgcolor: '#5865f2', color: '#fff', fontSize: 10, fontWeight: 700, px: 0.5, borderRadius: 0.5 }}>APP</Box>
        </Box>
        <Box sx={{ fontSize: 15, lineHeight: 1.4, wordBreak: 'break-word' }}>
          {text ? blocks.map((b, i) => {
            const key = `b${i}`;
            if (b.t === 'pre') return <Box key={key} component="pre" sx={{ m: 0, my: 0.5, p: 1, fontFamily: 'monospace', fontSize: 13, bgcolor: '#2b2d31', border: '1px solid #1e1f22', borderRadius: 1, whiteSpace: 'pre-wrap' }}><Marked text={b.v} /></Box>;
            if (b.t === 'heading') return <Box key={key} sx={{ fontWeight: 700, fontSize: b.level === 1 ? 24 : b.level === 2 ? 20 : 17, my: 0.5 }}><DiscordInline nodes={b.children} /></Box>;
            if (b.t === 'subtext') return <Box key={key} sx={{ fontSize: 12, color: '#949ba4' }}><DiscordInline nodes={b.children} /></Box>;
            if (b.t === 'quote') return <Box key={key} sx={{ borderLeft: '4px solid #4e5058', pl: 1 }}><DiscordInline nodes={b.children} /></Box>;
            if (b.t === 'li') return <Box key={key} sx={{ display: 'flex', gap: 1, pl: 1 }}><span>•</span><span><DiscordInline nodes={b.children} /></span></Box>;
            return <Box key={key} sx={{ minHeight: '1.4em', whiteSpace: 'pre-wrap' }}><DiscordInline nodes={b.children} /></Box>;
          }) : <Box component="span" sx={{ color: '#949ba4' }}>Nothing to show yet.</Box>}
        </Box>
        {embed && (
          <Box sx={{ mt: 0.75, maxWidth: 420, bgcolor: '#2b2d31', borderLeft: `4px solid ${embed.color || '#5865f2'}`, borderRadius: 1, p: 1.25 }}>
            {embed.author && <Typography variant="caption" sx={{ fontWeight: 700, color: '#f2f3f5', display: 'block', mb: 0.25 }}>{embed.author}</Typography>}
            {embed.title && <Typography variant="body2" sx={{ fontWeight: 700, color: '#f2f3f5' }}><Marked text={embed.title} /></Typography>}
            {embed.description && <Box sx={{ fontSize: 14, whiteSpace: 'pre-wrap' }}><DiscordInline nodes={parseDiscordMarkdown(embed.description).flatMap((x) => x.children || [{ t: 'text', v: x.v }])} /></Box>}
            {(embed.fields || []).map((f) => (
              <Box key={f.name} sx={{ mt: 0.75 }}>
                <Typography variant="caption" sx={{ fontWeight: 700, color: '#f2f3f5', display: 'block' }}>{f.name}</Typography>
                <Box sx={{ fontSize: 13.5, whiteSpace: 'pre-wrap' }}><DiscordInline nodes={parseDiscordInline(f.value)} /></Box>
              </Box>
            ))}
            {embed.imageLabel && <Box sx={{ mt: 1, bgcolor: '#1e1f22', color: '#949ba4', borderRadius: 1, py: 2.5, textAlign: 'center', fontSize: 12.5 }}>Image: {embed.imageLabel} (not loaded in this preview)</Box>}
            {embed.footer && <Typography variant="caption" sx={{ color: '#949ba4', display: 'block', mt: 0.5 }}>{embed.footer}</Typography>}
          </Box>
        )}
        {buttons?.length > 0 && (
          <Box sx={{ mt: 0.75, display: 'flex', gap: 0.75, flexWrap: 'wrap' }} aria-hidden="true">
            {buttons.flat().map((b, i) => (
              <Box key={i} sx={{ bgcolor: '#4e5058', color: '#fff', borderRadius: 1, px: 1.5, py: 0.5, fontSize: 13.5, pointerEvents: 'none', userSelect: 'none' }}>{b.text}</Box>
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
}

// ── Public component ──────────────────────────────────────────────────────────
/**
 * @param platform  'telegram' | 'discord'
 * @param text      the template/text exactly as it is stored
 * @param syntax    placeholder syntax: 'python' (str.format), 'single' ({name}, unknown left as is), or 'none' (no templating)
 * @param vars      sample values (defaults to the shared invented SAMPLE_VALUES)
 * @param plain     Telegram only: the message is sent with no parse_mode
 * @param buttons   [[{ text }]]  (inert)   media: { kind, label }   embed: Discord embed {title, description, color, footer}
 * @param sample    true when `text` is an AI-generated example, not authored content
 */
export function MessagePreview({
  platform = 'telegram', text, syntax = 'python', vars = SAMPLE_VALUES, plain = false, buttons, media, embed,
  botName = 'Telegizer', destination, linkPreview, kind = 'message', sample = false, notes = [], replyTo, fallbackToPlain = false, html = false, maxLength,
}) {
  const debounced = useDebounced(text);
  const [showSource, setShowSource] = useState(false);
  const prepared = useMemo(() => {
    if (syntax === 'none') return { marked: String(debounced ?? ''), unknown: [], plainText: String(debounced ?? '') };
    const { segments, unknown } = fillTemplate(debounced, vars, syntax);
    const marked = segments.map((s) => {
      if (s.type === 'var') return `${MARK.varOpen}${s.name}${MARK.varMid}${s.text}${MARK.varClose}`;
      if (s.type === 'unknown') return `${MARK.unkOpen}${s.name}${MARK.unkClose}`;
      return s.text;
    }).join('');
    return { marked, unknown, plainText: segments.map((s) => s.text).join('') };
  }, [debounced, syntax, vars]);

  const parseWarnings = useMemo(
    () => (platform === 'telegram' && !plain ? (html ? parseTelegramHtml(stripMarks(prepared.marked)) : parseTelegramMarkdown(stripMarks(prepared.marked))).warnings : []),
    [platform, plain, html, prepared.marked],
  );
  const len = lengthNotes(platform, prepared.plainText, { hasMedia: !!media, kind, limit: maxLength });
  // Some sends retry as plain text when Telegram rejects the formatting (e.g. the auto knowledge reply).
  const fellBack = fallbackToPlain && parseWarnings.length > 0;
  const warnings = fellBack ? [
    'Telegram rejects this formatting, so the bot sends the reply as plain text instead (shown below).',
    ...len.notes, ...notes,
  ] : [
    ...(prepared.unknown.length ? [`Unknown placeholder${prepared.unknown.length > 1 ? 's' : ''} ${prepared.unknown.map((n) => `{${n}}`).join(', ')}: ${syntax === 'python' ? 'the bot cannot fill these in, so this message would fail to send' : 'these are posted as written'}.`] : []),
    ...parseWarnings, ...len.notes, ...notes,
  ];

  return (
    <Box data-testid="message-preview">
      <Stack direction="row" spacing={0.75} alignItems="center" useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
        <Chip size="small" color="warning" variant="outlined" label="Preview — not sent" />
        <Chip size="small" variant="outlined" label={platform === 'telegram' ? 'Telegram' : 'Discord'} />
        {destination && <Typography variant="caption" color="text.secondary">{destination}</Typography>}
        {sample && <Chip size="small" color="info" label="AI sample" />}
      </Stack>
      {platform === 'telegram'
        ? <TelegramBubble text={prepared.marked} plain={plain || fellBack} html={html} buttons={buttons} media={media} botName={botName} linkPreview={linkPreview} replyTo={replyTo} />
        : <DiscordBubble text={prepared.marked} buttons={buttons} embed={embed} botName={botName} replyTo={replyTo} />}
      {warnings.map((w) => <Alert key={w} severity="warning" sx={{ mt: 1, py: 0 }}>{w}</Alert>)}
      {text ? (
        <Box sx={{ mt: 0.75 }}>
          <Button size="small" onClick={() => setShowSource((v) => !v)} aria-expanded={showSource} sx={{ textTransform: 'none', minHeight: 0, py: 0 }}>
            {showSource ? 'Hide source text' : 'Show source text'}
          </Button>
          {showSource && (
            <Box component="pre" sx={{ m: 0, mt: 0.5, p: 1, borderRadius: 1, bgcolor: 'action.hover', fontSize: 12.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{String(debounced ?? '')}</Box>
          )}
        </Box>
      ) : null}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
        {len.length.toLocaleString()} characters.{' '}
        {syntax !== 'none' && 'Underlined values are samples, not real member data. '}
        Buttons, links and mentions are not clickable here. The final look can differ slightly between apps and devices.
      </Typography>
    </Box>
  );
}

export default MessagePreview;
