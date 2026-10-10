import React, { useState } from 'react';
import {
  Alert, Box, Button, Chip, Collapse, IconButton, InputAdornment, Pagination, Paper, Stack,
  TextField, ToggleButton, ToggleButtonGroup, Tooltip, Typography,
} from '@mui/material';
import { Delete, Search } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { insights, settings } from '../../services/api';
import {
  BreakdownBars, EmptyNote, InsightError, Loading, MemberLink, Panel, PeriodChips, ProfileButton,
  StatGrid, StatTile, TrendChart, memberProfilePath, useInsight,
} from './shared';

const PERIODS = [
  { key: '7d', label: '7 days' },
  { key: '30d', label: '30 days' },
  { key: '90d', label: '90 days' },
];

/** Plain-language description of the group's EXISTING escalation setup (read-only). */
export function describeEscalation(e) {
  if (!e) return null;
  const parts = [];
  if (e.single_threshold?.enabled && e.single_threshold.threshold) {
    const w = e.single_threshold.window_hours;
    parts.push(`${e.single_threshold.action || 'action'} at ${e.single_threshold.threshold} warnings${w ? ` within ${w}h` : ''}`);
  }
  if (e.ladder_enabled && e.ladder_steps?.length) {
    parts.push(`escalation ladder: ${[...e.ladder_steps].sort((a, b) => (a.at_warning || 0) - (b.at_warning || 0))
      .map((s) => `${s.action || 'action'} at ${s.at_warning}`).join(' → ')}`);
  } else if (!e.ladder_enabled && e.max_warnings) {
    parts.push(`${e.warning_action || 'action'} at ${e.max_warnings} warnings`);
  }
  return parts.length ? parts.join(' · ') : 'No automatic escalation configured';
}

function MemberHistory({ botId, groupId, userId, isViewer, onChanged, fmt }) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const load = React.useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const r = await insights.member(botId, groupId, userId);
      setState({ data: r.data, loading: false, error: null });
    } catch (e) {
      setState({ data: null, loading: false, error: e?.response?.data?.error || 'Could not load warning history' });
    }
  }, [botId, groupId, userId]);
  React.useEffect(() => { load(); }, [load]);

  const remove = async (id) => {
    try {
      await settings.removeWarning(botId, groupId, id);
      toast.success('Warning removed');
      await load();
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.error || 'Failed to remove warning');
    }
  };

  if (state.loading) return <Loading label="Loading history…" />;
  if (state.error) return <InsightError message={state.error} onRetry={load} />;
  const ws = state.data.warnings;
  return (
    <Box sx={{ mt: 1 }}>
      {ws.map((w) => (
        <Box key={w.id} sx={{ py: 1, borderTop: '1px solid', borderColor: 'divider', display: 'flex', gap: 1, alignItems: 'flex-start' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
              <Typography variant="caption" fontWeight={700}>{fmt(w.created_at)}</Typography>
              <Chip size="small" label={w.active ? 'Active' : 'Removed'} color={w.active ? 'warning' : 'default'} variant={w.active ? 'filled' : 'outlined'} />
              <Typography variant="caption" color="text.secondary">Issued by {w.moderator || 'unknown'}</Typography>
            </Box>
            {w.reason && <Typography variant="body2" sx={{ mt: 0.25, wordBreak: 'break-word' }}>{w.reason}</Typography>}
            {w.message_text && (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                Message: {w.message_text}
              </Typography>
            )}
          </Box>
          {w.active && (
            <Tooltip title={isViewer ? 'View-only access' : 'Remove this warning'}>
              <span>
                <IconButton size="small" color="error" aria-label="Remove warning" disabled={isViewer} onClick={() => remove(w.id)}>
                  <Delete fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          )}
        </Box>
      ))}
      {state.data.moderation_event_total > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', pt: 1 }}>
          {state.data.moderation_event_total} related moderation event{state.data.moderation_event_total === 1 ? '' : 's'} — open the profile for the full timeline.
        </Typography>
      )}
    </Box>
  );
}

function MemberRow({ m, ctx }) {
  const { botId, groupId, isOfficial, fmt, isViewer, renderActions, onChanged } = ctx;
  const [open, setOpen] = useState(false);
  const profile = memberProfilePath({ isOfficial, botId, groupId, userId: m.user_id });
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <Box sx={{ minWidth: 0, flex: '1 1 220px' }}>
          <MemberLink member={m} profile={profile} secondary={m.user_id ? `ID ${m.user_id}` : undefined} />
        </Box>
        <Chip size="small" color={m.active_warnings > 1 ? 'warning' : 'default'} variant={m.active_warnings > 1 ? 'filled' : 'outlined'}
          label={`${m.active_warnings} active warning${m.active_warnings === 1 ? '' : 's'}`} />
      </Box>
      <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
        {m.reasons.map((r) => <Chip key={r.label} size="small" variant="outlined" label={`${r.label}${r.count > 1 ? ` ×${r.count}` : ''}`} />)}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
        Issued by {m.issuers.map((i) => `${i.name}${i.count > 1 ? ` (${i.count})` : ''}`).join(', ')} · latest {fmt(m.latest_at)}
        {m.active_warnings > 1 ? ` · first ${fmt(m.first_at)}` : ''}
      </Typography>
      <Box sx={{ display: 'flex', gap: 1, mt: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <Button size="small" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? 'Hide history' : 'Show warning history'}</Button>
        <ProfileButton to={profile} />
        {renderActions && renderActions(m.user_id, m.username)}
      </Box>
      <Collapse in={open} unmountOnExit>
        <MemberHistory botId={botId} groupId={groupId} userId={m.user_id} isViewer={isViewer} onChanged={onChanged} fmt={fmt} />
      </Collapse>
    </Paper>
  );
}

