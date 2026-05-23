import React, { useState, useEffect, useRef } from 'react';
import { useScrollReveal } from '../hooks/useScrollReveal';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  Grid, Chip, Container, Stack, Divider, Avatar,
  Accordion, AccordionSummary, AccordionDetails,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  SmartToy, Shield, Schedule, BarChart, People, CheckCircle,
  AutoAwesome, Bolt, Warning, TrendingDown, AccessTime,
  ArrowForward, CurrencyBitcoin, Lock,
} from '@mui/icons-material';
import TelegizerLogo from '../components/TelegizerLogo';
import { useNavigate } from 'react-router-dom';

const PAIN_POINTS = [
  {
    icon: <Warning fontSize="large" />,
    title: 'Spam is killing your group',
    desc: 'Bots, scammers, and link-droppers flood your chat the moment you stop watching. Manual bans don\'t scale.',
  },
  {
    icon: <TrendingDown fontSize="large" />,
    title: 'Engagement is slowly dying',
    desc: 'No consistent content, no interaction prompts, no reason to stay. Members ghost after the first week.',
  },
  {
    icon: <AccessTime fontSize="large" />,
    title: 'You\'re the bottleneck',
    desc: 'Every welcome message, every pinned post, every moderation decision — manually done by you, every day.',
  },
  {
    icon: <People fontSize="large" />,
    title: 'You have no idea what\'s working',
    desc: 'No growth metrics, no activity data, no way to know which content keeps people coming back.',
  },
];

const FEATURES = [
  {
    icon: <Shield fontSize="large" />,
    title: 'AutoMod — Set it. Forget it.',
    desc: 'Auto-remove spam, links, bad words, and media. Warn → mute → ban automatically. Your group stays clean 24/7.',
    badge: 'Most Used',
    badgeColor: 'warning',
    plan: 'Free',
  },
  {
    icon: <Schedule fontSize="large" />,
    title: 'Scheduled Content',
    desc: 'Write posts once, publish them forever. Daily updates, weekly recaps, polls — on autopilot in any timezone.',
    badge: null,
    plan: 'Free',
  },
  {
    icon: <People fontSize="large" />,
    title: 'Member System',
    desc: 'XP, levels, roles, and verification challenges. Active members get rewarded. Bad actors get removed.',
    badge: null,
    plan: 'Free',
  },
  {
    icon: <BarChart fontSize="large" />,
    title: 'Growth Analytics',
    desc: 'See exactly which invite links drive joins, peak activity hours, member retention, and moderation stats.',
    badge: null,
    plan: 'Pro',
    planColor: 'primary',
  },
  {
    icon: <AutoAwesome fontSize="large" />,
    title: 'AI Knowledge Base',
    desc: 'Upload your docs or FAQ. The bot answers member questions automatically — no human needed.',
    badge: 'Pro',
    badgeColor: 'primary',
    plan: 'Pro',
    planColor: 'primary',
  },
  {
    icon: <Bolt fontSize="large" />,
    title: 'Webhooks & Integrations',
    desc: 'Push GitHub releases, price alerts, or any API event straight to your Telegram group.',
    badge: 'Enterprise',
    badgeColor: 'secondary',
    plan: 'Enterprise',
    planColor: 'secondary',
  },
  {
    icon: <SmartToy fontSize="large" />,
    title: 'Auto Reply Triggers',
    desc: 'Define keyword triggers and the bot replies instantly. Answer FAQs, share links, or run commands — hands-free.',
    badge: null,
    plan: 'Free',
  },
  {
    icon: <Lock fontSize="large" />,
    title: 'Coordinated Campaigns',
    desc: 'Organise community participation events — like/repost campaigns, AMAs, and engagement drives. Members earn XP for taking part.',
    badge: 'Pro',
    badgeColor: 'primary',
    plan: 'Pro',
    planColor: 'primary',
  },
  {
    icon: <People fontSize="large" />,
    title: 'Invite Link Tracking',
    desc: 'Create trackable invite links and see exactly which source drives the most new members.',
    badge: null,
    plan: 'Free',
  },
];

const PLANS = [
  {
    name: 'Free',
    price: '$0',
    daily: null,
    period: 'forever',
    color: 'default',
    features: ['1 bot', '3 groups per bot', 'Basic moderation', 'Welcome messages', 'XP system'],
    cta: 'Start Free',
    ctaVariant: 'outlined',
    tier: null,
  },
  {
    name: 'Pro',
    price: '$19',
    daily: '$0.63/day',
    period: '/month',
    color: 'primary',
    popular: true,
    features: ['3 bots', 'Unlimited groups', 'Advanced AutoMod', 'Scheduled messages', 'Analytics', 'AI Knowledge Base', 'Priority support'],
    cta: 'Get Pro',
    ctaVariant: 'contained',
    tier: 'pro',
  },
  {
    name: 'Enterprise',
    price: '$49',
    daily: '$1.63/day',
    period: '/month',
    color: 'secondary',
    features: ['50 bots', 'All Pro features', 'API access', 'Webhook integrations', 'SLA guarantee', 'Dedicated support'],
    cta: 'Get Enterprise',
    ctaVariant: 'outlined',
    tier: 'enterprise',
  },
];

