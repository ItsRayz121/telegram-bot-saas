import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Grid, Typography, TextField, MenuItem, Button, Chip,
  CircularProgress, Alert, List, ListItem, ListItemText, Stack, Switch,
  FormControlLabel, IconButton, Tooltip,
} from '@mui/material';
import { Delete, Add, Send, Edit as EditIcon, StopCircle } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';

const TEXT_TYPES = new Set([0, 5]);
const STATUS_COLOR = { draft: 'default', pending: 'warning', scheduled: 'info', open: 'info', ended: 'success', failed: 'error' };
const POLL_STATUS_LABEL = { pending: 'posting…', scheduled: 'scheduled', draft: 'draft', open: 'live', ended: 'ended', failed: 'failed' };

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
  const [msg, setMsg] = useState(null);  // { ok, text }

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/digest`).then(({ data }) => setCfg(data)).catch(() => {});
  }, [guildId]);

  if (!cfg) return null;
  // Edit locally; persist explicitly with Save so failures surface (auto-save
  // used to swallow errors and silently revert on the next load).
  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/digest`, {
        enabled: cfg.enabled, channel_id: cfg.channel_id, cadence: cfg.cadence,
        weekday: cfg.weekday, hour_utc: cfg.hour_utc,
      });
      setCfg(data);
      setMsg({ ok: true, text: 'Saved' });
    } catch {
      setMsg({ ok: false, text: 'Could not save the digest settings.' });
    }
    setBusy(false);
  };

  const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const cadence = cfg.cadence || 'daily';
  return (
    <GuildizerCollapsibleCard id="members.content.activity_digest" title="Activity digest">
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Posts an activity summary on your chosen cadence (AI-polished when an AI key is configured).
      </Typography>
      <FormControlLabel control={<Switch checked={!!cfg.enabled}
        onChange={(e) => set({ enabled: e.target.checked })} />} label="Enable activity digest" />
      <TextField select fullWidth size="small" margin="dense" label="Channel"
        value={cfg.channel_id || ''} onChange={(e) => set({ channel_id: e.target.value || null })}>
        {channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
      </TextField>
      <TextField select fullWidth size="small" margin="dense" label="Cadence"
        value={cadence} onChange={(e) => set({ cadence: e.target.value })}>
        <MenuItem value="daily">Daily</MenuItem>
        <MenuItem value="weekly">Weekly</MenuItem>
        <MenuItem value="monthly">Monthly (1st of the month)</MenuItem>
      </TextField>
      {cadence === 'weekly' && (
        <TextField select fullWidth size="small" margin="dense" label="Day of week"
          value={cfg.weekday ?? 0} onChange={(e) => set({ weekday: Number(e.target.value) })}>
          {WEEKDAYS.map((d, i) => <MenuItem key={d} value={i}>{d}</MenuItem>)}
        </TextField>
      )}
      <TextField type="number" fullWidth size="small" margin="dense" label="Post after (UTC hour)"
        value={cfg.hour_utc ?? 18} inputProps={{ min: 0, max: 23 }}
        onChange={(e) => set({ hour_utc: Number(e.target.value) })} />
      {msg && <Alert severity={msg.ok ? 'success' : 'error'} sx={{ mt: 1, py: 0 }}>{msg.text}</Alert>}
      <Button variant="contained" size="small" sx={{ mt: 1 }} disabled={busy} onClick={save}>
        {busy ? 'Saving…' : 'Save'}
      </Button>
    </GuildizerCollapsibleCard>
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
  const [editingId, setEditingId] = useState(null);

  const setEm = (patch) => setEmbed((e) => ({ ...e, ...patch }));
  const embedHasContent = !!(embed.title.trim() || embed.description.trim()
    || embed.image_url.trim() || embed.thumbnail_url.trim() || embed.footer.trim());

  function reset() {
    setEditingId(null); setContent(''); setWhen(''); setChannelId('');
    setRecurrence('none'); setEmbed(EMPTY_EMBED); setWithEmbed(false);
  }
  function startEdit(m) {
    setEditingId(m.id);
    setContent(m.content || ''); setChannelId(m.channel_id || '');
    setWhen(m.next_run_at ? toLocalInput(m.next_run_at) : '');
    setRecurrence(m.recurrence || 'none');
    setWithEmbed(!!m.embed); setEmbed(m.embed ? { ...EMPTY_EMBED, ...m.embed } : EMPTY_EMBED);
  }

  async function add() {
    setBusy(true);
    const payload = {
      content, channel_id: channelId, recurrence,
      next_run_at: new Date(when).toISOString(),
      embed: withEmbed && embedHasContent ? embed : null,
    };
    try {
      if (editingId) await guildizerApi.put(`/api/guilds/${guildId}/scheduled-messages/${editingId}`, payload);
      else await guildizerApi.post(`/api/guilds/${guildId}/scheduled-messages`, payload);
      reset();
      await onChanged();
    } catch { /* parent shows errors on reload */ }
    setBusy(false);
  }

  return (
    <GuildizerCollapsibleCard id="members.content.scheduled_messages" title="Scheduled messages">
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
      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
        <Button startIcon={editingId ? <EditIcon /> : <Add />} variant="contained" size="small"
          disabled={busy || (!content.trim() && !(withEmbed && embedHasContent)) || !channelId || !when} onClick={add}>
          {editingId ? 'Save changes' : 'Schedule'}
        </Button>
        {editingId && <Button size="small" color="inherit" onClick={reset}>Cancel</Button>}
      </Stack>
      <List dense sx={{ mt: 1 }}>
        {messages.map((m) => (
          <ListItem key={m.id} disableGutters sx={{ gap: 1, alignItems: 'center' }}>
            <ListItemText
              sx={{ my: 0, minWidth: 0 }}
              primary={m.content || m.embed?.title || m.embed?.description || '(embed)'}
              secondary={`${m.embed ? 'embed · ' : ''}${m.recurrence !== 'none' ? `${m.recurrence} · ` : ''}next: ${m.next_run_at ? new Date(m.next_run_at).toLocaleString() : '—'}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }}
              secondaryTypographyProps={{ variant: 'caption', noWrap: true }} />
            <Stack direction="row" spacing={0.25} alignItems="center" sx={{ flexShrink: 0 }}>
              <Switch size="small" checked={m.enabled}
                onChange={(e) => guildizerApi.put(`/api/guilds/${guildId}/scheduled-messages/${m.id}`, { enabled: e.target.checked }).then(onChanged)} />
              <IconButton size="small" onClick={() => startEdit(m)}><EditIcon fontSize="small" /></IconButton>
              <IconButton size="small" color="error" onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/scheduled-messages/${m.id}`).then(onChanged)}>
                <Delete fontSize="small" />
              </IconButton>
            </Stack>
          </ListItem>
        ))}
        {messages.length === 0 && <Typography variant="body2" color="text.secondary">Nothing scheduled.</Typography>}
      </List>
    </GuildizerCollapsibleCard>
  );
}

