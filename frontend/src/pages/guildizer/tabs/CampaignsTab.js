import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Button, TextField, MenuItem, Switch,
  FormControlLabel, List, ListItem, ListItemText, IconButton, Chip, Alert,
  CircularProgress, Stack, Divider,
} from '@mui/material';
import { Add, Delete, ArrowBack } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const TEXT_TYPES = new Set([0, 5]);
const TYPES = ['proof_collection', 'content_submission', 'social_task', 'raid'];
const VMODES = ['manual', 'honor', 'link'];
const STATUS_COLOR = { draft: 'default', active: 'success', paused: 'warning', closed: 'default' };

export default function CampaignsTab({ guildId, channels = [] }) {
  const [campaigns, setCampaigns] = useState([]);
  const [plan, setPlan] = useState('free');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));

  async function load() {
    setLoading(true);
    try { const { data } = await guildizerApi.get(`/api/guilds/${guildId}/campaigns`); setCampaigns(data.campaigns); setPlan(data.plan); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [guildId]);

  if (selected) return <CampaignDetail guildId={guildId} campaignId={selected} channels={textChannels} plan={plan} onBack={() => { setSelected(null); load(); }} />;

  return (
    <Card variant="outlined"><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="subtitle1" fontWeight={700}>Campaigns</Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => setCreating((v) => !v)}>{creating ? 'Close' : 'New campaign'}</Button>
      </Stack>

      {creating && <CreateForm guildId={guildId} channels={textChannels} onCreated={() => { setCreating(false); load(); }} />}

      {loading ? <Box sx={{ display: 'grid', placeItems: 'center', py: 3 }}><CircularProgress /></Box> : (
        <>
          {campaigns.length === 0 && <Typography variant="body2" color="text.secondary">No campaigns yet.</Typography>}
          <List dense>
            {campaigns.map((c) => (
              <ListItem key={c.id} button onClick={() => setSelected(c.id)} divider
                secondaryAction={<Typography variant="caption" color="text.secondary">{c.counts.verified}✓ / {c.counts.pending}⏳</Typography>}>
                <Chip size="small" label={c.status} color={STATUS_COLOR[c.status]} sx={{ mr: 1.5 }} />
                <ListItemText primary={c.title} secondary={`${c.task_count} tasks`} />
              </ListItem>
            ))}
          </List>
          {plan !== 'pro' && <Typography variant="caption" color="text.disabled" display="block" mt={1}>Free plan: 1 active campaign. Campaign leaderboards are Pro.</Typography>}
        </>
      )}
    </CardContent></Card>
  );
}

