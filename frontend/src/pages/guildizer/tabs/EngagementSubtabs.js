/**
 * Engagement area subtabs (Telegizer-parity IA): Raids · Invite Links.
 * (The Campaigns subtab reuses CampaignsTab directly.)
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, TextField, MenuItem, Button, Chip,
  CircularProgress, Alert, List, ListItem, ListItemText, Stack,
} from '@mui/material';
import { RocketLaunch } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const TEXT_TYPES = new Set([0, 5]);
const STATUS_COLOR = { draft: 'default', active: 'success', paused: 'warning', closed: 'default' };

// ── Raids: raid-type campaigns with a focused quick-create form ───────────────
export function RaidsSubtab({ guildId, channels = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const [raids, setRaids] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [goals, setGoals] = useState('Repost, like and reply to the post.');
  const [hours, setHours] = useState(24);
  const [xp, setXp] = useState(50);
  const [channelId, setChannelId] = useState('');

  const reload = useCallback(async () => {
    try {
      const { data } = await guildizerApi.get(`/api/guilds/${guildId}/campaigns`);
      setRaids((data.campaigns || []).filter((c) => c.type === 'raid'));
      setError(null);
    } catch { setError('Failed to load raids.'); setRaids([]); }
  }, [guildId]);

  useEffect(() => { reload(); }, [reload]);

  async function createRaid() {
    setBusy(true);
    try {
      const { data } = await guildizerApi.post(`/api/guilds/${guildId}/campaigns`, {
        type: 'raid',
        title,
        description: goals,
        task_url: url,
        verification_mode: 'honor',
        reward_xp: xp,
        channel_id: channelId || null,
      });
      // activate + announce right away — a raid is time-critical
      await guildizerApi.put(`/api/guilds/${guildId}/campaigns/${data.id}`, {
        status: 'active',
        ends_at: new Date(Date.now() + hours * 3600 * 1000).toISOString(),
      });
      if (channelId) {
        await guildizerApi.post(`/api/guilds/${guildId}/campaigns/${data.id}/post`).catch(() => {});
      }
      setTitle(''); setUrl('');
      await reload();
    } catch { setError('Could not create the raid.'); }
    setBusy(false);
  }

  async function endRaid(id) {
    try {
      await guildizerApi.put(`/api/guilds/${guildId}/campaigns/${id}`, { status: 'closed' });
      await reload();
    } catch { setError('Could not close the raid.'); }
  }

  if (raids === null) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Grid container spacing={2}>
      {error && <Grid item xs={12}><Alert severity="warning" onClose={() => setError(null)}>{error}</Alert></Grid>}

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Launch a raid</Typography>
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Rally the server on a post — members who take part earn XP. Announced in the chosen channel.
          </Typography>
          <TextField fullWidth size="small" margin="dense" label="Raid title"
            value={title} inputProps={{ maxLength: 200 }} onChange={(e) => setTitle(e.target.value)} />
          <TextField fullWidth size="small" margin="dense" label="Target post URL"
            placeholder="https://x.com/…" value={url} onChange={(e) => setUrl(e.target.value)} />
          <TextField fullWidth multiline minRows={2} size="small" margin="dense"
            label="Goals (what members should do)"
            value={goals} inputProps={{ maxLength: 2000 }} onChange={(e) => setGoals(e.target.value)} />
          <Stack direction="row" spacing={1}>
            <TextField type="number" size="small" margin="dense" label="Duration (hours)"
              value={hours} inputProps={{ min: 1, max: 168 }} onChange={(e) => setHours(Number(e.target.value))} sx={{ flex: 1 }} />
            <TextField type="number" size="small" margin="dense" label="XP reward"
              value={xp} inputProps={{ min: 0, max: 100000 }} onChange={(e) => setXp(Number(e.target.value))} sx={{ flex: 1 }} />
          </Stack>
          <TextField select fullWidth size="small" margin="dense" label="Announce in channel"
            value={channelId} onChange={(e) => setChannelId(e.target.value)}>
            <MenuItem value="">— don't announce —</MenuItem>
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
          <Button startIcon={<RocketLaunch />} variant="contained" size="small" sx={{ mt: 1 }}
            disabled={busy || !title.trim() || !/^https?:\/\//.test(url)} onClick={createRaid}>
            Launch raid
          </Button>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Raids</Typography>
          {raids.length === 0 && <Typography variant="body2" color="text.secondary">No raids yet.</Typography>}
          <List dense>
            {raids.map((r) => (
              <ListItem key={r.id} disableGutters
                secondaryAction={r.status === 'active' && (
                  <Button size="small" color="inherit" onClick={() => endRaid(r.id)}>End</Button>
                )}>
                <Chip size="small" variant="outlined" label={r.status} color={STATUS_COLOR[r.status] || 'default'} sx={{ mr: 1 }} />
                <ListItemText
                  primary={r.title}
                  secondary={`${r.reward_xp} XP · ${r.submission_count ?? 0} participants${r.ends_at ? ` · ends ${new Date(r.ends_at).toLocaleString()}` : ''}`}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </CardContent></Card>
      </Grid>
    </Grid>
  );
}

// ── Invite Links: referral tracking + reward settings ─────────────────────────
export function InviteLinksSubtab({ guildId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [xp, setXp] = useState(0);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const { data: res } = await guildizerApi.get(`/api/guilds/${guildId}/referrals`);
      setData(res); setXp(res.xp_per_referral || 0); setError(null);
    } catch { setError('Failed to load invite tracking.'); setData({ leaderboard: [], recent: [] }); }
  }, [guildId]);

  useEffect(() => { reload(); }, [reload]);

  async function saveXp() {
    setBusy(true);
    try {
      await guildizerApi.put(`/api/guilds/${guildId}/referrals/settings`, { xp_per_referral: xp });
    } catch { setError('Save failed.'); }
    setBusy(false);
  }

  if (data === null) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Grid container spacing={2}>
      {error && <Grid item xs={12}><Alert severity="warning" onClose={() => setError(null)}>{error}</Alert></Grid>}

      <Grid item xs={12} md={5}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Referral rewards</Typography>
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            The bot tracks which invite each member joined through. Members create their own tracked
            link with /invitelink.
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField type="number" size="small" label="XP per referral" value={xp}
              inputProps={{ min: 0, max: 1000 }} onChange={(e) => setXp(Number(e.target.value))} sx={{ flex: 1 }} />
            <Button variant="contained" size="small" disabled={busy} onClick={saveXp}>Save</Button>
          </Stack>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={7}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Top inviters</Typography>
          {data.leaderboard.length === 0 && <Typography variant="body2" color="text.secondary">No tracked invites yet.</Typography>}
          <List dense>
            {data.leaderboard.map((r, i) => (
              <ListItem key={r.inviter_id} disableGutters
                secondaryAction={<Typography variant="caption" color="text.secondary">{r.joins} joins</Typography>}>
                <Typography variant="body2" fontWeight={700} color="primary.main" sx={{ width: 34 }}>#{i + 1}</Typography>
                <ListItemText primary={r.inviter_name || r.inviter_id} primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Recent joins via invites</Typography>
          {data.recent.length === 0 && <Typography variant="body2" color="text.secondary">Nothing yet.</Typography>}
          <List dense>
            {data.recent.map((j) => (
              <ListItem key={j.id} disableGutters
                secondaryAction={<Typography variant="caption" color="text.disabled">{new Date(j.created_at).toLocaleString()}</Typography>}>
                <ListItemText
                  primary={`${j.member_name || j.member_id} joined`}
                  secondary={j.inviter_name ? `invited by ${j.inviter_name}${j.invite_code ? ` · ${j.invite_code}` : ''}` : (j.invite_code || 'unknown invite')}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </CardContent></Card>
      </Grid>
    </Grid>
  );
}
