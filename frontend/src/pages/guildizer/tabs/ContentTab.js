import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, TextField, MenuItem, Button, Chip,
  CircularProgress, Alert, List, ListItem, ListItemText, Stack, Switch,
  FormControlLabel, IconButton,
} from '@mui/material';
import { Delete, Add } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const TEXT_TYPES = new Set([0, 5]);
const STATUS_COLOR = { pending: 'default', open: 'info', ended: 'success', failed: 'error' };

export default function ContentTab({ guildId, channels = [] }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([]);
  const [polls, setPolls] = useState([]);
  const [responses, setResponses] = useState([]);

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));

  const reload = useCallback(async () => {
    try {
      const [m, p, r] = await Promise.all([
        guildizerApi.get(`/api/guilds/${guildId}/scheduled-messages`),
        guildizerApi.get(`/api/guilds/${guildId}/polls`),
        guildizerApi.get(`/api/guilds/${guildId}/auto-responses`),
      ]);
      setMessages(m.data.messages); setPolls(p.data.polls); setResponses(r.data.responses);
      setError(null);
    } catch { setError('Failed to load content settings.'); }
    setLoading(false);
  }, [guildId]);

  useEffect(() => { reload(); }, [reload]);

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Grid container spacing={2}>
      {error && <Grid item xs={12}><Alert severity="warning" onClose={() => setError(null)}>{error}</Alert></Grid>}

      <Grid item xs={12}>
        <SchedulerCard guildId={guildId} messages={messages} channels={textChannels} onChanged={reload} />
      </Grid>
      <Grid item xs={12}>
        <PollsCard guildId={guildId} polls={polls} channels={textChannels} onChanged={reload} />
      </Grid>
      <Grid item xs={12}>
        <DigestCard guildId={guildId} channels={textChannels} />
      </Grid>
      <Grid item xs={12}>
        <AutoResponsesCard guildId={guildId} responses={responses} onChanged={reload} />
      </Grid>
    </Grid>
  );
}

export function DigestCard({ guildId, channels }) {
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/digest`).then(({ data }) => setCfg(data)).catch(() => {});
  }, [guildId]);

  if (!cfg) return null;
  const save = async (patch) => {
    setBusy(true);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/digest`, { ...cfg, ...patch });
      setCfg(data);
    } catch { /* leave as-is */ }
    setBusy(false);
  };

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>Daily digest</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Posts a daily activity summary (AI-polished when an AI key is configured).
      </Typography>
      <FormControlLabel control={<Switch checked={!!cfg.enabled} disabled={busy}
        onChange={(e) => save({ enabled: e.target.checked })} />} label="Enable daily digest" />
      <TextField select fullWidth size="small" margin="dense" label="Channel"
        value={cfg.channel_id || ''} onChange={(e) => save({ channel_id: e.target.value || null })}>
        {channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
      </TextField>
      <TextField type="number" fullWidth size="small" margin="dense" label="Post after (UTC hour)"
        value={cfg.hour_utc ?? 18} inputProps={{ min: 0, max: 23 }}
        onChange={(e) => save({ hour_utc: Number(e.target.value) })} />
    </CardContent></Card>
  );
}

const EMPTY_EMBED = { title: '', description: '', color: '#5865F2', image_url: '', thumbnail_url: '', footer: '' };

