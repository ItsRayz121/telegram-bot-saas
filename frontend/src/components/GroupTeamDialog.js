import React, { useCallback, useEffect, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Box, Typography, Stack,
  List, ListItem, ListItemText, IconButton, Tooltip, Select, MenuItem, CircularProgress,
  Alert, Chip, ToggleButton, ToggleButtonGroup,
} from '@mui/material';
import { Delete, ContentCopy, PersonAdd } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { groupTeam } from '../services/api';

const ROLE_HELP = {
  manager: 'Full control: settings, moderation, automations, forwarding, tasks.',
  viewer: 'Can look at everything but cannot change anything.',
};

// Works for one group ({ group }) or for every group a bot manages ({ bot: { key, label } }).
export default function GroupTeamDialog({ group, bot, open, onClose }) {
  const isBot = !!bot;
  const id = isBot ? bot.key : group?.telegram_group_id;
  const api = isBot
    ? {
      get: groupTeam.botGet, createInvite: groupTeam.botCreateInvite, cancelInvite: groupTeam.botCancelInvite,
      setRole: groupTeam.botSetRole, removeMember: groupTeam.botRemoveMember,
    }
    : {
      get: groupTeam.get, createInvite: groupTeam.createInvite, cancelInvite: groupTeam.cancelInvite,
      setRole: groupTeam.setRole, removeMember: groupTeam.removeMember,
    };

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [members, setMembers] = useState([]);
  const [inherited, setInherited] = useState([]);
  const [invites, setInvites] = useState([]);
  const [max, setMax] = useState(10);
  const [groupCount, setGroupCount] = useState(null);
  const [role, setRole] = useState('manager');

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const { data } = await api.get(id);
      setMembers(data.members); setInvites(data.invites); setMax(data.max_members);
      setInherited(data.inherited || []); setGroupCount(data.group_count ?? null); setError('');
    } catch (e) {
      setError(e?.response?.data?.error || 'Could not load team access.');
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isBot]);

  useEffect(() => { if (open) { setLoading(true); load(); } }, [open, load]);

  const run = async (fn, okMsg) => {
    setBusy(true);
    try { await fn(); if (okMsg) toast.success(okMsg); await load(); }
    catch (e) { setError(e?.response?.data?.error || 'Something went wrong.'); }
    setBusy(false);
  };

  const copy = (text) => {
    try { navigator.clipboard.writeText(text); toast.success('Copied'); } catch { /* ignore */ }
  };

  const title = isBot ? `Share all groups of ${bot.label}` : `Team access — ${group?.title}`;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {isBot ? (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Gives access to <strong>every group this bot manages</strong>
            {groupCount !== null ? ` (${groupCount} now)` : ''}, including groups you link to it later.
            Groups managed by your other bots stay private. You can still set a different role for one
            group from that group's own Team button. Send the access code; they paste it under
            "Join with access code" on My Groups. Each code works once and expires in 7 days.
          </Typography>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Give people access to <strong>this group only</strong>: its settings, moderation, analytics,
            automations, forwarding, tasks and notes. They won't see your other groups, billing, or API
            keys, and can't unlink the group. Send them the access code; they paste it under
            "Join with access code" on My Groups. Each code works once and expires in 7 days.
          </Typography>
        )}
        {error && <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
          <ToggleButtonGroup size="small" exclusive value={role} onChange={(_, v) => v && setRole(v)}>
            <ToggleButton value="manager" sx={{ textTransform: 'none' }}>Manager</ToggleButton>
            <ToggleButton value="viewer" sx={{ textTransform: 'none' }}>Viewer</ToggleButton>
          </ToggleButtonGroup>
          <Button variant="contained" size="small" startIcon={<PersonAdd />} disabled={busy}
            onClick={() => run(() => api.createInvite(id, role), 'Access code created')}>
            New access code
          </Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
          {ROLE_HELP[role]}
        </Typography>

        {loading ? (
          <Box sx={{ display: 'grid', placeItems: 'center', py: 3 }}><CircularProgress size={24} /></Box>
        ) : (
          <>
            {invites.length > 0 && (
              <>
                <Typography variant="subtitle2" fontWeight={700}>Open access codes</Typography>
                <List dense>
                  {invites.map((i) => (
                    <ListItem key={i.id} disableGutters sx={{ pr: 10 }}
                      secondaryAction={(
                        <Stack direction="row" spacing={0.5}>
                          <Tooltip title="Copy access code">
                            <IconButton size="small" onClick={() => copy(i.code)}><ContentCopy fontSize="small" /></IconButton>
                          </Tooltip>
                          <Tooltip title="Cancel code">
                            <IconButton size="small" disabled={busy}
                              onClick={() => run(() => api.cancelInvite(id, i.id))}><Delete fontSize="small" /></IconButton>
                          </Tooltip>
                        </Stack>
                      )}>
                      <ListItemText
                        primary={(
                          <Stack direction="row" spacing={1} alignItems="center">
                            <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.85rem', wordBreak: 'break-all' }}>{i.code}</Typography>
                            <Chip size="small" label={i.role} />
                          </Stack>
                        )}
                        secondary={`Expires ${new Date(i.expires_at).toLocaleDateString()}`} />
                    </ListItem>
                  ))}
                </List>
              </>
            )}

            <Typography variant="subtitle2" fontWeight={700} sx={{ mt: 1 }}>
              {isBot ? 'People with access to all of this bot' : 'People with access to this group'} ({members.length}/{max})
            </Typography>
            {members.length === 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>No one yet.</Typography>
            ) : (
              <List dense>
                {members.map((m) => (
                  <ListItem key={m.user_id} disableGutters
                    secondaryAction={(
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <Select size="small" value={m.role} disabled={busy}
                          onChange={(e) => run(() => api.setRole(id, m.user_id, e.target.value))}>
                          <MenuItem value="manager">Manager</MenuItem>
                          <MenuItem value="viewer">Viewer</MenuItem>
                        </Select>
                        <Tooltip title="Remove access">
                          <IconButton size="small" disabled={busy}
                            onClick={() => run(() => api.removeMember(id, m.user_id), 'Access removed')}>
                            <Delete fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    )}>
                    <ListItemText primary={m.full_name || m.email} secondary={m.full_name ? m.email : null} />
                  </ListItem>
                ))}
              </List>
            )}

            {!isBot && inherited.length > 0 && (
              <>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mt: 1 }}>
                  Also has access through the whole bot
                </Typography>
                <List dense>
                  {inherited.map((m) => (
                    <ListItem key={`${m.bot_key}-${m.user_id}`} disableGutters>
                      <ListItemText
                        primary={m.full_name || m.email}
                        secondary={`${m.role} · via ${m.bot_key === '__official__' ? 'the official bot' : '@' + m.bot_key} (change it in "Share a whole bot")`} />
                    </ListItem>
                  ))}
                </List>
              </>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  );
}
