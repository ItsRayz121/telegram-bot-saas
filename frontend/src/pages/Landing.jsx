import React, { useState, useEffect, useRef } from 'react';
import { useScrollReveal } from '../hooks/useScrollReveal';
import {
  Box, AppBar, Toolbar, Typography, Button, Grid, Container, Stack, Skeleton,
  Accordion, AccordionSummary, AccordionDetails, Link,
} from '@mui/material';
import { analytics as analyticsApi } from '../services/api';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  SmartToy, Shield, Schedule, BarChart, People, Check, Remove,
  AutoAwesome, Bolt, Campaign, Link as LinkIcon, Telegram, Forum, ArrowForward,
} from '@mui/icons-material';
import TelegizerLogo from '../components/TelegizerLogo';
import PlatformSwitcher from '../components/PlatformSwitcher';
import { useNavigate } from 'react-router-dom';
import usePageMeta from '../hooks/usePageMeta';
import { PALETTE, FONT_MONO } from '../theme';

const mono = { fontFamily: FONT_MONO, fontVariantNumeric: 'tabular-nums', letterSpacing: 0 };

// ── Content ──────────────────────────────────────────────────────────────────

// Before → After. Same group, same admin, minus the manual grind.
const BEFORE_AFTER = [
  ['Spam piles up until you clear it by hand', 'AutoMod removes spam the moment it lands'],
  ['You type every welcome message yourself', 'New members are welcomed automatically'],
  ['Posts only go out when you are online', 'Posts publish on schedule, in any timezone'],
  ['You guess what drives growth', 'Analytics show which invite links bring people'],
  ['Moderation eats your evenings', 'The bot handles the routine, you run the community'],
];

const FEATURES = [
  { icon: Shield, title: 'AutoMod', plan: 'Free', desc: 'Removes spam, links, banned words and media. Warns, mutes and bans on rules you set.' },
  { icon: Schedule, title: 'Scheduled posts', plan: 'Free', desc: 'Write once and publish on a schedule. Daily updates, weekly recaps and polls in any timezone.' },
  { icon: People, title: 'Member levels', plan: 'Free', desc: 'XP, levels, roles and join verification. Active members get rewarded, bots get stopped.' },
  { icon: SmartToy, title: 'Auto replies', plan: 'Free', desc: 'Keyword triggers that answer common questions, share links or run commands.' },
  { icon: LinkIcon, title: 'Invite tracking', plan: 'Free', desc: 'Trackable invite links that show which source brings the most new members.' },
  { icon: BarChart, title: 'Growth analytics', plan: 'Pro', desc: 'Joins per invite link, peak hours, retention and moderation stats.' },
  { icon: AutoAwesome, title: 'AI knowledge base', plan: 'Pro', desc: 'Upload your docs or FAQ and the bot answers member questions from them.' },
  { icon: Bolt, title: 'Webhooks', plan: 'Pro', desc: 'Send GitHub releases, price alerts or any API event straight to your group.' },
  { icon: Campaign, title: 'Campaigns', plan: 'Pro', desc: 'Repost drives, AMAs and engagement tasks where members earn XP for taking part.' },
];

const PLANS = [
  {
    name: 'Free', price: '$0', period: 'forever', note: 'Runs on the shared @telegizer_bot',
    features: ['Unlimited groups', 'Basic moderation', 'Welcome messages', 'Scheduled messages', 'XP system'],
    cta: 'Start free', tier: null,
  },
  {
    name: 'Pro', price: '$9', period: 'per month', note: 'About $0.30 a day', popular: true,
    features: ['3 custom bots', 'Unlimited groups', 'Advanced AutoMod', 'Analytics', 'AI knowledge base', 'Webhooks', 'Priority support'],
    cta: 'Get Pro', tier: 'pro',
  },
  {
    name: 'Enterprise', price: '$49', period: 'per month', note: 'About $1.63 a day',
    features: ['50 custom bots', 'Everything in Pro', 'API access', 'SLA', 'Dedicated support'],
    cta: 'Get Enterprise', tier: 'enterprise',
  },
];

const STEPS = [
  { title: 'Create a free account', desc: 'Email and password, about 30 seconds.' },
  { title: 'Get a bot token from @BotFather', desc: 'In Telegram, message @BotFather and send /newbot.' },
  { title: 'Paste the token into Telegizer', desc: 'The bot connects right away. No code.' },
  { title: 'Add the bot to your group as admin', desc: 'The group shows up in your dashboard.' },
  { title: 'Turn on what you need', desc: 'AutoMod, scheduled posts, levels, analytics.' },
];

// Real, named testimonials. Add entries here (with the person's permission) and the section switches
// from the paraphrased feedback below to these automatically. Only `quote` and `name` are required.
//   { quote: '…', name: 'Mira K.', role: 'Admin', community: 'Base builders', members: '12K members',
//     link: 'https://t.me/basebuilders' }
const TESTIMONIALS = [];

// Paraphrased feedback from early test communities — shown only while TESTIMONIALS is empty, and labelled
// as paraphrased, never presented as named quotes.
const EARLY_FEEDBACK = [
  { text: 'AutoMod cut my daily moderation work dramatically. Spam was the biggest pain point and now it just handles itself.', context: 'Community admin, crypto group' },
  { text: 'Scheduling posts once and forgetting about them is exactly what I needed. My group stays active even when I am offline.', context: 'Project founder, managing 4 groups' },
  { text: 'Seeing which invite links actually brought real members changed how I run growth.', context: 'Group owner, DeFi community' },
];

// The wider product family. Telegizer (this page) is the Telegram pillar; Echo is
// the in-app AI assistant; Guildizer is the separate Discord product (shares this
// origin). Cross-sell only — the hero stays 100% focused on Telegram groups.
const PRODUCT_FAMILY = [
  { icon: Telegram, name: 'Telegizer', tag: 'Telegram groups', desc: 'Moderation, scheduled posts, member levels and growth analytics for Telegram groups.', to: null },
  { icon: SmartToy, name: 'Echo', tag: 'AI assistant', desc: 'A personal assistant inside Telegram for reminders, notes, tasks and daily digests.', cta: 'Explore Echo', to: '/echo' },
  { icon: Forum, name: 'Guildizer', tag: 'Discord servers', desc: 'The same moderation and growth tools, built natively for Discord servers.', cta: 'Explore Guildizer', to: '/guildizer-landing' },
];

