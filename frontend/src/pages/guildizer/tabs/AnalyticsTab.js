import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, CircularProgress, Alert,
  ToggleButtonGroup, ToggleButton, Stack, Tooltip,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';

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
        <BarsCard title="Messages per day" series={data.series} field="messages" color="#5865F2" />
      </Grid>
      <Grid item xs={12} md={6}>
        <BarsCard title="Joins per day" series={data.series} field="joins" color="#3BA55D" />
      </Grid>
      <Grid item xs={12} md={6}>
        <BarsCard title="Leaves per day" series={data.series} field="leaves" color="#ED4245" />
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

function BarsCard({ title, series, field, color }) {
  const max = Math.max(1, ...series.map((d) => d[field]));
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>{title}</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Daily activity over the selected window. Hover a bar to see its date and exact count.
      </Typography>
      <Stack direction="row" spacing={0.5} alignItems="flex-end" sx={{ height: 120 }}>
        {series.map((d) => (
          <Tooltip key={d.day} title={`${d.day}: ${d[field]}`}>
            <Box sx={{
              flex: 1,
              height: `${Math.max(3, (d[field] / max) * 100)}%`,
              bgcolor: color,
              opacity: d[field] === 0 ? 0.25 : 0.9,
              borderRadius: 0.5,
              minWidth: 4,
            }} />
          </Tooltip>
        ))}
      </Stack>
      <Stack direction="row" justifyContent="space-between" mt={0.5}>
        <Typography variant="caption" color="text.disabled">{series[0]?.day}</Typography>
        <Typography variant="caption" color="text.disabled">{series[series.length - 1]?.day}</Typography>
      </Stack>
    </CardContent></Card>
  );
}
