import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, CardActionArea, Grid, CircularProgress, Alert, Button,
  ToggleButton, ToggleButtonGroup, Stack,
} from '@mui/material';
import { OpenInNew, TrendingUp, TrendingDown, TrendingFlat } from '@mui/icons-material';
import {
  ResponsiveContainer, BarChart, Bar, AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, Tooltip,
  CartesianGrid, Legend,
} from 'recharts';
import { admin } from '../../services/api';

const DAY_RANGES = [
  { key: 7, label: '7D' }, { key: 30, label: '30D' }, { key: 90, label: '90D' }, { key: 365, label: '1Y' },
];
const C = {
  managed: '#2196f3', verified: '#22c55e', free: '#64748b', trial: '#f59e0b', paid: '#7c4dff',
  official: '#8b5cf6', custom: '#00bcd4',
};
const BOT_STATUS_COLORS = { active: '#22c55e', paused: '#f59e0b', error: '#ef4444', inactive: '#64748b' };
// Google Analytics realtime is the source of truth for "people on the site right now".
const GA_URL = process.env.REACT_APP_GA_DASHBOARD_URL || 'https://analytics.google.com/analytics/web/';

// Shared chart look: soft tooltip card, horizontal grid only.
const TT = {
  contentStyle: { borderRadius: 8, border: '1px solid rgba(128,128,128,0.25)', fontSize: 12, boxShadow: '0 6px 20px rgba(0,0,0,0.25)' },
  cursor: { fill: 'rgba(128,128,128,0.08)' },
};
const GRID = { strokeDasharray: '3 3', opacity: 0.25, vertical: false };
const Gradient = ({ id, color, top = 0.9, bottom = 0.35 }) => (
  <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stopColor={color} stopOpacity={top} />
    <stop offset="100%" stopColor={color} stopOpacity={bottom} />
  </linearGradient>
);