const FAQ = [
  { q: 'Is it safe to add the bot as admin?', a: 'Telegizer only asks for the Telegram permissions it needs: delete messages, ban or restrict users, pin messages and invite links. It never reads private messages or group data outside the scope of bot commands.' },
  { q: 'Which Telegram permissions does the bot need?', a: 'At minimum: delete messages, restrict members, pin messages and add members. Invite link tracking also needs "Invite users via link". Telegram shows the exact prompt when you make the bot admin.' },
  { q: 'What happens if I cancel or my plan expires?', a: 'Your bots keep running, but paid features such as advanced moderation and analytics become read-only. Free plan features stay on indefinitely, and everything comes back as soon as you renew.' },
  { q: 'Which coins and payment methods are supported?', a: 'Payments go through NOWPayments and support USDT, BTC, ETH, BNB, TRX, SOL and 300+ other coins. Card payments are not available yet.' },
  { q: 'How long do crypto payments take to confirm?', a: 'Most confirm in 1 to 10 minutes. Bitcoin and Ethereum can take 10 to 30 minutes or more when the network is busy. Your plan activates automatically once the payment confirms.' },
  { q: 'Can I manage several groups with one bot?', a: 'Yes. The shared @telegizer_bot can join unlimited groups on every plan. Your own custom bots support 3 groups each on Free and unlimited groups on Pro and Enterprise. Each group keeps its own settings, rules, XP and schedule. Pro includes up to 3 custom bots, Enterprise up to 50.' },
  { q: 'What is the difference between Free, Pro and Enterprise?', a: 'Free: unlimited groups on the shared @telegizer_bot with basic moderation, welcome messages, scheduled messages, custom commands and XP. Pro ($9/month): up to 3 custom bots, advanced AutoMod, analytics, AI knowledge base and AI credits. Enterprise ($49/month): 50 custom bots, everything in Pro, API access, dedicated support and an SLA. Every new account starts with a free 14-day Pro trial.' },
  { q: 'Is my bot token stored securely?', a: 'Bot tokens are encrypted at rest with AES-256 (Fernet) before they are written to the database. They are never stored in plain text and never returned in API responses.' },
  { q: 'Can I change the timezone for scheduled posts?', a: 'Yes. Set a default timezone per group under Automation › Scheduler, and override it for any single message or poll.' },
];

// ── Shared pieces ─────────────────────────────────────────────────────────────

function SectionHead({ label, title, sub, center }) {
  return (
    <Box sx={{ mb: { xs: 5, md: 7 }, maxWidth: center ? 640 : 720, mx: center ? 'auto' : 0, textAlign: center ? 'center' : 'left' }}>
      {label && (
        <Typography sx={{ ...mono, fontSize: '0.8125rem', color: 'text.disabled', mb: 1.5 }}>{label}</Typography>
      )}
      <Typography component="h2" sx={{ fontSize: { xs: '1.75rem', md: '2.375rem' }, fontWeight: 500, lineHeight: 1.15, letterSpacing: '-0.02em', textWrap: 'balance' }}>
        {title}
      </Typography>
      {sub && (
        <Typography color="text.secondary" sx={{ mt: 2, fontSize: { xs: '1rem', md: '1.0625rem' }, lineHeight: 1.6, maxWidth: 560, mx: center ? 'auto' : 0 }}>
          {sub}
        </Typography>
      )}
    </Box>
  );
}

function Section({ children, alt, id, sx, innerRef }) {
  return (
    <Box
      component="section"
      id={id}
      ref={innerRef}
      sx={{ bgcolor: alt ? PALETTE.bg1 : 'transparent', borderTop: `1px solid ${PALETTE.border1}`, py: { xs: 10, md: 16 }, ...sx }}
    >
      <Container maxWidth="lg" sx={{ px: { xs: 2.5, sm: 4 } }}>{children}</Container>
    </Box>
  );
}

// ── Hero chat: the bot at work, drawn in code ─────────────────────────────────

function Bubble({ name, nameColor, children, meta, bot, struck, className }) {
  return (
    <Box className={className} sx={{ display: 'flex', gap: 1.25, alignItems: 'flex-end', position: 'relative' }}>
      <Box sx={{
        width: 28, height: 28, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center',
        bgcolor: bot ? PALETTE.blue : PALETTE.bg4, color: bot ? '#0f1012' : 'text.secondary', fontSize: 12, fontWeight: 600,
      }}>
        {bot ? <Telegram sx={{ fontSize: 16 }} /> : name[0].toUpperCase()}
      </Box>
      <Box sx={{
        position: 'relative', maxWidth: 340, px: 1.5, py: 1, bgcolor: PALETTE.bg3,
        borderRadius: '12px 12px 12px 4px', border: `1px solid ${PALETTE.border1}`,
      }}>
        <Typography sx={{ fontSize: 12, fontWeight: 500, color: nameColor || 'text.secondary', mb: 0.25 }}>{name}</Typography>
        <Typography component="div" sx={{ fontSize: { xs: 13, sm: 14 }, lineHeight: 1.45, color: 'text.primary', position: 'relative' }}>
          {children}
          {struck && <Box className="strike" sx={{ position: 'absolute', left: 0, right: 0, top: '52%', height: '1.5px', bgcolor: PALETTE.red, transformOrigin: 'left center' }} />}
        </Typography>
        {meta && <Typography sx={{ ...mono, fontSize: 11, color: 'text.disabled', mt: 0.5, textAlign: 'right' }}>{meta}</Typography>}
      </Box>
    </Box>
  );
}

function ServiceLine({ children, tone, className }) {
  return (
    <Box className={className} sx={{ display: 'flex', justifyContent: 'center' }}>
      <Typography sx={{
        ...mono, fontSize: { xs: 11, sm: 12 }, color: tone || 'text.secondary', px: 1.25, py: 0.5,
        borderRadius: '6px', bgcolor: 'rgba(236,236,238,0.04)', textAlign: 'center',
      }}>
        {children}
      </Typography>
    </Box>
  );
}

// True only while the homepage is rendered to static HTML at build time (src/prerender.jsx runs in Node).
const IS_PRERENDER = typeof window === 'undefined';

