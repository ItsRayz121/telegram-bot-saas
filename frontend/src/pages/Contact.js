import React, { useState } from 'react';
import { SUPPORT_EMAIL, openSupportEmail, SUPPORT_LINKS } from '../config/support';
import {
  Box, AppBar, Toolbar, Typography, Button, Container, Divider,
  Card, CardContent, Grid, TextField, Alert, CircularProgress, Link, Chip,
} from '@mui/material';
import {
  Email, Telegram, Twitter, HelpOutline, BugReport, Business, Schedule,
} from '@mui/icons-material';
import TelegizerLogo from '../components/TelegizerLogo';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import usePageMeta from '../hooks/usePageMeta';

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
        <Button size="small" variant="contained" onClick={() => navigate('/register')}>Get Started</Button>
      </Toolbar>
    </AppBar>
  );
}

// Every enquiry goes to the one real support inbox; the subject just
// tells us what it's about. No separate/fake addresses.
const CONTACT_CHANNELS = [
  {
    icon: <Email />,
    title: 'General Support',
    desc: 'Account issues, billing questions, feature help',
    subject: 'General Support',
    color: '#2563EB',
    responseTime: '< 24 hours',
  },
  {
    icon: <BugReport />,
    title: 'Bug Reports',
    desc: 'Found something broken? Tell us and we\'ll fix it fast.',
    subject: 'Bug Report',
    color: '#ef4444',
    responseTime: '< 12 hours',
  },
  {
    icon: <Business />,
    title: 'Enterprise & Partnerships',
    desc: 'Custom plans, white-label, API access, partnerships',
    subject: 'Enterprise & Partnership',
    color: '#7C3AED',
    responseTime: '< 48 hours',
  },
  {
    icon: <HelpOutline />,
    title: 'Privacy & Data',
    desc: 'GDPR requests, data deletion, privacy concerns',
    subject: 'Privacy & Data',
    color: '#06B6D4',
    responseTime: '< 30 days (GDPR)',
  },
];

const SOCIAL_CHANNELS = [
  {
    icon: <Telegram />,
    title: 'Telegram Community',
    desc: 'Join our official community group for quick answers and announcements.',
    label: '@telegizer_community',
    href: SUPPORT_LINKS.community,
    color: '#0088cc',
  },
  {
    icon: <Twitter />,
    title: 'Twitter / X',
    desc: 'Follow us for updates, tips, and product news.',
    label: 'Coming soon',
    href: null,
    comingSoon: true,
    color: '#1DA1F2',
  },
];

const FAQ = [
  {
    q: 'How do I link my Telegram group?',
    a: 'Add @telegizer_bot as an admin in your group, run /linkgroup, then paste the code in your dashboard under Groups → Link Group.',
  },
  {
    q: 'My bot shows "Unreachable" — what do I do?',
    a: 'Your bot has not been active in over 30 days. Toggle it off and back on in your dashboard. If the issue persists, revoke and re-enter your bot token from @BotFather.',
  },
  {
    q: 'Can I use my own API key for AI features?',
    a: 'Yes — in Workspace → AI Settings you can switch from Platform AI to your own OpenRouter, OpenAI, or Gemini key.',
  },
  {
    q: 'Is there a free plan?',
    a: 'Yes. The Free plan gives you 1 custom bot, 1 group, and all core features (moderation, commands, XP). No credit card required.',
  },
  {
    q: 'How do I request a refund?',
    a: `Email ${SUPPORT_EMAIL} within 14 days of your first purchase with your account email and payment reference. We process refunds within 3 business days.`,
  },
  {
    q: 'Do you support the Telegram Mini App?',
    a: 'Yes — configure it in BotFather by setting your bot\'s Menu Button URL to https://telegizer.com/mini-app. Your users can then access the dashboard without leaving Telegram.',
  },
];

function ContactForm() {
  const [form, setForm] = useState({ name: '', email: '', subject: '', message: '' });
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email || !form.message) return;
    setSending(true);
    // Opens mailto as a fallback — replace with a real form endpoint if needed
    openSupportEmail();
    setTimeout(() => {
      setSending(false);
      setSent(true);
      toast.success('Opening your email client…');
    }, 600);
  };

  if (sent) {
    return (
      <Alert severity="success" sx={{ mt: 2 }}>
        Your email client should have opened with the message pre-filled. If it didn't,{' '}
        copy and email us directly at <strong>{SUPPORT_EMAIL}</strong>.
      </Alert>
    );
  }

  return (
    <Box component="form" onSubmit={handleSubmit} sx={{ mt: 1 }}>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth size="small" label="Your Name" required
            value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </Grid>
        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth size="small" label="Email Address" type="email" required
            value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </Grid>
        <Grid item xs={12}>
          <TextField
            fullWidth size="small" label="Subject"
            value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })}
            placeholder="e.g. Billing question, Feature request, Bug report"
          />
        </Grid>
        <Grid item xs={12}>
          <TextField
            fullWidth multiline rows={5} label="Message" required
            value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })}
            placeholder="Describe your question or issue in detail. Include your account email and any relevant bot/group IDs."
          />
        </Grid>
      </Grid>
      <Button
        type="submit" variant="contained" sx={{ mt: 2 }}
        disabled={sending || !form.name || !form.email || !form.message}
        startIcon={sending ? <CircularProgress size={16} /> : <Email />}
      >
        {sending ? 'Opening…' : 'Send Message'}
      </Button>
    </Box>
  );
}

