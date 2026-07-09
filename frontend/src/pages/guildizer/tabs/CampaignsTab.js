import React, { useEffect, useMemo, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Button, TextField, MenuItem, Switch,
  FormControlLabel, List, ListItem, ListItemButton, ListItemText, IconButton, Chip, Alert,
  CircularProgress, Stack, Divider, Tabs, Tab, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions,
  Stepper, Step, StepLabel,
} from '@mui/material';
import { Add, Delete, ArrowBack, Download, EmojiEvents } from '@mui/icons-material';
import guildizerApi, { guildizerXVerifyKey } from '../../../services/guildizerApi';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';
import { downloadCsv } from './csv';

// ── X auto-verify status signal (Telegizer parity) ────────────────────────────
// 3-state health for the "Auto-verify on X" toggle so the owner knows whether raid
// actions confirm automatically or fall back to manual. Account-level (the owner's
// BYO key or the platform key) → identical across guilds, fetched once with the list.
const X_STATUS_META = {
  live: {
    color: 'success', dot: '🟢', label: 'X auto-verify: live',
    detail: 'Reposts, comments, quotes & follows confirm automatically in real time. (Likes can’t be auto-verified — X keeps likes private.)',
  },
  rejected: {
    color: 'warning', dot: '🟡', label: 'X auto-verify: key rejected',
    detail: 'A key is configured but X rejected it (invalid key, no credits, or rate-limited). Until it’s fixed, submissions fall back to manual review.',
  },
  disabled: {
    color: 'default', dot: '⚪', label: 'X auto-verify: not configured',
    detail: 'No twitterapi.io key is available, so submissions go to manual review. Add your own key to confirm actions automatically.',
  },
};

function XAutoverifyStatus({ status, enabled, onManageKey }) {
  const meta = X_STATUS_META[status] || X_STATUS_META.disabled;
  if (!enabled) {
    return (
      <Tooltip title={meta.detail}>
        <Chip size="small" variant="outlined" color={meta.color}
          label={`${meta.dot} ${meta.label}`} onClick={onManageKey} sx={{ mt: 1 }} />
      </Tooltip>
    );
  }
  const severity = status === 'live' ? 'success' : status === 'rejected' ? 'warning' : 'info';
  // Button below the detail (not in Alert's right-hand action slot) so the text
  // spans full width — 2–3 lines instead of a narrow ~10-line column on mobile.
  return (
    <Alert severity={severity} sx={{ mt: 1 }}>
      <strong>{meta.dot} {meta.label}</strong>
      <Typography variant="caption" display="block">{meta.detail}</Typography>
      {onManageKey && (
        <Button color="inherit" size="small" onClick={onManageKey}
          sx={{ mt: 0.5, px: 0, minWidth: 0, whiteSpace: 'nowrap' }}>
          {status === 'live' ? 'Manage key' : 'Add your key'}
        </Button>
      )}
    </Alert>
  );
}

