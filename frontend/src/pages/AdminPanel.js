import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, AppBar, Toolbar, Typography, IconButton, Card, CardContent,
  Grid, CircularProgress, TextField, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Chip, Button, Dialog,
  DialogTitle, DialogContent, DialogActions, MenuItem, Select,
  FormControl, InputLabel, Pagination, InputAdornment, Tabs, Tab,
  Alert, Tooltip, LinearProgress, Stack,
} from '@mui/material';
import {
  ArrowBack, Search, Block, CheckCircle, Delete, Groups, SmartToy,
  LinkOff, Lock, Warning, TrendingUp, People, AttachMoney,
  History, FolderOpen, Campaign, VerifiedUser, Refresh,
  CheckCircleOutline, Cancel, Circle, Flag,
  Security, AccountTree, TrendingDown, Payment, FileDownload,
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

// ─── Tab panel wrapper ────────────────────────────────────────────────────────

function TabPanel({ value, index, children }) {
  return value === index ? <Box pt={3}>{children}</Box> : null;
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
              <Button variant="outlined" fullWidth onClick={handleUpdateSub} disabled={actionLoading === 'sub'} sx={{ mb: 2 }}>
                {actionLoading === 'sub' ? <CircularProgress size={18} /> : 'Update Subscription'}
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
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

const TABS = [
  { label: 'Dashboard', icon: <TrendingUp fontSize="small" /> },
  { label: 'Users', icon: <People fontSize="small" /> },
  { label: 'TG Groups', icon: <Groups fontSize="small" /> },
  { label: 'Custom Bots', icon: <SmartToy fontSize="small" /> },
  { label: 'Suspicious', icon: <Warning fontSize="small" /> },
  { label: 'Referrals', icon: <VerifiedUser fontSize="small" /> },
  { label: 'Directory', icon: <FolderOpen fontSize="small" /> },
  { label: 'Announce', icon: <Campaign fontSize="small" /> },
  { label: 'Audit Log', icon: <History fontSize="small" /> },
  { label: 'Reports', icon: <Flag fontSize="small" /> },
];

export default function AdminPanel() {
  const navigate = useNavigate();

  useEffect(() => {
    import('../services/api').then(({ auth: authApi }) => {
      authApi.getMe()
        .then(r => {
          const u = r.data?.user || {};
          if (!u.is_admin) navigate('/dashboard', { replace: true });
          localStorage.setItem('user', JSON.stringify({ ...u }));
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

  // Keyboard shortcuts: 1–9 to switch tabs, R to refresh dashboard
  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= TABS.length) { setActiveTab(num - 1); return; }
      if (e.key === 'r' || e.key === 'R') { fetchDashboard(); toast.info('Dashboard refreshed'); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [fetchDashboard]);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate('/dashboard')} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          <Typography variant="h6" fontWeight={600} flex={1}>Admin Panel</Typography>
          <Chip label="ADMIN" size="small" color="error" sx={{ fontWeight: 700 }} />
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

        {/* Tab navigation */}
        <Paper sx={{ mb: 3 }}>
          <Tabs
            value={activeTab}
            onChange={(_, v) => setActiveTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{ borderBottom: 1, borderColor: 'divider' }}
          >
            {TABS.map((t, i) => (
              <Tab key={i} icon={t.icon} iconPosition="start" label={t.label} sx={{ minHeight: 48, fontSize: 13 }} />
            ))}
          </Tabs>
        </Paper>

        <TabPanel value={activeTab} index={0}>
          <DashboardTab
            stats={stats} botStats={botStats} revenue={revenue} health={health}
            featureAdoption={featureAdoption}
            loading={dashLoading} onRefresh={fetchDashboard}
          />
        </TabPanel>

        <TabPanel value={activeTab} index={1}>
          <UsersTab onAdminError={handleAdminError} />
        </TabPanel>

        <TabPanel value={activeTab} index={2}>
          <TelegramGroupsTab onAdminError={handleAdminError} />
        </TabPanel>

        <TabPanel value={activeTab} index={3}>
          <CustomBotsTab onAdminError={handleAdminError} />
        </TabPanel>

        <TabPanel value={activeTab} index={4}>
          <SuspiciousTab onAdminError={handleAdminError} />
        </TabPanel>

        <TabPanel value={activeTab} index={5}>
          <ReferralsTab onAdminError={handleAdminError} />
        </TabPanel>

        <TabPanel value={activeTab} index={6}>
          <DirectoryTab onAdminError={handleAdminError} />
        </TabPanel>

        <TabPanel value={activeTab} index={7}>
          <AnnouncementsTab onAdminError={handleAdminError} />
        </TabPanel>

        <TabPanel value={activeTab} index={8}>
          <AuditLogTab onAdminError={handleAdminError} />
        </TabPanel>

        <TabPanel value={activeTab} index={9}>
          <ReportsTab onAdminError={handleAdminError} />
        </TabPanel>

      </Box>
    </Box>
  );
}
