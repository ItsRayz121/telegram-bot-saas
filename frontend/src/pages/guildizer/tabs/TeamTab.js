import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Typography, CircularProgress, Alert, List, ListItem,
  ListItemText, Stack, IconButton, Button, Tooltip, Chip,
} from '@mui/material';
import { Delete, Add, ContentCopy } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

export default function TeamTab({ guildId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await guildizerApi.get(`/api/guilds/${guildId}/team`);
      setMembers(data.members); setInvites(data.invites); setError(null);
    } catch { setError('Failed to load the team.'); }
    setLoading(false);
  }, [guildId]);

  useEffect(() => { load(); }, [load]);

  async function createInvite() {
    setBusy(true);
    try { await guildizerApi.post(`/api/guilds/${guildId}/team/invites`); await load(); }
    catch { setError('Could not create an invite.'); }
    setBusy(false);
  }

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Card variant="outlined"><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={0.5}>
        <Typography variant="subtitle1" fontWeight={700}>Team access</Typography>
        <Button startIcon={<Add />} variant="contained" size="small" disabled={busy} onClick={createInvite}>
          New invite code
        </Button>
      </Stack>
      <Typography variant="caption" color="text.secondary" display="block" mb={2}>
        Give dashboard access to people who don't have Manage Server on Discord.
        Send them a code — they redeem it from the Discord page after logging in.
        Codes are one-use and expire after 7 days.
      </Typography>
      {error && <Alert severity="warning" sx={{ mb: 1 }} onClose={() => setError(null)}>{error}</Alert>}

      {invites.length > 0 && (
        <>
          <Typography variant="subtitle2" fontWeight={700}>Open invites</Typography>
          <List dense>
            {invites.map((i) => (
              <ListItem key={i.id} disableGutters
                secondaryAction={(
                  <Stack direction="row" spacing={0.5}>
                    <Tooltip title="Copy code">
                      <IconButton size="small" onClick={() => navigator.clipboard.writeText(i.code)}>
                        <ContentCopy fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <IconButton size="small" color="error"
                      onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/team/invites/${i.id}`).then(load)}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </Stack>
                )}>
                <ListItemText primary={<code>{i.code}</code>}
                  secondary={`expires ${new Date(i.expires_at).toLocaleString()}`} />
              </ListItem>
            ))}
          </List>
        </>
      )}

      <Typography variant="subtitle2" fontWeight={700} mt={1}>Members</Typography>
      {members.length === 0 && <Typography variant="body2" color="text.secondary">No team members yet.</Typography>}
      <List dense>
        {members.map((m) => (
          <ListItem key={m.user_id} disableGutters
            secondaryAction={(
              <IconButton size="small" color="error"
                onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/team/members/${m.user_id}`).then(load)}>
                <Delete fontSize="small" />
              </IconButton>
            )}>
            <Chip size="small" variant="outlined" label={m.role} sx={{ mr: 1 }} />
            <ListItemText primary={m.username || m.user_id}
              secondary={`since ${m.created_at ? new Date(m.created_at).toLocaleDateString() : ''}`} />
          </ListItem>
        ))}
      </List>
    </CardContent></Card>
  );
}
