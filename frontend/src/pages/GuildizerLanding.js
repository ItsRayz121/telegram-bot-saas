import React from 'react';
import { useScrollReveal } from '../hooks/useScrollReveal';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  Grid, Chip, Container, Stack, Avatar,
  Accordion, AccordionSummary, AccordionDetails,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Shield, Schedule, BarChart, People, CheckCircle,
  AutoAwesome, Bolt, Warning, TrendingDown, AccessTime,
  ArrowForward, CurrencyBitcoin, Lock, Telegram, Forum, SmartToy,
} from '@mui/icons-material';
import PlatformSwitcher from '../components/PlatformSwitcher';
import { useNavigate } from 'react-router-dom';
import usePageMeta from '../hooks/usePageMeta';

const ACCENT = '#5865F2'; // Discord blurple
const ACCENT2 = '#8b5cf6';

const PAIN_POINTS = [
  {
    icon: <Lock fontSize="large" />,
    title: 'A raid or nuke can wipe your server',
    desc: 'Mass-join raids, deleted channels, and a single compromised admin can destroy months of work in minutes.',
  },
  {
    icon: <Warning fontSize="large" />,
    title: 'Scams slip past Discord\'s defaults',
    desc: 'Fake Nitro links, phishing DMs, and bot spam flood your channels faster than your mods can react.',
  },
  {
    icon: <TrendingDown fontSize="large" />,
    title: 'Engagement fizzles after the hype',
    desc: 'Without roles, levels, and reasons to return, members lurk for a day and then go silent.',
  },
  {
    icon: <AccessTime fontSize="large" />,
    title: 'You\'re moderating instead of building',
    desc: 'Every welcome, every role, every ban — handled by you, around the clock, by hand.',
  },
];

const FEATURES = [
  {
    icon: <Shield fontSize="large" />,
    title: 'AutoMod — Set it. Forget it.',
    desc: 'Auto-remove spam, invite links, slurs, and walls of text. Warn → mute → ban automatically. Your server stays clean 24/7.',
    badge: 'Most Used', badgeColor: 'warning', plan: 'Free',
  },
  {
    icon: <Lock fontSize="large" />,
    title: 'Anti-Nuke Guard',
    desc: 'Detect mass-ban, mass-channel-delete, and rogue-admin behavior — then lock it down before the damage spreads.',
    badge: 'Pro', badgeColor: 'primary', plan: 'Pro', planColor: 'primary',
  },
  {
    icon: <People fontSize="large" />,
    title: 'Self-Roles & Reaction Roles',
    desc: 'Let members pick their own roles from buttons or reactions — no manual assignment, no role clutter.',
    plan: 'Free',
  },
  {
    icon: <Bolt fontSize="large" />,
    title: 'Leveling & Voice XP',
    desc: 'Reward active chatters and voice users with XP, levels, and automatic role rewards.',
    plan: 'Free',
  },
  {
    icon: <Forum fontSize="large" />,
    title: 'Tickets & Support Threads',
    desc: 'Members open private ticket threads from a panel; your staff get a full transcript when the ticket closes.',
    badge: 'Pro', badgeColor: 'primary', plan: 'Pro', planColor: 'primary',
  },
  {
    icon: <AutoAwesome fontSize="large" />,
    title: 'Starboard',
    desc: 'The best messages get pinned to a starboard automatically once they hit your reaction threshold.',
    plan: 'Free',
  },
  {
    icon: <CheckCircle fontSize="large" />,
    title: 'Welcome & Onboarding',
    desc: 'Greet new members, assign starter roles, and DM the rules — automatically, the moment they join.',
    plan: 'Free',
  },
  {
    icon: <BarChart fontSize="large" />,
    title: 'Server Analytics',
    desc: 'Member growth, join sources, peak activity hours, and moderation stats — all in one dashboard.',
    badge: 'Pro', badgeColor: 'primary', plan: 'Pro', planColor: 'primary',
  },
  {
    icon: <Schedule fontSize="large" />,
    title: 'Scheduled & Embed Posts',
    desc: 'Compose rich embeds and auto-publish announcements on a schedule, in any timezone.',
    plan: 'Free',
  },
];

