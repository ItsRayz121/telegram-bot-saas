import React, { useState } from 'react';
import {
  Alert, Box, Button, Chip, Collapse, FormControl, InputAdornment, InputLabel, MenuItem, Pagination,
  Paper, Select, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography,
} from '@mui/material';
import { Search } from '@mui/icons-material';
import { insights } from '../../services/api';
import {
  BreakdownBars, EmptyNote, InsightError, Loading, MemberLink, Panel, PeriodChips, ProfileButton,
  StatGrid, StatTile, TrendChart, memberProfilePath, useInsight,
} from './shared';

export const AUDIT_PERIODS = [
  { key: '7d', label: '7 days' },
  { key: '30d', label: '30 days' },
  { key: '90d', label: '90 days' },
  { key: 'all', label: 'All time' },
];

const ACTION_COLOR = {
  warn: 'warning', mute: 'warning', tempmute: 'warning', kick: 'error', ban: 'error', tempban: 'error',
  purge: 'info', unban: 'success', unmute: 'success',
};
const actionColor = (a) => ACTION_COLOR[a] || (String(a).includes('ban') ? 'error' : String(a).includes('warn') ? 'warning' : 'default');

function actorText(e) {
  if (e.automatic) return `Automatic${e.moderator && !/^automod$/i.test(e.moderator) ? ` (${e.moderator})` : ' (AutoMod)'}`;
  return e.moderator ? `Manual · ${e.moderator}` : 'Manual · moderator not recorded';
}

function EventRow({ e, fmt }) {
  return (
    <Box sx={{ py: 1, borderTop: '1px solid', borderColor: 'divider' }}>
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <Typography variant="caption" fontWeight={700}>{fmt(e.timestamp)}</Typography>
        <Typography variant="caption" color="text.secondary">{actorText(e)}</Typography>
      </Box>
      {e.reason && <Typography variant="body2" sx={{ mt: 0.25, wordBreak: 'break-word' }}>{e.reason}</Typography>}
      {e.enforced && <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Rule action taken: {e.enforced}</Typography>}
      {e.message_text && (
        <Box sx={{ mt: 0.5, p: 1, borderRadius: 1, bgcolor: 'action.hover' }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Message evidence</Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{e.message_text}</Typography>
        </Box>
      )}
    </Box>
  );
}

function GroupCard({ g, ctx }) {
  const { botId, groupId, isOfficial, days, search, fmt, renderActions } = ctx;
  const [open, setOpen] = useState(false);
  const [extra, setExtra] = useState(null);   // all events once "show all" was used
  const [loadingAll, setLoadingAll] = useState(false);
  const [err, setErr] = useState(null);
  const profile = memberProfilePath({ isOfficial, botId, groupId, userId: g.user_id });
  const events = extra || g.events;

  const showAll = async () => {
    setLoadingAll(true); setErr(null);
    try {
      let page = 1; let all = []; let pages = 1;
      do {
        // eslint-disable-next-line no-await-in-loop
        const r = await insights.get(botId, groupId, 'audit-group-events', {
          user_id: g.user_id || undefined, action: g.action, label: g.reason_label, days, q: search || undefined, page, per_page: 100,
        });
        all = all.concat(r.data.events); pages = r.data.pages; page += 1;
      } while (page <= pages && page <= 10);
      setExtra(all);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Could not load all events');
    } finally {
      setLoadingAll(false);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <Box sx={{ minWidth: 0, flex: '1 1 220px' }}>
          {g.user_id || g.username
            ? <MemberLink member={g} profile={profile} secondary={g.user_id ? `ID ${g.user_id}` : undefined} />
            : <Typography variant="body2" color="text.secondary">No member recorded</Typography>}
        </Box>
        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" alignItems="center">
          <Chip size="small" color={actionColor(g.action)} label={g.action} />
          <Chip size="small" variant="outlined" label={g.reason_label} sx={{ maxWidth: 220 }} />
          <Chip size="small" color={g.count > 1 ? 'warning' : 'default'} variant={g.count > 1 ? 'filled' : 'outlined'} label={`×${g.count}`}
            aria-label={`${g.count} event${g.count === 1 ? '' : 's'}`} />
        </Stack>
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
        Latest {fmt(g.latest_at)}{g.count > 1 ? ` · first ${fmt(g.first_at)}` : ''} · By{' '}
        {g.actors.map((a) => `${a.name}${g.count > 1 ? ` (${a.count})` : ''}`).join(', ')}
        {g.automatic > 0 && g.manual > 0 ? ` · ${g.automatic} automatic, ${g.manual} manual` : g.automatic > 0 ? ' · automatic' : ' · manual'}
      </Typography>
      {g.full_reason && g.full_reason !== g.reason_label && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, wordBreak: 'break-word' }} noWrap={!open}>
          {g.full_reason}
        </Typography>
      )}
      <Box sx={{ display: 'flex', gap: 1, mt: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <Button size="small" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? 'Hide events' : `Show ${g.count} event${g.count === 1 ? '' : 's'}`}
        </Button>
        <ProfileButton to={profile} />
        {g.user_id && renderActions && renderActions(g.user_id, g.username)}
      </Box>
      <Collapse in={open} unmountOnExit>
        <Box sx={{ mt: 1 }}>
          {events.map((e) => <EventRow key={e.id} e={e} fmt={fmt} />)}
          {!extra && g.count > g.events.length && (
            <Box sx={{ pt: 1 }}>
              <Button size="small" variant="outlined" onClick={showAll} disabled={loadingAll}>
                {loadingAll ? 'Loading…' : `Load all ${g.count} events`}
              </Button>
            </Box>
          )}
          {err && <Alert severity="error" sx={{ mt: 1 }}>{err}</Alert>}
        </Box>
      </Collapse>
    </Paper>
  );
}