export function SchedulerCard({ guildId, messages, channels, onChanged }) {
  const [content, setContent] = useState('');
  const [channelId, setChannelId] = useState('');
  const [when, setWhen] = useState('');
  const [recurrence, setRecurrence] = useState('none');
  const [withEmbed, setWithEmbed] = useState(false);
  const [embed, setEmbed] = useState(EMPTY_EMBED);
  const [busy, setBusy] = useState(false);

  const setEm = (patch) => setEmbed((e) => ({ ...e, ...patch }));
  const embedHasContent = !!(embed.title.trim() || embed.description.trim()
    || embed.image_url.trim() || embed.thumbnail_url.trim() || embed.footer.trim());

  async function add() {
    setBusy(true);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/scheduled-messages`, {
        content, channel_id: channelId, recurrence,
        next_run_at: new Date(when).toISOString(),
        embed: withEmbed && embedHasContent ? embed : null,
      });
      setContent(''); setWhen(''); setEmbed(EMPTY_EMBED); setWithEmbed(false);
      await onChanged();
    } catch { /* parent shows errors on reload */ }
    setBusy(false);
  }

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>Scheduled messages</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Queue one-off or recurring posts to a channel, optionally with a rich embed.
      </Typography>
      <TextField fullWidth multiline minRows={2} size="small" margin="dense" label="Message"
        value={content} inputProps={{ maxLength: 2000 }} onChange={(e) => setContent(e.target.value)} />
      <TextField select fullWidth size="small" margin="dense" label="Channel"
        value={channelId} onChange={(e) => setChannelId(e.target.value)}>
        {channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
      </TextField>
      <Stack direction="row" spacing={1}>
        <TextField type="datetime-local" size="small" margin="dense" label="First run"
          InputLabelProps={{ shrink: true }} value={when} onChange={(e) => setWhen(e.target.value)} sx={{ flex: 1 }} />
        <TextField select size="small" margin="dense" label="Repeat" value={recurrence}
          onChange={(e) => setRecurrence(e.target.value)} sx={{ minWidth: 120 }}>
          {['none', 'hourly', 'daily', 'weekly'].map((r) => <MenuItem key={r} value={r}>{r}</MenuItem>)}
        </TextField>
      </Stack>
      <FormControlLabel control={<Switch size="small" checked={withEmbed} onChange={(e) => setWithEmbed(e.target.checked)} />}
        label={<Typography variant="body2">Add a rich embed</Typography>} />
      {withEmbed && (
        <Box sx={{ pl: 1, borderLeft: '3px solid', borderColor: 'divider', mb: 1 }}>
          <TextField fullWidth size="small" margin="dense" label="Embed title"
            value={embed.title} inputProps={{ maxLength: 256 }} onChange={(e) => setEm({ title: e.target.value })} />
          <TextField fullWidth multiline minRows={2} size="small" margin="dense" label="Embed text"
            value={embed.description} inputProps={{ maxLength: 4000 }} onChange={(e) => setEm({ description: e.target.value })} />
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField type="color" size="small" margin="dense" label="Accent" value={embed.color}
              onChange={(e) => setEm({ color: e.target.value })} sx={{ width: 90 }} InputLabelProps={{ shrink: true }} />
            <TextField size="small" margin="dense" label="Footer" value={embed.footer}
              inputProps={{ maxLength: 2048 }} onChange={(e) => setEm({ footer: e.target.value })} sx={{ flex: 1 }} />
          </Stack>
          <TextField fullWidth size="small" margin="dense" label="Image URL (https://…)"
            value={embed.image_url} onChange={(e) => setEm({ image_url: e.target.value })} />
          <TextField fullWidth size="small" margin="dense" label="Thumbnail URL (https://…)"
            value={embed.thumbnail_url} onChange={(e) => setEm({ thumbnail_url: e.target.value })} />
        </Box>
      )}
      <Button startIcon={<Add />} variant="contained" size="small" sx={{ mt: 1 }}
        disabled={busy || (!content.trim() && !(withEmbed && embedHasContent)) || !channelId || !when} onClick={add}>
        Schedule
      </Button>
      <List dense sx={{ mt: 1 }}>
        {messages.map((m) => (
          <ListItem key={m.id} disableGutters
            secondaryAction={(
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Switch size="small" checked={m.enabled}
                  onChange={(e) => guildizerApi.put(`/api/guilds/${guildId}/scheduled-messages/${m.id}`, { enabled: e.target.checked }).then(onChanged)} />
                <IconButton size="small" onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/scheduled-messages/${m.id}`).then(onChanged)}>
                  <Delete fontSize="small" />
                </IconButton>
              </Stack>
            )}>
            <ListItemText
              primary={m.content || m.embed?.title || m.embed?.description || '(embed)'}
              secondary={`${m.embed ? 'embed · ' : ''}${m.recurrence !== 'none' ? `${m.recurrence} · ` : ''}next: ${m.next_run_at ? new Date(m.next_run_at).toLocaleString() : '—'}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
        {messages.length === 0 && <Typography variant="body2" color="text.secondary">Nothing scheduled.</Typography>}
      </List>
    </CardContent></Card>
  );
}

export function PollsCard({ guildId, polls, channels, onChanged }) {
  const [question, setQuestion] = useState('');
  const [answersText, setAnswersText] = useState('');
  const [channelId, setChannelId] = useState('');
  const [duration, setDuration] = useState(24);
  const [multiselect, setMultiselect] = useState(false);
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/polls`, {
        question, channel_id: channelId, duration_hours: duration, multiselect,
        answers: answersText.split('\n').map((a) => a.trim()).filter(Boolean),
      });
      setQuestion(''); setAnswersText('');
      await onChanged();
    } catch { /* parent shows errors on reload */ }
    setBusy(false);
  }

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>Polls (native)</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Post a native Discord poll with timed voting and optional multiple choice.
      </Typography>
      <TextField fullWidth size="small" margin="dense" label="Question"
        value={question} inputProps={{ maxLength: 300 }} onChange={(e) => setQuestion(e.target.value)} />
      <TextField fullWidth multiline minRows={2} size="small" margin="dense"
        label="Answers (one per line, 2–10)"
        value={answersText} onChange={(e) => setAnswersText(e.target.value)} />
      <TextField select fullWidth size="small" margin="dense" label="Channel"
        value={channelId} onChange={(e) => setChannelId(e.target.value)}>
        {channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
      </TextField>
      <Stack direction="row" spacing={1} alignItems="center">
        <TextField type="number" size="small" margin="dense" label="Duration (hours)"
          value={duration} inputProps={{ min: 1, max: 768 }}
          onChange={(e) => setDuration(Number(e.target.value))} sx={{ width: 150 }} />
        <FormControlLabel control={<Switch checked={multiselect} onChange={(e) => setMultiselect(e.target.checked)} />}
          label="Multiple choice" />
      </Stack>
      <Button startIcon={<Add />} variant="contained" size="small" sx={{ mt: 1 }}
        disabled={busy || !question.trim() || !channelId} onClick={add}>
        Post poll
      </Button>
      <List dense sx={{ mt: 1 }}>
        {polls.map((p) => (
          <ListItem key={p.id} disableGutters
            secondaryAction={p.status !== 'open' && (
              <IconButton size="small" onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/polls/${p.id}`).then(onChanged)}>
                <Delete fontSize="small" />
              </IconButton>
            )}>
            <Chip size="small" variant="outlined" label={p.status} color={STATUS_COLOR[p.status] || 'default'} sx={{ mr: 1 }} />
            <ListItemText
              primary={p.question}
              secondary={p.status === 'ended'
                ? Object.entries(p.results || {}).map(([a, v]) => `${a}: ${v}`).join(' · ') || 'no votes'
                : `${(p.answers || []).length} options${p.ends_at ? ` · ends ${new Date(p.ends_at).toLocaleString()}` : ''}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
        {polls.length === 0 && <Typography variant="body2" color="text.secondary">No polls yet.</Typography>}
      </List>
    </CardContent></Card>
  );
}

export function AutoResponsesCard({ guildId, responses, onChanged }) {
  const [trigger, setTrigger] = useState('');
  const [response, setResponse] = useState('');
  const [matchType, setMatchType] = useState('contains');
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/auto-responses`, {
        trigger, response, match_type: matchType,
      });
      setTrigger(''); setResponse('');
      await onChanged();
    } catch { /* parent shows errors on reload */ }
    setBusy(false);
  }

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>Auto-responses</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Automatically reply when a message matches a trigger phrase.
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField size="small" margin="dense" label="Trigger" value={trigger}
          inputProps={{ maxLength: 120 }} onChange={(e) => setTrigger(e.target.value)} sx={{ flex: 1 }} />
        <TextField select size="small" margin="dense" label="Match" value={matchType}
          onChange={(e) => setMatchType(e.target.value)} sx={{ minWidth: 130 }}>
          <MenuItem value="contains">contains</MenuItem>
          <MenuItem value="exact">exact message</MenuItem>
        </TextField>
        <TextField size="small" margin="dense" label="Reply" value={response}
          inputProps={{ maxLength: 2000 }} onChange={(e) => setResponse(e.target.value)} sx={{ flex: 2 }} />
        <Button startIcon={<Add />} variant="contained" size="small" sx={{ mt: 1 }}
          disabled={busy || !trigger.trim() || !response.trim()} onClick={add}>
          Add
        </Button>
      </Stack>
      <List dense sx={{ mt: 1 }}>
        {responses.map((r) => (
          <ListItem key={r.id} disableGutters
            secondaryAction={(
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Switch size="small" checked={r.enabled}
                  onChange={(e) => guildizerApi.put(`/api/guilds/${guildId}/auto-responses/${r.id}`, { enabled: e.target.checked }).then(onChanged)} />
                <IconButton size="small" onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/auto-responses/${r.id}`).then(onChanged)}>
                  <Delete fontSize="small" />
                </IconButton>
              </Stack>
            )}>
            <ListItemText
              primary={`"${r.trigger}" (${r.match_type}) → ${r.response}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
        {responses.length === 0 && <Typography variant="body2" color="text.secondary">No auto-responses yet.</Typography>}
      </List>
    </CardContent></Card>
  );
}
