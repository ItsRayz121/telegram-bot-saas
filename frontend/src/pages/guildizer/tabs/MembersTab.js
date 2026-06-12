import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Typography, TextField, MenuItem, CircularProgress,
  Alert, List, ListItem, ListItemText, Stack, Chip, IconButton, Collapse, Button,
} from '@mui/material';
import { ExpandMore, ExpandLess } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const SORTS = [
  { value: 'xp', label: 'XP' },
  { value: 'messages', label: 'Messages' },
  { value: 'last_seen', label: 'Last seen' },
];

export default function MembersTab({ guildId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [members, setMembers] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('xp');

  const load = useCallback(async (s = search, srt = sort) => {
    try {
      const { data } = await guildizerApi.get(
        `/api/guilds/${guildId}/members?search=${encodeURIComponent(s)}&sort=${srt}&limit=100`,
      );
      setMembers(data.members); setTotal(data.total); setError(null);
    } catch { setError('Failed to load members.'); }
    setLoading(false);
  }, [guildId, search, sort]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId, sort]);

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Card variant="outlined"><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
        <Typography variant="h6" fontWeight={600}>Members ({total} tracked)</Typography>
        <Stack direction="row" spacing={1}>
          <TextField size="small" label="Search name or ID" value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load()} />
          <TextField select size="small" label="Sort" value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORTS.map((s) => <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>)}
          </TextField>
        </Stack>
      </Stack>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Members appear here once they chat (activity is tracked by the bot). Wallets come from /wallet.
      </Typography>
      {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}</Alert>}
      {members.length === 0 && <Typography variant="body2" color="text.secondary">No tracked members yet.</Typography>}
      <List dense>
        {members.map((m) => <MemberRow key={m.user_id} guildId={guildId} member={m} onSaved={load} />)}
      </List>
    </CardContent></Card>
  );
}

function MemberRow({ guildId, member, onSaved }) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState(member.admin_notes || '');
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await guildizerApi.put(`/api/guilds/${guildId}/members/${member.user_id}`, { admin_notes: notes });
      await onSaved();
    } catch { /* parent reload surfaces issues */ }
    setBusy(false);
  }

  return (
    <>
      <ListItem disableGutters divider
        secondaryAction={(
          <IconButton size="small" onClick={() => setOpen((v) => !v)}>
            {open ? <ExpandLess /> : <ExpandMore />}
          </IconButton>
        )}>
        <ListItemText
          primary={(
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="body2" fontWeight={700}>{member.username || member.user_id}</Typography>
              <Chip size="small" variant="outlined" label={`lvl ${member.level}`} />
              {member.wallet && <Chip size="small" variant="outlined" color="info" label="wallet" />}
              {member.admin_notes && <Chip size="small" variant="outlined" color="warning" label="note" />}
            </Stack>
          )}
          secondary={`${member.xp} XP · ${member.messages} msgs · last seen ${member.last_seen ? new Date(member.last_seen).toLocaleString() : 'never'}`}
        />
      </ListItem>
      <Collapse in={open}>
        <Box sx={{ pl: 2, pb: 1.5 }}>
          {member.wallet && (
            <Typography variant="caption" display="block" mb={0.5}>
              Wallet: <code>{member.wallet}</code>
            </Typography>
          )}
          <Stack direction="row" spacing={1} alignItems="flex-start">
            <TextField fullWidth multiline minRows={1} size="small" label="Admin notes"
              value={notes} inputProps={{ maxLength: 2000 }} onChange={(e) => setNotes(e.target.value)} />
            <Button size="small" variant="outlined" disabled={busy} onClick={save}>Save</Button>
          </Stack>
        </Box>
      </Collapse>
    </>
  );
}
