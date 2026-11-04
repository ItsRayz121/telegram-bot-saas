import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Typography, Switch, FormControlLabel, TextField,
  MenuItem, Button, Chip, CircularProgress, Alert, Snackbar, Stack, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material';
import { Add, Delete, Send } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';

const TEXT_TYPES = new Set([0, 5]);
const MAX_MENUS = 10;
const MAX_ENTRIES = 20;
const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'local time';
const STATUS = {
  draft: ['Draft', 'default'], scheduled: ['Scheduled', 'info'], publishing: ['Publishing…', 'warning'],
  published: ['Published', 'success'], unpublished: ['Unpublished', 'default'], failed: ['Failed', 'error'],
};
function StatusBadge({ menu }) {
  const [label, color] = STATUS[menu.status || 'draft'] || STATUS.draft;
  return (
    <Stack direction="row" spacing={0.75} alignItems="center">
      <Chip size="small" color={color} variant="outlined" label={label} />
      {menu.status === 'scheduled' && menu.post_at && <Typography variant="caption" color="text.secondary">{new Date(menu.post_at).toLocaleString()}</Typography>}
      {menu.status === 'failed' && <Typography variant="caption" color="error">{menu.post_error}</Typography>}
    </Stack>
  );
}

// Members › Self-roles: reaction-role / button-role menus. Saved via
// PUT /self-roles; "Post" queues the bot to publish the menu message.
const saveError = (e) => (e?.response?.data?.error === 'role_not_assignable'
  ? 'A menu entry points at a role with moderation or management permissions (or @everyone / an integration role). Pick a plain role.'
  : 'Save failed.');