function HeroChat() {
  const root = useRef(null);

  // One entrance, and it explains the product: each event lands in order.
  // GSAP loads as its own chunk; reduced-motion users get the finished state.
  useEffect(() => {
    const el = root.current;
    if (!el || !window.matchMedia || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;
    let ctx; let cancelled = false;
    el.classList.add('chat-pending');
    import('gsap').then(({ gsap }) => {
      if (cancelled) return;
      ctx = gsap.context(() => {
        // Opacity + transform only (autoAlpha also toggles visibility): both stay on the compositor, whereas
        // the earlier clip-path reveal forced layout on every frame while the page was still loading.
        const HIDDEN = { autoAlpha: 0, y: 10 };
        const SHOWN = { autoAlpha: 1, y: 0 };
        const tl = gsap.timeline({ delay: 0.3, defaults: { ease: 'power3.out', duration: 0.45 } });
        gsap.set('.m', HIDDEN);
        el.classList.remove('chat-pending');
        tl.to('.m1', SHOWN)
          .to('.m2', SHOWN, '+=0.35')
          .fromTo('.m2 .strike', { scaleX: 0 }, { scaleX: 1, duration: 0.35, ease: 'power2.inOut' }, '+=0.45')
          .to('.m2 .spam-text', { color: PALETTE.text3, duration: 0.3 }, '<0.2')
          .to('.m3', SHOWN, '<0.1')
          .to('.m4', SHOWN, '+=0.5')
          .to('.m5', SHOWN, '+=0.3')
          .to('.m6', SHOWN, '+=0.55')
          .to('.m7', SHOWN, '+=0.45');
      }, el);
      el.classList.remove('chat-pending');
    }).catch(() => el.classList.remove('chat-pending'));
    return () => { cancelled = true; el.classList.remove('chat-pending'); if (ctx) ctx.revert(); };
  }, []);

  return (
    <Box
      ref={root}
      // The pre-rendered HTML starts with the messages hidden, the same state the entrance animation
      // starts from, so they do not show, vanish and replay when the app takes over.
      className={IS_PRERENDER ? 'chat-pending' : undefined}
      aria-label="Example: Telegizer moderating a Telegram group"
      role="img"
      sx={{
        width: '100%', maxWidth: 520, mx: { xs: 'auto', md: 0 }, ml: { md: 'auto' },
        bgcolor: PALETTE.bg2, border: `1px solid ${PALETTE.border2}`, borderRadius: '16px', overflow: 'hidden',
        boxShadow: '0 24px 64px rgba(0,0,0,0.45)',
        '&.chat-pending .m': { visibility: 'hidden' },
        // No animation will run for these users, so never hide the messages.
        '@media (prefers-reduced-motion: reduce)': { '&.chat-pending .m': { visibility: 'visible' } },
      }}
    >
      {/* Group header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 2, height: 56, borderBottom: `1px solid ${PALETTE.border1}`, bgcolor: PALETTE.bg1 }}>
        <Box sx={{ width: 32, height: 32, borderRadius: '50%', bgcolor: '#2c4a63', display: 'grid', placeItems: 'center', fontSize: 13, fontWeight: 600, color: '#cfe4f7' }}>B</Box>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography sx={{ fontSize: 14, fontWeight: 500, lineHeight: 1.2 }}>Base builders</Typography>
          <Typography sx={{ ...mono, fontSize: 12, color: 'text.disabled' }}>12,847 members</Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: PALETTE.green }} />
          <Typography sx={{ ...mono, fontSize: 12, color: 'text.secondary' }}>bot admin</Typography>
        </Box>
      </Box>

      {/* Messages */}
      <Stack spacing={1.5} sx={{ p: { xs: 1.5, sm: 2.5 }, pb: { xs: 2, sm: 3 } }}>
        <Bubble className="m m1" name="nik.eth" meta="18:01">anyone know when the snapshot is?</Bubble>
        <Bubble className="m m2" name="fast_claim" meta="18:02" struck><Box component="span" className="spam-text">Free airdrop, claim now t.me/+x9Kq…</Box></Bubble>
        <ServiceLine className="m m3" tone={PALETTE.red}>18:02  removed · link spam · muted 24h</ServiceLine>
        <ServiceLine className="m m4">18:04  mira_k joined via invite “twitter-bio”</ServiceLine>
        <Bubble className="m m5" bot name="Telegizer" nameColor={PALETTE.blueLt} meta="18:04">
          Welcome, Mira. The rules are pinned, have a read before posting.
        </Bubble>
        <Bubble className="m m6" bot name="Telegizer" nameColor={PALETTE.blueLt} meta="scheduled · 18:00 UTC">
          Weekly AMA starts in one hour. Drop your questions in this thread.
        </Bubble>
        <ServiceLine className="m m7">18:06  dan_ol reached level 5 · +40 XP</ServiceLine>
      </Stack>
    </Box>
  );
}

// ── Analytics preview: the group analytics page, drawn in code ──────────────

// 30 days of member counts for an example group (steady growth with two launch spikes).
const GROWTH = [11840, 11872, 11901, 11915, 11960, 11994, 12010, 12031, 12088, 12204, 12266, 12290, 12301, 12333, 12352,
  12370, 12398, 12415, 12466, 12590, 12631, 12650, 12671, 12688, 12702, 12731, 12760, 12784, 12811, 12847];
const INVITES = [['twitter-bio', 412], ['partner-ama', 268], ['newsletter', 151], ['discord-x', 74], ['website', 52]];

function AnalyticsPreview() {
  const W = 640; const H = 220; const P = 8;
  const min = Math.min(...GROWTH) - 40; const max = Math.max(...GROWTH) + 20;
  const pts = GROWTH.map((v, i) => [P + (i * (W - P * 2)) / (GROWTH.length - 1), H - P - ((v - min) / (max - min)) * (H - P * 2)]);
  const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  const area = `${line} L${pts[pts.length - 1][0].toFixed(1)} ${H} L${P} ${H} Z`;
  const topInvite = INVITES[0][1];
  const kpis = [
    ['Members', '12,847', '+1,007 vs last 30 days'],
    ['Joined', '1,214', '+18% vs last 30 days'],
    ['Spam removed', '1,392', '96% within 10 s'],
    ['Active today', '2,306', '18% of members'],
  ];
  return (
    <Box sx={{ p: { xs: 2, md: 3 } }}>
      <Grid container spacing={0} sx={{ mb: 3 }}>
        {kpis.map(([label, value, delta], i) => (
          <Grid item xs={6} md={3} key={label} sx={{ py: 1.5, pl: { md: i ? 3 : 0 }, borderLeft: { md: i ? `1px solid ${PALETTE.border1}` : 'none' } }}>
            <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{label}</Typography>
            <Typography data-figure sx={{ fontSize: { xs: 22, md: 28 }, fontWeight: 500, lineHeight: 1.2, mt: 0.5 }}>{value}</Typography>
            <Typography sx={{ ...mono, fontSize: 12, color: i < 2 ? PALETTE.green : 'text.disabled', mt: 0.5 }}>{delta}</Typography>
          </Grid>
        ))}
      </Grid>
      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Box sx={{ border: `1px solid ${PALETTE.border1}`, borderRadius: '12px', p: 2, bgcolor: PALETTE.bg1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1.5 }}>
              <Typography sx={{ fontSize: 14, fontWeight: 500 }}>Member growth</Typography>
              <Typography sx={{ ...mono, fontSize: 12, color: 'text.disabled' }}>last 30 days</Typography>
            </Box>
            <Box component="svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" sx={{ width: '100%', height: { xs: 140, md: 220 }, display: 'block' }} aria-hidden="true">
              <defs>
                <linearGradient id="lpArea" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor={PALETTE.blue} stopOpacity="0.22" />
                  <stop offset="1" stopColor={PALETTE.blue} stopOpacity="0" />
                </linearGradient>
              </defs>
              {[0.25, 0.5, 0.75].map((f) => <line key={f} x1="0" x2={W} y1={H * f} y2={H * f} stroke={PALETTE.border1} strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
              <path d={area} fill="url(#lpArea)" />
              <path d={line} fill="none" stroke={PALETTE.blue} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
              {['Oct 29', 'Nov 6', 'Nov 14', 'Nov 22', 'Nov 27'].map((d) => <Typography key={d} sx={{ ...mono, fontSize: 11, color: 'text.disabled' }}>{d}</Typography>)}
            </Box>
          </Box>
        </Grid>
        <Grid item xs={12} md={4}>
          <Box sx={{ border: `1px solid ${PALETTE.border1}`, borderRadius: '12px', p: 2, bgcolor: PALETTE.bg1, height: '100%' }}>
            <Typography sx={{ fontSize: 14, fontWeight: 500, mb: 2 }}>Joins by invite link</Typography>
            <Stack spacing={1.75}>
              {INVITES.map(([name, n], i) => (
                <Box key={name}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.75 }}>
                    <Typography sx={{ ...mono, fontSize: 12, color: 'text.secondary' }}>{name}</Typography>
                    <Typography sx={{ ...mono, fontSize: 12 }}>{n}</Typography>
                  </Box>
                  <Box sx={{ height: 4, borderRadius: 2, bgcolor: 'rgba(236,236,238,0.06)' }}>
                    <Box sx={{ height: 4, borderRadius: 2, width: `${(n / topInvite) * 100}%`, bgcolor: i === 0 ? PALETTE.blue : '#4a4b52' }} />
                  </Box>
                </Box>
              ))}
            </Stack>
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
}

// ── Live platform numbers ─────────────────────────────────────────────────────

function useAnimatedCount(target, duration = 1200) {
  const [display, setDisplay] = useState(0);
  const frameRef = useRef(null);
  useEffect(() => {
    if (!target) { setDisplay(0); return undefined; }
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setDisplay(target); return undefined; }
    const start = performance.now();
    const step = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(eased * target));
      if (progress < 1) frameRef.current = requestAnimationFrame(step);
    };
    frameRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frameRef.current);
  }, [target, duration]);
  return display;
}

