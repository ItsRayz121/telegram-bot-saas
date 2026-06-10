import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Switch, FormControlLabel, TextField,
  MenuItem, Button, List, ListItem, ListItemText, Chip, CircularProgress, Alert, Snackbar,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';

const TEXT_TYPES = new Set([0, 5]);

export default function LevelingTab({ guildId, channels = [] }) {
  const [cfg, setCfg] = useState(null);
  const [board, setBoard] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));

  useEffect(() => {
    Promise.all([
      guildizerApi.get(`/api/guilds/${guildId}/leveling`),
      guildizerApi.get(`/api/guilds/${guildId}/leaderboard?limit=10`).catch(() => ({ data: { leaderboard: [] } })),
    ]).then(([s, b]) => { setCfg(s.data); setBoard(b.data.leaderboard || []); })
      .catch(() => setError('Failed to load leveling.'))
      .finally(() => setLoading(false));
  }, [guildId]);

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));

  async function save() {
    setSaving(true); setError(null);
    try { const { data } = await guildizerApi.put(`/api/guilds/${guildId}/leveling`, cfg); setCfg(data); setSaved(true); }
    catch { setError('Save failed.'); } finally { setSaving(false); }
  }

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
  if (!cfg) return <Alert severity="warning">{error || 'No settings.'}</Alert>;

  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>XP &amp; levels</Typography>
          <FormControlLabel control={<Switch checked={cfg.levels_enabled} onChange={(e) => set({ levels_enabled: e.target.checked })} />} label="Award XP for chatting (100 XP per level)" />
          <TextField type="number" size="small" margin="dense" fullWidth label="XP per message"
            value={cfg.xp_per_message} inputProps={{ min: 0, max: 1000 }} onChange={(e) => set({ xp_per_message: Number(e.target.value) })} />
          <TextField type="number" size="small" margin="dense" fullWidth label="Cooldown between awards (seconds)"
            value={cfg.xp_cooldown_seconds} inputProps={{ min: 0, max: 3600 }} onChange={(e) => set({ xp_cooldown_seconds: Number(e.target.value) })} />
          <FormControlLabel control={<Switch checked={cfg.announce_level_up} onChange={(e) => set({ announce_level_up: e.target.checked })} />} label="Announce level-ups" />
          <TextField select size="small" margin="dense" fullWidth label="Announce in channel"
            value={cfg.levelup_channel_id || ''} onChange={(e) => set({ levelup_channel_id: e.target.value || null })}>
            <MenuItem value="">— same channel as message —</MenuItem>
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
          <TextField size="small" margin="dense" fullWidth label="Level-up message" placeholder="🎉 {user} reached level {level}!"
            value={cfg.levelup_message} inputProps={{ maxLength: 1000 }} onChange={(e) => set({ levelup_message: e.target.value })}
            helperText="Placeholders: {user} {username} {level}" />
          <Box sx={{ mt: 1, display: 'flex', justifyContent: 'flex-end', gap: 2, alignItems: 'center' }}>
            {error && <Alert severity="error" sx={{ py: 0 }}>{error}</Alert>}
            <Button variant="contained" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</Button>
          </Box>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Leaderboard</Typography>
          {board.length === 0 && <Typography variant="body2" color="text.secondary">No XP earned yet.</Typography>}
          <List dense>
            {board.map((m) => (
              <ListItem key={m.user_id} disableGutters secondaryAction={<Typography variant="caption" color="text.secondary">{m.xp} XP</Typography>}>
                <Typography variant="body2" fontWeight={700} color="primary.main" sx={{ width: 34 }}>#{m.rank}</Typography>
                <ListItemText primary={m.username || m.user_id} primaryTypographyProps={{ noWrap: true }} />
                <Chip size="small" label={`Lvl ${m.level}`} sx={{ mr: 1 }} />
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