const PLANS = [
  {
    name: 'Free', price: '$0', daily: null, period: 'forever', color: 'default',
    features: ['1 bot', '3 servers per bot', 'Basic moderation', 'Welcome messages', 'Leveling & XP'],
    cta: 'Start Free', ctaVariant: 'outlined', tier: null,
  },
  {
    name: 'Pro', price: '$9', daily: '$0.30/day', period: '/month', color: 'primary', popular: true,
    features: ['3 bots', 'Unlimited servers', 'Advanced AutoMod', 'Anti-Nuke Guard', 'Tickets', 'Analytics', 'Priority support'],
    cta: 'Get Pro', ctaVariant: 'contained', tier: 'pro',
  },
  {
    name: 'Enterprise', price: '$49', daily: '$1.63/day', period: '/month', color: 'secondary',
    features: ['50 bots', 'All Pro features', 'API access', 'Webhook integrations', 'SLA guarantee', 'Dedicated support'],
    cta: 'Get Enterprise', ctaVariant: 'outlined', tier: 'enterprise',
  },
];

const STEPS = [
  { n: '1', title: 'Create your free account', desc: 'Email + password. Done in 30 seconds.' },
  { n: '2', title: 'Click "Add to Discord"', desc: 'Authorize Guildizer with the permissions it needs — nothing more.' },
  { n: '3', title: 'Pick your server', desc: 'Your server appears in the dashboard automatically.' },
  { n: '4', title: 'Set your roles & channels', desc: 'Tell Guildizer your mod-log channel, mute role, and welcome channel.' },
  { n: '5', title: 'Turn on automation', desc: 'Enable AutoMod, anti-nuke, leveling, and tickets — done.' },
];

const FAQS = [
  {
    q: 'What permissions does Guildizer need?',
    a: 'Manage Roles, Manage Channels, Kick/Ban Members, Manage Messages, and Read/Send Messages. You grant exactly these during the "Add to Discord" authorization — Guildizer never asks for more than it uses.',
  },
  {
    q: 'Is my server safe with Anti-Nuke on?',
    a: 'Yes — that\'s the point. Anti-Nuke watches for destructive admin actions (mass bans, mass channel deletes, sudden permission changes) and can automatically revoke the actor\'s roles and halt the spree. You set the thresholds.',
  },
  {
    q: 'Does one plan cover both Telegram and Discord?',
    a: 'Yes. A single Pro or Enterprise subscription unlocks paid features across Guildizer (Discord) and Telegizer (Telegram) on the same account — one plan, every platform.',
  },
  {
    q: 'What happens if I cancel or my plan expires?',
    a: 'Your bot keeps running, but paid features (Anti-Nuke, tickets, analytics, etc.) become read-only. You keep all free features indefinitely and everything comes back the moment you renew.',
  },
  {
    q: 'What coins and payment methods are supported?',
    a: 'Payments are processed via NOWPayments and support USDT, BTC, ETH, BNB, SOL, and 300+ other coins. Card payments are not available at this time.',
  },
  {
    q: 'Can I run my own branded Discord bot?',
    a: 'Yes. Custom branded bots are supported on Pro (3 bots) and Enterprise (50 bots), each with its own settings, roles, and automation.',
  },
];

const PRODUCT_FAMILY = [
  {
    icon: <Telegram fontSize="large" />, name: 'Telegizer', tag: 'Telegram groups',
    desc: 'Moderation, scheduled content, member systems, and growth analytics for your Telegram groups — all from one dashboard.',
    cta: 'Explore Telegizer', to: '/',
  },
  {
    icon: <SmartToy fontSize="large" />, name: 'Echo', tag: 'AI assistant',
    desc: 'Your personal AI assistant on Telegram — reminders, notes, tasks, smart links, and daily digests, right inside chat.',
    cta: 'Explore Echo', to: '/echo',
  },
  {
    icon: <Forum fontSize="large" />, name: 'Guildizer', tag: 'Discord servers',
    desc: 'The same automation, moderation, and growth tools — rebuilt natively for your Discord servers.',
    chip: "You're here", to: null,
  },
];