const fmtDay = (iso) => new Date(iso + 'T00:00:00Z').toLocaleDateString([], { month: 'short', day: 'numeric', timeZone: 'UTC' });
const n = (v) => (v == null ? '—' : Number(v).toLocaleString());
const signed = (v) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${Number(v).toLocaleString()}`);

function usePlatformOverview() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const res = await admin.getPlatformOverview(days, { signal });
      setData(res.data);
    } catch (e) {
      if (e?.code === 'ERR_CANCELED') return;
      setError(e?.response?.data?.error || 'Could not load platform overview.');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  return { days, setDays, data, loading, error, reload: () => load() };
}

function RangeToggle({ days, setDays }) {
  return (
    <ToggleButtonGroup size="small" exclusive value={days} onChange={(_, v) => v && setDays(v)} aria-label="Time range">
      {DAY_RANGES.map(r => <ToggleButton key={r.key} value={r.key} sx={{ px: 1.5, minHeight: 36 }}>{r.label}</ToggleButton>)}
    </ToggleButtonGroup>
  );
}

/** Real change over a window. delta null = unknown (renders nothing); 0 = "no change". */
export function TrendChip({ delta, label }) {
  if (delta == null) return null;
  const up = delta > 0, down = delta < 0;
  const Icon = up ? TrendingUp : down ? TrendingDown : TrendingFlat;
  const color = up ? '#22c55e' : down ? '#ef4444' : '#94a3b8';
  return (
    <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.25 }}>
      <Icon sx={{ fontSize: 16, color }} />
      <Typography variant="caption" sx={{ color, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
        {delta === 0 ? 'No change' : `${up ? '+' : '−'}${Math.abs(delta).toLocaleString()}`}
      </Typography>
      {label && <Typography variant="caption" color="text.disabled">{label}</Typography>}
    </Stack>
  );
}

// onClick makes the whole tile a button (keyboard + screen-reader friendly via CardActionArea).
// trend = { delta, label } shows real change over a window (see TrendChip).
export function Tile({ label, value, sub, color, onClick, trend }) {
  const body = (
    <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h5" fontWeight={700} sx={{ color, fontVariantNumeric: 'tabular-nums' }}>{value}</Typography>
      {trend && <TrendChip delta={trend.delta} label={trend.label} />}
      {sub && <Typography variant="caption" color="text.secondary" display="block">{sub}</Typography>}
      {onClick && <Typography variant="caption" color="primary.main">View →</Typography>}
    </CardContent>
  );
  return (
    <Card variant="outlined" sx={{
      height: '100%', borderRadius: 2, borderTop: `3px solid ${color || 'rgba(128,128,128,0.35)'}`,
      transition: 'box-shadow .15s, transform .15s',
      ...(onClick ? { '&:hover': { boxShadow: 4, transform: 'translateY(-1px)' } } : {}),
    }}>
      {onClick ? <CardActionArea onClick={onClick} sx={{ height: '100%' }}>{body}</CardActionArea> : body}
    </Card>
  );
}

function ChartCard({ title, subtitle, children, empty }) {
  return (
    <Card variant="outlined" sx={{ height: '100%', borderRadius: 2 }}>
      <CardContent>
        <Typography variant="subtitle2" fontWeight={600}>{title}</Typography>
        {subtitle && <Typography variant="caption" color="text.secondary" display="block">{subtitle}</Typography>}
        <Box sx={{ height: 240, mt: 1 }}>
          {empty
            ? <Typography variant="body2" color="text.secondary" pt={4} textAlign="center">{empty}</Typography>
            : children}
        </Box>
      </CardContent>
    </Card>
  );
}

function Shell({ state, children }) {
  const { data, loading, error, reload } = state;
  if (error) return <Alert severity="error" action={<Button color="inherit" size="small" onClick={reload}>Retry</Button>}>{error}</Alert>;
  if (!data) return <Box display="flex" justifyContent="center" py={4}><CircularProgress size={28} /></Box>;
  return <Box sx={{ opacity: loading ? 0.6 : 1, transition: 'opacity .15s' }}>{children}</Box>;
}

/** Users section: website accounts vs members managed by our bots. */
export function ManagedMembersPanel({ onOpen }) {
  const open = (key, filter) => (onOpen ? () => onOpen(key, filter || {}) : undefined);
  const state = usePlatformOverview();
  const { data, days, setDays } = state;
  const tr7 = (k) => (data?.trends && data.trends[k] != null ? { delta: data.trends[k], label: `vs ${data.trends.window_days}d ago` } : null);
  const t = data?.totals;
  const hist = (data?.history || []).map(h => ({ ...h, label: fmtDay(h.day) }));
  const latest = hist.length ? hist[hist.length - 1] : null;

  return (
    <Card sx={{ mb: 3, borderRadius: 2 }}>
      <CardContent>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} justifyContent="space-between" mb={2}>
          <Box>
            <Typography variant="subtitle2" color="text.secondary" fontWeight={600} textTransform="uppercase" letterSpacing={1}>
              Managed members
            </Typography>
            <Typography variant="caption" color="text.secondary">
              People inside groups our bots protect (not website accounts). Verified = passed our bot&apos;s verification.
            </Typography>
          </Box>
          <RangeToggle days={days} setDays={setDays} />
        </Stack>
        <Shell state={state}>
          <Grid container spacing={2} mb={2}>
            <Grid item xs={6} md><Tile label="Members managed" value={n(t?.managed_members)} color={C.managed} sub={`in ${n(t?.groups_total)} active groups`} trend={tr7('managed_members')} onClick={open('groups')} /></Grid>
            <Grid item xs={6} md><Tile label="Verified by bot" value={n(t?.verified_members)} color={C.verified}
              sub={t?.managed_members ? `${Math.round((t.verified_members * 100) / t.managed_members)}% of managed` : ''} trend={tr7('verified_members')} onClick={open('proof')} /></Grid>
            <Grid item xs={6} md><Tile label="Website accounts" value={n(t?.users_total)} sub={`${n(t?.users_paid)} paid · ${n(t?.users_trial)} on trial`} trend={tr7('users_total')} onClick={open('users')} /></Grid>
            <Grid item xs={6} md><Tile label="Official-bot groups" value={n(t?.groups_official)} color={C.official} onClick={open('groups', { bot_type: 'official' })} /></Grid>
            <Grid item xs={6} md><Tile label="Custom-bot groups" value={n(t?.groups_custom)} color={C.custom} onClick={open('groups', { bot_type: 'custom' })} /></Grid>
          </Grid>

          <Grid container spacing={2}>
            <Grid item xs={12} md={7}>
              <ChartCard title="Members managed over time" subtitle="Daily snapshot · UTC"
                empty={hist.length < 2 ? 'History builds up one point per day from the day this shipped.' : null}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={hist} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
                    <defs><Gradient id="gManaged" color={C.managed} top={0.5} bottom={0.02} /><Gradient id="gVerified" color={C.verified} top={0.5} bottom={0.02} /></defs>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip {...TT} />
                    <Legend />
                    <Area type="monotone" dataKey="managed_members" name="Managed" stroke={C.managed} strokeWidth={2} fill="url(#gManaged)" />
                    <Area type="monotone" dataKey="verified_members" name="Verified" stroke={C.verified} strokeWidth={2} fill="url(#gVerified)" />
                  </AreaChart>
                </ResponsiveContainer>
              </ChartCard>
            </Grid>
            <Grid item xs={12} md={5}>
              <ChartCard
                title="Members gained per day"
                subtitle={latest?.managed_gained != null
                  ? `Latest: ${signed(latest.managed_gained)} managed, ${signed(latest.verified_gained)} verified`
                  : 'Difference between daily snapshots'}
                empty={hist.filter(h => h.managed_gained != null).length === 0 ? 'Needs at least two days of snapshots.' : null}
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={hist} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip {...TT} />
                    <Legend />
                    <Bar dataKey="managed_gained" name="Managed" fill={C.managed} radius={[4, 4, 0, 0]} maxBarSize={22} />
                    <Bar dataKey="verified_gained" name="Verified" fill={C.verified} radius={[4, 4, 0, 0]} maxBarSize={22} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </Grid>
          </Grid>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }} mt={2}>
            <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
              Visitors on the site right now come from Google Analytics (Reports → Realtime).
            </Typography>
            <Button size="small" variant="outlined" endIcon={<OpenInNew fontSize="small" />} href={GA_URL} target="_blank" rel="noopener noreferrer">
              Open live traffic
            </Button>
          </Stack>
        </Shell>
      </CardContent>
    </Card>
  );
}

/** Dashboard: plans, trials and custom bots as charts instead of bare numbers. */
export function PlatformCharts({ onOpen }) {
  const open = (key, filter) => (onOpen ? () => onOpen(key, filter || {}) : undefined);
  const PLAN_FILTER = { Free: 'free', Trial: 'trial', Paid: 'pro' };
  const state = usePlatformOverview();
  const { data, days, setDays } = state;
  const tr7 = (k) => (data?.trends && data.trends[k] != null ? { delta: data.trends[k], label: `vs ${data.trends.window_days}d ago` } : null);
  const hist = (data?.history || []).map(h => ({ ...h, label: fmtDay(h.day) }));
  const statusData = Object.entries(data?.custom_bots_by_status || {}).map(([name, value]) => ({ name, value }));
  const perBot = data?.groups_per_custom_bot || [];
  const tr = data?.trials;
  const t = data?.totals;
  const planNow = t ? [
    { name: 'Free', value: t.users_free, color: C.free },
    { name: 'Trial', value: t.users_trial, color: C.trial },
    { name: 'Paid', value: t.users_paid, color: C.paid },
  ].filter(d => d.value > 0) : [];

  return (
    <Card sx={{ mb: 3, borderRadius: 2 }}>
      <CardContent>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} justifyContent="space-between" mb={2}>
          <Typography variant="subtitle2" color="text.secondary" fontWeight={600} textTransform="uppercase" letterSpacing={1}>
            Plans, trials &amp; custom bots
          </Typography>
          <RangeToggle days={days} setDays={setDays} />
        </Stack>
        <Shell state={state}>
          <Grid container spacing={2} mb={2}>
            <Grid item xs={6} md={3}><Tile label="Trials active" value={n(tr?.active)} color={C.trial} sub={`${n(tr?.expiring_7d)} end within 7 days`} trend={tr7('users_trial')} onClick={open('users', { tier: 'trial' })} /></Grid>
            <Grid item xs={6} md={3}><Tile label="Trial → paid" value={tr?.conversion_pct == null ? '—' : `${tr.conversion_pct}%`}
              sub={`${n(tr?.converted_to_paid)} of ${n(tr?.ever_started)} trials`} color={C.paid} /></Grid>
            <Grid item xs={6} md={3}><Tile label="Custom bots active" value={n(t?.custom_bots_active)} color={C.custom} sub={`${n(t?.custom_bots_total)} total`} trend={tr7('custom_bots_active')} onClick={open('bots')} /></Grid>
            <Grid item xs={6} md={3}><Tile label="Custom-bot trials granted" value={n(tr?.custom_bot_trials_active)} sub="admin-approved, 1 bot each" /></Grid>
          </Grid>

          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <ChartCard title="Users by plan over time" subtitle="Free vs signup trial vs paid · daily snapshot"
                empty={hist.length < 2 ? 'History builds up one point per day from the day this shipped.' : null}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={hist} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip {...TT} />
                    <Legend />
                    <Bar dataKey="users_free" name="Free" stackId="p" fill={C.free} />
                    <Bar dataKey="users_trial" name="Trial" stackId="p" fill={C.trial} />
                    <Bar dataKey="users_paid" name="Paid" stackId="p" fill={C.paid} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <ChartCard title="Plan mix now" subtitle={onOpen ? 'Click a slice to list those users' : undefined} empty={planNow.length === 0 ? 'No users yet.' : null}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={planNow} dataKey="value" nameKey="name" innerRadius={45} outerRadius={80} paddingAngle={2}
                      style={{ cursor: onOpen ? 'pointer' : 'default' }}
                      onClick={(d) => onOpen && onOpen('users', { tier: PLAN_FILTER[d.name] || '' })}>
                      {planNow.map(d => <Cell key={d.name} fill={d.color} />)}
                    </Pie>
                    <Tooltip {...TT} /><Legend />
                  </PieChart>
                </ResponsiveContainer>
              </ChartCard>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <ChartCard title="Custom bots by status" empty={statusData.length === 0 ? 'No custom bots.' : null}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={statusData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={80} paddingAngle={2}
                      style={{ cursor: onOpen ? 'pointer' : 'default' }} onClick={() => onOpen && onOpen('bots', {})}>
                      {statusData.map(d => <Cell key={d.name} fill={BOT_STATUS_COLORS[d.name] || '#94a3b8'} />)}
                    </Pie>
                    <Tooltip {...TT} /><Legend />
                  </PieChart>
                </ResponsiveContainer>
              </ChartCard>
            </Grid>
            <Grid item xs={12}>
              <ChartCard title="Groups per custom bot" subtitle="Top 10 by linked groups · members in those groups shown on hover"
                empty={perBot.length === 0 ? 'No custom bot has linked groups yet.' : null}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={perBot} margin={{ top: 8, right: 16, left: -10, bottom: 0 }}>
                    <defs><Gradient id="gBots" color={C.custom} top={0.95} bottom={0.45} /></defs>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="bot" interval={0} angle={-25} textAnchor="end" height={70} tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip {...TT} formatter={(v, name, p) => [`${v} groups · ${n(p.payload.members)} members`, 'Linked']} />
                    <Bar dataKey="groups" name="Groups" fill="url(#gBots)" radius={[4, 4, 0, 0]} maxBarSize={48}
                      style={{ cursor: onOpen ? 'pointer' : 'default' }} onClick={() => onOpen && onOpen('bots', {})} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </Grid>
          </Grid>
        </Shell>
      </CardContent>
    </Card>
  );
}
