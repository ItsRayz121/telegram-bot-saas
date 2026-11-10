import React, { useEffect, useState } from 'react';
import {
  Alert, Box, Button, CircularProgress, FormControlLabel, MenuItem, Select, Stack, Switch, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Tooltip, Typography,
} from '@mui/material';
import InfoOutlined from '@mui/icons-material/InfoOutlined';

// One shared command-management table for Telegizer (Telegram) and Guildizer (Discord):
//   Command | Who Can Access | Delete Command | Delete Reply | Time (Seconds) | Status
// Every row is independent. The server owns the behaviour: this component only edits rows and
// hands them to onChange(command, patch); the page saves them with onSave().
//
// Props
//   rows        [{command, scope, topic_ids, delete_command, delete_reply, seconds, enabled}]
//   topics      known Telegram forum topics [{thread_id, name}] (accessMode "topics")
//   limits      {min_seconds, max_seconds, can_delete_command, note}
//   accessMode  "topics": Everyone / Selected topics (Telegram)
//               "fixed":  read-only text from accessLabel(row) (Discord: channel limits live in Leveling)
//   failures    jobs that failed in the last 24h (usually: bot is missing the delete right)
const HEAD_CELL = { fontWeight: 600, fontSize: '0.68rem', color: 'text.secondary', lineHeight: 1.2, py: 1, px: 0.75, verticalAlign: 'bottom' };

export function validSeconds(value, limits) {
  const n = Number(value);
  return Number.isInteger(n) && n >= (limits?.min_seconds ?? 1) && n <= (limits?.max_seconds ?? 86400);
}

function SecondsField({ value, limits, onCommit, disabled }) {
  const [text, setText] = useState(String(value));
  useEffect(() => { setText(String(value)); }, [value]);
  const ok = validSeconds(text, limits);
  return (
    <TextField
      size="small" type="number" value={text} disabled={disabled} error={!ok}
      onChange={(e) => {
        setText(e.target.value);
        if (validSeconds(e.target.value, limits)) onCommit(Number(e.target.value));
        else onCommit(null); // invalid: parent blocks Save until fixed
      }}
      inputProps={{ min: limits?.min_seconds ?? 1, max: limits?.max_seconds ?? 86400, 'aria-label': 'Time in seconds' }}
      sx={{ width: '100%', maxWidth: 72, '& input': { py: 0.5, px: 1, fontSize: '0.8rem' } }}
    />
  );
}

function TopicPicker({ row, topics, onChange }) {
  const ids = row.topic_ids || [];
  if (!topics.length) {
    return (
      <TextField
        size="small" fullWidth label="Topic ID or link" placeholder="e.g. 12345 or https://t.me/c/123/456"
        value={row._manual ?? (ids[0] || '')}
        onChange={(e) => {
          const raw = e.target.value;
          const m = raw.match(/(\d+)\s*$/);
          onChange({ _manual: raw, topic_ids: m ? [m[1]] : [] });
        }}
        helperText="No forum topics detected yet. Paste a topic link or enter its ID."
      />
    );
  }
  return (
    <Stack direction="row" flexWrap="wrap" gap={1}>
      {topics.map((t) => (
        <FormControlLabel
          key={t.thread_id}
          control={(
            <Switch
              size="small" checked={ids.includes(String(t.thread_id))}
              onChange={(e) => onChange({
                topic_ids: e.target.checked
                  ? [...new Set([...ids, String(t.thread_id)])]
                  : ids.filter((x) => x !== String(t.thread_id)),
              })}
            />
          )}
          label={t.name}
        />
      ))}
    </Stack>
  );
}