function GuildizerBrand() {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Forum sx={{ color: ACCENT }} />
      <Typography variant="h6" fontWeight={800} sx={{ letterSpacing: '-0.02em' }}>
        Guildizer
      </Typography>
    </Box>
  );
}

export default function GuildizerLanding() {
  usePageMeta(
    'Guildizer — Discord Server Management',
    'Guildizer automates Discord moderation, anti-nuke protection, self-roles, leveling, tickets, and analytics — from one dashboard. Free plan available.'
  );
  const navigate = useNavigate();
  const token = localStorage.getItem('token');

  const [painRef, painVisible] = useScrollReveal(0.08);
  const [solutionRef, solutionVisible] = useScrollReveal(0.15);
  const [featuresRef, featuresVisible] = useScrollReveal(0.05);
  const [stepsRef, stepsVisible] = useScrollReveal(0.1);
  const [pricingRef, pricingVisible] = useScrollReveal(0.05);
  const [faqRef, faqVisible] = useScrollReveal(0.1);
  const [familyRef, familyVisible] = useScrollReveal(0.1);
  const [ctaRef, ctaVisible] = useScrollReveal(0.15);

  const reveal = (visible, delay = 0) => ({
    opacity: visible ? 1 : 0,
    transform: visible ? 'none' : 'translateY(22px)',
    transition: `opacity 0.55s ease ${delay}ms, transform 0.55s cubic-bezier(0.22,1,0.36,1) ${delay}ms`,
  });

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>

      {/* ── Nav ── */}
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.default' }}>
        <Toolbar sx={{ maxWidth: 1200, mx: 'auto', width: '100%', px: { xs: 2, md: 3 } }}>
          <Box sx={{ flexGrow: 1, cursor: 'pointer' }} onClick={() => navigate('/guildizer-landing')}>
            <GuildizerBrand />
          </Box>
          <Button onClick={() => navigate('/pricing')} sx={{ mr: 1, display: { xs: 'none', sm: 'inline-flex' }, color: 'text.secondary' }}>
            Pricing
          </Button>
          {token ? (
            <Button variant="contained" onClick={() => navigate('/guildizer')} sx={{ bgcolor: ACCENT, '&:hover': { bgcolor: ACCENT, filter: 'brightness(1.08)' } }}>
              Dashboard
            </Button>
          ) : (
            <Stack direction="row" spacing={1}>
              <Button onClick={() => navigate('/login')} sx={{ color: 'text.secondary' }}>Sign In</Button>
              <Button variant="contained" onClick={() => navigate('/register')} sx={{ bgcolor: ACCENT, '&:hover': { bgcolor: ACCENT, filter: 'brightness(1.08)' } }}>
                Start Free
              </Button>
            </Stack>
          )}
        </Toolbar>
      </AppBar>

      {/* ── Hero ── */}
      <Box sx={{ background: 'linear-gradient(160deg, #0d1117 0%, #15163a 50%, #0d1117 100%)', pt: { xs: 8, md: 14 }, pb: { xs: 8, md: 14 }, textAlign: 'center', px: 2, position: 'relative', overflow: 'hidden' }}>
        <Box sx={{
          position: 'absolute', top: '20%', left: '50%', transform: 'translateX(-50%)',
          width: { xs: '90vw', sm: 500, md: 600 }, height: { xs: 180, sm: 240, md: 300 },
          borderRadius: '50%', background: `radial-gradient(ellipse, ${ACCENT}24 0%, transparent 70%)`, pointerEvents: 'none',
        }} />
        <Container maxWidth="md" sx={{ position: 'relative' }}>
          <PlatformSwitcher active="discord:server" />
          <Chip
            label="Built for Discord server admins"
            size="small"
            sx={{ mb: 3, bgcolor: `${ACCENT}1f`, color: '#fff', fontWeight: 600, border: `1px solid ${ACCENT}55` }}
          />
          <Typography variant="h1" fontWeight={900} mb={2.5} sx={{ fontSize: { xs: '2.2rem', sm: '3rem', md: '3.75rem' }, lineHeight: 1.1, letterSpacing: '-0.02em' }}>
            Manage Your Discord Server{' '}
            <Box component="span" sx={{ background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT2})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
              Without the Manual Work
            </Box>
          </Typography>
          <Typography variant="h5" color="text.secondary" mb={1.5} sx={{ fontWeight: 400, fontSize: { xs: '1.1rem', md: '1.3rem' } }}>
            Moderation, anti-nuke, and growth — handled natively.
          </Typography>
          <Typography variant="body1" color="text.disabled" mb={5} sx={{ maxWidth: 540, mx: 'auto', lineHeight: 1.7 }}>
            Guildizer brings auto-mod, anti-nuke protection, self-roles, leveling, tickets, and
            analytics to Discord — all from a single dashboard.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center" mb={3}>
            <Button variant="contained" size="large" onClick={() => navigate('/register')} endIcon={<ArrowForward />}
              sx={{ py: { xs: 1.25, sm: 1.75 }, px: { xs: 2.5, sm: 4 }, fontSize: { xs: '0.92rem', sm: '1.05rem' }, fontWeight: 700, bgcolor: ACCENT, '&:hover': { bgcolor: ACCENT, filter: 'brightness(1.08)' } }}>
              Start Free — Takes 60 Seconds
            </Button>
            <Button variant="outlined" size="large" onClick={() => navigate('/pricing')}
              sx={{ py: { xs: 1.25, sm: 1.75 }, px: { xs: 2.5, sm: 4 }, fontSize: { xs: '0.92rem', sm: '1.05rem' } }}>
              View Pricing
            </Button>
          </Stack>
          <Typography variant="caption" color="text.disabled">
            14-day Pro trial included · No credit card required · Free plan, forever · Pay with 300+ cryptos · No auto-renew
          </Typography>
        </Container>

        {/* Dashboard preview */}
        <Box sx={{ mt: 7, mx: 'auto', maxWidth: 860, px: { xs: 2, md: 0 }, position: 'relative' }}>
          <Typography variant="caption" color="text.disabled" display="block" textAlign="center" mb={2}>
            Example dashboard — illustrative data only
          </Typography>
          <Box sx={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 100, zIndex: 1, background: 'linear-gradient(transparent, #0d1117)', pointerEvents: 'none' }} />
          <Box sx={{ p: 2.5, bgcolor: 'rgba(20,22,45,0.6)', borderRadius: 3, border: `1px solid ${ACCENT}1f`, boxShadow: `0 0 60px ${ACCENT}1f, 0 24px 80px rgba(0,0,0,0.5)` }}>
            <Grid container spacing={1.5} mb={2}>
              {[
                { label: 'Members', value: '8,540', delta: '+182 today', color: ACCENT },
                { label: 'Raids Blocked', value: '96', delta: 'this month', color: '#66bb6a' },
                { label: 'Messages', value: '120,400', delta: 'last 30 days', color: '#29b6f6' },
                { label: 'Channels', value: '24', delta: 'monitored', color: '#ce93d8' },
              ].map(s => (
                <Grid item xs={6} sm={3} key={s.label}>
                  <Box sx={{ bgcolor: '#1e2140', borderRadius: 2, p: 1.5, border: '1px solid rgba(255,255,255,0.06)' }}>
                    <Typography variant="caption" color="text.secondary" display="block">{s.label}</Typography>
                    <Typography fontWeight={800} sx={{ fontSize: '1.25rem', color: s.color }}>{s.value}</Typography>
                    <Typography variant="caption" color="text.disabled">{s.delta}</Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
            <Grid container spacing={1.5}>
              <Grid item xs={12} sm={8}>
                <Box sx={{ bgcolor: '#1e2140', borderRadius: 2, p: 2, border: '1px solid rgba(255,255,255,0.06)', height: 120 }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1.5}>Member Growth</Typography>
                  <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: '4px', height: 72 }}>
                    {[40, 55, 48, 70, 62, 85, 78, 95, 88, 100, 92, 110].map((h, i) => (
                      <Box key={i} sx={{ flex: 1, bgcolor: i === 11 ? ACCENT : `${ACCENT}59`, borderRadius: '3px 3px 0 0', height: `${h}%` }} />
                    ))}
                  </Box>
                </Box>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Box sx={{ bgcolor: '#1e2140', borderRadius: 2, p: 2, border: '1px solid rgba(255,255,255,0.06)', height: 120 }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1}>Recent Actions</Typography>
                  {[
                    { text: 'Raid blocked', color: 'error.main' },
                    { text: 'Member joined', color: 'success.main' },
                    { text: 'Role assigned', color: ACCENT },
                    { text: 'Ticket opened', color: 'warning.main' },
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

      {/* ── Stats Strip ── */}
      <Box sx={{ bgcolor: '#0b1626', borderTop: '1px solid', borderBottom: '1px solid', borderColor: 'divider', py: 3 }}>
        <Container maxWidth="md">
          <Grid container justifyContent="center" spacing={0}>
            {[
              { value: '300+', label: 'Cryptos Accepted' },
              { value: '15+', label: 'Server Tools' },
              { value: '24/7', label: 'Always Running' },
              { value: '5 min', label: 'Setup Time' },
            ].map((s, i) => (
              <Grid item xs={6} sm={3} key={s.label} sx={{
                textAlign: 'center', py: 1.5,
                borderLeft: { xs: i % 2 !== 0 ? '1px solid' : 'none', sm: i > 0 ? '1px solid' : 'none' },
                borderTop: { xs: i >= 2 ? '1px solid' : 'none', sm: 'none' }, borderColor: 'divider',
              }}>
                <Typography variant="h4" fontWeight={800} sx={{ color: ACCENT, fontSize: { xs: '1.6rem', sm: '2rem', md: '2.125rem' } }}>{s.value}</Typography>
                <Typography variant="caption" color="text.secondary">{s.label}</Typography>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* ── Pain ── */}
      <Box sx={{ bgcolor: '#07101f' }}>
        <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
          <Box ref={painRef} sx={{ textAlign: 'center', mb: 6, ...reveal(painVisible) }}>
            <Typography variant="overline" color="error.main" fontWeight={700} letterSpacing={2}>The Problem</Typography>
            <Typography variant="h4" fontWeight={800} mt={1} mb={1.5}>Running a Discord server shouldn't feel like a full-time job</Typography>
            <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 560, mx: 'auto' }}>
              If you're moderating a server without automation, here's what your day looks like:
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

      {/* ── Solution bridge ── */}
      <Box ref={solutionRef} sx={{ bgcolor: '#0b1626', borderTop: '1px solid', borderBottom: '1px solid', borderColor: 'divider', py: { xs: 6, md: 8 }, textAlign: 'center', px: 2, ...reveal(solutionVisible) }}>
        <Container maxWidth="sm">
          <Typography variant="overline" color="success.main" fontWeight={700} letterSpacing={2}>How It Helps</Typography>
          <Typography variant="h4" fontWeight={800} mt={1} mb={2}>
            Replace repetitive moderation with{' '}
            <Box component="span" sx={{ background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT2})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>reliable automation</Box>
          </Typography>
          <Typography variant="body1" color="text.secondary" lineHeight={1.8}>
            Add Guildizer to your server and configure what you want automated — spam removal,
            anti-nuke, self-roles, leveling, tickets. It runs in the background so you can focus on
            your community, not the admin work.
          </Typography>
        </Container>
      </Box>

      {/* ── Features ── */}
      <Box sx={{ bgcolor: '#07101f' }}>
        <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
          <Box ref={featuresRef} sx={{ textAlign: 'center', mb: 6, ...reveal(featuresVisible) }}>
            <Typography variant="overline" sx={{ color: ACCENT }} fontWeight={700} letterSpacing={2}>Features</Typography>
            <Typography variant="h4" fontWeight={800} mt={1} mb={1}>
              One dashboard.{' '}
              <Box component="span" sx={{ background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT2})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>Full control.</Box>
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Everything your server needs, built in — no extra bots, no plugins to juggle.
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
                    <Box sx={{ color: ACCENT, mb: 1.5 }}>{f.icon}</Box>
                    <Typography variant="h6" fontWeight={700} mb={1}>{f.title}</Typography>
                    <Typography variant="body2" color="text.secondary" lineHeight={1.7}>{f.desc}</Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* ── How It Works ── */}
      <Box sx={{ bgcolor: '#0b1626', borderTop: '1px solid', borderColor: 'divider', py: { xs: 8, md: 10 } }}>
        <Container maxWidth="sm">
          <Box ref={stepsRef} sx={{ textAlign: 'center', mb: 6, ...reveal(stepsVisible) }}>
            <Typography variant="overline" sx={{ color: ACCENT }} fontWeight={700} letterSpacing={2}>Setup</Typography>
            <Typography variant="h4" fontWeight={800} mt={1} mb={1}>Up and running in 5 minutes</Typography>
            <Typography variant="body1" color="text.secondary">No coding. No DevOps. Just add the bot and automate.</Typography>
          </Box>
          <Stack spacing={3}>
            {STEPS.map((s, i) => (
              <Box key={s.n} sx={{ display: 'flex', alignItems: 'flex-start', gap: 2, ...reveal(stepsVisible, i * 60) }}>
                <Avatar sx={{ bgcolor: ACCENT, width: 36, height: 36, fontSize: '0.9rem', fontWeight: 800, flexShrink: 0 }}>{s.n}</Avatar>
                <Box>
                  <Typography fontWeight={700} mb={0.25}>{s.title}</Typography>
                  <Typography variant="body2" color="text.secondary">{s.desc}</Typography>
                </Box>
              </Box>
            ))}
          </Stack>
          <Box sx={{ textAlign: 'center', mt: 5, ...reveal(stepsVisible, STEPS.length * 60) }}>
            <Button variant="contained" size="large" onClick={() => navigate('/register')} endIcon={<ArrowForward />}
              sx={{ py: 1.5, px: 4, bgcolor: ACCENT, '&:hover': { bgcolor: ACCENT, filter: 'brightness(1.08)' } }}>
              Get Started Free
            </Button>
          </Box>
        </Container>
      </Box>

      {/* ── Pricing ── */}
      <Box sx={{ bgcolor: '#07101f', borderTop: '1px solid', borderColor: 'divider', py: { xs: 8, md: 12 } }}>
        <Container maxWidth="lg">
          <Box ref={pricingRef} sx={{ textAlign: 'center', mb: 6, ...reveal(pricingVisible) }}>
            <Typography variant="overline" sx={{ color: ACCENT }} fontWeight={700} letterSpacing={2}>Pricing</Typography>
            <Typography variant="h4" fontWeight={800} mt={1} mb={1}>
              Simple,{' '}
              <Box component="span" sx={{ background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT2})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>transparent pricing</Box>
            </Typography>
            <Typography variant="body1" color="text.secondary">
              One subscription covers Discord <Box component="span" sx={{ color: '#fff' }}>and</Box> Telegram. Start free, upgrade when you need more.
            </Typography>
          </Box>
          <Grid container spacing={3} justifyContent="center">
            {PLANS.map((plan, i) => (
              <Grid item xs={12} sm={6} md={4} key={plan.name} sx={reveal(pricingVisible, i * 90)}>
                <Box sx={{ position: 'relative', pt: '14px', height: '100%' }}>
                  {plan.popular && (
                    <Chip label="Most Popular" size="small" sx={{ position: 'absolute', top: 0, left: '50%', transform: 'translateX(-50%)', zIndex: 1, fontWeight: 700, bgcolor: ACCENT, color: '#fff' }} />
                  )}
                  <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column', border: plan.popular ? '2px solid' : '1px solid', borderColor: plan.popular ? ACCENT : 'divider' }}>
                    <CardContent sx={{ flexGrow: 1, p: 3 }}>
                      <Typography variant="h5" fontWeight={800} mb={0.5}>{plan.name}</Typography>
                      <Box sx={{ mb: 0.5 }}>
                        <Typography component="span" variant="h3" fontWeight={900}>{plan.price}</Typography>
                        <Typography component="span" variant="body1" color="text.secondary">{plan.period}</Typography>
                      </Box>
                      {plan.daily && <Typography variant="caption" color="text.disabled" display="block" mb={2}>That's only {plan.daily}</Typography>}
                      <Button fullWidth variant={plan.ctaVariant} size="large" sx={{ mb: 3, fontWeight: 700, ...(plan.ctaVariant === 'contained' ? { bgcolor: ACCENT, '&:hover': { bgcolor: ACCENT, filter: 'brightness(1.08)' } } : { color: ACCENT, borderColor: ACCENT }) }}
                        onClick={() => plan.tier ? navigate('/pricing') : navigate('/register')}>
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
                <CheckCircle fontSize="small" sx={{ color: ACCENT }} />
                <Typography variant="body2" color="text.secondary">No auto-renew</Typography>
              </Box>
            </Box>
          </Box>
        </Container>
      </Box>

      {/* ── FAQ ── */}
      <Box ref={faqRef} sx={{ py: { xs: 8, md: 10 }, bgcolor: '#0b1626', borderTop: '1px solid', borderColor: 'divider', ...reveal(faqVisible) }}>
        <Container maxWidth="md">
          <Typography variant="overline" sx={{ color: ACCENT }} fontWeight={700} display="block" textAlign="center">FAQ</Typography>
          <Typography variant="h4" fontWeight={800} textAlign="center" mb={5}>Frequently asked questions</Typography>
          {FAQS.map(({ q, a }) => (
            <Accordion key={q} disableGutters elevation={0} sx={{ border: '1px solid', borderColor: 'divider', mb: 1, borderRadius: '8px !important', '&:before': { display: 'none' } }}>
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

      {/* ── Product family ── */}
      <Box ref={familyRef} sx={{ bgcolor: '#07101f', borderTop: '1px solid', borderColor: 'divider', py: { xs: 8, md: 10 }, ...reveal(familyVisible) }}>
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 6 }}>
            <Typography variant="overline" sx={{ color: ACCENT }} fontWeight={700} letterSpacing={2}>The Telegizer Family</Typography>
            <Typography variant="h4" fontWeight={800} mt={1} mb={1}>
              One toolkit for{' '}
              <Box component="span" sx={{ background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT2})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>every community you run</Box>
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 580, mx: 'auto' }}>
              Guildizer is part of a small family of tools built to run online communities
              without the busywork — across both Discord and Telegram.
            </Typography>
          </Box>
          <Grid container spacing={3} justifyContent="center">
            {PRODUCT_FAMILY.map((p, i) => (
              <Grid item xs={12} sm={6} md={4} key={p.name} sx={reveal(familyVisible, i * 90)}>
                <Card sx={{ height: '100%', p: 1, display: 'flex', flexDirection: 'column' }}>
                  <CardContent sx={{ flexGrow: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
                      <Box sx={{ color: ACCENT }}>{p.icon}</Box>
                      <Chip label={p.tag} size="small" variant="outlined" sx={{ fontSize: 11, height: 20 }} />
                    </Box>
                    <Typography variant="h6" fontWeight={700} mb={1}>{p.name}</Typography>
                    <Typography variant="body2" color="text.secondary" lineHeight={1.7}>{p.desc}</Typography>
                  </CardContent>
                  <Box sx={{ px: 2, pb: 2 }}>
                    {p.to ? (
                      <Button variant="outlined" size="small" endIcon={<ArrowForward />} onClick={() => navigate(p.to)}>{p.cta}</Button>
                    ) : (
                      <Chip label={p.chip} size="small" sx={{ fontWeight: 600, bgcolor: ACCENT, color: '#fff' }} />
                    )}
                  </Box>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* ── Final CTA ── */}
      <Box ref={ctaRef} sx={{ background: 'linear-gradient(135deg, #1a1a6e 0%, #2d1060 50%, #0a2040 100%)', py: { xs: 8, md: 10 }, textAlign: 'center', px: 2, position: 'relative', overflow: 'hidden', ...reveal(ctaVisible) }}>
        <Box sx={{ position: 'absolute', top: -60, right: -60, width: 340, height: 340, borderRadius: '50%', background: `radial-gradient(circle, ${ACCENT}38 0%, transparent 70%)`, pointerEvents: 'none' }} />
        <Container maxWidth="sm" sx={{ position: 'relative' }}>
          <Typography variant="h4" fontWeight={800} color="white" mb={2}>Stop moderating your server by hand</Typography>
          <Typography variant="body1" sx={{ color: 'rgba(255,255,255,0.75)', mb: 4, lineHeight: 1.7 }}>
            Your first bot is free — no credit card, no setup complexity. Takes 60 seconds.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center">
            <Button variant="contained" size="large" onClick={() => navigate('/register')} endIcon={<ArrowForward />}
              sx={{ bgcolor: 'white', color: '#1a1a6e', py: { xs: 1.25, sm: 1.75 }, px: { xs: 2.5, sm: 4 }, fontWeight: 700, '&:hover': { bgcolor: '#e8f0ff', transform: 'translateY(-1px)' } }}>
              Create Free Account
            </Button>
            <Button variant="outlined" size="large" onClick={() => navigate('/pricing')}
              sx={{ borderColor: 'rgba(255,255,255,0.35)', color: 'white', py: { xs: 1.25, sm: 1.75 }, px: { xs: 2.5, sm: 4 }, '&:hover': { borderColor: 'rgba(255,255,255,0.7)', bgcolor: 'rgba(255,255,255,0.07)' } }}>
              See Pricing
            </Button>
          </Stack>
        </Container>
      </Box>

      {/* ── Footer ── */}
      <Box sx={{ bgcolor: '#07101f', borderTop: '1px solid', borderColor: 'divider', py: 4 }}>
        <Container maxWidth="lg">
          <Grid container alignItems="center" spacing={2}>
            <Grid item xs={12} sm="auto">
              <GuildizerBrand />
              <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>Automate your Discord server</Typography>
            </Grid>
            <Grid item xs={12} sm sx={{ textAlign: { xs: 'left', sm: 'center' } }}>
              <Stack direction="row" spacing={1} flexWrap="wrap" justifyContent={{ xs: 'flex-start', sm: 'center' }}>
                <Button size="small" onClick={() => navigate('/')} sx={{ color: 'text.secondary' }}>Telegram</Button>
                <Button size="small" onClick={() => navigate('/echo')} sx={{ color: 'text.secondary' }}>Echo</Button>
                <Button size="small" onClick={() => navigate('/pricing')} sx={{ color: 'text.secondary' }}>Pricing</Button>
                <Button size="small" onClick={() => navigate('/login')} sx={{ color: 'text.secondary' }}>Sign In</Button>
                <Button size="small" onClick={() => navigate('/register')} sx={{ color: 'text.secondary' }}>Register</Button>
                <Button size="small" onClick={() => navigate('/terms')} sx={{ color: 'text.secondary' }}>Terms</Button>
                <Button size="small" onClick={() => navigate('/privacy')} sx={{ color: 'text.secondary' }}>Privacy</Button>
              </Stack>
            </Grid>
            <Grid item xs={12} sm="auto" sx={{ textAlign: { xs: 'left', sm: 'right' } }}>
              <Typography variant="caption" color="text.disabled">© {new Date().getFullYear()} Guildizer. All rights reserved.</Typography>
            </Grid>
          </Grid>
        </Container>
      </Box>

    </Box>
  );
}
