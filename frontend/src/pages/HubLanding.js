import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Button, Card, CardContent, Chip, Skeleton,
  Divider, Alert, Avatar,
} from '@mui/material';
import {
  SmartToy, Add, Settings, GroupAdd, AutoMode, Lock, Psychology,
} from '@mui/icons-material';
import hub from '../services/hubApi';
import { PALETTE } from '../theme';

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
    <Box sx={{ p: { xs: 2, sm: 3 }, maxWidth: 920, mx: 'auto' }}>

      {/* ── Hero header ── */}
      <Box
        sx={{
          mb: 4, p: { xs: 2.5, sm: 3.5 }, borderRadius: 3, position: 'relative', overflow: 'hidden',
          background: `linear-gradient(135deg, rgba(157,108,247,0.12) 0%, rgba(61,142,248,0.08) 50%, transparent 100%)`,
          border: `1px solid rgba(157,108,247,0.2)`,
          boxShadow: '0 4px 24px rgba(0,0,0,0.35)',
        }}
      >
        {/* Ambient glow orb */}
        <Box sx={{
          position: 'absolute', top: -40, right: -40, width: 200, height: 200,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(157,108,247,0.18) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />
        <Box sx={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 2 }}>
          <Avatar
            sx={{
              width: 48, height: 48, flexShrink: 0,
              background: `linear-gradient(135deg, ${PALETTE.purple}, ${PALETTE.blue})`,
              boxShadow: `0 0 20px ${PALETTE.glowPurple}`,
            }}
          >
            <Psychology fontSize="medium" />
          </Avatar>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.25 }}>
              <Typography variant="h5" fontWeight={800} letterSpacing="-0.02em">
                AI Assistant Hub
              </Typography>
              <Box className="ai-pulse-dot" />
            </Box>
            <Typography variant="body2" color="text.secondary">
              Quietly observes your groups. Surfaces what matters.
            </Typography>
          </Box>
        </Box>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── Official Bot Card ── */}
      <Box sx={{ mb: 3 }}>
        {loading ? <OfficialBotSkeleton /> : (
          <OfficialBotCard bot={officialBot} onManage={() => navigate('/hub/official/overview')} />
        )}
      </Box>

      <Divider sx={{ mb: 3, borderColor: PALETTE.border1 }} />

      {/* ── Custom Bots section ── */}
      <CustomBotsSection plan={plan} />
    </Box>
  );
}


