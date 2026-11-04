import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Typography, Stack, Chip, Button, Alert, CircularProgress, FormControlLabel, Switch, FormGroup, Checkbox,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';

const ERR = {
  already_reviewed: 'Someone already reviewed this one.',
  missing_permission: "Discord refused — Guildizer's role must be above the member's top role and have the permission.",
  member_gone: 'The member is no longer in the server.',
  role_not_assignable: 'That role now carries moderation permissions, so it cannot be granted this way.',
  bot_not_in_server: "Guildizer isn't in this server.",
};
const LABEL = { kick: 'Kick', ban: 'Ban', timeout: 'Temporary mute', rank: 'Level rank' };

// Staff approval queue for held severe ladder actions and level ranks. The switches are
// opt-in: with everything off the bot acts immediately, exactly as before.
// kinds = ['kick','ban','timeout'] (Moderation) or ['rank'] (Roles); roleName resolves rank ids.
export default function ApprovalQueue({ guildId, kinds, roleName }) {
  const [data, setData] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => guildizerApi.get(`/api/guilds/${guildId}/approvals`)
    .then(({ data: d }) => setData(d)).catch(() => setMsg({ sev: 'warning', text: "Couldn't load approvals." })), [guildId]);
  useEffect(() => { load(); }, [load]);

  const setting = data?.settings || { require_approval: [], rank_approval: false };
  async function save(patch) {
    setData((d) => ({ ...d, settings: { ...d.settings, ...patch } }));
    try { await guildizerApi.put(`/api/guilds/${guildId}/approvals/settings`, patch); } catch { setMsg({ sev: 'error', text: "Couldn't save." }); load(); }
  }
  async function review(a, decision) {
    setBusy(true); setMsg(null);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/approvals/${a.id}/review`, { decision });
      setMsg({ sev: 'success', text: decision === 'approve' ? `Approved — ${LABEL[a.kind].toLowerCase()} applied to ${a.username || a.user_id}.` : 'Rejected — nothing was done.' });
    } catch (e) { setMsg({ sev: 'error', text: ERR[e?.response?.data?.error] || "Couldn't review it." }); } finally { setBusy(false); load(); }
  }

  const rows = (data?.approvals || []).filter((a) => kinds.includes(a.kind));
  const ranks = kinds.includes('rank');
  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={600} mb={0.5}>Staff approval</Typography>
      {ranks ? (
        <FormControlLabel control={<Switch checked={!!setting.rank_approval} onChange={(e) => save({ rank_approval: e.target.checked })} />}
          label="Level ranks wait for staff approval instead of being granted automatically" />
      ) : (
        <>
          <Typography variant="body2" color="text.secondary">Hold these Warning Escalation actions until a staff member approves them here. Unticked actions run immediately.</Typography>
          <FormGroup row>
            {kinds.map((k) => (
              <FormControlLabel key={k} label={LABEL[k]}
                control={<Checkbox size="small" checked={setting.require_approval.includes(k)}
                  onChange={(e) => save({ require_approval: e.target.checked ? [...setting.require_approval, k] : setting.require_approval.filter((x) => x !== k) })} />} />
            ))}
          </FormGroup>
        </>
      )}
      {msg && <Alert severity={msg.sev} sx={{ my: 1 }} onClose={() => setMsg(null)}>{msg.text}</Alert>}
      {!data && <CircularProgress size={18} />}
      {data && rows.length === 0 && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>Nothing waiting for approval.</Typography>}
      <Stack spacing={0.75} sx={{ mt: 1 }}>
        {rows.map((a) => (
          <Box key={a.id} sx={{ p: 1, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Chip size="small" color={a.kind === 'ban' ? 'error' : 'warning'} variant="outlined" label={LABEL[a.kind]} />
              <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }} noWrap>
                <b>{a.username || a.user_id}</b>{a.kind === 'rank' && a.role_id ? ` → ${roleName ? roleName(a.role_id) : a.role_id}` : ''}{a.kind === 'timeout' && a.minutes ? ` · ${a.minutes} min` : ''}
              </Typography>
              <Typography variant="caption" color="text.secondary">{new Date(a.created_at).toLocaleString()}</Typography>
            </Stack>
            {a.reason && <Typography variant="caption" color="text.secondary" display="block">{a.reason}</Typography>}
            {a.result_error && <Typography variant="caption" color="error" display="block">Last attempt failed: {ERR[a.result_error] || a.result_error}</Typography>}
            <Stack direction="row" spacing={1} mt={0.75}>
              <Button size="small" variant="contained" color={a.kind === 'ban' ? 'error' : 'primary'} disabled={busy} onClick={() => review(a, 'approve')}>Approve</Button>
              <Button size="small" color="inherit" disabled={busy} onClick={() => review(a, 'reject')}>Reject</Button>
            </Stack>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}
