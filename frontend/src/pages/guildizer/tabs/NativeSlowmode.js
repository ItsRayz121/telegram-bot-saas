import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box, Typography, Button, Chip, CircularProgress, Alert, Stack, IconButton, Checkbox,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem, Autocomplete, Tooltip,
} from '@mui/material';
import { Add, Edit, Refresh, PowerSettingsNew } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

// Discord-native cooldown presets (rate_limit_per_user, seconds). Any 0–21600 is valid;
// these are the ones Discord's own UI offers.
export const SLOWMODE_PRESETS = [
  [5, '5s'], [10, '10s'], [15, '15s'], [30, '30s'], [60, '1 min'], [120, '2 min'],
  [300, '5 min'], [600, '10 min'], [900, '15 min'], [1800, '30 min'],
  [3600, '1 hour'], [7200, '2 hours'], [21600, '6 hours'],
];
export const fmtCooldown = (s) => {
  const p = SLOWMODE_PRESETS.find(([v]) => v === s);
  if (p) return p[1];
  if (s >= 3600 && s % 3600 === 0) return `${s / 3600} h`;
  if (s >= 60 && s % 60 === 0) return `${s / 60} min`;
  return `${s}s`;
};
const ERR = {
  missing_permission: 'Missing Manage Channels permission here',
  channel_not_found: 'Channel no longer exists',
  rate_limited: 'Discord rate limit — try again',
  not_in_server: 'Not a channel of this server',
  discord_error: 'Discord rejected the change',
};