function OfficialBotCard({ bot, onManage }) {
  const navigate = useNavigate();
  if (!bot) return null;

  return (
    <Card
      sx={{
        borderColor: 'rgba(61,142,248,0.35)',
        borderWidth: 1.5,
        background: `linear-gradient(135deg, rgba(61,142,248,0.07) 0%, rgba(15,29,53,0.9) 100%)`,
        boxShadow: `0 4px 28px rgba(0,0,0,0.4), 0 0 0 1px rgba(61,142,248,0.18)`,
        transition: 'box-shadow 0.2s ease',
        '&:hover': { boxShadow: `0 8px 36px rgba(0,0,0,0.5), 0 0 0 1px rgba(61,142,248,0.32)` },
      }}
    >
      <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Avatar
              sx={{
                width: 48, height: 48, borderRadius: 2, flexShrink: 0,
                background: `linear-gradient(135deg, ${PALETTE.blue}, ${PALETTE.cyan})`,
                boxShadow: `0 0 16px ${PALETTE.glowBlue}`,
              }}
            >
              <SmartToy sx={{ color: '#fff', fontSize: 22 }} />
            </Avatar>
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Typography variant="subtitle1" fontWeight={700} letterSpacing="-0.01em">
                  {bot.display_name || 'Official Telegizer Assistant'}
                </Typography>
                <Chip
                  label="Active"
                  size="small"
                  sx={{
                    bgcolor: 'rgba(34,197,94,0.15)', color: '#22c55e',
                    border: '1px solid rgba(34,197,94,0.35)',
                    height: 18, fontSize: '0.65rem', fontWeight: 600,
                    boxShadow: '0 0 8px rgba(34,197,94,0.25)',
                  }}
                />
                <Chip
                  label="Shared"
                  size="small"
                  variant="outlined"
                  sx={{ height: 18, fontSize: '0.65rem', borderColor: PALETTE.border2, color: 'text.secondary' }}
                />
              </Box>
              <Typography variant="caption" color="text.secondary">
                @{bot.telegram_bot_username || 'telegizer_bot'} · Always Active
              </Typography>
            </Box>
          </Box>
        </Box>

        {/* Stats row */}
        <Box
          sx={{
            mt: 2.5, display: 'flex', gap: 0,
            bgcolor: 'rgba(0,0,0,0.2)', borderRadius: 2,
            border: `1px solid ${PALETTE.border1}`,
            overflow: 'hidden',
          }}
        >
          <StatItem label="Groups" value={bot.group_count ?? 0} />
          <Divider orientation="vertical" flexItem sx={{ borderColor: PALETTE.border1 }} />
          <StatItem label="Pending tasks" value={bot.pending_tasks ?? 0} />
          <Divider orientation="vertical" flexItem sx={{ borderColor: PALETTE.border1 }} />
          <StatItem label="Meetings today" value={bot.meetings_today ?? 0} />
          {bot.last_summary && (
            <>
              <Divider orientation="vertical" flexItem sx={{ borderColor: PALETTE.border1 }} />
              <StatItem label="Last summary" value={formatRelative(bot.last_summary)} />
            </>
          )}
        </Box>

        <Box sx={{ mt: 2.5, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={<GroupAdd />}
            onClick={() => navigate('/hub/official/settings')}
          >
            Add to Group
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
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="subtitle1" fontWeight={700} letterSpacing="-0.01em">Custom Bots</Typography>
          <Box className="ai-pulse-dot" sx={{ width: 5, height: 5 }} />
        </Box>
        {!isFree && (
          <Typography variant="caption" color="text.secondary">
            {plan === 'pro' ? '2 slots' : 'Unlimited'}
          </Typography>
        )}
      </Box>

      {isFree ? (
        <Card
          sx={{
            borderStyle: 'dashed', borderColor: PALETTE.border2,
            background: 'transparent',
            transition: 'border-color 0.2s, box-shadow 0.2s',
            '&:hover': { borderColor: `${PALETTE.purple}66`, boxShadow: `0 0 20px rgba(157,108,247,0.1)` },
          }}
        >
          <CardContent sx={{ textAlign: 'center', py: 5 }}>
            <Box
              sx={{
                width: 52, height: 52, borderRadius: 2, mx: 'auto', mb: 1.5,
                background: 'rgba(157,108,247,0.08)',
                border: `1px solid rgba(157,108,247,0.2)`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <Lock sx={{ fontSize: 22, color: PALETTE.purple + '99' }} />
            </Box>
            <Typography variant="body2" fontWeight={700} gutterBottom letterSpacing="-0.01em">
              Custom Bots — Pro &amp; Enterprise
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" mb={2.5} sx={{ maxWidth: 360, mx: 'auto' }}>
              Connect your own @bot to observe specific groups with a custom identity.
              Available on Pro and Enterprise plans.
            </Typography>
            <Button variant="contained" size="small" color="secondary" href="/billing">
              Upgrade to Pro
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card
          sx={{
            borderStyle: 'dashed', borderColor: PALETTE.border2,
            background: 'transparent',
          }}
        >
          <CardContent sx={{ textAlign: 'center', py: 5 }}>
            <Box
              sx={{
                width: 52, height: 52, borderRadius: 2, mx: 'auto', mb: 1.5,
                background: 'rgba(61,142,248,0.08)',
                border: `1px solid rgba(61,142,248,0.2)`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <AutoMode sx={{ fontSize: 22, color: `${PALETTE.blue}99` }} />
            </Box>
            <Typography variant="body2" fontWeight={700} gutterBottom letterSpacing="-0.01em">
              Custom Bots — Coming Soon
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" mb={2.5}>
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
    <Box sx={{ flex: 1, px: 2, py: 1.5, textAlign: 'center' }}>
      <Typography variant="h6" fontWeight={800} lineHeight={1} letterSpacing="-0.02em">
        {value}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.68rem' }}>
        {label}
      </Typography>
    </Box>
  );
}


function OfficialBotSkeleton() {
  return (
    <Card>
      <CardContent sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', gap: 1.5, mb: 2 }}>
          <Skeleton variant="rounded" width={48} height={48} sx={{ borderRadius: 2, bgcolor: 'rgba(255,255,255,0.06)' }} />
          <Box sx={{ flex: 1 }}>
            <Skeleton width="50%" height={22} sx={{ bgcolor: 'rgba(255,255,255,0.06)' }} />
            <Skeleton width="35%" height={16} sx={{ mt: 0.5, bgcolor: 'rgba(255,255,255,0.04)' }} />
          </Box>
        </Box>
        <Box sx={{ display: 'flex', gap: 3 }}>
          <Skeleton width={80} height={40} sx={{ bgcolor: 'rgba(255,255,255,0.05)' }} />
          <Skeleton width={80} height={40} sx={{ bgcolor: 'rgba(255,255,255,0.05)' }} />
          <Skeleton width={80} height={40} sx={{ bgcolor: 'rgba(255,255,255,0.05)' }} />
        </Box>
        <Box sx={{ display: 'flex', gap: 1, mt: 2.5 }}>
          <Skeleton variant="rounded" width={130} height={32} sx={{ bgcolor: 'rgba(255,255,255,0.05)' }} />
          <Skeleton variant="rounded" width={150} height={32} sx={{ bgcolor: 'rgba(255,255,255,0.05)' }} />
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
