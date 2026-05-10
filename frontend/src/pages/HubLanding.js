import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Button, Card, CardContent, Chip, Skeleton,
  Divider, Alert, Avatar, Stack, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, CircularProgress,
} from '@mui/material';
import {
  SmartToy, Add, Settings, GroupAdd, Lock, Psychology,
  Delete,
} from '@mui/icons-material';
import { hub } from '../services/api';
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
          <Typography variant="subtitle1" fontWeight={700} letterSpacing="-0.01em">Assistant Bots</Typography>
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
          '&:hover': { borderColor: `${PALETTE.purple}66`, boxShadow: `0 0 20px rgba(157,108,247,0.1)` } }}>
          <CardContent sx={{ textAlign: 'center', py: 5 }}>
            <Box sx={{ width: 52, height: 52, borderRadius: 2, mx: 'auto', mb: 1.5, background: 'rgba(157,108,247,0.08)', border: `1px solid rgba(157,108,247,0.2)`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Lock sx={{ fontSize: 22, color: PALETTE.purple + '99' }} />
            </Box>
            <Typography variant="body2" fontWeight={700} gutterBottom letterSpacing="-0.01em">
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
          '&:hover': { borderColor: `${PALETTE.blue}55`, boxShadow: `0 0 16px rgba(61,142,248,0.08)` } }}>
          <CardContent sx={{ textAlign: 'center', py: 5 }}>
            <Box sx={{ width: 52, height: 52, borderRadius: 2, mx: 'auto', mb: 1.5, background: 'rgba(61,142,248,0.08)', border: `1px solid rgba(61,142,248,0.2)`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <SmartToy sx={{ fontSize: 22, color: `${PALETTE.blue}99` }} />
            </Box>
            <Typography variant="body2" fontWeight={700} gutterBottom letterSpacing="-0.01em">No assistant bots yet</Typography>
            <Typography variant="caption" color="text.secondary" display="block" mb={2.5}>
              Connect a custom bot token to use it as an AI assistant in your groups.
            </Typography>
            <Button variant="contained" size="small" startIcon={<Add />} onClick={() => setBotRegOpen(true)}>Add Bot</Button>
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
                '&:hover': { boxShadow: `0 0 16px rgba(61,142,248,0.12)`, borderColor: `${PALETTE.blue}55` },
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
                  sx={{ height: 20, fontSize: '0.68rem', fontWeight: 600 }} />
                {/* Actions — Manage navigates to the bot's own workspace; Delete is inline */}
                <Button
                  size="small"
                  variant="contained"
                  sx={{ fontSize: '0.72rem', flexShrink: 0, ml: 0.5 }}
                  onClick={() => navigate(`/hub/bots/${bot.id}/overview`)}
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
            Add Another Bot
          </Button>
        </Stack>
      )}

      <BotRegistrationDialog
        open={botRegOpen}
        plan={plan}
        onClose={() => setBotRegOpen(false)}
        onRegistered={(bot) => {
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

function BotRegistrationDialog({ open, onClose, onRegistered, plan }) {
  const [displayName, setDisplayName] = useState('');
  const [token, setToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) { setDisplayName(''); setToken(''); setError(null); }
  }, [open]);

  const handleCreate = async () => {
    if (!displayName.trim()) { setError('Display name is required'); return; }
    if (!token.trim()) { setError('Bot token is required'); return; }
    setSaving(true);
    setError(null);
    try {
      const res = await hub.createBot({ display_name: displayName, telegram_bot_token: token });
      onRegistered(res.data.bot);
    } catch (e) {
      const err = e.response?.data?.error;
      if (err === 'plan_limit') setError('Custom bot limit reached. Upgrade your plan.');
      else if (err === 'invalid_token') setError('Invalid bot token. Check it in @BotFather.');
      else if (err === 'already_registered') setError('This bot is already registered.');
      else setError('Registration failed. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Connect Assistant Bot</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '12px !important' }}>
        {plan === 'free' && (
          <Alert severity="warning">Assistant bots require a Pro or Enterprise plan.</Alert>
        )}
        {error && <Alert severity="error">{error}</Alert>}
        <TextField label="Display Name" value={displayName} onChange={e => setDisplayName(e.target.value)}
          size="small" disabled={plan === 'free'} helperText="How it appears in your Hub" />
        <TextField label="Bot Token" value={token} onChange={e => setToken(e.target.value)}
          size="small" disabled={plan === 'free'}
          helperText="Get this from @BotFather → /mybots → API Token"
          type="password" />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleCreate} variant="contained" disabled={saving || plan === 'free'}>
          {saving ? <CircularProgress size={16} /> : 'Connect Bot'}
        </Button>
      </DialogActions>
    </Dialog>
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
