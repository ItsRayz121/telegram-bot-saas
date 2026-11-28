import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Box, Typography, Button, Stack, Container } from '@mui/material';
import { ArrowForward, Telegram, Pause, PlayArrow, Tag, Forum, SmartToy } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import PlatformSwitcher from '../PlatformSwitcher';
import Sticker from './Stickers';
import { PALETTE, FONT_MONO } from '../../theme';

// Story-driven hero shared by the Telegizer, Guildizer and Echo landing pages.
// The script lives in stories.js; this file plays it. Chapters advance on a timer, pause when the hero
// is off screen, the tab is hidden, the pointer rests on the chat, or the visitor presses pause.
// Reduced-motion visitors get each chapter fully drawn, no autoplay, and step through it themselves.

const mono = { fontFamily: FONT_MONO, fontVariantNumeric: 'tabular-nums', letterSpacing: 0 };
const IS_PRERENDER = typeof window === 'undefined';
const TICK = 100;

const SKIN = {
  telegram: { accent: PALETTE.blue, accentLt: PALETTE.blueLt, botIcon: Telegram },
  discord: { accent: '#5865F2', accentLt: '#a5adff', botIcon: Forum },
  echo: { accent: PALETTE.purple, accentLt: PALETTE.purpleLt, botIcon: SmartToy },
};

// The visitor's own white-label bot gets its own colour so it reads as "not us".
const OWN = { bg: '#c98a2b', fg: '#1a1206', name: '#f0c27a' };

const TONE = {
  calm: { frame: PALETTE.border2, glow: 'transparent' },
  alarm: { frame: '#5a2a2d', glow: 'rgba(235,82,87,0.10)' },
  safe: { frame: PALETTE.border2, glow: 'transparent' },
};