// Channel Slow Mode (Discord native): one cooldown per channel, applied to many at once.
// Reads the LIVE value from Discord, so changes made in Discord itself show up here.
export default function NativeSlowmode({ guildId, botPaced }) {
  const [channels, setChannels] = useState(null);
  const [loadErr, setLoadErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [picked, setPicked] = useState([]);           // checked rows for bulk edit
  const [dlg, setDlg] = useState(null);               // { ids: [channelId], seconds }

  const load = useCallback(() => {
    setLoadErr(null);
    return guildizerApi.get(`/api/guilds/${guildId}/native-slowmode`)
      .then(({ data }) => setChannels(data.channels))
      .catch((e) => setLoadErr(e?.response?.data?.error === 'bot_not_in_server'
        ? 'Guildizer isn\'t in this server yet.'
        : 'Couldn\'t read the channels from Discord.'));
  }, [guildId]);
  useEffect(() => { load(); }, [load]);

  const byId = useMemo(() => Object.fromEntries((channels || []).map((c) => [c.id, c])), [channels]);
  const active = (channels || []).filter((c) => c.seconds > 0);

  async function apply(ids, seconds) {
    setBusy(true); setMsg(null);
    try {
      let data;
      try {
        ({ data } = await guildizerApi.post(`/api/guilds/${guildId}/native-slowmode`,
          { channel_ids: ids, seconds }));
      } catch (e) {
        data = e?.response?.data;
        if (!data?.results) throw e;               // 207 partial arrives as a result body
      }
      const failed = data.results.filter((r) => !r.ok);
      const done = data.results.length - failed.length;
      setMsg(failed.length
        ? { sev: 'warning', text: `${done} updated, ${failed.length} failed: ${failed.map((r) => `#${r.name || r.channel_id} (${ERR[r.error] || r.error})`).join(', ')}` }
        : { sev: 'success', text: seconds ? `Cooldown ${fmtCooldown(seconds)} set on ${done} channel${done === 1 ? '' : 's'}.` : `Slow mode turned off on ${done} channel${done === 1 ? '' : 's'}.` });
      setPicked((p) => p.filter((id) => failed.some((r) => r.channel_id === id)));
      setDlg((d) => (failed.length ? { ids: failed.map((r) => r.channel_id), seconds: d?.seconds ?? seconds } : null));
    } catch (e) {
      setMsg({ sev: 'error', text: e?.response?.data?.error === 'bot_not_in_server'
        ? 'Guildizer isn\'t in this server yet.' : 'Couldn\'t reach Discord — nothing was changed.' });
    } finally { setBusy(false); load(); }
  }

  const togglePick = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={0.5}>
        <Typography variant="subtitle2" fontWeight={600}>Channel Slow Mode · Discord native</Typography>
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="Re-read from Discord"><span>
            <IconButton size="small" onClick={load} aria-label="Refresh from Discord"><Refresh fontSize="small" /></IconButton>
          </span></Tooltip>
          <Button size="small" variant="contained" startIcon={<Add />} disabled={!channels}
            onClick={() => setDlg({ ids: [], seconds: 30 })}>Add Channels</Button>
        </Stack>
      </Stack>
      <Typography variant="body2" color="text.secondary" mb={1.5}>
        Discord enforces the cooldown <b>per channel</b> and keeps working when Guildizer is offline.
        Pick several channels to apply one cooldown in one go. Needs <b>Manage Channels</b>.
      </Typography>

      {loadErr && <Alert severity="warning" sx={{ mb: 1 }}>{loadErr}</Alert>}
      {msg && <Alert severity={msg.sev} sx={{ mb: 1 }} onClose={() => setMsg(null)}>{msg.text}</Alert>}
      {!channels && !loadErr && <CircularProgress size={20} />}

      {channels && active.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
          No channel has a cooldown. Use <b>Add Channels</b> to set one.
        </Typography>
      )}

      {picked.length > 0 && (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="caption">{picked.length} selected</Typography>
          <Button size="small" onClick={() => setDlg({ ids: picked, seconds: byId[picked[0]]?.seconds || 30 })}>Change cooldown</Button>
          <Button size="small" color="warning" disabled={busy} onClick={() => apply(picked, 0)}>Turn off</Button>
        </Stack>
      )}

      <Stack spacing={0.5}>
        {active.map((c) => (
          <Stack key={c.id} direction="row" alignItems="center" spacing={1}
            sx={{ px: 1, py: 0.5, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
            <Checkbox size="small" checked={picked.includes(c.id)} onChange={() => togglePick(c.id)}
              inputProps={{ 'aria-label': `Select #${c.name}` }} />
            <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }} noWrap>
              {c.type === 2 ? '🔊' : '#'} {c.name}
            </Typography>
            <Chip size="small" label={fmtCooldown(c.seconds)} />
            <Chip size="small" color="success" variant="outlined" label="Active" />
            {botPaced && !botPaced.excluded.includes(String(c.id)) && (
              <Tooltip title="Server-wide Protection is also on and covers this channel: a message can be blocked by Discord's cooldown AND removed by the bot if it follows the member's previous message too soon.">
                <Chip size="small" color="warning" variant="outlined" label="Also bot-paced" />
              </Tooltip>
            )}
            <Tooltip title="Edit cooldown"><IconButton size="small" aria-label={`Edit #${c.name}`}
              onClick={() => setDlg({ ids: [c.id], seconds: c.seconds })}><Edit fontSize="small" /></IconButton></Tooltip>
            <Tooltip title="Turn off slow mode (channel is kept)"><span>
              <IconButton size="small" aria-label={`Turn off slow mode on #${c.name}`} disabled={busy}
                onClick={() => apply([c.id], 0)}><PowerSettingsNew fontSize="small" /></IconButton>
            </span></Tooltip>
          </Stack>
        ))}
      </Stack>

      <Dialog open={!!dlg} onClose={() => !busy && setDlg(null)} fullWidth maxWidth="sm">
        <DialogTitle>{dlg?.ids.length && dlg.ids.every((i) => byId[i]?.seconds > 0) ? 'Change cooldown' : 'Add channels'}</DialogTitle>
        <DialogContent>
          <Autocomplete multiple disableCloseOnSelect size="small" sx={{ mt: 1 }}
            options={channels || []} value={(dlg?.ids || []).map((i) => byId[i]).filter(Boolean)}
            getOptionLabel={(c) => `${c.type === 2 ? '🔊' : '#'} ${c.name}`}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            onChange={(_, v) => setDlg((d) => ({ ...d, ids: v.map((c) => c.id) }))}
            renderOption={(props, c) => (
              <li {...props} key={c.id}>
                {c.type === 2 ? '🔊' : '#'} {c.name}
                {c.seconds > 0 && <Chip size="small" sx={{ ml: 1 }} label={fmtCooldown(c.seconds)} />}
              </li>
            )}
            renderInput={(p) => <TextField {...p} label="Channels" placeholder="Search channels" />} />
          <TextField select size="small" fullWidth sx={{ mt: 2 }} label="Cooldown"
            value={dlg?.seconds ?? 30} onChange={(e) => setDlg((d) => ({ ...d, seconds: Number(e.target.value) }))}
            helperText="Applied to every selected channel. Different channels can have different cooldowns.">
            {SLOWMODE_PRESETS.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
            {dlg && !SLOWMODE_PRESETS.some(([v]) => v === dlg.seconds) && dlg.seconds > 0 &&
              <MenuItem value={dlg.seconds}>{fmtCooldown(dlg.seconds)} (current)</MenuItem>}
          </TextField>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDlg(null)} disabled={busy}>Cancel</Button>
          <Button variant="contained" disabled={busy || !dlg?.ids.length} onClick={() => apply(dlg.ids, dlg.seconds)}>
            {busy ? 'Applying…' : `Apply to ${dlg?.ids.length || 0}`}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