export default function AuditLogPanel({
  botId, groupId, isOfficial, mode, onMode, period, onPeriod, search, onSearch, actionType, onActionType,
  fmt, renderActions, refreshKey, children,
}) {
  const [repeatedOnly, setRepeatedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const days = period === 'all' ? 'all' : period;
  const base = { days, q: search.trim() || undefined, action_type: actionType || undefined };
  const summary = useInsight(botId, groupId, 'audit-summary', { ...base, _r: refreshKey });
  const grouped = useInsight(botId, groupId, 'audit-groups', {
    ...base, min_count: repeatedOnly ? 2 : 1, page, per_page: 20, _r: refreshKey,
  }, mode === 'grouped');
  const s = summary.data;
  const reset = (fn) => (v) => { setPage(1); fn(v); };

  return (
    <>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {isOfficial
          ? 'Moderation actions (warnings, mutes, kicks, bans, AutoMod removals) recorded for this group.'
          : 'Moderation actions (warnings, mutes, kicks, bans, AutoMod removals) recorded by your bot in this group.'}
      </Typography>

      {summary.error && !s ? <InsightError message={summary.error} onRetry={summary.reload} /> : (
        <>
          <StatGrid>
            <StatTile label="Actions" value={s?.total_actions} loading={summary.loading && !s}
              hint={period === 'all' ? 'All recorded history' : `Last ${period.replace('d', '')} days`} />
            <StatTile label="Members affected" value={s?.unique_members} loading={summary.loading && !s}
              hint={s?.events_without_member ? `+ ${s.events_without_member} without a member id` : 'Unique member ids'} />
            <StatTile label="Automatic" value={s?.automatic} loading={summary.loading && !s} hint="AutoMod / RaidGuard" />
            <StatTile label="Manual" value={s?.manual} loading={summary.loading && !s} hint="Moderators and dashboard" />
            <StatTile label="Members with repeats" value={s?.members_with_repeats} loading={summary.loading && !s}
              tone={s?.members_with_repeats ? 'warning.main' : undefined} hint="2+ actions · select to filter"
              selected={mode === 'grouped' && repeatedOnly}
              onClick={() => { onMode('grouped'); setPage(1); setRepeatedOnly((v) => !v); }} />
          </StatGrid>
          {s?.truncated && (
            <Alert severity="info" sx={{ mb: 1.5 }}>
              Showing the most recent {s.row_cap.toLocaleString()} matching actions. Choose a shorter period for exact totals.
            </Alert>
          )}
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '3fr 2fr' }, mb: 2 }}>
            <Panel title="Actions over time" sx={{ mb: 0 }}>
              <TrendChart series={s?.series || []} keys={[{ key: 'count', label: 'Actions', color: '#f59e0b' }]} height={150}
                emptyText={summary.loading && !s ? 'Loading…' : 'No actions in this period.'} />
            </Panel>
            <Panel title="Rules and reasons involved" subtitle="Select one to search for it" sx={{ mb: 0 }}>
              <BreakdownBars rows={s?.top_rules || []} onPick={(label) => { setPage(1); onSearch(label); }} activeLabel={search} color="warning.main" />
            </Panel>
          </Box>
        </>
      )}

      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mb: 1.5 }}>
        <PeriodChips value={period} options={AUDIT_PERIODS} onChange={reset(onPeriod)} ariaLabel="Audit log period" />
        <ToggleButtonGroup size="small" exclusive value={mode} onChange={(_, v) => v && onMode(v)} aria-label="Audit log view">
          <ToggleButton value="grouped" aria-label="Grouped by member and reason">Grouped</ToggleButton>
          <ToggleButton value="events" aria-label="Individual events">Individual events</ToggleButton>
        </ToggleButtonGroup>
        {mode === 'grouped' && (
          <Chip size="small" clickable label="Repeated only (2+)" aria-pressed={repeatedOnly} variant={repeatedOnly ? 'filled' : 'outlined'}
            color={repeatedOnly ? 'warning' : 'default'} onClick={() => { setPage(1); setRepeatedOnly((v) => !v); }} />
        )}
      </Box>
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', mb: 2 }}>
        <TextField
          size="small" sx={{ flex: '1 1 260px' }} value={search} onChange={(e) => reset(onSearch)(e.target.value)}
          placeholder="Search target, moderator, reason, action, message…" inputProps={{ 'aria-label': 'Search audit log' }}
          InputProps={{ startAdornment: (<InputAdornment position="start"><Search fontSize="small" /></InputAdornment>) }}
        />
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel id="audit-action-label">Action</InputLabel>
          <Select labelId="audit-action-label" label="Action" value={actionType} onChange={(e) => reset(onActionType)(e.target.value)}>
            <MenuItem value="">All actions</MenuItem>
            {['warn', 'mute', 'tempmute', 'kick', 'ban', 'tempban', 'unban', 'unmute', 'purge'].map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
          </Select>
        </FormControl>
      </Box>

      {mode === 'events' ? children : (
        grouped.error && !grouped.data ? <InsightError message={grouped.error} onRetry={grouped.reload} /> :
        grouped.loading && !grouped.data ? <Loading label="Grouping events…" /> :
        !grouped.data || grouped.data.groups.length === 0 ? (
          <EmptyNote>{repeatedOnly ? 'No member has repeated actions in this period.' : 'No moderation actions match these filters.'}</EmptyNote>
        ) : (
          <>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }} aria-live="polite">
              {grouped.data.total_groups.toLocaleString()} group{grouped.data.total_groups === 1 ? '' : 's'} covering {grouped.data.total_events.toLocaleString()} event{grouped.data.total_events === 1 ? '' : 's'}
              {' '}· grouped by member, action and reason/rule
            </Typography>
            <Stack spacing={1.25} aria-busy={grouped.loading}>
              {grouped.data.groups.map((g) => (
                <GroupCard key={g.key} g={g} ctx={{ botId, groupId, isOfficial, days, search: search.trim(), fmt, renderActions }} />
              ))}
            </Stack>
            {grouped.data.pages > 1 && (
              <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                <Pagination count={grouped.data.pages} page={page} onChange={(_, p) => setPage(p)} color="primary" />
              </Box>
            )}
          </>
        )
      )}
    </>
  );
}
