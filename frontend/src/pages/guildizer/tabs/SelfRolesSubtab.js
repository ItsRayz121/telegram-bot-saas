import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Typography, Switch, FormControlLabel, TextField,
  MenuItem, Button, Chip, CircularProgress, Alert, Snackbar, Stack, IconButton,
} from '@mui/material';
import { Add, Delete, Send } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';

const TEXT_TYPES = new Set([0, 5]);
const MAX_MENUS = 10;
const MAX_ENTRIES = 20;

// Members › Self-roles: reaction-role / button-role menus. Saved via
// PUT /self-roles; "Post" queues the bot to publish the menu message.
export default function SelfRolesSubtab({ guildId, channels = [], roles = [] }) {
  const [menus, setMenus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState('');

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const assignableRoles = roles.filter((r) => !r.managed && r.name !== '@everyone');

  const load = () => guildizerApi.get(`/api/guilds/${guildId}/self-roles`)
    .then(({ data }) => setMenus(data.menus || []))
    .catch(() => setError('Failed to load self-role menus.'))
    .finally(() => setLoading(false));

  useEffect(() => {
    load();
    /* eslint-disable-next-line */
  }, [guildId]);

  const setMenu = (i, patch) => setMenus((ms) => ms.map((m, j) => (j === i ? { ...m, ...patch } : m)));
  const setEntry = (i, k, patch) => setMenu(i, {
    entries: menus[i].entries.map((e, j) => (j === k ? { ...e, ...patch } : e)),
  });

  async function save() {
    setSaving(true); setError(null);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/self-roles`, { menus });
      setMenus(data.menus || []);
      setSaved(true);
    } catch { setError('Save failed.'); } finally { setSaving(false); }
  }

  async function post(menu) {
    setError(null);
    try {
      // Persist edits first so the bot posts what's on screen, then queue.
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/self-roles`, { menus });
      setMenus(data.menus || []);
      await guildizerApi.post(`/api/guilds/${guildId}/self-roles/${menu.id}/post`);
      setNotice('Queued — the bot posts the menu within ~20 seconds.');
      load();
    } catch (e) {
      setError(e?.response?.data?.message || 'Could not queue the post.');
    }
  }

  async function unpost(menu) {
    setError(null);
    try {
      await guildizerApi.delete(`/api/guilds/${guildId}/self-roles/${menu.id}/post`);
      setNotice('Queued — the bot removes the posted menu shortly.');
      load();
    } catch { setError('Could not queue the removal.'); }
  }

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
  if (!menus) return <Alert severity="warning">{error || 'No data.'}</Alert>;

  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Typography variant="body2" color="text.secondary">
          Members pick their own roles from a posted menu — buttons or reactions. Guildizer's
          role must sit above any role it assigns; roles with moderation permissions are never
          self-assignable.
        </Typography>
      </Grid>

      {menus.map((m, i) => (
        <Grid item xs={12} key={m.id ?? `new-${i}`}>
          <GuildizerCollapsibleCard
            id={`gz.members.selfrole_menu_${m.id ?? `new_${i}`}`}
            defaultOpen={!m.id}
            title={`Menu — ${m.title || 'untitled'}`}
            action={(
              <Stack direction="row" spacing={1} alignItems="center">
                {m.message_id && <Chip size="small" color="success" variant="outlined" label="Posted" />}
                {m.needs_post && <Chip size="small" color="info" variant="outlined" label="Post queued" />}
                {m.needs_delete && <Chip size="small" color="warning" variant="outlined" label="Removal queued" />}
                {m.post_error && <Chip size="small" color="error" variant="outlined" label={`Post failed: ${m.post_error}`} />}
                <IconButton size="small" onClick={() => setMenus(menus.filter((_, j) => j !== i))}>
                  <Delete fontSize="small" />
                </IconButton>
              </Stack>
            )}
          >
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <TextField size="small" margin="dense" fullWidth label="Title"
                  value={m.title} inputProps={{ maxLength: 100 }}
                  onChange={(e) => setMenu(i, { title: e.target.value })} />
                <TextField size="small" margin="dense" fullWidth multiline minRows={2} label="Description (optional)"
                  value={m.description} inputProps={{ maxLength: 1000 }}
                  onChange={(e) => setMenu(i, { description: e.target.value })} />
                <TextField select size="small" margin="dense" fullWidth label="Channel"
                  value={m.channel_id || ''} onChange={(e) => setMenu(i, { channel_id: e.target.value || null })}>
                  <MenuItem value="">— pick a channel —</MenuItem>
                  {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
                </TextField>
                <TextField select size="small" margin="dense" fullWidth label="Style"
                  value={m.style || 'buttons'} onChange={(e) => setMenu(i, { style: e.target.value })}>
                  <MenuItem value="buttons">Buttons (recommended)</MenuItem>
                  <MenuItem value="reactions">Reactions</MenuItem>
                </TextField>
                <FormControlLabel control={<Switch checked={!!m.max_one} onChange={(e) => setMenu(i, { max_one: e.target.checked })} />}
                  label="Max one role from this menu (picking another swaps it)" />
              </Grid>

              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2" fontWeight={700} mb={0.5}>Roles</Typography>
                {(m.entries || []).map((e, k) => (
                  <Stack key={k} direction="row" spacing={1} alignItems="center" mb={1}>
                    <TextField size="small" label="Emoji" value={e.emoji || ''} sx={{ width: 90 }}
                      inputProps={{ maxLength: 64 }} placeholder="🎮"
                      onChange={(ev) => setEntry(i, k, { emoji: ev.target.value })} />
                    <TextField size="small" label="Label" value={e.label || ''} sx={{ flex: 1 }}
                      inputProps={{ maxLength: 80 }}
                      onChange={(ev) => setEntry(i, k, { label: ev.target.value })} />
                    <TextField select size="small" label="Role" value={e.role_id || ''} sx={{ flex: 1 }}
                      onChange={(ev) => setEntry(i, k, { role_id: ev.target.value })}>
                      {assignableRoles.map((r) => <MenuItem key={r.id} value={r.id}>{r.name}</MenuItem>)}
                      {!assignableRoles.some((r) => r.id === e.role_id) && e.role_id && (
                        <MenuItem value={e.role_id}>{e.role_id}</MenuItem>
                      )}
                    </TextField>
                    <IconButton size="small" onClick={() => setMenu(i, { entries: m.entries.filter((_, j) => j !== k) })}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </Stack>
                ))}
                {(m.style || 'buttons') === 'reactions' && (
                  <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                    Reaction menus need an emoji on every row.
                  </Typography>
                )}
                <Stack direction="row" spacing={1}>
                  <Button size="small" startIcon={<Add />}
                    disabled={(m.entries || []).length >= MAX_ENTRIES || assignableRoles.length === 0}
                    onClick={() => setMenu(i, { entries: [...(m.entries || []), { emoji: '', label: '', role_id: assignableRoles[0]?.id }] })}>
                    Add role
                  </Button>
                  <Button size="small" variant="outlined" startIcon={<Send />}
                    disabled={!m.channel_id || (m.entries || []).length === 0 || !m.id}
                    onClick={() => post(m)}>
                    {m.message_id ? 'Re-post menu' : 'Post menu'}
                  </Button>
                  {m.message_id && (
                    <Button size="small" color="inherit" onClick={() => unpost(m)}>Remove posted message</Button>
                  )}
                </Stack>
                {!m.id && (
                  <Typography variant="caption" color="text.secondary" display="block" mt={0.5}>
                    Save first to enable posting.
                  </Typography>
                )}
              </Grid>
            </Grid>
          </GuildizerCollapsibleCard>
        </Grid>
      ))}

      <Grid item xs={12}>
        <Button startIcon={<Add />} disabled={menus.length >= MAX_MENUS}
          onClick={() => setMenus([...menus, {
            id: null, title: '', description: '', channel_id: null,
            style: 'buttons', max_one: false, entries: [],
          }])}>
          Add menu
        </Button>
      </Grid>

      <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, alignItems: 'center' }}>
        {error && <Alert severity="error" sx={{ py: 0 }}>{error}</Alert>}
        <Button variant="contained" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</Button>
      </Grid>

      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
      <Snackbar open={!!notice} autoHideDuration={3500} onClose={() => setNotice('')} message={notice}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Grid>
  );
}
