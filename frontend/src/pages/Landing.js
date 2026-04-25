import React, { useState } from 'react';
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
    title: 'Raid Coordinator',
    desc: 'Launch coordinated community raids on Twitter/X. Members earn XP for participating — gamified growth.',
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
    features: ['1 bot', '1 group per bot', 'Basic moderation', 'Welcome messages', 'XP system'],
    cta: 'Start Free',
    ctaVariant: 'outlined',
    tier: null,
  },
  {
    name: 'Pro',
    price: '$9',
    daily: '$0.30/day',
    period: '/month',
    color: 'primary',
    popular: true,
    features: ['5 bots', 'Unlimited groups', 'Advanced AutoMod', 'Scheduled messages', 'Analytics', 'AI Knowledge Base', 'Priority support'],
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

const TESTIMONIALS = [
  {
    name: 'Alex K.',
    role: 'Crypto community admin — 12,000 members',
    text: 'AutoMod alone saved me 2 hours a day. Spam dropped by 90% in the first week.',
  },
  {
    name: 'Maria S.',
    role: 'NFT project founder — 3 groups',
    text: 'Scheduling daily updates used to take me an hour every morning. Now it runs itself.',
  },
  {
    name: 'James R.',
    role: 'DeFi project — 5 communities',
    text: 'The analytics finally showed me which invite links were actually bringing in real members.',
  },
];

export default function Landing() {
  const navigate = useNavigate();
  const token = localStorage.getItem('token');

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>

      {/* â"€â"€ Nav â"€â"€ */}
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.default' }}>
        <Toolbar sx={{ maxWidth: 1200, mx: 'auto', width: '100%', px: { xs: 2, md: 3 } }}>
          <Box sx={{ flexGrow: 1 }}>
            <TelegizerLogo size="md" />
          </Box>
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
            label="âœ¦  Built for Telegram communities"
            size="small"
            sx={{ mb: 3, bgcolor: 'rgba(33,150,243,0.12)', color: 'primary.light', fontWeight: 600, border: '1px solid rgba(33,150,243,0.3)' }}
          />
          <Typography
            variant="h1"
            fontWeight={900}
            mb={2.5}
            sx={{ fontSize: { xs: '2.2rem', sm: '3rem', md: '3.75rem' }, lineHeight: 1.1, letterSpacing: '-0.02em' }}
          >
            Turn Your Telegram Group{' '}
            <Box component="span" sx={{ color: 'primary.main' }}>
              Into a Growth Machine
            </Box>
          </Typography>
          <Typography
            variant="h5"
            color="text.secondary"
            mb={1.5}
            sx={{ fontWeight: 400, fontSize: { xs: '1.1rem', md: '1.3rem' } }}
          >
            No spam. No manual work. Just growth.
          </Typography>
          <Typography
            variant="body1"
            color="text.disabled"
            mb={5}
            sx={{ maxWidth: 520, mx: 'auto', lineHeight: 1.7 }}
          >
            Telegizer automates moderation, scheduling, member management, and analytics
            for every Telegram group you run — from one dashboard.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center" mb={3}>
            <Button
              variant="contained"
              size="large"
              onClick={() => navigate('/register')}
              endIcon={<ArrowForward />}
              sx={{ py: 1.75, px: 4, fontSize: '1.05rem', fontWeight: 700 }}
            >
              Start Free — Takes 60 Seconds
            </Button>
            <Button
              variant="outlined"
              size="large"
              onClick={() => navigate('/pricing')}
              sx={{ py: 1.75, px: 4, fontSize: '1.05rem' }}
            >
              View Pricing
            </Button>
          </Stack>
          <Typography variant="caption" color="text.disabled">
            No credit card required · Free plan, forever · Upgrade anytime with crypto
          </Typography>
        </Container>
      </Box>

      {/* â"€â"€ Stats Strip â"€â"€ */}
      <Box sx={{ bgcolor: 'background.paper', borderTop: '1px solid', borderBottom: '1px solid', borderColor: 'divider', py: 3 }}>
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

      {/* â"€â"€ Pain â"€â"€ */}
      <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
        <Box sx={{ textAlign: 'center', mb: 6 }}>
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
          {PAIN_POINTS.map((p) => (
            <Grid item xs={12} sm={6} key={p.title}>
              <Card sx={{ height: '100%', p: 1, borderColor: 'rgba(211,47,47,0.2)', bgcolor: 'rgba(211,47,47,0.03)' }}>
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

      {/* â"€â"€ Solution bridge â"€â"€ */}
      <Box sx={{ bgcolor: 'background.paper', borderTop: '1px solid', borderBottom: '1px solid', borderColor: 'divider', py: { xs: 6, md: 8 }, textAlign: 'center', px: 2 }}>
        <Container maxWidth="sm">
          <Typography variant="overline" color="success.main" fontWeight={700} letterSpacing={2}>
            The Solution
          </Typography>
          <Typography variant="h4" fontWeight={800} mt={1} mb={2}>
            Telegizer handles everything you're doing manually — automatically
          </Typography>
          <Typography variant="body1" color="text.secondary" lineHeight={1.8}>
            More automation → more consistent engagement → more trust → more members who stay.
            That's the growth loop Telegizer puts in motion the moment you connect your first bot.
          </Typography>
        </Container>
      </Box>

      {/* â"€â"€ Features â"€â"€ */}
      <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
        <Box sx={{ textAlign: 'center', mb: 6 }}>
          <Typography variant="overline" color="primary.main" fontWeight={700} letterSpacing={2}>
            Features
          </Typography>
          <Typography variant="h4" fontWeight={800} mt={1} mb={1}>
            One dashboard. Full control.
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Everything your community needs, built in — no plugins, no integrations required.
          </Typography>
        </Box>
        <Grid container spacing={3}>
          {FEATURES.map((f) => (
            <Grid item xs={12} sm={6} md={4} key={f.title}>
              <Card sx={{ height: '100%', p: 1, position: 'relative' }}>
                {(f.badge || f.plan) && (
                  <Box sx={{ position: 'absolute', top: 12, right: 12, display: 'flex', gap: 0.5 }}>
                    {f.badge ? (
                      <Chip label={f.badge} size="small" color={f.badgeColor || 'primary'} sx={{ fontSize: 10, height: 20 }} />
                    ) : (
                      <Chip label={f.plan} size="small" color={f.planColor || 'default'} variant="outlined" sx={{ fontSize: 10, height: 20 }} />
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

      {/* â"€â"€ How It Works â"€â"€ */}
      <Box sx={{ bgcolor: 'background.paper', borderTop: '1px solid', borderColor: 'divider', py: { xs: 8, md: 10 } }}>
        <Container maxWidth="sm">
          <Box sx={{ textAlign: 'center', mb: 6 }}>
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
            {STEPS.map((s) => (
              <Box key={s.n} sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
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
          <Box sx={{ textAlign: 'center', mt: 5 }}>
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
      <Container maxWidth="lg" sx={{ py: { xs: 8, md: 10 } }}>
        <Box sx={{ textAlign: 'center', mb: 6 }}>
          <Typography variant="overline" color="primary.main" fontWeight={700} letterSpacing={2}>
            Community Love
          </Typography>
          <Typography variant="h4" fontWeight={800} mt={1}>
            What community admins say
          </Typography>
        </Box>
        <Grid container spacing={3}>
          {TESTIMONIALS.map((t) => (
            <Grid item xs={12} sm={6} md={4} key={t.name}>
              <Card sx={{ height: '100%', p: 1 }}>
                <CardContent>
                  <Typography variant="body1" color="text.primary" lineHeight={1.7} mb={2} sx={{ fontStyle: 'italic' }}>
                    "{t.text}"
                  </Typography>
                  <Divider sx={{ mb: 2 }} />
                  <Typography variant="body2" fontWeight={700}>{t.name}</Typography>
                  <Typography variant="caption" color="text.secondary">{t.role}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* â"€â"€ Pricing â"€â"€ */}
      <Box sx={{ bgcolor: 'background.paper', borderTop: '1px solid', borderColor: 'divider', py: { xs: 8, md: 12 } }}>
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 6 }}>
            <Typography variant="overline" color="primary.main" fontWeight={700} letterSpacing={2}>
              Pricing
            </Typography>
            <Typography variant="h4" fontWeight={800} mt={1} mb={1}>
              Simple, transparent pricing
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Start free. Upgrade when you need more. No surprises.
            </Typography>
          </Box>
          <Grid container spacing={3} justifyContent="center">
            {PLANS.map((plan) => (
              <Grid item xs={12} sm={6} md={4} key={plan.name}>
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
            <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 3, flexWrap: 'wrap', justifyContent: 'center' }}>
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
      <Box sx={{ py: { xs: 8, md: 10 }, bgcolor: 'background.default' }}>
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
              a: 'Crypto payments accept USDT, BTC, ETH, BNB, TRX, SOL, and 300+ other coins via NOWPayments. Card / bank transfer via Lemon Squeezy is coming soon.'
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
              a: 'Free: 1 bot, basic moderation, welcome messages, XP system. Pro ($9/mo): 5 bots, unlimited groups, advanced AutoMod, scheduled messages, analytics, polls, AI knowledge base. Enterprise ($49/mo): 50 bots, all Pro features plus raid coordination, API access, dedicated support, SLA.'
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

      {/* â"€â"€ Final CTA â"€â"€ */}
      <Box
        sx={{
          background: 'linear-gradient(135deg, #1565c0 0%, #7c4dff 100%)',
          py: { xs: 8, md: 10 },
          textAlign: 'center',
          px: 2,
        }}
      >
        <Container maxWidth="sm">
          <Typography variant="h4" fontWeight={800} color="white" mb={2}>
            Your community deserves better than manual work
          </Typography>
          <Typography variant="body1" sx={{ color: 'rgba(255,255,255,0.85)', mb: 4, lineHeight: 1.7 }}>
            Join community admins who stopped doing it all by hand.
            Your first bot is free. No credit card. Takes 60 seconds.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center">
            <Button
              variant="contained"
              size="large"
              onClick={() => navigate('/register')}
              endIcon={<ArrowForward />}
              sx={{ bgcolor: 'white', color: 'primary.main', py: 1.75, px: 4, fontWeight: 700, '&:hover': { bgcolor: '#f0f0f0' } }}
            >
              Create Free Account
            </Button>
            <Button
              variant="outlined"
              size="large"
              onClick={() => navigate('/pricing')}
              sx={{ borderColor: 'rgba(255,255,255,0.5)', color: 'white', py: 1.75, px: 4, '&:hover': { borderColor: 'white', bgcolor: 'rgba(255,255,255,0.1)' } }}
            >
              See Pricing
            </Button>
          </Stack>
        </Container>
      </Box>

      {/* â"€â"€ Footer â"€â"€ */}
      <Box sx={{ bgcolor: 'background.paper', borderTop: '1px solid', borderColor: 'divider', py: 4 }}>
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