const EMPTY_POLL_FORM = { question: '', answers: ['', ''], channelId: '', duration: 24, multiselect: false, mode: 'now', scheduledAt: '' };

export function PollsCard({ guildId, polls, channels, onChanged }) {
  const [form, setForm] = useState(EMPTY_POLL_FORM);
  const [editingId, setEditingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const setAnswer = (i, val) => setForm((f) => ({ ...f, answers: f.answers.map((a, j) => (j === i ? val : a)) }));
  const addAnswer = () => setForm((f) => (f.answers.length >= 10 ? f : { ...f, answers: [...f.answers, ''] }));
  const removeAnswer = (i) => setForm((f) => (f.answers.length <= 2 ? f : { ...f, answers: f.answers.filter((_, j) => j !== i) }));
  const reset = () => { setForm(EMPTY_POLL_FORM); setEditingId(null); setError(null); };

  const cleanAnswers = form.answers.map((a) => a.trim()).filter(Boolean);
  const canSubmit = form.question.trim() && cleanAnswers.length >= 2 && form.channelId
    && (form.mode !== 'schedule' || form.scheduledAt);

  async function submit() {
    setBusy(true); setError(null);
    const payload = {
      question: form.question, answers: cleanAnswers, channel_id: form.channelId,
      duration_hours: form.duration, multiselect: form.multiselect, mode: form.mode,
      scheduled_at: form.mode === 'schedule' && form.scheduledAt ? new Date(form.scheduledAt).toISOString() : null,
    };
    try {
      if (editingId) await guildizerApi.put(`/api/guilds/${guildId}/polls/${editingId}`, payload);
      else await guildizerApi.post(`/api/guilds/${guildId}/polls`, payload);
      reset();
      await onChanged();
    } catch { setError('Could not save the poll — check the question, at least 2 answers, and a channel.'); }
    setBusy(false);
  }

  function startEdit(p) {
    setEditingId(p.id);
    setError(null);
    const ans = (p.answers || []).slice();
    while (ans.length < 2) ans.push('');
    setForm({
      question: p.question || '', answers: ans, channelId: p.channel_id || '',
      duration: p.duration_hours || 24, multiselect: !!p.multiselect,
      mode: p.status === 'draft' ? 'draft' : p.status === 'scheduled' ? 'schedule' : 'now',
      scheduledAt: p.scheduled_at ? toLocalInput(p.scheduled_at) : '',
    });
  }

  const act = (id, verb) => guildizerApi.post(`/api/guilds/${guildId}/polls/${id}/${verb}`).then(onChanged).catch(() => {});
  const del = (id) => guildizerApi.delete(`/api/guilds/${guildId}/polls/${id}`).then(onChanged).catch(() => {});

  const submitLabel = editingId ? 'Save changes'
    : form.mode === 'draft' ? 'Save draft'
    : form.mode === 'schedule' ? 'Schedule poll' : 'Post poll';

  return (
    <GuildizerCollapsibleCard id="members.content.polls_native" title="Polls (native)">
      <Typography variant="body2" color="text.secondary" mb={2}>
        Post a native Discord poll with timed voting and optional multiple choice.
        Post it now, schedule it for later, or save it as a draft.
      </Typography>
      <TextField fullWidth size="small" margin="dense" label="Question"
        value={form.question} inputProps={{ maxLength: 300 }} onChange={(e) => set({ question: e.target.value })} />

      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
        Answers (2–10)
      </Typography>
      {form.answers.map((a, i) => (
        <Stack key={i} direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
          <TextField fullWidth size="small" label={`Option ${i + 1}`} value={a}
            inputProps={{ maxLength: 55 }} onChange={(e) => setAnswer(i, e.target.value)} />
          <IconButton size="small" disabled={form.answers.length <= 2} onClick={() => removeAnswer(i)} title="Remove option">
            <Delete fontSize="small" />
          </IconButton>
        </Stack>
      ))}
      <Button size="small" startIcon={<Add />} disabled={form.answers.length >= 10} onClick={addAnswer} sx={{ mt: 0.5 }}>
        Add option
      </Button>

      <TextField select fullWidth size="small" margin="dense" label="Channel"
        value={form.channelId} onChange={(e) => set({ channelId: e.target.value })}>
        {channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
      </TextField>
      <Stack direction="row" spacing={1} alignItems="center">
        <TextField type="number" size="small" margin="dense" label="Duration (hours)"
          value={form.duration} inputProps={{ min: 1, max: 768 }}
          onChange={(e) => set({ duration: Number(e.target.value) })} sx={{ width: 150 }} />
        <FormControlLabel control={<Switch checked={form.multiselect} onChange={(e) => set({ multiselect: e.target.checked })} />}
          label="Multiple choice" />
      </Stack>

      <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
        <TextField select size="small" margin="dense" label="When" value={form.mode}
          onChange={(e) => set({ mode: e.target.value })} sx={{ minWidth: 150 }}>
          <MenuItem value="now">Post now</MenuItem>
          <MenuItem value="schedule">Schedule</MenuItem>
          <MenuItem value="draft">Save as draft</MenuItem>
        </TextField>
        {form.mode === 'schedule' && (
          <TextField type="datetime-local" size="small" margin="dense" label="Post at"
            InputLabelProps={{ shrink: true }} value={form.scheduledAt}
            onChange={(e) => set({ scheduledAt: e.target.value })} sx={{ flex: 1 }} />
        )}
      </Stack>

      {error && <Alert severity="error" sx={{ mt: 1, py: 0 }}>{error}</Alert>}
      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
        <Button startIcon={editingId ? null : <Add />} variant="contained" size="small"
          disabled={busy || !canSubmit} onClick={submit}>
          {busy ? 'Saving…' : submitLabel}
        </Button>
        {editingId && <Button size="small" onClick={reset} disabled={busy}>Cancel</Button>}
      </Stack>

      <List dense sx={{ mt: 1 }}>
        {polls.map((p) => (
          <ListItem key={p.id} disableGutters sx={{ gap: 1, alignItems: 'flex-start' }}>
            <Chip size="small" variant="outlined" label={POLL_STATUS_LABEL[p.status] || p.status}
              color={STATUS_COLOR[p.status] || 'default'} sx={{ flexShrink: 0, mt: 0.3 }} />
            <ListItemText
              sx={{ my: 0, minWidth: 0 }}
              primary={p.question}
              secondary={p.status === 'ended'
                ? (Object.entries(p.results || {}).map(([a, v]) => `${a}: ${v}`).join(' · ') || 'no votes')
                : p.status === 'scheduled' && p.scheduled_at
                  ? `${(p.answers || []).length} options · posts ${new Date(p.scheduled_at).toLocaleString()}`
                  : `${(p.answers || []).length} options${p.ends_at ? ` · ends ${new Date(p.ends_at).toLocaleString()}` : ''}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }}
              secondaryTypographyProps={{ variant: 'caption', sx: { wordBreak: 'break-word' } }} />
            <Stack direction="row" spacing={0.25} alignItems="center" sx={{ flexShrink: 0 }}>
              {(p.status === 'draft' || p.status === 'scheduled') && (
                <Tooltip title="Post now"><IconButton size="small" color="primary" onClick={() => act(p.id, 'post')}><Send fontSize="small" /></IconButton></Tooltip>
              )}
              {['draft', 'pending', 'scheduled'].includes(p.status) && (
                <Tooltip title="Edit"><IconButton size="small" onClick={() => startEdit(p)}><EditIcon fontSize="small" /></IconButton></Tooltip>
              )}
              {p.status === 'open' && (
                <Tooltip title="End poll now"><IconButton size="small" color="warning" onClick={() => act(p.id, 'end')}><StopCircle fontSize="small" /></IconButton></Tooltip>
              )}
              {p.status !== 'open' && (
                <IconButton size="small" color="error" onClick={() => del(p.id)} title="Delete"><Delete fontSize="small" /></IconButton>
              )}
            </Stack>
          </ListItem>
        ))}
        {polls.length === 0 && <Typography variant="body2" color="text.secondary">No polls yet.</Typography>}
      </List>
    </GuildizerCollapsibleCard>
  );
}

// datetime-local needs "YYYY-MM-DDTHH:mm" in *local* time; convert from a stored ISO/UTC string.
function toLocalInput(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function AutoResponsesCard({ guildId, responses, onChanged }) {
  const [trigger, setTrigger] = useState('');
  const [response, setResponse] = useState('');
  const [matchType, setMatchType] = useState('contains');
  const [asKnowledge, setAsKnowledge] = useState(false);
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/auto-responses`, {
        trigger, response, match_type: matchType, use_as_ai_knowledge: asKnowledge,
      });
      setTrigger(''); setResponse(''); setAsKnowledge(false);
      await onChanged();
    } catch { /* parent shows errors on reload */ }
    setBusy(false);
  }

  return (
    <GuildizerCollapsibleCard id="members.content.auto_responses" title="Auto-responses">
      <Typography variant="body2" color="text.secondary" mb={2}>
        Automatically reply when a message matches a trigger phrase. Flag one as
        <b> AI knowledge</b> and the /ask AI can also answer related questions from it.
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
      <FormControlLabel sx={{ mt: 0.5 }}
        control={<Switch size="small" checked={asKnowledge} onChange={(e) => setAsKnowledge(e.target.checked)} />}
        label={<Typography variant="body2">Use as AI knowledge for /ask</Typography>} />
      <List dense sx={{ mt: 1 }}>
        {responses.map((r) => (
          <ListItem key={r.id} disableGutters sx={{ gap: 1, alignItems: 'center' }}>
            <ListItemText
              sx={{ my: 0, minWidth: 0 }}
              primary={`"${r.trigger}" (${r.match_type}) → ${r.response}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
            <Stack direction="row" spacing={0.5} alignItems="center" sx={{ flexShrink: 0 }}>
              <Tooltip title="Let the /ask AI answer from this trigger">
                <Chip size="small" label="AI" clickable
                  color={r.use_as_ai_knowledge ? 'primary' : 'default'}
                  variant={r.use_as_ai_knowledge ? 'filled' : 'outlined'}
                  onClick={() => guildizerApi.put(`/api/guilds/${guildId}/auto-responses/${r.id}`, { use_as_ai_knowledge: !r.use_as_ai_knowledge }).then(onChanged)}
                  sx={{ height: 20, fontSize: '0.65rem' }} />
              </Tooltip>
              <Switch size="small" checked={r.enabled}
                onChange={(e) => guildizerApi.put(`/api/guilds/${guildId}/auto-responses/${r.id}`, { enabled: e.target.checked }).then(onChanged)} />
              <IconButton size="small" color="error" onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/auto-responses/${r.id}`).then(onChanged)}>
                <Delete fontSize="small" />
              </IconButton>
            </Stack>
          </ListItem>
        ))}
        {responses.length === 0 && <Typography variant="body2" color="text.secondary">No auto-responses yet.</Typography>}
      </List>
    </GuildizerCollapsibleCard>
  );
}