function CreateForm({ guildId, channels, onCreated }) {
  const [d, setD] = useState({ title: '', type: 'proof_collection', verification_mode: 'manual', description: '', reward_xp: 50, channel_id: '', one_per_user: true });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function create() {
    setSaving(true); setError(null);
    try { await guildizerApi.post(`/api/guilds/${guildId}/campaigns`, d); onCreated(); }
    catch { setError('Could not create campaign.'); } finally { setSaving(false); }
  }

  return (
    <Box sx={{ p: 2, mb: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      <TextField size="small" fullWidth margin="dense" label="Title" value={d.title} inputProps={{ maxLength: 200 }} onChange={(e) => setD({ ...d, title: e.target.value })} />
      <Grid container spacing={1}>
        <Grid item xs={6}><TextField select size="small" fullWidth margin="dense" label="Type" value={d.type} onChange={(e) => setD({ ...d, type: e.target.value })}>{TYPES.map((t) => <MenuItem key={t} value={t}>{t.replace('_', ' ')}</MenuItem>)}</TextField></Grid>
        <Grid item xs={6}><TextField select size="small" fullWidth margin="dense" label="Verification" value={d.verification_mode} onChange={(e) => setD({ ...d, verification_mode: e.target.value })}>{VMODES.map((m) => <MenuItem key={m} value={m}>{m}</MenuItem>)}</TextField></Grid>
      </Grid>
      <TextField size="small" fullWidth margin="dense" label="Description" multiline minRows={2} value={d.description} inputProps={{ maxLength: 2000 }} onChange={(e) => setD({ ...d, description: e.target.value })} />
      <Grid container spacing={1}>
        <Grid item xs={6}><TextField type="number" size="small" fullWidth margin="dense" label="Reward XP" value={d.reward_xp} onChange={(e) => setD({ ...d, reward_xp: Number(e.target.value) })} /></Grid>
        <Grid item xs={6}><TextField select size="small" fullWidth margin="dense" label="Announce channel" value={d.channel_id} onChange={(e) => setD({ ...d, channel_id: e.target.value })}><MenuItem value="">— none —</MenuItem>{channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}</TextField></Grid>
      </Grid>
      <FormControlLabel control={<Switch checked={d.one_per_user} onChange={(e) => setD({ ...d, one_per_user: e.target.checked })} />} label="One submission per user" />
      <Box><Button variant="contained" onClick={create} disabled={saving || !d.title.trim()}>{saving ? 'Creating…' : 'Create campaign'}</Button></Box>
    </Box>
  );
}

function CampaignDetail({ guildId, campaignId, channels, plan, onBack }) {
  const base = `/api/guilds/${guildId}/campaigns/${campaignId}`;
  const [c, setC] = useState(null);
  const [subs, setSubs] = useState([]);
  const [board, setBoard] = useState(null);
  const [task, setTask] = useState({ title: '', reward_xp: 25, verification_mode: 'manual', task_url: '' });
  const [msg, setMsg] = useState(null);

  async function load() {
    const { data } = await guildizerApi.get(base); setC(data);
    const s = await guildizerApi.get(`${base}/submissions?status=pending`); setSubs(s.data.submissions);
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [campaignId]);

  async function patch(body) {
    try { const { data } = await guildizerApi.put(base, body); setC((p) => ({ ...p, ...data })); setMsg(null); }
    catch (e) { setMsg(e?.response?.status === 402 ? 'Free plan allows 1 active campaign — upgrade to Pro.' : 'Update failed.'); }
  }
  async function addTask() {
    if (!task.title.trim()) return;
    await guildizerApi.post(`${base}/tasks`, task); setTask({ title: '', reward_xp: 25, verification_mode: 'manual', task_url: '' }); load();
  }
  const delTask = async (tid) => { await guildizerApi.delete(`${base}/tasks/${tid}`); load(); };
  const review = async (sid, action) => { await guildizerApi.post(`${base}/submissions/${sid}/review`, { action }); load(); };
  async function post() {
    try { await guildizerApi.post(`${base}/post`); setMsg('Queued — the bot will post within ~20s.'); }
    catch (e) { setMsg(e?.response?.status === 400 ? 'Set an announce channel first.' : 'Post failed.'); }
  }
  async function loadBoard() {
    try { const { data } = await guildizerApi.get(`${base}/leaderboard`); setBoard(data.leaderboard); }
    catch (e) { setMsg(e?.response?.status === 402 ? 'Campaign leaderboards are a Pro feature.' : 'Failed to load.'); }
  }

  if (!c) return <Box sx={{ display: 'grid', placeItems: 'center', py: 3 }}><CircularProgress /></Box>;

  return (
    <Box>
      <Button startIcon={<ArrowBack />} onClick={onBack} color="inherit" sx={{ mb: 1 }}>All campaigns</Button>
      {msg && <Alert severity="info" sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg}</Alert>}
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Card variant="outlined"><CardContent>
            <Typography variant="h6" fontWeight={700}>{c.title}</Typography>
            <Stack direction="row" spacing={1} alignItems="center" mb={1}>
              <Chip size="small" label={c.status} color={STATUS_COLOR[c.status]} />
              <Typography variant="caption" color="text.secondary">{c.type.replace('_', ' ')} · {c.verification_mode}</Typography>
            </Stack>
            <TextField select size="small" fullWidth margin="dense" label="Announce channel" value={c.channel_id || ''} onChange={(e) => patch({ channel_id: e.target.value || null })}>
              <MenuItem value="">— none —</MenuItem>{channels.map((ch) => <MenuItem key={ch.id} value={ch.id}># {ch.name}</MenuItem>)}
            </TextField>
            <Stack direction="row" spacing={1} flexWrap="wrap" mt={1} useFlexGap>
              {c.status !== 'active' && <Button size="small" variant="contained" onClick={() => patch({ status: 'active' })}>Activate</Button>}
              {c.status === 'active' && <Button size="small" variant="outlined" onClick={() => patch({ status: 'paused' })}>Pause</Button>}
              {c.status === 'active' && <Button size="small" variant="outlined" onClick={post}>Re-post</Button>}
              <Button size="small" variant="outlined" color="inherit" onClick={() => patch({ status: 'closed' })}>Close</Button>
            </Stack>
            {c.post_status === 'posted' && <Typography variant="caption" color="success.main" display="block" mt={1}>Posted ✓</Typography>}
            {c.post_status === 'failed' && <Typography variant="caption" color="error" display="block" mt={1}>Post failed: {c.post_error}</Typography>}
          </CardContent></Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card variant="outlined"><CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>Tasks</Typography>
            {c.tasks.length === 0 && <Typography variant="body2" color="text.secondary">No tasks — single-task campaign.</Typography>}
            <List dense>
              {c.tasks.map((t) => (
                <ListItem key={t.id} disableGutters secondaryAction={<IconButton size="small" color="error" onClick={() => delTask(t.id)}><Delete fontSize="small" /></IconButton>}>
                  <ListItemText primary={t.title} secondary={`${t.reward_xp} XP · ${t.verification_mode}`} />
                </ListItem>
              ))}
            </List>
            <Divider sx={{ my: 1 }} />
            <TextField size="small" fullWidth margin="dense" label="Task title" value={task.title} onChange={(e) => setTask({ ...task, title: e.target.value })} />
            <Grid container spacing={1}>
              <Grid item xs={6}><TextField type="number" size="small" fullWidth margin="dense" label="Reward XP" value={task.reward_xp} onChange={(e) => setTask({ ...task, reward_xp: Number(e.target.value) })} /></Grid>
              <Grid item xs={6}><TextField select size="small" fullWidth margin="dense" label="Verification" value={task.verification_mode} onChange={(e) => setTask({ ...task, verification_mode: e.target.value })}>{VMODES.map((m) => <MenuItem key={m} value={m}>{m}</MenuItem>)}</TextField></Grid>
            </Grid>
            <TextField size="small" fullWidth margin="dense" label="Task link (optional)" placeholder="https://…" value={task.task_url} onChange={(e) => setTask({ ...task, task_url: e.target.value })} />
            <Button size="small" variant="outlined" onClick={addTask} disabled={!task.title.trim()}>Add task</Button>
          </CardContent></Card>
        </Grid>

        <Grid item xs={12}>
          <Card variant="outlined"><CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>Pending submissions ({subs.length})</Typography>
            {subs.length === 0 && <Typography variant="body2" color="text.secondary">Nothing to review.</Typography>}
            <List dense>
              {subs.map((s) => (
                <ListItem key={s.id} disableGutters secondaryAction={
                  <Stack direction="row" spacing={0.5}>
                    <Button size="small" onClick={() => review(s.id, 'verify')}>Verify</Button>
                    <Button size="small" color="error" onClick={() => review(s.id, 'reject')}>Reject</Button>
                  </Stack>}>
                  <ListItemText primary={s.username || s.user_id} secondary={s.proof?.value || '(no proof text)'} secondaryTypographyProps={{ noWrap: true }} />
                </ListItem>
              ))}
            </List>
          </CardContent></Card>
        </Grid>

        <Grid item xs={12}>
          <Card variant="outlined"><CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography variant="subtitle1" fontWeight={700}>Leaderboard {plan !== 'pro' && <Chip size="small" label="Pro" sx={{ ml: 1 }} />}</Typography>
              <Button size="small" variant="outlined" onClick={loadBoard}>Load</Button>
            </Stack>
            {board && board.length === 0 && <Typography variant="body2" color="text.secondary">No verified submissions yet.</Typography>}
            {board && (
              <List dense>
                {board.map((r) => (
                  <ListItem key={r.user_id} disableGutters secondaryAction={<Typography variant="caption" color="text.secondary">{r.xp_earned} XP</Typography>}>
                    <Typography variant="body2" fontWeight={700} color="primary.main" sx={{ width: 34 }}>#{r.rank}</Typography>
                    <ListItemText primary={r.username || r.user_id} />
                    <Chip size="small" label={`${r.verified}✓`} sx={{ mr: 1 }} />
                  </ListItem>
                ))}
              </List>
            )}
          </CardContent></Card>
        </Grid>
      </Grid>
    </Box>
  );
}