function prefersReducedMotion() {
  return !IS_PRERENDER && !!window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// Builds what the chat shows at `elapsed` ms into a chapter: visible rows, struck-out ids, member count.
function useFrame(story, sceneIdx, elapsed) {
  return useMemo(() => {
    let members = story.members;
    // Earlier chapters' member changes carry forward only inside the same act
    // ("without" and "with" are two versions of the same five minutes).
    const scene = story.scenes[sceneIdx];
    story.scenes.slice(0, sceneIdx).forEach((s) => {
      if (s.act && s.act !== scene.act) return;
      s.events.forEach((e) => { if (e.type === 'members' && members != null) members += e.delta; });
    });
    const removed = {};
    const rows = [];
    let stamp = null;
    scene.events.forEach((e, i) => {
      if (e.t > elapsed) return;
      if (e.type === 'remove') removed[e.target] = e.reason;
      else if (e.type === 'members') { if (members != null) members += e.delta; }
      else if (e.type === 'stamp') { if (elapsed < e.t + e.dur) stamp = { ...e, key: `${scene.key}-${i}` }; }
      else rows.push({ ...e, key: `${scene.key}-${i}` });
    });
    return { rows, removed, members, stamp };
  }, [story, sceneIdx, elapsed]);
}

// ── Chat pieces ──────────────────────────────────────────────────────────────

function Avatar({ name, bot, own, skin, size = 28 }) {
  const s = SKIN[skin];
  const Icon = s.botIcon;
  if (own) {
    return (
      <Box sx={{ width: size, height: size, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center', bgcolor: OWN.bg, color: OWN.fg, fontSize: size * 0.36, fontWeight: 700 }}>
        {own}
      </Box>
    );
  }
  return (
    <Box sx={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center',
      bgcolor: bot ? s.accent : PALETTE.bg4, color: bot ? '#0f1012' : 'text.secondary', fontSize: 12, fontWeight: 600,
    }}>
      {bot ? <Icon sx={{ fontSize: size * 0.56 }} /> : (name || '?')[0].toUpperCase()}
    </Box>
  );
}

function RemovedNote({ reason }) {
  return (
    <Typography className="st-removed" sx={{ ...mono, fontSize: 11, color: PALETTE.red, mt: 0.5 }}>
      removed · {reason}
    </Typography>
  );
}

// Body of a message, shared by every skin. Handles the blurred image, forwards and the strike-out.
function Body({ row, removed, skin }) {
  const struck = !!removed;
  return (
    <Box sx={{ position: 'relative', opacity: struck ? 0.5 : 1, transition: 'opacity 0.3s ease' }}>
      {row.type === 'fwd' && skin !== 'echo' && (
        <Typography sx={{ fontSize: 11.5, color: SKIN[skin].accentLt, mb: 0.25 }}>Forwarded from {row.from}</Typography>
      )}
      {row.type === 'media' ? (
        <Box sx={{
          width: { xs: 168, sm: 196 }, height: { xs: 92, sm: 108 }, borderRadius: '8px', position: 'relative', overflow: 'hidden',
          background: 'radial-gradient(circle at 30% 40%, #8a5a4f 0, #5b3a3a 35%, #2c2224 70%), #2c2224',
        }}>
          <Box sx={{ position: 'absolute', inset: 0, backdropFilter: 'blur(14px)', bgcolor: 'rgba(15,16,18,0.35)', display: 'grid', placeItems: 'center' }}>
            <Typography sx={{ ...mono, fontSize: 11, color: '#f3d7d7', px: 1, py: 0.25, borderRadius: '4px', bgcolor: 'rgba(15,16,18,0.6)' }}>
              18+ · {row.label}
            </Typography>
          </Box>
        </Box>
      ) : (
        <Typography component="div" sx={{ fontSize: { xs: 13, sm: 14 }, lineHeight: 1.45, color: 'text.primary', overflowWrap: 'anywhere' }}>
          {row.text}
        </Typography>
      )}
      {struck && (
        <Box className="st-strike" sx={{
          position: 'absolute', left: 0, right: 0, top: row.type === 'media' ? '50%' : '58%', height: '1.5px',
          bgcolor: PALETTE.red, transformOrigin: 'left center',
        }} />
      )}
    </Box>
  );
}

function BotTag({ children, skin, own }) {
  if (!children) return null;
  return (
    <Typography component="span" sx={{ ...mono, fontSize: 10.5, color: own ? OWN.name : SKIN[skin].accentLt, border: `1px solid ${own ? OWN.bg : SKIN[skin].accent}55`, borderRadius: '4px', px: 0.5, ml: 0.75, lineHeight: 1.5 }}>
      {children}
    </Typography>
  );
}

// Who a row is from: the product bot, the visitor's own bot, or a member.
function who(row, story) {
  const bot = row.type === 'bot' || (row.type === 'sticker' && !!row.own);
  const own = row.own && story.ownBot ? story.ownBot : null;
  return { bot, own: own ? own.avatar : null, name: own ? own.name : bot ? story.botName : row.name };
}

function NameLine({ row, story, skin }) {
  const { bot, own, name } = who(row, story);
  return (
    <Typography component="div" sx={{ fontSize: 12, fontWeight: 500, color: own ? OWN.name : bot ? SKIN[skin].accentLt : 'text.secondary', mb: 0.25, display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
      {name}
      {row.role && <Box component="span" sx={{ ...mono, fontSize: 10.5, color: PALETTE.green, ml: 0.75 }}>{row.role}</Box>}
      {bot && <BotTag skin={skin} own={!!own}>{row.tag}</BotTag>}
    </Typography>
  );
}

// A sticker message: the art itself, no bubble, the way Telegram and Discord show stickers.
function StickerMsg({ row, story }) {
  const { bot, own, name } = who(row, story);
  const discord = story.skin === 'discord';
  return (
    <Box sx={{ display: 'flex', gap: discord ? 1.5 : 1.25, alignItems: discord ? 'flex-start' : 'flex-end' }}>
      <Avatar name={name} bot={bot} own={own} skin={story.skin} size={discord ? 32 : 28} />
      <Box>
        {discord && <NameLine row={row} story={story} skin="discord" />}
        <Box sx={{ width: { xs: 84, sm: 100 }, '& svg': { width: '100%', height: 'auto' } }}>
          <Sticker art={row.art} />
        </Box>
      </Box>
    </Box>
  );
}

// The big overlay for a dramatic beat: bot raid, too late, on duty.
function Stamp({ stamp, playing }) {
  const red = stamp.art !== 'shield';
  const run = playing ? 'running' : 'paused';
  return (
    <Box sx={{
      position: 'absolute', inset: 0, zIndex: 2, display: 'grid', placeItems: 'center', pointerEvents: 'none',
      bgcolor: red ? 'rgba(40,10,12,0.6)' : 'rgba(10,22,36,0.6)', backdropFilter: 'blur(2px)',
      animation: `stStampBg ${stamp.dur}ms ease both`, animationPlayState: run,
      '@keyframes stStampBg': { '0%': { opacity: 0 }, '10%': { opacity: 1 }, '82%': { opacity: 1 }, '100%': { opacity: 0 } },
    }}>
      <Box sx={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1.5,
        animation: `${red ? 'stStampShake' : 'stStampPop'} ${stamp.dur}ms cubic-bezier(0.22,1,0.36,1) both`, animationPlayState: run,
        '@keyframes stStampPop': { '0%': { transform: 'scale(0.5)' }, '14%': { transform: 'scale(1.08)' }, '22%': { transform: 'scale(1)' }, '100%': { transform: 'scale(1)' } },
        '@keyframes stStampShake': {
          '0%': { transform: 'scale(0.5) rotate(0)' }, '12%': { transform: 'scale(1.1) rotate(-6deg)' }, '18%': { transform: 'scale(1) rotate(5deg)' },
          '24%': { transform: 'rotate(-3deg)' }, '30%': { transform: 'rotate(0)' }, '100%': { transform: 'rotate(0)' },
        },
      }}>
        <Box sx={{ width: { xs: 120, sm: 150 }, '& svg': { width: '100%', height: 'auto' } }}><Sticker art={stamp.art} /></Box>
        <Typography sx={{ fontSize: { xs: 22, sm: 26 }, fontWeight: 600, letterSpacing: '-0.02em', color: red ? '#ffd9da' : '#d9ecff', textShadow: '0 2px 12px rgba(0,0,0,0.5)' }}>
          {stamp.text}
        </Typography>
      </Box>
    </Box>
  );
}

function TelegramMsg({ row, removed, story }) {
  const { bot, own, name } = who(row, story);
  return (
    <Box sx={{ display: 'flex', gap: 1.25, alignItems: 'flex-end' }}>
      <Avatar name={name} bot={bot} own={own} skin="telegram" />
      <Box sx={{ maxWidth: { xs: 'calc(100% - 40px)', sm: 340 }, px: 1.5, py: 1, bgcolor: PALETTE.bg3, borderRadius: '12px 12px 12px 4px', border: `1px solid ${own ? '#5a4220' : PALETTE.border1}` }}>
        <NameLine row={row} story={story} skin="telegram" />
        <Body row={row} removed={removed} skin="telegram" />
        {removed && <RemovedNote reason={removed} />}
      </Box>
    </Box>
  );
}

function DiscordMsg({ row, removed, story }) {
  const { bot, own, name } = who(row, story);
  return (
    <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
      <Avatar name={name} bot={bot} own={own} skin="discord" size={32} />
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.25, flexWrap: 'wrap' }}>
          <Typography sx={{ fontSize: 13.5, fontWeight: 500, color: own ? OWN.name : bot ? '#a5adff' : row.role ? PALETTE.green : 'text.primary' }}>{name}</Typography>
          {bot && <Typography component="span" sx={{ fontSize: 10, fontWeight: 600, bgcolor: own ? OWN.bg : '#5865F2', color: own ? OWN.fg : '#fff', borderRadius: '3px', px: 0.5, lineHeight: 1.6 }}>APP</Typography>}
          {row.role && <Typography component="span" sx={{ ...mono, fontSize: 10.5, color: PALETTE.green }}>{row.role}</Typography>}
          {bot && row.tag && <BotTag skin="discord" own={!!own}>{row.tag}</BotTag>}
        </Box>
        <Body row={row} removed={removed} skin="discord" />
        {removed && <RemovedNote reason={removed} />}
      </Box>
    </Box>
  );
}

function EchoMsg({ row, removed, story }) {
  if (row.type === 'me') {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Box sx={{ maxWidth: '82%', px: 1.5, py: 1, bgcolor: '#1d3b38', borderRadius: '12px 12px 4px 12px', border: '1px solid #2a524d' }}>
          <Typography sx={{ fontSize: { xs: 13, sm: 14 }, lineHeight: 1.45, overflowWrap: 'anywhere' }}>{row.text}</Typography>
        </Box>
      </Box>
    );
  }
  if (row.type === 'fwd') {
    // Incoming pings from other chats, shown as notifications piling up.
    return (
      <Box sx={{ display: 'flex', gap: 1.25, alignItems: 'center', px: 1.25, py: 1, borderRadius: '10px', bgcolor: PALETTE.bg3, border: `1px solid ${PALETTE.border1}` }}>
        <Avatar name={row.from} skin="echo" size={26} />
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: 12, fontWeight: 500, color: 'text.secondary' }}>{row.from}</Typography>
          <Typography noWrap sx={{ fontSize: 13, color: 'text.primary' }}>{row.text}</Typography>
        </Box>
      </Box>
    );
  }
  return <TelegramLikeBot row={row} removed={removed} story={story} />;
}

