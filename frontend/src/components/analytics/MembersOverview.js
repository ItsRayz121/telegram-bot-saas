import React from 'react';
import { Box, Button, Chip, Typography } from '@mui/material';
import {
  EmptyNote, InsightError, MemberLink, Panel,
  StatGrid, StatTile, TrendChart, memberProfilePath, useInsight,
} from './shared';

const WINDOW_LABEL = { '1d': 'the last 24 hours', '7d': 'the last 7 days', '30d': 'the last 30 days' };

/**
 * Overview above the Members directory. Every number comes from the server over
 * the whole group, scoped to the same period chip the table below uses.
 */
export default function MembersOverview({
  botId, groupId, isOfficial, period, warnedOnly, onToggleWarned, refreshKey,
}) {
  const { data, loading, error, reload } = useInsight(botId, groupId, 'members', { period, _r: refreshKey });
  const profile = (userId) => memberProfilePath({ isOfficial, botId, groupId, userId });
  const win = WINDOW_LABEL[period];
  const unknownHint = 'Pick a period to measure';

  if (error && !data) return <InsightError message={error} onRetry={reload} />;

  return (
    <Box sx={{ mb: 2 }} aria-busy={loading}>
      {error && <InsightError message={`${error} - showing the last loaded numbers.`} onRetry={reload} />}
      <StatGrid>
        <StatTile label="Total members" value={data?.total_members} loading={loading && !data}
          hint="Everyone tracked in this group" />
        <StatTile label="Active members" value={data?.active_members} loading={loading && !data}
          hint={win ? `Posted in ${win}` : unknownHint} />
        <StatTile label="New members" value={data?.new_members} loading={loading && !data}
          hint={win ? `Joined in ${win}` : unknownHint} />
        <StatTile
          label="With active warnings" value={data?.members_with_active_warnings} loading={loading && !data}
          tone={data?.members_with_active_warnings ? 'warning.main' : undefined}
          hint={data ? `${data.active_warning_records} active warning record${data.active_warning_records === 1 ? '' : 's'}` : undefined}
          onClick={onToggleWarned} selected={warnedOnly}
        />
      </StatGrid>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '3fr 2fr' } }}>
        <Panel
          title="Member activity"
          subtitle={data ? `Members who earned XP each day, plus new joins · last ${data.series_days} days` : undefined}
          sx={{ mb: 0 }}
        >
          <TrendChart
            series={data?.series || []}
            keys={[
              { key: 'active_contributors', label: 'Members earning XP', color: '#3d8ef8' },
              { key: 'joins', label: 'New members', color: '#22c55e' },
            ]}
            emptyText={loading ? 'Loading…' : 'No XP or joins recorded in this window.'}
          />
          {data?.series_note && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>{data.series_note}</Typography>
          )}
        </Panel>

        <Panel title="Worth a closer look" subtitle="Select a person to open their profile" sx={{ mb: 0 }}>
          <Typography variant="overline" color="text.secondary">Repeated warnings</Typography>
          {!data || data.repeat_warned.length === 0 ? (
            <EmptyNote>{loading && !data ? 'Loading…' : 'Nobody holds more than one active warning.'}</EmptyNote>
          ) : (
            <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0, display: 'grid', gap: 1, mb: 1.5 }}>
              {data.repeat_warned.map((m) => (
                <Box component="li" key={m.user_id} sx={{ display: 'flex', alignItems: 'center', gap: 1, justifyContent: 'space-between' }}>
                  <MemberLink member={m} profile={profile(m.user_id)} secondary={`${m.warnings} active warnings`} />
                  <Chip size="small" color="warning" variant="outlined" label={`×${m.warnings}`} />
                </Box>
              ))}
            </Box>
          )}
          {data?.repeat_warned?.length > 0 && !warnedOnly && (
            <Button size="small" onClick={onToggleWarned} sx={{ mb: 1 }}>Filter table to members with warnings</Button>
          )}

          <Typography variant="overline" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>Leading contributors</Typography>
          {!data || data.top_contributors.length === 0 ? (
            <EmptyNote>{loading && !data ? 'Loading…' : 'No XP earned yet.'}</EmptyNote>
          ) : (
            <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0, display: 'grid', gap: 1 }}>
              {data.top_contributors.slice(0, 3).map((m) => (
                <Box component="li" key={m.user_id} sx={{ display: 'flex', alignItems: 'center', gap: 1, justifyContent: 'space-between' }}>
                  <MemberLink member={m} profile={profile(m.user_id)} secondary={`Level ${m.level}`} />
                  <Typography variant="body2" fontWeight={700} color="primary.main" sx={{ whiteSpace: 'nowrap' }}>
                    {m.xp.toLocaleString()} XP
                  </Typography>
                </Box>
              ))}
            </Box>
          )}
          {data && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{data.top_contributors_basis}</Typography>}
        </Panel>
      </Box>
    </Box>
  );
}
