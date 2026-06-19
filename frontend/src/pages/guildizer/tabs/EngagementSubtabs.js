/**
 * Engagement area subtabs (Telegizer-parity IA): Raids · Invite Links ·
 * Tickets · Starboard · Boosts. (The Campaigns subtab reuses CampaignsTab directly.)
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Grid, Typography, TextField, MenuItem, Button, Chip,
  CircularProgress, Alert, List, ListItem, ListItemText, Stack,
  FormControlLabel, Switch,
} from '@mui/material';
import { RocketLaunch, Send, DeleteOutline } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';

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
  const [mode, setMode] = useState('now'); // now | draft

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
      if (mode === 'now') {
        // activate + announce right away — a raid is time-critical
        await guildizerApi.put(`/api/guilds/${guildId}/campaigns/${data.id}`, {
          status: 'active',
          ends_at: new Date(Date.now() + hours * 3600 * 1000).toISOString(),
        });
        if (channelId) {
          await guildizerApi.post(`/api/guilds/${guildId}/campaigns/${data.id}/post`).catch(() => {});
        }
      }
      // mode === 'draft': leave it as a draft to launch later from the list below.
      setTitle(''); setUrl('');
      await reload();
    } catch { setError('Could not create the raid.'); }
    setBusy(false);
  }

  async function launchDraft(id) {
    try {
      await guildizerApi.put(`/api/guilds/${guildId}/campaigns/${id}`, {
        status: 'active', ends_at: new Date(Date.now() + hours * 3600 * 1000).toISOString(),
      });
      await guildizerApi.post(`/api/guilds/${guildId}/campaigns/${id}/post`).catch(() => {});
      await reload();
    } catch { setError('Could not launch the raid.'); }
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

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="gz.engagement.launch_a_raid" title="Launch a raid">
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
          <Stack direction="row" spacing={1}>
            <TextField select fullWidth size="small" margin="dense" label="Announce in channel"
              value={channelId} onChange={(e) => setChannelId(e.target.value)}>
              <MenuItem value="">— don't announce —</MenuItem>
              {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
            </TextField>
            <TextField select size="small" margin="dense" label="When" value={mode}
              onChange={(e) => setMode(e.target.value)} sx={{ minWidth: 150 }}>
              <MenuItem value="now">Launch now</MenuItem>
              <MenuItem value="draft">Save as draft</MenuItem>
            </TextField>
          </Stack>
          <Button startIcon={<RocketLaunch />} variant="contained" size="small" sx={{ mt: 1 }}
            disabled={busy || !title.trim() || !/^https?:\/\//.test(url)} onClick={createRaid}>
            {mode === 'draft' ? 'Save draft' : 'Launch raid'}
          </Button>
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="gz.engagement.raids_list" title="Raids">
          <Typography variant="body2" color="text.secondary" mb={2}>Active and past raids, with participant counts and end times.</Typography>
          {raids.length === 0 && <Typography variant="body2" color="text.secondary">No raids yet.</Typography>}
          <List dense>
            {raids.map((r) => (
              <ListItem key={r.id} disableGutters
                secondaryAction={(
                  r.status === 'active'
                    ? <Button size="small" color="inherit" onClick={() => endRaid(r.id)}>End</Button>
                    : r.status === 'draft'
                      ? <Button size="small" startIcon={<RocketLaunch />} onClick={() => launchDraft(r.id)}>Launch</Button>
                      : null
                )}>
                <Chip size="small" variant="outlined" label={r.status} color={STATUS_COLOR[r.status] || 'default'} sx={{ mr: 1 }} />
                <ListItemText
                  primary={r.title}
                  secondary={`${r.reward_xp} XP · ${r.counts?.total ?? 0} participants${r.ends_at ? ` · ends ${new Date(r.ends_at).toLocaleString()}` : ''}`}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </GuildizerCollapsibleCard>
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

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="gz.engagement.referral_rewards" title="Referral rewards">
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            The bot tracks which invite each member joined through. Members create their own tracked
            link with /invitelink.
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField type="number" size="small" label="XP per referral" value={xp}
              inputProps={{ min: 0, max: 1000 }} onChange={(e) => setXp(Number(e.target.value))} sx={{ flex: 1 }} />
            <Button variant="contained" size="small" disabled={busy} onClick={saveXp}>Save</Button>
          </Stack>
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="gz.engagement.top_inviters" title="Top inviters">
          <Typography variant="body2" color="text.secondary" mb={2}>Members ranked by how many people joined through their tracked invites.</Typography>
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
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="gz.engagement.recent_joins" title="Recent joins via invites">
          <Typography variant="body2" color="text.secondary" mb={2}>The latest members to join and which invite brought them in.</Typography>
          {data.recent.length === 0 && <Typography variant="body2" color="text.secondary">Nothing yet.</Typography>}
          <List dense>
            {data.recent.map((j) => (
              <ListItem key={j.id} disableGutters
                secondaryAction={<Typography variant="caption" color="text.disabled">{new Date(j.created_at).toLocaleString()}</Typography>}>
                <ListItemText
                  primary={`${j.joiner_name || j.joiner_id} joined`}
                  secondary={j.inviter_name ? `invited by ${j.inviter_name}${j.code ? ` · ${j.code}` : ''}` : (j.code || 'unknown invite')}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </GuildizerCollapsibleCard>
      </Grid>
    </Grid>
  );
}

// ── Tickets: button → private support thread, transcript on close ─────────────
export function TicketsSubtab({ guildId, channels = [], roles = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const assignableRoles = roles.filter((r) => !r.managed && r.name !== '@everyone');
  const [cfg, setCfg] = useState(null);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const { data } = await guildizerApi.get(`/api/guilds/${guildId}/tickets`);
      setCfg(data); setError(null);
    } catch { setError('Failed to load ticket settings.'); }
  }, [guildId]);

  useEffect(() => { reload(); }, [reload]);

  const set = (patch) => { setSaved(false); setCfg((c) => ({ ...c, ...patch })); };

  async function save() {
    setBusy(true);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/tickets`, cfg);
      setCfg(data); setSaved(true); setError(null);
    } catch { setError('Save failed.'); }
    setBusy(false);
  }

  async function postPanel() {
    setBusy(true);
    try {
      await guildizerApi.put(`/api/guilds/${guildId}/tickets`, cfg);
      await guildizerApi.post(`/api/guilds/${guildId}/tickets/panel`);
      await reload();
    } catch (e) { setError(e?.response?.data?.message || 'Could not queue the panel.'); }
    setBusy(false);
  }

  async function removePanel() {
    setBusy(true);
    try {
      await guildizerApi.delete(`/api/guilds/${guildId}/tickets/panel`);
      await reload();
    } catch { setError('Could not queue the removal.'); }
    setBusy(false);
  }

  if (cfg === null) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  const panelStatus = cfg.needs_post ? { label: 'posting…', color: 'warning' }
    : cfg.needs_delete ? { label: 'removing…', color: 'warning' }
    : cfg.post_error ? { label: cfg.post_error, color: 'error' }
    : cfg.panel_message_id ? { label: 'panel posted', color: 'success' }
    : { label: 'not posted', color: 'default' };

  return (
    <Grid container spacing={2}>
      {error && <Grid item xs={12}><Alert severity="warning" onClose={() => setError(null)}>{error}</Alert></Grid>}

      <Grid item xs={12}>
        <GuildizerCollapsibleCard
          id="gz.engagement.ticket_system"
          title="Ticket system"
          action={(
            <FormControlLabel sx={{ mr: 0 }} label="Enabled"
              control={<Switch checked={!!cfg.enabled} onChange={(e) => set({ enabled: e.target.checked })} />} />
          )}
        >
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Members click a button on the panel to open a private support thread.
            Closing a ticket posts its transcript to the channel you pick below.
          </Typography>
          <TextField select fullWidth size="small" margin="dense" label="Panel channel"
            value={cfg.panel_channel_id || ''} onChange={(e) => set({ panel_channel_id: e.target.value || null })}>
            <MenuItem value="">— pick a channel —</MenuItem>
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
          <TextField fullWidth size="small" margin="dense" label="Panel title"
            value={cfg.panel_title} inputProps={{ maxLength: 256 }} onChange={(e) => set({ panel_title: e.target.value })} />
          <TextField fullWidth multiline minRows={2} size="small" margin="dense" label="Panel message"
            value={cfg.panel_message} inputProps={{ maxLength: 2000 }} onChange={(e) => set({ panel_message: e.target.value })} />
          <TextField fullWidth size="small" margin="dense" label="Button label"
            value={cfg.button_label} inputProps={{ maxLength: 80 }} onChange={(e) => set({ button_label: e.target.value })} />
          <TextField select fullWidth size="small" margin="dense" label="Support role (pinged into each ticket)"
            value={cfg.support_role_id || ''} onChange={(e) => set({ support_role_id: e.target.value || null })}>
            <MenuItem value="">— none —</MenuItem>
            {assignableRoles.map((r) => <MenuItem key={r.id} value={r.id}>{r.name}</MenuItem>)}
          </TextField>
          <TextField select fullWidth size="small" margin="dense" label="Transcript channel"
            value={cfg.transcript_channel_id || ''} onChange={(e) => set({ transcript_channel_id: e.target.value || null })}>
            <MenuItem value="">— don't keep transcripts —</MenuItem>
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
          <TextField fullWidth multiline minRows={2} size="small" margin="dense"
            label="First message inside a new ticket (optional)"
            value={cfg.welcome_message} inputProps={{ maxLength: 1500 }} onChange={(e) => set({ welcome_message: e.target.value })} />
          <TextField type="number" size="small" margin="dense" label="Max open tickets per member"
            value={cfg.max_open_per_member} inputProps={{ min: 1, max: 10 }}
            onChange={(e) => set({ max_open_per_member: Number(e.target.value) })} sx={{ width: 220 }} />
          <Stack direction="row" spacing={1} alignItems="center" mt={1} flexWrap="wrap" useFlexGap>
            <Button variant="contained" size="small" disabled={busy} onClick={save}>
              {saved ? 'Saved ✓' : 'Save'}
            </Button>
            <Button startIcon={<Send />} variant="outlined" size="small"
              disabled={busy || !cfg.panel_channel_id} onClick={postPanel}>
              {cfg.panel_message_id ? 'Re-post panel' : 'Post panel'}
            </Button>
            {cfg.panel_message_id && (
              <Button startIcon={<DeleteOutline />} color="inherit" size="small"
                disabled={busy} onClick={removePanel}>
                Remove panel
              </Button>
            )}
            <Chip size="small" variant="outlined" label={panelStatus.label} color={panelStatus.color} />
          </Stack>
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard
          id="gz.engagement.open_tickets"
          title={`Open tickets${cfg.open?.length ? ` (${cfg.open.length})` : ''}`}
        >
          <Typography variant="body2" color="text.secondary" mb={2}>Currently open support threads members have opened from the panel.</Typography>
          {(!cfg.open || cfg.open.length === 0) &&
            <Typography variant="body2" color="text.secondary">No open tickets. {cfg.counter > 0 ? `${cfg.counter} handled so far.` : ''}</Typography>}
          <List dense>
            {(cfg.open || []).map((t) => (
              <ListItem key={t.thread_id} disableGutters
                secondaryAction={<Typography variant="caption" color="text.disabled">
                  {t.opened_at ? new Date(t.opened_at + 'Z').toLocaleString() : ''}
                </Typography>}>
                <Chip size="small" variant="outlined" label={`#${String(t.number).padStart(4, '0')}`} sx={{ mr: 1 }} />
                <ListItemText primary={t.username || t.user_id}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </GuildizerCollapsibleCard>
      </Grid>
    </Grid>
  );
}

// ── Starboard: ⭐-threshold reposts to a best-of channel ───────────────────────
export function StarboardSubtab({ guildId, channels = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const [cfg, setCfg] = useState(null);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    guildizerApi.get(`/api/guilds/${guildId}/starboard`)
      .then(({ data }) => { if (alive) setCfg(data); })
      .catch(() => { if (alive) setError('Failed to load starboard settings.'); });
    return () => { alive = false; };
  }, [guildId]);

  const set = (patch) => { setSaved(false); setCfg((c) => ({ ...c, ...patch })); };

  async function save() {
    setBusy(true);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/starboard`, cfg);
      setCfg(data); setSaved(true); setError(null);
    } catch { setError('Save failed.'); }
    setBusy(false);
  }

  if (cfg === null && !error) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Grid container spacing={2}>
      {error && <Grid item xs={12}><Alert severity="warning" onClose={() => setError(null)}>{error}</Alert></Grid>}

      {cfg && (
        <Grid item xs={12}>
          <GuildizerCollapsibleCard
            id="gz.engagement.starboard"
            title="Starboard"
            action={(
              <FormControlLabel sx={{ mr: 0 }} label="Enabled"
                control={<Switch checked={!!cfg.enabled} onChange={(e) => set({ enabled: e.target.checked })} />} />
            )}
          >
            <Typography variant="caption" color="text.secondary" display="block" mb={1}>
              When a message collects enough reactions, the bot reposts it to your
              best-of channel and keeps the count updated.
            </Typography>
            <TextField select fullWidth size="small" margin="dense" label="Starboard channel"
              value={cfg.channel_id || ''} onChange={(e) => set({ channel_id: e.target.value || null })}>
              <MenuItem value="">— pick a channel —</MenuItem>
              {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
            </TextField>
            <Stack direction="row" spacing={1}>
              <TextField size="small" margin="dense" label="Emoji" value={cfg.emoji}
                inputProps={{ maxLength: 64 }} onChange={(e) => set({ emoji: e.target.value })} sx={{ flex: 1 }} />
              <TextField type="number" size="small" margin="dense" label="Stars needed"
                value={cfg.threshold} inputProps={{ min: 1, max: 100 }}
                onChange={(e) => set({ threshold: Number(e.target.value) })} sx={{ flex: 1 }} />
            </Stack>
            <FormControlLabel sx={{ display: 'block', mt: 0.5 }} label="Let authors star their own messages"
              control={<Switch checked={!!cfg.allow_self_star} onChange={(e) => set({ allow_self_star: e.target.checked })} />} />
            <Stack direction="row" spacing={1} alignItems="center" mt={1}>
              <Button variant="contained" size="small" disabled={busy} onClick={save}>
                {saved ? 'Saved ✓' : 'Save'}
              </Button>
              {cfg.posted_count > 0 && (
                <Typography variant="caption" color="text.secondary">
                  {cfg.posted_count} message{cfg.posted_count === 1 ? '' : 's'} on the board
                </Typography>
              )}
            </Stack>
          </GuildizerCollapsibleCard>
        </Grid>
      )}
    </Grid>
  );
}

// ── Events: native Discord scheduled events from the dashboard ────────────────
const VOICEISH_TYPES = { voice: 2, stage: 13 };
const EVENT_STATUS_COLOR = { draft: 'warning', pending: 'default', created: 'info', done: 'success', failed: 'error', cancelled: 'default' };

export function EventsSubtab({ guildId, channels = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [entityType, setEntityType] = useState('external');
  const [channelId, setChannelId] = useState('');
  const [location, setLocation] = useState('');
  const [startAt, setStartAt] = useState('');
  const [endAt, setEndAt] = useState('');
  const [remind, setRemind] = useState(15);
  const [remindChannel, setRemindChannel] = useState('');
  const [mode, setMode] = useState('now'); // now | draft

  const voiceChannels = channels.filter((c) => c.type === VOICEISH_TYPES[entityType]);

  const reload = useCallback(() => guildizerApi.get(`/api/guilds/${guildId}/events`)
    .then(({ data }) => setEvents(data.events))
    .catch(() => { setError('Failed to load events.'); setEvents([]); }), [guildId]);
  useEffect(() => { reload(); }, [reload]);

  async function add() {
    setBusy(true); setError(null);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/events`, {
        name, description, entity_type: entityType,
        channel_id: entityType === 'external' ? null : channelId,
        location: entityType === 'external' ? location : '',
        start_at: new Date(startAt).toISOString(),
        end_at: endAt ? new Date(endAt).toISOString() : null,
        remind_minutes: remind,
        reminder_channel_id: remindChannel || null,
        draft: mode === 'draft',
      });
      setName(''); setDescription(''); setLocation(''); setStartAt(''); setEndAt('');
      await reload();
    } catch { setError('Could not create the event.'); }
    setBusy(false);
  }

  async function publish(id) {
    setError(null);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/events/${id}/publish`);
      await reload();
    } catch { setError('Could not publish the draft — make sure the start time is still in the future.'); }
  }

  if (events === null) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  const formOk = name.trim() && startAt
    && (entityType === 'external' ? location.trim() : channelId);

  return (
    <Grid container spacing={2}>
      {error && <Grid item xs={12}><Alert severity="warning" onClose={() => setError(null)}>{error}</Alert></Grid>}

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="gz.engagement.new_server_event" title="📅 New server event">
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Creates a native Discord scheduled event members can mark interest in.
            The bot needs the Manage Events permission.
          </Typography>
          <TextField fullWidth size="small" margin="dense" label="Event name"
            value={name} inputProps={{ maxLength: 100 }} onChange={(e) => setName(e.target.value)} />
          <TextField fullWidth multiline minRows={2} size="small" margin="dense" label="Description"
            value={description} inputProps={{ maxLength: 1000 }} onChange={(e) => setDescription(e.target.value)} />
          <TextField select fullWidth size="small" margin="dense" label="Where"
            value={entityType} onChange={(e) => { setEntityType(e.target.value); setChannelId(''); }}>
            <MenuItem value="external">Somewhere else (external)</MenuItem>
            <MenuItem value="voice">Voice channel</MenuItem>
            <MenuItem value="stage">Stage channel</MenuItem>
          </TextField>
          {entityType === 'external' ? (
            <TextField fullWidth size="small" margin="dense" label="Location (link or place)"
              value={location} inputProps={{ maxLength: 200 }} onChange={(e) => setLocation(e.target.value)} />
          ) : (
            <TextField select fullWidth size="small" margin="dense" label="Channel"
              value={channelId} onChange={(e) => setChannelId(e.target.value)}>
              {voiceChannels.map((c) => <MenuItem key={c.id} value={c.id}>🔊 {c.name}</MenuItem>)}
            </TextField>
          )}
          <Stack direction="row" spacing={1}>
            <TextField type="datetime-local" size="small" margin="dense" label="Starts"
              InputLabelProps={{ shrink: true }} value={startAt} onChange={(e) => setStartAt(e.target.value)} sx={{ flex: 1 }} />
            <TextField type="datetime-local" size="small" margin="dense" label="Ends (optional)"
              InputLabelProps={{ shrink: true }} value={endAt} onChange={(e) => setEndAt(e.target.value)} sx={{ flex: 1 }} />
          </Stack>
          <Stack direction="row" spacing={1}>
            <TextField type="number" size="small" margin="dense" label="Remind (min before, 0 = off)"
              value={remind} inputProps={{ min: 0, max: 1440 }}
              onChange={(e) => setRemind(Number(e.target.value))} sx={{ flex: 1 }} />
            <TextField select size="small" margin="dense" label="Reminder channel"
              value={remindChannel} onChange={(e) => setRemindChannel(e.target.value)} sx={{ flex: 1 }}>
              <MenuItem value="">— none —</MenuItem>
              {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
            </TextField>
          </Stack>
          <TextField select fullWidth size="small" margin="dense" label="When to create"
            value={mode} onChange={(e) => setMode(e.target.value)}>
            <MenuItem value="now">Create on Discord now</MenuItem>
            <MenuItem value="draft">Save as draft (publish later)</MenuItem>
          </TextField>
          <Button startIcon={<RocketLaunch />} variant="contained" size="small" sx={{ mt: 1 }}
            disabled={busy || !formOk} onClick={add}>
            {mode === 'draft' ? 'Save draft' : 'Create event'}
          </Button>
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="gz.engagement.events_list" title="Upcoming & recent">
          <Typography variant="body2" color="text.secondary" mb={2}>Scheduled events with their status — cancel or remove them here.</Typography>
          {events.length === 0 && <Typography variant="body2" color="text.secondary">No events yet.</Typography>}
          <List dense>
            {events.map((ev) => (
              <ListItem key={ev.id} disableGutters
                secondaryAction={(
                  <Stack direction="row" spacing={0.5}>
                    {ev.status === 'draft' && (
                      <Button size="small" startIcon={<RocketLaunch />} onClick={() => publish(ev.id)}>
                        Publish
                      </Button>
                    )}
                    <Button size="small" color="inherit"
                      onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/events/${ev.id}`).then(reload)}>
                      {ev.status === 'created' ? 'Cancel' : 'Remove'}
                    </Button>
                  </Stack>
                )}>
                <Chip size="small" label={ev.status} color={EVENT_STATUS_COLOR[ev.status] || 'default'}
                  variant="outlined" sx={{ mr: 1 }} />
                <ListItemText
                  primary={ev.name}
                  secondary={`${new Date(ev.start_at).toLocaleString()}${ev.error ? ` · ${ev.error}` : ''}`}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </GuildizerCollapsibleCard>
      </Grid>
    </Grid>
  );
}

// ── Boosts: thank-you post + reward role + XP on server boost ─────────────────
export function BoostsSubtab({ guildId, channels = [], roles = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const [cfg, setCfg] = useState(null);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    guildizerApi.get(`/api/guilds/${guildId}/boosts`)
      .then(({ data }) => { if (alive) setCfg(data); })
      .catch(() => { if (alive) setError('Failed to load boost settings.'); });
    return () => { alive = false; };
  }, [guildId]);

  const set = (patch) => { setSaved(false); setCfg((c) => ({ ...c, ...patch })); };

  async function save() {
    setBusy(true);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/boosts`, cfg);
      setCfg(data); setSaved(true); setError(null);
    } catch { setError('Save failed.'); }
    setBusy(false);
  }

  if (cfg === null && !error) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Grid container spacing={2}>
      {error && <Grid item xs={12}><Alert severity="warning" onClose={() => setError(null)}>{error}</Alert></Grid>}

      {cfg && (
        <Grid item xs={12}>
          <GuildizerCollapsibleCard
            id="gz.engagement.boost_tracking"
            title="🚀 Boost tracking"
            action={(
              <FormControlLabel sx={{ mr: 0 }} label="Enabled"
                control={<Switch checked={!!cfg.enabled} onChange={(e) => set({ enabled: e.target.checked })} />} />
            )}
          >
            <Typography variant="caption" color="text.secondary" display="block" mb={1}>
              When someone boosts, the bot says thanks, can grant an extra reward role
              (on top of Discord's native booster role), and can award bonus XP. The
              reward role is removed when the boost ends.
            </Typography>
            <TextField fullWidth multiline minRows={2} size="small" margin="dense" label="Thank-you message"
              value={cfg.message || ''} inputProps={{ maxLength: 1500 }}
              onChange={(e) => set({ message: e.target.value })}
              helperText="Placeholders: {user} {server} {count}" />
            <TextField select fullWidth size="small" margin="dense" label="Post in channel"
              value={cfg.channel_id || ''} onChange={(e) => set({ channel_id: e.target.value || null })}>
              <MenuItem value="">— system channel —</MenuItem>
              {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
            </TextField>
            <TextField select fullWidth size="small" margin="dense" label="Extra reward role"
              value={cfg.role_id || ''} onChange={(e) => set({ role_id: e.target.value || null })}
              helperText="Roles with moderation/management permissions are never granted.">
              <MenuItem value="">— none —</MenuItem>
              {roles.map((r) => <MenuItem key={r.id} value={r.id}>@ {r.name}</MenuItem>)}
            </TextField>
            <TextField type="number" size="small" margin="dense" fullWidth label="XP bonus per boost (0 = off)"
              value={cfg.xp_bonus ?? 0} inputProps={{ min: 0, max: 10000 }}
              onChange={(e) => set({ xp_bonus: Number(e.target.value) })}
              helperText="Needs leveling enabled (Members → XP & Roles)." />
            <Button variant="contained" size="small" sx={{ mt: 1 }} disabled={busy} onClick={save}>
              {saved ? 'Saved ✓' : 'Save'}
            </Button>
          </GuildizerCollapsibleCard>
        </Grid>
      )}
    </Grid>
  );
}
