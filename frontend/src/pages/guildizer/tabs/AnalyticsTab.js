import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, CircularProgress, Alert,
  ToggleButtonGroup, ToggleButton, Stack,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';
import DailyBars from '../../../components/charts/DailyBars';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';

export default function AnalyticsTab({ guildId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [days, setDays] = useState(14);

  const load = useCallback(async (d = days) => {
    try {
      const { data: res } = await guildizerApi.get(`/api/guilds/${guildId}/analytics?days=${d}`);
      setData(res); setError(null);
    } catch { setError('Failed to load analytics.'); }
    setLoading(false);
  }, [guildId, days]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
  if (!data) return <Alert severity="warning">{error || 'No data.'}</Alert>;

  const t = data.totals;
  return (
    <Grid container spacing={2}>
      <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'flex-end' }}>
        <ToggleButtonGroup size="small" exclusive value={days} onChange={(_, v) => v && setDays(v)}>
          <ToggleButton value={7}>7d</ToggleButton>
          <ToggleButton value={14}>14d</ToggleButton>
          <ToggleButton value={30}>30d</ToggleButton>
        </ToggleButtonGroup>
      </Grid>

      <StatCard label="Messages" value={t.messages} />
      <StatCard label="Joins" value={t.joins} />
      <StatCard label="Leaves" value={t.leaves} />
      <StatCard label="Active today" value={t.actives_today} />

      <Grid item xs={12}>
        <BarsCard id="analytics.overview.messages" title="Messages per day" series={data.series} field="messages" label="Messages" color="#5865F2" />
      </Grid>
      <Grid item xs={12} md={6}>
        <BarsCard id="analytics.overview.joins" title="Joins per day" series={data.series} field="joins" label="Joins" color="#3BA55D" />
      </Grid>
      <Grid item xs={12} md={6}>
        <BarsCard id="analytics.overview.leaves" title="Leaves per day" series={data.series} field="leaves" label="Leaves" color="#ED4245" />
      </Grid>
      <Grid item xs={12} md={6}>
        <BarsCard id="analytics.overview.mod" title="Moderation actions per day" series={data.series} field="mod_actions" label="Mod actions" color="#FAA61A" />
      </Grid>
      <Grid item xs={12} md={6}>
        <GuildizerCollapsibleCard id="analytics.overview.levels" title="Members by level">
          {(data.level_distribution || []).map((b) => {
            const top = Math.max(1, ...(data.level_distribution || []).map((x) => x.members));
            return (
              <Stack key={b.label} direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
                <Typography variant="caption" sx={{ width: 48 }}>Lvl {b.label}</Typography>
                <Box sx={{ flex: 1, height: 14, borderRadius: 1, bgcolor: 'action.hover' }}>
                  <Box sx={{ width: `${(b.members / top) * 100}%`, height: '100%', borderRadius: 1, bgcolor: '#5865F2' }} />
                </Box>
                <Typography variant="caption" sx={{ width: 40, textAlign: 'right' }}>{b.members}</Typography>
              </Stack>
            );
          })}
        </GuildizerCollapsibleCard>
      </Grid>
    </Grid>
  );
}

function StatCard({ label, value }) {
  return (
    <Grid item xs={6} md={3}>
      <Card variant="outlined"><CardContent sx={{ textAlign: 'center' }}>
        <Typography variant="h4" fontWeight={800}>{value}</Typography>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
      </CardContent></Card>
    </Grid>
  );
}

function BarsCard({ id, title, series, field, color, label }) {
  const total = (series || []).reduce((a, d) => a + (Number(d[field]) || 0), 0);
  const avg = series && series.length ? total / series.length : 0;
  return (
    <GuildizerCollapsibleCard id={id} title={title}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
        Total {total.toLocaleString()} · Avg {avg.toFixed(1)}/day
      </Typography>
      <DailyBars series={series} dateKey="day" keys={[{ key: field, label: label || title, color }]} />
    </GuildizerCollapsibleCard>
  );
}