function XKeyDialog({ open, onClose, onSaved }) {
  const [info, setInfo] = useState(null);
  const [keyInput, setKeyInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!open) return;
    setKeyInput(''); setErr(null); setLoading(true);
    guildizerXVerifyKey.get()
      .then((r) => setInfo(r.data)).catch(() => setInfo(null))
      .finally(() => setLoading(false));
  }, [open]);

  async function save() {
    if (!keyInput.trim()) return;
    setBusy(true); setErr(null);
    try {
      const r = await guildizerXVerifyKey.save(keyInput.trim());
      onSaved?.(r.data.status); onClose();
    } catch (e) { setErr(e?.response?.data?.error || 'Failed to save key'); }
    finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setErr(null);
    try {
      const r = await guildizerXVerifyKey.delete();
      onSaved?.(r.data.status); onClose();
    } catch (e) { setErr(e?.response?.data?.error || 'Failed to remove key'); }
    finally { setBusy(false); }
  }

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Your twitterapi.io key</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Add your own <strong>twitterapi.io</strong> key to run X auto-verify on your own
          credits instead of the shared platform key. It’s <strong>account-level</strong> — one
          key covers every server you manage. Get a key at{' '}
          <a href="https://twitterapi.io" target="_blank" rel="noopener noreferrer">twitterapi.io</a>.
        </Typography>
        {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
        {loading ? (
          <Box sx={{ display: 'grid', placeItems: 'center', py: 2 }}><CircularProgress size={24} /></Box>
        ) : (
          <>
            {info?.configured && (
              <Alert severity={info.status === 'live' ? 'success' : info.status === 'rejected' ? 'warning' : 'info'} sx={{ mb: 2 }}>
                Saved key {info.masked_key ? `(${info.masked_key})` : ''} — current status: <strong>{info.status}</strong>.
              </Alert>
            )}
            <TextField fullWidth type="password" label="twitterapi.io API key"
              placeholder={info?.configured ? 'Paste a new key to replace' : 'Paste your key'}
              value={keyInput} onChange={(e) => setKeyInput(e.target.value)} autoComplete="off" />
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
              We check the key against the live API before saving, so a bad key is caught here.
            </Typography>
          </>
        )}
      </DialogContent>
      <DialogActions>
        {info?.configured && <Button color="error" onClick={remove} disabled={busy}>Remove key</Button>}
        <Box sx={{ flex: 1 }} />
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={busy || !keyInput.trim()}>
          {busy ? 'Saving…' : 'Save & verify'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

const TEXT_TYPES = new Set([0, 5]);
const TYPES = ['proof_collection', 'content_submission', 'social_task', 'raid', 'giveaway'];
const TYPE_LABEL = { proof_collection: 'Proof Collection', content_submission: 'Content Submission', social_task: 'Social Task', raid: 'Twitter Raid', giveaway: 'Giveaway' };
// Twitter Raid targets, stored under campaign settings.raid_goals.
const RAID_GOALS = [['likes', 'Likes'], ['retweets', 'Retweets'], ['comments', 'Comments'], ['follows', 'Follows']];
const cleanGoals = (g) => Object.fromEntries(
  RAID_GOALS.map(([k]) => [k, parseInt(g?.[k], 10)]).filter(([, v]) => v > 0));
const VMODES = ['manual', 'honor', 'link'];
// Typed proof fields — 1:1 with Telegizer's CampaignManager FIELD_TYPES.
const FIELD_TYPES = [
  { value: 'text', label: 'Text' },
  { value: 'url', label: 'URL / Link' },
  { value: 'uid', label: 'Exchange UID' },
  { value: 'wallet', label: 'Wallet address' },
  { value: 'screenshot', label: 'Screenshot' },
  { value: 'tx_hash', label: 'Transaction hash' },
  { value: 'username', label: 'Username / handle' },
];
const STATUS_COLOR = { draft: 'default', active: 'success', paused: 'warning', closed: 'default' };

export default function CampaignsTab({ guildId, channels = [] }) {
  const [campaigns, setCampaigns] = useState([]);
  const [plan, setPlan] = useState('free');
  const [xStatus, setXStatus] = useState('disabled');
  const [keyDialogOpen, setKeyDialogOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);
  const [typeFilter, setTypeFilter] = useState('all');
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));

  const summary = useMemo(() => {
    const active = campaigns.filter((c) => c.status === 'active').length;
    const submissions = campaigns.reduce((n, c) => n + (c.counts?.verified || 0) + (c.counts?.pending || 0), 0);
    const pending = campaigns.reduce((n, c) => n + (c.counts?.pending || 0), 0);
    return { total: campaigns.length, active, submissions, pending };
  }, [campaigns]);

  const shown = typeFilter === 'all' ? campaigns : campaigns.filter((c) => c.type === typeFilter);

  async function load() {
    setLoading(true);
    try {
      const { data } = await guildizerApi.get(`/api/guilds/${guildId}/campaigns`);
      setCampaigns(data.campaigns); setPlan(data.plan);
      if (data.x_autoverify_status) setXStatus(data.x_autoverify_status);
    } finally { setLoading(false); }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  if (selected) return <CampaignDetail guildId={guildId} campaignId={selected} channels={textChannels} plan={plan} xStatus={xStatus} onXStatus={setXStatus} onBack={() => { setSelected(null); load(); }} />;

  return (
    <>
    <GuildizerCollapsibleCard id="gz.engagement.campaigns" title="Campaigns">
      <Stack direction="row" justifyContent="flex-end" alignItems="center" mb={2}>
        <Button variant="contained" startIcon={<Add />} onClick={() => setCreating((v) => !v)}>{creating ? 'Close' : 'New campaign'}</Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" mb={2}>Run proof, content, social, and raid campaigns that reward members with XP for completing tasks. Members participate from Discord.</Typography>

      {plan !== 'pro' && (
        <Alert severity="info" icon={false} sx={{ mb: 2 }}>
          <strong>Free plan:</strong> 1 active campaign, manual/honor proof. Pro unlocks multiple
          campaigns, link-validity checks, per-campaign leaderboards and bulk CSV export.
        </Alert>
      )}

      {/* Summary cards (Telegizer parity) */}
      <Grid container spacing={1.5} mb={2}>
        {[['Campaigns', summary.total], ['Active', summary.active, 'success.main'], ['Submissions', summary.submissions], ['Pending Review', summary.pending, 'warning.main']].map(([label, val, color]) => (
          <Grid item xs={6} md={3} key={label}>
            <Card variant="outlined"><CardContent sx={{ py: 1.5, textAlign: 'center' }}>
              <Typography variant="h5" fontWeight={800} sx={color ? { color } : undefined}>{val}</Typography>
              <Typography variant="caption" color="text.secondary">{label}</Typography>
            </CardContent></Card>
          </Grid>
        ))}
      </Grid>

      {/* Type filter tabs */}
      <Tabs value={typeFilter} onChange={(_, v) => setTypeFilter(v)} variant="scrollable" scrollButtons="auto"
        sx={{ mb: 1, minHeight: 36, '& .MuiTab-root': { minHeight: 36, textTransform: 'none' } }}>
        <Tab value="all" label={`All (${campaigns.length})`} />
        {TYPES.map((t) => <Tab key={t} value={t} label={`${TYPE_LABEL[t]} (${campaigns.filter((c) => c.type === t).length})`} />)}
      </Tabs>

      {creating && <CreateForm guildId={guildId} channels={textChannels} plan={plan} xStatus={xStatus} onManageKey={() => setKeyDialogOpen(true)} onCreated={() => { setCreating(false); load(); }} />}

      {loading ? <Box sx={{ display: 'grid', placeItems: 'center', py: 3 }}><CircularProgress /></Box> : (
        <>
          {shown.length === 0 && <Typography variant="body2" color="text.secondary">No campaigns{typeFilter !== 'all' ? ' of this type' : ''} yet.</Typography>}
          <List dense>
            {shown.map((c) => (
              // ListItemButton (not `<ListItem button secondaryAction>`, which
              // silently breaks the row click) so the whole row opens the campaign.
              // Counts sit inside the button so tapping them still opens detail.
              <ListItem key={c.id} disablePadding divider>
                <ListItemButton onClick={() => setSelected(c.id)} sx={{ gap: 1 }}>
                  <Chip size="small" label={c.status} color={STATUS_COLOR[c.status]} sx={{ flexShrink: 0 }} />
                  <ListItemText sx={{ minWidth: 0 }} primary={c.title} secondary={`${TYPE_LABEL[c.type] || c.type} · ${c.task_count} tasks`}
                    primaryTypographyProps={{ noWrap: true }} secondaryTypographyProps={{ noWrap: true }} />
                  <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
                    {c.counts.verified}✓ / {c.counts.pending}⏳
                  </Typography>
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        </>
      )}
    </GuildizerCollapsibleCard>
    <XKeyDialog open={keyDialogOpen} onClose={() => setKeyDialogOpen(false)}
      onSaved={(s) => { if (s) setXStatus(s); load(); }} />
    </>
  );
}

const WIZARD_STEPS = ['Task & Proof', 'Schedule & Reward'];

function CreateForm({ guildId, channels, plan, xStatus = 'disabled', onManageKey, onCreated }) {
  const [d, setD] = useState({ title: '', type: 'proof_collection', verification_mode: 'manual', description: '', reward_xp: 50, channel_id: '', one_per_user: true, task_url: '', raid_goals: {}, auto_verify_x: false });
  const [step, setStep] = useState(0);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const isRaid = d.type === 'raid';
  const isPro = plan === 'pro';
  const step0Valid = !!d.title.trim();

  async function create() {
    setSaving(true); setError(null);
    const { raid_goals, auto_verify_x, ...rest } = d;
    const body = { ...rest, task_url: rest.task_url || null };
    if (isRaid) body.settings = { raid_goals: cleanGoals(raid_goals), auto_verify_x: !!(isPro && auto_verify_x) };
    try { await guildizerApi.post(`/api/guilds/${guildId}/campaigns`, body); onCreated(); }
    catch (e) { setError(e?.response?.data?.message || e?.response?.data?.error || 'Could not create campaign.'); }
    finally { setSaving(false); }
  }

  return (
    <Box sx={{ p: 2, mb: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
      <Stepper activeStep={step} sx={{ mb: 2 }}>
        {WIZARD_STEPS.map((s) => <Step key={s}><StepLabel>{s}</StepLabel></Step>)}
      </Stepper>
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}

      {step === 0 && (
        <>
          <TextField size="small" fullWidth margin="dense" label="Title" value={d.title} inputProps={{ maxLength: 200 }} onChange={(e) => setD({ ...d, title: e.target.value })} />
          <Grid container spacing={1}>
            <Grid item xs={6}><TextField select size="small" fullWidth margin="dense" label="Type" value={d.type} onChange={(e) => setD({ ...d, type: e.target.value })}>{TYPES.map((t) => <MenuItem key={t} value={t}>{TYPE_LABEL[t]}</MenuItem>)}</TextField></Grid>
            <Grid item xs={6}><TextField select size="small" fullWidth margin="dense" label="Verification" value={d.verification_mode} onChange={(e) => setD({ ...d, verification_mode: e.target.value })}>{VMODES.map((m) => <MenuItem key={m} value={m}>{m}</MenuItem>)}</TextField></Grid>
          </Grid>
          <TextField size="small" fullWidth margin="dense" label="Description" multiline minRows={2} value={d.description} inputProps={{ maxLength: 2000 }} onChange={(e) => setD({ ...d, description: e.target.value })} />
          {isRaid && (
            <>
              <TextField size="small" fullWidth margin="dense" label="Tweet URL" placeholder="https://x.com/…"
                value={d.task_url} onChange={(e) => setD({ ...d, task_url: e.target.value })} />
              <Typography variant="caption" color="text.secondary" display="block" mt={1}>Raid goals (shown as targets in the announcement)</Typography>
              <Grid container spacing={1}>
                {RAID_GOALS.map(([k, label]) => (
                  <Grid item xs={6} sm={3} key={k}>
                    <TextField type="number" size="small" fullWidth margin="dense" label={label} inputProps={{ min: 0 }}
                      value={d.raid_goals[k] || ''} onChange={(e) => setD({ ...d, raid_goals: { ...d.raid_goals, [k]: e.target.value } })} />
                  </Grid>
                ))}
              </Grid>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mt: 0.5 }}>
                <Typography variant="body2">Auto-verify on X (Pro)</Typography>
                <Switch checked={isPro && d.auto_verify_x} disabled={!isPro}
                  onChange={(e) => setD({ ...d, auto_verify_x: e.target.checked })} />
              </Box>
              {isPro ? (
                <XAutoverifyStatus status={xStatus} enabled={d.auto_verify_x} onManageKey={onManageKey} />
              ) : (
                <Typography variant="caption" color="text.secondary" display="block">
                  Real-time X verification is a Pro feature. You can still run the raid with manual proof review.
                </Typography>
              )}
            </>
          )}
          <Typography variant="caption" color="text.secondary" display="block" mt={1.5}>
            After creating, add sub-tasks and custom proof fields from the campaign's detail view.
          </Typography>
        </>
      )}

      {step === 1 && (
        <>
          <Grid container spacing={1}>
            <Grid item xs={6}><TextField type="number" size="small" fullWidth margin="dense" label="Reward XP" value={d.reward_xp} onChange={(e) => setD({ ...d, reward_xp: Number(e.target.value) })} /></Grid>
            <Grid item xs={6}><TextField select size="small" fullWidth margin="dense" label="Announce channel" value={d.channel_id} onChange={(e) => setD({ ...d, channel_id: e.target.value })}><MenuItem value="">— none —</MenuItem>{channels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}</TextField></Grid>
          </Grid>
          <FormControlLabel control={<Switch checked={d.one_per_user} onChange={(e) => setD({ ...d, one_per_user: e.target.checked })} />} label="One submission per user" />
        </>
      )}

      <Stack direction="row" spacing={1} justifyContent="flex-end" mt={2}>
        {step > 0 && <Button onClick={() => setStep((s) => s - 1)} disabled={saving}>Back</Button>}
        {step < WIZARD_STEPS.length - 1
          ? <Button variant="contained" onClick={() => setStep((s) => s + 1)} disabled={!step0Valid}>Next</Button>
          : <Button variant="contained" onClick={create} disabled={saving || !step0Valid}>{saving ? 'Creating…' : 'Create campaign'}</Button>}
      </Stack>
    </Box>
  );
}

function CampaignDetail({ guildId, campaignId, channels, plan, xStatus = 'disabled', onXStatus, onBack }) {
  const base = `/api/guilds/${guildId}/campaigns/${campaignId}`;
  const [c, setC] = useState(null);
  const [subs, setSubs] = useState([]);
  const [board, setBoard] = useState(null);
  const [task, setTask] = useState({ title: '', reward_xp: 25, verification_mode: 'manual', task_url: '' });
  const [msg, setMsg] = useState(null);
  const [winnerCount, setWinnerCount] = useState(1);
  const [keyDialogOpen, setKeyDialogOpen] = useState(false);

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
  async function pickWinners() {
    try {
      const { data } = await guildizerApi.get(`${base}/submissions?status=verified`);
      const verified = data.submissions || [];
      if (verified.length === 0) { setMsg('No verified submissions to draw winners from yet.'); return; }
      const n = Math.max(1, Math.min(winnerCount, verified.length));
      const picked = [...verified].sort(() => Math.random() - 0.5).slice(0, n)
        .map((s) => ({ id: s.id, user_id: s.user_id, username: s.username }));
      const mergedSettings = { ...(c.settings || {}), winners: picked };
      const { data: updated } = await guildizerApi.put(base, { settings: mergedSettings });
      setC((p) => ({ ...p, ...updated }));
      setMsg(`Picked ${picked.length} winner${picked.length === 1 ? '' : 's'}.`);
    } catch { setMsg('Could not draw winners.'); }
  }
  async function exportCsv() {
    try {
      const { data } = await guildizerApi.get(`${base}/submissions`);
      const rows = (data.submissions || []).map((s) => [
        s.username || '', s.user_id, s.status,
        s.proof?.value || '',
        s.proof?.fields ? Object.entries(s.proof.fields).map(([k, v]) => `${k}: ${v}`).join(' | ') : '',
        s.created_at ? new Date(s.created_at).toLocaleString() : '',
      ]);
      downloadCsv(`campaign_${campaignId}_submissions.csv`, ['Name', 'User ID', 'Status', 'Proof', 'Fields', 'Submitted'], rows);
    } catch { setMsg('Could not export submissions.'); }
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
              <Button size="small" variant="outlined" startIcon={<Download />} onClick={exportCsv}>Export CSV</Button>
              <Button size="small" variant="outlined" color="inherit" onClick={() => patch({ status: 'closed' })}>Close</Button>
              {c.status !== 'active' && (
                <Button size="small" variant="outlined" color="error" onClick={remove}>Delete</Button>
              )}
            </Stack>
            {/* Pick Winners — random draw over verified submissions (giveaways, raffles). */}
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap mt={1}>
              <TextField type="number" size="small" label="Winners" value={winnerCount}
                inputProps={{ min: 1, max: 50 }} sx={{ width: 100 }}
                onChange={(e) => setWinnerCount(Math.max(1, Number(e.target.value) || 1))} />
              <Button size="small" variant="outlined" startIcon={<EmojiEvents />} onClick={pickWinners}>Pick Winners</Button>
            </Stack>
            {c.settings?.winners?.length > 0 && (
              <Alert severity="success" icon={<EmojiEvents fontSize="inherit" />} sx={{ mt: 1 }}>
                Winners: {c.settings.winners.map((w) => (w.username ? `@${w.username}` : w.user_id)).join(', ')}
              </Alert>
            )}
            {c.post_status === 'posted' && <Typography variant="caption" color="success.main" display="block" mt={1}>Posted ✓</Typography>}
            {c.post_status === 'failed' && <Typography variant="caption" color="error" display="block" mt={1}>Post failed: {c.post_error}</Typography>}
          </CardContent></Card>
        </Grid>

        {c.type === 'raid' && (
          <Grid item xs={12}>
            <RaidSetupCard campaign={c} onSave={patch} plan={plan} xStatus={xStatus}
              onManageKey={() => setKeyDialogOpen(true)} />
          </Grid>
        )}

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
          <FieldsCard guildId={guildId} campaignId={campaignId}
            autoVerifyActive={c.type === 'raid' && !!(c.settings || {}).auto_verify_x && plan === 'pro'} />
        </Grid>

        <Grid item xs={12}>
          <GuildizerCollapsibleCard id="gz.campaigns.pending_submissions" title={`Pending submissions (${subs.length})`}>
            <Typography variant="body2" color="text.secondary" mb={2}>Review member proof submissions and verify or reject each one.</Typography>
            {subs.length === 0 && <Typography variant="body2" color="text.secondary">Nothing to review.</Typography>}
            <List dense>
              {subs.map((s) => (
                // Flex row so the proof text truncates and the Verify/Reject
                // buttons stay clear of it on narrow screens.
                <ListItem key={s.id} disableGutters sx={{ gap: 1, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  {s.proof?.link_check && (
                    <Chip size="small" sx={{ flexShrink: 0, mt: 0.25 }} variant="outlined"
                      color={s.proof.link_check === 'valid' ? 'success' : s.proof.link_check === 'invalid' ? 'error' : 'default'}
                      label={`link ${s.proof.link_check}`} />
                  )}
                  <ListItemText
                    sx={{ my: 0, minWidth: 0, flex: '1 1 160px' }}
                    primary={s.username || s.user_id}
                    secondary={[s.proof?.value, s.proof?.fields && Object.entries(s.proof.fields).map(([k, v]) => `${k}: ${v}`).join(' · ')].filter(Boolean).join(' — ') || '(no proof text)'}
                    secondaryTypographyProps={{ sx: { wordBreak: 'break-word' } }} />
                  <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0, ml: 'auto' }}>
                    <Button size="small" variant="outlined" onClick={() => review(s.id, 'verify')}>Verify</Button>
                    <Button size="small" variant="outlined" color="error" onClick={() => review(s.id, 'reject')}>Reject</Button>
                  </Stack>
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
      <XKeyDialog open={keyDialogOpen} onClose={() => setKeyDialogOpen(false)}
        onSaved={(s) => { if (s && onXStatus) onXStatus(s); }} />
    </Box>
  );
}


function RaidSetupCard({ campaign, onSave, plan, xStatus = 'disabled', onManageKey }) {
  const [tweet, setTweet] = useState(campaign.task_url || '');
  const [goals, setGoals] = useState((campaign.settings || {}).raid_goals || {});
  const [autoVerify, setAutoVerify] = useState(!!(campaign.settings || {}).auto_verify_x);
  const isPro = plan === 'pro';
  return (
    <GuildizerCollapsibleCard id="gz.campaigns.raid_setup" title="🐦 Twitter Raid setup">
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        The tweet to raid and the engagement targets shown in the announcement. Members submit their proof link.
      </Typography>
      <TextField size="small" fullWidth margin="dense" label="Tweet URL" placeholder="https://x.com/…"
        value={tweet} onChange={(e) => setTweet(e.target.value)} />
      <Grid container spacing={1} mt={0.5}>
        {RAID_GOALS.map(([k, label]) => (
          <Grid item xs={6} sm={3} key={k}>
            <TextField type="number" size="small" fullWidth label={label} inputProps={{ min: 0 }}
              value={goals[k] || ''} onChange={(e) => setGoals({ ...goals, [k]: e.target.value })} />
          </Grid>
        ))}
      </Grid>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mt: 0.5 }}>
        <Typography variant="body2">Auto-verify on X (Pro)</Typography>
        <Switch checked={isPro && autoVerify} disabled={!isPro}
          onChange={(e) => setAutoVerify(e.target.checked)} />
      </Box>
      {isPro ? (
        <>
          <XAutoverifyStatus status={xStatus} enabled={autoVerify} onManageKey={onManageKey} />
          {autoVerify && (
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
              Members tap the button and enter their X @username; reposts, comments, quotes and
              follows are checked live. Likes need manual review (X keeps likes private).
            </Typography>
          )}
        </>
      ) : (
        <Typography variant="caption" color="text.secondary" display="block">
          Real-time X verification is a Pro feature. Members still submit proof for manual review.
        </Typography>
      )}
      <Box>
        <Button size="small" variant="outlined" sx={{ mt: 1.5 }}
          onClick={() => onSave({ task_url: tweet || null, settings: { raid_goals: cleanGoals(goals), auto_verify_x: !!(isPro && autoVerify) } })}>
          Save raid setup
        </Button>
      </Box>
    </GuildizerCollapsibleCard>
  );
}

function FieldsCard({ guildId, campaignId, autoVerifyActive = false }) {
  const [fields, setFields] = useState([]);
  const [label, setLabel] = useState('');
  const [fieldType, setFieldType] = useState('text');

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

  const typeLabel = (t) => (FIELD_TYPES.find((x) => x.value === t) || {}).label || 'Text';

  return (
    <GuildizerCollapsibleCard id="gz.campaigns.proof_form_fields" title="Proof form fields">
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        {autoVerifyActive
          ? 'Auto-verify already confirms the X actions — you only need extra fields for things the bot can’t read from X (wallet, email, UID for a reward).'
          : 'Extra inputs shown in the proof popup (max 4) — e.g. wallet address, username on X.'}
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ xs: 'stretch', sm: 'center' }}>
        <TextField size="small" label="Field label" value={label} inputProps={{ maxLength: 45 }}
          onChange={(e) => setLabel(e.target.value)} sx={{ flex: 1 }} />
        <TextField select size="small" label="Type" value={fieldType}
          onChange={(e) => setFieldType(e.target.value)} sx={{ minWidth: 150 }}>
          {FIELD_TYPES.map((t) => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
        </TextField>
        <Button size="small" variant="outlined" disabled={!label.trim() || fields.length >= 4}
          onClick={() => guildizerApi.post(`/api/guilds/${guildId}/campaigns/${campaignId}/fields`, { label, field_type: fieldType }).then(() => { setLabel(''); setFieldType('text'); load(); })}>
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
            <ListItemText primary={f.label} secondary={`${typeLabel(f.field_type)} · ${f.required ? 'required' : 'optional'}`} />
          </ListItem>
        ))}
        {fields.length === 0 && <Typography variant="body2" color="text.secondary">No extra fields.</Typography>}
      </List>
    </GuildizerCollapsibleCard>
  );
}
