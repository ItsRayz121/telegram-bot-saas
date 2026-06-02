import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Button, Card, CardContent, Chip,
  Container, CircularProgress, Avatar, Divider, Stack,
} from '@mui/material';
import {
  SmartToy, Shield, BarChart, CheckCircle, ArrowForward,
  CardGiftcard, People, EmojiEvents,
} from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { referrals } from '../services/api';
import TelegizerLogo from '../components/TelegizerLogo';

const FEATURES = [
  { icon: Shield,    label: 'AutoMod',           desc: 'Spam, links, caps — removed automatically' },
  { icon: SmartToy,  label: 'AI Knowledge Base',  desc: 'Bot answers FAQs from your docs' },
  { icon: BarChart,  label: 'Analytics',          desc: 'Growth, engagement, top members' },
  { icon: People,    label: 'XP & Levels',        desc: 'Gamified community engagement' },
];

const SOCIAL_PROOF = [
  '5,000+ Telegram communities managed',
  'Free plan forever — no credit card required',
  'Setup in under 2 minutes',
];

export default function InviteLanding() {
  const navigate = useNavigate();
  const { code } = useParams();

  const [referrerName, setReferrerName] = useState(null);
  const [loading, setLoading] = useState(!!code);

  useEffect(() => {
    if (!code) return;
    referrals.lookupCode(code)
      .then((res) => {
        if (res.data.valid) setReferrerName(res.data.referrer_first_name);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [code]);

  const handleGetStarted = () => {
    if (window?.Telegram?.WebApp?.initData) {
      navigate('/mini-app', { replace: true });
    } else {
      navigate(`/register${code ? `?ref=${code}` : ''}`);
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', display: 'flex', flexDirection: 'column' }}>
      {/* Nav */}
      <Box sx={{ px: { xs: 2, md: 4 }, py: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <TelegizerLogo size={28} />
        <Button variant="outlined" size="small" onClick={() => navigate('/login')}>
          Sign in
        </Button>
      </Box>

      <Container maxWidth="sm" sx={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', py: 6 }}>

        {/* Referral badge */}
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mb: 4 }}>
            <CircularProgress size={24} />
          </Box>
        ) : referrerName ? (
          <Box sx={{ textAlign: 'center', mb: 4 }}>
            <Avatar
              sx={{ width: 56, height: 56, bgcolor: 'primary.main', fontSize: 24, mx: 'auto', mb: 1.5 }}
            >
              {referrerName[0].toUpperCase()}
            </Avatar>
            <Chip
              icon={<CardGiftcard />}
              label={`${referrerName} invited you to Telegizer`}
              color="primary"
              sx={{ fontWeight: 600, px: 1 }}
            />
          </Box>
        ) : null}

        {/* Hero */}
        <Box sx={{ textAlign: 'center', mb: 4 }}>
          <Typography variant="h4" fontWeight={800} gutterBottom>
            Run your Telegram group on autopilot
          </Typography>
          <Typography variant="body1" color="text.secondary" maxWidth={420} mx="auto">
            Telegizer handles moderation, welcome messages, scheduled posts, analytics,
            and AI-powered responses — so you can focus on building your community.
          </Typography>
        </Box>

        {/* Social proof */}
        <Stack direction="row" flexWrap="wrap" gap={1} justifyContent="center" mb={3}>
          {SOCIAL_PROOF.map(s => (
            <Chip
              key={s}
              icon={<EmojiEvents sx={{ fontSize: '14px !important' }} />}
              label={s}
              size="small"
              variant="outlined"
              sx={{ fontSize: '0.72rem' }}
            />
          ))}
        </Stack>

        {/* Feature list */}
        <Card sx={{ mb: 4 }}>
          <CardContent sx={{ p: { xs: 2, md: 3 } }}>
            <Stack spacing={2}>
              {FEATURES.map(({ icon: Icon, label, desc }) => (
                <Box key={label} sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Box sx={{ p: 1, borderRadius: 2, bgcolor: 'rgba(37,99,235,0.12)', flexShrink: 0 }}>
                    <Icon sx={{ fontSize: 20, color: 'primary.main' }} />
                  </Box>
                  <Box>
                    <Typography variant="body2" fontWeight={700}>{label}</Typography>
                    <Typography variant="caption" color="text.secondary">{desc}</Typography>
                  </Box>
                  <CheckCircle sx={{ ml: 'auto', color: 'success.main', fontSize: 18, flexShrink: 0 }} />
                </Box>
              ))}
            </Stack>
          </CardContent>
        </Card>

        {/* CTA */}
        <Button
          variant="contained"
          size="large"
          fullWidth
          endIcon={<ArrowForward />}
          onClick={handleGetStarted}
          sx={{ py: 1.5, fontSize: '1rem', fontWeight: 700, mb: 2 }}
        >
          {referrerName ? `Accept ${referrerName}'s Invite — Get Started Free` : 'Get Started Free'}
        </Button>
        <Typography variant="caption" color="text.secondary" textAlign="center" display="block">
          No credit card required · Free plan forever · Setup in 2 minutes
        </Typography>

        <Divider sx={{ my: 3 }} />

        <Typography variant="caption" color="text.secondary" textAlign="center" display="block">
          Already have an account?{' '}
          <Typography
            component="span"
            variant="caption"
            color="primary.main"
            sx={{ cursor: 'pointer', textDecoration: 'underline' }}
            onClick={() => navigate('/login')}
          >
            Sign in
          </Typography>
        </Typography>
      </Container>
    </Box>
  );
}
