import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Button, Card, CardContent, Chip, Skeleton,
  Divider, Alert, Avatar, Stack, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, CircularProgress,
} from '@mui/material';
import {
  SmartToy, Add, Settings, GroupAdd, Lock, Psychology,
  Delete, Groups, Assignment, Event, History,
} from '@mui/icons-material';
import { hub } from '../services/api';
import BotTokenConnectModal from '../components/shared/BotTokenConnectModal';
import { PALETTE } from '../theme';

/** Centralized feature gate — mirrors backend MAX_CUSTOM_BOTS config. */
export function canUseCustomBots(plan) {
  return plan === 'pro' || plan === 'enterprise';
}
export function customBotLimit(plan) {
  if (plan === 'enterprise') return 50;
  if (plan === 'pro') return 3;
  return 0;
}
export function customBotLimitLabel(plan) {
  if (plan === 'enterprise') return 'Unlimited';
  if (plan === 'pro') return '3 slots';
  return '0';
}

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
          background: `#18191c`,
          border: `1px solid ${PALETTE.border1}`,
        }}
      >
        <Box sx={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 2 }}>
          <Avatar
            sx={{
              width: 48, height: 48, flexShrink: 0,
              bgcolor: PALETTE.bg4, color: 'text.primary',
            }}
          >
            <Psychology fontSize="medium" />
          </Avatar>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.25 }}>
              <Typography variant="h5" fontWeight={600} letterSpacing="-0.02em">
                Echo — AI Assistant Layer
              </Typography>
              <Box className="ai-pulse-dot" />
            </Box>
            <Typography variant="body2" color="text.secondary">
              Works alongside Telegizer's moderation and automation. Extracts tasks, meetings,
              and reminders from your group conversations — so nothing important gets missed.
            </Typography>
          </Box>
        </Box>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── Official Bot Card ── */}
      <Box sx={{ mb: 3 }}>
        {loading ? <OfficialBotSkeleton /> : (
          <OfficialBotCard bot={officialBot} onManage={() => navigate('/ark/official/overview')} />
        )}
      </Box>

      <Divider sx={{ mb: 3, borderColor: PALETTE.border1 }} />


      {/* ── First-visit decision guide ── */}
      {!loading && !status?.official_bot && !(status?.custom_bots?.length) && (
        <DecisionGuideCard plan={plan} />
      )}

      {/* ── Custom Bots section ── */}
      <CustomBotsSection plan={plan} />
    </Box>
  );
}