function formatStat(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (n >= 10_000) return (n / 1_000).toFixed(1).replace(/\.0$/, '') + 'K';
  return n.toLocaleString();
}

function Stat({ target, label, sub, visible, loading }) {
  const reduced = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const count = useAnimatedCount(visible || reduced ? (target || 0) : 0);
  return (
    <Box sx={{ py: { xs: 2.5, md: 1 }, px: { xs: 0, md: 3 }, height: '100%' }}>
      {loading ? (
        <Skeleton variant="text" width={96} height={48} sx={{ bgcolor: 'rgba(236,236,238,0.06)' }} />
      ) : (
        <Typography data-figure sx={{ fontSize: { xs: '2rem', md: '2.5rem' }, fontWeight: 500, lineHeight: 1.1, letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums' }}>
          {target != null ? formatStat(count) : '—'}
        </Typography>
      )}
      <Typography sx={{ fontSize: '0.875rem', mt: 1 }}>{label}</Typography>
      <Typography sx={{ fontSize: '0.8125rem', color: 'text.disabled', mt: 0.25, lineHeight: 1.4 }}>{sub}</Typography>
    </Box>
  );
}

function LivePlatformStats({ proofRef, proofVisible, stats, statsLoading, proofKeys }) {
  const allCards = [
    { key: 'members', proofKey: 'members_protected', target: stats?.total_members ?? null, label: 'Members tracked', sub: 'across all groups' },
    { key: 'mod', proofKey: 'moderation_actions', target: stats?.total_mod_actions ?? null, label: 'Moderation actions', sub: 'spam removals, bans and mutes' },
    { key: 'new_members', proofKey: 'new_members_week', target: stats?.new_members_this_week ?? null, label: 'New members this week', sub: 'joined groups run by Telegizer' },
    { key: 'groups', proofKey: 'groups_managed', target: stats?.groups_managed ?? stats?.total_groups ?? null, label: 'Groups managed', sub: 'using Telegizer right now' },
    { key: 'groups_ever', proofKey: 'groups_ever', target: stats?.groups_ever ?? null, label: 'Groups served, all time', sub: 'every group that has used it' },
    { key: 'official', proofKey: 'official_groups', target: stats?.official_groups ?? null, label: 'Groups on the shared bot', sub: 'using @telegizer_bot' },
    { key: 'bots', proofKey: 'custom_bots_created', target: stats?.custom_bots ?? null, label: 'Custom bots created', sub: 'private bots built on Telegizer' },
  ];
  // The admin's Public/Private switches decide which counters visitors see.
  // proofKeys: array = known, undefined = still loading (show skeleton cards),
  // null = the proof endpoint failed with no cache (keep the old show-all behaviour).
  const cards = Array.isArray(proofKeys) ? allCards.filter((c) => proofKeys.includes(c.proofKey)) : allCards;
  const shown = cards.slice(0, 4);

  return (
    <Section id="proof" innerRef={proofRef}>
      <Grid container spacing={{ xs: 4, md: 8 }} alignItems="flex-start">
        <Grid item xs={12} md={4}>
          <SectionHead
            label="live · updated weekly"
            title="Real groups, real numbers"
            sub="Every figure here comes straight from the Telegizer database, official bot and custom bots included."
          />
        </Grid>
        <Grid item xs={12} md={8}>
          {shown.length > 0 && (
            <Grid container sx={{ borderTop: { xs: 'none', md: `1px solid ${PALETTE.border1}` }, pt: { md: 4 } }}>
              {shown.map((c, i) => (
                <Grid item xs={6} md={shown.length >= 4 ? 3 : 12 / shown.length} key={c.key}
                  sx={{ borderLeft: { md: i > 0 ? `1px solid ${PALETTE.border1}` : 'none' }, borderTop: { xs: `1px solid ${PALETTE.border1}`, md: 'none' }, '& > div': { px: { md: i === 0 ? 0 : 3 } } }}>
                  <Stat {...c} visible={proofVisible} loading={statsLoading} />
                </Grid>
              ))}
            </Grid>
          )}
          {cards.length > 4 && (
            <Stack direction="row" spacing={3} useFlexGap flexWrap="wrap" sx={{ mt: 4 }}>
              {cards.slice(4).map((c) => (
                <Typography key={c.key} sx={{ ...mono, fontSize: '0.8125rem', color: 'text.secondary' }}>
                  {statsLoading || c.target == null ? '—' : c.target.toLocaleString()} <Box component="span" sx={{ color: 'text.disabled' }}>{c.label.toLowerCase()}</Box>
                </Typography>
              ))}
            </Stack>
          )}
        </Grid>
      </Grid>

      {/* The real analytics screen */}
      <Box sx={{ mt: { xs: 6, md: 10 }, borderRadius: '16px', border: `1px solid ${PALETTE.border2}`, overflow: 'hidden', bgcolor: PALETTE.bg2 }}>
        <Box sx={{ height: 40, display: 'flex', alignItems: 'center', gap: 0.75, px: 2, borderBottom: `1px solid ${PALETTE.border1}` }}>
          {[0, 1, 2].map((d) => <Box key={d} sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: PALETTE.bg4 }} />)}
          <Typography sx={{ ...mono, fontSize: 12, color: 'text.disabled', ml: 1.5 }}>Group analytics</Typography>
        </Box>
        <AnalyticsPreview />
      </Box>
      <Typography sx={{ ...mono, fontSize: 12, color: 'text.disabled', mt: 1.5 }}>Example data, same layout as the group analytics page</Typography>
    </Section>
  );
}

