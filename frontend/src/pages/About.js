import React from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Container, Divider,
  Card, CardContent, Grid, Chip, Avatar,
} from '@mui/material';
import {
  AutoFixHigh, Security, BarChart, SmartToy, Groups, Bolt,
  CheckCircle, Favorite, OpenInNew, Email, Telegram,
} from '@mui/icons-material';
import TelegizerLogo from '../components/TelegizerLogo';
import { useNavigate } from 'react-router-dom';

function PageNav() {
  const navigate = useNavigate();
  return (
    <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.default' }}>
      <Toolbar>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer', flexGrow: 1 }} onClick={() => navigate('/')}>
          <TelegizerLogo size="sm" variant="icon" />
          <Typography variant="h6" fontWeight={700}>Telegizer</Typography>
        </Box>
        <Button size="small" onClick={() => navigate('/login')} sx={{ mr: 1 }}>Sign In</Button>
        <Button size="small" variant="contained" onClick={() => navigate('/register')}>Get Started Free</Button>
      </Toolbar>
    </AppBar>
  );
}

const PILLARS = [
  {
    icon: <AutoFixHigh sx={{ fontSize: 28 }} />,
    title: 'Automation First',
    desc: 'Every feature is designed to run 24/7 without you lifting a finger — from AutoMod to scheduled posts to AI digests.',
    color: '#2563EB',
  },
  {
    icon: <Security sx={{ fontSize: 28 }} />,
    title: 'Privacy by Design',
    desc: 'Bot tokens encrypted at rest. Passwords hashed. No ads. No data selling. Your community data belongs to you.',
    color: '#7C3AED',
  },
  {
    icon: <BarChart sx={{ fontSize: 28 }} />,
    title: 'Built for Growth',
    desc: 'XP systems, analytics, and engagement tools that help your community grow — not just survive.',
    color: '#06B6D4',
  },
  {
    icon: <Favorite sx={{ fontSize: 28 }} />,
    title: 'Community-Driven',
    desc: 'We build what our users need. Most major features were requested directly by community managers like you.',
    color: '#ef4444',
  },
];

const FEATURES = [
  { icon: <Security fontSize="small" />, label: 'AutoMod & Spam Protection' },
  { icon: <AutoFixHigh fontSize="small" />, label: 'Scheduled Messages & Polls' },
  { icon: <Groups fontSize="small" />, label: 'XP / Level System' },
  { icon: <BarChart fontSize="small" />, label: 'Growth Analytics' },
  { icon: <SmartToy fontSize="small" />, label: 'AI Daily Digest' },
  { icon: <Bolt fontSize="small" />, label: 'Custom Commands' },
  { icon: <SmartToy fontSize="small" />, label: 'AI Auto-Reply' },
  { icon: <Groups fontSize="small" />, label: 'Member CRM' },
  { icon: <Bolt fontSize="small" />, label: 'Smart Reminders' },
  { icon: <BarChart fontSize="small" />, label: 'Telegram Mini App' },
  { icon: <AutoFixHigh fontSize="small" />, label: 'Workflow Automation' },
  { icon: <Security fontSize="small" />, label: 'Warn / Mute / Ban / Tempban' },
];

const TIMELINE = [
  { year: '2024', label: 'Founded', desc: 'Started as a simple bot manager for a small Telegram community.' },
  { year: 'Q1 2025', label: 'First 100 Groups', desc: 'AutoMod, scheduled messages, and basic analytics launched.' },
  { year: 'Q2 2025', label: 'AI Features', desc: 'AI Daily Digest, Auto-Reply, and the Assistant Hub went live.' },
  { year: 'Q4 2025', label: 'Mini App', desc: 'Telegram Mini App launched — manage your community without leaving Telegram.' },
  { year: '2026', label: 'Full Platform', desc: 'Workspace, CRM, Channels, Marketplace, and Custom Bot Builder shipped.' },
];

const VALUES = [
  'We ship fast and iterate based on real user feedback',
  'We never sell your data or show ads — ever',
  'We keep the free tier genuinely useful',
  "We reply to every support email personally",
  'We document decisions and changes as we build',
  'We take security seriously: tokens encrypted, passwords hashed, HTTPS everywhere',
];

