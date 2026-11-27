import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip,
  LinearProgress, Table, TableBody, TableCell, TableRow,
  Skeleton, Avatar,
} from '@mui/material';
import {
  CheckCircle, EmojiEvents, People, CardGiftcard,
  Share, Telegram,
} from '@mui/icons-material';
import { referrals as referralsApi } from '../services/api';
import { track } from '../services/analytics';
import ReferralLinks from '../components/ReferralLinks';

const MILESTONES = [
  { count: 3,  reward: '7 days Pro',    icon: '🎁', color: '#4a9ff5' },
  { count: 10, reward: '1 month Pro',   icon: '🚀', color: '#4fb3a5' },
];

function MilestoneCard({ milestone, total }) {
  const reached = total >= milestone.count;
  const progress = Math.min((total / milestone.count) * 100, 100);
  return (
    <Card
      sx={{
        border: '1px solid',
        borderColor: reached ? 'success.main' : 'divider',
        bgcolor: reached ? 'rgba(76,195,138,0.05)' : 'background.paper',
        borderRadius: 2,
        flex: 1,
        minWidth: 0,
      }}
    >
      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Typography fontSize={22}>{milestone.icon}</Typography>
          <Box sx={{ flex: 1 }}>
            <Typography variant="body2" fontWeight={600}>{milestone.reward}</Typography>
            <Typography variant="caption" color="text.secondary">
              {milestone.count} referrals required
            </Typography>
          </Box>
          {reached && <CheckCircle fontSize="small" sx={{ color: 'success.main' }} />}
        </Box>
        <LinearProgress
          variant="determinate"
          value={progress}
          sx={{
            height: 6, borderRadius: 3,
            bgcolor: 'rgba(255,255,255,0.08)',
            '& .MuiLinearProgress-bar': {
              bgcolor: reached ? 'success.main' : milestone.color,
            },
          }}
        />
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          {reached ? 'Reached! Reward applied automatically.' : `${total} / ${milestone.count}`}
        </Typography>
      </CardContent>
    </Card>
  );
}

function StepBadge({ n, label, sub }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
      <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: '0.85rem', fontWeight: 600, flexShrink: 0 }}>
        {n}
      </Avatar>
      <Box>
        <Typography variant="body2" fontWeight={600}>{label}</Typography>
        <Typography variant="caption" color="text.secondary">{sub}</Typography>
      </Box>
    </Box>
  );
}