function TelegramLikeBot({ row, removed, story }) {
  return (
    <Box sx={{ display: 'flex', gap: 1.25, alignItems: 'flex-end' }}>
      <Avatar name={story.botName} bot skin="echo" />
      <Box sx={{ maxWidth: '82%', px: 1.5, py: 1, bgcolor: PALETTE.bg3, borderRadius: '12px 12px 12px 4px', border: `1px solid ${PALETTE.border1}` }}>
        <Typography sx={{ fontSize: 12, fontWeight: 500, color: PALETTE.purpleLt, mb: 0.25, display: 'flex', alignItems: 'center' }}>
          {story.botName}<BotTag skin="echo">{row.tag}</BotTag>
        </Typography>
        <Body row={row} removed={removed} skin="echo" />
      </Box>
    </Box>
  );
}

function ServiceLine({ row }) {
  const color = row.tone === 'red' ? PALETTE.red : row.tone === 'green' ? PALETTE.green : 'text.secondary';
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center' }}>
      <Typography sx={{ ...mono, fontSize: { xs: 11, sm: 12 }, color, px: 1.25, py: 0.5, borderRadius: '6px', bgcolor: 'rgba(236,236,238,0.04)', textAlign: 'center' }}>
        {row.text}
      </Typography>
    </Box>
  );
}

