import React, { useState } from 'react';
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

const CONTACT_CHANNELS = [
  {
    icon: <Email />,
    title: 'General Support',
    desc: 'Account issues, billing questions, feature help',
    value: 'fazalelahi5577@gmail.com',
    href: 'mailto:fazalelahi5577@gmail.com?subject=Telegizer%20Support%20Request',
    color: '#2563EB',
    responseTime: '< 24 hours',
  },
  {
    icon: <BugReport />,
    title: 'Bug Reports',
    desc: 'Found something broken? Tell us and we\'ll fix it fast.',
    value: 'bugs@telegizer.com',
    href: 'mailto:bugs@telegizer.com',
    color: '#ef4444',
    responseTime: '< 12 hours',
  },
  {
    icon: <Business />,
    title: 'Enterprise & Partnerships',
    desc: 'Custom plans, white-label, API access, partnerships',
    value: 'enterprise@telegizer.com',
    href: 'mailto:enterprise@telegizer.com',
    color: '#7C3AED',
    responseTime: '< 48 hours',
  },
  {
    icon: <HelpOutline />,
    title: 'Privacy & Data',
    desc: 'GDPR requests, data deletion, privacy concerns',
    value: 'privacy@telegizer.com',
    href: 'mailto:privacy@telegizer.com',
    color: '#06B6D4',
    responseTime: '< 30 days (GDPR)',
  },
];

const SOCIAL_CHANNELS = [
  {
    icon: <Telegram />,
    title: 'Telegram Community',
    desc: 'Join our official support group for quick answers and announcements.',
    label: '@TelegizerSupport',
    href: 'https://t.me/TelegizerSupport',
    color: '#0088cc',
  },
  {
    icon: <Twitter />,
    title: 'Twitter / X',
    desc: 'Follow us for updates, tips, and product news.',
    label: '@TelegizerApp',
    href: 'https://twitter.com/TelegizerApp',
    color: '#1DA1F2',
  },
];

const FAQ = [
  {
    q: 'How do I link my Telegram group?',
    a: 'Add @telegizer_bot as an admin in your group, run /linkgroup, then paste the code in your dashboard under Groups → Link Group.',
  },
  {
    q: 'My bot shows "Restarting" — what do I do?',
    a: 'Toggle the bot off and back on in your dashboard. If it persists, revoke and re-enter your bot token from @BotFather. This is usually caused by a Telegram conflict from another running instance.',
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
    a: 'Email fazalelahi5577@gmail.com within 14 days of your first purchase with your account email and payment reference. We process refunds within 3 business days.',
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
    const body = encodeURIComponent(`From: ${form.name} <${form.email}>\nSubject: ${form.subject}\n\n${form.message}`);
    window.open(`mailto:fazalelahi5577@gmail.com?subject=${encodeURIComponent(form.subject || 'Contact from telegizer.com')}&body=${body}`, '_blank');
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
        copy and email us directly at <strong>support@telegizer.com</strong>.
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
  const navigate = useNavigate();

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <PageNav />

      {/* Hero */}
      <Box sx={{ py: { xs: 6, md: 8 }, textAlign: 'center', borderBottom: '1px solid', borderColor: 'divider' }}>
        <Container maxWidth="md">
          <Typography variant="h3" fontWeight={800} mb={2}>Contact Us</Typography>
          <Typography variant="body1" color="text.secondary" maxWidth={520} mx="auto">
            We're a small team and we actually read every message. Tell us what you need and
            we'll get back to you quickly.
          </Typography>
          <Box sx={{ display: 'flex', gap: 1.5, justifyContent: 'center', flexWrap: 'wrap', mt: 3 }}>
            <Chip icon={<Schedule sx={{ fontSize: 14 }} />} label="Mon–Fri, 9am–6pm UTC" size="small" variant="outlined" />
            <Chip label="Average reply: under 24 hours" size="small" variant="outlined" color="success" />
          </Box>
        </Container>
      </Box>

      <Container maxWidth="lg" sx={{ py: 6 }}>

        {/* Email channels */}
        <Typography variant="h5" fontWeight={700} mb={3}>Email Channels</Typography>
        <Grid container spacing={2} mb={6}>
          {CONTACT_CHANNELS.map((ch) => (
            <Grid item xs={12} sm={6} key={ch.title}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                    <Box sx={{ color: ch.color }}>{ch.icon}</Box>
                    <Box>
                      <Typography variant="subtitle2" fontWeight={700}>{ch.title}</Typography>
                      <Chip label={ch.responseTime} size="small" sx={{ height: 18, fontSize: '0.65rem', mt: 0.25 }} />
                    </Box>
                  </Box>
                  <Typography variant="body2" color="text.secondary" mb={1.5} lineHeight={1.7}>
                    {ch.desc}
                  </Typography>
                  <Link href={ch.href} color="primary.main" underline="hover" variant="body2" fontFamily="monospace">
                    {ch.value}
                  </Link>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        {/* Community */}
        <Typography variant="h5" fontWeight={700} mb={3}>Community & Social</Typography>
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
                  <Link href={ch.href} target="_blank" rel="noopener noreferrer" color="primary.main" underline="hover" variant="body2">
                    {ch.label}
                  </Link>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        {/* Send us a message */}
        <Grid container spacing={4} mb={6}>
          <Grid item xs={12} md={6}>
            <Typography variant="h5" fontWeight={700} mb={1}>Send Us a Message</Typography>
            <Typography variant="body2" color="text.secondary" mb={2}>
              Fill in the form and we'll open your email client with everything pre-filled.
              You can also email us directly at{' '}
              <Link href="mailto:fazalelahi5577@gmail.com?subject=Telegizer%20Support%20Request" color="primary.main" underline="hover">
                fazalelahi5577@gmail.com
              </Link>.
            </Typography>
            <ContactForm />
          </Grid>

          {/* FAQ */}
          <Grid item xs={12} md={6}>
            <Typography variant="h5" fontWeight={700} mb={3}>Frequently Asked Questions</Typography>
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
        <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap', pb: 4 }}>
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
