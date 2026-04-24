import React from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  Grid, Chip, Container, Stack, Divider,
} from '@mui/material';
import {
  SmartToy, Shield, Schedule, BarChart, People, CheckCircle,
  AutoAwesome, Security, Bolt,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const FEATURES = [
  {
    icon: <Shield fontSize="large" />,
    title: 'Advanced AutoMod',
    desc: 'Automatically remove spam, links, and offensive content. Set custom rules for your community.',
  },
  {
    icon: <Schedule fontSize="large" />,
    title: 'Scheduled Messages',
    desc: 'Schedule announcements, polls, and posts at exactly the right time in any timezone.',
  },
  {
    icon: <People fontSize="large" />,
    title: 'Member Management',
    desc: 'XP system, levels, warnings, verification challenges, and role-based permissions.',
  },
  {
    icon: <BarChart fontSize="large" />,
    title: 'Analytics Dashboard',
    desc: 'Track member growth, activity, moderation actions, and invite link performance.',
  },
  {
    icon: <AutoAwesome fontSize="large" />,
    title: 'AI Knowledge Base',
    desc: 'Let your bot answer questions automatically from your uploaded documents.',
  },
  {
    icon: <Bolt fontSize="large" />,
    title: 'Webhook Integrations',
    desc: 'Connect GitHub, price feeds, or any service to send messages to your Telegram group.',
  },
];

const PLANS = [
  {
    name: 'Free',
    price: '$0',
    period: 'forever',
    color: 'default',
    features: ['1 bot', '1 group per bot', 'Basic moderation', 'Welcome messages'],
    cta: 'Start Free',
    ctaVariant: 'outlined',
  },
  {
    name: 'Pro',
    price: '$9',
    period: '/month',
    color: 'primary',
    popular: true,
    features: ['5 bots', 'Unlimited groups', 'Scheduled messages', 'Analytics', 'Priority support'],
    cta: 'Get Pro',
    ctaVariant: 'contained',
  },
  {
    name: 'Enterprise',
    price: '$49',
    period: '/month',
    color: 'secondary',
    features: ['50 bots', 'All Pro features', 'API access', 'SLA guarantee', 'Dedicated support'],
    cta: 'Get Enterprise',
    ctaVariant: 'outlined',
  },
];

const STATS = [
  { value: '300+', label: 'Cryptocurrencies Accepted' },
  { value: '17+', label: 'Bot Features' },
  { value: '24/7', label: 'Bot Uptime' },
  { value: '5 min', label: 'Setup Time' },
];

export default function Landing() {
  const navigate = useNavigate();
  const token = localStorage.getItem('token');

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* Nav */}
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.default' }}>
        <Toolbar sx={{ maxWidth: 1200, mx: 'auto', width: '100%', px: { xs: 2, md: 3 } }}>
          <SmartToy sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="h6" fontWeight={700} sx={{ flexGrow: 1 }}>
            BotForge
          </Typography>
          <Button onClick={() => navigate('/pricing')} sx={{ mr: 1, display: { xs: 'none', sm: 'inline-flex' } }}>
            Pricing
          </Button>
          {token ? (
            <Button variant="contained" onClick={() => navigate('/dashboard')}>
              Dashboard
            </Button>
          ) : (
            <Stack direction="row" spacing={1}>
              <Button onClick={() => navigate('/login')}>Sign In</Button>
              <Button variant="contained" onClick={() => navigate('/register')}>
                Start Free
              </Button>
            </Stack>
          )}
        </Toolbar>
      </AppBar>

      {/* Hero */}
      <Box
        sx={{
          background: 'linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%)',
          pt: { xs: 8, md: 12 },
          pb: { xs: 8, md: 12 },
          textAlign: 'center',
          px: 2,
        }}
      >
        <Container maxWidth="md">
          <Chip
            label="Powered by AI — Built for Telegram Communities"
            size="small"
            sx={{ mb: 3, bgcolor: 'primary.main', color: 'white', fontWeight: 600 }}
          />
          <Typography
            variant="h2"
            fontWeight={800}
            mb={3}
            sx={{ fontSize: { xs: '2rem', sm: '2.75rem', md: '3.5rem' }, lineHeight: 1.15 }}
          >
            Automate & Grow Your{' '}
            <Box component="span" sx={{ color: 'primary.main' }}>
              Telegram Community
            </Box>
          </Typography>
          <Typography
            variant="h6"
            color="text.secondary"
            mb={5}
            sx={{ maxWidth: 580, mx: 'auto', fontWeight: 400, lineHeight: 1.6 }}
          >
            BotForge gives you one dashboard to manage moderation, scheduling, member tracking,
            analytics, and AI responses — for every Telegram group you run.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center">
            <Button
              variant="contained"
              size="large"
              onClick={() => navigate('/register')}
              sx={{ py: 1.5, px: 4, fontSize: '1rem' }}
            >
              Start Free — No Credit Card
            </Button>
            <Button
              variant="outlined"
              size="large"
              onClick={() => navigate('/pricing')}
              sx={{ py: 1.5, px: 4, fontSize: '1rem' }}
            >
              View Pricing
            </Button>
          </Stack>
        </Container>
      </Box>

      {/* Stats */}
      <Box sx={{ bgcolor: 'background.paper', borderTop: '1px solid', borderBottom: '1px solid', borderColor: 'divider', py: 4 }}>
        <Container maxWidth="md">
          <Grid container spacing={2} justifyContent="center">
            {STATS.map((s) => (
              <Grid item xs={6} sm={3} key={s.label} sx={{ textAlign: 'center' }}>
                <Typography variant="h4" fontWeight={800} color="primary.main">{s.value}</Typography>
                <Typography variant="body2" color="text.secondary">{s.label}</Typography>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Features */}
      <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
        <Typography variant="h4" fontWeight={700} textAlign="center" mb={1}>
          Everything your community needs
        </Typography>
        <Typography variant="body1" color="text.secondary" textAlign="center" mb={6}>
          One bot. One dashboard. Full control.
        </Typography>
        <Grid container spacing={3}>
          {FEATURES.map((f) => (
            <Grid item xs={12} sm={6} md={4} key={f.title}>
              <Card sx={{ height: '100%', p: 1 }}>
                <CardContent>
                  <Box sx={{ color: 'primary.main', mb: 1.5 }}>{f.icon}</Box>
                  <Typography variant="h6" fontWeight={700} mb={1}>{f.title}</Typography>
                  <Typography variant="body2" color="text.secondary" lineHeight={1.6}>
                    {f.desc}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* How it works */}
      <Box sx={{ bgcolor: 'background.paper', borderTop: '1px solid', borderColor: 'divider', py: { xs: 8, md: 10 } }}>
        <Container maxWidth="md">
          <Typography variant="h4" fontWeight={700} textAlign="center" mb={1}>
            Up and running in 5 minutes
          </Typography>
          <Typography variant="body1" color="text.secondary" textAlign="center" mb={6}>
            No coding required. Just connect your bot and start managing.
          </Typography>
          <Stack spacing={3}>
            {[
              { step: '1', title: 'Create a free account', desc: 'Sign up with your email in seconds.' },
              { step: '2', title: 'Connect your Telegram bot', desc: 'Paste your BotFather token — we handle the rest.' },
              { step: '3', title: 'Add bot to your group', desc: 'Add as admin and your group appears in the dashboard.' },
              { step: '4', title: 'Configure & automate', desc: 'Turn on features, schedule posts, set up AutoMod, and grow.' },
            ].map((item) => (
              <Box key={item.step} sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
                <Box
                  sx={{
                    width: 40, height: 40, borderRadius: '50%', bgcolor: 'primary.main',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0, fontWeight: 700, fontSize: '1rem',
                  }}
                >
                  {item.step}
                </Box>
                <Box>
                  <Typography fontWeight={600} mb={0.25}>{item.title}</Typography>
                  <Typography variant="body2" color="text.secondary">{item.desc}</Typography>
                </Box>
              </Box>
            ))}
          </Stack>
        </Container>
      </Box>

      {/* Pricing preview */}
      <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
        <Typography variant="h4" fontWeight={700} textAlign="center" mb={1}>
          Simple, honest pricing
        </Typography>
        <Typography variant="body1" color="text.secondary" textAlign="center" mb={6}>
          Pay with crypto (USDT, BTC, ETH) or card. Cancel anytime.
        </Typography>
        <Grid container spacing={3} justifyContent="center">
          {PLANS.map((plan) => (
            <Grid item xs={12} sm={6} md={4} key={plan.name}>
              <Card
                sx={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  position: 'relative',
                  border: plan.popular ? '2px solid' : '1px solid',
                  borderColor: plan.popular ? 'primary.main' : 'divider',
                }}
              >
                {plan.popular && (
                  <Chip
                    label="Most Popular"
                    color="primary"
                    size="small"
                    sx={{ position: 'absolute', top: -12, left: '50%', transform: 'translateX(-50%)' }}
                  />
                )}
                <CardContent sx={{ flexGrow: 1, p: 3 }}>
                  <Typography variant="h5" fontWeight={700} mb={1}>{plan.name}</Typography>
                  <Box sx={{ mb: 3 }}>
                    <Typography component="span" variant="h3" fontWeight={800}>{plan.price}</Typography>
                    <Typography component="span" variant="body1" color="text.secondary">{plan.period}</Typography>
                  </Box>
                  <Button
                    fullWidth
                    variant={plan.ctaVariant}
                    color={plan.color === 'default' ? 'inherit' : plan.color}
                    size="large"
                    sx={{ mb: 3 }}
                    onClick={() => navigate(plan.name === 'Free' ? '/register' : '/pricing')}
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
            </Grid>
          ))}
        </Grid>
        <Typography variant="body2" color="text.secondary" textAlign="center" mt={4}>
          Payments accepted via crypto (USDT, BTC, ETH, BNB, 300+ coins) and card (coming soon).
        </Typography>
      </Container>

      {/* CTA Banner */}
      <Box
        sx={{
          background: 'linear-gradient(135deg, #1565c0 0%, #7c4dff 100%)',
          py: { xs: 6, md: 8 },
          textAlign: 'center',
          px: 2,
        }}
      >
        <Typography variant="h4" fontWeight={700} color="white" mb={2}>
          Ready to take control of your community?
        </Typography>
        <Typography variant="body1" sx={{ color: 'rgba(255,255,255,0.85)', mb: 4, maxWidth: 480, mx: 'auto' }}>
          Join now. Your first bot is completely free. No credit card required.
        </Typography>
        <Button
          variant="contained"
          size="large"
          onClick={() => navigate('/register')}
          sx={{ bgcolor: 'white', color: 'primary.main', py: 1.5, px: 5, fontSize: '1rem', '&:hover': { bgcolor: '#f0f0f0' } }}
        >
          Create Free Account
        </Button>
      </Box>

      {/* Footer */}
      <Box sx={{ bgcolor: 'background.paper', borderTop: '1px solid', borderColor: 'divider', py: 4 }}>
        <Container maxWidth="lg">
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <SmartToy sx={{ color: 'primary.main' }} />
              <Typography fontWeight={700}>BotForge</Typography>
            </Box>
            <Stack direction="row" spacing={3} flexWrap="wrap">
              <Button size="small" onClick={() => navigate('/pricing')} sx={{ color: 'text.secondary' }}>Pricing</Button>
              <Button size="small" onClick={() => navigate('/login')} sx={{ color: 'text.secondary' }}>Sign In</Button>
              <Button size="small" onClick={() => navigate('/register')} sx={{ color: 'text.secondary' }}>Register</Button>
            </Stack>
            <Typography variant="caption" color="text.disabled">
              © {new Date().getFullYear()} BotForge. All rights reserved.
            </Typography>
          </Box>
        </Container>
      </Box>
    </Box>
  );
}