// ── Cards ────────────────────────────────────────────────────────────────────

function CardShell({ children, tone, skin }) {
  const border = tone === 'red' ? '#5a2a2d' : tone === 'own' ? '#6b4d22' : tone === 'accent' ? `${SKIN[skin].accent}66` : PALETTE.border2;
  return (
    <Box sx={{ ml: skin === 'discord' ? 5.5 : 4.75, mr: { xs: 0, sm: 2 }, p: 1.75, borderRadius: '12px', bgcolor: tone === 'red' ? '#1d1416' : PALETTE.bg1, border: `1px solid ${border}` }}>
      {children}
    </Box>
  );
}

function FigureGrid({ rows, cols, color }) {
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 1.5 }}>
      {rows.map(([n, label]) => (
        <Box key={label}>
          <Typography data-figure sx={{ fontSize: { xs: 18, sm: 20 }, fontWeight: 500, lineHeight: 1.15, color: color || 'text.primary', fontVariantNumeric: 'tabular-nums' }}>{n}</Typography>
          <Typography sx={{ fontSize: 11.5, color: 'text.secondary', lineHeight: 1.3, mt: 0.25 }}>{label}</Typography>
        </Box>
      ))}
    </Box>
  );
}

function StoryCard({ row, skin, story }) {
  const s = SKIN[skin];
  switch (row.card) {
    case 'cost':
      return (
        <CardShell tone="red" skin={skin}>
          <Typography sx={{ fontSize: 13, fontWeight: 500, color: '#f3b4b6', mb: 1.25 }}>{row.title || 'Five minutes later'}</Typography>
          <FigureGrid rows={row.rows} cols={3} color={PALETTE.red} />
        </CardShell>
      );
    case 'verify':
      return (
        <CardShell tone="accent" skin={skin}>
          <Typography sx={{ fontSize: 12, fontWeight: 500, color: s.accentLt, mb: 0.5 }}>{story.botName}</Typography>
          <Typography sx={{ fontSize: 13.5, mb: 1.25 }}>
            {row.roles ? `${row.who}, confirm you are human, then pick your roles.` : `${row.who}, tap below to confirm you are human.`}
          </Typography>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Box className="st-press" sx={{ fontSize: 13, fontWeight: 500, px: 1.5, py: 0.6, borderRadius: '8px', bgcolor: s.accent, color: '#0f1012' }}>I’m human</Box>
            {row.roles && ['Builder', 'Trader', 'Artist'].map((r, i) => (
              <Box key={r} sx={{ fontSize: 13, px: 1.25, py: 0.6, borderRadius: '8px', border: `1px solid ${i === 0 ? s.accent : PALETTE.border2}`, color: i === 0 ? s.accentLt : 'text.secondary' }}>{r}</Box>
            ))}
          </Stack>
        </CardShell>
      );
    case 'campaign': {
      const pct = Math.round((row.done / row.total) * 100);
      return (
        <CardShell tone="accent" skin={skin}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 1, mb: 1 }}>
            <Typography sx={{ fontSize: 13.5, fontWeight: 500 }}>{row.title}</Typography>
            <Typography sx={{ ...mono, fontSize: 12, color: s.accentLt, whiteSpace: 'nowrap' }}>{row.reward}</Typography>
          </Box>
          <Box sx={{ height: 4, borderRadius: 2, bgcolor: 'rgba(236,236,238,0.08)', mb: 0.75 }}>
            <Box className="st-bar" sx={{ height: 4, borderRadius: 2, width: `${pct}%`, bgcolor: s.accent, transformOrigin: 'left center' }} />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1 }}>
            <Typography sx={{ ...mono, fontSize: 11.5, color: 'text.disabled' }}>
              {row.button ? row.ends : `${row.done}/${row.total} joined · ${row.ends}`}
            </Typography>
            <Box sx={{ fontSize: 12.5, fontWeight: 500, px: 1.25, py: 0.4, borderRadius: '7px', border: `1px solid ${s.accent}`, color: s.accentLt, whiteSpace: 'nowrap' }}>
              {row.button || 'Join task'}
            </Box>
          </Box>
        </CardShell>
      );
    }
    case 'proof':
      return (
        <CardShell skin={skin}>
          <Typography sx={{ fontSize: 12, fontWeight: 500, color: 'text.secondary', mb: 0.75 }}>{row.who} submitted proof</Typography>
          <Stack spacing={0.5}>
            <Typography sx={{ ...mono, fontSize: 12, color: s.accentLt, overflowWrap: 'anywhere' }}>{row.link}</Typography>
            <Typography sx={{ ...mono, fontSize: 12, color: 'text.secondary' }}>wallet {row.wallet}</Typography>
          </Stack>
          <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, mt: 1.25, px: 1, py: 0.25, borderRadius: '6px', bgcolor: 'rgba(76,195,138,0.12)' }}>
            <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: PALETTE.green }} />
            <Typography sx={{ ...mono, fontSize: 11.5, color: PALETTE.green }}>checked automatically</Typography>
          </Box>
        </CardShell>
      );
    case 'setup':
      return (
        <CardShell tone="own" skin={skin}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 1, mb: 1.25 }}>
            <Typography sx={{ fontSize: 13.5, fontWeight: 500 }}>New custom bot</Typography>
            <Typography sx={{ ...mono, fontSize: 12, color: OWN.name, whiteSpace: 'nowrap' }}>done in {row.time}</Typography>
          </Box>
          <Stack spacing={0.9}>
            {row.steps.map((step, i) => (
              <Box key={step} className="st-step" sx={{ display: 'flex', alignItems: 'center', gap: 1, '--st-delay': `${0.3 + i * 0.45}s` }}>
                <Box sx={{ width: 18, height: 18, borderRadius: '50%', display: 'grid', placeItems: 'center', bgcolor: 'rgba(76,195,138,0.15)', color: PALETTE.green, fontSize: 12, fontWeight: 700 }}>✓</Box>
                <Typography sx={{ fontSize: 13 }}>{step}</Typography>
              </Box>
            ))}
          </Stack>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1.5, pt: 1.25, borderTop: `1px solid ${PALETTE.border1}`, flexWrap: 'wrap' }}>
            <Avatar own={story.ownBot?.avatar} skin={skin} size={26} />
            <Typography sx={{ fontSize: 13, fontWeight: 500, color: OWN.name }}>{story.ownBot?.name}</Typography>
            <Typography sx={{ ...mono, fontSize: 11.5, color: 'text.disabled' }}>your name, your picture</Typography>
          </Box>
        </CardShell>
      );
    case 'leaderboard':
      return (
        <CardShell skin={skin}>
          <Typography sx={{ fontSize: 12.5, fontWeight: 500, mb: 1 }}>This week’s leaderboard</Typography>
          <Stack spacing={0.6}>
            {row.rows.map(([n, xp], i) => (
              <Box key={n} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography sx={{ ...mono, fontSize: 12, color: i === 0 ? s.accentLt : 'text.disabled', width: 16 }}>{i + 1}</Typography>
                <Typography sx={{ fontSize: 13, flex: 1 }}>{n}</Typography>
                <Typography sx={{ ...mono, fontSize: 12, color: 'text.secondary' }}>{xp.toLocaleString('en-US')} XP</Typography>
              </Box>
            ))}
          </Stack>
        </CardShell>
      );
    case 'summary':
      return (
        <CardShell tone="accent" skin={skin}>
          <Typography sx={{ fontSize: 14, fontWeight: 500, mb: 1.5 }}>{row.title}</Typography>
          <FigureGrid rows={row.rows} cols={3} />
          <Typography sx={{ ...mono, fontSize: 11, color: 'text.disabled', mt: 1.5, pt: 1.25, borderTop: `1px solid ${PALETTE.border1}` }}>{row.foot}</Typography>
        </CardShell>
      );
    default:
      return null;
  }
}

