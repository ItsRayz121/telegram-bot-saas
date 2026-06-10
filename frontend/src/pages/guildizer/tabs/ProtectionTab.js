import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Switch, FormControlLabel, TextField,
  MenuItem, Button, Chip, CircularProgress, Alert, Snackbar, List, ListItem, ListItemText, Stack,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';

const TEXT_TYPES = new Set([0, 5]);
const CF_ACTIONS = ['delete', 'warn', 'timeout', 'kick', 'ban'];
const RG_ACTIONS = ['timeout', 'kick'];
const CAT_LABEL = {
  nsfw: 'NSFW', csam: 'CSAM', invite: 'Invite', link: 'Link', custom: 'Blocked word',
  spam: 'Spam', raid: 'Raid', lockdown_join: 'Lockdown join', join_gate: 'Join gate', manual_lockdown: 'Lockdown',
};
const CAT_COLOR = { nsfw: 'error', csam: 'error', raid: 'warning', manual_lockdown: 'warning', lockdown_join: 'warning', invite: 'info', link: 'info' };

export default function ProtectionTab({ guildId, channels = [] }) {
  const [cfg, setCfg] = useState(null);
  const [wordsText, setWordsText] = useState('');
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));

  const loadEvents = () => guildizerApi.get(`/api/guilds/${guildId}/protection/events?limit=50`)
    .then(({ data }) => setEvents(data.events)).catch(() => {});

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/moderation`)
      .then(({ data }) => { setCfg(data); setWordsText((data.cf_custom_words || []).join(', ')); })
      .catch(() => setError('Failed to load protection settings.'))
      .finally(() => setLoading(false));
    loadEvents(); /* eslint-disable-next-line */
  }, [guildId]);

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));

  async function save() {
    setSaving(true); setError(null);
    try {
      const payload = { ...cfg, cf_custom_words: wordsText.split(',').map((w) => w.trim()).filter(Boolean) };
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/moderation`, payload);
      setCfg(data); setWordsText((data.cf_custom_words || []).join(', ')); setSaved(true);
    } catch { setError('Save failed.'); } finally { setSaving(false); }
  }

  async function lockdown(minutes) {
    const { data } = await guildizerApi.post(`/api/guilds/${guildId}/moderation/lockdown`, { minutes });
    setCfg(data); loadEvents();
  }

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
  if (!cfg) return <Alert severity="warning">{error || 'No settings.'}</Alert>;

  const num = (label, key, min, max) => (
    <TextField type="number" size="small" margin="dense" fullWidth label={label}
      value={cfg[key]} inputProps={{ min, max }} onChange={(e) => set({ [key]: Number(e.target.value) })} />
  );

  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Content filter</Typography>
          <FormControlLabel control={<Switch checked={cfg.cf_enabled} onChange={(e) => set({ cf_enabled: e.target.checked })} />} label="Scan messages and act on violations" />
          <TextField select size="small" margin="dense" fullWidth label="Action on violation"
            value={cfg.cf_action} onChange={(e) => set({ cf_action: e.target.value })}
            helperText="CSAM always bans regardless of this setting.">
            {CF_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
          </TextField>
          <FormControlLabel control={<Switch checked={cfg.cf_nsfw} onChange={(e) => set({ cf_nsfw: e.target.checked })} />} label="Block NSFW / explicit content" />
          <FormControlLabel control={<Switch checked={cfg.cf_invites} onChange={(e) => set({ cf_invites: e.target.checked })} />} label="Remove foreign Discord invites" />
          <FormControlLabel control={<Switch checked={cfg.cf_links} onChange={(e) => set({ cf_links: e.target.checked })} />} label="Remove shortened / suspicious links" />
          <TextField size="small" margin="dense" fullWidth label="Custom blocked words" placeholder="word1, word2, …"
            value={wordsText} onChange={(e) => { setWordsText(e.target.value); }} helperText="Comma-separated (leet/spacing aware)." />
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Raid guard</Typography>
          <FormControlLabel control={<Switch checked={cfg.rg_enabled} onChange={(e) => set({ rg_enabled: e.target.checked })} />} label="Auto-lock on coordinated spam" />
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Triggers on many distinct accounts tripping the filter or posting identical text — not raw join rate.
          </Typography>
          {num('Window (seconds)', 'rg_window_seconds', 10, 600)}
          {num('Violators to trigger', 'rg_trigger_violators', 2, 50)}
          {num('Duplicate-flood threshold', 'rg_duplicate_threshold', 2, 50)}
          {num('Lockdown minutes', 'rg_lockdown_minutes', 1, 1440)}
          <TextField select size="small" margin="dense" fullWidth label="Lockdown action for joiners"
            value={cfg.rg_lockdown_action} onChange={(e) => set({ rg_lockdown_action: e.target.value })}>
            {RG_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
          </TextField>
          <FormControlLabel control={<Switch checked={cfg.rg_notify} onChange={(e) => set({ rg_notify: e.target.checked })} />} label="Announce when raid mode activates" />
          <TextField select size="small" margin="dense" fullWidth label="Announce in channel"
            value={cfg.rg_notify_channel_id || ''} onChange={(e) => set({ rg_notify_channel_id: e.target.value || null })}>
            <MenuItem value="">— system channel —</MenuItem>
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Join gate</Typography>
          {num('Minimum account age (days, 0 = off)', 'jg_min_account_age_days', 0, 365)}
          <Typography variant="caption" color="text.disabled">Newer accounts are kicked on join. Useful during raids.</Typography>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Emergency lockdown</Typography>
          {cfg.manual_lockdown_active ? (
            <>
              <Typography color="error" fontWeight={600} mb={1}>🔒 Active until {new Date(cfg.manual_lockdown_until).toLocaleString()}</Typography>
              <Button variant="outlined" onClick={() => lockdown(0)}>Lift lockdown</Button>
            </>
          ) : (
            <>
              <Typography variant="body2" color="text.secondary" mb={1}>Instantly restrict every new joiner (timeout/kick per raid-guard action).</Typography>
              <Stack direction="row" spacing={1}>
                <Button variant="contained" onClick={() => lockdown(30)}>Lock 30 min</Button>
                <Button variant="outlined" onClick={() => lockdown(120)}>Lock 2 h</Button>
              </Stack>
            </>
          )}
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, alignItems: 'center' }}>
        {error && <Alert severity="error" sx={{ py: 0 }}>{error}</Alert>}
        <Button variant="contained" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</Button>
      </Grid>

      <Grid item xs={12}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Protection activity</Typography>
          {events.length === 0 && <Typography variant="body2" color="text.secondary">No events yet.</Typography>}
          <List dense>
            {events.map((e) => (
              <ListItem key={e.id} disableGutters
                secondaryAction={<Typography variant="caption" color="text.disabled">{new Date(e.created_at).toLocaleString()}</Typography>}>
                <Chip size="small" label={CAT_LABEL[e.category] || e.category} color={CAT_COLOR[e.category] || 'default'} variant="outlined" sx={{ mr: 1 }} />
                <ListItemText primary={`${e.action} — ${e.username ? e.username + ' · ' : ''}${e.detail || ''}`}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </CardContent></Card>
      </Grid>

      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Grid>
  );
}
