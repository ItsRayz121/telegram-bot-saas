import React, { useEffect, useState, useMemo } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Switch, FormControlLabel,
  TextField, MenuItem, Button, Chip, CircularProgress, Alert, Snackbar,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';
import { useSaveBar } from './saveBar';

const TEXT_TYPES = new Set([0, 5]);

export default function SettingsTab({ guildId, channels = [], roles = [] }) {
  const [cfg, setCfg] = useState(null);
  const [orig, setOrig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const assignableRoles = roles.filter((r) => r.name !== '@everyone' && !r.managed);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/settings`)
      .then(({ data }) => { setCfg(data); setOrig(JSON.stringify(data)); })
      .catch(() => setError('Failed to load settings.'))
      .finally(() => setLoading(false));
  }, [guildId]);

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));
  const setW2 = (patch) => setCfg((c) => ({ ...c, welcome2: { ...c.welcome2, ...patch } }));
  const toggleRole = (id) => {
    const has = cfg.autorole_ids.includes(id);
    set({ autorole_ids: has ? cfg.autorole_ids.filter((r) => r !== id) : [...cfg.autorole_ids, id] });
  };

  async function save() {
    setSaving(true); setError(null);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/settings`, cfg);
      setCfg(data); setOrig(JSON.stringify(data)); setSaved(true);
    } catch { setError('Save failed.'); }
    finally { setSaving(false); }
  }

  const dirty = useMemo(() => cfg != null && orig != null && JSON.stringify(cfg) !== orig, [cfg, orig]);
  const sb = useSaveBar({ save, dirty, saving });

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
  if (!cfg) return <Alert severity="warning">{error || 'No settings.'}</Alert>;

  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Welcome message</Typography>
          <FormControlLabel
            control={<Switch checked={cfg.welcome_enabled} onChange={(e) => set({ welcome_enabled: e.target.checked })} />}
            label="Send a message when a member joins"
          />
          <TextField select fullWidth size="small" margin="normal" label="Channel"
            value={cfg.welcome_channel_id || ''} onChange={(e) => set({ welcome_channel_id: e.target.value || null })}>
            <MenuItem value="">— none —</MenuItem>
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
          <TextField fullWidth multiline minRows={2} size="small" margin="normal" label="Message"
            value={cfg.welcome_message} inputProps={{ maxLength: 2000 }}
            onChange={(e) => set({ welcome_message: e.target.value })}
            helperText="Placeholders: {user} {server} {member_count}" />
          <FormControlLabel
            control={<Switch checked={!!cfg.welcome2?.use_embed} onChange={(e) => setW2({ use_embed: e.target.checked })} />}
            label="Send as a rich embed (avatar + image)"
          />
          <FormControlLabel
            control={<Switch checked={!!cfg.welcome2?.ai_welcome} onChange={(e) => setW2({ ai_welcome: e.target.checked })} />}
            label="Add an AI-personalized welcome line (needs AI key)"
          />
          <TextField fullWidth multiline minRows={2} size="small" margin="dense" label="Rules text (optional)"
            value={cfg.welcome2?.rules_text || ''} inputProps={{ maxLength: 1024 }}
            onChange={(e) => setW2({ rules_text: e.target.value })}
            helperText="Shown under the welcome message." />
          <TextField fullWidth size="small" margin="dense" label="Image URL (embed only)"
            value={cfg.welcome2?.image_url || ''}
            onChange={(e) => setW2({ image_url: e.target.value })} />
          <TextField type="number" fullWidth size="small" margin="dense"
            label="Auto-delete after seconds (0 = keep)"
            value={cfg.welcome2?.delete_after_seconds ?? 0} inputProps={{ min: 0, max: 3600 }}
            onChange={(e) => setW2({ delete_after_seconds: Number(e.target.value) })} />
        </CardContent></Card>
      </Grid>

      <Grid item xs={12}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>DM new members</Typography>
          <FormControlLabel
            control={<Switch checked={!!cfg.welcome2?.dm_enabled} onChange={(e) => setW2({ dm_enabled: e.target.checked })} />}
            label="Send a private DM when a member joins"
          />
          <TextField fullWidth multiline minRows={2} size="small" margin="dense" label="DM message"
            value={cfg.welcome2?.dm_message || ''} inputProps={{ maxLength: 2000 }}
            onChange={(e) => setW2({ dm_message: e.target.value })}
            helperText="Placeholders: {user} {server} {member_count}. Members with DMs closed are skipped." />
        </CardContent></Card>
      </Grid>

      <Grid item xs={12}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Leave message</Typography>
          <FormControlLabel
            control={<Switch checked={cfg.leave_enabled} onChange={(e) => set({ leave_enabled: e.target.checked })} />}
            label="Send a message when a member leaves"
          />
          <TextField select fullWidth size="small" margin="normal" label="Channel"
            value={cfg.leave_channel_id || ''} onChange={(e) => set({ leave_channel_id: e.target.value || null })}>
            <MenuItem value="">— none —</MenuItem>
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
          <TextField fullWidth multiline minRows={2} size="small" margin="normal" label="Message"
            value={cfg.leave_message} inputProps={{ maxLength: 2000 }}
            onChange={(e) => set({ leave_message: e.target.value })} />
        </CardContent></Card>
      </Grid>

      <Grid item xs={12}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Auto-roles</Typography>
          <FormControlLabel
            control={<Switch checked={cfg.autorole_enabled} onChange={(e) => set({ autorole_enabled: e.target.checked })} />}
            label="Assign roles automatically on join"
          />
          {assignableRoles.length === 0 && <Typography variant="body2" color="text.secondary">No assignable roles.</Typography>}
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1 }}>
            {assignableRoles.map((r) => (
              <Chip key={r.id} label={r.name} clickable
                color={cfg.autorole_ids.includes(r.id) ? 'primary' : 'default'}
                variant={cfg.autorole_ids.includes(r.id) ? 'filled' : 'outlined'}
                onClick={() => toggleRole(r.id)}
                sx={{ '& .MuiChip-label': { display: 'flex', alignItems: 'center' } }} />
            ))}
          </Box>
          <Typography variant="caption" color="text.disabled" display="block" mt={1}>
            Guildizer's role must sit above any role it assigns.
          </Typography>
        </CardContent></Card>
      </Grid>

      {!sb && (
        <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, alignItems: 'center' }}>
          {error && <Alert severity="error" sx={{ py: 0 }}>{error}</Alert>}
          <Button variant="contained" onClick={save} disabled={saving || !dirty}>
            {saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
          </Button>
        </Grid>
      )}
      {sb && error && <Grid item xs={12}><Alert severity="error">{error}</Alert></Grid>}

      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)}
        message="Saved" anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Grid>
  );
}