function DecisionGuideCard({ plan }) {
  const navigate = useNavigate();
  const isPro = plan === 'pro' || plan === 'enterprise';
  return (
    <Card sx={{ mb: 3, border: '1px solid', borderColor: 'divider' }}>
      <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="subtitle1" fontWeight={600} mb={0.5}>Which bot type is right for you?</Typography>
        <Typography variant="body2" color="text.secondary" mb={3}>
          Telegizer gives you two ways to use Echo. Start instantly with the shared bot, or connect
          your own branded bot for full control.
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <Card variant="outlined" sx={{ flex: 1, p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <SmartToy color="primary" />
              <Typography variant="subtitle2" fontWeight={600}>Official bot</Typography>
              <Chip label="Free" size="small" color="success" />
            </Box>
            <Typography variant="body2" color="text.secondary" mb={2}>
              Instant setup — no BotFather required. Shared infrastructure managed by Telegizer.
            </Typography>
            {[
              '✅ Instant activation',
              '✅ Free on all plans',
              '✅ Managed & updated for you',
              '❌ Shared bot username',
            ].map(f => (
              <Typography key={f} variant="caption" display="block" color="text.secondary">{f}</Typography>
            ))}
            <Button
              variant="contained" size="small" fullWidth sx={{ mt: 2 }}
              onClick={() => navigate('/ark/workspace')}
            >
              Use official bot
            </Button>
          </Card>

          <Card variant="outlined" sx={{ flex: 1, p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Add color="secondary" />
              <Typography variant="subtitle2" fontWeight={600}>Custom bot</Typography>
              <Chip label="Pro" size="small" color="primary" />
            </Box>
            <Typography variant="body2" color="text.secondary" mb={2}>
              Your own bot token from BotFather. Full brand control with your custom username.
            </Typography>
            {[
              '✅ Your own bot username',
              '✅ Full branding control',
              '✅ Multiple bots',
              isPro ? '✅ Available on your plan' : '⚡ Requires Pro or Enterprise',
            ].map(f => (
              <Typography key={f} variant="caption" display="block" color="text.secondary">{f}</Typography>
            ))}
            <Button
              variant={isPro ? 'contained' : 'outlined'}
              color="secondary" size="small" fullWidth sx={{ mt: 2 }}
              onClick={() => navigate(isPro ? '/ark/custom-bot/new' : '/pricing')}
            >
              {isPro ? 'Add custom bot' : 'Upgrade to Pro'}
            </Button>
          </Card>
        </Stack>
      </CardContent>
    </Card>
  );
}


function OfficialBotCard({ bot, onManage }) {
  const navigate = useNavigate();
  if (!bot) return null;

  return (
    <Card
      sx={{
        borderColor: 'rgba(74,159,245,0.35)',
        borderWidth: 1.5,
        background: `#18191c`,
        boxShadow: `0 4px 28px rgba(0,0,0,0.4), 0 0 0 1px rgba(74,159,245,0.18)`,
        transition: 'box-shadow 0.2s ease',
        '&:hover': { boxShadow: `0 8px 36px rgba(0,0,0,0.5), 0 0 0 1px rgba(74,159,245,0.32)` },
      }}
    >
      <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Avatar
              sx={{
                width: 48, height: 48, borderRadius: 2, flexShrink: 0,
                background: `#27282d`,
                boxShadow: `0 0 16px ${PALETTE.glowBlue}`,
              }}
            >
              <SmartToy sx={{ color: '#fff', fontSize: 22 }} />
            </Avatar>
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Typography variant="subtitle1" fontWeight={600} letterSpacing="-0.01em">
                  {bot.display_name || 'Official Telegizer Assistant'}
                </Typography>
                <Chip
                  label="Active"
                  size="small"
                  sx={{
                    bgcolor: 'rgba(76,195,138,0.15)', color: '#4cc38a',
                    border: '1px solid rgba(76,195,138,0.35)',
                    height: 18, fontSize: '0.6875rem', fontWeight: 600,
                    boxShadow: 'none',
                  }}
                />
                <Chip
                  label="Shared"
                  size="small"
                  variant="outlined"
                  sx={{ height: 18, fontSize: '0.6875rem', borderColor: PALETTE.border2, color: 'text.secondary' }}
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
            mt: 2.5,
            display: 'grid',
            gridTemplateColumns: {
              xs: 'repeat(2, 1fr)',
              sm: bot.last_summary ? 'repeat(4, 1fr)' : 'repeat(3, 1fr)',
            },
            gap: 1,
          }}
        >
          <StatItem icon={<Groups sx={{ fontSize: 15 }} />} color={PALETTE.blue} label="Groups" value={bot.group_count ?? 0} />
          <StatItem icon={<Assignment sx={{ fontSize: 15 }} />} color={PALETTE.amber} label="Pending tasks" value={bot.pending_tasks ?? 0} />
          <StatItem
            icon={<Event sx={{ fontSize: 15 }} />}
            color={PALETTE.purple}
            label="Meetings today"
            value={bot.meetings_today ?? 0}
            sx={!bot.last_summary ? { gridColumn: { xs: '1 / -1', sm: 'auto' } } : undefined}
          />
          {bot.last_summary && (
            <StatItem icon={<History sx={{ fontSize: 15 }} />} color={PALETTE.cyan} label="Last summary" value={formatRelative(bot.last_summary)} />
          )}
        </Box>

        <Box sx={{ mt: 2.5, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={<GroupAdd />}
            onClick={() => navigate('/ark/official/settings')}
          >
            Add to group
          </Button>
          <Button
            variant="contained"
            size="small"
            startIcon={<Settings />}
            onClick={onManage}
          >
            Manage assistant
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}


function CustomBotsSection({ plan }) {
  const navigate = useNavigate();
  const hasAccess = canUseCustomBots(plan);
  const limit = customBotLimit(plan);
  const [botList, setBotList] = useState([]);
  const [botsLoading, setBotsLoading] = useState(false);
  const [botRegOpen, setBotRegOpen] = useState(false);
  const [botToDelete, setBotToDelete] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const loadBots = () => {
    if (!hasAccess) return;
    setBotsLoading(true);
    hub.listBots()
      .then(r => {
        const all = r.data?.bots || [];
        setBotList(all.filter(b => b.bot_type === 'custom'));
      })
      .catch(() => {})
      .finally(() => setBotsLoading(false));
  };

  useEffect(() => { loadBots(); }, [hasAccess]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDelete = async () => {
    if (!botToDelete || deleteConfirm !== botToDelete.display_name) return;
    setDeleteLoading(true); setDeleteError(null);
    try {
      await hub.deleteBot(botToDelete.id);
      setBotList(prev => prev.filter(b => b.id !== botToDelete.id));
      setBotToDelete(null); setDeleteConfirm('');
    } catch (e) {
      setDeleteError(e?.response?.data?.error || 'Failed to delete bot.');
    }
    setDeleteLoading(false);
  };

  const remaining = limit - botList.length;
  const slotsLabel = plan === 'enterprise' ? 'Unlimited' : `${remaining} slot${remaining !== 1 ? 's' : ''} free`;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="subtitle1" fontWeight={600} letterSpacing="-0.01em">Assistant bots</Typography>
          <Box className="ai-pulse-dot" sx={{ width: 5, height: 5 }} />
        </Box>
        {hasAccess && (
          <Typography variant="caption" color="text.secondary">{slotsLabel}</Typography>
        )}
      </Box>

      {!hasAccess ? (
        /* ── Free users: upsell ── */
        <Card sx={{ borderStyle: 'dashed', borderColor: PALETTE.border2, background: 'transparent',
          transition: 'border-color 0.2s, box-shadow 0.2s',
          '&:hover': { borderColor: `${PALETTE.purple}66`, boxShadow: `0 0 20px rgba(79,179,165,0.1)` } }}>
          <CardContent sx={{ textAlign: 'center', py: 5 }}>
            <Box sx={{ width: 52, height: 52, borderRadius: 2, mx: 'auto', mb: 1.5, background: 'rgba(79,179,165,0.08)', border: `1px solid rgba(79,179,165,0.2)`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Lock sx={{ fontSize: 22, color: PALETTE.purple + '99' }} />
            </Box>
            <Typography variant="body2" fontWeight={600} gutterBottom letterSpacing="-0.01em">
              Assistant Bots — Pro &amp; Enterprise
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" mb={2.5} sx={{ maxWidth: 360, mx: 'auto' }}>
              Connect your own @bot to observe specific groups with a custom identity.
              Available on Pro and Enterprise plans.
            </Typography>
            <Button variant="contained" size="small" color="secondary" href="/billing">Upgrade to Pro</Button>
          </CardContent>
        </Card>
      ) : botsLoading ? (
        <Card sx={{ borderStyle: 'dashed', borderColor: PALETTE.border2, background: 'transparent' }}>
          <CardContent sx={{ py: 3 }}>
            <Skeleton width="40%" height={20} sx={{ mb: 1, bgcolor: 'rgba(255,255,255,0.06)' }} />
            <Skeleton width="60%" height={16} sx={{ bgcolor: 'rgba(255,255,255,0.04)' }} />
          </CardContent>
        </Card>
      ) : botList.length === 0 ? (
        <Card sx={{ borderStyle: 'dashed', borderColor: PALETTE.border2, background: 'transparent',
          transition: 'border-color 0.2s, box-shadow 0.2s',
          '&:hover': { borderColor: `${PALETTE.blue}55`, boxShadow: `0 0 16px rgba(74,159,245,0.08)` } }}>
          <CardContent sx={{ textAlign: 'center', py: 5 }}>
            <Box sx={{ width: 52, height: 52, borderRadius: 2, mx: 'auto', mb: 1.5, background: 'rgba(74,159,245,0.08)', border: `1px solid rgba(74,159,245,0.2)`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <SmartToy sx={{ fontSize: 22, color: `${PALETTE.blue}99` }} />
            </Box>
            <Typography variant="body2" fontWeight={600} gutterBottom letterSpacing="-0.01em">No assistant bots yet</Typography>
            <Typography variant="caption" color="text.secondary" display="block" mb={2.5}>
              Connect a custom bot token to use it as an AI assistant in your groups.
            </Typography>
            <Button variant="contained" size="small" startIcon={<Add />} onClick={() => setBotRegOpen(true)}>Add bot</Button>
          </CardContent>
        </Card>
      ) : (
        /* ── Pro/Enterprise, bots exist — each card navigates to its own workspace ── */
        <Stack spacing={1.5}>
          {botList.map(bot => (
            <Card
              key={bot.id}
              sx={{
                border: `1px solid ${PALETTE.border1}`,
                transition: 'box-shadow 0.18s, border-color 0.18s',
                '&:hover': { boxShadow: `0 0 16px rgba(74,159,245,0.12)`, borderColor: `${PALETTE.blue}55` },
              }}
            >
              <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, py: '12px !important' }}>
                <Avatar sx={{ width: 36, height: 36, bgcolor: PALETTE.blue + '22', color: PALETTE.blue, flexShrink: 0 }}>
                  <SmartToy sx={{ fontSize: 18 }} />
                </Avatar>
                <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                  <Typography variant="body2" fontWeight={600} noWrap>
                    {bot.display_name || bot.telegram_bot_username || `Bot #${bot.id}`}
                  </Typography>
                  {bot.telegram_bot_username && (
                    <Typography variant="caption" color="text.secondary">
                      @{bot.telegram_bot_username} · {bot.group_count ?? 0} groups
                    </Typography>
                  )}
                </Box>
                <Chip label="Active" color="success" size="small"
                  sx={{ height: 20, fontSize: '0.6875rem', fontWeight: 600 }} />
                {/* Actions — Manage navigates to the bot's own workspace; Delete is inline */}
                <Button
                  size="small"
                  variant="contained"
                  sx={{ fontSize: '0.72rem', flexShrink: 0, ml: 0.5 }}
                  onClick={() => navigate(`/ark/bots/${bot.id}/overview`)}
                >
                  Manage
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  sx={{ fontSize: '0.72rem', flexShrink: 0, minWidth: 0, px: 1 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setBotToDelete(bot);
                    setDeleteConfirm('');
                    setDeleteError(null);
                  }}
                  title="Delete bot"
                >
                  <Delete sx={{ fontSize: 15 }} />
                </Button>
              </CardContent>
            </Card>
          ))}
          <Button variant="outlined" size="small" startIcon={<Add />}
            onClick={() => setBotRegOpen(true)} sx={{ alignSelf: 'flex-start' }}>
            Add another bot
          </Button>
        </Stack>
      )}

      <BotTokenConnectModal
        open={botRegOpen}
        mode="assistant_hub"
        plan={plan}
        onClose={() => setBotRegOpen(false)}
        onConnected={(bot) => {
          setBotList(prev => [...prev, bot]);
          setBotRegOpen(false);
        }}
      />

      {/* Delete confirmation dialog */}
      <Dialog open={Boolean(botToDelete)} onClose={() => setBotToDelete(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete {botToDelete?.display_name || 'this bot'}?</DialogTitle>
        <DialogContent>
          {deleteError && <Alert severity="error" sx={{ mb: 2 }}>{deleteError}</Alert>}
          <Typography variant="body2" color="text.secondary" mb={2}>
            This permanently removes the bot integration, stops the webhook, and disconnects all groups.
            This cannot be undone.
          </Typography>
          <TextField
            label={`Type "${botToDelete?.display_name || 'bot name'}" to confirm`}
            size="small" fullWidth
            value={deleteConfirm}
            onChange={e => setDeleteConfirm(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setBotToDelete(null)} size="small" color="inherit">Cancel</Button>
          <Button onClick={handleDelete} variant="contained" color="error" size="small"
            disabled={deleteConfirm !== (botToDelete?.display_name || '') || deleteLoading}>
            {deleteLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Delete Bot
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

function StatItem({ icon, color, label, value, sx }) {
  return (
    <Box
      sx={{
        minWidth: 0,
        px: 1.5, py: 1.5,
        textAlign: 'center',
        borderRadius: 2,
        bgcolor: 'rgba(255,255,255,0.03)',
        border: `1px solid ${PALETTE.border1}`,
        ...sx,
      }}
    >
      {icon && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 0.5, color }}>
          {icon}
        </Box>
      )}
      <Typography variant="h6" fontWeight={600} lineHeight={1.1} letterSpacing="-0.02em" noWrap>
        {value}
      </Typography>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ fontSize: '0.6875rem', display: 'block', mt: 0.25, whiteSpace: 'normal', lineHeight: 1.25 }}
      >
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

