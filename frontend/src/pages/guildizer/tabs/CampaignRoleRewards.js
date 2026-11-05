import React, { useCallback, useEffect, useState } from 'react';
import { Box, Typography, Stack, TextField, MenuItem, Chip, Alert, CircularProgress, FormControlLabel, Switch } from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';

const ERR = {
  role_not_assignable: 'That role carries moderation or management permissions, so it cannot be a reward.',
  unknown_role: 'That role is not in this server (try refreshing).',
};

// Members → Roles → Campaign reward roles. Pick a role per campaign: every member whose
// submission is VERIFIED receives it once (granted by the bot within about 30 seconds). Plain
// roles only; the campaign itself is configured in Engagement → Campaigns, untouched.
export default function CampaignRoleRewards({ guildId, safeRoles }) {
  const [rows, setRows] = useState(null);
  const [msg, setMsg] = useState(null);
  const [includePast, setIncludePast] = useState(false);

  const load = useCallback(() => guildizerApi.get(`/api/guilds/${guildId}/roles/campaign-rewards`)
    .then(({ data }) => setRows(data.campaigns)).catch(() => setMsg({ sev: 'warning', text: "Couldn't load campaigns." })), [guildId]);
  useEffect(() => { load(); }, [load]);

  async function setRole(c, roleId) {
    setMsg(null);
    try {
      await guildizerApi.put(`/api/guilds/${guildId}/roles/campaign-rewards/${c.id}`, { role_id: roleId, include_past: includePast });
      setMsg({ sev: 'success', text: roleId ? `Verified members of "${c.title}" will receive the role.` : 'Reward role removed.' });
    } catch (e) { setMsg({ sev: 'error', text: ERR[e?.response?.data?.error] || "Couldn't save." }); }
    load();
  }

  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={600} mb={0.5}>Campaign reward roles</Typography>
      <Typography variant="body2" color="text.secondary" mb={1}>
        A member whose campaign submission is verified earns the role you pick — once, even for multi-task campaigns.
      </Typography>
      <FormControlLabel control={<Switch size="small" checked={includePast} onChange={(e) => setIncludePast(e.target.checked)} />}
        label="Also give it to members who were verified before I set it" />
      {msg && <Alert severity={msg.sev} sx={{ my: 1 }} onClose={() => setMsg(null)}>{msg.text}</Alert>}
      {!rows && <CircularProgress size={18} />}
      {rows && rows.length === 0 && <Typography variant="body2" color="text.secondary">No campaigns yet.</Typography>}
      <Stack spacing={0.75} sx={{ mt: 1 }}>
        {rows?.map((c) => (
          <Stack key={c.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap
            sx={{ p: 1, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
            <Typography variant="body2" sx={{ flex: '1 1 160px', minWidth: 0 }} noWrap>{c.title}</Typography>
            <Chip size="small" variant="outlined" label={c.status} />
            <TextField select size="small" label="Reward role" value={c.role_id || ''} sx={{ minWidth: 180 }}
              onChange={(e) => setRole(c, e.target.value)}>
              <MenuItem value="">— none —</MenuItem>
              {safeRoles.map((r) => <MenuItem key={r.id} value={r.id}>{r.name}</MenuItem>)}
              {c.role_id && !safeRoles.some((r) => r.id === c.role_id) && <MenuItem value={c.role_id}>{c.role_id}</MenuItem>}
            </TextField>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}