export default function CommandManagementTable({
  rows, topics = [], limits = {}, accessMode = 'topics', accessLabel, failures = 0,
  onChange, onSave, saving = false, dirty = true, invalid = false, loading = false, error = false, onRetry,
}) {
  const canDeleteCommand = limits.can_delete_command !== false;
  const set = (command, patch) => onChange(command, patch);

  if (loading) return <Box sx={{ py: 3, textAlign: 'center' }}><CircularProgress size={22} /></Box>;

  if (error && !rows.length) {
    return (
      <Alert severity="error" action={onRetry ? <Button color="inherit" size="small" onClick={onRetry}>Retry</Button> : null}>
        Could not load the commands (connection problem?). Your settings are unchanged.
      </Alert>
    );
  }

  return (
    <Box>
      {failures > 0 && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          {failures} cleanup{failures > 1 ? 's' : ''} failed in the last 24 hours. Give the bot the “Delete messages” admin
          right, then new cleanups will work.
        </Alert>
      )}
      {!canDeleteCommand && limits.note && (
        <Alert severity="info" icon={<InfoOutlined fontSize="small" />} sx={{ mb: 1.5 }}>{limits.note}</Alert>
      )}
      <TableContainer sx={{ border: 1, borderColor: 'divider', borderRadius: 2, overflowX: 'hidden' }}>
        <Table size="small" sx={{ width: '100%', tableLayout: 'fixed', '& td': { px: 0.75, py: 0.75, fontSize: '0.8rem' } }}>
          <colgroup>
            <col style={{ width: '17%' }} /><col style={{ width: '25%' }} /><col style={{ width: '15%' }} />
            <col style={{ width: '14%' }} /><col style={{ width: '16%' }} /><col style={{ width: '13%' }} />
          </colgroup>
          <TableHead>
            <TableRow>
              <TableCell sx={HEAD_CELL}>Command</TableCell>
              <TableCell sx={HEAD_CELL}>Who Can Access</TableCell>
              <TableCell sx={HEAD_CELL} align="center">
                Delete Command
                <Tooltip title={canDeleteCommand ? "Deletes the member's command message" : 'Not possible on Discord: a slash command is not a message the bot can delete'}>
                  <InfoOutlined sx={{ fontSize: 12, ml: 0.25, verticalAlign: 'middle' }} />
                </Tooltip>
              </TableCell>
              <TableCell sx={HEAD_CELL} align="center">
                Delete Reply
                <Tooltip title="Deletes the bot's answer to the command">
                  <InfoOutlined sx={{ fontSize: 12, ml: 0.25, verticalAlign: 'middle' }} />
                </Tooltip>
              </TableCell>
              <TableCell sx={HEAD_CELL} align="center">
                Time (Seconds)
                <Tooltip title="Counted from the moment the bot's reply is sent. Both messages are removed together.">
                  <InfoOutlined sx={{ fontSize: 12, ml: 0.25, verticalAlign: 'middle' }} />
                </Tooltip>
              </TableCell>
              <TableCell sx={HEAD_CELL} align="center">Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <React.Fragment key={row.command}>
                <TableRow hover sx={{ '& td': { borderBottom: row.scope === 'specific_topics' && accessMode === 'topics' ? 0 : undefined } }}>
                  <TableCell>
                    <Typography component="span" sx={{ fontFamily: 'monospace', fontWeight: 600, fontSize: '0.75rem', wordBreak: 'break-all' }}>
                      {row.command}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    {accessMode === 'topics' ? (
                      <Select
                        size="small" value={row.scope} fullWidth sx={{ fontSize: '0.8rem', '& .MuiSelect-select': { py: 0.5, pl: 1, pr: '24px !important' } }}
                        onChange={(e) => set(row.command, { scope: e.target.value })}
                        inputProps={{ 'aria-label': `Who can use ${row.command}` }}
                      >
                        <MenuItem value="all_group">Everyone</MenuItem>
                        <MenuItem value="specific_topics">Selected topics</MenuItem>
                      </Select>
                    ) : (
                      <Typography variant="body2" color="text.secondary">{accessLabel ? accessLabel(row) : 'Everyone'}</Typography>
                    )}
                  </TableCell>
                  <TableCell align="center">
                    <Switch
                      size="small" checked={canDeleteCommand && row.delete_command}
                      disabled={!canDeleteCommand}
                      onChange={(e) => set(row.command, { delete_command: e.target.checked })}
                      inputProps={{ 'aria-label': `Delete ${row.command} message` }}
                    />
                  </TableCell>
                  <TableCell align="center">
                    <Switch
                      size="small" checked={row.delete_reply}
                      onChange={(e) => set(row.command, { delete_reply: e.target.checked })}
                      inputProps={{ 'aria-label': `Delete ${row.command} reply` }}
                    />
                  </TableCell>
                  <TableCell align="center">
                    <SecondsField
                      value={row.seconds} limits={limits}
                      disabled={!(row.delete_reply || (canDeleteCommand && row.delete_command))}
                      onCommit={(n) => set(row.command, n === null ? { _invalid: true } : { seconds: n, _invalid: false })}
                    />
                  </TableCell>
                  <TableCell align="center">
                    <Switch
                      size="small" checked={row.enabled}
                      onChange={(e) => set(row.command, { enabled: e.target.checked })}
                      inputProps={{ 'aria-label': `${row.command} enabled` }}
                    />
                  </TableCell>
                </TableRow>
                {accessMode === 'topics' && row.scope === 'specific_topics' && (
                  <TableRow>
                    <TableCell colSpan={6} sx={{ pt: 0 }}>
                      <TopicPicker row={row} topics={topics} onChange={(patch) => set(row.command, patch)} />
                    </TableCell>
                  </TableRow>
                )}
              </React.Fragment>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <Stack direction="row" alignItems="center" spacing={2} sx={{ mt: 1.5 }}>
        <Button variant="contained" size="small" disabled={saving || invalid || !dirty} onClick={onSave}>
          {saving ? <CircularProgress size={16} sx={{ mr: 1 }} /> : null}
          Save commands
        </Button>
        {invalid && (
          <Typography variant="caption" color="error">
            Time must be a whole number between {limits.min_seconds ?? 1} and {limits.max_seconds ?? 86400}.
          </Typography>
        )}
      </Stack>
    </Box>
  );
}

