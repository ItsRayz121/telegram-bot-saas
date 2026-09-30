import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Grid, CircularProgress, Alert, Button,
  ToggleButton, ToggleButtonGroup, Stack,
} from '@mui/material';
import { TrendingUp, TrendingDown } from '@mui/icons-material';
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';
import { admin } from '../../services/api';

const RANGES = [
  { key: '1d', label: '1 Day', vs: 'previous 24h' },
  { key: '7d', label: '7 Days', vs: 'previous 7 days' },
  { key: '30d', label: '30 Days', vs: 'previous 30 days' },
  { key: '6m', label: '6 Months', vs: 'previous 6 months' },
  { key: '1y', label: '1 Year', vs: 'previous year' },
  { key: 'all', label: 'All Time', vs: null },
];

const SERIES = [
  { key: 'users', label: 'Users', color: '#2196f3' },
  { key: 'groups', label: 'Groups connected', color: '#8b5cf6' },
  { key: 'custom_bots', label: 'Custom bots', color: '#00bcd4' },
];

function fmtBucket(iso, bucket) {
  const d = new Date(iso + 'Z');
  if (bucket === 'hour') return d.toLocaleTimeString([], { hour: 'numeric', timeZone: 'UTC' });
  if (bucket === 'month') return d.toLocaleDateString([], { month: 'short', year: '2-digit', timeZone: 'UTC' });
  if (bucket === 'year') return String(d.getUTCFullYear());
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

function Delta({ block, vs }) {
  if (!vs || block.previous_new == null) return null;
  if (block.change_pct == null) {
    return <Typography variant="caption" color="text.secondary">{block.previous_new} in {vs} (no baseline)</Typography>;
  }
  const up = block.change_pct >= 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <Stack direction="row" spacing={0.5} alignItems="center">
      <Icon sx={{ fontSize: 16, color: up ? '#22c55e' : '#ef4444' }} />
      <Typography variant="caption" color="text.secondary">
        {up ? '+' : ''}{block.change_pct}% vs {vs} ({block.previous_new})
      </Typography>
    </Stack>
  );
}

export default function GrowthAnalytics() {
  const [range, setRange] = useState('30d');
  const [series, setSeries] = useState('users');
  const [metric, setMetric] = useState('new');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const res = await admin.getGrowth(range, { signal });
      setData(res.data);
    } catch (e) {
      if (e?.code === 'ERR_CANCELED') return;
      setError(e?.response?.data?.error || e?.response?.data?.message || 'Could not load growth data.');
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  const rangeDef = RANGES.find(r => r.key === range);
  const block = data?.[series];
  const seriesDef = SERIES.find(s => s.key === series);
  const chartData = (block?.points || []).map(p => ({ ...p, label: fmtBucket(p.t, data.bucket) }));
  const perBucket = { hour: 'hour', day: 'day', week: 'week', month: 'month', year: 'year' }[data?.bucket] || '';

  return (
    <Card sx={{ mb: 3, borderRadius: 2 }}>
      <CardContent>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} justifyContent="space-between" mb={2}>
          <Typography variant="subtitle2" color="text.secondary" fontWeight={600} textTransform="uppercase" letterSpacing={1}>
            Growth
          </Typography>
          <Box sx={{ overflowX: 'auto', maxWidth: '100%' }}>
            <ToggleButtonGroup size="small" exclusive value={range} onChange={(_, v) => v && setRange(v)} aria-label="Time range">
              {RANGES.map(r => (
                <ToggleButton key={r.key} value={r.key} sx={{ px: 1.5, whiteSpace: 'nowrap', minHeight: 36 }}>{r.label}</ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Box>
        </Stack>

        <Grid container spacing={2} mb={2}>
          {SERIES.map(s => {
            const b = data?.[s.key];
            const selected = s.key === series;
            return (
              <Grid item xs={12} sm={4} key={s.key}>
                <Card
                  variant="outlined"
                  onClick={() => setSeries(s.key)}
                  role="button" tabIndex={0} aria-pressed={selected}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSeries(s.key); } }}
                  sx={{ cursor: 'pointer', borderColor: selected ? s.color : 'divider', borderWidth: selected ? 2 : 1 }}
                >
                  <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                    <Typography variant="caption" color="text.secondary">{s.label}</Typography>
                    <Stack direction="row" spacing={1} alignItems="baseline">
                      <Typography variant="h5" fontWeight={700}>{b ? b.total.toLocaleString() : '—'}</Typography>
                      <Typography variant="body2" sx={{ color: s.color }} fontWeight={600}>
                        {b ? `+${b.new.toLocaleString()} in ${rangeDef.label.toLowerCase()}` : ''}
                      </Typography>
                    </Stack>
                    {b && <Delta block={b} vs={rangeDef.vs} />}
                    {s.key === 'groups' && b && (
                      <Typography variant="caption" color="text.secondary" display="block">
                        {b.active_now.toLocaleString()} active now
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            );
          })}
        </Grid>

        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
          <Typography variant="caption" color="text.secondary">
            {seriesDef.label} · {metric === 'new' ? `new per ${perBucket}` : 'cumulative total'} · UTC
          </Typography>
          <ToggleButtonGroup size="small" exclusive value={metric} onChange={(_, v) => v && setMetric(v)} aria-label="Metric">
            <ToggleButton value="new" sx={{ px: 1.5 }}>New</ToggleButton>
            <ToggleButton value="total" sx={{ px: 1.5 }}>Total</ToggleButton>
          </ToggleButtonGroup>
        </Stack>

        {error && (
          <Alert severity="error" action={<Button color="inherit" size="small" onClick={() => load()}>Retry</Button>}>
            {error}
          </Alert>
        )}
        {!error && (
          <Box sx={{ height: { xs: 220, md: 280 }, position: 'relative' }}>
            {loading && !data && <Box display="flex" justifyContent="center" pt={8}><CircularProgress size={28} /></Box>}
            {data && (
              <Box sx={{ height: '100%', opacity: loading ? 0.5 : 1, transition: 'opacity .15s' }}>
                <ResponsiveContainer width="100%" height="100%">
                  {metric === 'new' ? (
                    <BarChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Bar dataKey="new" name="New" fill={seriesDef.color} radius={[3, 3, 0, 0]} />
                    </BarChart>
                  ) : (
                    <LineChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
                      <Tooltip />
                      <Line type="monotone" dataKey="total" name="Total" stroke={seriesDef.color} strokeWidth={2} dot={false} />
                    </LineChart>
                  )}
                </ResponsiveContainer>
              </Box>
            )}
          </Box>
        )}
        {data && block && block.points.length === 0 && (
          <Typography variant="body2" color="text.secondary" mt={1}>No data in this range yet.</Typography>
        )}
      </CardContent>
    </Card>
  );
}