const STEPS = [
  { n: '1', title: 'Create your free account', desc: 'Email + password. Done in 30 seconds.' },
  { n: '2', title: 'Get a bot token from @BotFather', desc: 'Open Telegram, message @BotFather, send /newbot.' },
  { n: '3', title: 'Paste the token into Telegizer', desc: 'We connect your bot instantly. No code required.' },
  { n: '4', title: 'Add the bot to your group as admin', desc: 'Your group appears in the dashboard automatically.' },
  { n: '5', title: 'Turn on automation', desc: 'Enable AutoMod, schedule posts, track growth — done.' },
];

const EARLY_FEEDBACK = [
  {
    text: 'AutoMod cut my daily moderation work dramatically. Spam was the biggest pain point.',
    context: 'Community admin, crypto group',
  },
  {
    text: 'Scheduling posts once and forgetting about them is exactly what I needed.',
    context: 'Project founder, multiple groups',
  },
  {
    text: 'Seeing which invite links actually brought real members changed how I run growth.',
    context: 'Group owner, DeFi community',
  },
];

function StatCard({ target, label, sub, color, delay, visible, reveal }) {
  const count = useAnimatedCount(visible ? (target || 0) : 0);
  return (
    <Box sx={{
      textAlign: 'center', p: { xs: 2, sm: 2.5 },
      bgcolor: 'rgba(15,30,53,0.7)',
      borderRadius: 2,
      border: '1px solid rgba(255,255,255,0.07)',
      ...reveal(visible, delay),
    }}>
      <Typography variant="h4" fontWeight={900} color={color} sx={{ fontSize: { xs: '1.7rem', sm: '2.1rem' }, fontVariantNumeric: 'tabular-nums' }}>
        {target != null ? formatStat(count) : '—'}
      </Typography>
      <Typography variant="body2" fontWeight={600} mt={0.25}>{label}</Typography>
      <Typography variant="caption" color="text.disabled" display="block" mt={0.25} lineHeight={1.4}>{sub}</Typography>
    </Box>
  );
}

