import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Grid, Stack, Chip, Button, CircularProgress, LinearProgress,
  Breadcrumbs, Link as MuiLink, Paper, Alert, TextField, FormControl, InputLabel,
  Select, MenuItem, Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material';
import { ArrowBack, Block, CheckCircle, Delete, Save } from '@mui/icons-material';
import { useParams, useNavigate, Link as RouterLink } from 'react-router-dom';
import { toast } from 'react-toastify';
import { admin } from '../services/api';
import { Field, SectionTitle, fmtDate, fmtDateTime, usd } from '../components/AdminDetailKit';

export default function AdminUserDetail() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const [u, setU] = useState(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState('');

  const [subTier, setSubTier] = useState('free');
  const [notes, setNotes] = useState('');
  const [notesDirty, setNotesDirty] = useState(false);

  const [banOpen, setBanOpen] = useState(false);
  const [banReason, setBanReason] = useState('');
  const [giftOpen, setGiftOpen] = useState(false);
  const [giftTier, setGiftTier] = useState('pro');
  const [giftDays, setGiftDays] = useState(30);
  const [giftNote, setGiftNote] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await admin.getUser(userId);
      const data = res.data.user;
      setU(data);
      setSubTier(data.subscription_tier || 'free');
      setNotes(data.admin_notes || '');
      setNotesDirty(false);
    } catch (err) {
      toast.error(err?.response?.data?.error || 'Failed to load user');
    } finally { setLoading(false); }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  const run = async (key, fn, okMsg, reload = true) => {
    setAction(key);
    try { await fn(); if (okMsg) toast.success(okMsg); if (reload) await load(); }
    catch (err) { toast.error(err?.response?.data?.error || 'Action failed'); }
    finally { setAction(''); }
  };

  const handleUpdateSub = () => run('sub', () => admin.updateSubscription(userId, { tier: subTier }), 'Subscription updated');
  const handleUnban = () => run('unban', () => admin.unbanUser(userId), 'User unbanned');
  const handleBan = () => run('ban', async () => {
    await admin.banUser(userId, { reason: banReason || 'Violation of terms of service' });
    setBanOpen(false);
  }, 'User banned');
  const handleGift = () => run('gift', async () => {
    await admin.giftSubscription(userId, { tier: giftTier, duration_days: giftDays, note: giftNote });
    setGiftOpen(false);
  }, `Gifted ${giftTier} for ${giftDays} days`);
  const handleDelete = () => {
    if (!window.confirm('Permanently delete this user? This cannot be undone.')) return;
    run('del', () => admin.deleteUser(userId), 'User deleted', false).then(() => navigate('/admin'));
  };
  const saveNotes = () => run('notes', async () => {
    await admin.updateUserNotes(userId, { notes });
    setNotesDirty(false);
  }, 'Notes saved', false);

  if (loading && !u) return <Box display="flex" justifyContent="center" mt={8}><CircularProgress /></Box>;
  if (!u) {
    return (
      <Box p={3}>
        <Button startIcon={<ArrowBack />} onClick={() => navigate('/admin')}>Back to Admin</Button>
        <Alert severity="error" sx={{ mt: 2 }}>User not found.</Alert>
      </Box>
    );
  }

  const riskColor = u.risk?.level === 'high' ? 'error' : u.risk?.level === 'medium' ? 'warning' : 'success';

  return (
    <Box sx={{ maxWidth: 1100, mx: 'auto', p: { xs: 2, sm: 3 }, pb: 'var(--bottom-nav-clearance, 24px)' }}>
      <Breadcrumbs sx={{ mb: 1 }}>
        <MuiLink component={RouterLink} to="/admin" underline="hover" color="inherit">Admin</MuiLink>
        <MuiLink component={RouterLink} to="/admin" underline="hover" color="inherit">Users</MuiLink>
        <Typography color="text.primary">{u.full_name || u.email || `User ${u.id}`}</Typography>
      </Breadcrumbs>

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }} mb={2}>
        <Button startIcon={<ArrowBack />} onClick={() => navigate('/admin')} size="small">Back</Button>
        <Box flex={1}>
          <Typography variant="h5" fontWeight={700}>{u.full_name || '—'}</Typography>
          <Typography variant="caption" color="text.secondary">ID: {u.id} · Joined {fmtDate(u.created_at)}</Typography>
        </Box>
        <Chip size="small" color={riskColor} label={`Risk: ${u.risk?.score ?? 0} (${u.risk?.level || 'low'})`} />
        <Chip size="small" label={(u.subscription_tier || 'free').toUpperCase()} variant="outlined" />
        {u.is_banned && <Chip size="small" color="error" label="BANNED" />}
      </Stack>

      {loading && <LinearProgress sx={{ mb: 2 }} />}

      {u.is_banned && (
        <Alert severity="error" sx={{ mb: 2 }}>
          <Typography variant="body2" fontWeight={600}>Banned</Typography>
          <Typography variant="caption">{u.ban_reason}</Typography>
        </Alert>
      )}

      <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
        <SectionTitle sx={{ mt: 0 }}>Profile & Auth</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><Field label="Email" value={u.email} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Plan" value={u.subscription_tier?.toUpperCase()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Auth source" value={u.auth?.provider} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Timezone" value={u.timezone} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Telegram" value={u.telegram_username ? `@${u.telegram_username}` : (u.auth?.telegram_user_id || '—')} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Telegram ID" mono value={u.auth?.telegram_user_id} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Email verified" value={u.auth?.email_verified ? 'Yes' : 'No'} /></Grid>
          <Grid item xs={6} sm={3}><Field label="2FA" value={u.auth?.two_factor_enabled ? 'Enabled' : 'Disabled'} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Password set" value={u.auth?.has_password ? 'Yes' : 'No'} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Recovery email" value="Not tracked yet" /></Grid>
          <Grid item xs={6} sm={3}><Field label="Last login" value="Not tracked yet" /></Grid>
          <Grid item xs={6} sm={3}><Field label="Referral code" mono value={u.referral_code} /></Grid>
        </Grid>

        <SectionTitle>Revenue & Subscription</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><Field label="Lifetime revenue" value={usd(u.revenue?.lifetime_usd || 0)} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Payments" value={u.revenue?.payment_count ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Trial used" value={u.revenue?.trial_used ? 'Yes' : 'No'} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Expires" value={u.revenue?.subscription_expires_at ? fmtDate(u.revenue.subscription_expires_at) : '—'} /></Grid>
        </Grid>
        {u.recent_payments?.length > 0 && (
          <Box mt={1}>
            {u.recent_payments.slice(0, 6).map((p) => (
              <Stack key={p.id} direction="row" justifyContent="space-between" py={0.5} borderBottom="1px solid" borderColor="divider">
                <Typography variant="caption">{p.plan?.toUpperCase()} · {p.provider} · {p.status}</Typography>
                <Typography variant="caption" fontWeight={600} color="success.main">{usd((p.amount_usd || 0) / 100)}</Typography>
                <Typography variant="caption" color="text.disabled">{fmtDate(p.created_at)}</Typography>
              </Stack>
            ))}
          </Box>
        )}

        <SectionTitle>Referrals</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <Field label="Referred by" value={u.referrer
              ? `${u.referrer.email || u.referrer.name || 'User ' + u.referrer.user_id} (${u.referrer.status})`
              : 'Direct signup'} />
          </Grid>
          <Grid item xs={6} sm={3}><Field label="Referrals made" value={u.referral_stats?.total ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Approved" value={u.referral_stats?.approved ?? 0} /></Grid>
        </Grid>
        {u.referrals_made?.length > 0 && (
          <Box mt={1}>
            {u.referrals_made.slice(0, 6).map((r, i) => (
              <Stack key={i} direction="row" spacing={1} justifyContent="space-between" py={0.5} borderBottom="1px solid" borderColor="divider" alignItems="center">
                <Typography variant="caption" noWrap sx={{ flex: 1 }}>{r.email || `User ${r.referred_user_id}`}</Typography>
                <Chip size="small" label={r.status} color={r.status === 'approved' ? 'success' : r.status === 'pending' ? 'warning' : 'default'} />
                {(r.ip_match || r.device_match) && <Chip size="small" color="error" label={r.ip_match ? 'IP match' : 'Device match'} />}
                <Typography variant="caption" color="text.disabled">{fmtDate(r.created_at)}</Typography>
              </Stack>
            ))}
          </Box>
        )}

        <SectionTitle>Groups & Bots</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><Field label="Groups owned" value={u.owned_groups?.length ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Admin of (TG)" value={u.admin_of_groups?.length ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Custom bots" value={u.custom_bots?.length ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Legacy bots" value={u.bots?.length ?? 0} /></Grid>
        </Grid>
        {u.owned_groups?.length > 0 && (
          <Box mt={1}>
            {u.owned_groups.slice(0, 8).map((g) => (
              <Stack key={g.telegram_group_id} direction="row" spacing={1} justifyContent="space-between" py={0.5} borderBottom="1px solid" borderColor="divider" alignItems="center">
                <MuiLink component={RouterLink} to={`/admin/groups/${g.telegram_group_id}`} variant="caption" noWrap sx={{ flex: 1 }}>{g.title}</MuiLink>
                <Chip size="small" label={g.bot_status} color={g.bot_status === 'active' ? 'success' : g.bot_status === 'pending' ? 'warning' : 'default'} />
                <Typography variant="caption" color="text.disabled">{(g.member_count || 0).toLocaleString()} · {g.linked_via_bot_type}</Typography>
              </Stack>
            ))}
          </Box>
        )}
        {u.admin_of_groups?.length > 0 && (
          <Box mt={1}>
            {u.admin_of_groups.slice(0, 8).map((g) => (
              <Stack key={g.telegram_group_id} direction="row" justifyContent="space-between" py={0.4} borderBottom="1px solid" borderColor="divider">
                <MuiLink component={RouterLink} to={`/admin/groups/${g.telegram_group_id}`} variant="caption">{g.title}</MuiLink>
                <Typography variant="caption" color="text.disabled">{g.role}</Typography>
              </Stack>
            ))}
          </Box>
        )}

        <SectionTitle>Official Bot Usage</SectionTitle>
        {u.official_bot_usage ? (
          <Grid container spacing={2}>
            <Grid item xs={6} sm={3}><Field label="Groups active in" value={u.official_bot_usage.groups_active_in} /></Grid>
            <Grid item xs={6} sm={3}><Field label="Messages" value={(u.official_bot_usage.total_messages || 0).toLocaleString()} /></Grid>
            <Grid item xs={6} sm={3}><Field label="XP" value={(u.official_bot_usage.total_xp || 0).toLocaleString()} /></Grid>
            <Grid item xs={6} sm={3}><Field label="Last message" value={u.official_bot_usage.last_message_at ? fmtDate(u.official_bot_usage.last_message_at) : '—'} /></Grid>
          </Grid>
        ) : <Typography variant="caption" color="text.disabled">No linked Telegram identity — usage not attributable.</Typography>}

        <SectionTitle>Risk & Suspicious Activity</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><Field label="Risk score" value={`${u.risk?.score ?? 0} / 100`} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Suspicious flag" value={u.risk?.is_suspicious ? 'Yes' : 'No'} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Chargebacks" value={u.risk?.chargeback_count ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Suspicious events" value={u.risk?.suspicious_event_count ?? 0} /></Grid>
        </Grid>
        {u.suspicious_events?.length > 0 && (
          <Box mt={1}>
            {u.suspicious_events.map((s) => (
              <Typography key={s.id} variant="caption" display="block" color="warning.main">
                • {s.reason} <Typography component="span" variant="caption" color="text.disabled">({fmtDate(s.created_at)})</Typography>
              </Typography>
            ))}
          </Box>
        )}

        <SectionTitle>Admin Notes</SectionTitle>
        <TextField
          fullWidth multiline minRows={2} size="small" placeholder="Internal notes about this user (visible to admins only)…"
          value={notes} onChange={(e) => { setNotes(e.target.value); setNotesDirty(true); }}
        />
        <Box mt={1}>
          <Button size="small" variant="contained" startIcon={action === 'notes' ? <CircularProgress size={14} /> : <Save />}
            onClick={saveNotes} disabled={!notesDirty || !!action}>Save notes</Button>
        </Box>

        <SectionTitle>Admin Actions Against This User</SectionTitle>
        {u.admin_actions?.length > 0 ? u.admin_actions.slice(0, 12).map((a) => (
          <Stack key={a.id} direction="row" justifyContent="space-between" py={0.4} borderBottom="1px solid" borderColor="divider">
            <Typography variant="caption">{a.action}{a.severity && a.severity !== 'info' ? ` · ${a.severity}` : ''}</Typography>
            <Typography variant="caption" color="text.disabled">{fmtDateTime(a.created_at)}</Typography>
          </Stack>
        )) : <Typography variant="caption" color="text.disabled">No admin actions recorded.</Typography>}

        <SectionTitle>Activity Timeline</SectionTitle>
        {u.timeline?.length > 0 ? u.timeline.slice(0, 20).map((t, i) => (
          <Stack key={i} direction="row" justifyContent="space-between" py={0.4} borderBottom="1px solid" borderColor="divider">
            <Typography variant="caption">{t.label}</Typography>
            <Typography variant="caption" color="text.disabled">{fmtDateTime(t.at)}</Typography>
          </Stack>
        )) : <Typography variant="caption" color="text.disabled">No activity recorded.</Typography>}

        <SectionTitle>Manage</SectionTitle>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel>Subscription Tier</InputLabel>
              <Select value={subTier} label="Subscription Tier" onChange={(e) => setSubTier(e.target.value)}>
                <MenuItem value="free">Free</MenuItem>
                <MenuItem value="pro">Pro</MenuItem>
                <MenuItem value="enterprise">Enterprise</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={8}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <Button variant="outlined" onClick={handleUpdateSub} disabled={action === 'sub'}>
                {action === 'sub' ? <CircularProgress size={18} /> : 'Update subscription'}
              </Button>
              <Button variant="contained" color="success" onClick={() => setGiftOpen(true)} disabled={!!action}>🎁 Gift</Button>
              {u.is_banned ? (
                <Button variant="outlined" color="success" startIcon={<CheckCircle />} onClick={handleUnban} disabled={!!action}>
                  {action === 'unban' ? <CircularProgress size={18} /> : 'Unban'}
                </Button>
              ) : (
                <Button variant="outlined" color="warning" startIcon={<Block />} onClick={() => setBanOpen(true)} disabled={!!action}>Ban</Button>
              )}
              <Button variant="outlined" color="error" startIcon={<Delete />} onClick={handleDelete} disabled={!!action}>
                {action === 'del' ? <CircularProgress size={18} /> : 'Delete'}
              </Button>
            </Stack>
          </Grid>
        </Grid>
      </Paper>

      {/* Gift dialog */}
      <Dialog open={giftOpen} onClose={() => setGiftOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>🎁 Gift Subscription — {u.email}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} pt={1}>
            <FormControl fullWidth size="small">
              <InputLabel>Plan</InputLabel>
              <Select value={giftTier} label="Plan" onChange={(e) => setGiftTier(e.target.value)}>
                <MenuItem value="pro">Pro</MenuItem>
                <MenuItem value="enterprise">Enterprise</MenuItem>
              </Select>
            </FormControl>
            <TextField size="small" label="Duration (days)" type="number" value={giftDays}
              onChange={(e) => setGiftDays(Number(e.target.value))} inputProps={{ min: 1, max: 3650 }} />
            <TextField size="small" label="Note (internal)" value={giftNote}
              onChange={(e) => setGiftNote(e.target.value)} placeholder="e.g. KOL partnership, support goodwill…" />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGiftOpen(false)}>Cancel</Button>
          <Button variant="contained" color="success" onClick={handleGift} disabled={action === 'gift'}>
            {action === 'gift' ? <CircularProgress size={16} /> : `Gift ${giftDays} days`}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Ban dialog */}
      <Dialog open={banOpen} onClose={() => setBanOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Ban {u.email}</DialogTitle>
        <DialogContent>
          <TextField fullWidth multiline rows={2} label="Reason" value={banReason}
            onChange={(e) => setBanReason(e.target.value)} sx={{ mt: 1 }} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBanOpen(false)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={handleBan} disabled={action === 'ban'}>
            {action === 'ban' ? <CircularProgress size={18} /> : 'Confirm Ban'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