function Row({ row, removed, story }) {
  if (row.type === 'service') return <ServiceLine row={row} />;
  if (row.type === 'card') return <StoryCard row={row} skin={story.skin} story={story} />;
  if (row.type === 'sticker') return <StickerMsg row={row} story={story} />;
  if (story.skin === 'discord') return <DiscordMsg row={row} removed={removed} story={story} />;
  if (story.skin === 'echo') return <EchoMsg row={row} removed={removed} story={story} />;
  return <TelegramMsg row={row} removed={removed} story={story} />;
}

// ── Window chrome ────────────────────────────────────────────────────────────

function Header({ story, scene, members, startMembers }) {
  const s = SKIN[story.skin];
  const dropped = members != null && members < startMembers;
  const statusColor = scene.status.tone === 'red' ? PALETTE.red : PALETTE.green;
  const memberLine = members != null && (
    <Typography sx={{ ...mono, fontSize: 12, color: dropped ? PALETTE.red : 'text.disabled', transition: 'color 0.3s ease' }}>
      {members.toLocaleString('en-US')} members
    </Typography>
  );
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 2, height: 56, borderBottom: `1px solid ${PALETTE.border1}`, bgcolor: PALETTE.bg1 }}>
      {story.skin === 'discord' ? (
        <Tag sx={{ fontSize: 22, color: 'text.disabled' }} />
      ) : (
        <Box sx={{ width: 32, height: 32, borderRadius: '50%', bgcolor: story.skin === 'echo' ? s.accent : '#2c4a63', display: 'grid', placeItems: 'center', fontSize: 13, fontWeight: 600, color: story.skin === 'echo' ? '#0f1012' : '#cfe4f7' }}>
          {story.header.avatar}
        </Box>
      )}
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Typography noWrap sx={{ fontSize: 14, fontWeight: 500, lineHeight: 1.2 }}>
          {story.header.title}
          {story.header.server && <Box component="span" sx={{ color: 'text.disabled', fontWeight: 400 }}> · {story.header.server}</Box>}
        </Typography>
        {memberLine || <Typography sx={{ ...mono, fontSize: 12, color: 'text.disabled' }}>assistant bot</Typography>}
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexShrink: 0 }}>
        <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: statusColor, transition: 'background-color 0.3s ease' }} />
        <Typography sx={{ ...mono, fontSize: 12, color: 'text.secondary', display: { xs: 'none', sm: 'block' } }}>{scene.status.text}</Typography>
      </Box>
    </Box>
  );
}