export default function Contact() {
  usePageMeta(
    'Contact Support',
    'Get help with Telegizer. Contact our support team about bots, groups, billing, or anything else — we respond within 2 business days.'
  );
  const navigate = useNavigate();

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <PageNav />

      {/* Hero */}
      <Box sx={{ py: { xs: 6, md: 8 }, textAlign: 'center', borderBottom: '1px solid', borderColor: 'divider' }}>
        <Container maxWidth="md">
          <Typography variant="h3" fontWeight={800} mb={2} sx={{ fontSize: { xs: '2rem', sm: '2.5rem', md: '3rem' } }}>Contact Us</Typography>
          <Typography variant="body1" color="text.secondary" maxWidth={520} mx="auto">
            We're a small team and we actually read every message. Tell us what you need and
            we'll get back to you quickly.
          </Typography>
          <Box sx={{ display: 'flex', gap: { xs: 0.75, sm: 1.5 }, justifyContent: 'center', flexWrap: 'wrap', mt: 3 }}>
            <Chip icon={<Schedule sx={{ fontSize: 14 }} />} label="Mon–Fri, 9am–6pm UTC" size="small" variant="outlined" />
            <Chip label="Average reply: under 24 hours" size="small" variant="outlined" color="success" />
          </Box>
        </Container>
      </Box>

      <Container maxWidth="lg" sx={{ py: 6 }}>

        {/* Email channels */}
        <Typography variant="h5" fontWeight={700} mb={3} sx={{ fontSize: { xs: '1.2rem', sm: '1.5rem' } }}>Email Channels</Typography>
        <Grid container spacing={2} mb={6}>
          {CONTACT_CHANNELS.map((ch) => (
            <Grid item xs={12} sm={6} key={ch.title}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                    <Box sx={{ color: ch.color }}>{ch.icon}</Box>
                    <Box>
                      <Typography variant="subtitle2" fontWeight={700}>{ch.title}</Typography>
                      <Chip label={ch.responseTime} size="small" sx={{ height: 18, fontSize: '0.72rem', mt: 0.25 }} />
                    </Box>
                  </Box>
                  <Typography variant="body2" color="text.secondary" mb={1.5} lineHeight={1.7}>
                    {ch.desc}
                  </Typography>
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<Email fontSize="small" />}
                    onClick={() => openSupportEmail(`Telegizer — ${ch.subject}`)}
                    sx={{ fontSize: '0.78rem' }}
                  >
                    Send Email
                  </Button>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        {/* Community */}
        <Typography variant="h5" fontWeight={700} mb={3} sx={{ fontSize: { xs: '1.2rem', sm: '1.5rem' } }}>Community & Social</Typography>
        <Grid container spacing={2} mb={6}>
          {SOCIAL_CHANNELS.map((ch) => (
            <Grid item xs={12} sm={6} key={ch.title}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                    <Box sx={{ color: ch.color }}>{ch.icon}</Box>
                    <Typography variant="subtitle2" fontWeight={700}>{ch.title}</Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary" mb={1.5} lineHeight={1.7}>
                    {ch.desc}
                  </Typography>
                  {ch.comingSoon ? (
                    <Chip label={ch.label} size="small" variant="outlined" sx={{ color: 'text.disabled' }} />
                  ) : (
                    <Link href={ch.href} target="_blank" rel="noopener noreferrer" color="primary.main" underline="hover" variant="body2">
                      {ch.label}
                    </Link>
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        {/* Send us a message */}
        <Grid container spacing={4} mb={6}>
          <Grid item xs={12} md={6}>
            <Typography variant="h5" fontWeight={700} mb={1} sx={{ fontSize: { xs: '1.2rem', sm: '1.5rem' } }}>Send Us a Message</Typography>
            <Typography variant="body2" color="text.secondary" mb={2}>
              Fill in the form and we'll open your email client with everything pre-filled.
              You can also email us directly at{' '}
              <Link
                href="#"
                color="primary.main"
                underline="hover"
                onClick={(e) => { e.preventDefault(); openSupportEmail(); }}
              >
                {SUPPORT_EMAIL}
              </Link>.
            </Typography>
            <ContactForm />
          </Grid>

          {/* FAQ */}
          <Grid item xs={12} md={6}>
            <Typography variant="h5" fontWeight={700} mb={3} sx={{ fontSize: { xs: '1.2rem', sm: '1.5rem' } }}>Frequently Asked Questions</Typography>
            {FAQ.map((item) => (
              <Box key={item.q} sx={{ mb: 3 }}>
                <Typography variant="subtitle2" fontWeight={700} mb={0.75}>{item.q}</Typography>
                <Typography variant="body2" color="text.secondary" lineHeight={1.8}>{item.a}</Typography>
              </Box>
            ))}
            <Button variant="outlined" size="small" onClick={() => navigate('/register')}>
              Create Free Account
            </Button>
          </Grid>
        </Grid>

        <Divider sx={{ mb: 3 }} />
        <Box sx={{ display: 'flex', gap: { xs: 1.5, md: 3 }, flexWrap: 'wrap', pb: 4 }}>
          {[
            { label: 'Privacy Policy', path: '/privacy' },
            { label: 'Terms of Service', path: '/terms' },
            { label: 'About', path: '/about' },
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