export default function SelfRolesSubtab({ guildId, channels = [], roles = [] }) {
  const [menus, setMenus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState('');
  const [preview, setPreview] = useState(null);       // menu shown in the Preview dialog
  const [showArchived, setShowArchived] = useState(false);
  const [scheduleAt, setScheduleAt] = useState({});   // menu index -> datetime-local string

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const [safeIds, setSafeIds] = useState(null);   // roles with no moderation/management permissions
  const assignableRoles = roles.filter((r) => !r.managed && r.name !== '@everyone' && (!safeIds || safeIds.has(r.id)));

  const load = () => guildizerApi.get(`/api/guilds/${guildId}/self-roles`)
    .then(({ data }) => setMenus(data.menus || []))
    .catch(() => setError('Failed to load self-role menus.'))
    .finally(() => setLoading(false));

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/roles/overview`)
      .then(({ data }) => setSafeIds(new Set(data.roles.filter((r) => r.assignable).map((r) => r.id))))
      .catch(() => setSafeIds(null));
  }, [guildId]);

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
    } catch (e) { setError(saveError(e)); } finally { setSaving(false); }
  }

  async function post(menu, i) {
    setError(null);
    try {
      // Persist edits first so the bot posts what's on screen, then queue.
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/self-roles`, { menus });
      setMenus(data.menus || []);
      const when = scheduleAt[i];
      const body = when ? { post_at: new Date(when).toISOString() } : {};
      const { data: res } = await guildizerApi.post(`/api/guilds/${guildId}/self-roles/${menu.id}/post`, body);
      setNotice(res.post_status === 'scheduled'
        ? `Scheduled — the bot posts the menu at ${new Date(res.post_at).toLocaleString()}.`
        : 'Queued — the bot posts the menu within ~20 seconds.');
      setScheduleAt((s) => ({ ...s, [i]: '' }));
      load();
    } catch (e) {
      setError(e?.response?.data?.error === 'role_not_assignable' ? saveError(e) : (e?.response?.data?.message || 'Could not queue the post.'));
    }
  }

  async function unpost(menu) {
    setError(null);
    try {
      await guildizerApi.delete(`/api/guilds/${guildId}/self-roles/${menu.id}/post`);
      setNotice(menu.message_id ? 'Queued — the bot removes the posted menu shortly. Members keep their roles.' : 'Cancelled.');
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

      {menus.some((x) => x.archived) && (
        <Grid item xs={12}>
          <Button size="small" color="inherit" onClick={() => setShowArchived((v) => !v)}>
            {showArchived ? 'Hide archived menus' : `Show archived menus (${menus.filter((x) => x.archived).length})`}
          </Button>
        </Grid>
      )}

      {menus.map((m, i) => (m.archived && !showArchived ? null : (
        <Grid item xs={12} key={m.id ?? `new-${i}`}>
          <GuildizerCollapsibleCard
            id={`gz.members.selfrole_menu_${m.id ?? `new_${i}`}`}
            defaultOpen={!m.id}
            title={`Menu — ${m.title || 'untitled'}`}
            action={(
              <Stack direction="row" spacing={1} alignItems="center">
                <StatusBadge menu={m} />
                <IconButton aria-label="Delete" size="small" onClick={() => setMenus(menus.filter((_, j) => j !== i))}>
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
                    <IconButton aria-label="Delete" size="small" onClick={() => setMenu(i, { entries: m.entries.filter((_, j) => j !== k) })}>
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
                </Stack>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center" mt={1}>
                  <TextField type="datetime-local" size="small" label={`Schedule (${tz})`}
                    InputLabelProps={{ shrink: true }} value={scheduleAt[i] || ''}
                    onChange={(ev) => setScheduleAt((s2) => ({ ...s2, [i]: ev.target.value }))}
                    sx={{ minWidth: 210 }} disabled={m.status === 'publishing'} />
                  <Button size="small" variant="contained" startIcon={<Send />}
                    disabled={!m.channel_id || (m.entries || []).length === 0 || !m.id || m.status === 'publishing' || !!m.archived}
                    onClick={() => post(m, i)}>
                    {scheduleAt[i] ? 'Schedule' : m.status === 'published' ? 'Update published post' : m.status === 'unpublished' ? 'Republish' : 'Publish now'}
                  </Button>
                  {m.status === 'published' && (
                    <Button size="small" color="warning" variant="outlined" onClick={() => unpost(m)}>Unpublish</Button>
                  )}
                  {m.status === 'scheduled' && (
                    <Button size="small" color="inherit" variant="outlined" onClick={() => unpost(m)}>Cancel schedule</Button>
                  )}
                  {m.status === 'failed' && (
                    <Button size="small" color="inherit" variant="outlined" onClick={() => unpost(m)}>Clear error</Button>
                  )}
                  <Button size="small" color="inherit" onClick={() => setMenus([...menus, { ...m, id: null, title: `${m.title || 'Menu'} (copy)`, message_id: null, status: 'draft', needs_post: false, post_at: null, post_error: null }])}
                    disabled={menus.length >= MAX_MENUS}>Duplicate</Button>
                  <Button size="small" color="inherit" onClick={() => setPreview(m)}>Preview</Button>
                  <Button size="small" color="inherit"
                    disabled={!m.archived && ['published', 'publishing', 'scheduled'].includes(m.status)}
                    onClick={() => setMenu(i, { archived: !m.archived })}>{m.archived ? 'Unarchive' : 'Archive'}</Button>
                </Stack>
                {m.status === 'published' && (
                  <Typography variant="caption" color="text.secondary" display="block" mt={0.5}>
                    Edits are saved here first; <b>Update published post</b> then edits the live message in place. Unpublishing removes the message — members keep the roles they already have.
                  </Typography>
                )}
                {!m.id && (
                  <Typography variant="caption" color="text.secondary" display="block" mt={0.5}>
                    Save first to enable posting.
                  </Typography>
                )}
              </Grid>
            </Grid>
          </GuildizerCollapsibleCard>
        </Grid>
      )))}

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

      <Dialog open={!!preview} onClose={() => setPreview(null)} fullWidth maxWidth="xs">
        {preview && (
          <>
            <DialogTitle>Preview — nothing is posted</DialogTitle>
            <DialogContent>
              <Box sx={{ p: 1.5, borderRadius: 1, bgcolor: 'action.hover' }}>
                <Typography variant="body2" fontWeight={700}>{preview.title || 'Pick your roles'}</Typography>
                {preview.description && <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{preview.description}</Typography>}
                {(preview.style || 'buttons') === 'reactions' ? (
                  <Box sx={{ mt: 1 }}>
                    {(preview.entries || []).filter((e) => e.emoji).map((e, k) => (
                      <Typography key={k} variant="body2">{e.emoji} — {e.label || 'role'}</Typography>
                    ))}
                    <Typography variant="caption" color="text.secondary">React to get a role; remove your reaction to drop it.</Typography>
                  </Box>
                ) : (
                  <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                    {(preview.entries || []).map((e, k) => <Chip key={k} label={`${e.emoji || ''} ${e.label || 'Role'}`.trim()} />)}
                  </Stack>
                )}
              </Box>
              <Typography variant="caption" color="text.secondary" display="block" mt={1}>
                Goes to {preview.channel_id ? `#${(textChannels.find((c) => c.id === preview.channel_id) || {}).name || preview.channel_id}` : 'no channel yet'}
                {preview.max_one ? ' · members can hold only one of these roles' : ' · members can hold several'}.
              </Typography>
            </DialogContent>
            <DialogActions><Button onClick={() => setPreview(null)}>Close</Button></DialogActions>
          </>
        )}
      </Dialog>

      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
      <Snackbar open={!!notice} autoHideDuration={3500} onClose={() => setNotice('')} message={notice}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Grid>
  );
}