export function StoryPlayer({ story }) {
  const reduced = useRef(prefersReducedMotion()).current;
  const [sceneIdx, setSceneIdx] = useState(0);
  // Chapter one starts fully drawn so the pre-rendered page and the live one match on first paint.
  const [elapsed, setElapsed] = useState(() => (reduced ? Infinity : 0));
  const [userPaused, setUserPaused] = useState(reduced);
  const [hoverPaused, setHoverPaused] = useState(false);
  const [offscreen, setOffscreen] = useState(false);
  const [animate, setAnimate] = useState(false);
  const root = useRef(null);

  const scene = story.scenes[sceneIdx];
  const playing = !userPaused && !hoverPaused && !offscreen && !IS_PRERENDER;
  const frame = useFrame(story, sceneIdx, sceneIdx === 0 && !animate ? Infinity : elapsed);

  const goTo = useCallback((i) => {
    setAnimate(true);
    setSceneIdx((i + story.scenes.length) % story.scenes.length);
    setElapsed(reduced ? Infinity : 0);
  }, [reduced, story.scenes.length]);

  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(() => {
      setElapsed((e) => e + TICK);
    }, TICK);
    return () => clearInterval(id);
  }, [playing]);

  useEffect(() => {
    if (elapsed >= scene.dur && elapsed !== Infinity) goTo(sceneIdx + 1);
  }, [elapsed, scene.dur, sceneIdx, goTo]);

  // Pause off screen and in background tabs.
  useEffect(() => {
    const el = root.current;
    if (!el || typeof IntersectionObserver === 'undefined') return undefined;
    const io = new IntersectionObserver(([entry]) => setOffscreen(!entry.isIntersecting), { threshold: 0.25 });
    io.observe(el);
    const onVis = () => setOffscreen(document.hidden);
    document.addEventListener('visibilitychange', onVis);
    return () => { io.disconnect(); document.removeEventListener('visibilitychange', onVis); };
  }, []);

  const tone = TONE[scene.tone];
  const progress = elapsed === Infinity ? 1 : Math.min(elapsed / scene.dur, 1);
  const s = SKIN[story.skin];

  return (
    <Box ref={root} sx={{ width: '100%', maxWidth: 520, mx: { xs: 'auto', md: 0 }, ml: { md: 'auto' } }}>
      {/* Screen-reader transcript of the whole story; the animated window is decorative. */}
      <Box component="ol" sx={{ position: 'absolute', width: '1px', height: '1px', m: '-1px', p: 0, border: 0, overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap' }}>
        {story.scenes.map((sc) => <li key={sc.key}>{sc.time}, {sc.title}. {sc.body}</li>)}
      </Box>

      {/* Caption: the chapter's line of narration */}
      <Box key={scene.key} className={animate ? 'st-cap' : undefined} aria-hidden="true" sx={{
        minHeight: { xs: 76, sm: 72 }, mb: 1.5,
        '&.st-cap': { animation: reduced ? 'none' : 'stCap 0.4s ease-out both' },
        '@keyframes stCap': { from: { opacity: 0, transform: 'translateY(4px)' }, to: { opacity: 1, transform: 'none' } },
      }}>
        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1.25 }}>
          <Typography sx={{ ...mono, fontSize: 13, color: scene.tone === 'alarm' ? PALETTE.red : s.accentLt }}>{scene.time}</Typography>
          <Typography sx={{ fontSize: { xs: 16, sm: 17 }, fontWeight: 500, letterSpacing: '-0.01em' }}>{scene.title}</Typography>
        </Box>
        <Typography sx={{ fontSize: { xs: 13.5, sm: 14 }, color: 'text.secondary', lineHeight: 1.5, mt: 0.5, maxWidth: 480 }}>{scene.body}</Typography>
      </Box>

      {/* The chat window */}
      <Box
        aria-hidden="true"
        onPointerEnter={(e) => { if (e.pointerType === 'mouse') setHoverPaused(true); }}
        onPointerLeave={() => setHoverPaused(false)}
        sx={{
          bgcolor: PALETTE.bg2, borderRadius: '16px', overflow: 'hidden',
          border: `1px solid ${tone.frame}`,
          boxShadow: `0 24px 64px rgba(0,0,0,0.45), 0 0 0 6px ${tone.glow}`,
          transition: 'border-color 0.5s ease, box-shadow 0.5s ease',
        }}
      >
        <Header story={story} scene={scene} members={frame.members} startMembers={story.members} />
        <Box sx={{ position: 'relative' }}>
        {frame.stamp && !reduced && <Stamp key={frame.stamp.key} stamp={frame.stamp} playing={playing} />}
        <Box sx={{
          height: { xs: 340, sm: 440 }, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 1.5,
          px: { xs: 1.5, sm: 2.5 }, py: 2, overflow: 'hidden',
          maskImage: 'linear-gradient(to bottom, transparent 0, #000 56px)',
          WebkitMaskImage: 'linear-gradient(to bottom, transparent 0, #000 56px)',
          '& > *': { flexShrink: 0 },
          ...(animate && !reduced ? {
            '& > .st-row': { animation: 'stIn 0.32s cubic-bezier(0.22,1,0.36,1) both' },
            '& .st-strike': { animation: 'stStrike 0.3s ease-out both' },
            '& .st-removed': { animation: 'stFade 0.3s ease-out both' },
            '& .st-bar': { animation: 'stBar 0.9s cubic-bezier(0.22,1,0.36,1) 0.2s both' },
            '& .st-step': { animation: 'stIn 0.3s cubic-bezier(0.22,1,0.36,1) both', animationDelay: 'var(--st-delay)' },
          } : {}),
          '@keyframes stIn': { from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'none' } },
          '@keyframes stStrike': { from: { transform: 'scaleX(0)' }, to: { transform: 'scaleX(1)' } },
          '@keyframes stFade': { from: { opacity: 0 }, to: { opacity: 1 } },
          '@keyframes stBar': { from: { transform: 'scaleX(0)' }, to: { transform: 'scaleX(1)' } },
        }}>
          {frame.rows.map((row) => (
            <Box className="st-row" key={row.key}>
              <Row row={row} removed={row.id ? frame.removed[row.id] : undefined} story={story} />
            </Box>
          ))}
        </Box>
        </Box>
      </Box>

      {/* Chapter controls */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1.5 }}>
        <Box role="group" aria-label="Story chapters" sx={{ display: 'flex', gap: 0.5, flex: 1 }}>
          {story.scenes.map((sc, i) => {
            const fill = i < sceneIdx ? 1 : i === sceneIdx ? progress : 0;
            return (
              <Box
                key={sc.key}
                component="button"
                type="button"
                onClick={() => goTo(i)}
                aria-label={`Chapter ${i + 1}: ${sc.title}`}
                aria-current={i === sceneIdx ? 'step' : undefined}
                sx={{
                  flex: 1, height: 24, p: 0, border: 0, bgcolor: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center',
                  '&:focus-visible': { outline: `2px solid ${s.accent}`, outlineOffset: 2, borderRadius: '4px' },
                }}
              >
                <Box sx={{ height: 3, width: '100%', borderRadius: 2, bgcolor: 'rgba(236,236,238,0.12)', overflow: 'hidden' }}>
                  <Box sx={{
                    height: '100%', width: '100%', transformOrigin: 'left center', transform: `scaleX(${fill})`,
                    bgcolor: sc.tone === 'alarm' ? PALETTE.red : s.accent,
                    transition: playing && i === sceneIdx && fill > 0 ? `transform ${TICK}ms linear` : 'none',
                  }} />
                </Box>
              </Box>
            );
          })}
        </Box>
        <Box
          component="button"
          type="button"
          onClick={() => {
            if (reduced) { goTo(sceneIdx + 1); return; }
            setAnimate(true);
            setUserPaused((p) => !p);
          }}
          aria-label={reduced ? 'Next chapter' : userPaused ? 'Play story' : 'Pause story'}
          sx={{
            width: 32, height: 32, display: 'grid', placeItems: 'center', borderRadius: '8px', cursor: 'pointer',
            border: `1px solid ${PALETTE.border2}`, bgcolor: 'transparent', color: 'text.secondary',
            '&:hover': { color: 'text.primary' },
            '&:focus-visible': { outline: `2px solid ${s.accent}`, outlineOffset: 2 },
          }}
        >
          {reduced ? <ArrowForward sx={{ fontSize: 16 }} /> : userPaused ? <PlayArrow sx={{ fontSize: 18 }} /> : <Pause sx={{ fontSize: 18 }} />}
        </Box>
      </Box>
      <Typography sx={{ ...mono, fontSize: 12, color: 'text.disabled', mt: 1, textAlign: { xs: 'center', md: 'right' } }}>
        Illustrative story, example names and numbers
      </Typography>
    </Box>
  );
}