export default function About() {
  const navigate = useNavigate();

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <PageNav />

      {/* Hero */}
      <Box sx={{ py: { xs: 8, md: 12 }, textAlign: 'center', background: 'linear-gradient(160deg, rgba(37,99,235,0.08) 0%, rgba(124,58,237,0.06) 100%)' }}>
        <Container maxWidth="md">
          <Box sx={{ display: 'flex', justifyContent: 'center', mb: 3 }}>
            <TelegizerLogo size="lg" variant="icon" />
          </Box>
          <Typography variant="h3" fontWeight={800} mb={2}>
            We're building the command center for Telegram communities
          </Typography>
          <Typography variant="body1" color="text.secondary" maxWidth={600} mx="auto" lineHeight={1.8}>
            Telegizer started because managing a Telegram group was unnecessarily hard. We wanted
            one platform — automation, analytics, moderation, and AI — without piecing together
            ten separate bots.
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', mt: 4, flexWrap: 'wrap' }}>
            <Button variant="contained" size="large" onClick={() => navigate('/register')}>
              Start Free — No Credit Card
            </Button>
            <Button variant="outlined" size="large" onClick={() => navigate('/pricing')}>
              See Pricing
            </Button>
          </Box>
        </Container>
      </Box>

      <Container maxWidth="lg" sx={{ py: 8 }}>

        {/* Mission */}
        <Grid container spacing={6} alignItems="center" mb={10}>
          <Grid item xs={12} md={6}>
            <Chip label="Our Mission" size="small" color="primary" sx={{ mb: 2 }} />
            <Typography variant="h4" fontWeight={800} mb={3}>
              Community management should be effortless
            </Typography>
            <Typography variant="body1" color="text.secondary" lineHeight={1.9} mb={2}>
              Telegram has over 900 million active users and hundreds of millions of group members.
              Yet the tools for managing those communities are fragmented, unreliable, and often
              require technical knowledge most community managers don't have.
            </Typography>
            <Typography variant="body1" color="text.secondary" lineHeight={1.9}>
              Telegizer fixes this. One dashboard, one bot, everything you need — from basic spam
              protection to AI-powered daily digests. Built for community managers, not developers.
            </Typography>
          </Grid>
          <Grid item xs={12} md={6}>
            <Grid container spacing={2}>
              {PILLARS.map((p) => (
                <Grid item xs={12} sm={6} key={p.title}>
                  <Card sx={{ height: '100%', border: `1px solid ${p.color}22` }}>
                    <CardContent>
                      <Box sx={{ color: p.color, mb: 1.5 }}>{p.icon}</Box>
                      <Typography variant="subtitle2" fontWeight={700} mb={1}>{p.title}</Typography>
                      <Typography variant="body2" color="text.secondary" lineHeight={1.7}>{p.desc}</Typography>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </Grid>
        </Grid>

        <Divider sx={{ mb: 8 }} />

        {/* Features grid */}
        <Box sx={{ textAlign: 'center', mb: 5 }}>
          <Chip label="What We've Built" size="small" color="primary" sx={{ mb: 2 }} />
          <Typography variant="h4" fontWeight={800} mb={2}>Everything in one platform</Typography>
          <Typography variant="body1" color="text.secondary" maxWidth={500} mx="auto">
            12+ features that work together — not a dozen separate bots you have to juggle.
          </Typography>
        </Box>
        <Grid container spacing={1.5} mb={10} justifyContent="center">
          {FEATURES.map((f) => (
            <Grid item key={f.label}>
              <Box sx={{
                display: 'flex', alignItems: 'center', gap: 1,
                px: 2, py: 1, bgcolor: 'background.paper',
                border: '1px solid', borderColor: 'divider', borderRadius: 2,
              }}>
                <Box sx={{ color: 'primary.main' }}>{f.icon}</Box>
                <Typography variant="body2" fontWeight={500}>{f.label}</Typography>
              </Box>
            </Grid>
          ))}
        </Grid>

        <Divider sx={{ mb: 8 }} />

        {/* Timeline */}
        <Box sx={{ textAlign: 'center', mb: 5 }}>
          <Chip label="Our Story" size="small" color="primary" sx={{ mb: 2 }} />
          <Typography variant="h4" fontWeight={800}>How we got here</Typography>
        </Box>
        <Box sx={{ maxWidth: 600, mx: 'auto', mb: 10 }}>
          {TIMELINE.map((t, i) => (
            <Box key={t.year} sx={{ display: 'flex', gap: 3, mb: 4, position: 'relative' }}>
              <Box sx={{ flexShrink: 0, textAlign: 'right', width: 80 }}>
                <Typography variant="caption" color="primary.main" fontWeight={700}>{t.year}</Typography>
              </Box>
              <Box sx={{ position: 'relative' }}>
                <Box sx={{
                  width: 12, height: 12, borderRadius: '50%', bgcolor: 'primary.main',
                  mt: 0.4, flexShrink: 0,
                  '&::after': i < TIMELINE.length - 1 ? {
                    content: '""', position: 'absolute', left: 5, top: 14,
                    width: 2, height: 40, bgcolor: 'divider',
                  } : {},
                }} />
              </Box>
              <Box sx={{ pb: 1 }}>
                <Typography variant="subtitle2" fontWeight={700}>{t.label}</Typography>
                <Typography variant="body2" color="text.secondary" lineHeight={1.7}>{t.desc}</Typography>
              </Box>
            </Box>
          ))}
        </Box>

        <Divider sx={{ mb: 8 }} />

        {/* Values */}
        <Grid container spacing={6} alignItems="flex-start" mb={10}>
          <Grid item xs={12} md={5}>
            <Chip label="Our Values" size="small" color="primary" sx={{ mb: 2 }} />
            <Typography variant="h4" fontWeight={800} mb={2}>How we operate</Typography>
            <Typography variant="body1" color="text.secondary" lineHeight={1.9}>
              We're a small, focused team. No VC pressure, no growth-at-all-costs mindset.
              We build tools we'd use ourselves and treat our users the way we'd want to be treated.
            </Typography>
          </Grid>
          <Grid item xs={12} md={7}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              {VALUES.map((v) => (
                <Box key={v} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
                  <CheckCircle fontSize="small" color="success" sx={{ mt: 0.2, flexShrink: 0 }} />
                  <Typography variant="body2" color="text.secondary" lineHeight={1.8}>{v}</Typography>
                </Box>
              ))}
            </Box>
          </Grid>
        </Grid>

        <Divider sx={{ mb: 8 }} />

        {/* Founder */}
        <Box sx={{ textAlign: 'center', mb: 5 }}>
          <Chip label="The Founder" size="small" color="primary" sx={{ mb: 2 }} />
          <Typography variant="h4" fontWeight={800} mb={1}>Built by someone who gets it</Typography>
          <Typography variant="body1" color="text.secondary" maxWidth={500} mx="auto" mb={6}>
            Telegizer is an independent product, built and maintained by one person who was tired of
            patching together five different bots to run a Telegram community.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 10 }}>
          <Card sx={{ maxWidth: 360, width: '100%', border: '1px solid', borderColor: 'divider' }}>
            <CardContent sx={{ textAlign: 'center', p: '28px !important' }}>
              <Avatar
                src="/founder.jpg"
                alt="Fazal Elahi — Founder of Telegizer"
                sx={{ width: 120, height: 120, mx: 'auto', mb: 2.5, border: '3px solid', borderColor: 'primary.main' }}
              />
              <Typography variant="h6" fontWeight={700} mb={0.5}>Fazal Elahi</Typography>
              <Typography variant="body2" color="text.secondary" mb={0.5}>Founder & Developer</Typography>
              <Typography variant="caption" color="text.disabled" display="block" mb={2.5}>
                Building Telegizer since 2024
              </Typography>
              <Typography variant="body2" color="text.secondary" lineHeight={1.8} mb={3} textAlign="left">
                I started Telegizer because I was managing multiple Telegram communities and spending
                hours every day on moderation, scheduling, and answering the same questions.
                I built the tool I needed — and made it available to every community manager who
                feels the same pain.
              </Typography>
              <Box sx={{ display: 'flex', gap: 1.5, justifyContent: 'center' }}>
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<Email fontSize="small" />}
                  href="mailto:fazalelahi5577@gmail.com?subject=Telegizer%20Support%20Request"
                  sx={{ fontSize: '0.75rem' }}
                >
                  Email Me
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<Telegram fontSize="small" />}
                  href="https://t.me/telegizer_support"
                  target="_blank"
                  rel="noopener noreferrer"
                  sx={{ fontSize: '0.75rem' }}
                >
                  Telegram
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Box>

        <Divider sx={{ mb: 8 }} />

        {/* CTA */}
        <Box sx={{
          textAlign: 'center', py: 8,
          background: 'linear-gradient(135deg, rgba(37,99,235,0.08) 0%, rgba(124,58,237,0.08) 100%)',
          borderRadius: 3, border: '1px solid', borderColor: 'divider',
          mb: 6,
        }}>
          <Typography variant="h4" fontWeight={800} mb={2}>
            Ready to grow your Telegram community?
          </Typography>
          <Typography variant="body1" color="text.secondary" mb={4} maxWidth={480} mx="auto">
            Connect your first bot for free and see what automated community management looks like.
            No credit card. No code. No complexity.
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Button variant="contained" size="large" onClick={() => navigate('/register')}>
              Create Free Account
            </Button>
            <Button
              variant="outlined" size="large"
              endIcon={<OpenInNew fontSize="small" />}
              onClick={() => navigate('/contact')}
            >
              Talk to Us
            </Button>
          </Box>
        </Box>

        <Divider sx={{ mb: 3 }} />
        <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap', pb: 4 }}>
          {[
            { label: 'Privacy Policy', path: '/privacy' },
            { label: 'Terms of Service', path: '/terms' },
            { label: 'Contact', path: '/contact' },
            { label: 'Back to Home', path: '/' },
          ].map(({ label, path }) => (
            <Typography
              key={path}
              variant="body2"
              color="primary.main"
              sx={{ cursor: 'pointer' }}
              onClick={() => navigate(path)}
            >
              {label}
            </Typography>
          ))}
        </Box>
      </Container>
    </Box>
  );
}
