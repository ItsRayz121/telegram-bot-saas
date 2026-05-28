import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Container, Typography, Button, Card, CardContent,
  Chip, CircularProgress, Alert, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, IconButton,
  Tooltip, Grid, Divider, Stack, LinearProgress,
} from '@mui/material';
import {
  Add, SmartToy, Delete, Refresh, OpenInNew, Groups,
  BarChart, Psychology, Lock,
} from '@mui/icons-material';
import { track } from '../services/analytics';
import { toast } from 'react-toastify';
import { customBots, telegramGroups as telegramGroupsApi } from '../services/api';
import TopNav from '../components/TopNav';
import PlanGate from '../components/PlanGate';
import UpsellModal from '../components/UpsellModal';

function _getUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

const BOT_USERNAME = process.env.REACT_APP_BOT_USERNAME || 'telegizer_bot';

function _relativeTime(iso) {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function StatusChip({ status }) {
  const map = {
    active:      { label: 'Active',      color: 'success' },
    idle:        { label: 'Idle',        color: 'default' },
    offline:     { label: 'Offline',     color: 'default' },
    unreachable: { label: 'Unreachable', color: 'error'   },
    // legacy — map gracefully so old API responses never break
    inactive:   { label: 'Offline',  color: 'default' },
    stopped:    { label: 'Offline',  color: 'default' },
    unknown:    { label: 'Active',   color: 'success' },
    recovering: { label: 'Active',   color: 'success' },
    starting:   { label: 'Active',   color: 'success' },
    warning:    { label: 'Active',   color: 'success' },
    error:      { label: 'Unreachable', color: 'error' },
  };
  const { label, color } = map[status] || { label: 'Active', color: 'success' };
  return <Chip label={label} color={color} size="small" />;
}

export default function MyBots() {
  const navigate = useNavigate();
  const [bots, setBots] = useState([]);
  const [officialGroups, setOfficialGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ bot_token: '' });
  const [validating, setValidating] = useState(false);
  const [preview, setPreview] = useState(null); // bot info from Telegram after validate
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [upsellOpen, setUpsellOpen] = useState(false);
  const [upsellMessage, setUpsellMessage] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [botsRes, groupsRes] = await Promise.all([
        customBots.list(),
        telegramGroupsApi.list(),
      ]);
      setBots(botsRes.data.bots || []);
      setOfficialGroups((groupsRes.data.groups || []).filter(
        (g) => (g.linked_via_bot_type === 'official' || !g.linked_via_bot_type) && !g.linked_bot_id
      ));
    } catch {
      toast.error('Failed to load bots');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleValidate = async () => {
    if (!form.bot_token) return;
    setValidating(true);
    setAddError('');
    setPreview(null);
    try {
      const res = await customBots.validateToken(form.bot_token);
      setPreview(res.data);
    } catch (err) {
      // Never clear the token field on error — user should be able to correct it
      setAddError(err.response?.data?.error || 'Could not verify token. Check your connection and try again.');
    } finally {
      setValidating(false);
    }
  };

  const handleAdd = async () => {
    if (!preview) return;
    setAdding(true);
    setAddError('');
    try {
      await customBots.add({ bot_token: form.bot_token, bot_username: preview.bot_username });
      track('feature_used', { feature: 'custom_bot' });
      toast.success(`@${preview.bot_username} connected!`);
      setAddOpen(false);
      setForm({ bot_token: '' });
      setPreview(null);
      load();
    } catch (err) {
      const errMsg = err.response?.data?.error || 'Failed to connect bot';
      if (errMsg.toLowerCase().includes('bot limit')) {
        setUpsellMessage(errMsg);
        setUpsellOpen(true);
        setAddOpen(false);
      } else {
        setAddError(errMsg);
      }
    } finally {
      setAdding(false);
    }
  };

  const handleCloseAddDialog = () => {
    setAddOpen(false);
    setPreview(null);
    setAddError('');
    // Do NOT clear bot_token so user can re-open and try again
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await customBots.delete(deleteTarget.id);
      toast.success(`@${deleteTarget.bot_username} disconnected`);
      setDeleteTarget(null);
      load();
    } catch {
      toast.error('Failed to disconnect bot');
    }
  };

  const user = _getUser();

  return (
    <PlanGate plan="pro" userTier={user.subscription_tier} feature="Custom Bots">
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <TopNav hasSidebar
        breadcrumb={[
          { label: 'Dashboard', path: '/dashboard' },
          { label: 'My Bots' },
        ]}
        actions={
          <Button variant="contained" startIcon={<Add />} size="small" onClick={() => setAddOpen(true)}>
            Connect Bot
          </Button>
        }
      />

      <Container maxWidth="lg" sx={{ py: 4 }}>
        {/* Page header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
          <Box>
            <Typography variant="h4" fontWeight={700}>My Bots</Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              Official shared bot + any custom bots you connect
            </Typography>
          </Box>
          <IconButton onClick={load} disabled={loading}><Refresh /></IconButton>
        </Box>

        {/* ── Official Telegizer Bot ─────────────────────────────────────────── */}
        <Typography variant="overline" color="text.secondary" sx={{ mb: 1, display: 'block', letterSpacing: 1.5 }}>
          Official Telegizer Bot
        </Typography>
        <Card sx={{ mb: 4, border: '1px solid', borderColor: 'success.dark', background: 'rgba(34,197,94,0.05)' }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
              <SmartToy sx={{ fontSize: 40, color: 'success.main', mt: 0.5 }} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.5 }}>
                  <Typography variant="h6" fontWeight={700}>@{BOT_USERNAME}</Typography>
                  <Chip label="Always Active" color="success" size="small" />
                  <Chip label="Shared" variant="outlined" size="small" />
                </Box>
                <Typography variant="body2" color="text.secondary" mb={2}>
                  One shared bot serving all your linked groups. Automod, verification, custom commands — all managed from your dashboard.
                </Typography>

                {/* Stats row */}
                <Grid container spacing={2} sx={{ mb: 2 }}>
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ textAlign: 'center', p: 1.5, bgcolor: 'background.default', borderRadius: 2 }}>
                      <Typography variant="h5" fontWeight={700} color="success.main">
                        {loading ? '…' : officialGroups.length}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">Groups Linked</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ textAlign: 'center', p: 1.5, bgcolor: 'background.default', borderRadius: 2 }}>
                      <Typography variant="h5" fontWeight={700} color="primary.main">
                        {loading ? '…' : officialGroups.filter((g) => g.bot_status === 'active').length}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">Active Groups</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ textAlign: 'center', p: 1.5, bgcolor: 'background.default', borderRadius: 2 }}>
                      <Typography variant="h5" fontWeight={700} color="info.main">
                        {loading ? '…' : officialGroups.filter((g) => {
                          const p = g.bot_permissions || {};
                          return Object.keys(p).length > 0 && Object.values(p).every(Boolean);
                        }).length}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">Full Permissions</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ textAlign: 'center', p: 1.5, bgcolor: 'background.default', borderRadius: 2 }}>
                      <Typography variant="h5" fontWeight={700} color="warning.main">
                        {loading ? '…' : officialGroups.filter((g) => {
                          const p = g.bot_permissions || {};
                          return Object.keys(p).length > 0 && !Object.values(p).every(Boolean);
                        }).length}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">Need Permissions</Typography>
                    </Box>
                  </Grid>
                </Grid>

                {/* Action buttons */}
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Button
                    variant="contained"
                    size="small"
                    startIcon={<Groups />}
                    onClick={() => navigate('/groups?bot_type=official')}
                  >
                    Manage Groups
                  </Button>
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={<BarChart />}
                    onClick={() => navigate('/official-analytics')}
                  >
                    Analytics
                  </Button>
                  <Button
                    variant="outlined"
                    size="small"
                    endIcon={<OpenInNew />}
                    href={`https://t.me/${BOT_USERNAME}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open Bot
                  </Button>
                </Stack>
              </Box>
            </Box>

            {/* Linked groups preview */}
            {!loading && officialGroups.length > 0 && (
              <>
                <Divider sx={{ my: 2 }} />
                <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1}>
                  LINKED GROUPS
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  {officialGroups.slice(0, 6).map((g) => (
                    <Chip
                      key={g.telegram_group_id}
                      label={g.title}
                      size="small"
                      color={g.bot_status === 'active' ? 'success' : 'default'}
                      variant="outlined"
                      onClick={() => navigate(`/groups/${g.telegram_group_id}`)}
                      sx={{ cursor: 'pointer' }}
                    />
                  ))}
                  {officialGroups.length > 6 && (
                    <Chip
                      label={`+${officialGroups.length - 6} more`}
                      size="small"
                      variant="outlined"
                      onClick={() => navigate('/groups')}
                      sx={{ cursor: 'pointer' }}
                    />
                  )}
                </Box>
              </>
            )}
          </CardContent>
        </Card>

        {/* ── Custom Bots ───────────────────────────────────────────────────── */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1.5 }}>
            Custom Bots
          </Typography>
          <Button variant="outlined" size="small" startIcon={<Add />} onClick={() => setAddOpen(true)}>
            Connect Bot
          </Button>
        </Box>

        {loading ? (
          <Box sx={{ py: 4 }}><LinearProgress /></Box>
        ) : bots.length === 0 ? (
          <Card sx={{ textAlign: 'center', py: 6 }}>
            <SmartToy sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" gutterBottom>No custom bots connected</Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              Pro/Enterprise users can connect their own bot for white-label usage.
            </Typography>
            <Button variant="contained" startIcon={<Add />} onClick={() => setAddOpen(true)}>
              Connect Bot Token
            </Button>
          </Card>
        ) : (
          <Grid container spacing={2}>
            {bots.map((bot) => {
              const lastActiveLabel = bot.last_active ? _relativeTime(bot.last_active) : 'Never';
              const healthStatus = bot.health_status || bot.status || 'active';

              return (
                <Grid item xs={12} md={6} key={bot.id}>
                  <Card>
                    <CardContent>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                        <Box>
                          <Typography variant="h6" fontWeight={600}>
                            {bot.bot_name || `@${bot.bot_username}`}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            @{bot.bot_username}
                          </Typography>
                          {bot.hub_bot_id && (
                            <Chip
                              icon={<Psychology sx={{ fontSize: '13px !important' }} />}
                              label="Also in Echo"
                              size="small"
                              color="secondary"
                              variant="outlined"
                              sx={{ mt: 0.5, fontSize: '0.7rem' }}
                            />
                          )}
                        </Box>
                        <StatusChip status={healthStatus} />
                      </Box>

                      <Divider sx={{ my: 1.5 }} />

                      {/* Stats */}
                      <Grid container spacing={1} sx={{ mb: 1.5 }}>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">Groups Linked</Typography>
                          <Typography variant="body2" fontWeight={600}>
                            {bot.linked_groups_count ?? 0}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">Last Active</Typography>
                          <Typography variant="body2" fontWeight={600}>
                            {lastActiveLabel}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">Added</Typography>
                          <Typography variant="body2" fontWeight={600}>
                            {new Date(bot.created_at).toLocaleDateString()}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">Status</Typography>
                          <Typography variant="body2" fontWeight={600} color={
                            healthStatus === 'active' ? 'success.main' :
                            healthStatus === 'unreachable' ? 'error.main' : 'text.secondary'
                          }>
                            {healthStatus === 'active' ? 'Active' :
                             healthStatus === 'idle' ? 'Idle' :
                             healthStatus === 'offline' ? 'Offline' :
                             healthStatus === 'unreachable' ? 'Unreachable' : 'Active'}
                          </Typography>
                        </Grid>
                      </Grid>

                      {healthStatus === 'unreachable' && (
                        <Alert severity="error" sx={{ mb: 1.5, py: 0.5 }}>
                          Bot hasn't been active in over 30 days. Check your token is still valid.
                        </Alert>
                      )}

                      {/* Actions */}
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Button
                          size="small"
                          variant="contained"
                          startIcon={<Groups />}
                          onClick={() => navigate(`/groups?bot_id=${bot.id}`)}
                          sx={{ flex: 1 }}
                        >
                          Groups
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          endIcon={<OpenInNew />}
                          href={`https://t.me/${bot.bot_username}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          sx={{ flex: 1 }}
                        >
                          Open
                        </Button>
                        <Tooltip title="Disconnect bot">
                          <IconButton size="small" color="error" onClick={() => setDeleteTarget(bot)}>
                            <Delete fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>
              );
            })}
          </Grid>
        )}
      </Container>

      {/* Connect bot dialog — two-step: validate → preview → save */}
      <Dialog open={addOpen} onClose={handleCloseAddDialog} maxWidth="sm" fullWidth>
        <DialogTitle>Connect Your Own Bot</DialogTitle>
        <DialogContent sx={{ pt: '16px !important' }}>
          <Alert severity="info" sx={{ mb: 2 }}>
            Create a bot via <strong>@BotFather</strong> on Telegram, then paste the token below.
            Your token is encrypted and never exposed.
          </Alert>

          {addError && (
            <Alert severity="error" sx={{ mb: 2 }}>{addError}</Alert>
          )}

          {/* Step 1 — enter token */}
          <TextField
            fullWidth
            label="Bot Token"
            value={form.bot_token}
            onChange={(e) => {
              setForm({ bot_token: e.target.value.trim() });
              setPreview(null);   // reset preview if token changes
              setAddError('');
            }}
            placeholder="1234567890:AAAA..."
            type="text"
            autoComplete="off"
            sx={{ mb: 2 }}
            disabled={validating || adding}
          />

          {/* Security disclosure */}
          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75, mb: 2, p: 1.25, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 1.5, border: '1px solid', borderColor: 'divider' }}>
            <Lock sx={{ fontSize: 13, color: 'text.disabled', mt: 0.1, flexShrink: 0 }} />
            <Typography variant="caption" color="text.disabled" lineHeight={1.5}>
              Your token is encrypted with AES-256 before storage. We never log or display it in plaintext.
              Revoke access at any time by regenerating your token in @BotFather.
            </Typography>
          </Box>

          {/* Step 2 — preview after validation */}
          {preview && (
            <Alert severity="success" sx={{ mb: 2 }}>
              <Typography variant="body2" fontWeight={600}>✅ Bot verified!</Typography>
              <Typography variant="body2">Name: <strong>{preview.bot_name}</strong></Typography>
              <Typography variant="body2">Username: <strong>@{preview.bot_username}</strong></Typography>
              {!preview.can_join_groups && (
                <Typography variant="body2" color="warning.main" mt={0.5}>
                  ⚠️ This bot cannot join groups. Enable "Allow Groups &amp; Channels" in @BotFather settings.
                </Typography>
              )}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseAddDialog}>Cancel</Button>

          {/* Show Verify button until preview is ready */}
          {!preview ? (
            <Button
              variant="contained"
              onClick={handleValidate}
              disabled={validating || !form.bot_token}
            >
              {validating ? <CircularProgress size={20} /> : 'Verify Token'}
            </Button>
          ) : (
            <Button
              variant="contained"
              color="success"
              onClick={handleAdd}
              disabled={adding}
            >
              {adding ? <CircularProgress size={20} /> : 'Connect Bot'}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Disconnect confirm */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle>Disconnect Bot?</DialogTitle>
        <DialogContent>
          <Typography>
            Disconnect <strong>@{deleteTarget?.bot_username}</strong>? Groups using this bot will fall back
            to the official Telegizer bot.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDelete}>Disconnect</Button>
        </DialogActions>
      </Dialog>
      <UpsellModal
        open={upsellOpen}
        onClose={() => setUpsellOpen(false)}
        feature="custom_bot"
        limitMessage={upsellMessage}
      />
    </Box>
    </PlanGate>
  );
}

