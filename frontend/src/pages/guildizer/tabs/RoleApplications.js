import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Typography, Stack, Chip, Button, Alert, CircularProgress, Autocomplete, TextField, ToggleButtonGroup, ToggleButton,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';

const ERR = {
  already_reviewed: 'Someone already reviewed this one.',
  missing_permission: "Guildizer couldn't give the role — it needs Manage Roles and must sit above that role.",
  member_or_role_gone: 'The member left or the role was deleted.',
  role_not_assignable: 'That role now carries moderation permissions, so it can no longer be granted this way.',
  bot_not_in_server: "Guildizer isn't in this server.",
  discord_error: 'Discord rejected it. Try again.',
};

// Members → Roles → Applications. Members apply on Discord with /applyrole; staff review
// here. Approving grants the real Discord role; the roles on offer are chosen below and can
// never include a role with moderation/management permissions (the server refuses them).
export default function RoleApplications({ guildId, safeRoles }) {
  const [offered, setOffered] = useState(null);
  const [apps, setApps] = useState(null);
  const [status, setStatus] = useState('pending');
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const loadApps = useCallback(() => guildizerApi.get(`/api/guilds/${guildId}/roles/applications`, { params: { status } })
    .then(({ data }) => setApps(data.applications)).catch(() => setMsg({ sev: 'warning', text: "Couldn't load applications." })), [guildId, status]);
  useEffect(() => { loadApps(); }, [loadApps]);
  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/roles/applications/config`).then(({ data }) => setOffered(data.roles)).catch(() => setOffered([]));
  }, [guildId]);

  async function saveOffered(next) {
    setOffered(next);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/roles/applications/config`, { roles: next });
      setOffered(data.roles); setMsg(null);
    } catch (e) {
      setMsg({ sev: 'error', text: e?.response?.data?.error === 'role_not_assignable' ? 'That role carries moderation permissions and cannot be offered.' : "Couldn't save." });
      guildizerApi.get(`/api/guilds/${guildId}/roles/applications/config`).then(({ data }) => setOffered(data.roles)).catch(() => {});
    }
  }

  async function review(a, decision) {
    setBusy(true); setMsg(null);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/roles/applications/${a.id}/review`, { decision });
      setMsg({ sev: 'success', text: decision === 'approve' ? `Approved — ${a.username || a.user_id} now has ${a.role_name}.` : 'Rejected.' });
    } catch (e) {
      setMsg({ sev: 'error', text: ERR[e?.response?.data?.error] || "Couldn't review it." });
    } finally { setBusy(false); loadApps(); }
  }

  const options = (safeRoles || []).map((r) => ({ role_id: r.id, label: r.name }));
  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={600} mb={0.5}>Applications</Typography>
      <Typography variant="body2" color="text.secondary" mb={1}>
        Roles members can apply for with <b>/applyrole</b> (for example Official Creator). Staff approve or reject below.
      </Typography>
      <Autocomplete multiple size="small" options={options} getOptionLabel={(o) => o.label}
        isOptionEqualToValue={(a, b) => a.role_id === b.role_id}
        value={(offered || []).map((o) => options.find((x) => x.role_id === o.role_id) || { role_id: o.role_id, label: o.label || o.role_id })}
        onChange={(_, v) => saveOffered(v.map((x) => ({ role_id: x.role_id, label: x.label })))}
        disabled={offered == null}
        renderInput={(p) => <TextField {...p} label="Roles open for application" placeholder="Add role" />} />
      {msg && <Alert severity={msg.sev} sx={{ mt: 1 }} onClose={() => setMsg(null)}>{msg.text}</Alert>}
      <ToggleButtonGroup exclusive size="small" value={status} onChange={(_, v) => v && setStatus(v)} sx={{ mt: 1.5, mb: 1 }}>
        {['pending', 'approved', 'rejected'].map((s) => <ToggleButton key={s} value={s} sx={{ textTransform: 'capitalize', px: 1.5 }}>{s}</ToggleButton>)}
      </ToggleButtonGroup>
      {!apps && <CircularProgress size={18} />}
      {apps && apps.length === 0 && <Typography variant="body2" color="text.secondary">No {status} applications.</Typography>}
      <Stack spacing={0.75}>
        {apps?.map((a) => (
          <Box key={a.id} sx={{ p: 1, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }} noWrap><b>{a.username || a.user_id}</b> → {a.role_name}</Typography>
              <Typography variant="caption" color="text.secondary">{new Date(a.created_at).toLocaleString()}</Typography>
              {a.status !== 'pending' && <Chip size="small" label={a.status} color={a.status === 'approved' ? 'success' : 'default'} />}
            </Stack>
            {a.evidence && <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5, wordBreak: 'break-word' }}>{a.evidence}</Typography>}
            {a.status === 'pending' && (
              <Stack direction="row" spacing={1} mt={0.75}>
                <Button size="small" variant="contained" disabled={busy} onClick={() => review(a, 'approve')}>Approve</Button>
                <Button size="small" color="inherit" disabled={busy} onClick={() => review(a, 'reject')}>Reject</Button>
              </Stack>
            )}
          </Box>
        ))}
      </Stack>
    </Box>
  );
}