export default function Referrals() {
  const [stats, setStats] = useState(null);
  const [leaderboard, setLeaderboard] = useState(null);
  const [loading, setLoading] = useState(true);

  const botUsername = (process.env.REACT_APP_TELEGRAM_BOT_USERNAME || 'telegizer_bot').replace(/^@/, '');
  const refCode  = stats?.referral_code;
  // Both links carry the same code → same referrer credited either way.
  const tgLink   = refCode ? `https://t.me/${botUsername}?start=ref_${refCode}` : '';
  const webLink  = refCode ? `${window.location.origin}/r/${refCode}` : '';
  const inviteLink = tgLink || webLink;

  const handleTelegramShare = () => {
    // Share the web invite URL via Telegram (so it works for non-Telegram recipients too)
    const url = `https://t.me/share/url?url=${encodeURIComponent(webLink || inviteLink)}&text=${encodeURIComponent('Join me on Telegizer — the easiest way to manage your Telegram community!')}`;
    window.open(url, '_blank', 'noopener,noreferrer');
    track('referral_shared', { method: 'telegram' });
  };

  useEffect(() => {
    Promise.all([
      referralsApi.getStats().then(r => setStats(r.data)).catch(() => {}),
      referralsApi.getLeaderboard().then(r => setLeaderboard(r.data)).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  const handleShare = () => {
    if (navigator.share) {
      navigator.share({ title: 'Join Telegizer', text: 'Manage your Telegram groups with Telegizer!', url: webLink || inviteLink }).catch(() => {});
    } else if (inviteLink) {
      navigator.clipboard.writeText(webLink || inviteLink).catch(() => {});
    }
    track('referral_shared', { method: 'native' });
  };

  const total = stats?.total_referrals ?? 0;

  return (
    <Box sx={{ maxWidth: 800, mx: 'auto', px: { xs: 2, md: 3 }, py: 3 }}>

      {/* ── Hero ── */}
      <Box sx={{ mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
          <CardGiftcard sx={{ color: 'primary.main', fontSize: 28 }} />
          <Typography variant="h5" fontWeight={600}>Invite Friends — Earn Free Pro</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary">
          Share your link. When friends sign up and activate, you earn free Pro time automatically.
        </Typography>
      </Box>

      {/* ── Invite link box ── */}
      <Card sx={{ mb: 3, border: '1px solid', borderColor: 'primary.main', borderRadius: 2, bgcolor: 'rgba(74,159,245,0.05)' }}>
        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
          <ReferralLinks refCode={refCode} botUsername={botUsername} primary="telegram" />
          <Typography variant="caption" color="text.disabled" sx={{ display: 'block', mt: 1 }}>
            Either link credits you — friends are tracked to the same referral code.
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, mt: 1.5, flexWrap: 'wrap' }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<Share />}
              onClick={handleShare}
              disabled={!inviteLink}
              sx={{ borderRadius: 1.5 }}
            >
              Share
            </Button>
            <Button
              variant="contained"
              size="small"
              startIcon={<Telegram />}
              onClick={handleTelegramShare}
              disabled={!inviteLink}
              sx={{ borderRadius: 1.5, bgcolor: '#0088cc', '&:hover': { bgcolor: '#007ab8' } }}
            >
              Share on Telegram
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* ── Milestones ── */}
      <Typography variant="subtitle2" fontWeight={600} mb={1.5}>Your Progress</Typography>
      {loading ? (
        <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
          <Skeleton variant="rounded" height={100} sx={{ flex: 1 }} />
          <Skeleton variant="rounded" height={100} sx={{ flex: 1 }} />
        </Box>
      ) : (
        <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap' }}>
          {MILESTONES.map(m => <MilestoneCard key={m.count} milestone={m} total={total} />)}
        </Box>
      )}

      {total > 0 && (
        <Chip
          icon={<People fontSize="small" />}
          label={`${total} successful referral${total !== 1 ? 's' : ''} total`}
          size="small"
          color="primary"
          variant="outlined"
          sx={{ mb: 3 }}
        />
      )}

      {/* ── Leaderboard ── */}
      {!loading && leaderboard && leaderboard.leaderboard?.length > 0 && (
        <Card sx={{ mb: 3, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
          <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <EmojiEvents sx={{ color: 'warning.main' }} />
              <Typography variant="subtitle2" fontWeight={600}>
                Top Referrers — {leaderboard.month || ''}
              </Typography>
            </Box>
            <Table size="small" sx={{ tableLayout: 'fixed', width: '100%' }}>
              <TableBody>
                {leaderboard.leaderboard.map((entry) => (
                  <TableRow
                    key={entry.rank}
                    sx={{ bgcolor: entry.is_current_user ? 'rgba(74,159,245,0.07)' : 'transparent' }}
                  >
                    <TableCell sx={{ width: 36, pr: 0, fontWeight: 600, color: entry.rank <= 3 ? 'warning.main' : 'text.secondary', fontSize: '0.8rem' }}>
                      {entry.rank <= 3 ? ['🥇','🥈','🥉'][entry.rank - 1] : `#${entry.rank}`}
                    </TableCell>
                    <TableCell sx={{ fontWeight: entry.is_current_user ? 600 : 400, fontSize: '0.85rem' }}>
                      {entry.name}
                      {entry.is_current_user && <Chip label="You" size="small" color="primary" sx={{ ml: 1, height: 18, fontSize: '0.6rem' }} />}
                    </TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600, fontSize: '0.85rem' }}>
                      {entry.referrals}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {leaderboard.current_user_rank === null && leaderboard.current_user_count === 0 && (
              <Typography variant="caption" color="text.disabled" display="block" mt={1.5} textAlign="center">
                Refer friends to appear on the leaderboard
              </Typography>
            )}
            {leaderboard.current_user_rank === null && leaderboard.current_user_count > 0 && (
              <Box sx={{ mt: 1.5, pt: 1.5, borderTop: '1px dashed', borderColor: 'divider' }}>
                <Typography variant="caption" color="text.secondary">
                  Your rank this month: unranked · {leaderboard.current_user_count} referral{leaderboard.current_user_count !== 1 ? 's' : ''}
                </Typography>
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── How it works ── */}
      <Card sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
          <Typography variant="subtitle2" fontWeight={600} mb={2}>How it works</Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <StepBadge n="1" label="Copy your link" sub="Share it anywhere — Telegram, Twitter, email, anywhere." />
            <StepBadge n="2" label="Friend signs up" sub="They register using your unique referral link." />
            <StepBadge n="3" label="You earn automatically" sub="Hit 3 referrals → 7 days Pro. Hit 10 → 1 month Pro. No action needed." />
          </Box>
        </CardContent>
      </Card>

    </Box>
  );
}
