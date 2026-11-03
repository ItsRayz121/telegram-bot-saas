import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Box, Card, CardContent, Typography, CircularProgress, Alert, List, ListItem,
  ListItemText, Stack, IconButton, Button, Tooltip, Chip, TextField, MenuItem, Divider,
} from '@mui/material';
import { Delete, Add, ContentCopy, Send } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const ROLE_HELP = {
  manager: 'Manager: full control of this server in the dashboard.',
  viewer: 'Viewer: can look at everything but cannot change anything.',
};
const STATUS_COLOR = { pending: 'warning', accepted: 'success', declined: 'default', expired: 'default' };

const errorText = (e, fallback) => e?.response?.data?.message || fallback;

function RoleSelect({ value, onChange, disabled, label = 'Role' }) {
  return (
    <TextField select size="small" label={label} value={value} disabled={disabled}
      onChange={(e) => onChange(e.target.value)} sx={{ minWidth: 130 }}>
      <MenuItem value="manager">Manager</MenuItem>
      <MenuItem value="viewer">Viewer</MenuItem>
    </TextField>
  );
}

export default function TeamTab({ guildId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [team, setTeam] = useState({ members: [], invites: [], direct_invites: [], invitations: [] });
  const [busy, setBusy] = useState(false);
  const [codeRole, setCodeRole] = useState('manager');
  const [directRole, setDirectRole] = useState('manager');
  const [query, setQuery] = useState('');
  const [found, setFound] = useState([]);
  const searchSeq = useRef(0);

  const base = `/api/guilds/${guildId}/team`;
  const readOnly = team.your_role === 'viewer';
  const disabled = team.enabled === false;

  const load = useCallback(async () => {
    try {
      const { data } = await guildizerApi.get(base);
      setTeam(data); setError(null);
    } catch { setError('Failed to load the team.'); }
    setLoading(false);
  }, [base]);

  useEffect(() => { load(); }, [load]);

  // Search the server's member list (debounced); a stale response never overwrites a newer one.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2 || readOnly) { setFound([]); return undefined; }
    const seq = ++searchSeq.current;
    const t = setTimeout(async () => {
      try {
        const { data } = await guildizerApi.get(`${base}/candidates`, { params: { q } });
        if (seq === searchSeq.current) setFound(data.members || []);
      } catch { if (seq === searchSeq.current) setFound([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [query, base, readOnly]);

  async function run(fn, fail) {
    setBusy(true); setNotice(null);
    try { await fn(); await load(); return true; }
    catch (e) { setError(errorText(e, fail)); return false; }
    finally { setBusy(false); }
  }

  const createInvite = () => run(
    () => guildizerApi.post(`${base}/invites`, { role: codeRole }), 'Could not create an invite.');

  const sendDirect = async (member) => {
    const ok = await run(
      () => guildizerApi.post(`${base}/invites/direct`, { discord_user_id: member.user_id, role: directRole }),
      'Could not send the invitation.');
    if (ok) { setNotice(`Invitation sent to ${member.username}. They accept it in a Discord DM.`); setQuery(''); setFound([]); }
  };

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600}>Team access</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={2}>
        Give dashboard access to people who don't have Manage Server on Discord. Invite someone
        directly (the bot sends them a message with Accept / Decline) or share a one-use code that
        they redeem from the Discord page. Invitations expire after 7 days.
      </Typography>
      {disabled && <Alert severity="warning" sx={{ mb: 1 }}>Team access is switched off right now. Existing members cannot sign in to this server until it is turned back on.</Alert>}
      {readOnly && <Alert severity="info" sx={{ mb: 1 }}>You have view-only access, so you can see the team but not change it.</Alert>}
      {error && <Alert severity="warning" sx={{ mb: 1 }} onClose={() => setError(null)}>{error}</Alert>}
      {notice && <Alert severity="success" sx={{ mb: 1 }} onClose={() => setNotice(null)}>{notice}</Alert>}

      {!readOnly && (
        <>
          <Typography variant="subtitle2" fontWeight={700}>Invite a server member</Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} mt={0.5} alignItems={{ sm: 'center' }}>
            <TextField size="small" fullWidth label="Search members by name" value={query}
              disabled={disabled || team.direct_enabled === false}
              onChange={(e) => setQuery(e.target.value)} />
            <RoleSelect value={directRole} onChange={setDirectRole} disabled={disabled} />
          </Stack>
          <Typography variant="caption" color="text.secondary" display="block" mt={0.5}>
            {team.direct_enabled === false
              ? 'Direct invitations are paused. Use an access code below.'
              : `${ROLE_HELP[directRole]} Only people already in this server's member list can be invited.`}
          </Typography>
          {found.length > 0 && (
            <List dense>
              {found.map((m) => (
                <ListItem key={m.user_id} disableGutters
                  secondaryAction={m.has_access ? <Chip size="small" label={`Already ${m.member_role}`} />
                    : m.pending ? <Chip size="small" color="warning" label="Invite pending" />
                      : (
                        <Button size="small" variant="contained" startIcon={<Send />} disabled={busy}
                          onClick={() => sendDirect(m)}>Invite</Button>
                      )}>
                  <ListItemText primary={m.username || m.user_id} />
                </ListItem>
              ))}
            </List>
          )}
          <Divider sx={{ my: 2 }} />
          <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
            <Typography variant="subtitle2" fontWeight={700}>Access code</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <RoleSelect value={codeRole} onChange={setCodeRole} disabled={disabled} />
              <Button startIcon={<Add />} variant="outlined" size="small" disabled={busy || disabled} onClick={createInvite}>
                New invite code
              </Button>
            </Stack>
          </Stack>
        </>
      )}

      {team.invites.length > 0 && (
        <List dense>
          {team.invites.map((i) => (
            <ListItem key={i.id} disableGutters
              secondaryAction={(
                <Stack direction="row" spacing={0.5}>
                  <Tooltip title="Copy code">
                    <IconButton size="small" onClick={() => navigator.clipboard.writeText(i.code)}>
                      <ContentCopy fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <IconButton aria-label="Delete" size="small" color="error"
                    onClick={() => run(() => guildizerApi.delete(`${base}/invites/${i.id}`), 'Could not delete the invite.')}>
                    <Delete fontSize="small" />
                  </IconButton>
                </Stack>
              )}>
              <Chip size="small" variant="outlined" label={i.role} sx={{ mr: 1 }} />
              <ListItemText primary={<code>{i.code}</code>}
                secondary={`expires ${new Date(i.expires_at).toLocaleString()}`} />
            </ListItem>
          ))}
        </List>
      )}

      {team.direct_invites.length > 0 && (
        <>
          <Typography variant="subtitle2" fontWeight={700} mt={1}>Waiting for an answer</Typography>
          <List dense>
            {team.direct_invites.map((i) => (
              <ListItem key={i.id} disableGutters
                secondaryAction={!readOnly && (
                  <IconButton aria-label="Cancel invitation" size="small" color="error"
                    onClick={() => run(() => guildizerApi.delete(`${base}/invites/${i.id}`), 'Could not cancel the invitation.')}>
                    <Delete fontSize="small" />
                  </IconButton>
                )}>
                <Chip size="small" variant="outlined" label={i.role} sx={{ mr: 1 }} />
                <ListItemText primary={i.invitee_name || i.invitee_discord_id}
                  secondary={`expires ${new Date(i.expires_at).toLocaleString()}`} />
              </ListItem>
            ))}
          </List>
        </>
      )}

      <Typography variant="subtitle2" fontWeight={700} mt={1}>Members</Typography>
      {team.members.length === 0 && <Typography variant="body2" color="text.secondary">No team members yet.</Typography>}
      <List dense>
        {team.members.map((m) => (
          <ListItem key={m.user_id} disableGutters
            secondaryAction={!readOnly && (
              <IconButton aria-label="Delete" size="small" color="error"
                onClick={() => run(() => guildizerApi.delete(`${base}/members/${m.user_id}`), 'Could not remove the member.')}>
                <Delete fontSize="small" />
              </IconButton>
            )}>
            {readOnly
              ? <Chip size="small" variant="outlined" label={m.role} sx={{ mr: 1 }} />
              : (
                <TextField select size="small" value={m.role} sx={{ mr: 1, minWidth: 110 }} disabled={busy}
                  onChange={(e) => run(
                    () => guildizerApi.patch(`${base}/members/${m.user_id}`, { role: e.target.value }),
                    'Could not change the role.')}>
                  <MenuItem value="manager">Manager</MenuItem>
                  <MenuItem value="viewer">Viewer</MenuItem>
                </TextField>
              )}
            <ListItemText primary={m.username || m.user_id}
              secondary={`since ${m.created_at ? new Date(m.created_at).toLocaleDateString() : ''}`} />
          </ListItem>
        ))}
      </List>

      {team.invitations.length > 0 && (
        <>
          <Typography variant="subtitle2" fontWeight={700} mt={1}>Invitation history</Typography>
          <List dense>
            {team.invitations.map((i) => (
              <ListItem key={i.id} disableGutters>
                <Chip size="small" color={STATUS_COLOR[i.status] || 'default'} label={i.status} sx={{ mr: 1, minWidth: 78 }} />
                <ListItemText primary={`${i.invitee_name || i.invitee_discord_id} · ${i.role}`} />
              </ListItem>
            ))}
          </List>
        </>
      )}
    </CardContent></Card>
  );
}
