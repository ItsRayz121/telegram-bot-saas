import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Box, AppBar, Toolbar, Typography, IconButton, Card, CardContent,
  Grid, CircularProgress, TextField, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Chip, Button, Dialog,
  DialogTitle, DialogContent, DialogActions, MenuItem, Select,
  FormControl, InputLabel, Pagination, InputAdornment, Tabs, Tab,
  Alert, Tooltip, LinearProgress, Stack, Divider, Switch, FormControlLabel,
} from '@mui/material';
import {
  ArrowBack, Search, Block, CheckCircle, Delete, Groups, SmartToy,
  LinkOff, Lock, Warning, TrendingUp, People, AttachMoney,
  History, FolderOpen, Campaign, VerifiedUser, Refresh,
  CheckCircleOutline, Cancel, Circle, Flag,
  Security, AccountTree, TrendingDown, Payment, FileDownload,
  MonitorHeart, NetworkCheck, Tune, Key, Psychology, AttachMoney as MoneyIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { admin } from '../services/api';
import { LineChart, Line, XAxis, YAxis, Tooltip as ReTooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function parseApiError(err) {
  const status = err?.response?.status;
  const data = err?.response?.data;
  const message = data?.error || data?.message || err?.message || 'Unknown error';
  return { message, is403: status === 403 };
}

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function usd(val) {
  return `$${(val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ─── Reusable stat card ───────────────────────────────────────────────────────

function StatCard({ label, value, color = '#2196f3', sub, icon: Icon }) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent sx={{ pb: '12px !important' }}>
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between">
          <Box>
            <Typography variant="h4" fontWeight={700} sx={{ color, lineHeight: 1.2 }}>
              {value?.toLocaleString() ?? '—'}
            </Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>{label}</Typography>
            {sub && <Typography variant="caption" color="text.disabled">{sub}</Typography>}
          </Box>
          {Icon && (
            <Box sx={{ bgcolor: `${color}18`, borderRadius: 2, p: 1, display: 'flex' }}>
              <Icon sx={{ color, fontSize: 22 }} />
            </Box>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

// ─── Status chip helper ───────────────────────────────────────────────────────

function StatusChip({ label, map }) {
  const defaults = { active: 'success', approved: 'success', ok: 'success', pending: 'warning', warning: 'warning', error: 'error', disabled: 'error', rejected: 'error', banned: 'error', suspicious: 'warning', unknown: 'default', info: 'info', critical: 'error' };
  const color = (map || defaults)[label] || defaults[label] || 'default';
  return <Chip label={label} size="small" color={color} />;
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyRow({ cols, message = 'No records found' }) {
  return (
    <TableRow>
      <TableCell colSpan={cols} align="center">
        <Typography color="text.secondary" py={3}>{message}</Typography>
      </TableCell>
    </TableRow>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 0 — DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════════

function DashboardTab({ stats, botStats, revenue, health, featureAdoption, loading, onRefresh }) {
  if (loading) return <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box>;

  const healthColor = (v) => {
    if (v === 'ok') return '#22c55e';
    if (v === 'unknown') return '#f59e0b';
    return '#ef4444';
  };

  return (
    <Box>
      {/* User stats */}
      <Typography variant="subtitle2" color="text.secondary" fontWeight={600} mb={1} textTransform="uppercase" letterSpacing={1}>
        Platform Users
      </Typography>
      <Grid container spacing={2} mb={3}>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Total Users" value={stats?.total_users} icon={People} /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Free" value={stats?.free_users} color="#64748b" /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Pro" value={stats?.pro_users} color="#7c4dff" icon={VerifiedUser} /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Enterprise" value={stats?.enterprise_users} color="#f59e0b" /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard label="New (7d)" value={stats?.new_users_7d} color="#06b6d4" /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Banned" value={stats?.banned_users} color="#ef4444" /></Grid>
      </Grid>

      {/* Bot / group stats */}
      <Typography variant="subtitle2" color="text.secondary" fontWeight={600} mb={1} textTransform="uppercase" letterSpacing={1}>
        Bot Ecosystem
      </Typography>
      <Grid container spacing={2} mb={3}>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Custom Bots" value={stats?.total_bots} color="#00bcd4" icon={SmartToy} /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Active Bots" value={stats?.active_bots} color="#22c55e" /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Groups (Official)" value={botStats?.total_linked_groups} color="#8b5cf6" icon={Groups} /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Active Groups" value={botStats?.active_groups} color="#22c55e" /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Pending Groups" value={botStats?.pending_groups} color="#f59e0b" /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard label="Total Members" value={stats?.total_members} color="#06b6d4" /></Grid>
      </Grid>

      {/* Revenue */}
      {revenue && (
        <>
          <Typography variant="subtitle2" color="text.secondary" fontWeight={600} mb={1} textTransform="uppercase" letterSpacing={1}>
            Revenue
          </Typography>
          <Grid container spacing={2} mb={3}>
            <Grid item xs={6} sm={4} md={2}><StatCard label="MRR" value={usd(revenue.mrr)} color="#22c55e" icon={AttachMoney} /></Grid>
            <Grid item xs={6} sm={4} md={2}><StatCard label="ARR" value={usd(revenue.arr)} color="#16a34a" /></Grid>
            <Grid item xs={6} sm={4} md={2}><StatCard label="This Month" value={usd(revenue.this_month)} color="#2563eb" /></Grid>
            <Grid item xs={6} sm={4} md={2}><StatCard label="Last Month" value={usd(revenue.last_month)} color="#64748b" /></Grid>
            <Grid item xs={6} sm={4} md={2}><StatCard label="All Time" value={usd(revenue.total_all_time)} color="#7c4dff" /></Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Card sx={{ height: '100%' }}>
                <CardContent sx={{ pb: '12px !important' }}>
                  <Typography variant="body2" color="text.secondary" mb={0.5}>Payment Methods</Typography>
                  <Typography variant="caption" display="block">Card: <b>{revenue.lemonsqueezy_count}</b></Typography>
                  <Typography variant="caption" display="block">Crypto: <b>{revenue.nowpayments_count}</b></Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Churn stats */}
          {(revenue.churned_30d !== undefined) && (
            <Grid container spacing={2} mb={2}>
              <Grid item xs={6} sm={3}>
                <StatCard
                  label="Churned (30d)"
                  value={revenue.churned_30d}
                  color="#ef4444"
                  sub={revenue.churned_30d_prev != null ? `prev 30d: ${revenue.churned_30d_prev}` : undefined}
                  icon={TrendingDown}
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <StatCard label="Active Pro" value={revenue.pro_subscribers} color="#7c4dff" />
              </Grid>
              <Grid item xs={6} sm={3}>
                <StatCard label="Active Enterprise" value={revenue.enterprise_subscribers} color="#f59e0b" />
              </Grid>
            </Grid>
          )}

          {/* Revenue trend chart */}
          {revenue.monthly_trend?.length > 0 && (
            <Card sx={{ mb: 3, p: 2 }}>
              <Typography variant="subtitle2" fontWeight={600} mb={2}>Monthly Revenue (Last 6 Months)</Typography>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={revenue.monthly_trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                  <ReTooltip formatter={(v) => [`$${v}`, 'Revenue']} />
                  <Line type="monotone" dataKey="revenue" stroke="#22c55e" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* Cohort conversion funnel */}
          {revenue.cohort?.length > 0 && (
            <Card sx={{ mb: 3 }}>
              <CardContent sx={{ pb: '12px !important' }}>
                <Typography variant="subtitle2" fontWeight={600} mb={2}>Cohort Conversion (Free → Pro → Enterprise)</Typography>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Cohort</TableCell>
                        <TableCell align="right">Free</TableCell>
                        <TableCell align="right">Pro</TableCell>
                        <TableCell align="right">Enterprise</TableCell>
                        <TableCell align="right">Conversion %</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {revenue.cohort.map(row => {
                        const total = (row.free || 0) + (row.pro || 0) + (row.enterprise || 0);
                        const paidPct = total ? (((row.pro || 0) + (row.enterprise || 0)) / total * 100).toFixed(1) : '0.0';
                        return (
                          <TableRow key={row.month}>
                            <TableCell>{row.month}</TableCell>
                            <TableCell align="right">{row.free || 0}</TableCell>
                            <TableCell align="right" sx={{ color: '#7c4dff', fontWeight: 600 }}>{row.pro || 0}</TableCell>
                            <TableCell align="right" sx={{ color: '#f59e0b', fontWeight: 600 }}>{row.enterprise || 0}</TableCell>
                            <TableCell align="right">
                              <Chip
                                label={`${paidPct}%`}
                                size="small"
                                color={Number(paidPct) >= 20 ? 'success' : Number(paidPct) >= 10 ? 'warning' : 'default'}
                              />
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Platform health */}
      {/* Feature Adoption Matrix */}
      {featureAdoption && featureAdoption.features?.length > 0 && (
        <>
          <Typography variant="subtitle2" color="text.secondary" fontWeight={600} mb={1} textTransform="uppercase" letterSpacing={1}>
            Feature Adoption
          </Typography>
          <Card sx={{ mb: 3 }}>
            <CardContent sx={{ pb: '12px !important' }}>
              <Typography variant="caption" color="text.disabled" mb={2} display="block">
                Unique users who have used each feature · Total users: {featureAdoption.total_users?.toLocaleString()}
              </Typography>
              <Grid container spacing={1}>
                {featureAdoption.features.map((f) => (
                  <Grid item xs={12} sm={6} md={4} key={f.feature}>
                    <Box sx={{ mb: 1 }}>
                      <Stack direction="row" justifyContent="space-between" mb={0.5}>
                        <Typography variant="body2">{f.feature}</Typography>
                        <Typography variant="body2" fontWeight={600} color="text.secondary">
                          {f.users?.toLocaleString()} <Typography component="span" variant="caption" color="text.disabled">({f.pct}%)</Typography>
                        </Typography>
                      </Stack>
                      <LinearProgress
                        variant="determinate"
                        value={Math.min(f.pct, 100)}
                        sx={{ height: 6, borderRadius: 3, bgcolor: '#f0f4f8', '& .MuiLinearProgress-bar': { bgcolor: f.pct > 50 ? '#22c55e' : f.pct > 20 ? '#f59e0b' : '#64748b' } }}
                      />
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </>
      )}

      {health && (
        <>
          <Typography variant="subtitle2" color="text.secondary" fontWeight={600} mb={1} textTransform="uppercase" letterSpacing={1}>
            Platform Health
          </Typography>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1} mb={2}>
                <Circle sx={{ fontSize: 12, color: health.status === 'ok' ? '#22c55e' : '#ef4444' }} />
                <Typography variant="body2" fontWeight={600}>
                  Status: <span style={{ color: health.status === 'ok' ? '#22c55e' : '#ef4444' }}>{health.status?.toUpperCase()}</span>
                </Typography>
                <Typography variant="caption" color="text.disabled" ml="auto">
                  Checked {fmtDateTime(health.timestamp)}
                </Typography>
                <IconButton size="small" onClick={onRefresh}><Refresh fontSize="small" /></IconButton>
              </Stack>
              <Grid container spacing={2}>
                {Object.entries(health.checks || {}).filter(([k]) => typeof health.checks[k] === 'string').map(([key, val]) => (
                  <Grid item xs={6} sm={3} key={key}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Circle sx={{ fontSize: 10, color: healthColor(val) }} />
                      <Box>
                        <Typography variant="caption" color="text.secondary" textTransform="capitalize">{key.replace(/_/g, ' ')}</Typography>
                        <Typography variant="body2" fontWeight={500} sx={{ color: healthColor(val) }}>{val}</Typography>
                      </Box>
                    </Stack>
                  </Grid>
                ))}
                <Grid item xs={6} sm={3}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <History sx={{ fontSize: 14, color: '#64748b' }} />
                    <Box>
                      <Typography variant="caption" color="text.secondary">Admin Actions (1h)</Typography>
                      <Typography variant="body2" fontWeight={500}>{health.checks?.admin_actions_last_hour ?? '—'}</Typography>
                    </Box>
                  </Stack>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </>
      )}
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 1 — USER MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════

function UsersTab({ onAdminError }) {
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [tierFilter, setTierFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedUser, setSelectedUser] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [subTier, setSubTier] = useState('');
  const [actionLoading, setActionLoading] = useState('');
  const [banReason, setBanReason] = useState('Violation of terms of service');
  const [banDialogOpen, setBanDialogOpen] = useState(false);
  const [giftDialogOpen, setGiftDialogOpen] = useState(false);
  const [giftTier, setGiftTier] = useState('pro');
  const [giftDays, setGiftDays] = useState(30);
  const [giftNote, setGiftNote] = useState('');

  const fetchUsers = useCallback(async (p = 1, s = '', tier = '', status = '') => {
    setLoading(true);
    try {
      const res = await admin.getUsers({ page: p, per_page: 20, search: s, tier, status });
      setUsers(res.data.users);
      setTotal(res.data.total);
      setPages(res.data.pages);
    } catch (err) {
      onAdminError(err, 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, [onAdminError]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const refresh = () => fetchUsers(page, search, tierFilter, statusFilter);

  const exportUsersCSV = async () => {
    try {
      const res = await admin.getUsers({ page: 1, per_page: 9999, search, tier: tierFilter, status: statusFilter });
      const all = res.data.users || [];
      const headers = ['Name', 'Email', 'User ID', 'Plan', 'Email Verified', 'Status', 'Joined'];
      const rows = all.map(u => [
        u.full_name || '',
        u.email || '',
        u.id || '',
        u.subscription_tier || '',
        u.email_verified ? 'Yes' : 'No',
        u.is_banned ? 'Banned' : u.is_suspicious ? 'Suspicious' : 'Active',
        u.created_at ? new Date(u.created_at).toLocaleDateString() : '',
      ]);
      const csv = [headers, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'users.csv'; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Export failed'); }
  };

  const openDetail = async (user) => {
    try {
      const res = await admin.getUser(user.id);
      setSelectedUser(res.data.user);
      setSubTier(res.data.user.subscription_tier);
      setDetailOpen(true);
    } catch {
      toast.error('Failed to load user details');
    }
  };

  const handleUpdateSub = async () => {
    setActionLoading('sub');
    try {
      await admin.updateSubscription(selectedUser.id, { tier: subTier });
      toast.success('Subscription updated');
      setDetailOpen(false);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to update subscription');
    } finally { setActionLoading(''); }
  };

  const handleBan = async () => {
    setActionLoading('ban');
    try {
      await admin.banUser(selectedUser.id, { reason: banReason });
      toast.success('User banned');
      setBanDialogOpen(false);
      setDetailOpen(false);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to ban user');
    } finally { setActionLoading(''); }
  };

  const handleUnban = async () => {
    setActionLoading('unban');
    try {
      await admin.unbanUser(selectedUser.id);
      toast.success('User unbanned');
      setDetailOpen(false);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to unban user');
    } finally { setActionLoading(''); }
  };

  const handleGiftSubscription = async () => {
    setActionLoading('gift');
    try {
      await admin.giftSubscription(selectedUser.id, { tier: giftTier, duration_days: giftDays, note: giftNote });
      toast.success(`🎁 Gifted ${giftTier} for ${giftDays} days to ${selectedUser.email}`);
      setGiftDialogOpen(false);
      setDetailOpen(false);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to gift subscription');
    } finally { setActionLoading(''); }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Permanently delete ${selectedUser.email}? This cannot be undone.`)) return;
    setActionLoading('del');
    try {
      await admin.deleteUser(selectedUser.id);
      toast.success('User deleted');
      setDetailOpen(false);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to delete user');
    } finally { setActionLoading(''); }
  };

  return (
    <Box>
      {/* Filters row */}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} mb={1.5} alignItems={{ sm: 'center' }}>
        <TextField
          size="small" placeholder="Search email or name…" value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); fetchUsers(1, e.target.value, tierFilter, statusFilter); }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1 }}
        />
        <Typography variant="body2" color="text.secondary" whiteSpace="nowrap">
          {total.toLocaleString()} users
        </Typography>
        <Button size="small" variant="outlined" startIcon={<FileDownload />} onClick={exportUsersCSV}>
          Export CSV
        </Button>
      </Stack>

      {/* Tier filter chips */}
      <Stack direction="row" spacing={0.75} mb={0.75} flexWrap="wrap" useFlexGap>
        <Typography variant="caption" color="text.secondary" alignSelf="center" mr={0.5}>Tier:</Typography>
        {[['', 'All'], ['free', 'Free'], ['pro', 'Pro'], ['enterprise', 'Enterprise']].map(([val, label]) => (
          <Chip key={val} label={label} size="small"
            color={tierFilter === val ? (val === 'enterprise' ? 'secondary' : 'primary') : 'default'}
            variant={tierFilter === val ? 'filled' : 'outlined'}
            onClick={() => { setTierFilter(val); setPage(1); fetchUsers(1, search, val, statusFilter); }}
          />
        ))}
      </Stack>

      {/* Status filter chips */}
      <Stack direction="row" spacing={0.75} mb={2} flexWrap="wrap" useFlexGap>
        <Typography variant="caption" color="text.secondary" alignSelf="center" mr={0.5}>Status:</Typography>
        {[['', 'All'], ['active', 'Active'], ['banned', 'Banned'], ['suspicious', 'Suspicious']].map(([val, label]) => (
          <Chip key={val} label={label} size="small"
            color={statusFilter === val ? (val === 'banned' ? 'error' : val === 'suspicious' ? 'warning' : val === 'active' ? 'success' : 'primary') : 'default'}
            variant={statusFilter === val ? 'filled' : 'outlined'}
            onClick={() => { setStatusFilter(val); setPage(1); fetchUsers(1, search, tierFilter, val); }}
          />
        ))}
      </Stack>

      {loading ? (
        <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box>
      ) : (
        <>
          <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2, overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>User</TableCell>
                  <TableCell>Plan</TableCell>
                  <TableCell>Verified</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Joined</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {users.length === 0 ? <EmptyRow cols={6} /> : users.map((u) => (
                  <TableRow key={u.id} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight={500}>{u.full_name || '—'}</Typography>
                      <Typography variant="caption" color="text.secondary">{u.email}</Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={u.subscription_tier?.toUpperCase()}
                        size="small"
                        color={u.subscription_tier === 'enterprise' ? 'secondary' : u.subscription_tier === 'pro' ? 'primary' : 'default'}
                      />
                    </TableCell>
                    <TableCell>
                      {u.email_verified
                        ? <CheckCircleOutline color="success" fontSize="small" />
                        : <Cancel color="disabled" fontSize="small" />}
                    </TableCell>
                    <TableCell>
                      {u.is_banned
                        ? <Chip label="Banned" color="error" size="small" />
                        : u.is_suspicious
                          ? <Chip label="Suspicious" color="warning" size="small" />
                          : <Chip label="Active" color="success" size="small" />}
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">{fmtDate(u.created_at)}</Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" onClick={() => openDetail(u)}>Details</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {pages > 1 && (
            <Box display="flex" justifyContent="center">
              <Pagination count={pages} page={page} onChange={(_, p) => { setPage(p); fetchUsers(p, search, tierFilter, statusFilter); }} color="primary" />
            </Box>
          )}
        </>
      )}

      {/* User detail dialog */}
      <Dialog open={detailOpen} onClose={() => setDetailOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ pb: 1 }}>
          <Typography fontWeight={700}>{selectedUser?.full_name || selectedUser?.email}</Typography>
          <Typography variant="caption" color="text.secondary">ID: {selectedUser?.id} · Joined {fmtDate(selectedUser?.created_at)}</Typography>
        </DialogTitle>
        <DialogContent>
          {selectedUser && (
            <Box>
              <Grid container spacing={1.5} mb={2}>
                <Grid item xs={6}><Typography variant="caption" color="text.secondary">Email</Typography><Typography variant="body2">{selectedUser.email}</Typography></Grid>
                <Grid item xs={6}><Typography variant="caption" color="text.secondary">Bots</Typography><Typography variant="body2">{selectedUser.bots?.length ?? 0}</Typography></Grid>
                <Grid item xs={6}><Typography variant="caption" color="text.secondary">Telegram</Typography><Typography variant="body2">{selectedUser.telegram_username ? `@${selectedUser.telegram_username}` : '—'}</Typography></Grid>
                <Grid item xs={6}><Typography variant="caption" color="text.secondary">2FA</Typography><Typography variant="body2">{selectedUser.totp_enabled ? 'Enabled' : 'Disabled'}</Typography></Grid>
              </Grid>

              {selectedUser.is_banned && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  <Typography variant="body2" fontWeight={600}>Banned</Typography>
                  <Typography variant="caption">{selectedUser.ban_reason}</Typography>
                </Alert>
              )}

              {/* Recent payments */}
              {selectedUser.recent_payments?.length > 0 && (
                <Box mb={2}>
                  <Typography variant="caption" color="text.secondary" fontWeight={600} textTransform="uppercase">Recent Payments</Typography>
                  {selectedUser.recent_payments.slice(0, 3).map((p) => (
                    <Stack key={p.id} direction="row" justifyContent="space-between" py={0.5} borderBottom="1px solid" borderColor="divider">
                      <Typography variant="caption">{p.plan?.toUpperCase()} · {p.provider}</Typography>
                      <Typography variant="caption" fontWeight={600} color="success.main">{usd((p.amount_usd || 0) / 100)}</Typography>
                      <Typography variant="caption" color="text.disabled">{fmtDate(p.created_at)}</Typography>
                    </Stack>
                  ))}
                </Box>
              )}

              <FormControl fullWidth sx={{ mb: 2 }} size="small">
                <InputLabel>Subscription Tier</InputLabel>
                <Select value={subTier} label="Subscription Tier" onChange={(e) => setSubTier(e.target.value)}>
                  <MenuItem value="free">Free</MenuItem>
                  <MenuItem value="pro">Pro</MenuItem>
                  <MenuItem value="enterprise">Enterprise</MenuItem>
                </Select>
              </FormControl>
              <Button variant="outlined" fullWidth onClick={handleUpdateSub} disabled={actionLoading === 'sub'} sx={{ mb: 1 }}>
                {actionLoading === 'sub' ? <CircularProgress size={18} /> : 'Update Subscription'}
              </Button>
              <Button variant="contained" color="success" fullWidth onClick={() => setGiftDialogOpen(true)} disabled={!!actionLoading} sx={{ mb: 2 }}>
                🎁 Gift Free Subscription
              </Button>

              <Grid container spacing={1}>
                {selectedUser.is_banned ? (
                  <Grid item xs={6}>
                    <Button fullWidth variant="outlined" color="success" startIcon={<CheckCircle />} onClick={handleUnban} disabled={!!actionLoading}>
                      {actionLoading === 'unban' ? <CircularProgress size={18} /> : 'Unban'}
                    </Button>
                  </Grid>
                ) : (
                  <Grid item xs={6}>
                    <Button fullWidth variant="outlined" color="warning" startIcon={<Block />} onClick={() => setBanDialogOpen(true)} disabled={!!actionLoading}>
                      Ban
                    </Button>
                  </Grid>
                )}
                <Grid item xs={6}>
                  <Button fullWidth variant="outlined" color="error" startIcon={<Delete />} onClick={handleDelete} disabled={!!actionLoading}>
                    {actionLoading === 'del' ? <CircularProgress size={18} /> : 'Delete'}
                  </Button>
                </Grid>
              </Grid>
            </Box>
          )}
        </DialogContent>
        <DialogActions><Button onClick={() => setDetailOpen(false)}>Close</Button></DialogActions>
      </Dialog>

      {/* Gift subscription dialog */}
      <Dialog open={giftDialogOpen} onClose={() => setGiftDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>🎁 Gift Subscription — {selectedUser?.email}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} pt={1}>
            <FormControl fullWidth size="small">
              <InputLabel>Plan</InputLabel>
              <Select value={giftTier} label="Plan" onChange={e => setGiftTier(e.target.value)}>
                <MenuItem value="pro">Pro</MenuItem>
                <MenuItem value="enterprise">Enterprise</MenuItem>
              </Select>
            </FormControl>
            <TextField
              size="small" label="Duration (days)" type="number"
              value={giftDays} onChange={e => setGiftDays(Number(e.target.value))}
              inputProps={{ min: 1, max: 3650 }}
            />
            <TextField
              size="small" label="Note (internal)" value={giftNote}
              onChange={e => setGiftNote(e.target.value)}
              placeholder="e.g. KOL partnership, support goodwill…"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGiftDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" color="success" onClick={handleGiftSubscription} disabled={actionLoading === 'gift'}>
            {actionLoading === 'gift' ? <CircularProgress size={16} /> : `Gift ${giftDays} days`}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Ban reason dialog */}
      <Dialog open={banDialogOpen} onClose={() => setBanDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Ban {selectedUser?.email}</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth multiline rows={2} label="Reason" value={banReason}
            onChange={(e) => setBanReason(e.target.value)} sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBanDialogOpen(false)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={handleBan} disabled={actionLoading === 'ban'}>
            {actionLoading === 'ban' ? <CircularProgress size={18} /> : 'Confirm Ban'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 2 — TELEGRAM GROUPS
// ═══════════════════════════════════════════════════════════════════════════════

function TelegramGroupsTab({ onAdminError }) {
  const [groups, setGroups] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async (p = 1, s = '', st = '') => {
    setLoading(true);
    try {
      const res = await admin.getTelegramGroups({ page: p, per_page: 20, search: s, status: st });
      setGroups(res.data.groups || []);
      setTotal(res.data.total || 0);
    } catch (err) { onAdminError(err, 'Failed to load groups'); }
    finally { setLoading(false); }
  }, [onAdminError]);

  useEffect(() => { fetch(); }, [fetch]);

  const handleDisable = async (g) => {
    if (!window.confirm(`Disable group "${g.title}"?`)) return;
    try { await admin.disableTelegramGroup(g.telegram_group_id); toast.success('Group disabled'); fetch(page, search, statusFilter); }
    catch { toast.error('Failed to disable group'); }
  };

  const handleUnlink = async (g) => {
    if (!window.confirm(`Unlink group "${g.title}" from its owner?`)) return;
    try { await admin.unlinkTelegramGroup(g.telegram_group_id); toast.success('Group unlinked'); fetch(page, search, statusFilter); }
    catch { toast.error('Failed to unlink group'); }
  };

  const pages = Math.ceil(total / 20);

  return (
    <Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} mb={2}>
        <TextField
          size="small" placeholder="Search title or group ID…" value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); fetch(1, e.target.value, statusFilter); }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1 }}
        />
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel>Status</InputLabel>
          <Select value={statusFilter} label="Status" onChange={(e) => { setStatusFilter(e.target.value); setPage(1); fetch(1, search, e.target.value); }}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="active">Active</MenuItem>
            <MenuItem value="pending">Pending</MenuItem>
            <MenuItem value="removed">Removed</MenuItem>
            <MenuItem value="disabled">Disabled</MenuItem>
          </Select>
        </FormControl>
        <Typography variant="body2" color="text.secondary" alignSelf="center" whiteSpace="nowrap">{total.toLocaleString()} groups</Typography>
      </Stack>

      {loading ? <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box> : (
        <>
          <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2, overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Group</TableCell>
                  <TableCell>Owner</TableCell>
                  <TableCell>Bot Type</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Cmds</TableCell>
                  <TableCell>Linked</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {groups.length === 0 ? <EmptyRow cols={7} /> : groups.map((g) => (
                  <TableRow key={g.telegram_group_id} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight={500}>{g.title}</Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>{g.telegram_group_id}</Typography>
                    </TableCell>
                    <TableCell><Typography variant="body2">{g.owner_email || '—'}</Typography></TableCell>
                    <TableCell>
                      <Chip label={g.linked_via_bot_type} size="small" color={g.linked_via_bot_type === 'official' ? 'success' : 'primary'} variant="outlined" />
                    </TableCell>
                    <TableCell><StatusChip label={g.bot_status} /></TableCell>
                    <TableCell>{g.command_count}</TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">{fmtDate(g.linked_at)}</Typography></TableCell>
                    <TableCell align="right">
                      <Tooltip title="Unlink from owner">
                        <IconButton size="small" color="warning" onClick={() => handleUnlink(g)}><LinkOff fontSize="small" /></IconButton>
                      </Tooltip>
                      <Tooltip title="Disable group">
                        <IconButton size="small" color="error" onClick={() => handleDisable(g)}><Block fontSize="small" /></IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {pages > 1 && <Box display="flex" justifyContent="center"><Pagination count={pages} page={page} onChange={(_, p) => { setPage(p); fetch(p, search, statusFilter); }} color="primary" /></Box>}
        </>
      )}
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 3 — CUSTOM BOTS
// ═══════════════════════════════════════════════════════════════════════════════

function CustomBotsTab({ onAdminError }) {
  const [bots, setBots] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      const res = await admin.getCustomBots({ page: p, per_page: 20 });
      setBots(res.data.bots || []);
      setTotal(res.data.total || 0);
    } catch (err) { onAdminError(err, 'Failed to load custom bots'); }
    finally { setLoading(false); }
  }, [onAdminError]);

  useEffect(() => { fetch(); }, [fetch]);

  const handleDisable = async (bot) => {
    if (!window.confirm(`Disable bot "${bot.bot_username || bot.id}"?`)) return;
    try { await admin.disableCustomBot(bot.id); toast.success('Bot disabled'); fetch(page); }
    catch { toast.error('Failed to disable bot'); }
  };

  const pages = Math.ceil(total / 20);

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" mb={2}>{total.toLocaleString()} custom bots</Typography>
      {loading ? <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box> : (
        <>
          <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2, overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Bot</TableCell>
                  <TableCell>Owner</TableCell>
                  <TableCell>Tier</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Created</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {bots.length === 0 ? <EmptyRow cols={6} /> : bots.map((b) => (
                  <TableRow key={b.id} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight={500}>{b.bot_username ? `@${b.bot_username}` : `Bot #${b.id}`}</Typography>
                      <Typography variant="caption" color="text.secondary">{b.bot_name}</Typography>
                    </TableCell>
                    <TableCell><Typography variant="body2">{b.owner_email || '—'}</Typography></TableCell>
                    <TableCell>
                      <Chip label={(b.owner_tier || 'free').toUpperCase()} size="small"
                        color={b.owner_tier === 'enterprise' ? 'secondary' : b.owner_tier === 'pro' ? 'primary' : 'default'} />
                    </TableCell>
                    <TableCell><StatusChip label={b.status || 'active'} /></TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">{fmtDate(b.created_at)}</Typography></TableCell>
                    <TableCell align="right">
                      <Button size="small" color="error" startIcon={<Block fontSize="small" />} onClick={() => handleDisable(b)}>
                        Disable
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {pages > 1 && <Box display="flex" justifyContent="center"><Pagination count={pages} page={page} onChange={(_, p) => { setPage(p); fetch(p); }} color="primary" /></Box>}
        </>
      )}
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 4 — SUSPICIOUS ACTIVITY
// ═══════════════════════════════════════════════════════════════════════════════

function SuspiciousEventsView({ onAdminError }) {
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [reviewed, setReviewed] = useState('false');
  const [loading, setLoading] = useState(false);

  const fetchEvents = useCallback(async (p = 1, r = 'false') => {
    setLoading(true);
    try {
      const res = await admin.getSuspicious({ page: p, per_page: 20, reviewed: r });
      setEvents(res.data.events || []);
      setTotal(res.data.total || 0);
    } catch (err) { onAdminError(err, 'Failed to load suspicious activity'); }
    finally { setLoading(false); }
  }, [onAdminError]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  const handleDismiss = async (id) => {
    try { await admin.dismissSuspicious(id); toast.success('Event dismissed'); fetchEvents(page, reviewed); }
    catch { toast.error('Failed to dismiss event'); }
  };

  const pages = Math.ceil(total / 20);

  return (
    <Box>
      <Stack direction="row" spacing={1.5} mb={2} alignItems="center">
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>Review Status</InputLabel>
          <Select value={reviewed} label="Review Status" onChange={(e) => { setReviewed(e.target.value); setPage(1); fetchEvents(1, e.target.value); }}>
            <MenuItem value="false">Unreviewed</MenuItem>
            <MenuItem value="true">Reviewed</MenuItem>
            <MenuItem value="">All</MenuItem>
          </Select>
        </FormControl>
        <Typography variant="body2" color="text.secondary">{total.toLocaleString()} events</Typography>
      </Stack>
      {loading ? <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box> : (
        <>
          <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2, overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Type</TableCell><TableCell>User</TableCell><TableCell>IP Hash</TableCell>
                  <TableCell>Device Hash</TableCell><TableCell>Reason</TableCell><TableCell>Time</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {events.length === 0 ? <EmptyRow cols={7} message="No unreviewed suspicious activity" /> : events.map((e) => (
                  <TableRow key={e.id} hover>
                    <TableCell><Chip label={e.event_type} size="small" color="warning" variant="outlined" /></TableCell>
                    <TableCell><Typography variant="caption">{e.user_email || `UID:${e.user_id}` || '—'}</Typography></TableCell>
                    <TableCell><Typography variant="caption" sx={{ fontFamily: 'monospace' }}>{e.ip_hash_prefix || '—'}</Typography></TableCell>
                    <TableCell><Typography variant="caption" sx={{ fontFamily: 'monospace' }}>{e.device_hash_prefix || '—'}</Typography></TableCell>
                    <TableCell><Typography variant="caption">{e.reason}</Typography></TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">{fmtDateTime(e.created_at)}</Typography></TableCell>
                    <TableCell align="right">
                      {!e.reviewed && (
                        <Button size="small" color="success" startIcon={<CheckCircle fontSize="small" />} onClick={() => handleDismiss(e.id)}>
                          Dismiss
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {pages > 1 && <Box display="flex" justifyContent="center"><Pagination count={pages} page={page} onChange={(_, p) => { setPage(p); fetchEvents(p, reviewed); }} color="primary" /></Box>}
        </>
      )}
    </Box>
  );
}

function FraudClustersView({ onAdminError }) {
  const [clusters, setClusters] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    admin.getFraudClusters()
      .then(r => setClusters(r.data.clusters || []))
      .catch(err => onAdminError(err, 'Failed to load clusters'))
      .finally(() => setLoading(false));
  }, [onAdminError]);

  if (loading) return <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box>;

  return (
    <Box>
      <Alert severity="warning" sx={{ mb: 2 }}>
        These IP/device hashes are shared by 2+ different user accounts — possible multi-accounting.
      </Alert>
      {clusters.length === 0 ? (
        <Alert severity="success">No multi-account clusters detected.</Alert>
      ) : clusters.map((c, i) => (
        <Card key={i} sx={{ mb: 1.5, borderLeft: '4px solid #f59e0b' }}>
          <CardContent sx={{ pb: '12px !important' }}>
            <Stack direction="row" spacing={1} alignItems="center" mb={1}>
              <AccountTree sx={{ fontSize: 18, color: '#f59e0b' }} />
              <Chip label={c.type === 'ip_hash' ? 'Shared IP' : 'Shared Device'} size="small" color="warning" />
              <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>{c.hash_prefix}…</Typography>
              <Chip label={`${c.user_count} accounts`} size="small" color="error" />
            </Stack>
            <Stack direction="row" flexWrap="wrap" gap={1}>
              {(c.users || []).map(u => (
                <Chip
                  key={u.id}
                  label={`${u.email} (${u.tier})`}
                  size="small"
                  color={u.banned ? 'error' : 'default'}
                  variant="outlined"
                />
              ))}
            </Stack>
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}

function ReferralFarmingView({ onAdminError }) {
  const [suspects, setSuspects] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    admin.getFraudReferralFarming()
      .then(r => setSuspects(r.data.suspects || []))
      .catch(err => onAdminError(err, 'Failed to load referral farming data'))
      .finally(() => setLoading(false));
  }, [onAdminError]);

  if (loading) return <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box>;

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 2 }}>
        Users with 3+ referrals — sorted by risk score (suspicious referrals × 3 + suspicious events).
      </Alert>
      {suspects.length === 0 ? (
        <Alert severity="success">No referral farming suspects detected.</Alert>
      ) : (
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Email</TableCell><TableCell>Tier</TableCell><TableCell>Total Referrals</TableCell>
                <TableCell>Suspicious Referrals</TableCell><TableCell>Suspicious Events</TableCell>
                <TableCell>Risk Score</TableCell><TableCell>Banned</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {suspects.map(s => (
                <TableRow key={s.referrer_id} hover>
                  <TableCell>{s.referrer_email}</TableCell>
                  <TableCell><Chip label={s.referrer_tier} size="small" /></TableCell>
                  <TableCell>{s.total_referrals}</TableCell>
                  <TableCell><Typography color={s.suspicious_referrals > 0 ? 'error' : 'text.primary'}>{s.suspicious_referrals}</Typography></TableCell>
                  <TableCell>{s.referrer_suspicious_events}</TableCell>
                  <TableCell>
                    <Chip
                      label={s.risk_score}
                      size="small"
                      color={s.risk_score >= 10 ? 'error' : s.risk_score >= 5 ? 'warning' : 'default'}
                    />
                  </TableCell>
                  <TableCell>{s.referrer_banned ? <Chip label="Banned" size="small" color="error" /> : '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}

function PaymentAnomaliesView({ onAdminError }) {
  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    admin.getFraudPaymentAnomalies()
      .then(r => setAnomalies(r.data.anomalies || []))
      .catch(err => onAdminError(err, 'Failed to load payment anomalies'))
      .finally(() => setLoading(false));
  }, [onAdminError]);

  if (loading) return <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box>;

  return (
    <Box>
      {anomalies.length === 0 ? (
        <Alert severity="success">No payment anomalies detected.</Alert>
      ) : (
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Type</TableCell><TableCell>User</TableCell><TableCell>Tier</TableCell>
                <TableCell>Detail</TableCell><TableCell>Risk</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {anomalies.map((a, i) => (
                <TableRow key={i} hover>
                  <TableCell><Chip label={a.type.replace(/_/g, ' ')} size="small" color="warning" variant="outlined" /></TableCell>
                  <TableCell><Typography variant="caption">{a.user_email || `UID:${a.user_id}`}</Typography></TableCell>
                  <TableCell><Chip label={a.user_tier || '?'} size="small" /></TableCell>
                  <TableCell>
                    <Typography variant="caption">
                      {a.type === 'multiple_payments_same_day'
                        ? `${a.payment_count} payments on ${a.date}`
                        : `$${((a.amount_usd || 0) / 100).toFixed(2)} via ${a.provider} on ${fmtDate(a.date)}`}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip label={a.risk} size="small" color={a.risk === 'high' ? 'error' : 'warning'} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}

function ChargebacksView({ onAdminError }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await admin.getFraudChargebacks();
      setRows(res.data.chargebacks || []);
    } catch (err) { onAdminError(err, 'Failed to load chargebacks'); }
    finally { setLoading(false); }
  }, [onAdminError]);

  useEffect(() => { load(); }, [load]);

  const handleRecord = async (userId) => {
    try {
      await admin.recordChargeback(userId);
      toast.success('Chargeback recorded');
      load();
    } catch { toast.error('Failed to record chargeback'); }
  };

  if (loading) return <Box display="flex" justifyContent="center" mt={3}><CircularProgress /></Box>;

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Users with recorded payment chargebacks. Use "Record" when you receive a chargeback notification from your payment processor.
      </Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>User</TableCell>
              <TableCell>Plan</TableCell>
              <TableCell align="center">Chargebacks</TableCell>
              <TableCell>Joined</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 && <EmptyRow cols={6} message="No chargebacks recorded" />}
            {rows.map(r => (
              <TableRow key={r.id} hover>
                <TableCell>
                  <Typography variant="body2" fontWeight={600}>{r.full_name}</Typography>
                  <Typography variant="caption" color="text.secondary">{r.email}</Typography>
                </TableCell>
                <TableCell><Chip label={r.tier} size="small" color={r.tier === 'pro' ? 'primary' : r.tier === 'enterprise' ? 'secondary' : 'default'} /></TableCell>
                <TableCell align="center">
                  <Chip label={r.chargeback_count} size="small" color={r.chargeback_count >= 3 ? 'error' : 'warning'} />
                </TableCell>
                <TableCell><Typography variant="caption">{fmtDate(r.created_at)}</Typography></TableCell>
                <TableCell>
                  {r.is_banned && <Chip label="Banned" size="small" color="error" sx={{ mr: 0.5 }} />}
                  {r.is_suspended && <Chip label="Suspended" size="small" color="warning" />}
                  {!r.is_banned && !r.is_suspended && <Chip label="Active" size="small" color="success" />}
                </TableCell>
                <TableCell>
                  <Button size="small" variant="outlined" color="warning" onClick={() => handleRecord(r.id)}>
                    +1 Chargeback
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

const FRAUD_VIEWS = [
  { key: 'events', label: 'Suspicious Events', icon: <Warning fontSize="small" /> },
  { key: 'clusters', label: 'Multi-Account Clusters', icon: <AccountTree fontSize="small" /> },
  { key: 'farming', label: 'Referral Farming', icon: <People fontSize="small" /> },
  { key: 'payments', label: 'Payment Anomalies', icon: <Payment fontSize="small" /> },
  { key: 'chargebacks', label: 'Chargebacks', icon: <TrendingDown fontSize="small" /> },
];

function SuspiciousTab({ onAdminError }) {
  const [subView, setSubView] = useState('events');

  return (
    <Box>
      <Stack direction="row" spacing={1} mb={2} flexWrap="wrap">
        {FRAUD_VIEWS.map(v => (
          <Button
            key={v.key}
            size="small"
            variant={subView === v.key ? 'contained' : 'outlined'}
            startIcon={v.icon}
            onClick={() => setSubView(v.key)}
            sx={{ borderRadius: 2 }}
          >
            {v.label}
          </Button>
        ))}
      </Stack>
      {subView === 'events' && <SuspiciousEventsView onAdminError={onAdminError} />}
      {subView === 'clusters' && <FraudClustersView onAdminError={onAdminError} />}
      {subView === 'farming' && <ReferralFarmingView onAdminError={onAdminError} />}
      {subView === 'payments' && <PaymentAnomaliesView onAdminError={onAdminError} />}
      {subView === 'chargebacks' && <ChargebacksView onAdminError={onAdminError} />}
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 5 — REFERRALS
// ═══════════════════════════════════════════════════════════════════════════════

function ReferralsTab({ onAdminError }) {
  const [referrals, setReferrals] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async (p = 1, s = '') => {
    setLoading(true);
    try {
      const res = await admin.getReferrals({ page: p, per_page: 20, status: s });
      setReferrals(res.data.referrals || []);
      setTotal(res.data.total || 0);
    } catch (err) { onAdminError(err, 'Failed to load referrals'); }
    finally { setLoading(false); }
  }, [onAdminError]);

  useEffect(() => { fetch(); }, [fetch]);

  const handleStatus = async (id, status) => {
    try { await admin.updateReferralStatus(id, { status }); toast.success(`Marked as ${status}`); fetch(page, statusFilter); }
    catch { toast.error('Failed to update referral'); }
  };

  const pages = Math.ceil(total / 20);

  return (
    <Box>
      <Stack direction="row" spacing={1.5} mb={2} alignItems="center">
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>Status</InputLabel>
          <Select value={statusFilter} label="Status" onChange={(e) => { setStatusFilter(e.target.value); setPage(1); fetch(1, e.target.value); }}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="pending">Pending</MenuItem>
            <MenuItem value="approved">Approved</MenuItem>
            <MenuItem value="suspicious">Suspicious</MenuItem>
            <MenuItem value="rejected">Rejected</MenuItem>
          </Select>
        </FormControl>
        <Typography variant="body2" color="text.secondary">{total.toLocaleString()} referrals</Typography>
      </Stack>

      {loading ? <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box> : (
        <>
          <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2, overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Referrer</TableCell>
                  <TableCell>Referred</TableCell>
                  <TableCell>Verified</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Date</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {referrals.length === 0 ? <EmptyRow cols={6} /> : referrals.map((r) => (
                  <TableRow key={r.id} hover>
                    <TableCell><Typography variant="caption">{r.referrer_email || '—'}</Typography></TableCell>
                    <TableCell><Typography variant="caption">{r.referred_email || '—'}</Typography></TableCell>
                    <TableCell>
                      {r.referred_email_verified
                        ? <CheckCircleOutline color="success" fontSize="small" />
                        : <Cancel color="disabled" fontSize="small" />}
                    </TableCell>
                    <TableCell><StatusChip label={r.status} /></TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">{fmtDate(r.created_at)}</Typography></TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                        {r.status !== 'approved' && (
                          <Button size="small" color="success" onClick={() => handleStatus(r.id, 'approved')}>Approve</Button>
                        )}
                        {r.status !== 'suspicious' && (
                          <Button size="small" color="warning" onClick={() => handleStatus(r.id, 'suspicious')}>Flag</Button>
                        )}
                        {r.status !== 'rejected' && (
                          <Button size="small" color="error" onClick={() => handleStatus(r.id, 'rejected')}>Reject</Button>
                        )}
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {pages > 1 && <Box display="flex" justifyContent="center"><Pagination count={pages} page={page} onChange={(_, p) => { setPage(p); fetch(p, statusFilter); }} color="primary" /></Box>}
        </>
      )}
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 6 — DIRECTORY MODERATION
// ═══════════════════════════════════════════════════════════════════════════════

function DirectoryTab({ onAdminError }) {
  const [listings, setListings] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('pending');
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async (p = 1, s = 'pending') => {
    setLoading(true);
    try {
      const res = await admin.getDirectory({ page: p, per_page: 20, status: s });
      setListings(res.data.listings || []);
      setTotal(res.data.total || 0);
    } catch (err) { onAdminError(err, 'Failed to load directory listings'); }
    finally { setLoading(false); }
  }, [onAdminError]);

  useEffect(() => { fetch(); }, [fetch]);

  const handleModerate = async (id, action) => {
    try {
      await admin.moderateDirectory(id, { action });
      toast.success(`Listing ${action}d`);
      fetch(page, statusFilter);
    } catch { toast.error(`Failed to ${action} listing`); }
  };

  const pages = Math.ceil(total / 20);

  return (
    <Box>
      <Stack direction="row" spacing={1.5} mb={2} alignItems="center">
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>Status</InputLabel>
          <Select value={statusFilter} label="Status" onChange={(e) => { setStatusFilter(e.target.value); setPage(1); fetch(1, e.target.value); }}>
            <MenuItem value="pending">Pending</MenuItem>
            <MenuItem value="approved">Approved</MenuItem>
            <MenuItem value="rejected">Rejected</MenuItem>
            <MenuItem value="">All</MenuItem>
          </Select>
        </FormControl>
        <Typography variant="body2" color="text.secondary">{total.toLocaleString()} listings</Typography>
      </Stack>

      {loading ? <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box> : (
        <>
          <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2, overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Bot Name</TableCell>
                  <TableCell>Category</TableCell>
                  <TableCell>Description</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Submitted</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {listings.length === 0 ? <EmptyRow cols={6} message="No listings in this status" /> : listings.map((l) => (
                  <TableRow key={l.id} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight={500}>{l.bot_name || l.name}</Typography>
                      <Typography variant="caption" color="text.secondary">{l.contact_email}</Typography>
                    </TableCell>
                    <TableCell><Chip label={l.category || '—'} size="small" variant="outlined" /></TableCell>
                    <TableCell sx={{ maxWidth: 200 }}>
                      <Typography variant="caption" sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {l.description || '—'}
                      </Typography>
                    </TableCell>
                    <TableCell><StatusChip label={l.moderation_status} /></TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">{fmtDate(l.created_at)}</Typography></TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                        {l.moderation_status !== 'approved' && (
                          <Button size="small" color="success" onClick={() => handleModerate(l.id, 'approve')}>Approve</Button>
                        )}
                        {l.moderation_status !== 'rejected' && (
                          <Button size="small" color="error" onClick={() => handleModerate(l.id, 'reject')}>Reject</Button>
                        )}
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {pages > 1 && <Box display="flex" justifyContent="center"><Pagination count={pages} page={page} onChange={(_, p) => { setPage(p); fetch(p, statusFilter); }} color="primary" /></Box>}
        </>
      )}
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 7 — ANNOUNCEMENTS
// ═══════════════════════════════════════════════════════════════════════════════

function AnnouncementsTab({ onAdminError }) {
  const [announcements, setAnnouncements] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [form, setForm] = useState({
    title: '', body: '', audience: 'all', channel: 'inapp', announcement_type: 'info',
  });

  const fetch = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      const res = await admin.getAnnouncements({ page: p, per_page: 20 });
      setAnnouncements(res.data.announcements || []);
      setTotal(res.data.total || 0);
    } catch (err) { onAdminError(err, 'Failed to load announcements'); }
    finally { setLoading(false); }
  }, [onAdminError]);

  useEffect(() => { fetch(); }, [fetch]);

  const handleSend = async () => {
    if (!form.title.trim() || !form.body.trim()) { toast.error('Title and body are required'); return; }
    setSending(true);
    try {
      const res = await admin.createAnnouncement(form);
      toast.success(res.data.message || 'Announcement sent');
      setComposeOpen(false);
      setForm({ title: '', body: '', audience: 'all', channel: 'inapp', announcement_type: 'info' });
      fetch(1);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to send announcement');
    } finally { setSending(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this announcement?')) return;
    try { await admin.deleteAnnouncement(id); toast.success('Deleted'); fetch(page); }
    catch { toast.error('Failed to delete'); }
  };

  const pages = Math.ceil(total / 20);

  const typeColor = { info: 'info', warning: 'warning', critical: 'error', security: 'error' };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="body2" color="text.secondary">{total} announcements sent</Typography>
        <Button variant="contained" startIcon={<Campaign />} onClick={() => setComposeOpen(true)}>
          New Announcement
        </Button>
      </Stack>

      {loading ? <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box> : (
        <>
          {announcements.length === 0 ? (
            <Alert severity="info">No announcements yet. Click "New Announcement" to send your first one.</Alert>
          ) : (
            announcements.map((a) => (
              <Card key={a.id} sx={{ mb: 1.5, borderLeft: '4px solid', borderLeftColor: `${typeColor[a.announcement_type]}.main` }}>
                <CardContent sx={{ pb: '12px !important' }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                    <Box flex={1} mr={2}>
                      <Stack direction="row" spacing={1} alignItems="center" mb={0.5}>
                        <Chip label={a.announcement_type} size="small" color={typeColor[a.announcement_type]} />
                        <Chip label={a.audience} size="small" variant="outlined" />
                        <Chip label={a.channel} size="small" variant="outlined" />
                        {a.sent && <Chip label={`${a.delivered_count} delivered`} size="small" color="success" variant="outlined" />}
                      </Stack>
                      <Typography variant="subtitle2" fontWeight={600}>{a.title}</Typography>
                      <Typography variant="body2" color="text.secondary" mt={0.5}
                        sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {a.body}
                      </Typography>
                      <Typography variant="caption" color="text.disabled" mt={0.5} display="block">
                        Sent {fmtDateTime(a.sent_at || a.created_at)}
                      </Typography>
                    </Box>
                    <IconButton size="small" color="error" onClick={() => handleDelete(a.id)}><Delete fontSize="small" /></IconButton>
                  </Stack>
                </CardContent>
              </Card>
            ))
          )}
          {pages > 1 && <Box display="flex" justifyContent="center" mt={2}><Pagination count={pages} page={page} onChange={(_, p) => { setPage(p); fetch(p); }} color="primary" /></Box>}
        </>
      )}

      {/* Compose dialog */}
      <Dialog open={composeOpen} onClose={() => setComposeOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>New Announcement</DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1}>
            <TextField
              label="Title" fullWidth size="small" value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              inputProps={{ maxLength: 200 }}
              helperText={`${form.title.length}/200`}
            />
            <TextField
              label="Body" fullWidth multiline rows={4} value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
            />
            <Stack direction="row" spacing={1.5}>
              <FormControl size="small" fullWidth>
                <InputLabel>Audience</InputLabel>
                <Select value={form.audience} label="Audience" onChange={(e) => setForm({ ...form, audience: e.target.value })}>
                  <MenuItem value="all">All Users</MenuItem>
                  <MenuItem value="free">Free Users</MenuItem>
                  <MenuItem value="pro">Pro Users</MenuItem>
                  <MenuItem value="enterprise">Enterprise Users</MenuItem>
                  <MenuItem value="with_bots">Users with Bots</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" fullWidth>
                <InputLabel>Channel</InputLabel>
                <Select value={form.channel} label="Channel" onChange={(e) => setForm({ ...form, channel: e.target.value })}>
                  <MenuItem value="inapp">In-App Only</MenuItem>
                  <MenuItem value="email">Email Only</MenuItem>
                  <MenuItem value="both">In-App + Email</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" fullWidth>
                <InputLabel>Type</InputLabel>
                <Select value={form.announcement_type} label="Type" onChange={(e) => setForm({ ...form, announcement_type: e.target.value })}>
                  <MenuItem value="info">Info</MenuItem>
                  <MenuItem value="warning">Warning</MenuItem>
                  <MenuItem value="critical">Critical</MenuItem>
                  <MenuItem value="security">🔒 Urgent Security Notice</MenuItem>
                </Select>
              </FormControl>
            </Stack>
            {form.announcement_type === 'critical' && (
              <Alert severity="error">Critical announcements appear as a full-screen modal for all recipients on their next app load.</Alert>
            )}
            {form.announcement_type === 'security' && (
              <Alert severity="error" icon={<Security />}>
                Urgent Security Notices are delivered immediately to all users regardless of audience setting, with a red banner that persists until dismissed.
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setComposeOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleSend} disabled={sending} startIcon={sending ? <CircularProgress size={16} /> : <Campaign />}>
            Send Announcement
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 8 — AUDIT LOG
// ═══════════════════════════════════════════════════════════════════════════════

function AuditLogTab({ onAdminError }) {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [methodFilter, setMethodFilter] = useState('');
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async (p = 1, method = '') => {
    setLoading(true);
    try {
      const res = await admin.getAuditLogs({ page: p, per_page: 30, method });
      setLogs(res.data.logs || []);
      setTotal(res.data.total || 0);
    } catch (err) { onAdminError(err, 'Failed to load audit logs'); }
    finally { setLoading(false); }
  }, [onAdminError]);

  useEffect(() => { fetch(); }, [fetch]);

  const methodColor = { GET: 'default', POST: 'primary', PUT: 'warning', DELETE: 'error', PATCH: 'secondary' };
  const pages = Math.ceil(total / 30);

  return (
    <Box>
      <Stack direction="row" spacing={1.5} mb={2} alignItems="center">
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel>Method</InputLabel>
          <Select value={methodFilter} label="Method" onChange={(e) => { setMethodFilter(e.target.value); setPage(1); fetch(1, e.target.value); }}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="GET">GET</MenuItem>
            <MenuItem value="POST">POST</MenuItem>
            <MenuItem value="PUT">PUT</MenuItem>
            <MenuItem value="DELETE">DELETE</MenuItem>
          </Select>
        </FormControl>
        <Typography variant="body2" color="text.secondary">{total.toLocaleString()} log entries</Typography>
      </Stack>

      {loading ? <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box> : (
        <>
          <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2, overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Admin</TableCell>
                  <TableCell>Method</TableCell>
                  <TableCell>Path</TableCell>
                  <TableCell>IP</TableCell>
                  <TableCell>Time</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {logs.length === 0 ? <EmptyRow cols={5} /> : logs.map((l) => (
                  <TableRow key={l.id} hover>
                    <TableCell><Typography variant="caption">{l.admin_email}</Typography></TableCell>
                    <TableCell><Chip label={l.method} size="small" color={methodColor[l.method] || 'default'} /></TableCell>
                    <TableCell><Typography variant="caption" sx={{ fontFamily: 'monospace' }}>{l.path}</Typography></TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>{l.ip_address || '—'}</Typography></TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">{fmtDateTime(l.created_at)}</Typography></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {pages > 1 && <Box display="flex" justifyContent="center"><Pagination count={pages} page={page} onChange={(_, p) => { setPage(p); fetch(p, methodFilter); }} color="primary" /></Box>}
        </>
      )}
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 9 — REPORTED MESSAGES
// ═══════════════════════════════════════════════════════════════════════════════

function ReportsTab({ onAdminError }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState('open');
  const [sourceFilter, setSourceFilter] = useState('');

  const fetch = useCallback(async (p = 1, status = statusFilter, source = sourceFilter) => {
    setLoading(true);
    try {
      const res = await admin.getReports({ page: p, per_page: 50, status, source });
      setReports(res.data.reports || []);
      setPages(res.data.pages || 1);
    } catch (err) {
      onAdminError(err, 'Failed to load reports');
    } finally {
      setLoading(false);
    }
  }, [onAdminError, statusFilter, sourceFilter]);

  useEffect(() => { fetch(1, statusFilter, sourceFilter); }, [fetch, statusFilter, sourceFilter]);

  const handleResolve = async (source, id) => {
    try {
      await admin.resolveReport(source, id);
      toast.success('Report resolved');
      fetch(page, statusFilter, sourceFilter);
    } catch (err) {
      onAdminError(err, 'Failed to resolve report');
    }
  };

  return (
    <Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} mb={2} alignItems="center">
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Status</InputLabel>
          <Select value={statusFilter} label="Status" onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="open">Open</MenuItem>
            <MenuItem value="resolved">Resolved</MenuItem>
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>Source</InputLabel>
          <Select value={sourceFilter} label="Source" onChange={(e) => { setSourceFilter(e.target.value); setPage(1); }}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="custom">Custom Bot Groups</MenuItem>
            <MenuItem value="official">Official Bot Groups</MenuItem>
          </Select>
        </FormControl>
        <Button size="small" startIcon={<Refresh />} onClick={() => fetch(page, statusFilter, sourceFilter)}>Refresh</Button>
      </Stack>

      {loading ? (
        <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box>
      ) : (
        <>
          <TableContainer component={Paper}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Source</TableCell>
                  <TableCell>Group ID</TableCell>
                  <TableCell>Reporter</TableCell>
                  <TableCell>Reported User</TableCell>
                  <TableCell>Reason</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Date</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {reports.length === 0 ? (
                  <EmptyRow cols={8} message="No reports found" />
                ) : reports.map((r) => (
                  <TableRow key={`${r.source}-${r.id}`}>
                    <TableCell><Chip label={r.source} size="small" color={r.source === 'official' ? 'primary' : 'default'} /></TableCell>
                    <TableCell sx={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <Tooltip title={String(r.group_id || '')}><span>{r.group_name || r.group_id || '—'}</span></Tooltip>
                    </TableCell>
                    <TableCell>{r.reporter_user_id}</TableCell>
                    <TableCell>{r.reported_user_id}</TableCell>
                    <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <Tooltip title={r.reason || ''}><span>{r.reason || '—'}</span></Tooltip>
                    </TableCell>
                    <TableCell><StatusChip label={r.status} /></TableCell>
                    <TableCell>{fmtDateTime(r.created_at)}</TableCell>
                    <TableCell>
                      {r.status === 'open' && (
                        <Button size="small" variant="outlined" color="success" startIcon={<CheckCircleOutline />}
                          onClick={() => handleResolve(r.source, r.id)}>
                          Resolve
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {pages > 1 && (
            <Box display="flex" justifyContent="center" mt={2}>
              <Pagination count={pages} page={page} onChange={(_, p) => { setPage(p); fetch(p, statusFilter, sourceFilter); }} color="primary" />
            </Box>
          )}
        </>
      )}
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB — PROMO CODES
// ═══════════════════════════════════════════════════════════════════════════════

function PromoCodesTab({ onAdminError }) {
  const [codes, setCodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [usageTarget, setUsageTarget] = useState(null);
  const [usageData, setUsageData] = useState(null);
  const [saving, setSaving] = useState(false);
  const emptyForm = { code: '', discount_type: 'percent', discount_value: '', max_uses: '', valid_until: '', is_influencer_code: false, influencer_name: '', label: '', applicable_plans: [] };
  const [form, setForm] = useState(emptyForm);

  const fetchCodes = useCallback(async () => {
    setLoading(true);
    try {
      const res = await admin.getPromoCodes();
      setCodes(res.data.promo_codes || []);
    } catch (err) { onAdminError(err, 'Failed to load promo codes'); }
    finally { setLoading(false); }
  }, [onAdminError]);

  useEffect(() => { fetchCodes(); }, [fetchCodes]);

  const openCreate = () => { setForm(emptyForm); setEditTarget(null); setCreateOpen(true); };
  const openEdit = (c) => {
    setForm({
      code: c.code, discount_type: c.discount_type, discount_value: String(c.discount_value),
      max_uses: c.max_uses ? String(c.max_uses) : '', valid_until: c.valid_until ? c.valid_until.slice(0, 10) : '',
      is_influencer_code: c.is_influencer_code, influencer_name: c.influencer_name || '',
      label: c.label || '', applicable_plans: c.applicable_plans || [],
    });
    setEditTarget(c);
    setCreateOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        ...form,
        discount_value: parseFloat(form.discount_value),
        max_uses: form.max_uses ? parseInt(form.max_uses) : null,
        valid_until: form.valid_until || null,
        applicable_plans: form.applicable_plans?.length ? form.applicable_plans : null,
      };
      if (editTarget) {
        await admin.updatePromoCode(editTarget.id, payload);
        toast.success('Promo code updated');
      } else {
        await admin.createPromoCode(payload);
        toast.success('Promo code created');
      }
      setCreateOpen(false);
      fetchCodes();
    } catch (err) { toast.error(err.response?.data?.error || 'Save failed'); }
    finally { setSaving(false); }
  };

  const handleToggle = async (c) => {
    try {
      await admin.updatePromoCode(c.id, { is_active: !c.is_active });
      fetchCodes();
    } catch { toast.error('Failed to toggle code'); }
  };

  const openUsage = async (c) => {
    setUsageTarget(c);
    setUsageData(null);
    try {
      const res = await admin.getPromoUsage(c.id);
      setUsageData(res.data);
    } catch {
      toast.error('Failed to load usage');
      setUsageData({ usages: [], error: true });
    }
  };

  if (loading) return <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box>;

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h6" fontWeight={700}>Promo Codes</Typography>
        <Button variant="contained" onClick={openCreate}>+ New Code</Button>
      </Stack>

      <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Code</TableCell>
              <TableCell>Discount</TableCell>
              <TableCell>Uses</TableCell>
              <TableCell>Valid Until</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {codes.length === 0 ? <EmptyRow cols={7} message="No promo codes yet" /> : codes.map(c => (
              <TableRow key={c.id} hover>
                <TableCell>
                  <Typography variant="body2" fontWeight={700} sx={{ fontFamily: 'monospace' }}>{c.code}</Typography>
                  {c.label && <Typography variant="caption" color="text.secondary">{c.label}</Typography>}
                </TableCell>
                <TableCell>
                  {c.discount_type === 'percent' ? `${c.discount_value}%` :
                   c.discount_type === 'fixed' ? `$${c.discount_value}` : `+${c.discount_value} days`}
                </TableCell>
                <TableCell>{c.uses_count}{c.max_uses ? ` / ${c.max_uses}` : ''}</TableCell>
                <TableCell>{c.valid_until ? fmtDate(c.valid_until) : '∞ No expiry'}</TableCell>
                <TableCell>
                  {c.is_influencer_code
                    ? <Chip label={`KOL: ${c.influencer_name || 'unnamed'}`} size="small" color="secondary" />
                    : <Chip label="Standard" size="small" />}
                </TableCell>
                <TableCell>
                  <Chip label={c.is_active ? 'Active' : 'Disabled'} size="small" color={c.is_active ? 'success' : 'default'} />
                </TableCell>
                <TableCell align="right">
                  <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                    <Button size="small" onClick={() => openUsage(c)}>Usage</Button>
                    <Button size="small" onClick={() => openEdit(c)}>Edit</Button>
                    <Button size="small" color={c.is_active ? 'error' : 'success'} onClick={() => handleToggle(c)}>
                      {c.is_active ? 'Disable' : 'Enable'}
                    </Button>
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Create / Edit dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editTarget ? `Edit — ${editTarget.code}` : 'New Promo Code'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} pt={1}>
            <TextField size="small" label="Code" value={form.code} disabled={!!editTarget}
              onChange={e => setForm(f => ({ ...f, code: e.target.value.toUpperCase() }))}
              inputProps={{ style: { fontFamily: 'monospace', letterSpacing: 2 } }} />
            <Stack direction="row" spacing={1.5}>
              <FormControl size="small" sx={{ flex: 1 }}>
                <InputLabel>Type</InputLabel>
                <Select value={form.discount_type} label="Type" onChange={e => setForm(f => ({ ...f, discount_type: e.target.value }))}>
                  <MenuItem value="percent">Percentage (%)</MenuItem>
                  <MenuItem value="fixed">Fixed ($)</MenuItem>
                  <MenuItem value="trial_days">Bonus Days</MenuItem>
                </Select>
              </FormControl>
              <TextField size="small" label="Value" type="number" sx={{ flex: 1 }}
                value={form.discount_value} onChange={e => setForm(f => ({ ...f, discount_value: e.target.value }))} />
            </Stack>
            <Stack direction="row" spacing={1.5}>
              <TextField size="small" label="Max Uses (blank = unlimited)" type="number" sx={{ flex: 1 }}
                value={form.max_uses} onChange={e => setForm(f => ({ ...f, max_uses: e.target.value }))} />
              <TextField size="small" label="Expires (blank = never)" type="date" sx={{ flex: 1 }}
                value={form.valid_until} onChange={e => setForm(f => ({ ...f, valid_until: e.target.value }))}
                InputLabelProps={{ shrink: true }} />
            </Stack>
            <TextField size="small" label="Internal Label / Note" value={form.label}
              onChange={e => setForm(f => ({ ...f, label: e.target.value }))} />
            <Stack direction="row" spacing={1} alignItems="center">
              <input type="checkbox" id="is_kol" checked={form.is_influencer_code}
                onChange={e => setForm(f => ({ ...f, is_influencer_code: e.target.checked }))} />
              <label htmlFor="is_kol"><Typography variant="body2">KOL / Influencer code</Typography></label>
            </Stack>
            {form.is_influencer_code && (
              <TextField size="small" label="Influencer Name" value={form.influencer_name}
                onChange={e => setForm(f => ({ ...f, influencer_name: e.target.value }))} />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? <CircularProgress size={16} /> : editTarget ? 'Save Changes' : 'Create Code'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Usage dialog */}
      <Dialog open={!!usageTarget} onClose={() => { setUsageTarget(null); setUsageData(null); }} maxWidth="sm" fullWidth>
        <DialogTitle>Usage — {usageTarget?.code} ({usageTarget?.uses_count} uses)</DialogTitle>
        <DialogContent>
          {!usageData ? <CircularProgress /> : usageData.usages?.length === 0 ? (
            <Typography color="text.secondary" py={2} textAlign="center">No usages yet.</Typography>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead><TableRow>
                  <TableCell>User ID</TableCell><TableCell>Original</TableCell><TableCell>Discount</TableCell><TableCell>Final</TableCell><TableCell>Date</TableCell>
                </TableRow></TableHead>
                <TableBody>
                  {usageData.usages.map(u => (
                    <TableRow key={u.id}>
                      <TableCell>{u.user_id}</TableCell>
                      <TableCell>${u.original_price?.toFixed(2)}</TableCell>
                      <TableCell><Typography variant="body2" color="success.main">-${u.discount_amount?.toFixed(2)}</Typography></TableCell>
                      <TableCell>${u.final_price?.toFixed(2)}</TableCell>
                      <TableCell>{fmtDateTime(u.used_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DialogContent>
        <DialogActions><Button onClick={() => { setUsageTarget(null); setUsageData(null); }}>Close</Button></DialogActions>
      </Dialog>
    </Box>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// TAB 11 — BOT HEALTH
// ═══════════════════════════════════════════════════════════════════════════════

function BotHealthTab({ onAdminError }) {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [pinging, setPinging] = useState({});            // key (scope:id) -> bool
  const [pingResult, setPingResult] = useState({});      // key -> {ok, text}
  const [errorsFor, setErrorsFor] = useState(null);      // {scope, ref, label}
  const [errors, setErrors] = useState([]);
  const [errorsLoading, setErrorsLoading] = useState(false);

  const fetch = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      const res = await admin.getBotHealth({ page: p, per_page: 25 });
      setData(res.data);
    } catch (err) { onAdminError(err, 'Failed to load bot health'); }
    finally { setLoading(false); }
  }, [onAdminError]);

  const [hc, setHc] = useState(null);
  const [hcRunning, setHcRunning] = useState(false);

  const loadHc = useCallback(async () => {
    try {
      const res = await admin.getBotHealthCenter();
      setHc(res.data);
    } catch { /* health center is optional; ignore */ }
  }, []);

  useEffect(() => { fetch(); loadHc(); }, [fetch, loadHc]);

  const runHealthCheck = async () => {
    setHcRunning(true);
    try {
      const res = await admin.runBotHealthCheck();
      const s = res.data.summary || {};
      toast.success(`Checked ${s.checked ?? 0} bots · ${s.failed ?? 0} failing · ${s.alerts ?? 0} alerts sent`);
      loadHc(); fetch(page);
    } catch (err) {
      toast.error(parseApiError(err).message);
    } finally { setHcRunning(false); }
  };

  const handlePing = async (scope, id) => {
    const key = `${scope}:${id ?? ''}`;
    setPinging((m) => ({ ...m, [key]: true }));
    try {
      const res = await admin.pingBot({ scope, id });
      const ok = !!res.data.ok;
      const disabled = ok && res.data.is_active === false;
      const text = ok
        ? (disabled
            ? `@${res.data.username || 'bot'} token works, but the bot is STOPPED (won't process messages until enabled)`
            : `@${res.data.username || 'bot'} is alive`)
        : (res.data.error || 'No response');
      setPingResult((m) => ({ ...m, [key]: { ok: ok && !disabled, text } }));
      if (!ok) toast.error(`❌ ${text}`);
      else if (disabled) toast.warning(`⚠️ ${text}`);
      else toast.success(`✅ ${text}`);
      fetch(page);   // refresh statuses
    } catch (err) {
      setPingResult((m) => ({ ...m, [key]: { ok: false, text: 'Request failed' } }));
      toast.error('Ping request failed');
    } finally {
      setPinging((m) => ({ ...m, [key]: false }));
    }
  };

  const openErrors = async (scope, ref, label) => {
    setErrorsFor({ scope, ref, label });
    setErrorsLoading(true);
    try {
      const res = await admin.getBotErrors({ scope, ref, limit: 50 });
      setErrors(res.data.errors || []);
    } catch { setErrors([]); }
    finally { setErrorsLoading(false); }
  };

  const official = data?.official || { error_count_24h: 0, last_error: null };
  const officialKey = 'official:';
  const officialPing = pingResult[officialKey];
  const bots = data?.custom_bots || [];
  const pages = data?.pages || 1;

  return (
    <Box>
      {/* Intro */}
      <Alert severity="info" sx={{ mb: 2, borderRadius: 2 }}>
        <Typography variant="body2">
          Press <b>Ping</b> to test a bot live against Telegram right now. <b>Status</b> reflects
          recent activity: <b>active</b> = working,&nbsp;<b>idle</b> = no activity in 7+ days,
          {' '}<b>offline</b> = stopped by owner, <b>unreachable</b> = silent 30+ days. The
          {' '}<b>Errors (24h)</b> column shows failures recorded automatically (polling crashes,
          AI, commands, webhooks) — click a number to see details.
        </Typography>
      </Alert>

      {/* Health Center — escalation grades (P1) */}
      <Card sx={{ mb: 2, border: '1px solid', borderColor: 'divider' }}>
        <CardContent>
          <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1.5} flexWrap="wrap" gap={1}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <MonitorHeart sx={{ color: '#3d8ef8' }} />
              <Typography variant="subtitle1" fontWeight={700}>Bot Health Center</Typography>
              <Typography variant="caption" color="text.secondary">
                {hc ? `${hc.total_monitored} monitored · auto-pinged every 6h` : 'no ping data yet'}
              </Typography>
            </Stack>
            <Button size="small" variant="contained" startIcon={<NetworkCheck />}
              disabled={hcRunning} onClick={runHealthCheck}>
              {hcRunning ? 'Checking…' : 'Run check now'}
            </Button>
          </Stack>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {[
              ['healthy', '#22c55e'], ['warning', '#f59e0b'], ['critical', '#ef4444'],
              ['inactive', '#64748b'], ['archived', '#475569'],
            ].map(([g, c]) => (
              <Chip key={g} label={`${g}: ${hc?.summary?.[g] ?? 0}`} size="small"
                sx={{ bgcolor: c, color: '#fff', fontWeight: 600 }} />
            ))}
          </Stack>
        </CardContent>
      </Card>

      {/* Summary cards */}
      <Grid container spacing={2} mb={1}>
        <Grid item xs={6} md={3}>
          <StatCard label="Community bots" value={data?.totals?.total_custom_bots ?? 0} color="#7c4dff" icon={SmartToy} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard label="Errors (last 24h)" value={data?.totals?.errors_24h ?? 0}
            color={(data?.totals?.errors_24h ?? 0) > 0 ? '#ef4444' : '#22c55e'} icon={Warning} />
        </Grid>
      </Grid>

      {/* Official bot card */}
      <Card sx={{ mb: 3, border: '1px solid', borderColor: 'divider' }}>
        <CardContent>
          <Stack direction={{ xs: 'column', sm: 'row' }} alignItems={{ sm: 'center' }} justifyContent="space-between" spacing={1.5}>
            <Box>
              <Stack direction="row" alignItems="center" spacing={1}>
                <MonitorHeart sx={{ color: '#7c4dff' }} />
                <Typography variant="h6" fontWeight={700}>Official bot (@telegizer_bot)</Typography>
                {officialPing && (
                  <Chip size="small" color={officialPing.ok ? 'success' : 'error'}
                    label={officialPing.ok ? 'Reachable' : 'Unreachable'} />
                )}
              </Stack>
              <Typography variant="body2" color="text.secondary" mt={0.5}>
                Errors (24h): <b style={{ color: official.error_count_24h > 0 ? '#ef4444' : 'inherit' }}>{official.error_count_24h}</b>
                {official.last_error && (
                  <> · last: {official.last_error.category} — {fmtDateTime(official.last_error.created_at)}</>
                )}
              </Typography>
              {official.last_error?.detail && (
                <Typography variant="caption" color="error" sx={{ fontFamily: 'monospace', display: 'block', mt: 0.5 }}>
                  {official.last_error.detail}
                </Typography>
              )}
            </Box>
            <Stack direction="row" spacing={1}>
              <Button variant="contained" startIcon={<NetworkCheck />}
                disabled={!!pinging[officialKey]}
                onClick={() => handlePing('official', null)}>
                {pinging[officialKey] ? 'Pinging…' : 'Ping now'}
              </Button>
              {official.error_count_24h > 0 && (
                <Button variant="outlined" onClick={() => openErrors('official', null, 'Official bot')}>View errors</Button>
              )}
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1}>
        <Typography variant="subtitle1" fontWeight={700}>Community bots</Typography>
        <Button size="small" startIcon={<Refresh />} onClick={() => fetch(page)}>Refresh</Button>
      </Stack>

      {loading ? <Box display="flex" justifyContent="center" mt={4}><CircularProgress /></Box> : (
        <>
          <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2, overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Bot</TableCell>
                  <TableCell>Owner</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Errors (24h)</TableCell>
                  <TableCell>Last error</TableCell>
                  <TableCell align="right">Test</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {bots.length === 0 ? <EmptyRow cols={6} /> : bots.map((b) => {
                  const key = `custom:${b.id}`;
                  const pr = pingResult[key];
                  return (
                    <TableRow key={b.id} hover>
                      <TableCell>
                        <Typography variant="body2" fontWeight={500}>@{b.bot_username}</Typography>
                        {b.bot_name && <Typography variant="caption" color="text.secondary">{b.bot_name}</Typography>}
                      </TableCell>
                      <TableCell><Typography variant="body2">{b.owner_email || '—'}</Typography></TableCell>
                      <TableCell>
                        <StatusChip label={b.status} map={{ active: 'success', idle: 'warning', offline: 'default', unreachable: 'error' }} />
                        {pr && (
                          <Tooltip title={pr.text}>
                            <Chip size="small" sx={{ ml: 0.5 }} color={pr.ok ? 'success' : 'error'}
                              label={pr.ok ? 'reachable' : 'down'} />
                          </Tooltip>
                        )}
                      </TableCell>
                      <TableCell align="right">
                        {b.error_count_24h > 0 ? (
                          <Button size="small" color="error" sx={{ minWidth: 0 }}
                            onClick={() => openErrors('custom', String(b.id), `@${b.bot_username}`)}>
                            {b.error_count_24h}
                          </Button>
                        ) : <Typography variant="body2" color="text.secondary">0</Typography>}
                      </TableCell>
                      <TableCell><Typography variant="caption" color="text.secondary">{fmtDateTime(b.last_error_at)}</Typography></TableCell>
                      <TableCell align="right">
                        <Button size="small" variant="outlined" startIcon={<NetworkCheck fontSize="small" />}
                          disabled={!!pinging[key]} onClick={() => handlePing('custom', b.id)}>
                          {pinging[key] ? '…' : 'Ping'}
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
          {pages > 1 && <Box display="flex" justifyContent="center"><Pagination count={pages} page={page} onChange={(_, p) => { setPage(p); fetch(p); }} color="primary" /></Box>}
        </>
      )}

      {/* Errors drill-down dialog */}
      <Dialog open={!!errorsFor} onClose={() => setErrorsFor(null)} maxWidth="md" fullWidth>
        <DialogTitle>Recent errors — {errorsFor?.label}</DialogTitle>
        <DialogContent dividers>
          {errorsLoading ? <Box display="flex" justifyContent="center" py={3}><CircularProgress /></Box> : (
            errors.length === 0 ? <Typography color="text.secondary" py={2}>No recorded errors.</Typography> : (
              <Stack spacing={1.5}>
                {errors.map((e) => {
                  const sevColor = { info: 'info', warning: 'warning', critical: 'error' }[e.severity] || 'error';
                  const sevLabel = { info: 'Info', warning: 'Warning', critical: 'Critical' }[e.severity] || 'Error';
                  return (
                  <Box key={e.id} sx={{ borderLeft: '3px solid', borderColor: `${sevColor}.main`, pl: 1.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                      <Chip size="small" color={sevColor} label={sevLabel} sx={{ height: 18, fontSize: '0.65rem', fontWeight: 700 }} />
                      {e.error_class && (
                        <Typography variant="caption" sx={{ fontWeight: 600, textTransform: 'capitalize' }}>
                          {e.error_class.replace(/_/g, ' ')}
                        </Typography>
                      )}
                      <Typography variant="caption" color="text.secondary">
                        {fmtDateTime(e.created_at)} · {e.category}{e.ref ? ` · ${e.ref}` : ''}
                      </Typography>
                    </Box>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-word' }}>{e.detail || '(no detail)'}</Typography>
                    {e.severity === 'info' && (
                      <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                        Deployment/restart event — not counted as a failure.
                      </Typography>
                    )}
                  </Box>
                  );
                })}
              </Stack>
            )
          )}
        </DialogContent>
        <DialogActions><Button onClick={() => setErrorsFor(null)}>Close</Button></DialogActions>
      </Dialog>
    </Box>
  );
}


// ─── Diagnostics tab (read-only audit snapshot) ───────────────────────────────

function KV({ label, value, color }) {
  return (
    <Stack direction="row" justifyContent="space-between" sx={{ py: 0.5, borderBottom: '1px solid', borderColor: 'divider' }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="body2" fontWeight={600} sx={{ color }}>{value}</Typography>
    </Stack>
  );
}

function DiagnosticsTab({ onAdminError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await admin.getDiagnostics();
      setData(res.data);
    } catch (err) {
      const { message, is403 } = parseApiError(err);
      if (is403) onAdminError?.(message); else toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [onAdminError]);

  const reconcile = useCallback(async (groupId) => {
    try {
      const res = await admin.reconcileGroup(groupId);
      if (res.data.promoted) toast.success('Promoted to active');
      else toast.info(res.data.reason || 'Not eligible yet');
      load();
    } catch (err) {
      toast.error(parseApiError(err).message);
    }
  }, [load]);

  const [aiTest, setAiTest] = useState(null);
  const [aiTesting, setAiTesting] = useState(false);
  const runAiTest = async () => {
    setAiTesting(true);
    try {
      const res = await admin.runAiSelftest();
      setAiTest(res.data.results || []);
    } catch (err) {
      toast.error(parseApiError(err).message);
    } finally { setAiTesting(false); }
  };

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}><CircularProgress /></Box>;
  }
  if (!data) return null;

  const { revenue, bots, groups, ai, health } = data;

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2}>
        <Box>
          <Typography variant="h6" fontWeight={700}>Diagnostics</Typography>
          <Typography variant="caption" color="text.secondary">
            Read-only audit snapshot · generated {fmtDateTime(data.generated_at)}
          </Typography>
        </Box>
        <Button startIcon={<Refresh />} onClick={load} variant="outlined" size="small">Refresh</Button>
      </Stack>

      <Alert severity="info" sx={{ mb: 2 }}>
        No mutations, no live Telegram/AI calls — every number is derived from the database, safe to refresh.
      </Alert>

      <Grid container spacing={2}>
        {/* Revenue (P4) */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}><CardContent>
            <Typography fontWeight={700} mb={1}>💰 Revenue (P4) — paid rows only</Typography>
            <KV label="MRR" value={usd(revenue.mrr_usd)} color="#22c55e" />
            <KV label="ARR" value={usd(revenue.arr_usd)} color="#16a34a" />
            <KV label="Paying subscribers" value={revenue.paying_subscribers} />
            <KV label="Tier head-count (pro / ent)" value={`${revenue.tier_headcount.pro} / ${revenue.tier_headcount.enterprise}`} color="#94a3b8" />
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{revenue.note}</Typography>
            {revenue.contributing_rows.length > 0 ? (
              <TableContainer sx={{ mt: 1.5 }}>
                <Table size="small">
                  <TableHead><TableRow>
                    <TableCell>Email</TableCell><TableCell>Plan</TableCell>
                    <TableCell align="right">Paid</TableCell><TableCell align="right">/mo</TableCell>
                  </TableRow></TableHead>
                  <TableBody>
                    {revenue.contributing_rows.map((r) => (
                      <TableRow key={r.user_id}>
                        <TableCell>{r.email}</TableCell>
                        <TableCell><Chip size="small" label={`${r.plan} · ${r.billing_period}`} /></TableCell>
                        <TableCell align="right">{usd(r.amount_usd)}</TableCell>
                        <TableCell align="right">{usd(r.monthly_value_usd)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Alert severity="success" sx={{ mt: 1.5 }}>No qualifying paid rows → MRR/ARR correctly $0.</Alert>
            )}
          </CardContent></Card>
        </Grid>

        {/* Bots (P6) */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}><CardContent>
            <Typography fontWeight={700} mb={1}>🤖 Bots (P6) — two tables reconciled</Typography>
            <KV label="custom_bots table" value={bots.custom_bots_table} />
            <KV label="legacy bots table" value={bots.legacy_bots_table} />
            <KV label="same username in both" value={bots.in_both_tables_same_username} color="#f59e0b" />
            <KV label="Unified distinct total" value={bots.unified_distinct_total} color="#3d8ef8" />
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{bots.note}</Typography>
          </CardContent></Card>
        </Grid>

        {/* AI availability (P2) */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}><CardContent>
            <Typography fontWeight={700} mb={1}>🧠 AI availability (P2)</Typography>
            <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
              <Typography variant="body2">Official bot AI moderation:</Typography>
              <Chip size="small" color={ai.official_bot.ai_moderation_wired ? 'success' : 'warning'}
                label={ai.official_bot.ai_moderation_wired ? 'wired' : 'rule-based only'} />
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>{ai.official_bot.note}</Typography>
            <KV label="Custom-bot AI wired" value={ai.custom_bots.ai_moderation_wired ? 'yes' : 'no'} color="#22c55e" />
            <KV label="Owners with workspace AI key" value={ai.custom_bots.owners_with_workspace_ai_key} />
            <KV label="Platform AI key configured" value={ai.custom_bots.platform_ai_key_configured ? 'yes' : 'no'}
              color={ai.custom_bots.platform_ai_key_configured ? '#22c55e' : '#ef4444'} />

            <Divider sx={{ my: 1.5 }} />
            <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1}>
              <Typography variant="body2" fontWeight={600}>End-to-end AI self-test</Typography>
              <Button size="small" variant="outlined" disabled={aiTesting} onClick={runAiTest}>
                {aiTesting ? 'Testing…' : 'Run AI self-test'}
              </Button>
            </Stack>
            {aiTest && aiTest.map((r) => (
              <Stack key={r.feature} direction="row" alignItems="flex-start" spacing={1} sx={{ py: 0.5 }}>
                <Chip size="small"
                  color={r.status === 'working' ? 'success' : r.status === 'broken' ? 'error' : 'default'}
                  label={r.status === 'working' ? 'Working' : r.status === 'broken' ? 'Broken' : 'Not connected'} />
                <Box>
                  <Typography variant="caption" fontWeight={600} sx={{ display: 'block' }}>{r.feature}</Typography>
                  <Typography variant="caption" color="text.secondary">{r.detail}</Typography>
                </Box>
              </Stack>
            ))}
            {!aiTest && (
              <Typography variant="caption" color="text.secondary">
                Makes real calls through each AI path with the platform key and reports Working / Broken / Not connected.
              </Typography>
            )}
          </CardContent></Card>
        </Grid>

        {/* Health (P1) */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}><CardContent>
            <Typography fontWeight={700} mb={1}>❤️ Bot health facts (P1)</Typography>
            <KV label="Legacy bots by status" value={Object.entries(health.legacy_bots_by_status).map(([k, v]) => `${k}:${v}`).join('  ') || '—'} />
            <KV label="Custom bots by status" value={Object.entries(health.custom_bots_by_status).map(([k, v]) => `${k}:${v}`).join('  ') || '—'} />
            <KV label="Errors (24h) by scope" value={Object.entries(health.errors_24h_by_scope).map(([k, v]) => `${k}:${v}`).join('  ') || 'none'} />
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{health.note}</Typography>
          </CardContent></Card>
        </Grid>

        {/* Pending groups (P5) */}
        <Grid item xs={12}>
          <Card><CardContent>
            <Typography fontWeight={700} mb={1}>
              📭 Pending groups (P5) — {groups.pending_count} pending · {groups.active_count} active
            </Typography>
            {groups.rows.length === 0 ? (
              <Alert severity="success">No pending groups.</Alert>
            ) : (
              <TableContainer>
                <Table size="small">
                  <TableHead><TableRow>
                    <TableCell>Group</TableCell><TableCell>Owner?</TableCell>
                    <TableCell>Recent activity</TableCell><TableCell>Why pending?</TableCell>
                    <TableCell align="right">Action</TableCell>
                  </TableRow></TableHead>
                  <TableBody>
                    {groups.rows.map((g) => (
                      <TableRow key={g.telegram_group_id}>
                        <TableCell>{g.title || g.telegram_group_id}</TableCell>
                        <TableCell>{g.has_owner ? '✓' : '—'}</TableCell>
                        <TableCell>{g.has_recent_activity_7d
                          ? <Chip size="small" color="success" label="active" />
                          : <Chip size="small" label="quiet" />}</TableCell>
                        <TableCell><Typography variant="caption">{g.why_pending}</Typography></TableCell>
                        <TableCell align="right">
                          <Button size="small" variant={g.will_auto_promote ? 'contained' : 'outlined'}
                            color={g.will_auto_promote ? 'success' : 'inherit'}
                            onClick={() => reconcile(g.telegram_group_id)}>
                            {g.will_auto_promote ? 'Activate' : 'Re-check'}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent></Card>
        </Grid>
      </Grid>
    </Box>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// TAB — AI MANAGEMENT (ai.manage)
// ═══════════════════════════════════════════════════════════════════════════════

const AI_FIELD_LABELS = {
  ai_default_model: 'Default model',
  ai_default_base_url: 'Default base URL',
  ai_daily_spend_cap_usd: 'Daily platform spend cap (USD)',
  ai_tokens_free: 'Daily token limit — Free',
  ai_tokens_pro: 'Daily token limit — Pro',
  ai_tokens_enterprise: 'Daily token limit — Enterprise',
};

function AITab({ onAdminError }) {
  const [form, setForm] = useState(null);
  const [original, setOriginal] = useState({});
  const [usage, setUsage] = useState(null);
  const [aiEnabled, setAiEnabled] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await admin.getAiConfig();
      const f = {}; (data.settings || []).forEach(s => { f[s.key] = s.value; });
      setForm(f); setOriginal({ ...f });
      setUsage(data.usage || null);
      setAiEnabled(data.ai_features_enabled);
    } catch (e) { onAdminError?.(e, 'Failed to load AI config'); }
    finally { setLoading(false); }
  }, [onAdminError]);
  useEffect(() => { load(); }, [load]);

  const changed = form ? Object.keys(form).filter(k => String(form[k]) !== String(original[k])) : [];

  const save = async () => {
    setSaving(true);
    try {
      const payload = {};
      changed.forEach(k => { payload[k] = form[k]; });
      const { data } = await admin.updateAiConfig(payload);
      const f = {}; (data.settings || []).forEach(s => { f[s.key] = s.value; });
      setForm(f); setOriginal({ ...f });
      toast.success(data.message || 'AI settings saved');
    } catch (e) { onAdminError?.(e, 'Failed to save AI settings'); }
    finally { setSaving(false); }
  };

  if (loading || !form) return <Box display="flex" justifyContent="center" py={6}><CircularProgress /></Box>;

  const isNumber = (k) => k !== 'ai_default_model' && k !== 'ai_default_base_url';

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2} flexWrap="wrap" gap={1}>
        <Box>
          <Typography variant="h6" fontWeight={700}>AI Management</Typography>
          <Typography variant="caption" color="text.secondary">
            Default model, platform spend cap and per-tier daily token limits. Applies within ~30s.
          </Typography>
        </Box>
        <Stack direction="row" gap={1} alignItems="center">
          {aiEnabled === false && <Chip label="AI features OFF" color="error" size="small" />}
          <Button size="small" startIcon={<Refresh />} onClick={load} disabled={saving}>Refresh</Button>
          <Button size="small" variant="contained" onClick={save} disabled={saving || changed.length === 0}>
            {saving ? 'Saving…' : `Save${changed.length ? ` (${changed.length})` : ''}`}
          </Button>
        </Stack>
      </Stack>

      {aiEnabled === false && (
        <Alert severity="warning" sx={{ mb: 2, borderRadius: 2 }}>
          The <b>ai_features_enabled</b> master switch is OFF (toggle it in Configuration → Feature Flags).
          These limits won't matter until AI is re-enabled.
        </Alert>
      )}

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1.5}>Settings</Typography>
              <Stack spacing={2}>
                {Object.keys(form).map(k => (
                  <TextField key={k} size="small" fullWidth
                    label={AI_FIELD_LABELS[k] || k}
                    type={isNumber(k) ? 'number' : 'text'}
                    value={form[k] ?? ''}
                    onChange={e => setForm({ ...form, [k]: isNumber(k) ? e.target.value : e.target.value })}
                  />
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1.5}>Usage today</Typography>
              {!usage ? <Typography variant="body2" color="text.secondary">No usage data.</Typography> : (
                <>
                  <Typography variant="body2" color="text.secondary">Platform AI spend</Typography>
                  <Typography variant="h5" fontWeight={700}>
                    {usage.spend_today_usd == null ? 'n/a' : usd(usage.spend_today_usd)}
                    <Typography component="span" variant="body2" color="text.secondary"> / {usd(usage.daily_cap_usd)} cap</Typography>
                  </Typography>
                  {usage.spend_pct != null && (
                    <LinearProgress variant="determinate" value={Math.min(100, usage.spend_pct)}
                      color={usage.spend_pct > 80 ? 'error' : 'primary'} sx={{ my: 1, height: 8, borderRadius: 1 }} />
                  )}
                  <Divider sx={{ my: 1.5 }} />
                  <Typography variant="body2" fontWeight={600} mb={0.5}>Top token users (today)</Typography>
                  {(usage.top_token_users || []).length === 0 ? (
                    <Typography variant="caption" color="text.secondary">No platform-key usage today.</Typography>
                  ) : (
                    <Table size="small">
                      <TableBody>
                        {usage.top_token_users.map(u => (
                          <TableRow key={u.id}>
                            <TableCell sx={{ fontSize: 12 }}>{u.email}</TableCell>
                            <TableCell><Chip label={u.tier} size="small" /></TableCell>
                            <TableCell align="right" sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                              {(u.tokens_today || 0).toLocaleString()}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// TAB — PRICING (Super Admin only)
// ═══════════════════════════════════════════════════════════════════════════════

function PricingTab({ onAdminError }) {
  const [prices, setPrices] = useState(null);
  const [original, setOriginal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await admin.getPricing();
      setPrices(data.prices); setOriginal(JSON.parse(JSON.stringify(data.prices)));
    } catch (e) { onAdminError?.(e, 'Failed to load pricing'); }
    finally { setLoading(false); }
  }, [onAdminError]);
  useEffect(() => { load(); }, [load]);

  const dirty = prices && original && JSON.stringify(prices) !== JSON.stringify(original);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await admin.updatePricing(prices);
      setPrices(data.prices); setOriginal(JSON.parse(JSON.stringify(data.prices)));
      toast.success(data.message || 'Pricing updated');
      setConfirm(false);
    } catch (e) { onAdminError?.(e, 'Failed to update pricing'); }
    finally { setSaving(false); }
  };

  if (loading || !prices) return <Box display="flex" justifyContent="center" py={6}><CircularProgress /></Box>;

  const setP = (tier, period, val) => setPrices({ ...prices, [tier]: { ...prices[tier], [period]: val } });

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2} flexWrap="wrap" gap={1}>
        <Box>
          <Typography variant="h6" fontWeight={700}>Pricing</Typography>
          <Typography variant="caption" color="text.secondary">
            Tier prices in USD. Drives the public plans page, checkout amount and payment verification — all in sync.
          </Typography>
        </Box>
        <Stack direction="row" gap={1}>
          <Button size="small" startIcon={<Refresh />} onClick={load} disabled={saving}>Refresh</Button>
          <Button size="small" variant="contained" color="warning" onClick={() => setConfirm(true)} disabled={saving || !dirty}>
            Save pricing
          </Button>
        </Stack>
      </Stack>

      <Alert severity="warning" sx={{ mb: 2, borderRadius: 2 }}>
        Pricing changes take effect immediately for new checkouts and are recorded in the audit log. Existing
        subscriptions are unaffected.
      </Alert>

      <Grid container spacing={2}>
        {['pro', 'enterprise'].map(tier => (
          <Grid item xs={12} md={6} key={tier}>
            <Card>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={700} mb={1.5} textTransform="capitalize">{tier}</Typography>
                <Stack spacing={2}>
                  {['monthly', 'annual'].map(period => (
                    <TextField key={period} size="small" fullWidth type="number"
                      label={`${period[0].toUpperCase()}${period.slice(1)} price (USD)`}
                      value={prices[tier]?.[period] ?? ''}
                      onChange={e => setP(tier, period, e.target.value)}
                      inputProps={{ min: 0.01, step: 0.01 }}
                      InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                    />
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Dialog open={confirm} onClose={() => !saving && setConfirm(false)}>
        <DialogTitle>Update pricing?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            New prices will apply to all new checkouts immediately and update the public pricing page. Confirm?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(false)} disabled={saving}>Cancel</Button>
          <Button color="warning" variant="contained" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Confirm'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// TAB — SECRET & API-KEY VAULT (Super Admin only)
// ═══════════════════════════════════════════════════════════════════════════════

const SECRET_CATEGORY_LABELS = {
  ai: 'AI Providers', telegram: 'Telegram Bots', payments: 'Payments',
  email: 'Email', social: 'Social / Link Checks', oauth: 'OAuth',
};
const SECRET_CATEGORY_ORDER = ['ai', 'telegram', 'payments', 'email', 'social', 'oauth'];

function SecretsTab({ onAdminError }) {
  const [secrets, setSecrets] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);   // secret object being set
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState(null); // { ok, message }
  const [confirmClear, setConfirmClear] = useState(null);
  const [testingRow, setTestingRow] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await admin.getSecrets();
      setSecrets(data.secrets || []);
    } catch (e) { onAdminError?.(e, 'Failed to load secrets'); }
    finally { setLoading(false); }
  }, [onAdminError]);
  useEffect(() => { load(); }, [load]);

  const openEdit = (s) => { setEditing(s); setValue(''); setTestResult(null); };

  const saveSecret = async () => {
    if (!value.trim()) return;
    setBusy(true);
    try {
      const { data } = await admin.setSecret(editing.name, value.trim());
      setSecrets(data.secrets || secrets);
      toast.success(`${editing.label} updated`);
      setEditing(null); setValue('');
    } catch (e) { onAdminError?.(e, 'Failed to save secret'); }
    finally { setBusy(false); }
  };

  const testInDialog = async () => {
    setBusy(true); setTestResult(null);
    try {
      const { data } = await admin.testSecret(editing.name, value.trim() || undefined);
      setTestResult(data);
    } catch (e) { setTestResult({ ok: false, message: 'Test request failed' }); }
    finally { setBusy(false); }
  };

  const testRow = async (s) => {
    setTestingRow(s.name);
    try {
      const { data } = await admin.testSecret(s.name);
      toast[data.ok ? 'success' : 'error'](`${s.label}: ${data.message}`);
      load();
    } catch (e) { onAdminError?.(e, 'Test failed'); }
    finally { setTestingRow(null); }
  };

  const doClear = async () => {
    setBusy(true);
    try {
      const { data } = await admin.clearSecret(confirmClear.name);
      setSecrets(data.secrets || secrets);
      toast.success(`${confirmClear.label} cleared — using environment value`);
      setConfirmClear(null);
    } catch (e) { onAdminError?.(e, 'Failed to clear secret'); }
    finally { setBusy(false); }
  };

  if (loading || !secrets) {
    return <Box display="flex" justifyContent="center" py={6}><CircularProgress /></Box>;
  }

  const byCat = {};
  secrets.forEach(s => { (byCat[s.category] = byCat[s.category] || []).push(s); });
  const cats = SECRET_CATEGORY_ORDER.filter(c => byCat[c]).concat(Object.keys(byCat).filter(c => !SECRET_CATEGORY_ORDER.includes(c)));

  const sourceChip = (s) => {
    if (s.source === 'db') return <Chip label="DB override" size="small" color="primary" />;
    if (s.source === 'env') return <Chip label="env var" size="small" color="default" />;
    return <Chip label="not set" size="small" color="warning" variant="outlined" />;
  };

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2} flexWrap="wrap" gap={1}>
        <Box>
          <Typography variant="h6" fontWeight={700}>Secrets &amp; API Keys</Typography>
          <Typography variant="caption" color="text.secondary">
            Manage platform keys without redeploying. Stored encrypted; values are write-only and never displayed.
          </Typography>
        </Box>
        <Button size="small" startIcon={<Refresh />} onClick={load}>Refresh</Button>
      </Stack>

      <Alert severity="warning" sx={{ mb: 2, borderRadius: 2 }}>
        Setting a value here overrides the environment variable for that key. Keys marked <b>applies on restart</b>
        &nbsp;(bot tokens) take effect after the next deploy/restart; the rest apply within ~30s.
      </Alert>

      <Stack spacing={2}>
        {cats.map(cat => (
          <Card key={cat}>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>{SECRET_CATEGORY_LABELS[cat] || cat}</Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Key</TableCell>
                      <TableCell>Value</TableCell>
                      <TableCell>Source</TableCell>
                      <TableCell>Last test</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {byCat[cat].map(s => (
                      <TableRow key={s.name} hover>
                        <TableCell>
                          <Typography variant="body2" fontWeight={600}>{s.label}</Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                            {s.name}{!s.live && ' · applies on restart'}
                          </Typography>
                        </TableCell>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{s.masked || '—'}</TableCell>
                        <TableCell>{sourceChip(s)}</TableCell>
                        <TableCell>
                          {s.last_test_ok == null ? <Typography variant="caption" color="text.disabled">—</Typography>
                            : s.last_test_ok ? <CheckCircle color="success" fontSize="small" />
                            : <Cancel color="error" fontSize="small" />}
                        </TableCell>
                        <TableCell align="right">
                          <Stack direction="row" gap={0.5} justifyContent="flex-end">
                            {s.testable && (
                              <Button size="small" disabled={testingRow === s.name || !s.is_set} onClick={() => testRow(s)}>
                                {testingRow === s.name ? '…' : 'Test'}
                              </Button>
                            )}
                            <Button size="small" variant="outlined" startIcon={<Key fontSize="small" />} onClick={() => openEdit(s)}>
                              {s.source === 'db' ? 'Rotate' : 'Set'}
                            </Button>
                            {s.source === 'db' && (
                              <Tooltip title="Clear DB override (revert to env var)">
                                <span><IconButton size="small" color="error" onClick={() => setConfirmClear(s)}><Delete fontSize="small" /></IconButton></span>
                              </Tooltip>
                            )}
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        ))}
      </Stack>

      {/* Set / rotate dialog */}
      <Dialog open={!!editing} onClose={() => !busy && setEditing(null)} fullWidth maxWidth="sm">
        <DialogTitle>{editing?.source === 'db' ? 'Rotate' : 'Set'} — {editing?.label}</DialogTitle>
        <DialogContent>
          <Typography variant="caption" color="text.secondary">
            The value is encrypted at rest and never shown again. Leave the panel without saving to cancel.
          </Typography>
          <TextField
            type="password" fullWidth autoFocus margin="normal" label="New value"
            value={value} onChange={e => { setValue(e.target.value); setTestResult(null); }}
            placeholder="Paste the key/token"
          />
          {testResult && (
            <Alert severity={testResult.ok ? 'success' : 'error'} sx={{ mt: 1 }}>{testResult.message}</Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(null)} disabled={busy}>Cancel</Button>
          {editing?.testable && (
            <Button onClick={testInDialog} disabled={busy || !value.trim()}>Test</Button>
          )}
          <Button variant="contained" onClick={saveSecret} disabled={busy || !value.trim()}>
            {busy ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Clear confirm */}
      <Dialog open={!!confirmClear} onClose={() => !busy && setConfirmClear(null)}>
        <DialogTitle>Clear {confirmClear?.label}?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            This removes the stored override. The key will fall back to its environment variable
            (or be unset if there is none). Continue?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmClear(null)} disabled={busy}>Cancel</Button>
          <Button color="error" variant="contained" onClick={doClear} disabled={busy}>Clear</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// TAB — PLATFORM CONFIGURATION & FEATURE FLAGS (Super Admin only)
// ═══════════════════════════════════════════════════════════════════════════════

const CATEGORY_LABELS = {
  branding: 'Branding', links: 'URLs & Links', localization: 'Localization',
  maintenance: 'Maintenance', onboarding: 'Onboarding',
};
const CATEGORY_ORDER = ['branding', 'links', 'localization', 'maintenance', 'onboarding'];

function prettyKey(k) {
  return k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function ConfigurationTab({ onAdminError }) {
  const [form, setForm] = useState(null);     // { key: value }
  const [original, setOriginal] = useState({});
  const [meta, setMeta] = useState({});        // key -> { category, is_public }
  const [flags, setFlags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState(null); // { title, body, color, onConfirm }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await admin.getPlatformConfig();
      const f = {}; const m = {};
      (data.settings || []).forEach(s => { f[s.key] = s.value; m[s.key] = { category: s.category, is_public: s.is_public }; });
      setForm(f); setOriginal({ ...f }); setMeta(m);
      setFlags(data.flags || []);
    } catch (e) { onAdminError?.(e, 'Failed to load configuration'); }
    finally { setLoading(false); }
  }, [onAdminError]);
  useEffect(() => { load(); }, [load]);

  const changedKeys = form ? Object.keys(form).filter(k => form[k] !== original[k]) : [];

  const doSave = async () => {
    setSaving(true);
    try {
      const payload = {};
      changedKeys.forEach(k => { payload[k] = form[k]; });
      const { data } = await admin.updatePlatformSettings(payload);
      const f = {}; (data.settings || []).forEach(s => { f[s.key] = s.value; });
      setForm(f); setOriginal({ ...f });
      toast.success(data.message || 'Configuration saved');
    } catch (e) { onAdminError?.(e, 'Failed to save configuration'); }
    finally { setSaving(false); setConfirm(null); }
  };

  const onSave = () => {
    // Confirm before enabling maintenance mode (it pauses the platform).
    if (form.maintenance_mode === true && original.maintenance_mode !== true) {
      setConfirm({
        title: 'Enable maintenance mode?',
        body: 'All non-admin users will be blocked from the app until you turn this off. Bots and webhooks keep running.',
        color: 'error', onConfirm: doSave,
      });
    } else { doSave(); }
  };

  const toggleFlag = (flag, next) => {
    const apply = async () => {
      try {
        const { data } = await admin.updateFeatureFlag(flag.key, next);
        setFlags(data.flags || flags);
        toast.success(`${prettyKey(flag.key)} ${next ? 'enabled' : 'disabled'}`);
      } catch (e) { onAdminError?.(e, 'Failed to update feature flag'); }
      finally { setConfirm(null); }
    };
    if (!next) {
      setConfirm({
        title: `Disable ${prettyKey(flag.key)}?`,
        body: flag.description || 'This turns the feature off platform-wide immediately.',
        color: 'error', onConfirm: apply,
      });
    } else { apply(); }
  };

  if (loading || !form) {
    return <Box display="flex" justifyContent="center" py={6}><CircularProgress /></Box>;
  }

  const byCategory = {};
  Object.keys(meta).forEach(k => {
    const cat = meta[k].category || 'other';
    (byCategory[cat] = byCategory[cat] || []).push(k);
  });
  const cats = CATEGORY_ORDER.filter(c => byCategory[c]).concat(Object.keys(byCategory).filter(c => !CATEGORY_ORDER.includes(c)));

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2} flexWrap="wrap" gap={1}>
        <Box>
          <Typography variant="h6" fontWeight={700}>Platform Configuration</Typography>
          <Typography variant="caption" color="text.secondary">
            Edit branding, links, localization, maintenance mode and feature flags. Changes apply within ~30s.
          </Typography>
        </Box>
        <Stack direction="row" gap={1}>
          <Button size="small" startIcon={<Refresh />} onClick={load} disabled={saving}>Refresh</Button>
          <Button size="small" variant="contained" onClick={onSave} disabled={saving || changedKeys.length === 0}>
            {saving ? 'Saving…' : `Save${changedKeys.length ? ` (${changedKeys.length})` : ''}`}
          </Button>
        </Stack>
      </Stack>

      <Grid container spacing={2}>
        {cats.map(cat => (
          <Grid item xs={12} md={6} key={cat}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={700} mb={1.5}
                  color={cat === 'maintenance' ? 'error.main' : 'text.primary'}>
                  {CATEGORY_LABELS[cat] || prettyKey(cat)}
                </Typography>
                <Stack spacing={2}>
                  {byCategory[cat].map(key => (
                    typeof form[key] === 'boolean' ? (
                      <FormControlLabel key={key}
                        control={<Switch checked={!!form[key]}
                          color={key === 'maintenance_mode' ? 'error' : 'primary'}
                          onChange={e => setForm({ ...form, [key]: e.target.checked })} />}
                        label={<Box>
                          <Typography variant="body2">{prettyKey(key)}</Typography>
                          {key === 'maintenance_mode' && form[key] && (
                            <Typography variant="caption" color="error">Platform is paused for non-admins</Typography>)}
                        </Box>}
                      />
                    ) : (
                      <TextField key={key} size="small" fullWidth
                        label={prettyKey(key)}
                        value={form[key] ?? ''}
                        multiline={key === 'maintenance_message'}
                        onChange={e => setForm({ ...form, [key]: e.target.value })}
                      />
                    )
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}

        {/* Feature flags */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1.5}>Feature Flags</Typography>
              <Stack divider={<Divider />}>
                {flags.map(flag => (
                  <Stack key={flag.key} direction="row" alignItems="center" justifyContent="space-between" py={1} gap={2}>
                    <Box>
                      <Typography variant="body2" fontWeight={600}>{prettyKey(flag.key)}</Typography>
                      <Typography variant="caption" color="text.secondary">{flag.description}</Typography>
                    </Box>
                    <Switch checked={!!flag.enabled} onChange={e => toggleFlag(flag, e.target.checked)} />
                  </Stack>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Dialog open={!!confirm} onClose={() => !saving && setConfirm(null)}>
        <DialogTitle>{confirm?.title}</DialogTitle>
        <DialogContent><Typography variant="body2">{confirm?.body}</Typography></DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(null)} disabled={saving}>Cancel</Button>
          <Button variant="contained" color={confirm?.color || 'primary'} disabled={saving} onClick={confirm?.onConfirm}>
            Confirm
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// TAB — ROLES & ACCESS (Super Admin only)
// ═══════════════════════════════════════════════════════════════════════════════

const ROLE_LABELS = {
  super_admin: 'Super Admin', admin: 'Admin', support: 'Support',
  finance: 'Finance', moderator: 'Moderator', analyst: 'Read-only Analyst',
};
const ROLE_COLORS = {
  super_admin: 'error', admin: 'primary', support: 'info',
  finance: 'success', moderator: 'warning', analyst: 'default',
};
const ASSIGNABLE_ROLES = ['admin', 'support', 'finance', 'moderator', 'analyst'];

function RolesTab({ onAdminError, currentUserId }) {
  const [admins, setAdmins] = useState(null);
  const [matrix, setMatrix] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState(null); // { row, newRole }
  const [saving, setSaving] = useState(false);
  const [showMatrix, setShowMatrix] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [aRes, mRes] = await Promise.allSettled([admin.getAdmins(), admin.getRoleMatrix()]);
      if (aRes.status === 'fulfilled') setAdmins(aRes.value.data.admins || []);
      else onAdminError?.(aRes.reason, 'Failed to load admins');
      if (mRes.status === 'fulfilled') setMatrix(mRes.value.data);
    } finally { setLoading(false); }
  }, [onAdminError]);
  useEffect(() => { load(); }, [load]);

  const applyRole = async () => {
    if (!confirm) return;
    setSaving(true);
    try {
      await admin.setAdminRole(confirm.row.id, { role: confirm.newRole || null });
      toast.success(confirm.newRole ? `Role set to ${ROLE_LABELS[confirm.newRole]}` : 'Admin access revoked');
      setConfirm(null);
      load();
    } catch (e) { onAdminError?.(e, 'Failed to update role'); }
    finally { setSaving(false); }
  };

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2} flexWrap="wrap" gap={1}>
        <Box>
          <Typography variant="h6" fontWeight={700}>Roles &amp; Access</Typography>
          <Typography variant="caption" color="text.secondary">
            Assign platform-admin roles. Only a Super Admin can manage roles, secrets, platform config and pricing.
          </Typography>
        </Box>
        <Stack direction="row" gap={1}>
          <Button size="small" variant="outlined" onClick={() => setShowMatrix(s => !s)}>
            {showMatrix ? 'Hide' : 'Show'} permission matrix
          </Button>
          <Button size="small" startIcon={<Refresh />} onClick={load}>Refresh</Button>
        </Stack>
      </Stack>

      <Alert severity="info" sx={{ mb: 2, borderRadius: 2 }}>
        Bootstrap admins (listed in the <code>ADMIN_EMAILS</code> environment variable) are always Super Admin and
        can only be changed via that env var. Grant a role to any user below to make them an admin without touching env.
      </Alert>

      {showMatrix && matrix && (
        <Paper variant="outlined" sx={{ p: 2, mb: 2, borderRadius: 2 }}>
          <Typography variant="subtitle2" fontWeight={700} mb={1}>Permission matrix</Typography>
          <Stack spacing={1.5}>
            {Object.entries(matrix.roles || {}).map(([role, info]) => (
              <Box key={role}>
                <Stack direction="row" alignItems="center" gap={1} mb={0.5}>
                  <Chip label={info.label} size="small" color={ROLE_COLORS[role] || 'default'} />
                  <Typography variant="caption" color="text.secondary">{info.description}</Typography>
                </Stack>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {(info.permissions || []).map(p => (
                    <Chip key={p} label={p} size="small" variant="outlined"
                      color={(matrix.super_only || []).includes(p) ? 'error' : 'default'}
                      sx={{ fontFamily: 'monospace', fontSize: 11 }} />
                  ))}
                </Box>
              </Box>
            ))}
          </Stack>
        </Paper>
      )}

      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Email</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>2FA</TableCell>
              <TableCell>Source</TableCell>
              <TableCell align="right">Change role</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={6} align="center"><CircularProgress size={24} sx={{ my: 3 }} /></TableCell></TableRow>
            ) : !admins || admins.length === 0 ? (
              <EmptyRow cols={6} message="No admins found" />
            ) : admins.map((row, i) => {
              const locked = row.is_bootstrap || (row.id && row.id === currentUserId) || !row.id;
              const lockReason = row.is_bootstrap
                ? 'Bootstrap admin — manage via ADMIN_EMAILS env var'
                : (row.id === currentUserId ? 'You cannot change your own role' : 'User has not registered yet');
              return (
                <TableRow key={row.id || `env-${i}`} hover>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{row.email}</TableCell>
                  <TableCell>{row.full_name || '—'}</TableCell>
                  <TableCell><Chip label={ROLE_LABELS[row.role] || row.role} size="small" color={ROLE_COLORS[row.role] || 'default'} /></TableCell>
                  <TableCell>{row.totp_enabled ? <CheckCircle color="success" fontSize="small" /> : <Cancel color="disabled" fontSize="small" />}</TableCell>
                  <TableCell><Typography variant="caption" color="text.secondary">{row.source === 'env_allowlist' ? 'env allowlist' : 'assigned'}</Typography></TableCell>
                  <TableCell align="right">
                    {locked ? (
                      <Tooltip title={lockReason}><span><Lock fontSize="small" color="disabled" /></span></Tooltip>
                    ) : (
                      <FormControl size="small" sx={{ minWidth: 150 }}>
                        <Select
                          value={row.role || ''}
                          displayEmpty
                          onChange={(e) => setConfirm({ row, newRole: e.target.value })}
                        >
                          {ASSIGNABLE_ROLES.map(r => <MenuItem key={r} value={r}>{ROLE_LABELS[r]}</MenuItem>)}
                          <Divider />
                          <MenuItem value=""><em>Revoke admin access</em></MenuItem>
                        </Select>
                      </FormControl>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={!!confirm} onClose={() => !saving && setConfirm(null)}>
        <DialogTitle>Change admin role?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            {confirm?.newRole
              ? <>Set <b>{confirm?.row?.email}</b> to <b>{ROLE_LABELS[confirm?.newRole]}</b>?</>
              : <>Revoke <b>all admin access</b> from <b>{confirm?.row?.email}</b>?</>}
          </Typography>
          <Alert severity="warning" sx={{ mt: 2 }}>
            This change takes effect immediately and is recorded in the audit log.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(null)} disabled={saving}>Cancel</Button>
          <Button onClick={applyRole} variant="contained" color={confirm?.newRole ? 'primary' : 'error'} disabled={saving}>
            {saving ? 'Saving…' : (confirm?.newRole ? 'Confirm' : 'Revoke')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function _initialPerms() {
  try { return JSON.parse(localStorage.getItem('user'))?.admin_permissions || null; }
  catch { return null; }
}

export default function AdminPanel() {
  const navigate = useNavigate();
  const [perms, setPerms] = useState(_initialPerms);
  const [me, setMe] = useState(null);

  useEffect(() => {
    import('../services/api').then(({ auth: authApi }) => {
      authApi.getMe()
        .then(r => {
          const u = r.data?.user || {};
          if (!u.is_admin) navigate('/dashboard', { replace: true });
          localStorage.setItem('user', JSON.stringify({ ...u }));
          setMe(u);
          setPerms(u.admin_permissions || []);
        })
        .catch(() => navigate('/dashboard', { replace: true }));
    });
  }, [navigate]);

  const [activeTab, setActiveTab] = useState(0);
  const [stats, setStats] = useState(null);
  const [botStats, setBotStats] = useState(null);
  const [revenue, setRevenue] = useState(null);
  const [health, setHealth] = useState(null);
  const [featureAdoption, setFeatureAdoption] = useState(null);
  const [dashLoading, setDashLoading] = useState(true);
  const [accessError, setAccessError] = useState(null);
  const accessErrorShown = useRef(false);

  const handleAdminError = useCallback((err, fallbackMsg) => {
    const { message, is403 } = parseApiError(err);
    if (is403) {
      if (!accessErrorShown.current) { accessErrorShown.current = true; setAccessError(message); }
    } else {
      toast.error(fallbackMsg || message);
    }
  }, []);

  const fetchDashboard = useCallback(async () => {
    setDashLoading(true);
    try {
      const [statsRes, botStatsRes, revenueRes, healthRes, adoptionRes] = await Promise.allSettled([
        admin.getStats(),
        admin.getTelegramGroupStats(),
        admin.getRevenue(),
        admin.getHealth(),
        admin.getFeatureAdoption(),
      ]);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data.stats);
      if (botStatsRes.status === 'fulfilled') setBotStats(botStatsRes.value.data.stats);
      if (revenueRes.status === 'fulfilled') setRevenue(revenueRes.value.data.revenue);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value.data);
      if (adoptionRes.status === 'fulfilled') setFeatureAdoption(adoptionRes.value.data);
      // Surface 403 from stats if it fires
      if (statsRes.status === 'rejected') handleAdminError(statsRes.reason, 'Failed to load stats');
    } finally {
      setDashLoading(false);
    }
  }, [handleAdminError]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  const can = useCallback((p) => !p || (perms || []).includes(p), [perms]);

  // Tab definitions, each gated by an RBAC permission. Tabs the current admin
  // role cannot access are hidden entirely (and the API also enforces it).
  const tabDefs = useMemo(() => ([
    { key: 'dashboard', label: 'Dashboard', icon: <TrendingUp fontSize="small" />, permission: 'analytics.view',
      render: () => <DashboardTab stats={stats} botStats={botStats} revenue={revenue} health={health} featureAdoption={featureAdoption} loading={dashLoading} onRefresh={fetchDashboard} /> },
    { key: 'users', label: 'Users', icon: <People fontSize="small" />, permission: 'users.view',
      render: () => <UsersTab onAdminError={handleAdminError} /> },
    { key: 'groups', label: 'TG Groups', icon: <Groups fontSize="small" />, permission: 'groups.view',
      render: () => <TelegramGroupsTab onAdminError={handleAdminError} /> },
    { key: 'bots', label: 'Custom Bots', icon: <SmartToy fontSize="small" />, permission: 'bots.view',
      render: () => <CustomBotsTab onAdminError={handleAdminError} /> },
    { key: 'suspicious', label: 'Suspicious', icon: <Warning fontSize="small" />, permission: 'fraud.view',
      render: () => <SuspiciousTab onAdminError={handleAdminError} /> },
    { key: 'referrals', label: 'Referrals', icon: <VerifiedUser fontSize="small" />, permission: 'referrals.manage',
      render: () => <ReferralsTab onAdminError={handleAdminError} /> },
    { key: 'directory', label: 'Directory', icon: <FolderOpen fontSize="small" />, permission: 'moderation.view',
      render: () => <DirectoryTab onAdminError={handleAdminError} /> },
    { key: 'announce', label: 'Announce', icon: <Campaign fontSize="small" />, permission: 'announcements.manage',
      render: () => <AnnouncementsTab onAdminError={handleAdminError} /> },
    { key: 'audit', label: 'Audit Log', icon: <History fontSize="small" />, permission: 'audit.view',
      render: () => <AuditLogTab onAdminError={handleAdminError} /> },
    { key: 'reports', label: 'Reports', icon: <Flag fontSize="small" />, permission: 'moderation.view',
      render: () => <ReportsTab onAdminError={handleAdminError} /> },
    { key: 'promo', label: 'Promo Codes', icon: <Payment fontSize="small" />, permission: 'billing.view',
      render: () => <PromoCodesTab onAdminError={handleAdminError} /> },
    { key: 'pricing', label: 'Pricing', icon: <MoneyIcon fontSize="small" />, permission: 'pricing.manage',
      render: () => <PricingTab onAdminError={handleAdminError} /> },
    { key: 'bothealth', label: 'Bot Health', icon: <MonitorHeart fontSize="small" />, permission: 'health.view',
      render: () => <BotHealthTab onAdminError={handleAdminError} /> },
    { key: 'diagnostics', label: 'Diagnostics', icon: <NetworkCheck fontSize="small" />, permission: 'health.view',
      render: () => <DiagnosticsTab onAdminError={handleAdminError} /> },
    { key: 'ai', label: 'AI', icon: <Psychology fontSize="small" />, permission: 'ai.manage',
      render: () => <AITab onAdminError={handleAdminError} /> },
    { key: 'config', label: 'Configuration', icon: <Tune fontSize="small" />, permission: 'config.manage',
      render: () => <ConfigurationTab onAdminError={handleAdminError} /> },
    { key: 'secrets', label: 'Secrets & Keys', icon: <Key fontSize="small" />, permission: 'secrets.manage',
      render: () => <SecretsTab onAdminError={handleAdminError} /> },
    { key: 'roles', label: 'Roles & Access', icon: <Security fontSize="small" />, permission: 'roles.manage',
      render: () => <RolesTab onAdminError={handleAdminError} currentUserId={me?.id} /> },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ]), [stats, botStats, revenue, health, featureAdoption, dashLoading, fetchDashboard, handleAdminError, me]);

  const visibleTabs = useMemo(() => tabDefs.filter(t => can(t.permission)), [tabDefs, can]);

  // Keep activeTab in range when the visible set changes.
  useEffect(() => {
    if (activeTab >= visibleTabs.length) setActiveTab(0);
  }, [visibleTabs.length, activeTab]);

  // Keyboard shortcuts: 1–9 to switch visible tabs, R to refresh dashboard
  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= visibleTabs.length) { setActiveTab(num - 1); return; }
      if (e.key === 'r' || e.key === 'R') { fetchDashboard(); toast.info('Dashboard refreshed'); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [fetchDashboard, visibleTabs.length]);

  const activeRole = me?.admin_role;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate('/dashboard')} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          <Typography variant="h6" fontWeight={600} flex={1}>Admin Panel</Typography>
          {activeRole && (
            <Chip label={(ROLE_LABELS[activeRole] || 'ADMIN').toUpperCase()} size="small"
              color={ROLE_COLORS[activeRole] || 'error'} sx={{ fontWeight: 700 }} />
          )}
        </Toolbar>
      </AppBar>

      <Box sx={{ maxWidth: 1400, mx: 'auto', p: { xs: 2, md: 3 } }}>

        {accessError && (
          <Alert
            severity="error" icon={<Lock />} sx={{ mb: 3, borderRadius: 2 }}
            action={
              <Button color="inherit" size="small" onClick={() => { accessErrorShown.current = false; setAccessError(null); fetchDashboard(); }}>
                Retry
              </Button>
            }
          >
            <Typography variant="body2" fontWeight={700}>Admin Access Denied</Typography>
            <Typography variant="caption">{accessError}</Typography>
          </Alert>
        )}

        {/* Tab navigation — only tabs the current role can access are shown */}
        <Paper sx={{ mb: 3 }}>
          <Tabs
            value={Math.min(activeTab, Math.max(0, visibleTabs.length - 1))}
            onChange={(_, v) => setActiveTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            allowScrollButtonsMobile
            sx={{ borderBottom: 1, borderColor: 'divider' }}
          >
            {visibleTabs.map((t) => (
              <Tab key={t.key} icon={t.icon} iconPosition="start" label={t.label} sx={{ minHeight: 48, fontSize: 13 }} />
            ))}
          </Tabs>
        </Paper>

        {perms === null ? (
          <Box display="flex" justifyContent="center" py={6}><CircularProgress /></Box>
        ) : visibleTabs.length === 0 ? (
          <Alert severity="info" sx={{ borderRadius: 2 }}>
            Your admin role has no sections enabled. Contact a Super Admin if you believe this is a mistake.
          </Alert>
        ) : (
          <Box pt={3}>{visibleTabs[activeTab]?.render?.()}</Box>
        )}

      </Box>
    </Box>
  );
}
