import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Container, Typography, Card, CardContent, Button, Chip,
  LinearProgress, Table, TableBody, TableCell, TableRow, Skeleton, Avatar,
} from '@mui/material';
import {
  CardGiftcard, ArrowBack, EmojiEvents, People, CheckCircle,
} from '@mui/icons-material';
import { referrals as referralsApi } from '../../services/api';
import ReferralLinks from '../../components/ReferralLinks';

// Same account-level referral system as Telegizer — Guildizer shares the unified
// account/plan, so the referral code, milestones and rewards are identical.
// Whether a friend uses the Website link or the Telegram link, the SAME referrer
// is credited (both carry the same code). Here the Website link is the primary
// share surface since Discord communities share on the web, not Telegram.
const MILESTONES = [
  { count: 3,  reward: '7 days Pro',  icon: '🎁', color: '#5865F2' },
  { count: 10, reward: '1 month Pro', icon: '🚀', color: '#9d6cf7' },
];

function MilestoneCard({ milestone, total }) {
  const reached = total >= milestone.count;
  const progress = Math.min((total / milestone.count) * 100, 100);
  return (
    <Card
      sx={{
        border: '1px solid',
        borderColor: reached ? 'success.main' : 'divider',
        bgcolor: reached ? 'rgba(34,197,94,0.05)' : 'background.paper',
        borderRadius: 2, flex: 1, minWidth: 0,
      }}
    >
      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Typography fontSize={22}>{milestone.icon}</Typography>
          <Box sx={{ flex: 1 }}>
            <Typography variant="body2" fontWeight={700}>{milestone.reward}</Typography>
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
            height: 6, borderRadius: 3, bgcolor: 'rgba(255,255,255,0.08)',
            '& .MuiLinearProgress-bar': { bgcolor: reached ? 'success.main' : milestone.color },
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
      <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: '0.85rem', fontWeight: 700, flexShrink: 0 }}>
        {n}
      </Avatar>
      <Box>
        <Typography variant="body2" fontWeight={600}>{label}</Typography>
        <Typography variant="caption" color="text.secondary">{sub}</Typography>
      </Box>
    </Box>
  );
}

export default function GuildizerReferrals() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [leaderboard, setLeaderboard] = useState(null);
  const [loading, setLoading] = useState(true);

  const botUsername = (process.env.REACT_APP_TELEGRAM_BOT_USERNAME || 'telegizer_bot').replace(/^@/, '');
  const refCode = stats?.referral_code;
  const total = stats?.total_referrals ?? 0;

  useEffect(() => {
    Promise.all([
      referralsApi.getStats().then(r => setStats(r.data)).catch(() => {}),
      referralsApi.getLeaderboard().then(r => setLeaderboard(r.data)).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  return (
    <Container maxWidth="md" sx={{ py: { xs: 2, sm: 3 } }}>
      <Button startIcon={<ArrowBack />} size="small" onClick={() => navigate('/guildizer')} sx={{ mb: 2 }}>
        Back to Guildizer
      </Button>

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <CardGiftcard color="primary" />
        <Typography variant="h5" fontWeight={800}>Invite Friends — Earn Free Pro</Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Share your link. When friends sign up and activate, you earn free Pro time automatically —
        it unlocks Pro across Telegizer, Echo and Guildizer on the same account.
      </Typography>

      {/* Share links */}
      <Card sx={{ mb: 3, border: '1px solid', borderColor: 'primary.main', borderRadius: 2, bgcolor: 'rgba(88,101,242,0.05)' }}>
        <CardContent sx={{ p: { xs: 2, sm: 2.5 }, '&:last-child': { pb: { xs: 2, sm: 2.5 } } }}>
          <ReferralLinks refCode={refCode} botUsername={botUsername} primary="web" />
          <Typography variant="caption" color="text.disabled" sx={{ display: 'block', mt: 1 }}>
            Either link credits you — friends are tracked to the same referral code.
          </Typography>
        </CardContent>
      </Card>

      {/* Milestones */}
      <Typography variant="subtitle2" fontWeight={700} mb={1.5}>Your Progress</Typography>
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

      {/* Leaderboard */}
      {!loading && leaderboard && leaderboard.leaderboard?.length > 0 && (
        <Card sx={{ mb: 3, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
          <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <EmojiEvents sx={{ color: 'warning.main' }} />
              <Typography variant="subtitle2" fontWeight={700}>
                Top Referrers — {leaderboard.month || ''}
              </Typography>
            </Box>
            <Table size="small" sx={{ tableLayout: 'fixed', width: '100%' }}>
              <TableBody>
                {leaderboard.leaderboard.map((entry) => (
                  <TableRow
                    key={entry.rank}
                    sx={{ bgcolor: entry.is_current_user ? 'rgba(88,101,242,0.08)' : 'transparent' }}
                  >
                    <TableCell sx={{ width: 36, pr: 0, fontWeight: 700, color: entry.rank <= 3 ? 'warning.main' : 'text.secondary', fontSize: '0.8rem' }}>
                      {entry.rank <= 3 ? ['🥇', '🥈', '🥉'][entry.rank - 1] : `#${entry.rank}`}
                    </TableCell>
                    <TableCell sx={{ fontWeight: entry.is_current_user ? 700 : 400, fontSize: '0.85rem' }}>
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
          </CardContent>
        </Card>
      )}

      {/* How it works */}
      <Card sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
          <Typography variant="subtitle2" fontWeight={700} mb={2}>How it works</Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <StepBadge n="1" label="Copy your link" sub="Share the Website or Telegram link anywhere — Discord, Twitter, email." />
            <StepBadge n="2" label="Friend signs up" sub="They register using your unique referral link. Both links credit you." />
            <StepBadge n="3" label="You earn automatically" sub="Hit 3 referrals → 7 days Pro. Hit 10 → 1 month Pro. No action needed." />
          </Box>
        </CardContent>
      </Card>
    </Container>
  );
}
