import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Button, TextField, MenuItem, Switch,
  FormControlLabel, List, ListItem, ListItemText, IconButton, Chip, Alert,
  CircularProgress, Stack, Divider,
} from '@mui/material';
import { Add, Delete, ArrowBack } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';

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
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  if (selected) return <CampaignDetail guildId={guildId} campaignId={selected} channels={textChannels} plan={plan} onBack={() => { setSelected(null); load(); }} />;

  return (
    <>
    <GuildizerCollapsibleCard id="gz.engagement.campaigns" title="Campaigns">
      <Stack direction="row" justifyContent="flex-end" alignItems="center" mb={2}>
        <Button variant="contained" startIcon={<Add />} onClick={() => setCreating((v) => !v)}>{creating ? 'Close' : 'New campaign'}</Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" mb={2}>Run proof, content, social, and raid campaigns that reward members with XP for completing tasks.</Typography>

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
    </GuildizerCollapsibleCard>
    <ReferralsCard guildId={guildId} />
    </>
  );
}

function ReferralsCard({ guildId }) {
  const [data, setData] = useState(null);
  const [xp, setXp] = useState(0);

  async function load() {
    try {
      const { data: d } = await guildizerApi.get(`/api/guilds/${guildId}/referrals`);
      setData(d); setXp(d.xp_per_referral);
    } catch { /* quietly empty */ }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  if (!data) return null;
  return (
    <GuildizerCollapsibleCard
      id="gz.engagement.referrals"
      title="Referrals"
      action={(
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField type="number" size="small" label="XP per referral" value={xp}
            inputProps={{ min: 0, max: 1000 }} onChange={(e) => setXp(Number(e.target.value))} sx={{ width: 140 }} />
          <Button size="small" variant="outlined"
            onClick={() => guildizerApi.put(`/api/guilds/${guildId}/referrals/settings`, { xp_per_referral: xp }).then(load)}>
            Save
          </Button>
        </Stack>
      )}
    >
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Members get a personal tracked invite with /invitelink. Joins are attributed automatically.
      </Typography>
      {data.leaderboard.length === 0
        ? <Typography variant="body2" color="text.secondary">No attributed joins yet.</Typography>
        : (
          <List dense>
            {data.leaderboard.map((r, i) => (
              <ListItem key={r.inviter_id} disableGutters
                secondaryAction={<Chip size="small" label={`${r.joins} joins`} />}>
                <Typography variant="body2" fontWeight={700} color="primary.main" sx={{ width: 34 }}>#{i + 1}</Typography>
                <ListItemText primary={r.inviter_name || r.inviter_id} />
              </ListItem>
            ))}
          </List>
        )}
    </GuildizerCollapsibleCard>
  );
}

function CreateForm({ guildId, channels, onCreated }) {
  const [d, setD] = useState({ title: '', type: 'proof_collection', verification_mode: 'manual', description: '', reward_xp: 50, channel_id: '', one_per_user: true });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function create() {
    setSaving(true); setError(null);
    try { await guildizerApi.post(`/api/guilds/${guildId}/campaigns`, d); onCreated(); }
    catch (e) { setError(e?.response?.data?.message || e?.response?.data?.error || 'Could not create campaign.'); }
    finally { setSaving(false); }
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
  useEffect(() => {
    load();
    if (plan === 'pro') loadBoard(); // auto-load; free plans see the Pro chip
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  async function patch(body) {
    try { const { data } = await guildizerApi.put(base, body); setC((p) => ({ ...p, ...data })); setMsg(null); }
    catch (e) {
      setMsg(e?.response?.status === 402
        ? (e?.response?.data?.message || 'Free plan allows 1 active campaign — upgrade to Pro.')
        : (e?.response?.data?.message || 'Update failed.'));
    }
  }
  async function remove() {
    if (!window.confirm(`Delete "${c.title}"? Its tasks and submissions are removed too.`)) return;
    try { await guildizerApi.delete(base); onBack(); }
    catch { setMsg('Delete failed.'); }
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
        <Grid item xs={12}>
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
              {c.status !== 'active' && (
                <Button size="small" variant="outlined" color="error" onClick={remove}>Delete</Button>
              )}
            </Stack>
            {c.post_status === 'posted' && <Typography variant="caption" color="success.main" display="block" mt={1}>Posted ✓</Typography>}
            {c.post_status === 'failed' && <Typography variant="caption" color="error" display="block" mt={1}>Post failed: {c.post_error}</Typography>}
          </CardContent></Card>
        </Grid>

        <Grid item xs={12}>
          <GuildizerCollapsibleCard id="gz.campaigns.tasks" title="Tasks">
            <Typography variant="body2" color="text.secondary" mb={2}>Break the campaign into individual tasks, each with its own XP reward and verification.</Typography>
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
          </GuildizerCollapsibleCard>
        </Grid>

        <Grid item xs={12}>
          <FieldsCard guildId={guildId} campaignId={campaignId} />
        </Grid>

        <Grid item xs={12}>
          <GuildizerCollapsibleCard id="gz.campaigns.pending_submissions" title={`Pending submissions (${subs.length})`}>
            <Typography variant="body2" color="text.secondary" mb={2}>Review member proof submissions and verify or reject each one.</Typography>
            {subs.length === 0 && <Typography variant="body2" color="text.secondary">Nothing to review.</Typography>}
            <List dense>
              {subs.map((s) => (
                <ListItem key={s.id} disableGutters secondaryAction={
                  <Stack direction="row" spacing={0.5}>
                    <Button size="small" onClick={() => review(s.id, 'verify')}>Verify</Button>
                    <Button size="small" color="error" onClick={() => review(s.id, 'reject')}>Reject</Button>
                  </Stack>}>
                  {s.proof?.link_check && (
                    <Chip size="small" sx={{ mr: 1 }} variant="outlined"
                      color={s.proof.link_check === 'valid' ? 'success' : s.proof.link_check === 'invalid' ? 'error' : 'default'}
                      label={`link ${s.proof.link_check}`} />
                  )}
                  <ListItemText
                    primary={s.username || s.user_id}
                    secondary={[s.proof?.value, s.proof?.fields && Object.entries(s.proof.fields).map(([k, v]) => `${k}: ${v}`).join(' · ')].filter(Boolean).join(' — ') || '(no proof text)'}
                    secondaryTypographyProps={{ noWrap: true }} />
                </ListItem>
              ))}
            </List>
          </GuildizerCollapsibleCard>
        </Grid>

        <Grid item xs={12}>
          <GuildizerCollapsibleCard
            id="gz.campaigns.leaderboard"
            title="Leaderboard"
            badge={plan !== 'pro' && <Chip size="small" label="Pro" sx={{ ml: 1 }} />}
            action={<Button size="small" variant="outlined" onClick={loadBoard}>{board ? 'Refresh' : 'Load'}</Button>}
          >
            <Typography variant="body2" color="text.secondary" mb={2}>Members ranked by the XP they have earned from verified submissions in this campaign.</Typography>
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
          </GuildizerCollapsibleCard>
        </Grid>
      </Grid>
    </Box>
  );
}


function FieldsCard({ guildId, campaignId }) {
  const [fields, setFields] = useState([]);
  const [label, setLabel] = useState('');

  async function load() {
    try {
      const { data } = await guildizerApi.get(`/api/guilds/${guildId}/campaigns/${campaignId}/fields`);
      setFields(data.fields);
    } catch { /* quietly empty */ }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  return (
    <GuildizerCollapsibleCard id="gz.campaigns.proof_form_fields" title="Proof form fields">
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Extra inputs shown in the proof popup (max 4) — e.g. wallet address, username on X.
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center">
        <TextField size="small" label="Field label" value={label} inputProps={{ maxLength: 45 }}
          onChange={(e) => setLabel(e.target.value)} sx={{ flex: 1 }} />
        <Button size="small" variant="outlined" disabled={!label.trim() || fields.length >= 4}
          onClick={() => guildizerApi.post(`/api/guilds/${guildId}/campaigns/${campaignId}/fields`, { label }).then(() => { setLabel(''); load(); })}>
          Add
        </Button>
      </Stack>
      <List dense>
        {fields.map((f) => (
          <ListItem key={f.id} disableGutters
            secondaryAction={(
              <IconButton size="small" color="error"
                onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/campaigns/${campaignId}/fields/${f.id}`).then(load)}>
                <Delete fontSize="small" />
              </IconButton>
            )}>
            <ListItemText primary={f.label} secondary={f.required ? 'required' : 'optional'} />
          </ListItem>
        ))}
        {fields.length === 0 && <Typography variant="body2" color="text.secondary">No extra fields.</Typography>}
      </List>
    </GuildizerCollapsibleCard>
  );
}
