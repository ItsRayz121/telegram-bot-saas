import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, TextField, MenuItem, Button, Chip,
  CircularProgress, Alert, List, ListItem, ListItemText, Stack, Switch,
  IconButton, Checkbox, FormControlLabel, Tooltip,
} from '@mui/material';
import { Delete, Add, ContentCopy } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const TEXT_TYPES = new Set([0, 5]);
const TRIGGERS = [
  { value: 'message_contains', label: 'Message contains…' },
  { value: 'member_join', label: 'Member joins' },
  { value: 'member_leave', label: 'Member leaves' },
  { value: 'reaction_add', label: 'Reaction added' },
];
const ACTIONS = [
  { value: 'send_message', label: 'Send a message' },
  { value: 'add_role', label: 'Add a role' },
  { value: 'remove_role', label: 'Remove a role' },
  { value: 'timeout', label: 'Timeout the member' },
];
const OUT_EVENTS = ['member_join', 'member_leave', 'moderation_action', 'raid_activated'];

export default function AutomationTab({ guildId, channels = [], roles = [] }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [workflows, setWorkflows] = useState([]);
  const [mirrors, setMirrors] = useState([]);
  const [inbound, setInbound] = useState([]);
  const [outbound, setOutbound] = useState([]);

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const assignableRoles = roles.filter((r) => !r.managed && r.name !== '@everyone');

  const reload = useCallback(async () => {
    try {
      const [w, m, i, o] = await Promise.all([
        guildizerApi.get(`/api/guilds/${guildId}/workflows`),
        guildizerApi.get(`/api/guilds/${guildId}/mirrors`),
        guildizerApi.get(`/api/guilds/${guildId}/inbound-webhooks`),
        guildizerApi.get(`/api/guilds/${guildId}/outbound-webhooks`),
      ]);
      setWorkflows(w.data.workflows); setMirrors(m.data.mirrors);
      setInbound(i.data.webhooks); setOutbound(o.data.webhooks);
      setError(null);
    } catch { setError('Failed to load automation settings.'); }
    setLoading(false);
  }, [guildId]);

  useEffect(() => { reload(); }, [reload]);

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Grid container spacing={2}>
      {error && <Grid item xs={12}><Alert severity="warning" onClose={() => setError(null)}>{error}</Alert></Grid>}
      <Grid item xs={12}>
        <WorkflowsCard guildId={guildId} workflows={workflows} channels={textChannels}
          roles={assignableRoles} onChanged={reload} />
      </Grid>
      <Grid item xs={12} md={6}>
        <MirrorsCard guildId={guildId} mirrors={mirrors} channels={textChannels} onChanged={reload} />
      </Grid>
      <Grid item xs={12} md={6}>
        <WebhooksCard guildId={guildId} inbound={inbound} outbound={outbound}
          channels={textChannels} onChanged={reload} />
      </Grid>
    </Grid>
  );
}

