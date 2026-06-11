import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Switch, FormControlLabel, TextField,
  MenuItem, Button, List, ListItem, ListItemText, Chip, CircularProgress, Alert,
  Snackbar, Stack, IconButton,
} from '@mui/material';
import { Add, Delete } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const TEXT_TYPES = new Set([0, 5]);

export default function LevelingTab({ guildId, channels = [], roles = [] }) {
  const [cfg, setCfg] = useState(null);
  const [board, setBoard] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const assignableRoles = roles.filter((r) => !r.managed && r.name !== '@everyone');
  const roleName = (id) => assignableRoles.find((r) => r.id === id)?.name || id;

  useEffect(() => {
    Promise.all([
      guildizerApi.get(`/api/guilds/${guildId}/leveling`),
      guildizerApi.get(`/api/guilds/${guildId}/leaderboard?limit=10`).catch(() => ({ data: { leaderboard: [] } })),
    ]).then(([s, b]) => { setCfg(s.data); setBoard(b.data.leaderboard || []); })
      .catch(() => setError('Failed to load leveling.'))
      .finally(() => setLoading(false));
  }, [guildId]);

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));
  const setL2 = (patch) => setCfg((c) => ({ ...c, leveling2: { ...c.leveling2, ...patch } }));

  async function save() {
    setSaving(true); setError(null);
    try { const { data } = await guildizerApi.put(`/api/guilds/${guildId}/leveling`, cfg); setCfg(data); setSaved(true); }
    catch { setError('Save failed.'); } finally { setSaving(false); }
  }

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
  if (!cfg) return <Alert severity="warning">{error || 'No settings.'}</Alert>;

  const l2 = cfg.leveling2 || {};
  const rewards = l2.role_rewards || [];
  const numL2 = (label, key, max = 1000) => (
    <TextField type="number" size="small" margin="dense" fullWidth label={label}
      value={l2[key] ?? 0} inputProps={{ min: 0, max }} onChange={(e) => setL2({ [key]: Number(e.target.value) })} />
  );

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
          {numL2('XP per reaction received (0 = off)', 'xp_per_reaction')}
          {numL2('Reaction XP cooldown (seconds)', 'reaction_cooldown_seconds', 3600)}
          <FormControlLabel control={<Switch checked={cfg.announce_level_up} onChange={(e) => set({ announce_level_up: e.target.checked })} />} label="Announce level-ups" />
          <TextField select size="small" margin="dense" fullWidth label="Announce in channel"
            value={cfg.levelup_channel_id || ''} onChange={(e) => set({ levelup_channel_id: e.target.value || null })}>
            <MenuItem value="">— same channel as message —</MenuItem>
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
          <TextField size="small" margin="dense" fullWidth label="Level-up message" placeholder="🎉 {user} reached level {level}!"
            value={cfg.levelup_message} inputProps={{ maxLength: 1000 }} onChange={(e) => set({ levelup_message: e.target.value })}
            helperText="Placeholders: {user} {username} {level}" />
          {numL2('Delete level-up message after (seconds, 0 = keep)', 'levelup_delete_after_seconds', 86400)}
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Moderation XP penalties</Typography>
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            XP removed when a member is moderated (XP never drops below 0). 0 disables a penalty.
          </Typography>
          {numL2('Warn penalty', 'penalty_warn', 10000)}
          {numL2('Timeout penalty', 'penalty_timeout', 10000)}
          {numL2('Kick penalty', 'penalty_kick', 10000)}
          {numL2('Ban penalty', 'penalty_ban', 10000)}
        </CardContent></Card>

        <Card variant="outlined" sx={{ mt: 2 }}><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Level → role rewards</Typography>
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Grant a role when a member reaches a level. Guildizer's role must sit above any role it assigns.
          </Typography>
          {rewards.map((r, i) => (
            <Stack key={i} direction="row" spacing={1} alignItems="center" mb={1}>
              <TextField type="number" size="small" label="From level" value={r.level}
                inputProps={{ min: 1, max: 1000 }} sx={{ width: 110 }}
                onChange={(e) => setL2({ role_rewards: rewards.map((x, j) => j === i ? { ...x, level: Number(e.target.value) } : x) })} />
              <TextField select size="small" label="Role" value={r.role_id} sx={{ flex: 1 }}
                onChange={(e) => setL2({ role_rewards: rewards.map((x, j) => j === i ? { ...x, role_id: e.target.value } : x) })}>
                {assignableRoles.map((ar) => <MenuItem key={ar.id} value={ar.id}>{ar.name}</MenuItem>)}
                {!assignableRoles.some((ar) => ar.id === r.role_id) && r.role_id && (
                  <MenuItem value={r.role_id}>{roleName(r.role_id)}</MenuItem>
                )}
              </TextField>
              <IconButton size="small" onClick={() => setL2({ role_rewards: rewards.filter((_, j) => j !== i) })}>
                <Delete fontSize="small" />
              </IconButton>
            </Stack>
          ))}
          <Button size="small" startIcon={<Add />}
            disabled={rewards.length >= 20 || assignableRoles.length === 0}
            onClick={() => setL2({ role_rewards: [...rewards, { level: (rewards[rewards.length - 1]?.level || 0) + 5, role_id: assignableRoles[0]?.id }] })}>
            Add reward
          </Button>
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

      <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, alignItems: 'center' }}>
        {error && <Alert severity="error" sx={{ py: 0 }}>{error}</Alert>}
        <Button variant="contained" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</Button>
      </Grid>

      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Grid>
  );
}
