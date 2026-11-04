import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Typography, Button, Chip, CircularProgress, Alert, Stack, IconButton, Avatar, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, Autocomplete,
} from '@mui/material';
import { Add, Close, SmartToy } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const STATUS = {
  installed: ['In server', 'success'],
  not_in_server: ['Not in server', 'default'],
  unresolved: ['Unresolved ID', 'warning'],
  not_a_bot: ['Not a bot', 'error'],
};
const ADD_ERR = {
  bad_id: "That isn't a valid Discord ID (15–21 digits).",
  not_a_bot: 'That ID belongs to a person, not a bot.',
  unknown_user: "Discord doesn't know that ID.",
  limit_reached: 'The list is full (50 bots).',
};

// Trusted Bots & Apps — compact rows. Add/remove persist immediately (one bot at a
// time) and report the new list up so the page's Save bar never overwrites it.
export default function TrustedBots({ guildId, onListChange }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [picked, setPicked] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dlgErr, setDlgErr] = useState(null);

  const load = useCallback(() => guildizerApi.get(`/api/guilds/${guildId}/trusted-bots`)
    .then(({ data: d }) => { setData(d); setErr(null); })
    .catch(() => setErr("Couldn't load trusted bots from Discord.")), [guildId]);
  useEffect(() => { load(); }, [load]);

  async function add(id) {
    setBusy(true); setDlgErr(null);
    try {
      const { data: d } = await guildizerApi.post(`/api/guilds/${guildId}/trusted-bots`, { id });
      onListChange?.(d.trusted_bot_ids);
      setOpen(false); setInput(''); setPicked(null);
      load();
    } catch (e) {
      setDlgErr(ADD_ERR[e?.response?.data?.error] || "Couldn't add it. Try again.");
    } finally { setBusy(false); }
  }
  async function remove(id) {
    setBusy(true);
    try {
      const { data: d } = await guildizerApi.delete(`/api/guilds/${guildId}/trusted-bots/${id}`);
      onListChange?.(d.trusted_bot_ids);
      await load();
    } catch { setErr("Couldn't remove it. Try again."); } finally { setBusy(false); }
  }

  const options = (data?.installed || []).filter((b) => !b.trusted);
  const typed = (picked?.id || input || '').trim();

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={0.5}>
        <Typography variant="subtitle2" fontWeight={600}>Trusted bots &amp; apps</Typography>
        <Button size="small" variant="outlined" startIcon={<Add />} onClick={() => { setOpen(true); setDlgErr(null); }}>
          Add Trusted Bot
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" mb={1}>
        Trusted bots may join without being kicked or flagged by <b>Bot Protection</b> above.
        This does <b>not</b> exempt them from anti-nuke, spam, raid or content rules.
      </Typography>
      {err && <Alert severity="warning" sx={{ mb: 1 }}>{err}</Alert>}
      {!data && !err && <CircularProgress size={20} />}
      {data && data.trusted.length === 0 && (
        <Typography variant="body2" color="text.secondary">No trusted bots yet.</Typography>
      )}
      <Stack spacing={0.5}>
        {data?.trusted.map((b) => {
          const [label, color] = STATUS[b.status] || STATUS.unresolved;
          return (
            <Stack key={b.id} direction="row" alignItems="center" spacing={1.25}
              sx={{ px: 1, py: 0.5, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
              <Avatar src={b.avatar_url || undefined} sx={{ width: 28, height: 28 }} alt=""><SmartToy fontSize="small" /></Avatar>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" noWrap>{b.name}</Typography>
                <Typography variant="caption" color="text.secondary">{b.id}</Typography>
              </Box>
              <Chip size="small" variant="outlined" color={color} label={label} />
              <Tooltip title="Remove from trusted"><span>
                <IconButton size="small" disabled={busy} onClick={() => remove(b.id)}
                  aria-label={`Remove ${b.name} from trusted bots`}><Close fontSize="small" /></IconButton>
              </span></Tooltip>
            </Stack>
          );
        })}
      </Stack>
      {data && !data.members_ok && (
        <Typography variant="caption" color="text.secondary" display="block" mt={1}>
          Couldn&apos;t list the bots in this server (is the Server Members intent on?). You can still add by ID.
        </Typography>
      )}

      <Dialog open={open} onClose={() => !busy && setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Add trusted bot</DialogTitle>
        <DialogContent>
          <Autocomplete freeSolo size="small" sx={{ mt: 1 }} options={options}
            value={picked} inputValue={input}
            onInputChange={(_, v) => { setInput(v); if (picked && v !== picked.name) setPicked(null); }}
            onChange={(_, v) => setPicked(v && typeof v === 'object' ? v : null)}
            getOptionLabel={(o) => (typeof o === 'string' ? o : o.name)}
            filterOptions={(opts, { inputValue }) => {
              const q = inputValue.trim().toLowerCase();
              return q ? opts.filter((o) => o.name.toLowerCase().includes(q) || (o.username || '').toLowerCase().includes(q) || o.id.includes(q)) : opts;
            }}
            renderOption={(p, o) => (
              <li {...p} key={o.id}>
                <Avatar src={o.avatar_url} sx={{ width: 22, height: 22, mr: 1 }} alt="" />
                {o.name}<Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>{o.id}</Typography>
              </li>
            )}
            renderInput={(p) => <TextField {...p} label="Search by name or paste an ID"
              helperText="Bots already in this server are listed. Any valid bot ID also works." />} />
          {dlgErr && <Alert severity="error" sx={{ mt: 1.5 }}>{dlgErr}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
          <Button variant="contained" disabled={busy || !/^\d{15,21}$/.test(typed)} onClick={() => add(typed)}>
            {busy ? 'Adding…' : 'Trust bot'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
