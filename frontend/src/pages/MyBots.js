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
  Settings, CheckCircle, Warning, BarChart, Bolt,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { customBots, telegramGroups as telegramGroupsApi } from '../services/api';
import TopNav from '../components/TopNav';

const BOT_USERNAME = process.env.REACT_APP_BOT_USERNAME || 'telegizer_bot';

function StatusChip({ status }) {
  const map = {
    active:   { label: 'Active',   color: 'success' },
    inactive: { label: 'Idle',     color: 'warning' },
    error:    { label: 'Error',    color: 'error'   },
    stopped:  { label: 'Stopped',  color: 'default' },
    unknown:  { label: 'Unknown',  color: 'default' },
  };
  const { label, color } = map[status] || { label: status || 'Unknown', color: 'default' };
  return <Chip label={label} color={color} size="small" />;
}

function PermSummary({ perms }) {
  if (!perms || Object.keys(perms).length === 0) {
    return <Chip label="Permissions unknown" color="default" size="small" />;
  }
  const granted = Object.values(perms).filter(Boolean).length;
  const total   = Object.keys(perms).length;
  if (granted === total) {
    return <Chip label="Full permissions" color="success" size="small" icon={<CheckCircle sx={{ fontSize: '14px !important' }} />} />;
  }
  const missing = total - granted;
  return <Chip label={`${missing} perm${missing > 1 ? 's' : ''} missing`} color="warning" size="small" icon={<Warning sx={{ fontSize: '14px !important' }} />} />;
}

export default function MyBots() {
  const navigate = useNavigate();
  const [bots, setBots] = useState([]);
  const [officialGroups, setOfficialGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ bot_token: '', bot_username: '' });
  const [adding, setAdding] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [botsRes, groupsRes] = await Promise.all([
        customBots.list(),
        telegramGroupsApi.list(),
      ]);
      setBots(botsRes.data.bots || []);
      setOfficialGroups((groupsRes.data.groups || []).filter(
        (g) => g.linked_via_bot_type === 'official' || !g.linked_via_bot_type
      ));
    } catch {
      toast.error('Failed to load bots');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    if (!form.bot_token || !form.bot_username) return;
    setAdding(true);
    try {
      await customBots.add(form);
      toast.success('Custom bot connected!');
      setAddOpen(false);
      setForm({ bot_token: '', bot_username: '' });
      load();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to connect bot');
    } finally {
      setAdding(false);
    }
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

  // Classify custom bot groups (linked_via_bot_type === custom bot id or username)
  const customBotGroups = (g) =>
    officialGroups.filter((og) => og.linked_via_bot_type !== 'official');

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <TopNav
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
                    onClick={() => navigate('/my-groups')}
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
                    rel="noreferrer"
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
                      onClick={() => navigate(`/my-groups/${g.telegram_group_id}`)}
                      sx={{ cursor: 'pointer' }}
                    />
                  ))}
                  {officialGroups.length > 6 && (
                    <Chip
                      label={`+${officialGroups.length - 6} more`}
                      size="small"
                      variant="outlined"
                      onClick={() => navigate('/my-groups')}
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
              const lastActive = bot.last_active ? new Date(bot.last_active) : null;
              const lastActiveLabel = lastActive
                ? lastActive.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                : 'Never';
              const healthStatus = bot.health_status || bot.status || 'unknown';

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
                            healthStatus === 'error' ? 'error.main' : 'warning.main'
                          }>
                            {healthStatus.charAt(0).toUpperCase() + healthStatus.slice(1)}
                          </Typography>
                        </Grid>
                      </Grid>

                      {healthStatus === 'error' && (
                        <Alert severity="error" sx={{ mb: 1.5, py: 0.5 }}>
                          Bot is unreachable. Check your token is still valid.
                        </Alert>
                      )}

                      {/* Actions */}
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Button
                          size="small"
                          variant="contained"
                          startIcon={<Groups />}
                          onClick={() => navigate('/my-groups')}
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
                          rel="noreferrer"
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

      {/* Connect bot dialog */}
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Connect Your Own Bot</DialogTitle>
        <DialogContent sx={{ pt: '16px !important' }}>
          <Alert severity="info" sx={{ mb: 2 }}>
            <strong>Tip:</strong> If your Telegram account is linked, you can paste your token directly
            in <strong>@{BOT_USERNAME} → Advanced → Connect Own Bot</strong>. The token is deleted immediately.
          </Alert>
          <Alert severity="success" sx={{ mb: 2 }}>
            Create a bot via <strong>@BotFather</strong> on Telegram, then paste the token below.
            It is encrypted and never exposed.
          </Alert>
          <TextField
            fullWidth
            label="Bot Token"
            value={form.bot_token}
            onChange={(e) => setForm({ ...form, bot_token: e.target.value.trim() })}
            placeholder="1234567890:AAAA..."
            type="password"
            sx={{ mb: 2 }}
          />
          <TextField
            fullWidth
            label="Bot Username"
            value={form.bot_username}
            onChange={(e) => setForm({ ...form, bot_username: e.target.value.trim().replace('@', '') })}
            placeholder="mybot"
            InputProps={{ startAdornment: <Typography color="text.secondary" mr={0.5}>@</Typography> }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleAdd}
            disabled={adding || !form.bot_token || !form.bot_username}
          >
            {adding ? <CircularProgress size={20} /> : 'Connect Bot'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Disconnect confirm */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
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
    </Box>
  );
}
