import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Grid, Stack, Chip, Button, CircularProgress, LinearProgress,
  Breadcrumbs, Link as MuiLink, Paper, Alert, Tabs, Tab, Card, CardContent,
  Table, TableHead, TableBody, TableRow, TableCell, TableContainer, Divider,
} from '@mui/material';
import {
  ArrowBack, Block, CheckCircle, Refresh, OpenInNew, SmartToy,
} from '@mui/icons-material';
import { useParams, useNavigate, Link as RouterLink } from 'react-router-dom';
import { toast } from 'react-toastify';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip as ReTooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { admin } from '../services/api';
import { Field, SectionTitle, fmtDate, fmtDateTime, usd } from '../components/AdminDetailKit';

const GRADE_COLOR = (g) =>
  g === 'healthy' ? 'success' : g === 'warning' ? 'warning' : g === 'critical' ? 'error' : 'default';

function StatCard({ label, value, sub, color }) {
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="h6" fontWeight={700} color={color || 'text.primary'} lineHeight={1.2}>{value}</Typography>
        {sub && <Typography variant="caption" color="text.disabled">{sub}</Typography>}
      </CardContent>
    </Card>
  );
}

const TABS = [
  'Overview', 'Owner', 'Connected Groups', 'Reach & Members', 'Health',
  'Feature Usage', 'AI Usage', 'Config', 'Errors & Logs', 'Actions',
];