export default function WarningsPanel({
  botId, groupId, isOfficial, mode, onMode, fmt, isViewer, renderActions, refreshKey, onChanged, children,
}) {
  const [period, setPeriod] = useState('30d');
  const [multiOnly, setMultiOnly] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const summary = useInsight(botId, groupId, 'warnings-summary', { days: period, _r: refreshKey });
  const members = useInsight(botId, groupId, 'warnings-members', {
    search: search.trim() || undefined, min_count: multiOnly ? 2 : 1, page, per_page: 20, _r: refreshKey,
  }, mode === 'members');
  const s = summary.data;
  const rule = describeEscalation(s?.escalation);

  return (
    <>
      {summary.error && !s ? <InsightError message={summary.error} onRetry={summary.reload} /> : (
        <>
          <StatGrid>
            <StatTile label="Active warning records" value={s?.active_records} loading={summary.loading && !s}
              hint="Currently counting · not period-limited" tone={s?.active_records ? 'warning.main' : undefined} />
            <StatTile label="Members holding them" value={s?.members_with_active} loading={summary.loading && !s}
              hint="Distinct members with 1+ active" />
            <StatTile label="Members with multiple" value={s?.members_with_multiple} loading={summary.loading && !s}
              hint={s?.max_active_per_member > 1 ? `Most held by one member: ${s.max_active_per_member}` : '2+ active warnings · select to filter'}
              selected={mode === 'members' && multiOnly}
              onClick={() => { onMode('members'); setPage(1); setMultiOnly((v) => !v); }} />
            <StatTile label={`Issued · last ${period.replace('d', '')} days`} value={s?.issued_in_period} loading={summary.loading && !s}
              hint={s ? `${s.issued_members_in_period} member${s.issued_members_in_period === 1 ? '' : 's'}${s.removed_in_period != null ? ` · ${s.removed_in_period} since removed` : ' · removed ones are not kept'}` : undefined} />
          </StatGrid>
          {rule && (
            <Alert severity="info" icon={false} sx={{ mb: 2 }}>
              <strong>Current escalation rule:</strong> {rule}. Grouping members here is only a view — it does not create or change any threshold.
            </Alert>
          )}
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '3fr 2fr' }, mb: 2 }}>
            <Panel
              title="Warnings issued over time"
              subtitle="Warnings issued in the selected period, including ones later removed (history, not the current total)"
              action={<PeriodChips value={period} options={PERIODS} onChange={setPeriod} ariaLabel="Warning history period" />}
              sx={{ mb: 0 }}
            >
              <TrendChart series={s?.series || []} keys={[{ key: 'count', label: 'Warnings issued', color: '#f59e0b' }]} height={150}
                emptyText={summary.loading && !s ? 'Loading…' : 'No warnings were issued in this period.'} />
            </Panel>
            <Panel title="Why members are warned" subtitle="Active warnings by reason" sx={{ mb: 0 }}>
              <BreakdownBars rows={s?.by_reason || []} color="warning.main" />
              {s && (s.by_issuer.Automation || s.by_issuer.Moderator) ? (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
                  Issued by automation: {s.by_issuer.Automation || 0} · by moderators: {s.by_issuer.Moderator || 0}
                </Typography>
              ) : null}
            </Panel>
          </Box>
        </>
      )}

      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mb: 1.5 }}>
        <ToggleButtonGroup size="small" exclusive value={mode} onChange={(_, v) => v && onMode(v)} aria-label="Warnings view">
          <ToggleButton value="members">By member</ToggleButton>
          <ToggleButton value="records">All records</ToggleButton>
        </ToggleButtonGroup>
        {mode === 'members' && (
          <Chip size="small" clickable label="Multiple warnings only (2+)" aria-pressed={multiOnly} variant={multiOnly ? 'filled' : 'outlined'}
            color={multiOnly ? 'warning' : 'default'} onClick={() => { setPage(1); setMultiOnly((v) => !v); }} />
        )}
      </Box>

      {mode === 'records' ? children : (
        <>
          <TextField size="small" fullWidth sx={{ mb: 1.5 }} value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }}
            placeholder="Search member id, name, username, reason, moderator…" inputProps={{ 'aria-label': 'Search warned members' }}
            InputProps={{ startAdornment: (<InputAdornment position="start"><Search fontSize="small" /></InputAdornment>) }} />
          {members.error && !members.data ? <InsightError message={members.error} onRetry={members.reload} /> :
            members.loading && !members.data ? <Loading label="Loading warned members…" /> :
            !members.data || members.data.members.length === 0 ? (
              <EmptyNote>{multiOnly ? 'No member holds more than one active warning.' : search ? 'No warned members match your search.' : 'No active warnings in this group.'}</EmptyNote>
            ) : (
              <>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }} aria-live="polite">
                  {members.data.total.toLocaleString()} member{members.data.total === 1 ? '' : 's'} with active warnings
                </Typography>
                <Stack spacing={1.25} aria-busy={members.loading}>
                  {members.data.members.map((m) => (
                    <MemberRow key={m.user_id} m={m} ctx={{ botId, groupId, isOfficial, fmt, isViewer, renderActions, onChanged }} />
                  ))}
                </Stack>
                {members.data.pages > 1 && (
                  <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                    <Pagination count={members.data.pages} page={page} onChange={(_, p) => setPage(p)} color="primary" />
                  </Box>
                )}
              </>
            )}
        </>
      )}
    </>
  );
}