function LivePlatformStats({ proofRef, proofVisible, reveal, stats }) {
  const cards = [
    {
      key: 'groups',
      target: stats?.total_groups ?? null,
      label: 'Active groups',
      sub: 'communities managed right now',
      color: 'secondary.main',
    },
    {
      key: 'members',
      target: stats?.total_members ?? null,
      label: 'Members managed',
      sub: 'total across all groups',
      color: 'primary.main',
    },
    {
      key: 'mod',
      target: stats?.total_mod_actions ?? null,
      label: 'Mod actions taken',
      sub: 'spam removed, bans, mutes — automated',
      color: 'success.main',
    },
    {
      key: 'ai',
      target: stats?.total_ai_replies ?? null,
      label: 'Auto-replies fired',
      sub: 'bot answered so admins didn\'t have to',
      color: 'warning.main',
    },
  ];

  const updatedAt = stats?.updated_at
    ? new Date(stats.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null;

  return (
    <Box ref={proofRef} sx={{ bgcolor: '#060e1c', borderBottom: '1px solid', borderColor: 'divider', py: { xs: 5, md: 7 } }}>
      <Container maxWidth="md">
        <Box sx={{ textAlign: 'center', mb: 4, ...reveal(proofVisible) }}>
          <Chip
            label={updatedAt ? `Live · Updated at ${updatedAt}` : 'Live platform data'}
            size="small"
            sx={{
              bgcolor: 'rgba(33,150,243,0.1)', color: 'primary.light',
              fontWeight: 600, border: '1px solid rgba(33,150,243,0.25)', mb: 1.5,
            }}
          />
          <Typography variant="h5" fontWeight={800}>
            A growing platform. Real numbers.
          </Typography>
          <Typography variant="body2" color="text.secondary" mt={0.5}>
            Every group added increases these counters. These are live totals from the Telegizer platform.
          </Typography>
        </Box>
        <Grid container spacing={2} justifyContent="center">
          {cards.map((c, i) => (
            <Grid item xs={6} sm={3} key={c.key}>
              <StatCard {...c} delay={i * 70} visible={proofVisible} reveal={reveal} />
            </Grid>
          ))}
        </Grid>
        {stats?.new_groups_this_week > 0 && (
          <Box sx={{ textAlign: 'center', mt: 3, ...reveal(proofVisible, 350) }}>
            <Typography variant="caption" color="text.disabled">
              +{stats.new_groups_this_week} new group{stats.new_groups_this_week !== 1 ? 's' : ''} joined this week
            </Typography>
          </Box>
        )}
      </Container>
    </Box>
  );
}

function useAnimatedCount(target, duration = 1400) {
  const [display, setDisplay] = useState(0);
  const frameRef = useRef(null);
  useEffect(() => {
    if (!target) { setDisplay(0); return; }
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
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M+';
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, '') + 'K+';
  return n.toLocaleString();
}

export default function Landing() {
  const navigate = useNavigate();
  const token = localStorage.getItem('token');

  const [platformStats, setPlatformStats] = useState(null);
  const [statsRef, statsVisible] = useScrollReveal(0.15);
  const [proofRef, proofVisible] = useScrollReveal(0.1);
  const [painRef, painVisible] = useScrollReveal(0.08);
  const [solutionRef, solutionVisible] = useScrollReveal(0.15);
  const [featuresRef, featuresVisible] = useScrollReveal(0.05);
  const [stepsRef, stepsVisible] = useScrollReveal(0.1);
  const [testimonialsRef, testimonialsVisible] = useScrollReveal(0.1);
  const [pricingRef, pricingVisible] = useScrollReveal(0.05);
  const [faqRef, faqVisible] = useScrollReveal(0.1);
  const [ctaRef, ctaVisible] = useScrollReveal(0.15);

  useEffect(() => {
    const base = process.env.REACT_APP_API_URL || '';
    fetch(`${base}/api/platform-stats`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setPlatformStats(data); })
      .catch(() => {});
  }, []);

  const reveal = (visible, delay = 0) => ({
    opacity: visible ? 1 : 0,
    transform: visible ? 'none' : 'translateY(22px)',
    transition: `opacity 0.55s ease ${delay}ms, transform 0.55s cubic-bezier(0.22,1,0.36,1) ${delay}ms`,
  });

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>

      {/* â"€â"€ Nav â"€â"€ */}
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.default' }}>
        <Toolbar sx={{ maxWidth: 1200, mx: 'auto', width: '100%', px: { xs: 2, md: 3 } }}>
          <Box sx={{ flexGrow: 1 }}>
            <TelegizerLogo size="md" />
          </Box>
          <Button onClick={() => navigate('/directory')} sx={{ mr: 1, display: { xs: 'none', md: 'inline-flex' }, color: 'text.secondary' }}>
            Directory
          </Button>
          <Button onClick={() => navigate('/pricing')} sx={{ mr: 1, display: { xs: 'none', sm: 'inline-flex' }, color: 'text.secondary' }}>
            Pricing
          </Button>
          {token ? (
            <Button variant="contained" onClick={() => navigate('/dashboard')}>
              Dashboard
            </Button>
          ) : (
            <Stack direction="row" spacing={1}>
              <Button onClick={() => navigate('/login')} sx={{ color: 'text.secondary' }}>Sign In</Button>
              <Button variant="contained" onClick={() => navigate('/register')}>
                Start Free
              </Button>
            </Stack>
          )}
        </Toolbar>
      </AppBar>

      {/* â"€â"€ Hero â"€â"€ */}
      <Box
        sx={{
          background: 'linear-gradient(160deg, #0d1117 0%, #0d1b2e 50%, #0d1117 100%)',
          pt: { xs: 8, md: 14 },
          pb: { xs: 8, md: 14 },
          textAlign: 'center',
          px: 2,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Background glow */}
        <Box sx={{
          position: 'absolute', top: '20%', left: '50%', transform: 'translateX(-50%)',
          width: { xs: '90vw', sm: 500, md: 600 }, height: { xs: 180, sm: 240, md: 300 },
          borderRadius: '50%',
          background: 'radial-gradient(ellipse, rgba(33,150,243,0.12) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />
        <Container maxWidth="md" sx={{ position: 'relative' }}>
          <Chip
            label="Built for Telegram community managers"
            size="small"
            sx={{ mb: 3, bgcolor: 'rgba(33,150,243,0.12)', color: 'primary.light', fontWeight: 600, border: '1px solid rgba(33,150,243,0.3)' }}
          />
          <Typography
            variant="h1"
            fontWeight={900}
            mb={2.5}
            sx={{ fontSize: { xs: '2.2rem', sm: '3rem', md: '3.75rem' }, lineHeight: 1.1, letterSpacing: '-0.02em' }}
          >
            Manage Your Telegram Group{' '}
            <Box component="span" className="gradient-text">
              Without the Manual Work
            </Box>
          </Typography>
          <Typography
            variant="h5"
            color="text.secondary"
            mb={1.5}
            sx={{ fontWeight: 400, fontSize: { xs: '1.1rem', md: '1.3rem' } }}
          >
            Moderation, scheduling, and analytics — handled automatically.
          </Typography>
          <Typography
            variant="body1"
            color="text.disabled"
            mb={5}
            sx={{ maxWidth: 520, mx: 'auto', lineHeight: 1.7 }}
          >
            Telegizer connects to your Telegram bot and automates moderation, scheduled posts,
            member management, and analytics — from a single dashboard.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center" mb={3}>
            <Button
              variant="contained"
              size="large"
              onClick={() => navigate('/register')}
              endIcon={<ArrowForward />}
              sx={{ py: { xs: 1.25, sm: 1.75 }, px: { xs: 2.5, sm: 4 }, fontSize: { xs: '0.92rem', sm: '1.05rem' }, fontWeight: 700 }}
            >
              Start Free — Takes 60 Seconds
            </Button>
            <Button
              variant="outlined"
              size="large"
              onClick={() => navigate('/pricing')}
              sx={{ py: { xs: 1.25, sm: 1.75 }, px: { xs: 2.5, sm: 4 }, fontSize: { xs: '0.92rem', sm: '1.05rem' } }}
            >
              View Pricing
            </Button>
          </Stack>
          <Typography variant="caption" color="text.disabled">
            No credit card required · Free plan, forever · Pay with 300+ cryptos · No auto-renew
          </Typography>
        </Container>

        {/* Dashboard preview — floating cards, no browser chrome */}
        <Box sx={{ mt: 7, mx: 'auto', maxWidth: 860, px: { xs: 2, md: 0 }, position: 'relative' }}>
          <Typography variant="caption" color="text.disabled" display="block" textAlign="center" mb={2}>
            Example dashboard — illustrative data only
          </Typography>
          {/* Fade-out bottom overlay */}
          <Box sx={{
            position: 'absolute', bottom: 0, left: 0, right: 0, height: 100, zIndex: 1,
            background: 'linear-gradient(transparent, #0d1117)',
            pointerEvents: 'none',
          }} />
          <Box sx={{ p: 2.5, bgcolor: 'rgba(15,30,53,0.6)', borderRadius: 3, border: '1px solid rgba(61,142,248,0.12)', boxShadow: '0 0 60px rgba(37,99,235,0.12), 0 24px 80px rgba(0,0,0,0.5)' }}>
              {/* Stat cards row */}
              <Grid container spacing={1.5} mb={2}>
                {[
                  { label: 'Members', value: '12,847', delta: '+214 today', color: 'primary.main' },
                  { label: 'Spam Blocked', value: '1,392', delta: 'this month', color: 'success.main' },
                  { label: 'Messages', value: '84,210', delta: 'last 30 days', color: 'info.main' },
                  { label: 'Active Groups', value: '3', delta: 'all healthy', color: 'secondary.main' },
                ].map(s => (
                  <Grid item xs={6} sm={3} key={s.label}>
                    <Box sx={{ bgcolor: '#1e293b', borderRadius: 2, p: 1.5, border: '1px solid rgba(255,255,255,0.06)' }}>
                      <Typography variant="caption" color="text.secondary" display="block">{s.label}</Typography>
                      <Typography fontWeight={800} sx={{ fontSize: '1.25rem', color: s.color }}>{s.value}</Typography>
                      <Typography variant="caption" color="text.disabled">{s.delta}</Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
              {/* Chart + activity row */}
              <Grid container spacing={1.5}>
                <Grid item xs={12} sm={8}>
                  <Box sx={{ bgcolor: '#1e293b', borderRadius: 2, p: 2, border: '1px solid rgba(255,255,255,0.06)', height: 120 }}>
                    <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1.5}>Member Growth</Typography>
                    {/* Simulated bar chart */}
                    <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: '4px', height: 72 }}>
                      {[40, 55, 48, 70, 62, 85, 78, 95, 88, 100, 92, 110].map((h, i) => (
                        <Box key={i} sx={{ flex: 1, bgcolor: i === 11 ? 'primary.main' : 'rgba(37,99,235,0.35)', borderRadius: '3px 3px 0 0', height: `${h}%`, transition: 'height 0.3s' }} />
                      ))}
                    </Box>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Box sx={{ bgcolor: '#1e293b', borderRadius: 2, p: 2, border: '1px solid rgba(255,255,255,0.06)', height: 120 }}>
                    <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1}>Recent Actions</Typography>
                    {[
                      { text: 'Spam removed', color: 'error.main' },
                      { text: 'New member joined', color: 'success.main' },
                      { text: 'Post scheduled', color: 'primary.main' },
                      { text: 'Raid launched', color: 'warning.main' },
                    ].map((item, i) => (
                      <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                        <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: item.color, flexShrink: 0 }} />
                        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.75rem' }}>{item.text}</Typography>
                      </Box>
                    ))}
                  </Box>
                </Grid>
              </Grid>
            </Box>
          </Box>
        </Box>

      {/* â"€â"€ Stats Strip â"€â"€ */}
      <Box ref={statsRef} sx={{ bgcolor: '#0b1626', borderTop: '1px solid', borderBottom: '1px solid', borderColor: 'divider', py: 3, ...reveal(statsVisible) }}>
        <Container maxWidth="md">
          <Grid container justifyContent="center" spacing={0}>
            {[
              { value: '300+', label: 'Cryptos Accepted' },
              { value: '17+', label: 'Bot Features' },
              { value: '24/7', label: 'Always Running' },
              { value: '5 min', label: 'Setup Time' },
            ].map((s, i) => (
              <Grid item xs={6} sm={3} key={s.label} sx={{
                textAlign: 'center', py: 1.5,
                borderLeft: { xs: i % 2 !== 0 ? '1px solid' : 'none', sm: i > 0 ? '1px solid' : 'none' },
                borderTop: { xs: i >= 2 ? '1px solid' : 'none', sm: 'none' },
                borderColor: 'divider',
              }}>
                <Typography variant="h4" fontWeight={800} color="primary.main" sx={{ fontSize: { xs: '1.6rem', sm: '2rem', md: '2.125rem' } }}>{s.value}</Typography>
                <Typography variant="caption" color="text.secondary">{s.label}</Typography>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* ── Live Platform Stats ── */}
      <LivePlatformStats proofRef={proofRef} proofVisible={proofVisible} reveal={reveal} stats={platformStats} />

      {/* ── Pain ── */}
      <Box sx={{ bgcolor: '#07101f' }}>
        <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
          <Box ref={painRef} sx={{ textAlign: 'center', mb: 6, ...reveal(painVisible) }}>
            <Typography variant="overline" color="error.main" fontWeight={700} letterSpacing={2}>
              The Problem
            </Typography>
            <Typography variant="h4" fontWeight={800} mt={1} mb={1.5}>
              Managing a Telegram group shouldn't feel like a full-time job
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 560, mx: 'auto' }}>
              If you're running a community without automation, here's what your day looks like:
            </Typography>
          </Box>
          <Grid container spacing={3}>
            {PAIN_POINTS.map((p, i) => (
              <Grid item xs={12} sm={6} key={p.title} sx={reveal(painVisible, i * 80)}>
                <Card sx={{ height: '100%', p: { xs: 1.5, sm: 1 }, borderColor: 'rgba(211,47,47,0.2)', bgcolor: 'rgba(211,47,47,0.03)' }}>
                  <CardContent>
                    <Box sx={{ color: 'error.main', mb: 1.5 }}>{p.icon}</Box>
                    <Typography variant="h6" fontWeight={700} mb={1}>{p.title}</Typography>
                    <Typography variant="body2" color="text.secondary" lineHeight={1.7}>{p.desc}</Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* â"€â"€ Solution bridge â"€â"€ */}
      <Box ref={solutionRef} sx={{ bgcolor: '#0b1626', borderTop: '1px solid', borderBottom: '1px solid', borderColor: 'divider', py: { xs: 6, md: 8 }, textAlign: 'center', px: 2, ...reveal(solutionVisible) }}>
        <Container maxWidth="sm">
          <Typography variant="overline" color="success.main" fontWeight={700} letterSpacing={2}>
            How It Helps
          </Typography>
          <Typography variant="h4" fontWeight={800} mt={1} mb={2}>
            Replace repetitive tasks with{' '}
            <Box component="span" className="gradient-text">reliable automation</Box>
          </Typography>
          <Typography variant="body1" color="text.secondary" lineHeight={1.8}>
            Connect your Telegram bot and configure what you want automated — spam removal,
            scheduled posts, welcome messages, analytics. Telegizer runs it in the background
            so you can focus on your community, not the admin work.
          </Typography>
        </Container>
      </Box>

      {/* â"€â"€ Features â"€â"€ */}
      <Box sx={{ bgcolor: '#07101f' }}>
        <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
          <Box ref={featuresRef} sx={{ textAlign: 'center', mb: 6, ...reveal(featuresVisible) }}>
            <Typography variant="overline" color="primary.main" fontWeight={700} letterSpacing={2}>
              Features
            </Typography>
            <Typography variant="h4" fontWeight={800} mt={1} mb={1}>
              One dashboard.{' '}
              <Box component="span" className="gradient-text">Full control.</Box>
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Everything your community needs, built in — no plugins, no integrations required.
            </Typography>
          </Box>
          <Grid container spacing={3}>
            {FEATURES.map((f, i) => (
              <Grid item xs={12} sm={6} md={4} key={f.title} sx={reveal(featuresVisible, (i % 3) * 70)}>
                <Card sx={{ height: '100%', p: 1, position: 'relative' }}>
                  {(f.badge || f.plan) && (
                    <Box sx={{ position: 'absolute', top: 12, right: 12, display: 'flex', gap: 0.5 }}>
                      {f.badge ? (
                        <Chip label={f.badge} size="small" color={f.badgeColor || 'primary'} sx={{ fontSize: 11, height: 20 }} />
                      ) : (
                        <Chip label={f.plan} size="small" color={f.planColor || 'default'} variant="outlined" sx={{ fontSize: 11, height: 20 }} />
                      )}
                    </Box>
                  )}
                  <CardContent sx={{ pt: (f.badge || f.plan) ? 4.5 : 2 }}>
                    <Box sx={{ color: 'primary.main', mb: 1.5 }}>{f.icon}</Box>
                    <Typography variant="h6" fontWeight={700} mb={1}>{f.title}</Typography>
                    <Typography variant="body2" color="text.secondary" lineHeight={1.7}>{f.desc}</Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* â"€â"€ How It Works â"€â"€ */}
      <Box sx={{ bgcolor: '#0b1626', borderTop: '1px solid', borderColor: 'divider', py: { xs: 8, md: 10 } }}>
        <Container maxWidth="sm">
          <Box ref={stepsRef} sx={{ textAlign: 'center', mb: 6, ...reveal(stepsVisible) }}>
            <Typography variant="overline" color="primary.main" fontWeight={700} letterSpacing={2}>
              Setup
            </Typography>
            <Typography variant="h4" fontWeight={800} mt={1} mb={1}>
              Up and running in 5 minutes
            </Typography>
            <Typography variant="body1" color="text.secondary">
              No coding. No DevOps. Just connect and automate.
            </Typography>
          </Box>
          <Stack spacing={3}>
            {STEPS.map((s, i) => (
              <Box key={s.n} sx={{ display: 'flex', alignItems: 'flex-start', gap: 2, ...reveal(stepsVisible, i * 60) }}>
                <Avatar sx={{ bgcolor: 'primary.main', width: 36, height: 36, fontSize: '0.9rem', fontWeight: 800, flexShrink: 0 }}>
                  {s.n}
                </Avatar>
                <Box>
                  <Typography fontWeight={700} mb={0.25}>{s.title}</Typography>
                  <Typography variant="body2" color="text.secondary">{s.desc}</Typography>
                </Box>
              </Box>
            ))}
          </Stack>
          <Box sx={{ textAlign: 'center', mt: 5, ...reveal(stepsVisible, STEPS.length * 60) }}>
            <Button
              variant="contained"
              size="large"
              onClick={() => navigate('/register')}
              endIcon={<ArrowForward />}
              sx={{ py: 1.5, px: 4 }}
            >
              Get Started Free
            </Button>
          </Box>
        </Container>
      </Box>

      {/* â"€â"€ Social Proof â"€â"€ */}
      <Box sx={{ bgcolor: '#07101f' }}>
        <Container maxWidth="lg" sx={{ py: { xs: 8, md: 10 } }}>
          <Box ref={testimonialsRef} sx={{ textAlign: 'center', mb: 6, ...reveal(testimonialsVisible) }}>
            <Typography variant="overline" color="primary.main" fontWeight={700} letterSpacing={2}>
              Early Feedback
            </Typography>
            <Typography variant="h4" fontWeight={800} mt={1}>
              What community admins say
            </Typography>
            <Typography variant="caption" color="text.disabled" display="block" mt={1}>
              Paraphrased from real user feedback. Names withheld for privacy.
            </Typography>
          </Box>
          <Grid container spacing={3}>
            {EARLY_FEEDBACK.map((t, i) => (
              <Grid item xs={12} sm={6} md={4} key={i} sx={reveal(testimonialsVisible, i * 90)}>
                <Card sx={{ height: '100%', p: 1 }}>
                  <CardContent>
                    <Typography variant="body1" color="text.primary" lineHeight={1.7} mb={2} sx={{ fontStyle: 'italic' }}>
                      "{t.text}"
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    <Typography variant="caption" color="text.secondary">{t.context}</Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* â"€â"€ Pricing â"€â"€ */}
      <Box sx={{ bgcolor: '#0b1626', borderTop: '1px solid', borderColor: 'divider', py: { xs: 8, md: 12 } }}>
        <Container maxWidth="lg">
          <Box ref={pricingRef} sx={{ textAlign: 'center', mb: 6, ...reveal(pricingVisible) }}>
            <Typography variant="overline" color="primary.main" fontWeight={700} letterSpacing={2}>
              Pricing
            </Typography>
            <Typography variant="h4" fontWeight={800} mt={1} mb={1}>
              Simple,{' '}
              <Box component="span" className="gradient-text">transparent pricing</Box>
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Start free. Upgrade when you need more. No surprises.
            </Typography>
          </Box>
          <Grid container spacing={3} justifyContent="center">
            {PLANS.map((plan, i) => (
              <Grid item xs={12} sm={6} md={4} key={plan.name} sx={reveal(pricingVisible, i * 90)}>
                <Box sx={{ position: 'relative', pt: '14px', height: '100%' }}>
                  {plan.popular && (
                    <Chip
                      label="Most Popular"
                      color="primary"
                      size="small"
                      sx={{
                        position: 'absolute',
                        top: 0,
                        left: '50%',
                        transform: 'translateX(-50%)',
                        zIndex: 1,
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                      }}
                    />
                  )}
                  <Card
                    sx={{
                      height: '100%',
                      display: 'flex',
                      flexDirection: 'column',
                      border: plan.popular ? '2px solid' : '1px solid',
                      borderColor: plan.popular ? 'primary.main' : 'divider',
                    }}
                  >
                  <CardContent sx={{ flexGrow: 1, p: 3 }}>
                    <Typography variant="h5" fontWeight={800} mb={0.5}>{plan.name}</Typography>
                    <Box sx={{ mb: 0.5 }}>
                      <Typography component="span" variant="h3" fontWeight={900}>{plan.price}</Typography>
                      <Typography component="span" variant="body1" color="text.secondary">{plan.period}</Typography>
                    </Box>
                    {plan.daily && (
                      <Typography variant="caption" color="text.disabled" display="block" mb={2}>
                        That's only {plan.daily}
                      </Typography>
                    )}
                    <Button
                      fullWidth
                      variant={plan.ctaVariant}
                      color={plan.color === 'default' ? 'inherit' : plan.color}
                      size="large"
                      sx={{ mb: 3, fontWeight: 700 }}
                      onClick={() => plan.tier ? navigate('/pricing') : navigate('/register')}
                    >
                      {plan.cta}
                    </Button>
                    <Stack spacing={1}>
                      {plan.features.map((f) => (
                        <Box key={f} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <CheckCircle fontSize="small" color="success" />
                          <Typography variant="body2">{f}</Typography>
                        </Box>
                      ))}
                    </Stack>
                  </CardContent>
                  </Card>
                </Box>
              </Grid>
            ))}
          </Grid>
          <Box sx={{ textAlign: 'center', mt: 4 }}>
            <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: { xs: 1.5, sm: 3 }, flexWrap: 'wrap', justifyContent: 'center' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                <CurrencyBitcoin fontSize="small" color="warning" />
                <Typography variant="body2" color="text.secondary">300+ cryptos accepted</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                <Lock fontSize="small" color="success" />
                <Typography variant="body2" color="text.secondary">14-day money-back guarantee</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                <CheckCircle fontSize="small" color="primary" />
                <Typography variant="body2" color="text.secondary">No auto-renew</Typography>
              </Box>
            </Box>
          </Box>
        </Container>
      </Box>

      {/* â"€â"€ FAQ â"€â"€ */}
      <Box ref={faqRef} sx={{ py: { xs: 8, md: 10 }, bgcolor: '#07101f', ...reveal(faqVisible) }}>
        <Container maxWidth="md">
          <Typography variant="overline" color="primary.main" fontWeight={700} display="block" textAlign="center">
            FAQ
          </Typography>
          <Typography variant="h4" fontWeight={800} textAlign="center" mb={5}>
            Frequently asked questions
          </Typography>
          {[
            {
              q: 'Is it safe to add the bot as admin?',
              a: 'Yes. Telegizer only requests the Telegram permissions it needs: delete messages, ban/restrict users, pin messages, and invite links. We never read private messages or access group data outside the scope of bot commands.'
            },
            {
              q: 'Which Telegram permissions does the bot need?',
              a: 'At minimum: Delete messages, Restrict members, Pin messages, and Add members. For invite link tracking you also need Invite users via link. You can see the exact prompt when you make the bot admin.'
            },
            {
              q: 'What happens if I cancel or my plan expires?',
              a: 'Your bots continue to run but paid features (scheduled messages, advanced moderation, analytics, etc.) become read-only. You keep your free plan features indefinitely. You can renew at any time and everything comes back immediately.'
            },
            {
              q: 'What coins and payment methods are supported?',
              a: 'Payments are processed via NOWPayments and support USDT, BTC, ETH, BNB, TRX, SOL, and 300+ other coins. Card payments are not available at this time.'
            },
            {
              q: 'How long do crypto payment confirmations take?',
              a: 'Most payments confirm in 1—10 minutes. Some networks (Bitcoin, Ethereum) may take 10—30+ minutes during congestion. Your plan activates automatically once the blockchain confirms the transaction.'
            },
            {
              q: 'Can I manage multiple groups with one bot?',
              a: 'Yes. One bot can be added to unlimited Telegram groups. Each group has its own settings, moderation rules, XP system, and scheduled content. Pro plan supports up to 5 bots; Enterprise supports 50.'
            },
            {
              q: 'What is included in Free vs Pro vs Enterprise?',
              a: 'Free: 1 bot, basic moderation, welcome messages, XP system. Pro ($19/mo): 3 bots, unlimited groups, advanced AutoMod, scheduled messages, analytics, AI knowledge base. Enterprise ($49/mo): 50 bots, all Pro features plus API access, dedicated support, SLA.'
            },
            {
              q: 'Do you store my bot token securely?',
              a: 'Yes. Bot tokens are encrypted at rest using AES-256 (Fernet) before being written to the database. Your token is never stored in plain text and is never exposed in API responses.'
            },
            {
              q: 'Can I change the timezone for scheduled posts?',
              a: 'Yes. You can set a default timezone per group (under Automation â€º Scheduler). You can also override the timezone for each individual scheduled message or poll.'
            },
          ].map(({ q, a }) => (
            <Accordion key={q} disableGutters elevation={0}
              sx={{ border: '1px solid', borderColor: 'divider', mb: 1, borderRadius: '8px !important', '&:before': { display: 'none' } }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography fontWeight={600}>{q}</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Typography variant="body2" color="text.secondary" lineHeight={1.7}>{a}</Typography>
              </AccordionDetails>
            </Accordion>
          ))}
        </Container>
      </Box>

      {/* ── Community Directory callout ── */}
      <Box sx={{ py: { xs: 6, md: 8 }, px: 2, textAlign: 'center', bgcolor: '#0b1626', borderTop: '1px solid', borderColor: 'divider' }}>
        <Container maxWidth="sm">
          <Chip label="Community Directory" size="small" sx={{ mb: 2, bgcolor: 'rgba(33,150,243,0.1)', color: 'primary.light', fontWeight: 600, border: '1px solid rgba(33,150,243,0.25)' }} />
          <Typography variant="h5" fontWeight={800} mb={1.5}>
            Discover Telegram Communities
          </Typography>
          <Typography variant="body1" color="text.secondary" mb={3} lineHeight={1.7}>
            Explore Telegram groups and channels — filtered by category, country, and size.
            List your community for free to help people find it.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center">
            <Button variant="contained" size="large" onClick={() => navigate('/directory')} endIcon={<ArrowForward />} sx={{ py: 1.5, px: 3 }}>
              Browse Directory
            </Button>
            <Button variant="outlined" size="large" onClick={() => navigate('/register')} sx={{ py: 1.5, px: 3 }}>
              List Your Community
            </Button>
          </Stack>
        </Container>
      </Box>

      {/* ── Final CTA ── */}
      <Box
        ref={ctaRef}
        sx={{
          background: 'linear-gradient(135deg, #0d2a5a 0%, #1a1a6e 40%, #2d1060 70%, #0a2040 100%)',
          backgroundSize: '200% 200%',
          animation: 'gradientShift 10s ease infinite',
          py: { xs: 8, md: 10 },
          textAlign: 'center',
          px: 2,
          position: 'relative',
          overflow: 'hidden',
          ...reveal(ctaVisible),
        }}
      >
        {/* Ambient orb — top right */}
        <Box sx={{
          position: 'absolute', top: -60, right: -60, width: 340, height: 340,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(157,108,247,0.22) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />
        {/* Ambient orb — bottom left */}
        <Box sx={{
          position: 'absolute', bottom: -80, left: -80, width: 400, height: 400,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(61,142,248,0.18) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />
        <Container maxWidth="sm" sx={{ position: 'relative' }}>
          <Typography variant="h4" fontWeight={800} color="white" mb={2}>
            Stop managing your community by hand
          </Typography>
          <Typography variant="body1" sx={{ color: 'rgba(255,255,255,0.75)', mb: 4, lineHeight: 1.7 }}>
            Your first bot is free — no credit card, no setup complexity. Takes 60 seconds.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center">
            <Button
              variant="contained"
              size="large"
              onClick={() => navigate('/register')}
              endIcon={<ArrowForward />}
              sx={{ bgcolor: 'white', color: '#0d2a5a', py: { xs: 1.25, sm: 1.75 }, px: { xs: 2.5, sm: 4 }, fontWeight: 700, '&:hover': { bgcolor: '#e8f0ff', transform: 'translateY(-1px)' } }}
            >
              Create Free Account
            </Button>
            <Button
              variant="outlined"
              size="large"
              onClick={() => navigate('/pricing')}
              sx={{ borderColor: 'rgba(255,255,255,0.35)', color: 'white', py: { xs: 1.25, sm: 1.75 }, px: { xs: 2.5, sm: 4 }, '&:hover': { borderColor: 'rgba(255,255,255,0.7)', bgcolor: 'rgba(255,255,255,0.07)' } }}
            >
              See Pricing
            </Button>
          </Stack>
        </Container>
      </Box>

      {/* â"€â"€ Footer â"€â"€ */}
      <Box sx={{ bgcolor: '#07101f', borderTop: '1px solid', borderColor: 'divider', py: 4 }}>
        <Container maxWidth="lg">
          <Grid container alignItems="center" spacing={2}>
            <Grid item xs={12} sm="auto">
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <TelegizerLogo size="sm" />
              </Box>
              <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>
                Automate your Telegram community
              </Typography>
            </Grid>
            <Grid item xs={12} sm sx={{ textAlign: { xs: 'left', sm: 'center' } }}>
              <Stack direction="row" spacing={1} flexWrap="wrap" justifyContent={{ xs: 'flex-start', sm: 'center' }}>
                <Button size="small" onClick={() => navigate('/directory')} sx={{ color: 'text.secondary' }}>Directory</Button>
                <Button size="small" onClick={() => navigate('/pricing')} sx={{ color: 'text.secondary' }}>Pricing</Button>
                <Button size="small" onClick={() => navigate('/login')} sx={{ color: 'text.secondary' }}>Sign In</Button>
                <Button size="small" onClick={() => navigate('/register')} sx={{ color: 'text.secondary' }}>Register</Button>
                <Button size="small" onClick={() => navigate('/terms')} sx={{ color: 'text.secondary' }}>Terms</Button>
                <Button size="small" onClick={() => navigate('/privacy')} sx={{ color: 'text.secondary' }}>Privacy</Button>
              </Stack>
            </Grid>
            <Grid item xs={12} sm="auto" sx={{ textAlign: { xs: 'left', sm: 'right' } }}>
              <Typography variant="caption" color="text.disabled">
                © {new Date().getFullYear()} Telegizer. All rights reserved.
              </Typography>
            </Grid>
          </Grid>
        </Container>
      </Box>

    </Box>
  );
}
