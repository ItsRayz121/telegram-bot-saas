import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, TextField, Button, List, ListItem,
  ListItemText, IconButton, Switch, FormControlLabel, Alert, InputAdornment, Stack,
} from '@mui/material';
import { Edit, Delete } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const BLANK = { name: '', description: 'Custom command', response: '', enabled: true };

export default function CommandsTab({ guildId }) {
  const [commands, setCommands] = useState([]);
  const [draft, setDraft] = useState(BLANK);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    try { const { data } = await guildizerApi.get(`/api/guilds/${guildId}/commands`); setCommands(data.commands); }
    catch { setError('Failed to load commands.'); }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  const cancel = () => { setEditingId(null); setDraft(BLANK); setError(null); };
  const startEdit = (c) => { setEditingId(c.id); setDraft({ name: c.name, description: c.description, response: c.response, enabled: c.enabled }); setError(null); };

  async function save() {
    setSaving(true); setError(null);
    try {
      if (editingId) await guildizerApi.put(`/api/guilds/${guildId}/commands/${editingId}`, draft);
      else await guildizerApi.post(`/api/guilds/${guildId}/commands`, draft);
      cancel(); await load();
    } catch (e) {
      setError(e?.response?.data?.error || 'Save failed — check the name.');
    } finally { setSaving(false); }
  }

  async function remove(id) {
    if (!window.confirm('Delete this command?')) return;
    await guildizerApi.delete(`/api/guilds/${guildId}/commands/${id}`);
    if (editingId === id) cancel();
    await load();
  }

  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700}>Slash commands</Typography>
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Members run these as <code>/name</code>. Changes go live within ~30s.
          </Typography>
          {commands.length === 0 && <Typography variant="body2" color="text.secondary">No commands yet.</Typography>}
          <List dense>
            {commands.map((c) => (
              <ListItem key={c.id} disableGutters
                secondaryAction={
                  <Stack direction="row" spacing={0.5}>
                    <IconButton size="small" onClick={() => startEdit(c)}><Edit fontSize="small" /></IconButton>
                    <IconButton size="small" color="error" onClick={() => remove(c.id)}><Delete fontSize="small" /></IconButton>
                  </Stack>
                }>
                <ListItemText primary={`/${c.name}`} secondary={c.enabled ? null : 'Disabled'} />
              </ListItem>
            ))}
          </List>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>{editingId ? 'Edit command' : 'New command'}</Typography>
          {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
          <TextField fullWidth size="small" margin="dense" label="Name"
            value={draft.name} inputProps={{ maxLength: 32 }}
            onChange={(e) => setDraft({ ...draft, name: e.target.value.toLowerCase() })}
            InputProps={{ startAdornment: <InputAdornment position="start">/</InputAdornment> }}
            helperText="Lowercase letters, numbers, - or _ (max 32)" />
          <TextField fullWidth size="small" margin="dense" label="Description"
            value={draft.description} inputProps={{ maxLength: 100 }}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
          <TextField fullWidth size="small" margin="dense" label="Response" multiline minRows={3}
            value={draft.response} inputProps={{ maxLength: 2000 }}
            placeholder="The text Guildizer replies with…"
            onChange={(e) => setDraft({ ...draft, response: e.target.value })} />
          <FormControlLabel
            control={<Switch checked={draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />}
            label="Enabled" />
          <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
            <Button variant="contained" onClick={save} disabled={saving || !draft.name.trim()}>
              {saving ? 'Saving…' : editingId ? 'Update' : 'Create'}
            </Button>
            {editingId && <Button onClick={cancel} color="inherit">Cancel</Button>}
          </Box>
        </CardContent></Card>
      </Grid>
    </Grid>
  );
}