// Full hero: switcher, headline, CTAs on the left; the story on the right (stacked on phones).
export default function StoryHero({ story, active, title, sub, subShort, primary, secondary, note, extra }) {
  const navigate = useNavigate();
  return (
    <Box component="section" sx={{ overflow: 'hidden' }}>
      <Container maxWidth="lg" sx={{ px: { xs: 2.5, sm: 4 }, pt: { xs: 4, md: 8 }, pb: { xs: 10, md: 12 }, minHeight: { md: 'calc(100vh - 64px)' }, display: 'flex', alignItems: 'center' }}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: { xs: 4, md: 8 }, alignItems: 'center', width: '100%' }}>
          <Box>
            <PlatformSwitcher active={active} align="left" />
            <Typography
              variant="h1"
              sx={{ fontSize: { xs: '2rem', sm: '3rem', md: '3.5rem' }, fontWeight: 500, lineHeight: 1.05, letterSpacing: '-0.03em', maxWidth: 580, textWrap: 'balance' }}
            >
              {title}
            </Typography>
            {/* Phones get a one-line intro so the story itself starts on the first screen. */}
            <Typography color="text.secondary" sx={{ display: { xs: subShort ? 'none' : 'block', sm: 'block' }, mt: { xs: 2, md: 3 }, fontSize: { xs: '1rem', md: '1.1875rem' }, lineHeight: 1.6, maxWidth: 520 }}>
              {sub}
            </Typography>
            {subShort && (
              <Typography color="text.secondary" sx={{ display: { xs: 'block', sm: 'none' }, mt: 1.5, fontSize: '1rem', lineHeight: 1.5 }}>
                {subShort}
              </Typography>
            )}
            <Stack direction="row" spacing={1.5} sx={{ mt: { xs: 3, md: 5 }, '& > *': { flex: { xs: 1, sm: 'none' }, whiteSpace: 'nowrap', px: { xs: '12px !important', sm: '24px !important' } }, '& > :first-of-type': { flex: { xs: 1.5, sm: 'none' } } }}>
              <Button variant="contained" size="large" onClick={() => navigate(primary.to)} endIcon={<ArrowForward />} sx={{ px: { xs: 2, sm: 3 } }}>
                {primary.label}
              </Button>
              <Button variant="outlined" size="large" onClick={() => navigate(secondary.to)} sx={{ px: { xs: 2, sm: 3 } }}>
                {secondary.label}
              </Button>
            </Stack>
            <Typography sx={{ ...mono, fontSize: '0.8125rem', color: 'text.disabled', mt: { xs: 2, md: 3 } }}>{note}</Typography>
            {extra}
          </Box>
          <StoryPlayer story={story} />
        </Box>
      </Container>
    </Box>
  );
}
