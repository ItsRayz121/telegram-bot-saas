import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Container, Typography, Button, Card, CardContent,
  Chip, CircularProgress, Alert, Grid, Divider, Stack,
} from '@mui/material';
import { SmartToy, Groups, SwapHoriz, FileDownload, WorkspacePremium } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { customBots } from '../services/api';
import TopNav from '../components/TopNav';
import { lifecycleStatusLine, formatLifecycleDate, DISCOUNT_CODE_FALLBACK } from '../components/CustomBotLifecycleBanner';

function _getUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

const STATUS_LABEL = {
  active: 'Active',
  inactive: 'Inactive',
  error: 'Unreachable',
  paused: 'Paused',
};

const REASON_LABEL = {
  trial_expired: 'your Pro trial ended',
  subscription_expired: 'your Pro plan expired',
};

export default function CustomBotLifecycle() {
  const { botId } = useParams();
  const navigate = useNavigate();
  const user = _getUser();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [reactivating, setReactivating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const res = await customBots.getLifecycleStatus(botId);
      setData(res.data);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [botId]);

  useEffect(() => { load(); }, [load]);

  const bot = data?.bot;
  const discountCode = data?.discount_code || (bot?.pause_reason ? DISCOUNT_CODE_FALLBACK[bot.pause_reason] : null);
  const pricingUrl = data?.pricing_url || (discountCode ? `/pricing?promo=${discountCode}` : '/pricing');
  const isPro = user.subscription_tier === 'pro' || user.subscription_tier === 'enterprise';

  const handleReactivate = async () => {
    if (!bot) return;
    // Still mid-grace (not paused yet) — "reactivate" isn't valid yet, the only
    // useful action is upgrading now, so send them there instead of no-oping.
    if (bot.status !== 'paused') {
      navigate(pricingUrl);
      return;
    }
    if (!isPro) {
      navigate(pricingUrl);
      return;
    }
    setReactivating(true);
    try {
      const res = await customBots.reactivate(bot.id);
      toast.success(res.data.message || 'Bot reactivated!');
      load();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Could not reactivate bot');
    } finally {
      setReactivating(false);
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <TopNav hasSidebar
        breadcrumb={[
          { label: 'Dashboard', path: '/dashboard' },
          { label: 'My Bots', path: '/custom-bots' },
          { label: 'Bot status' },
        ]}
      />

      <Container maxWidth="sm" sx={{ py: 4 }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : loadError || !bot ? (
          <Card sx={{ textAlign: 'center', py: 6 }}>
            <Typography variant="h6" gutterBottom>Couldn't load this bot</Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              It may have already been removed, or belongs to a different account.
            </Typography>
            <Button variant="contained" onClick={() => navigate('/custom-bots')}>Back to My Bots</Button>
          </Card>
        ) : (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
              <SmartToy sx={{ fontSize: 40, color: 'text.secondary' }} />
              <Box>
                <Typography variant="h5" fontWeight={700}>
                  {bot.bot_name || `@${bot.bot_username}`}
                </Typography>
                <Typography variant="body2" color="text.secondary">@{bot.bot_username}</Typography>
              </Box>
              <Chip
                label={STATUS_LABEL[bot.status] || 'Active'}
                color={bot.status === 'paused' ? 'warning' : bot.status === 'error' ? 'error' : 'success'}
                size="small"
                sx={{ ml: 'auto' }}
              />
            </Box>

            {bot.pause_reason ? (
              <>
                <Alert severity={bot.status === 'paused' ? 'error' : 'warning'} sx={{ mb: 3 }}>
                  <Typography variant="body2" fontWeight={600}>{lifecycleStatusLine(bot)}</Typography>
                </Alert>

                <Typography variant="body2" color="text.secondary" mb={3}>
                  {REASON_LABEL[bot.pause_reason] || 'Your plan changed'}, so this custom bot
                  {bot.status === 'paused'
                    ? ' has stopped responding in its groups.'
                    : ' is on a grace period before it pauses.'}
                  {' '}
                  {bot.status === 'paused'
                    ? `If you don't reactivate before ${formatLifecycleDate(bot.retention_deadline_at) || 'the deadline'}, the bot and its settings are permanently deleted — deleted rows and disconnected groups do not come back.`
                    : 'Once it pauses, its groups stop receiving moderation, automod, and scheduled messages until you reactivate.'}
                </Typography>

                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid item xs={6}>
                    <Card variant="outlined">
                      <CardContent sx={{ textAlign: 'center', py: 2 }}>
                        <Typography variant="h5" fontWeight={700}>{data.group_count ?? 0}</Typography>
                        <Typography variant="caption" color="text.secondary">Groups affected</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={6}>
                    <Card variant="outlined">
                      <CardContent sx={{ textAlign: 'center', py: 2 }}>
                        <Typography variant="h5" fontWeight={700}>{data.member_count ?? 0}</Typography>
                        <Typography variant="caption" color="text.secondary">Members affected</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>

                <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1.5 }}>
                  Your options
                </Typography>

                <Card variant="outlined" sx={{ mt: 1, mb: 1.5 }}>
                  <CardContent sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
                    <SwapHoriz color="primary" />
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" fontWeight={600}>Switch to the official bot (free)</Typography>
                      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                        @telegizer_bot is always free and unlimited. A group admin runs <code>/linkgroup</code>
                        {' '}inside each Telegram group to get a code, then pastes it on the Link Group screen —
                        Telegram doesn't allow us to add a bot to your group automatically.
                      </Typography>
                      <Button size="small" variant="outlined" startIcon={<Groups />} onClick={() => navigate('/groups')}>
                        Open group linking
                      </Button>
                    </Box>
                  </CardContent>
                </Card>

                <Card variant="outlined" sx={{ mb: 1.5 }}>
                  <CardContent sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
                    <FileDownload color="primary" />
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" fontWeight={600}>Export your settings</Typography>
                      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                        Download a portable JSON backup of each group's automod, AI, and community settings
                        from Settings → Import &amp; Export on that group's page, before the retention window ends.
                      </Typography>
                      <Button size="small" variant="outlined" startIcon={<Groups />} onClick={() => navigate(`/groups?bot_id=${bot.id}`)}>
                        Open bot's groups
                      </Button>
                    </Box>
                  </CardContent>
                </Card>

                <Card variant="outlined" sx={{ mb: 3, borderColor: 'warning.main' }}>
                  <CardContent sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
                    <WorkspacePremium color="warning" />
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" fontWeight={600}>
                        Reactivate{discountCode ? ` — ${discountCode} (20% off)` : ', 20% off'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                        {isPro
                          ? 'Your account is already on Pro/Enterprise — reactivate this bot now.'
                          : `Upgrade to Pro or Enterprise with code ${discountCode || ''} to bring this bot back online, then come back here to reactivate.`}
                      </Typography>
                      <Button
                        size="small"
                        variant="contained"
                        color="warning"
                        disabled={reactivating}
                        onClick={handleReactivate}
                      >
                        {reactivating
                          ? <CircularProgress size={16} sx={{ color: 'inherit' }} />
                          : isPro ? 'Reactivate Bot' : 'Upgrade & Reactivate'}
                      </Button>
                      {!isPro && (
                        <Typography variant="caption" color="text.disabled" display="block" mt={0.75}>
                          You'll upgrade first, then this bot resumes — no separate reactivation charge.
                        </Typography>
                      )}
                    </Box>
                  </CardContent>
                </Card>
              </>
            ) : (
              <Alert severity="success" sx={{ mb: 3 }}>
                This bot is active and not part of any pause/retention lifecycle.
              </Alert>
            )}

            <Divider sx={{ my: 2 }} />
            <Stack direction="row" justifyContent="center">
              <Button onClick={() => navigate('/custom-bots')}>Back to My Bots</Button>
            </Stack>
          </>
        )}
      </Container>
    </Box>
  );
}
