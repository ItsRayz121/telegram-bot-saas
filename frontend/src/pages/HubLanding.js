/**
 * /hub — Assistant Hub landing page.
 *
 * Shows the Official Telegizer Assistant card and a Custom Bots section
 * (plan-gated; custom bots are V1.5+).
 *
 * Mirrors the existing Groups page card-grid layout exactly.
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Button, Card, CardContent, Chip, Skeleton,
  Grid, Divider, Alert,
} from '@mui/material';
import {
  SmartToy, Add, Settings, GroupAdd, AutoMode, Lock,
} from '@mui/icons-material';
import hub from '../services/hubApi';

export default function HubLanding() {
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    hub.getStatus()
      .then(r => setStatus(r.data))
      .catch(e => setError(e?.response?.data?.message || 'Failed to load Hub'))
      .finally(() => setLoading(false));
  }, []);

  const officialBot = status?.official_bot;
  const plan = status?.plan || 'free';

  return (
    <Box sx={{ p: { xs: 2, sm: 3 }, maxWidth: 900, mx: 'auto' }}>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" fontWeight={700}>AI Assistant Hub</Typography>
        <Typography variant="body2" color="text.secondary" mt={0.5}>
          Quietly observes your groups. Surfaces what matters.
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
      )}

      {/* Official Bot Card */}
      <Box sx={{ mb: 3 }}>
        {loading ? (
          <OfficialBotSkeleton />
        ) : (
          <OfficialBotCard bot={officialBot} onManage={() => navigate('/hub/official/overview')} />
        )}
      </Box>

      <Divider sx={{ mb: 3 }} />

      {/* Custom Bots section — V1.5+ */}
      <CustomBotsSection plan={plan} />
    </Box>
  );
}


function OfficialBotCard({ bot, onManage }) {
  const navigate = useNavigate();

  if (!bot) return null;

  return (
    <Card variant="outlined" sx={{ borderColor: 'primary.main', borderWidth: 1.5 }}>
      <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Box
              sx={{
                width: 44, height: 44, borderRadius: 2,
                bgcolor: 'primary.main', display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <SmartToy sx={{ color: '#fff', fontSize: 22 }} />
            </Box>
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Typography variant="subtitle1" fontWeight={700}>
                  {bot.display_name || 'Official Telegizer Assistant'}
                </Typography>
                <Chip
                  label="Active"
                  size="small"
                  sx={{ bgcolor: 'success.main', color: '#fff', height: 18, fontSize: '0.65rem' }}
                />
                <Chip
                  label="Shared"
                  size="small"
                  variant="outlined"
                  sx={{ height: 18, fontSize: '0.65rem', borderColor: 'divider', color: 'text.secondary' }}
                />
              </Box>
              <Typography variant="caption" color="text.secondary">
                @{bot.telegram_bot_username || 'telegizer_bot'} · Always Active
              </Typography>
            </Box>
          </Box>
        </Box>

        <Box sx={{ mt: 2, display: 'flex', gap: 3, flexWrap: 'wrap' }}>
          <StatItem label="Groups connected" value={bot.group_count ?? 0} />
          <StatItem label="Pending tasks" value={bot.pending_tasks ?? 0} />
          <StatItem label="Meetings today" value={bot.meetings_today ?? 0} />
          {bot.last_summary && (
            <StatItem label="Last summary" value={formatRelative(bot.last_summary)} />
          )}
        </Box>

        <Box sx={{ mt: 2.5, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={<GroupAdd />}
            onClick={() => navigate('/hub/official/settings')}
          >
            + Add to Group
          </Button>
          <Button
            variant="contained"
            size="small"
            startIcon={<Settings />}
            onClick={onManage}
          >
            Manage Assistant
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}


function CustomBotsSection({ plan }) {
  const isFree = plan === 'free';

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="subtitle1" fontWeight={600}>Custom Bots</Typography>
        {!isFree && (
          <Typography variant="caption" color="text.secondary">
            {plan === 'pro' ? '2 slots' : 'Unlimited'}
          </Typography>
        )}
      </Box>

      {isFree ? (
        <Card variant="outlined" sx={{ borderStyle: 'dashed', borderColor: 'divider', bgcolor: 'transparent' }}>
          <CardContent sx={{ textAlign: 'center', py: 4 }}>
            <Lock sx={{ fontSize: 32, color: 'text.disabled', mb: 1 }} />
            <Typography variant="body2" fontWeight={600} gutterBottom>
              Custom Bots — Pro &amp; Enterprise
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" mb={2}>
              Connect your own @bot to observe specific groups with a custom identity.
              Available in V1.5 on Pro and Enterprise plans.
            </Typography>
            <Button variant="outlined" size="small" href="/billing">
              Upgrade to Pro
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card variant="outlined" sx={{ borderStyle: 'dashed', borderColor: 'divider', bgcolor: 'transparent' }}>
          <CardContent sx={{ textAlign: 'center', py: 4 }}>
            <AutoMode sx={{ fontSize: 32, color: 'text.disabled', mb: 1 }} />
            <Typography variant="body2" fontWeight={600} gutterBottom>
              Custom Bots — Coming in V1.5
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" mb={2}>
              Connect your own bots from the Custom Bots section to Assistant Hub.
            </Typography>
            <Button variant="outlined" size="small" disabled startIcon={<Add />}>
              Add Bot
            </Button>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}


function StatItem({ label, value }) {
  return (
    <Box>
      <Typography variant="h6" fontWeight={700} lineHeight={1}>{value}</Typography>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
    </Box>
  );
}


function OfficialBotSkeleton() {
  return (
    <Card variant="outlined">
      <CardContent sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', gap: 1.5, mb: 2 }}>
          <Skeleton variant="rounded" width={44} height={44} />
          <Box sx={{ flex: 1 }}>
            <Skeleton width="50%" height={22} />
            <Skeleton width="35%" height={16} sx={{ mt: 0.5 }} />
          </Box>
        </Box>
        <Box sx={{ display: 'flex', gap: 3 }}>
          <Skeleton width={80} height={40} />
          <Skeleton width={80} height={40} />
          <Skeleton width={80} height={40} />
        </Box>
        <Box sx={{ display: 'flex', gap: 1, mt: 2.5 }}>
          <Skeleton variant="rounded" width={130} height={32} />
          <Skeleton variant="rounded" width={150} height={32} />
        </Box>
      </CardContent>
    </Card>
  );
}


function formatRelative(isoString) {
  if (!isoString) return '—';
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