const STATS_CACHE_KEY = 'telegizer_platform_stats_v1';
const PROOF_KEYS_CACHE_KEY = 'telegizer_public_proof_keys_v1';
function loadCachedProofKeys() {
  try {
    const raw = JSON.parse(localStorage.getItem(PROOF_KEYS_CACHE_KEY) || 'null');
    return Array.isArray(raw) ? raw : undefined;
  } catch { return undefined; }
}
// NOTE: no fabricated fallback numbers here. If we have no real data (no cache,
// API down) the entire section is hidden rather than showing invented stats.
function loadCachedStats() {
  try {
    const raw = localStorage.getItem(STATS_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Landing() {
  usePageMeta();
  const navigate = useNavigate();
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;

  const [platformStats, setPlatformStats] = useState(() => loadCachedStats());
  const [statsLoading, setStatsLoading] = useState(true);
  const [proofKeys, setProofKeys] = useState(() => loadCachedProofKeys());
  const [proofRef, proofVisible] = useScrollReveal(0.1);

  useEffect(() => {
    let cancelled = false;
    // Fetch the numbers and the admin's public/private choices together so the
    // counters never flash in and then disappear.
    Promise.allSettled([analyticsApi.getPlatformStats(), analyticsApi.getPublicProof()])
      .then(([stats, proof]) => {
        if (cancelled) return;
        if (stats.status === 'fulfilled') {
          const data = stats.value.data;
          if (data && typeof data.total_members === 'number') {
            setPlatformStats(data);
            try { localStorage.setItem(STATS_CACHE_KEY, JSON.stringify(data)); } catch { /* quota */ }
          }
        } else if (process.env.NODE_ENV !== 'production') {
          console.warn('[platform-stats] fetch failed, using cached data if any:', stats.reason?.message);
        }
        // platformStats stays at cached value or null (section hidden) — never fabricated
        if (proof.status === 'fulfilled' && Array.isArray(proof.value.data?.metrics)) {
          const keys = proof.value.data.metrics.map((m) => m.key);
          setProofKeys(keys);
          try { localStorage.setItem(PROOF_KEYS_CACHE_KEY, JSON.stringify(keys)); } catch { /* quota */ }
        } else {
          setProofKeys((prev) => (prev === undefined ? null : prev)); // keep cache; else show all
        }
        setStatsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  // Deep link (/#proof): the section mounts after stats load, so the browser's own
  // hash scroll misses it. Scroll once it exists.
  useEffect(() => {
    if (statsLoading || window.location.hash !== '#proof') return;
    document.getElementById('proof')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [statsLoading]);

  // A counter is shown when its proof metric is public (or the choice is unknown).
  const showProof = (key) => !Array.isArray(proofKeys) || proofKeys.includes(key);
  const liveGroups = platformStats?.groups_managed;
  const showLiveLine = liveGroups > 0 && showProof('groups_managed');

  const navLink = { color: 'text.secondary', fontSize: '0.875rem', px: 1.5, minWidth: 0, '&:hover': { color: 'text.primary', bgcolor: 'transparent' } };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>

      {/* ── Nav ── */}
      <AppBar position="sticky" elevation={0} sx={{ bgcolor: PALETTE.bg0 }}>
        <Toolbar sx={{ maxWidth: 1200, mx: 'auto', width: '100%', px: { xs: 2.5, sm: 4 }, minHeight: { xs: 56, sm: 64 } }}>
          <Box sx={{ flexGrow: 1, display: 'flex' }}>
            <Box component="a" href="/" aria-label="Telegizer home" sx={{ display: 'inline-flex' }}><TelegizerLogo size="md" /></Box>
          </Box>
          <Stack direction="row" spacing={0.5} sx={{ display: { xs: 'none', md: 'flex' }, mr: 2 }}>
            <Button href="#features" sx={navLink}>Features</Button>
            <Button onClick={() => navigate('/pricing')} sx={navLink}>Pricing</Button>
            <Button href="#faq" sx={navLink}>FAQ</Button>
          </Stack>
          {token ? (
            <Button variant="contained" onClick={() => navigate('/dashboard')}>Dashboard</Button>
          ) : (
            <Stack direction="row" spacing={1} alignItems="center">
              <Button onClick={() => navigate('/login')} sx={navLink}>Log in</Button>
              <Button variant="contained" onClick={() => navigate('/register')}>Start free</Button>
            </Stack>
          )}
        </Toolbar>
      </AppBar>

      {/* ── Hero ── */}
      <Box component="section" sx={{ overflow: 'hidden' }}>
        <Container maxWidth="lg" sx={{ px: { xs: 2.5, sm: 4 }, pt: { xs: 6, md: 10 }, pb: { xs: 10, md: 14 }, minHeight: { md: 'calc(100vh - 64px)' }, display: 'flex', alignItems: 'center' }}>
          <Grid container spacing={{ xs: 7, md: 8 }} alignItems="center">
            <Grid item xs={12} md={6}>
              <PlatformSwitcher active="telegram:group" align="left" />
              <Typography
                variant="h1"
                sx={{ fontSize: { xs: '2.375rem', sm: '3rem', md: '3.5rem' }, fontWeight: 500, lineHeight: 1.05, letterSpacing: '-0.03em', maxWidth: 560, textWrap: 'balance' }}
              >
                Run your Telegram group without living in it
              </Typography>
              <Typography color="text.secondary" sx={{ mt: 3, fontSize: { xs: '1.0625rem', md: '1.1875rem' }, lineHeight: 1.6, maxWidth: 520 }}>
                Telegizer removes spam, welcomes new members, posts on schedule and shows what grows your group.
                Connect a bot and you are set up in about five minutes.
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 5 }}>
                <Button variant="contained" size="large" onClick={() => navigate('/register')} endIcon={<ArrowForward />} sx={{ px: 3 }}>
                  Start free
                </Button>
                <Button variant="outlined" size="large" onClick={() => navigate('/pricing')} sx={{ px: 3 }}>
                  See pricing
                </Button>
              </Stack>
              <Typography sx={{ ...mono, fontSize: '0.8125rem', color: 'text.disabled', mt: 3 }}>
                Free plan · 14-day Pro trial · no card required
              </Typography>
              {showLiveLine && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1.5 }}>
                  <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: PALETTE.green, flexShrink: 0 }} />
                  <Typography sx={{ ...mono, fontSize: '0.8125rem', color: 'text.secondary' }}>
                    running in {liveGroups.toLocaleString()} groups
                    {showProof('members_protected') && platformStats.total_members ? ` · ${platformStats.total_members.toLocaleString()} members` : ''}
                  </Typography>
                </Box>
              )}
            </Grid>
            <Grid item xs={12} md={6}>
              <HeroChat />
              <Typography sx={{ ...mono, fontSize: 12, color: 'text.disabled', mt: 1.5, textAlign: { xs: 'center', md: 'right' } }}>
                Example group, illustrative messages
              </Typography>
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* ── Live Platform Stats — only rendered with real data (cache or live API) ── */}
      {(platformStats || statsLoading) && (
        <LivePlatformStats proofRef={proofRef} proofVisible={proofVisible} stats={platformStats} statsLoading={statsLoading} proofKeys={proofKeys} />
      )}

      {/* ── Before / after ── */}
      <Section alt>
        <SectionHead
          label="what changes"
          title="Managing a group should not be a second job"
          sub="Connect your bot and choose what to automate. Telegizer runs it in the background."
        />
        <Box sx={{ border: `1px solid ${PALETTE.border1}`, borderRadius: '12px', overflow: 'hidden', bgcolor: PALETTE.bg2 }}>
          <Grid container sx={{ display: { xs: 'none', md: 'flex' }, borderBottom: `1px solid ${PALETTE.border1}` }}>
            <Grid item md={6} sx={{ px: 3, py: 2 }}><Typography sx={{ fontSize: '0.875rem', color: 'text.disabled' }}>By hand</Typography></Grid>
            <Grid item md={6} sx={{ px: 3, py: 2, borderLeft: `1px solid ${PALETTE.border1}` }}><Typography sx={{ fontSize: '0.875rem', color: 'text.secondary' }}>With Telegizer</Typography></Grid>
          </Grid>
          {BEFORE_AFTER.map(([before, after], i) => (
            <Grid container key={before} sx={{ borderTop: i ? `1px solid ${PALETTE.border1}` : 'none' }}>
              <Grid item xs={12} md={6} sx={{ px: { xs: 2.5, md: 3 }, pt: { xs: 2, md: 2.5 }, pb: { xs: 0.5, md: 2.5 }, display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
                <Remove sx={{ fontSize: 18, color: 'text.disabled', mt: '2px' }} />
                <Typography sx={{ fontSize: '0.9375rem', color: 'text.secondary' }}>{before}</Typography>
              </Grid>
              <Grid item xs={12} md={6} sx={{ px: { xs: 2.5, md: 3 }, pt: { xs: 0.5, md: 2.5 }, pb: { xs: 2, md: 2.5 }, display: 'flex', gap: 1.5, alignItems: 'flex-start', borderLeft: { md: `1px solid ${PALETTE.border1}` } }}>
                <Check sx={{ fontSize: 18, color: PALETTE.green, mt: '2px' }} />
                <Typography sx={{ fontSize: '0.9375rem' }}>{after}</Typography>
              </Grid>
            </Grid>
          ))}
        </Box>
      </Section>

      {/* ── Features ── */}
      <Section id="features">
        <SectionHead label="features" title="Everything a group admin does, built in" sub="Five tools are free on every plan. Pro adds analytics, AI answers, webhooks and campaigns." />
        <Grid container sx={{ borderTop: `1px solid ${PALETTE.border1}` }}>
          {FEATURES.map((f, i) => {
            const Icon = f.icon;
            return (
              <Grid item xs={12} sm={6} md={4} key={f.title} sx={{
                py: 4, pr: { sm: 4 }, pl: { sm: i % 2 ? 4 : 0, md: i % 3 ? 4 : 0 },
                borderBottom: `1px solid ${PALETTE.border1}`,
                borderLeft: { sm: i % 2 ? `1px solid ${PALETTE.border1}` : 'none', md: i % 3 ? `1px solid ${PALETTE.border1}` : 'none' },
              }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, mb: 1.5 }}>
                  <Icon sx={{ fontSize: 18, color: 'text.secondary' }} />
                  <Typography sx={{ fontSize: '1rem', fontWeight: 500, flex: 1 }}>{f.title}</Typography>
                  <Typography sx={{ ...mono, fontSize: 12, color: f.plan === 'Pro' ? PALETTE.blueLt : 'text.disabled' }}>{f.plan}</Typography>
                </Box>
                <Typography sx={{ fontSize: '0.9375rem', color: 'text.secondary', lineHeight: 1.6 }}>{f.desc}</Typography>
              </Grid>
            );
          })}
        </Grid>
      </Section>

      {/* ── How it works ── */}
      <Section alt>
        <Grid container spacing={{ xs: 5, md: 8 }}>
          <Grid item xs={12} md={5}>
            <SectionHead label="setup" title="Running in about five minutes" sub="No code and no servers. You need a Telegram account and a group you admin." />
            <Button variant="contained" size="large" onClick={() => navigate('/register')} endIcon={<ArrowForward />} sx={{ mt: { md: -3 } }}>
              Create a free account
            </Button>
          </Grid>
          <Grid item xs={12} md={7}>
            <Box component="ol" sx={{ listStyle: 'none', p: 0, m: 0 }}>
              {STEPS.map((s, i) => (
                <Box component="li" key={s.title} sx={{ display: 'flex', gap: 3, py: 3, borderTop: `1px solid ${PALETTE.border1}`, '&:last-of-type': { borderBottom: `1px solid ${PALETTE.border1}` } }}>
                  <Typography sx={{ ...mono, fontSize: '0.875rem', color: 'text.disabled', width: 24, pt: '2px', flexShrink: 0 }}>{String(i + 1).padStart(2, '0')}</Typography>
                  <Box>
                    <Typography sx={{ fontSize: '1rem', fontWeight: 500 }}>{s.title}</Typography>
                    <Typography sx={{ fontSize: '0.9375rem', color: 'text.secondary', mt: 0.5 }}>{s.desc}</Typography>
                  </Box>
                </Box>
              ))}
            </Box>
          </Grid>
        </Grid>
      </Section>

      {/* ── Testimonials (named) or early feedback (paraphrased) ── */}
      <Section>
        {TESTIMONIALS.length > 0 ? (
          <>
            <SectionHead label="testimonials" title="What group admins say" sub="From admins running Telegizer in their communities." />
            <Grid container spacing={3}>
              {TESTIMONIALS.map((t) => (
                <Grid item xs={12} md={TESTIMONIALS.length === 2 ? 6 : 4} key={t.name}>
                  <Box component="figure" sx={{ m: 0, height: '100%', display: 'flex', flexDirection: 'column', p: 3, borderRadius: '12px', bgcolor: PALETTE.bg2, border: `1px solid ${PALETTE.border1}` }}>
                    <Typography component="blockquote" sx={{ m: 0, fontSize: '1rem', lineHeight: 1.6, flex: 1 }}>“{t.quote}”</Typography>
                    <Box component="figcaption" sx={{ mt: 3 }}>
                      <Typography sx={{ fontSize: '0.875rem', fontWeight: 500 }}>{t.name}</Typography>
                      {t.role && <Typography sx={{ fontSize: '0.8125rem', color: 'text.secondary' }}>{t.role}</Typography>}
                      {t.community && (
                        <Typography sx={{ fontSize: '0.8125rem', color: 'text.secondary' }}>
                          {t.link
                            ? <Link href={t.link} target="_blank" rel="noopener noreferrer" sx={{ color: 'inherit' }}>{t.community}</Link>
                            : t.community}
                        </Typography>
                      )}
                      {t.members && <Typography sx={{ ...mono, fontSize: 12, color: 'text.disabled', mt: 0.5 }}>{t.members}</Typography>}
                    </Box>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </>
        ) : (
          <>
            <SectionHead label="early feedback" title="What early users tell us" sub="Paraphrased from our first test communities." />
            <Grid container spacing={3}>
              {EARLY_FEEDBACK.map((t) => (
                <Grid item xs={12} md={4} key={t.context}>
                  <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', p: 3, borderRadius: '12px', bgcolor: PALETTE.bg2, border: `1px solid ${PALETTE.border1}` }}>
                    <Typography sx={{ fontSize: '1rem', lineHeight: 1.6, flex: 1 }}>“{t.text}”</Typography>
                    <Typography sx={{ fontSize: '0.8125rem', color: 'text.disabled', mt: 3 }}>{t.context}</Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </>
        )}
      </Section>

      {/* ── Pricing ── */}
      <Section alt>
        <SectionHead label="pricing" title="Start free, upgrade when the group grows" sub="Pay with 300+ cryptocurrencies. Plans never auto-renew." />
        <Grid container spacing={3}>
          {PLANS.map((plan) => (
            <Grid item xs={12} md={4} key={plan.name}>
              <Box sx={{
                height: '100%', display: 'flex', flexDirection: 'column', p: { xs: 3, md: 4 }, borderRadius: '16px',
                bgcolor: plan.popular ? PALETTE.bg3 : PALETTE.bg2,
                border: `1px solid ${plan.popular ? '#3a3b41' : PALETTE.border1}`,
                boxShadow: plan.popular ? 'inset 0 1px 0 rgba(255,255,255,0.05)' : 'none',
              }}>
                <Box sx={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                  <Typography sx={{ fontSize: '1.0625rem', fontWeight: 500 }}>{plan.name}</Typography>
                  {plan.popular && <Typography sx={{ fontSize: '0.8125rem', color: PALETTE.blueLt }}>Most popular</Typography>}
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mt: 2 }}>
                  <Typography data-figure sx={{ fontSize: '2.75rem', fontWeight: 500, lineHeight: 1, letterSpacing: '-0.02em' }}>{plan.price}</Typography>
                  <Typography sx={{ color: 'text.secondary', fontSize: '0.9375rem' }}>{plan.period}</Typography>
                </Box>
                <Typography sx={{ fontSize: '0.8125rem', color: 'text.disabled', mt: 1 }}>{plan.note}</Typography>
                <Button
                  fullWidth size="large"
                  variant={plan.popular ? 'contained' : 'outlined'}
                  sx={{ mt: 3, mb: 3 }}
                  onClick={() => navigate(plan.tier ? '/pricing' : '/register')}
                >
                  {plan.cta}
                </Button>
                <Stack spacing={1.25}>
                  {plan.features.map((f) => (
                    <Box key={f} sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                      <Check sx={{ fontSize: 16, color: 'text.secondary' }} />
                      <Typography sx={{ fontSize: '0.9375rem' }}>{f}</Typography>
                    </Box>
                  ))}
                </Stack>
              </Box>
            </Grid>
          ))}
        </Grid>
        <Typography sx={{ ...mono, fontSize: '0.8125rem', color: 'text.disabled', mt: 4 }}>
          14-day money-back guarantee · no auto-renew · every account starts with 14 days of Pro
        </Typography>
      </Section>

      {/* ── FAQ ── */}
      <Section id="faq">
        <Grid container spacing={{ xs: 4, md: 8 }}>
          <Grid item xs={12} md={4}>
            <SectionHead label="faq" title="Common questions" />
            <Typography sx={{ fontSize: '0.9375rem', color: 'text.secondary', mt: { md: -3 } }}>
              Something else? <Link component="button" onClick={() => navigate('/contact')} sx={{ color: 'text.primary', fontSize: 'inherit', verticalAlign: 'baseline' }}>Contact us</Link>
            </Typography>
          </Grid>
          <Grid item xs={12} md={8}>
            <Box sx={{ borderTop: `1px solid ${PALETTE.border1}` }}>
              {FAQ.map(({ q, a }) => (
                <Accordion key={q} disableGutters elevation={0} square
                  sx={{ bgcolor: 'transparent', border: 'none', borderRadius: '0 !important', borderBottom: `1px solid ${PALETTE.border1}` }}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ fontSize: 20 }} />} sx={{ px: 0, minHeight: 60 }}>
                    <Typography sx={{ fontSize: '1rem', fontWeight: 500, pr: 2 }}>{q}</Typography>
                  </AccordionSummary>
                  <AccordionDetails sx={{ px: 0, pt: 0, pb: 3 }}>
                    <Typography sx={{ fontSize: '0.9375rem', color: 'text.secondary', lineHeight: 1.65, maxWidth: 640 }}>{a}</Typography>
                  </AccordionDetails>
                </Accordion>
              ))}
            </Box>
          </Grid>
        </Grid>
      </Section>

      {/* ── Product family (cross-sell — hero stays focused on Telegram) ── */}
      <Section alt>
        <SectionHead label="the telegizer family" title="One toolkit for every community you run" />
        <Grid container spacing={3}>
          {PRODUCT_FAMILY.map((p) => {
            const Icon = p.icon;
            return (
              <Grid item xs={12} md={4} key={p.name}>
                <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', p: 3, borderRadius: '12px', bgcolor: PALETTE.bg2, border: `1px solid ${PALETTE.border1}` }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, mb: 1.5 }}>
                    <Icon sx={{ fontSize: 18, color: 'text.secondary' }} />
                    <Typography sx={{ fontSize: '1rem', fontWeight: 500, flex: 1 }}>{p.name}</Typography>
                    <Typography sx={{ fontSize: '0.8125rem', color: 'text.disabled' }}>{p.tag}</Typography>
                  </Box>
                  <Typography sx={{ fontSize: '0.9375rem', color: 'text.secondary', lineHeight: 1.6, flex: 1 }}>{p.desc}</Typography>
                  <Box sx={{ mt: 2.5 }}>
                    {p.to ? (
                      <Button size="small" endIcon={<ArrowForward sx={{ fontSize: '16px !important' }} />} onClick={() => navigate(p.to)} sx={{ px: 0, color: 'text.primary', '&:hover': { bgcolor: 'transparent', color: PALETTE.blueLt } }}>
                        {p.cta}
                      </Button>
                    ) : (
                      <Typography sx={{ ...mono, fontSize: '0.8125rem', color: 'text.disabled', py: 0.5 }}>you are here</Typography>
                    )}
                  </Box>
                </Box>
              </Grid>
            );
          })}
        </Grid>
      </Section>

      {/* ── Final CTA ── */}
      <Section sx={{ py: { xs: 10, md: 14 } }}>
        <Box sx={{ textAlign: 'center', maxWidth: 560, mx: 'auto' }}>
          <Typography component="h2" sx={{ fontSize: { xs: '1.875rem', md: '2.5rem' }, fontWeight: 500, lineHeight: 1.15, letterSpacing: '-0.02em' }}>
            Give your group a moderator that never logs off
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 2, fontSize: '1.0625rem' }}>
            The free plan has no time limit and needs no card.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} justifyContent="center" sx={{ mt: 4 }}>
            <Button variant="contained" size="large" onClick={() => navigate('/register')} sx={{ px: 3 }}>Create free account</Button>
            <Button variant="outlined" size="large" onClick={() => navigate('/pricing')} sx={{ px: 3 }}>See pricing</Button>
          </Stack>
        </Box>
      </Section>

      {/* ── Footer ── */}
      <Box component="footer" sx={{ borderTop: `1px solid ${PALETTE.border1}`, py: 6, bgcolor: PALETTE.bg1 }}>
        <Container maxWidth="lg" sx={{ px: { xs: 2.5, sm: 4 } }}>
          <Grid container spacing={4} alignItems="flex-start">
            <Grid item xs={12} md={4}>
              <TelegizerLogo size="sm" />
              <Typography sx={{ fontSize: '0.875rem', color: 'text.secondary', mt: 1.5 }}>Moderation and growth for Telegram groups</Typography>
            </Grid>
            <Grid item xs={12} md={8}>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, md: 3 }, justifyContent: { md: 'flex-end' } }}>
                {[
                  ['Pricing', '/pricing'], ['About', '/about'], ['Contact', '/contact'], ['Log in', '/login'], ['Register', '/register'],
                  ['Terms', '/terms'], ['Privacy', '/privacy'], ['Acceptable use', '/acceptable-use'],
                ].map(([label, to]) => (
                  <Link key={to} component="button" onClick={() => navigate(to)} underline="hover" sx={{ color: 'text.secondary', fontSize: '0.875rem', '&:hover': { color: 'text.primary' } }}>
                    {label}
                  </Link>
                ))}
              </Box>
            </Grid>
          </Grid>
          <Typography sx={{ ...mono, fontSize: '0.75rem', color: 'text.disabled', mt: 5 }}>
            © {new Date().getFullYear()} Telegizer
          </Typography>
        </Container>
      </Box>
    </Box>
  );
}