// State + load/save wiring shared by every page that shows the table.
//   load(): Promise<{data}>   save(commands): Promise<{data}> (both talk to the real backend)
export function useCommandTable({ load, save, onSaved, onError }) {
  const [state, setState] = useState({ rows: [], topics: [], limits: {}, failures: 0 });
  const [saved, setSaved] = useState('[]');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  const apply = (data) => {
    const rows = data.commands || [];
    setState({ rows, topics: data.topics || [], limits: data.limits || {}, failures: data.delete_failures_24h || 0 });
    setSaved(JSON.stringify(rows));
  };

  const reload = React.useCallback(async () => {
    setLoading(true);
    setError(false);
    try { apply((await load()).data); } catch (e) { setError(true); if (onError) onError(e); } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);
  useEffect(() => { reload(); }, [reload]);

  const clean = (r) => ({
    command: r.command, scope: r.scope, topic_ids: r.topic_ids || [], delete_command: !!r.delete_command,
    delete_reply: !!r.delete_reply, seconds: r.seconds, enabled: !!r.enabled,
  });
  const change = (command, patch) => setState((s) => ({
    ...s, rows: s.rows.map((r) => (r.command === command ? { ...r, ...patch } : r)),
  }));
  const invalid = state.rows.some((r) => r._invalid);
  const dirty = JSON.stringify(state.rows.map(clean)) !== JSON.stringify(JSON.parse(saved).map(clean));

  const doSave = async (visible) => {
    // Only the visible rows that changed are sent, so another section's rows are never overwritten.
    const before = JSON.parse(saved);
    const changed = state.rows.filter((r) => (!visible || visible.includes(r.command))
      && JSON.stringify(clean(r)) !== JSON.stringify(clean(before.find((b) => b.command === r.command) || {})));
    if (!changed.length) return;
    setSaving(true);
    try {
      const res = await save(changed.map(clean));
      apply(res.data);
      if (onSaved) onSaved();
    } catch (e) { if (onError) onError(e); } finally { setSaving(false); }
  };

  return { ...state, loading, saving, dirty, invalid, error, change, save: doSave, reload };
}
