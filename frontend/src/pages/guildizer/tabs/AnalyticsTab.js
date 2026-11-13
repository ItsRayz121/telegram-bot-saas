import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, CircularProgress, Alert,
  ToggleButtonGroup, ToggleButton, Stack, Tooltip,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';
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
        <BarsCard id="analytics.overview.messages" title="Messages per day" series={data.series} field="messages" color="#5865F2" />
      </Grid>
      <Grid item xs={12} md={6}>
        <BarsCard id="analytics.overview.joins" title="Joins per day" series={data.series} field="joins" color="#3BA55D" />
      </Grid>
      <Grid item xs={12} md={6}>
        <BarsCard id="analytics.overview.leaves" title="Leaves per day" series={data.series} field="leaves" color="#ED4245" />
      </Grid>
      <Grid item xs={12} md={6}>
        <BarsCard id="analytics.overview.mod" title="Moderation actions per day" series={data.series} field="mod_actions" color="#FAA61A" />
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

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function shortDay(day) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(day || ''));
  return m ? `${MONTHS[Number(m[2]) - 1] || m[2]} ${Number(m[3])}` : String(day || '');
}

const CHART_H = 132; // px reserved for bar + its value label
const LABEL_H = 18;

function BarsCard({ id, title, series, field, color }) {
  const rows = (series || []).map((d) => ({ day: d.day, v: Number(d[field]) || 0 }));
  const max = Math.max(1, ...rows.map((r) => r.v));
  const total = rows.reduce((a, r) => a + r.v, 0);
  const avg = rows.length ? total / rows.length : 0;
  const colMin = rows.length > 14 ? 30 : 36; // px; wider scrolls on small screens
  const tickEvery = rows.length > 21 ? 3 : rows.length > 10 ? 2 : 1;
  const fmt = (n) => n.toLocaleString();

  return (
    <GuildizerCollapsibleCard id={id} title={title}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
        Total {fmt(total)} · Avg {avg.toFixed(1)}/day
      </Typography>
      <Box sx={{
        overflowX: 'auto', overflowY: 'hidden', pb: 0.5,
        '@keyframes gzGrow': { from: { transform: 'scaleY(0)' }, to: { transform: 'scaleY(1)' } },
        '@keyframes gzFade': { from: { opacity: 0 }, to: { opacity: 1 } },
      }}>
        <Box sx={{
          display: 'grid',
          gridTemplateColumns: `repeat(${rows.length}, minmax(${colMin}px, 1fr))`,
          columnGap: '4px',
          minWidth: rows.length * (colMin + 4),
        }}>
          {rows.map((r, i) => {
            const barH = r.v === 0 ? 2 : Math.max(4, (r.v / max) * (CHART_H - LABEL_H - 4));
            return (
              <Tooltip
                key={r.day}
                arrow
                enterTouchDelay={0}
                leaveTouchDelay={2500}
                title={<span><strong>{shortDay(r.day)}</strong><br />{fmt(r.v)} {r.v === 1 ? 'event' : 'events'}</span>}
              >
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: CHART_H, cursor: 'default', '&:hover .gz-bar': { filter: 'brightness(1.2)' } }}>
                  <Typography
                    component="span"
                    sx={{
                      height: LABEL_H, lineHeight: `${LABEL_H}px`, fontSize: 11, fontWeight: r.v === 0 ? 500 : 700,
                      fontVariantNumeric: 'tabular-nums', color: r.v === 0 ? 'text.disabled' : 'text.primary',
                      whiteSpace: 'nowrap', opacity: 0, animation: `gzFade .4s ease ${120 + i * 25}ms forwards`,
                      '@media (prefers-reduced-motion: reduce)': { animation: 'none', opacity: 1 },
                    }}
                  >
                    {r.v >= 100000 ? `${(r.v / 1000).toFixed(0)}k` : r.v >= 10000 ? `${(r.v / 1000).toFixed(1)}k` : r.v}
                  </Typography>
                  <Box
                    className="gz-bar"
                    sx={{
                      width: '70%', maxWidth: 28, height: barH, bgcolor: color, opacity: r.v === 0 ? 0.3 : 0.95,
                      borderRadius: '4px 4px 0 0', transformOrigin: 'bottom', transition: 'filter .15s',
                      animation: `gzGrow .5s cubic-bezier(.2,.8,.2,1) ${i * 25}ms both`,
                      '@media (prefers-reduced-motion: reduce)': { animation: 'none' },
                    }}
                  />
                </Box>
              </Tooltip>
            );
          })}
          {rows.map((r, i) => (
            <Typography key={`t-${r.day}`} variant="caption" color="text.disabled"
              sx={{ textAlign: 'center', fontSize: 10, mt: 0.5, whiteSpace: 'nowrap', borderTop: '1px solid', borderColor: 'divider', pt: 0.5 }}>
              {i % tickEvery === 0 || i === rows.length - 1 ? shortDay(r.day) : ' '}
            </Typography>
          ))}
        </Box>
      </Box>
    </GuildizerCollapsibleCard>
  );
}
