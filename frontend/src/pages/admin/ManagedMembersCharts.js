import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, CircularProgress, Grid, Stack, ToggleButton, ToggleButtonGroup, Typography,
} from '@mui/material';
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, CartesianGrid, Legend, ReferenceLine,
} from 'recharts';
import { admin } from '../../services/api';

// Series come from the daily snapshot table (UTC days). Definitions: backend/member_series.py.
const RANGES = [
  { key: '1d', label: '1D' }, { key: '7d', label: '7D' }, { key: '30d', label: '30D' }, { key: '12m', label: '12M' },
];
const COLORS = { managed: '#2196f3', verified: '#22c55e', up: '#22c55e', down: '#ef4444', verifiedNet: '#8b5cf6' };
const GRID = { strokeDasharray: '3 3', opacity: 0.25, vertical: false };
const TT = {
  contentStyle: { borderRadius: 8, border: '1px solid rgba(128,128,128,0.25)', fontSize: 12, boxShadow: '0 6px 20px rgba(0,0,0,0.25)' },
  cursor: { fill: 'rgba(128,128,128,0.08)' },
};

const parse = (iso) => new Date(`${iso}T00:00:00Z`);
const num = (v) => (v == null ? 'Unavailable' : Number(v).toLocaleString());
const signed = (v) => (v == null ? 'Unavailable' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toLocaleString()}`);

function labelFor(p, bucket, long = false) {
  const d = parse(p.period_start);
  if (bucket === 'month') {
    const base = d.toLocaleDateString([], { month: 'short', year: long ? 'numeric' : '2-digit', timeZone: 'UTC' });
    return p.partial ? `${base}${long ? ' (to date)' : '*'}` : base;
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', ...(long ? { year: 'numeric' } : {}), timeZone: 'UTC' });
}

export function periodWord(bucket) { return bucket === 'month' ? 'month' : 'day'; }

/** Y domain for a total: padded around the data so small real changes are visible; the chart says it is not zero-based. */
export function paddedDomain(values) {
  const v = values.filter((x) => x != null);
  if (!v.length) return ['auto', 'auto'];
  const lo = Math.min(...v); const hi = Math.max(...v);
  const pad = Math.max((hi - lo) * 0.15, Math.abs(hi) * 0.002, 1);
  return [Math.max(0, Math.floor(lo - pad)), Math.ceil(hi + pad)];   // counts never go below 0
}

function Card2({ title, subtitle, note, children, empty }) {
  return (
    <Card variant="outlined" sx={{ height: '100%', borderRadius: 2 }}>
      <CardContent>
        <Typography variant="subtitle2" fontWeight={600}>{title}</Typography>
        {subtitle && <Typography variant="caption" color="text.secondary" display="block">{subtitle}</Typography>}
        <Box sx={{ height: 240, mt: 1 }}>
          {empty ? <Typography variant="body2" color="text.secondary" pt={4} textAlign="center">{empty}</Typography> : children}
        </Box>
        {note && <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 0.5 }}>{note}</Typography>}
      </CardContent>
    </Card>
  );
}

function TotalTooltip({ active, payload, bucket }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <Box sx={{ ...TT.contentStyle, bgcolor: 'background.paper', p: 1.25, maxWidth: 280 }}>
      <Typography variant="caption" fontWeight={700} display="block">{labelFor(p, bucket, true)}</Typography>
      <Typography variant="caption" display="block">Managed at end of {periodWord(bucket)}: <strong>{num(p.managed)}</strong></Typography>
      <Typography variant="caption" display="block">Verified: <strong>{num(p.verified)}</strong></Typography>
      <Typography variant="caption" color="text.secondary" display="block">Snapshot taken {p.snapshot_day} (UTC){p.partial ? ' · period not complete' : ''}</Typography>
    </Box>
  );
}

function NetTooltip({ active, payload, bucket }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <Box sx={{ ...TT.contentStyle, bgcolor: 'background.paper', p: 1.25, maxWidth: 300 }}>
      <Typography variant="caption" fontWeight={700} display="block">{labelFor(p, bucket, true)}</Typography>
      <Typography variant="caption" display="block">Net change, managed: <strong>{signed(p.net_managed)}</strong></Typography>
      <Typography variant="caption" display="block">Net change, verified: <strong>{signed(p.net_verified)}</strong></Typography>
      {p.groups_delta != null && p.groups_delta !== 0 && (
        <Typography variant="caption" color="warning.main" display="block">
          Groups counted changed by {signed(p.groups_delta)} in this period, so part of this change may be groups entering or leaving the total.
        </Typography>
      )}
      {p.baseline_day
        ? <Typography variant="caption" color="text.secondary" display="block">Measured against the {p.baseline_day} snapshot{p.gap_days > 1 ? ` (${p.gap_days} days earlier; days in between have no snapshot)` : ''}.</Typography>
        : <Typography variant="caption" color="text.secondary" display="block">No earlier snapshot to compare with.</Typography>}
    </Box>
  );
}

export default function ManagedMembersCharts() {
  const [range, setRange] = useState('30d');
  const [state, setState] = useState({ data: null, loading: true, error: null });

  const load = useCallback(async (signal) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await admin.getManagedMembersSeries(range, { signal });
      setState({ data: res.data, loading: false, error: null });
    } catch (e) {
      if (e?.code === 'ERR_CANCELED') return;
      setState((s) => ({ data: s.data, loading: false, error: e?.response?.data?.error || 'Could not load the member history.' }));
    }
  }, [range]);

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  const { data, loading, error } = state;
  const bucket = data?.bucket || 'day';
  const pts = (data?.points || []).map((p) => ({ ...p, label: labelFor(p, bucket) }));
  const hasNet = pts.some((p) => p.net_managed != null);
  const allZero = hasNet && pts.every((p) => !p.net_managed && !p.net_verified);
  const rangeLabel = RANGES.find((r) => r.key === range)?.label;
  // Managed and Verified differ by orders of magnitude, so each gets its own axis: Managed (left) uses a padded,
  // clearly labelled truncated scale so small changes show; Verified (right) has its own scale.
  const managedDomain = paddedDomain(pts.map((p) => p.managed));
  const verifiedDomain = paddedDomain(pts.map((p) => p.verified));
  const single = pts.length === 1;
  const lagging = data?.current && pts.length && pts[pts.length - 1].managed !== data.current.managed_members;

  return (
    <Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} justifyContent="space-between" alignItems={{ sm: 'center' }} mb={1.5}>
        <Typography variant="caption" color="text.secondary">
          Both charts use the same range and UTC days. {bucket === 'month' ? 'Months show the end-of-month total and the net change over the month. ' : ''}
          {data?.data_starts ? `Snapshot history starts ${data.data_starts}.` : ''}
        </Typography>
        <ToggleButtonGroup size="small" exclusive value={range} onChange={(_, v) => v && setRange(v)} aria-label="Chart range">
          {RANGES.map((r) => <ToggleButton key={r.key} value={r.key} sx={{ px: 1.5, minHeight: 36 }}>{r.label}</ToggleButton>)}
        </ToggleButtonGroup>
      </Stack>
      {error && <Alert severity="error" sx={{ mb: 1.5 }} action={<Button color="inherit" size="small" onClick={() => load()}>Retry</Button>}>{error}</Alert>}
      {!data && loading ? <Box display="flex" justifyContent="center" py={4}><CircularProgress size={28} /></Box> : data && (
        <Box sx={{ opacity: loading ? 0.6 : 1, transition: 'opacity .15s' }}>
          <Grid container spacing={2}>
            <Grid item xs={12} md={7}>
              <Card2
                title="Members managed" subtitle={`Current membership of the groups our bots manage, at the end of each ${periodWord(bucket)} · ${rangeLabel} · UTC`}
                note={pts.length ? 'Each line has its own vertical axis and neither is forced to start at zero, so small changes are visible. “Managed” = sum of member counts of active, enabled groups; not unique people.' : undefined}
                empty={!pts.length ? 'No snapshots in this range yet. One snapshot is saved per day.' : null}
              >
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={pts} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
                    <YAxis yAxisId="m" allowDecimals={false} tick={{ fontSize: 11 }} domain={managedDomain} width={58} tickFormatter={(v) => v.toLocaleString()} />
                    <YAxis yAxisId="v" orientation="right" allowDecimals={false} tick={{ fontSize: 11, fill: COLORS.verified }} domain={verifiedDomain} width={44} tickFormatter={(v) => v.toLocaleString()} />
                    <Tooltip {...TT} content={<TotalTooltip bucket={bucket} />} />
                    <Legend />
                    <Line yAxisId="m" type="linear" dataKey="managed" name="Managed (left axis)" stroke={COLORS.managed} strokeWidth={2} dot={single || pts.length < 32 ? { r: 3 } : false} activeDot={{ r: 5 }} isAnimationActive={false} />
                    <Line yAxisId="v" type="linear" dataKey="verified" name="Verified (right axis)" stroke={COLORS.verified} strokeWidth={2} dot={single || pts.length < 32 ? { r: 3 } : false} activeDot={{ r: 5 }} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </Card2>
            </Grid>
            <Grid item xs={12} md={5}>
              <Card2
                title="Net member change"
                subtitle={`End-of-${periodWord(bucket)} total minus the previous snapshot · ${rangeLabel}`}
                note={'Not join/leave events: this also moves when a group enters or leaves the total (bot removed, group disabled or unlinked, access lost). Missing days are not counted as zero.'}
                empty={!pts.length ? 'No snapshots in this range yet.' : !hasNet ? 'Needs a snapshot from before this range to measure a change.' : null}
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={pts} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={52} tickFormatter={(v) => (v > 0 ? `+${v.toLocaleString()}` : v.toLocaleString())} domain={allZero ? [-1, 1] : ['auto', 'auto']} />
                    <ReferenceLine y={0} stroke="currentColor" strokeOpacity={0.6} />
                    <Tooltip {...TT} content={<NetTooltip bucket={bucket} />} />
                    <Legend payload={[
                      { value: 'Managed (rise)', type: 'square', color: COLORS.up },
                      { value: 'Managed (fall)', type: 'square', color: COLORS.down },
                      { value: 'Verified', type: 'square', color: COLORS.verifiedNet },
                    ]} />
                    <Bar dataKey="net_managed" name="Managed" maxBarSize={22} isAnimationActive={false}>
                      {pts.map((p) => <Cell key={p.period_start} fill={(p.net_managed ?? 0) < 0 ? COLORS.down : COLORS.up} />)}
                    </Bar>
                    <Bar dataKey="net_verified" name="Verified" fill={COLORS.verifiedNet} maxBarSize={22} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </Card2>
            </Grid>
          </Grid>
          {pts.length > 0 && allZero && <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>No net change in this range.</Typography>}
          {single && <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>Only one snapshot falls in this range, so there is a single point. Daily snapshots do not allow an hourly view.</Typography>}
          {lagging && <Typography variant="caption" color="warning.main" display="block" sx={{ mt: 1 }}>The latest snapshot differs from the live total ({data.current.managed_members.toLocaleString()}); the next refresh will reconcile it.</Typography>}
          {bucket === 'month' && pts.some((p) => p.partial) && <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>* Month is incomplete (still running, or snapshot history began mid-month).</Typography>}
        </Box>
      )}
    </Box>
  );
}