export function WorkflowsCard({ guildId, workflows, channels, roles, onChanged }) {
  const [name, setName] = useState('');
  const [trigger, setTrigger] = useState('message_contains');
  const [triggerValue, setTriggerValue] = useState('');
  const [channelFilter, setChannelFilter] = useState('');
  const [actionType, setActionType] = useState('send_message');
  const [actionText, setActionText] = useState('');
  const [actionChannel, setActionChannel] = useState('');
  const [actionRole, setActionRole] = useState('');
  const [actionMinutes, setActionMinutes] = useState(10);
  const [busy, setBusy] = useState(false);

  const needsValue = trigger === 'message_contains' || trigger === 'reaction_add';
  const action = { type: actionType };
  if (actionType === 'send_message') { action.text = actionText; if (actionChannel) action.channel_id = actionChannel; }
  if (actionType === 'add_role' || actionType === 'remove_role') action.role_id = actionRole;
  if (actionType === 'timeout') action.minutes = actionMinutes;
  const valid = name.trim()
    && (!needsValue || trigger === 'reaction_add' || triggerValue.trim())
    && (actionType !== 'send_message' || actionText.trim())
    && ((actionType !== 'add_role' && actionType !== 'remove_role') || actionRole);

  async function add() {
    setBusy(true);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/workflows`, {
        name, trigger_type: trigger, trigger_value: triggerValue,
        channel_filter: channelFilter || null, actions: [action],
      });
      setName(''); setTriggerValue(''); setActionText('');
      await onChanged();
    } catch { /* surfaced on reload */ }
    setBusy(false);
  }

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>Workflows</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        When a trigger fires, the bot runs the action. Placeholders in messages: {'{user} {server} {channel}'}
      </Typography>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} useFlexGap flexWrap="wrap">
        <TextField size="small" label="Name" value={name} onChange={(e) => setName(e.target.value)} sx={{ minWidth: 160 }} />
        <TextField select size="small" label="Trigger" value={trigger} onChange={(e) => setTrigger(e.target.value)} sx={{ minWidth: 180 }}>
          {TRIGGERS.map((t) => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
        </TextField>
        {needsValue && (
          <TextField size="small" label={trigger === 'reaction_add' ? 'Emoji (blank = any)' : 'Keyword'}
            value={triggerValue} onChange={(e) => setTriggerValue(e.target.value)} sx={{ minWidth: 140 }} />
        )}
        <TextField select size="small" label="Only in channel" value={channelFilter}
          onChange={(e) => setChannelFilter(e.target.value)} sx={{ minWidth: 160 }}>
          <MenuItem value="">any channel</MenuItem>
          {channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Action" value={actionType}
          onChange={(e) => setActionType(e.target.value)} sx={{ minWidth: 170 }}>
          {ACTIONS.map((a) => <MenuItem key={a.value} value={a.value}>{a.label}</MenuItem>)}
        </TextField>
        {actionType === 'send_message' && (
          <>
            <TextField size="small" label="Message" value={actionText}
              onChange={(e) => setActionText(e.target.value)} sx={{ flex: 1, minWidth: 200 }} />
            <TextField select size="small" label="In channel" value={actionChannel}
              onChange={(e) => setActionChannel(e.target.value)} sx={{ minWidth: 160 }}>
              <MenuItem value="">same channel</MenuItem>
              {channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
            </TextField>
          </>
        )}
        {(actionType === 'add_role' || actionType === 'remove_role') && (
          <TextField select size="small" label="Role" value={actionRole}
            onChange={(e) => setActionRole(e.target.value)} sx={{ minWidth: 160 }}>
            {roles.map((r) => <MenuItem key={r.id} value={r.id}>{r.name}</MenuItem>)}
          </TextField>
        )}
        {actionType === 'timeout' && (
          <TextField type="number" size="small" label="Minutes" value={actionMinutes}
            inputProps={{ min: 1, max: 40320 }} onChange={(e) => setActionMinutes(Number(e.target.value))}
            sx={{ width: 110 }} />
        )}
        <Button startIcon={<Add />} variant="contained" size="small" disabled={busy || !valid} onClick={add}>
          Add
        </Button>
      </Stack>
      <List dense sx={{ mt: 1 }}>
        {workflows.map((w) => (
          <ListItem key={w.id} disableGutters
            secondaryAction={(
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Chip size="small" variant="outlined" label={`${w.runs_count} runs`} />
                <Switch size="small" checked={w.enabled}
                  onChange={(e) => guildizerApi.put(`/api/guilds/${guildId}/workflows/${w.id}`, { enabled: e.target.checked }).then(onChanged)} />
                <IconButton size="small" onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/workflows/${w.id}`).then(onChanged)}>
                  <Delete fontSize="small" />
                </IconButton>
              </Stack>
            )}>
            <ListItemText
              primary={w.name}
              secondary={`${w.trigger_type}${w.trigger_value ? ` "${w.trigger_value}"` : ''} → ${(w.actions || []).map((a) => a.type).join(', ')}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
        {workflows.length === 0 && <Typography variant="body2" color="text.secondary">No workflows yet.</Typography>}
      </List>
    </CardContent></Card>
  );
}

export function MirrorsCard({ guildId, mirrors, channels, onChanged }) {
  const [sourceId, setSourceId] = useState('');
  const [destId, setDestId] = useState('');
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/mirrors`, {
        source_channel_id: sourceId, dest_channel_id: destId.trim(),
      });
      setSourceId(''); setDestId('');
      await onChanged();
    } catch { /* surfaced on reload */ }
    setBusy(false);
  }

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>Channel mirroring</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Reposts messages to another channel via webhook, keeping the author's name and avatar.
        The destination can be in another server the bot is in (paste its channel ID).
      </Typography>
      <TextField select fullWidth size="small" margin="dense" label="Source channel"
        value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
        {channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
      </TextField>
      <TextField fullWidth size="small" margin="dense" label="Destination channel ID"
        value={destId} onChange={(e) => setDestId(e.target.value)} />
      <Button startIcon={<Add />} variant="contained" size="small" sx={{ mt: 1 }}
        disabled={busy || !sourceId || !/^\d+$/.test(destId.trim())} onClick={add}>
        Add mirror
      </Button>
      <List dense sx={{ mt: 1 }}>
        {mirrors.map((m) => (
          <ListItem key={m.id} disableGutters
            secondaryAction={(
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Switch size="small" checked={m.enabled}
                  onChange={(e) => guildizerApi.put(`/api/guilds/${guildId}/mirrors/${m.id}`, { enabled: e.target.checked }).then(onChanged)} />
                <IconButton size="small" onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/mirrors/${m.id}`).then(onChanged)}>
                  <Delete fontSize="small" />
                </IconButton>
              </Stack>
            )}>
            <ListItemText
              primary={`${m.source_channel_id} → ${m.dest_channel_id}`}
              secondary={m.last_error ? `⚠ ${m.last_error}` : `${m.mirrored_count} mirrored`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
        {mirrors.length === 0 && <Typography variant="body2" color="text.secondary">No mirrors yet.</Typography>}
      </List>
    </CardContent></Card>
  );
}

export function WebhooksCard({ guildId, inbound, outbound, channels, onChanged }) {
  const [inName, setInName] = useState('');
  const [inChannel, setInChannel] = useState('');
  const [outUrl, setOutUrl] = useState('');
  const [outEvents, setOutEvents] = useState(['member_join', 'member_leave']);
  const [outSecret, setOutSecret] = useState('');
  const [busy, setBusy] = useState(false);

  async function addInbound() {
    setBusy(true);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/inbound-webhooks`, { name: inName, channel_id: inChannel });
      setInName('');
      await onChanged();
    } catch { /* surfaced on reload */ }
    setBusy(false);
  }

  async function addOutbound() {
    setBusy(true);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/outbound-webhooks`, {
        url: outUrl, events: outEvents, secret: outSecret,
      });
      setOutUrl(''); setOutSecret('');
      await onChanged();
    } catch { /* surfaced on reload */ }
    setBusy(false);
  }

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>Webhooks</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Receive external POSTs into a channel, or forward server events to your own URL.
      </Typography>

      <Typography variant="subtitle2" fontWeight={700}>Inbound (POST → channel)</Typography>
      <Stack direction="row" spacing={1} alignItems="center">
        <TextField size="small" margin="dense" label="Name" value={inName}
          onChange={(e) => setInName(e.target.value)} sx={{ flex: 1 }} />
        <TextField select size="small" margin="dense" label="Channel" value={inChannel}
          onChange={(e) => setInChannel(e.target.value)} sx={{ minWidth: 150 }}>
          {channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
        </TextField>
        <Button size="small" variant="contained" disabled={busy || !inChannel} onClick={addInbound}>Create</Button>
      </Stack>
      <List dense>
        {inbound.map((h) => (
          <ListItem key={h.id} disableGutters
            secondaryAction={(
              <Stack direction="row" spacing={0.5}>
                <Tooltip title="Copy URL">
                  <IconButton size="small" onClick={() => navigator.clipboard.writeText(h.url)}>
                    <ContentCopy fontSize="small" />
                  </IconButton>
                </Tooltip>
                <IconButton size="small" onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/inbound-webhooks/${h.id}`).then(onChanged)}>
                  <Delete fontSize="small" />
                </IconButton>
              </Stack>
            )}>
            <ListItemText primary={h.name} secondary={`${h.received_count} received · POST {"content": "…"}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
      </List>

      <Typography variant="subtitle2" fontWeight={700} mt={1}>Outbound (events → your URL)</Typography>
      <TextField fullWidth size="small" margin="dense" label="URL" value={outUrl}
        onChange={(e) => setOutUrl(e.target.value)} />
      <Stack direction="row" useFlexGap flexWrap="wrap">
        {OUT_EVENTS.map((ev) => (
          <FormControlLabel key={ev} control={(
            <Checkbox size="small" checked={outEvents.includes(ev)}
              onChange={(e) => setOutEvents((cur) => e.target.checked ? [...cur, ev] : cur.filter((x) => x !== ev))} />
          )} label={<Typography variant="caption">{ev}</Typography>} />
        ))}
      </Stack>
      <Stack direction="row" spacing={1} alignItems="center">
        <TextField size="small" margin="dense" label="HMAC secret (optional)" value={outSecret}
          onChange={(e) => setOutSecret(e.target.value)} sx={{ flex: 1 }} />
        <Button size="small" variant="contained" disabled={busy || !/^https?:\/\//.test(outUrl)} onClick={addOutbound}>
          Add
        </Button>
      </Stack>
      <List dense>
        {outbound.map((h) => (
          <ListItem key={h.id} disableGutters
            secondaryAction={(
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Switch size="small" checked={h.enabled}
                  onChange={(e) => guildizerApi.put(`/api/guilds/${guildId}/outbound-webhooks/${h.id}`, { enabled: e.target.checked }).then(onChanged)} />
                <IconButton size="small" onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/outbound-webhooks/${h.id}`).then(onChanged)}>
                  <Delete fontSize="small" />
                </IconButton>
              </Stack>
            )}>
            <ListItemText primary={h.url}
              secondary={`${(h.events || []).join(', ') || 'all events'} · ${h.delivered_count} delivered${h.last_error ? ` · ⚠ ${h.last_error}` : ''}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
      </List>
    </CardContent></Card>
  );
}