export default function AdminCustomBotDetail() {
  const { botId } = useParams();
  const navigate = useNavigate();
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(0);
  const [action, setAction] = useState('');

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await admin.getCustomBotDetail(botId);
      setD(res.data.bot);
    } catch (err) {
      toast.error(err?.response?.data?.error || 'Failed to load bot detail');
    } finally { setLoading(false); }
  }, [botId]);

  useEffect(() => { load(); }, [load]);

  const run = async (key, fn, okMsg) => {
    setAction(key);
    try { await fn(); if (okMsg) toast.success(okMsg); await load(true); }
    catch (err) { toast.error(err?.response?.data?.error || 'Action failed'); }
    finally { setAction(''); }
  };

  const handlePing = () => run('ping', async () => {
    const res = await admin.pingCustomBot(botId);
    if (res.data?.ok) toast.success(`@${res.data.username || d?.bot_username} is reachable`);
    else toast.error(res.data?.error || 'Bot unreachable');
  });
  const handleClear = () => run('clear', () => admin.clearBotHealth('custom', botId), 'Health state cleared');
  const handleEnable = () => run('enable', () => admin.enableCustomBot(botId), 'Bot enabled');
  const handleDisable = () => {
    if (!window.confirm(`Disable bot "${d?.bot_username || botId}"?`)) return;
    run('disable', () => admin.disableCustomBot(botId), 'Bot disabled');
  };

  if (loading && !d) return <Box display="flex" justifyContent="center" mt={8}><CircularProgress /></Box>;
  if (!d) {
    return (
      <Box p={3}>
        <Button startIcon={<ArrowBack />} onClick={() => navigate('/admin/bots/bots')}>Back to Custom Bots</Button>
        <Alert severity="error" sx={{ mt: 2 }}>Bot not found.</Alert>
      </Box>
    );
  }

  const h = d.health || {};
  const fu = d.feature_usage || {};
  const ai = d.ai_usage || null;
  const groups = d.connected_groups || [];
  const featureRows = Object.entries(fu.by_feature || {}).map(([feature, count]) => ({ feature, count }));
  const groupBars = groups
    .map((g) => ({ name: (g.title || '').slice(0, 16) || g.telegram_group_id, members: g.member_count || 0 }))
    .filter((g) => g.members > 0).slice(0, 12);

  return (
    <Box sx={{ maxWidth: 1100, mx: 'auto', p: { xs: 2, sm: 3 }, pb: 'var(--bottom-nav-clearance, 24px)' }}>
      <Breadcrumbs sx={{ mb: 1 }}>
        <MuiLink component={RouterLink} to="/admin" underline="hover" color="inherit">Admin</MuiLink>
        <MuiLink component={RouterLink} to="/admin/bots/bots" underline="hover" color="inherit">Custom Bots</MuiLink>
        <Typography color="text.primary">{d.bot_username ? `@${d.bot_username}` : `Bot #${d.id}`}</Typography>
      </Breadcrumbs>

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }} mb={2}>
        <Button startIcon={<ArrowBack />} onClick={() => navigate('/admin/bots/bots')} size="small">Back</Button>
        <Stack direction="row" spacing={1} alignItems="center" flex={1} minWidth={0}>
          <SmartToy sx={{ color: 'text.secondary' }} />
          <Box minWidth={0}>
            <Typography variant="h5" fontWeight={700} noWrap>{d.bot_username ? `@${d.bot_username}` : `Bot #${d.id}`}</Typography>
            <Typography variant="caption" color="text.secondary">{d.bot_name} · ID {d.id}</Typography>
          </Box>
        </Stack>
        {h.grade && <Chip size="small" label={h.grade} color={GRADE_COLOR(h.grade)} />}
        <Chip size="small" variant="outlined" label={d.status || 'active'} />
      </Stack>

      {loading && <LinearProgress sx={{ mb: 1 }} />}

      <Paper variant="outlined" sx={{ mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto" allowScrollButtonsMobile>
          {TABS.map((t) => <Tab key={t} label={t} sx={{ minHeight: 44, fontSize: 13 }} />)}
        </Tabs>
      </Paper>

      {/* Overview */}
      {tab === 0 && (
        <Box>
          <Grid container spacing={1.5}>
            <Grid item xs={6} sm={3}><StatCard label="Status" value={d.status || 'active'} /></Grid>
            <Grid item xs={6} sm={3}><StatCard label="Health" value={h.grade || 'unknown'} color={`${GRADE_COLOR(h.grade)}.main`} /></Grid>
            <Grid item xs={6} sm={3}><StatCard label="Groups" value={d.groups_count ?? 0} /></Grid>
            <Grid item xs={6} sm={3}><StatCard label="Members managed" value={(d.members_managed || 0).toLocaleString()} /></Grid>
            <Grid item xs={6} sm={3}><StatCard label="Errors 24h" value={h.errors_24h ?? 0} color={h.errors_24h ? 'error.main' : undefined} /></Grid>
            <Grid item xs={6} sm={3}><StatCard label="Errors 7d" value={h.errors_7d ?? 0} /></Grid>
            <Grid item xs={6} sm={3}><StatCard label="Last ping" value={h.last_ping_at ? fmtDate(h.last_ping_at) : 'never'} /></Grid>
            <Grid item xs={6} sm={3}><StatCard label="Feature events" value={(fu.total || 0).toLocaleString()} /></Grid>
          </Grid>
          <SectionTitle>Owner</SectionTitle>
          <Grid container spacing={1.5}>
            <Grid item xs={12} sm={5}><Field label="Owner" value={d.owner?.email || d.owner?.name || `User ${d.owner?.user_id}`} /></Grid>
            <Grid item xs={6} sm={4}><Field label="Telegram" value={d.owner?.telegram_username ? `@${d.owner.telegram_username}` : '—'} /></Grid>
            <Grid item xs={6} sm={3}><Field label="Tier" value={(d.owner?.tier || 'free').toUpperCase()} /></Grid>
          </Grid>
        </Box>
      )}

      {/* Owner */}
      {tab === 1 && (
        <Box>
          <Grid container spacing={1.5}>
            <Grid item xs={12} sm={6}><Field label="Email" value={d.owner?.email} /></Grid>
            <Grid item xs={12} sm={6}><Field label="Name" value={d.owner?.name} /></Grid>
            <Grid item xs={6} sm={4}><Field label="Telegram" value={d.owner?.telegram_username ? `@${d.owner.telegram_username}` : '—'} /></Grid>
            <Grid item xs={6} sm={4}><Field label="Tier" value={(d.owner?.tier || 'free').toUpperCase()} /></Grid>
            <Grid item xs={6} sm={4}><Field label="User ID" value={d.owner?.user_id} mono /></Grid>
          </Grid>
          {d.owner?.user_id && (
            <Button sx={{ mt: 2 }} size="small" variant="outlined" endIcon={<OpenInNew />}
              onClick={() => navigate(`/admin/users/${d.owner.user_id}`)}>
              Open owner profile
            </Button>
          )}
        </Box>
      )}

      {/* Connected Groups */}
      {tab === 2 && (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Group</TableCell><TableCell>Status</TableCell><TableCell align="right">Members</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {groups.length === 0
                ? <TableRow><TableCell colSpan={3}><Typography variant="caption" color="text.disabled">No connected groups.</Typography></TableCell></TableRow>
                : groups.map((g) => (
                  <TableRow key={g.telegram_group_id} hover>
                    <TableCell><Typography variant="body2" noWrap sx={{ maxWidth: 360 }}>{g.title || g.telegram_group_id}</Typography></TableCell>
                    <TableCell><Chip size="small" label={g.bot_status} color={g.bot_status === 'active' ? 'success' : 'default'} /></TableCell>
                    <TableCell align="right">{(g.member_count || 0).toLocaleString()}</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Reach & Members */}
      {tab === 3 && (
        <Box>
          <Grid container spacing={1.5} mb={2}>
            <Grid item xs={6} sm={4}><StatCard label="Connected groups" value={d.groups_count ?? 0} /></Grid>
            <Grid item xs={6} sm={4}><StatCard label="Members managed" value={(d.members_managed || 0).toLocaleString()} /></Grid>
            <Grid item xs={6} sm={4}><StatCard label="Avg / group" value={d.groups_count ? Math.round((d.members_managed || 0) / d.groups_count).toLocaleString() : 0} /></Grid>
          </Grid>
          <SectionTitle>Members per group</SectionTitle>
          {groupBars.length === 0 ? (
            <Typography variant="caption" color="text.disabled">No member-count data yet.</Typography>
          ) : (
            <Box sx={{ height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={groupBars} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={60} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <ReTooltip />
                  <Bar dataKey="members" fill="#3d8ef8" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          )}
        </Box>
      )}

      {/* Health */}
      {tab === 4 && (
        <Box>
          <Grid container spacing={1.5}>
            <Grid item xs={6} sm={3}><Field label="Grade" value={h.grade} /></Grid>
            <Grid item xs={6} sm={3}><Field label="Consec. failures" value={h.consecutive_failures ?? 0} /></Grid>
            <Grid item xs={6} sm={3}><Field label="Errors 24h" value={h.errors_24h ?? 0} /></Grid>
            <Grid item xs={6} sm={3}><Field label="Errors 7d" value={h.errors_7d ?? 0} /></Grid>
            <Grid item xs={12} sm={6}><Field label="Last ping" value={h.last_ping_at ? fmtDateTime(h.last_ping_at) : 'never'} /></Grid>
            <Grid item xs={12} sm={6}><Field label="Last successful ping" value={h.last_successful_ping ? fmtDateTime(h.last_successful_ping) : 'never'} /></Grid>
            <Grid item xs={12}><Field label="Last error" value={h.last_error || '—'} /></Grid>
          </Grid>
        </Box>
      )}

      {/* Feature Usage */}
      {tab === 5 && (
        <Box>
          {featureRows.length === 0 ? (
            <Typography variant="caption" color="text.disabled">
              No per-bot usage attributed yet. {fu.note}
            </Typography>
          ) : (
            <>
              <SectionTitle sx={{ mt: 0 }}>By feature ({(fu.total || 0).toLocaleString()} events)</SectionTitle>
              <Box sx={{ height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={featureRows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} />
                    <XAxis type="number" tick={{ fontSize: 10 }} />
                    <YAxis type="category" dataKey="feature" tick={{ fontSize: 11 }} width={90} />
                    <ReTooltip />
                    <Bar dataKey="count" fill="#9d6cf7" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </>
          )}
        </Box>
      )}

      {/* AI Usage */}
      {tab === 6 && (
        <Box>
          {ai && ai.total_tokens ? (
            <Grid container spacing={1.5}>
              <Grid item xs={6} sm={3}><StatCard label="Total tokens" value={(ai.total_tokens || 0).toLocaleString()} /></Grid>
              <Grid item xs={6} sm={3}><StatCard label="Input tokens" value={(ai.input_tokens || 0).toLocaleString()} /></Grid>
              <Grid item xs={6} sm={3}><StatCard label="Output tokens" value={(ai.output_tokens || 0).toLocaleString()} /></Grid>
              <Grid item xs={6} sm={3}><StatCard label="Cost" value={usd(ai.cost_usd)} color="success.main" /></Grid>
            </Grid>
          ) : (
            <Alert severity="info" variant="outlined">
              AI usage is tracked from the day the usage ledger shipped — no AI spend has been
              attributed to this bot yet.
            </Alert>
          )}
        </Box>
      )}

      {/* Config */}
      {tab === 7 && (
        <Grid container spacing={1.5}>
          <Grid item xs={6} sm={4}><Field label="Token" value={d.config?.token_configured ? 'Configured (hidden)' : 'Missing'} /></Grid>
          <Grid item xs={6} sm={4}><Field label="Status" value={d.config?.status} /></Grid>
          <Grid item xs={6} sm={4}><Field label="Revenue" value="Not tracked per-bot" /></Grid>
          <Grid item xs={6} sm={6}><Field label="Created" value={d.config?.created_at ? fmtDateTime(d.config.created_at) : '—'} /></Grid>
          <Grid item xs={6} sm={6}><Field label="Updated" value={d.config?.updated_at ? fmtDateTime(d.config.updated_at) : '—'} /></Grid>
        </Grid>
      )}

      {/* Errors & Logs */}
      {tab === 8 && (
        <Box>
          {(h.recent_errors || []).length === 0 ? (
            <Typography variant="caption" color="text.disabled">No recent errors logged.</Typography>
          ) : (
            <Stack spacing={0.75}>
              {h.recent_errors.map((e) => (
                <Paper key={e.id} variant="outlined" sx={{ p: 1 }}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                    <Chip size="small" label={e.severity || 'info'} color={e.severity === 'critical' ? 'error' : e.severity === 'warning' ? 'warning' : 'default'} />
                    {e.category && <Chip size="small" variant="outlined" label={e.category} />}
                    <Typography variant="caption" color="text.disabled">{fmtDateTime(e.created_at)}</Typography>
                  </Stack>
                  <Typography variant="body2" sx={{ mt: 0.5 }}>{e.detail}</Typography>
                </Paper>
              ))}
            </Stack>
          )}
        </Box>
      )}

      {/* Actions */}
      {tab === 9 && (
        <Box>
          <SectionTitle sx={{ mt: 0 }}>Operational actions</SectionTitle>
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
            <Button variant="outlined" startIcon={action === 'ping' ? <CircularProgress size={16} /> : <Refresh />}
              disabled={!!action} onClick={handlePing}>Ping</Button>
            <Button variant="outlined" color="success" startIcon={<CheckCircle />}
              disabled={!!action || (h.grade === 'healthy' || h.grade === 'unknown' || !h.grade)} onClick={handleClear}>
              Clear errors
            </Button>
            {d.status === 'inactive'
              ? <Button variant="outlined" color="success" startIcon={<CheckCircle />} disabled={!!action} onClick={handleEnable}>Enable</Button>
              : <Button variant="outlined" color="error" startIcon={<Block />} disabled={!!action} onClick={handleDisable}>Disable</Button>}
          </Stack>
          <Divider sx={{ my: 2 }} />
          <Typography variant="caption" color="text.disabled">
            Pinging performs a live Telegram getMe reachability test and updates the health state.
            Clearing errors resets the bot's accumulated failure counters after a fix.
          </Typography>
        </Box>
      )}
    </Box>
  );
}
