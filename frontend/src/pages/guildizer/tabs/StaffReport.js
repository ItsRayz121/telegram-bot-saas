import React, { useEffect, useState } from 'react';
import { Box, Typography, FormControlLabel, Switch, TextField, MenuItem, Stack, Alert } from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

// Weekly / monthly staff report, posted to the mod-action log channel (the private staff
// destination chosen above). Counts come from what Guildizer really recorded.
export default function StaffReport({ guildId, logChannelSet }) {
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/staff-report`).then(({ data }) => setCfg(data)).catch(() => setErr("Couldn't load."));
  }, [guildId]);
  async function save(patch) {
    setCfg((c) => ({ ...c, ...patch })); setErr(null);
    try { const { data } = await guildizerApi.put(`/api/guilds/${guildId}/staff-report`, patch); setCfg(data); } catch { setErr("Couldn't save."); }
  }
  if (!cfg) return err ? <Alert severity="warning">{err}</Alert> : null;
  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle2" fontWeight={600}>Staff report</Typography>
      <FormControlLabel control={<Switch checked={!!cfg.enabled} onChange={(e) => save({ enabled: e.target.checked })} />}
        label="Post a summary of moderation and role activity to the log channel" />
      {cfg.enabled && !logChannelSet && <Alert severity="warning" sx={{ mb: 1 }}>Turn on the log channel above first — the report goes there and nowhere else.</Alert>}
      {cfg.enabled && (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <TextField select size="small" label="Every" value={cfg.cadence} sx={{ width: 130 }} onChange={(e) => save({ cadence: e.target.value })}>
            <MenuItem value="weekly">Week</MenuItem><MenuItem value="monthly">Month (1st)</MenuItem>
          </TextField>
          {cfg.cadence === 'weekly' && (
            <TextField select size="small" label="On" value={cfg.weekday} sx={{ width: 140 }} onChange={(e) => save({ weekday: Number(e.target.value) })}>
              {DAYS.map((d, i) => <MenuItem key={d} value={i}>{d}</MenuItem>)}
            </TextField>
          )}
          <TextField type="number" size="small" label="Hour (UTC)" value={cfg.hour_utc} sx={{ width: 110 }}
            inputProps={{ min: 0, max: 23 }} onChange={(e) => save({ hour_utc: Number(e.target.value) })} />
        </Stack>
      )}
      {err && <Alert severity="error" sx={{ mt: 1 }}>{err}</Alert>}
    </Box>
  );
}
