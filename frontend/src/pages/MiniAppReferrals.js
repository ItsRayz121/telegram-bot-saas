import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Card, CardContent, Button, CircularProgress,
  Divider, Alert, Stack, Chip,
} from '@mui/material';
import { CardGiftcard, ContentCopy, Share, CheckCircle } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { tmaApi } from '../contexts/TelegramContext';
import { useTelegram } from '../contexts/TelegramContext';

const refApi = {
  getStats: () => tmaApi.get('/api/referrals/stats'),
};

const MILESTONES = [
  { count: 3, reward: '7 days Pro free' },
  { count: 10, reward: '30 days Pro free' },
];

export default function MiniAppReferrals() {
  const { appUser, tg, haptic } = useTelegram();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    refApi.getStats()
      .then(r => setStats(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const referralCode = appUser?.referral_code || '';
  const referralUrl = `https://opencalwtest.online/join?ref=${referralCode}`;
  const referralCount = stats?.referral_count ?? 0;

  const handleCopy = () => {
    haptic.impact('light');
    navigator.clipboard.writeText(referralUrl).then(() => {
      setCopied(true);
      toast.success('Link copied!');
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleShare = () => {
    haptic.impact('medium');
    if (tg?.switchInlineQuery) {
      // Share inside Telegram via inline mode
      tg.switchInlineQuery(`Join Telegizer with my link: ${referralUrl}`, ['users', 'groups', 'channels']);
    } else if (navigator.share) {
      navigator.share({
        title: 'Telegizer — Telegram Group Automation',
        text: 'Automate your Telegram groups for free. Join with my referral link:',
        url: referralUrl,
      }).catch(() => {});
    } else {
      handleCopy();
    }
  };

  if (loading) {
    return (
      <Box sx={{ py: 6, textAlign: 'center' }}><CircularProgress size={28} /></Box>
    );
  }

  return (
    <Box sx={{ pt: 1 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2.5 }}>
        <CardGiftcard sx={{ color: 'primary.main', fontSize: 28 }} />
        <Box>
          <Typography fontWeight={700} fontSize="1rem">Refer & Earn</Typography>
          <Typography variant="caption" color="text.secondary">
            Share your link. Earn free Pro days.
          </Typography>
        </Box>
      </Box>

      {/* Referral link card */}
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ p: 2 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1}>
            Your referral link
          </Typography>
          <Box sx={{
            bgcolor: 'rgba(37,99,235,0.08)', borderRadius: 2, p: 1.5, mb: 1.5,
            border: '1px solid rgba(37,99,235,0.2)', wordBreak: 'break-all',
          }}>
            <Typography variant="body2" fontFamily="monospace" fontSize="0.78rem">
              {referralUrl}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button
              fullWidth variant="contained" size="small"
              startIcon={copied ? <CheckCircle fontSize="small" /> : <ContentCopy fontSize="small" />}
              onClick={handleCopy}
              color={copied ? 'success' : 'primary'}
            >
              {copied ? 'Copied!' : 'Copy link'}
            </Button>
            <Button
              fullWidth variant="outlined" size="small"
              startIcon={<Share fontSize="small" />}
              onClick={handleShare}
            >
              Share
            </Button>
          </Stack>
        </CardContent>
      </Card>

      {/* Stats */}
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ p: 2 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1.5}>
            Your stats
          </Typography>
          <Stack direction="row" spacing={2}>
            <Box sx={{ textAlign: 'center', flex: 1 }}>
              <Typography variant="h4" fontWeight={800} color="primary.main">{referralCount}</Typography>
              <Typography variant="caption" color="text.secondary">Signups</Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Box sx={{ textAlign: 'center', flex: 1 }}>
              <Typography variant="h4" fontWeight={800} color="success.main">
                {stats?.rewards_earned_days ?? 0}
              </Typography>
              <Typography variant="caption" color="text.secondary">Pro days earned</Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* Milestones */}
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ p: 2 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1.5}>
            Milestones
          </Typography>
          {MILESTONES.map(m => {
            const done = referralCount >= m.count;
            return (
              <Box key={m.count} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.25 }}>
                <CheckCircle fontSize="small"
                  sx={{ color: done ? 'success.main' : 'text.disabled', flexShrink: 0 }} />
                <Box sx={{ flex: 1 }}>
                  <Typography variant="body2" fontWeight={600}
                    sx={{ color: done ? 'text.primary' : 'text.secondary' }}>
                    {m.count} referrals
                  </Typography>
                  <Typography variant="caption" color="text.disabled">{m.reward}</Typography>
                </Box>
                {done
                  ? <Chip label="Unlocked" color="success" size="small" sx={{ height: 18, fontSize: '0.6rem' }} />
                  : <Typography variant="caption" color="text.disabled">{referralCount}/{m.count}</Typography>
                }
              </Box>
            );
          })}
        </CardContent>
      </Card>

      <Alert severity="info" icon={false} sx={{ fontSize: '0.75rem' }}>
        Rewards apply automatically when your referred user verifies their email.
        You'll receive an email confirmation for each conversion.
      </Alert>
    </Box>
  );
}
