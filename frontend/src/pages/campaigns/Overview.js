import React, { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { Alert, Box, Button, Paper, Stack, Typography } from '@mui/material';
import { Refresh } from '@mui/icons-material';
import { engagementWs } from '../../services/api';
import { EmptyNote, InsightError, Loading, Panel, PeriodChips, StatGrid, StatTile, TrendChart } from '../../components/analytics/shared';
import { Freshness, ProgressBlock, StatusChip, TypeChip, fmtTime, timeLeft, useWorkspace, usePolled } from './common';

const PERIODS = [{ key: '7', label: '7 days' }, { key: '30', label: '30 days' }, { key: '90', label: '90 days' }];

function AttentionRow({ a, ws }) {
  const to = a.campaign_id ? ws.paths.detail(a.campaign_id) : ws.paths.review;
  const severity = a.kind === 'post_failed' ? 'error' : 'warning';
  const label = {
    post_failed: 'Group post failed', not_posted: 'Not posted yet', stale_reviews: 'Reviews waiting',
    flagged_pending: 'Possible duplicates', ending_soon: 'Ending soon',
  }[a.kind] || a.kind;
  return (
    <Alert severity={severity} sx={{ alignItems: 'center' }}
      action={<Button color="inherit" size="small" component={RouterLink} to={to}>{a.campaign_id ? 'Open' : 'Review'}</Button>}>
      <strong>{label}</strong>{a.title ? ` · ${a.title}` : ''} — {a.detail}
    </Alert>
  );
}

export default function Overview() {
  const ws = useWorkspace();
  const [days, setDays] = useState('30');
  const { data, loading, error, at, stale, reload } = usePolled(
    () => engagementWs.overview(ws.botId, ws.groupId, { days }), [ws.botId, ws.groupId, days, ws.tick], { enabled: ws.ready });
  const t = data?.totals;

  if (error && !data) return <InsightError message={error} onRetry={reload} />;

  return (
    <Box aria-busy={loading}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1.5 }}>
        <Freshness at={at} error={error} stale={stale} tz={ws.tz} />
        <Button size="small" startIcon={<Refresh />} onClick={reload} disabled={loading}>Refresh</Button>
      </Box>

      <StatGrid min={200}>
        <StatTile label="Active campaigns" value={t?.active_campaigns} loading={loading && !data}
          hint={t ? `${t.campaigns_total} campaign${t.campaigns_total === 1 ? '' : 's'} in this group in total` : undefined} />
        <Box component={RouterLink} to={ws.paths.review} sx={{ textDecoration: 'none', color: 'inherit', display: 'block', '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', borderRadius: 1 } }}>
          <StatTile label="Pending review" value={t?.pending_review} loading={loading && !data} tone={t?.pending_review ? 'warning.main' : undefined}
            hint="Submissions awaiting a decision, across all campaigns · open the queue" />
        </Box>
        <StatTile label="Approved submissions" value={t?.approved_submissions} loading={loading && !data}
          hint={t ? `Each submission counted once · ${t.approved_unique_participants} unique ${t.approved_unique_participants === 1 ? 'person' : 'people'}` : undefined} />
      </StatGrid>

      <Panel title="Needs attention" subtitle="Only real conditions found in this group's data" sx={{ mb: 2 }}>
        {!data ? <Loading /> : data.attention.length === 0 ? (
          <EmptyNote>Nothing needs attention right now.</EmptyNote>
        ) : (
          <Stack spacing={1}>{data.attention.map((a, i) => <AttentionRow key={`${a.kind}-${a.campaign_id || i}`} a={a} ws={ws} />)}</Stack>
        )}
        {data && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            "Waiting" means a pending submission older than {data.stale_review_hours} hours. There is no configured review deadline; this is just a reminder threshold.
          </Typography>
        )}
      </Panel>

      <Panel
        title="Submissions and review decisions"
        subtitle={data ? `${data.series_totals.submitted.toLocaleString()} submitted · ${data.series_totals.decisions.toLocaleString()} decisions in the last ${days} days` : undefined}
        action={<PeriodChips value={days} options={PERIODS} onChange={setDays} ariaLabel="Chart period" />}
      >
        <TrendChart series={data?.series || []} height={220}
          keys={[{ key: 'submitted', label: 'New submissions', color: '#3d8ef8' }, { key: 'decisions', label: 'Review decisions', color: '#22c55e' }]}
          emptyText={loading && !data ? 'Loading…' : 'No submissions or decisions in this period.'} />
        {data && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>{data.series_note}</Typography>}
      </Panel>

      <Panel title="Active campaigns" action={<Button size="small" component={RouterLink} to={ws.paths.list}>All campaigns</Button>}>
        {!data ? <Loading /> : data.running.length === 0 ? (
          <EmptyNote>No active campaigns. Create one from “New campaign”, or activate a draft.</EmptyNote>
        ) : (
          <Stack spacing={1.25}>
            {data.running.map((c) => (
              <Paper key={c.id} variant="outlined" sx={{ p: 1.5 }}>
                <Box sx={{ display: 'flex', gap: 1, justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <Box sx={{ minWidth: 0, flex: '1 1 240px' }}>
                    <Typography component={RouterLink} to={ws.paths.detail(c.id)} variant="subtitle2"
                      sx={{ color: 'text.primary', textDecoration: 'none', fontWeight: 700, wordBreak: 'break-word', '&:hover': { textDecoration: 'underline' } }}>
                      {c.title}
                    </Typography>
                    <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mt: 0.5 }}>
                      <TypeChip type={c.type} /> <StatusChip status={c.status} />
                    </Stack>
                  </Box>
                  <Box sx={{ textAlign: { xs: 'left', sm: 'right' } }}>
                    <Typography variant="body2" fontWeight={600}>{c.ends_at ? `Ends ${fmtTime(c.ends_at, ws.tz)}` : 'No deadline'}</Typography>
                    {c.ends_at && <Typography variant="caption" color="text.secondary">{timeLeft(c.ends_at)}</Typography>}
                  </Box>
                </Box>
                <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center', mt: 1 }}>
                  <Typography variant="body2"><strong>{c.pending}</strong> pending</Typography>
                  <Typography variant="body2"><strong>{c.approved}</strong> approved</Typography>
                  <Typography variant="body2" color="text.secondary">{c.submitted} submitted</Typography>
                  <Box sx={{ flex: 1 }} />
                  <Button size="small" component={RouterLink} to={ws.paths.detail(c.id)}>Open</Button>
                </Box>
                {(c.progress.participants || c.progress.actions) && <Box sx={{ mt: 1 }}><ProgressBlock progress={c.progress} /></Box>}
              </Paper>
            ))}
          </Stack>
        )}
      </Panel>
    </Box>
  );
}
