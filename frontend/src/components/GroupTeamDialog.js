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
  manager: 'Can change settings, moderate, and run tools for this group.',
  viewer: 'Can look at everything but cannot change anything.',
};

const joinLink = (code) => `${window.location.origin}/group-team/join/${code}`;

export default function GroupTeamDialog({ group, open, onClose }) {
  const gid = group?.telegram_group_id;
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [max, setMax] = useState(10);
  const [role, setRole] = useState('manager');

  const load = useCallback(async () => {
    if (!gid) return;
    try {
      const { data } = await groupTeam.get(gid);
      setMembers(data.members); setInvites(data.invites); setMax(data.max_members); setError('');
    } catch (e) {
      setError(e?.response?.data?.error || 'Could not load team access.');
    }
    setLoading(false);
  }, [gid]);

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

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Team access — {group?.title}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Invite people to manage <strong>this group only</strong>. They won't see your other groups,
          billing, or API keys, and can't unlink the group. Links are one-use and expire in 7 days.
        </Typography>
        {error && <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
          <ToggleButtonGroup size="small" exclusive value={role} onChange={(_, v) => v && setRole(v)}>
            <ToggleButton value="manager" sx={{ textTransform: 'none' }}>Manager</ToggleButton>
            <ToggleButton value="viewer" sx={{ textTransform: 'none' }}>Viewer</ToggleButton>
          </ToggleButtonGroup>
          <Button variant="contained" size="small" startIcon={<PersonAdd />} disabled={busy}
            onClick={() => run(() => groupTeam.createInvite(gid, role), 'Invite link created')}>
            New invite link
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
                <Typography variant="subtitle2" fontWeight={700}>Open invites</Typography>
                <List dense>
                  {invites.map((i) => (
                    <ListItem key={i.id} disableGutters
                      secondaryAction={(
                        <Stack direction="row" spacing={0.5}>
                          <Tooltip title="Copy invite link">
                            <IconButton size="small" onClick={() => copy(joinLink(i.code))}><ContentCopy fontSize="small" /></IconButton>
                          </Tooltip>
                          <Tooltip title="Cancel invite">
                            <IconButton size="small" disabled={busy}
                              onClick={() => run(() => groupTeam.cancelInvite(gid, i.id))}><Delete fontSize="small" /></IconButton>
                          </Tooltip>
                        </Stack>
                      )}>
                      <ListItemText
                        primary={<Chip size="small" label={i.role} />}
                        secondary={`Expires ${new Date(i.expires_at).toLocaleDateString()}`} />
                    </ListItem>
                  ))}
                </List>
              </>
            )}

            <Typography variant="subtitle2" fontWeight={700} sx={{ mt: 1 }}>
              People with access ({members.length}/{max})
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
                          onChange={(e) => run(() => groupTeam.setRole(gid, m.user_id, e.target.value))}>
                          <MenuItem value="manager">Manager</MenuItem>
                          <MenuItem value="viewer">Viewer</MenuItem>
                        </Select>
                        <Tooltip title="Remove access">
                          <IconButton size="small" disabled={busy}
                            onClick={() => run(() => groupTeam.removeMember(gid, m.user_id), 'Access removed')}>
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
          </>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  );
}
