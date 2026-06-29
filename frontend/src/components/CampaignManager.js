import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton,
  Chip, Alert, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Paper, FormControl, InputLabel, Select, MenuItem, Switch,
  FormControlLabel, Stepper, Step, StepLabel, Divider, Menu, Tooltip,
  CircularProgress, Stack, Tabs, Tab,
} from '@mui/material';
import {
  Add, Delete, DeleteOutline, Edit, MoreVert, Download, EmojiEvents, Campaign as CampaignIcon,
  CheckCircle, Cancel, Visibility, Send, Replay, ArrowDropDown,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { engagement } from '../services/api';

const TYPES = [
  { value: 'social_task',       label: 'Social Task',         emoji: '📢', chip: 'Social',   help: 'Like / repost / follow / subscribe / join a channel.' },
  { value: 'proof_collection',  label: 'Proof Collection',   emoji: '📋', chip: 'Proof',    help: 'Collect UID, wallet, referral link, screenshot or custom fields.' },
  { value: 'content_submission', label: 'Content Submission', emoji: '📝', chip: 'Content',  help: 'Users submit a link (YouTube / X / Telegram / blog) for review.' },
  { value: 'giveaway',          label: 'Giveaway',            emoji: '🎁', chip: 'Giveaway', help: 'Entry on completion of the task.' },
  { value: 'raid',              label: 'Twitter Raid',        emoji: '🐦', chip: 'Raid',     help: 'Coordinate a like/retweet/comment raid on a tweet. Members submit their proof link.' },
];

// Raid goal fields (stored under settings.raid_goals).
const RAID_GOALS = [
  { key: 'likes', label: 'Likes' },
  { key: 'retweets', label: 'Retweets' },
  { key: 'comments', label: 'Comments' },
  { key: 'quotes', label: 'Quote tweets' },
  { key: 'follows', label: 'Follows' },
];
const PLATFORMS = [
  { value: '', label: '—' },
  { value: 'x', label: 'X / Twitter' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'facebook', label: 'Facebook' },
  { value: 'other', label: 'Other' },
];
// Per-type wizard behaviour — what each campaign type actually asks for, so the
// five types stop looking identical. Drives field visibility, labels & defaults.
const TYPE_CONFIG = {
  social_task: {
    showPlatform: true, platformRequired: true,
    taskUrlLabel: 'Link to like / follow / join (optional)',
    defaultVerification: 'honor',
    proofHint: 'Social tasks are usually honor-based or a quick screenshot. Add a proof field only if you need one.',
  },
  proof_collection: {
    showPlatform: false,
    taskUrlLabel: 'Reference link (optional)',
    defaultVerification: 'manual',
    proofHint: 'This is the heart of a proof collection — add the fields you want to collect (UID, wallet, tx hash, screenshot…).',
  },
  content_submission: {
    showPlatform: true, platformRequired: false,
    taskUrlLabel: 'Example / brief for creators (optional)',
    defaultVerification: 'manual',   // free-safe; Pro can switch to link-validity
    autoUrlField: true,
    proofHint: 'Participants submit a link to their content (YouTube / X / blog). A required link field is added for you.',
  },
  giveaway: {
    showPlatform: false,
    taskUrlLabel: 'Entry link (optional)',
    defaultVerification: 'honor',
    proofHint: 'Keep entry light. The reward label and the winner picker (under Manage) are what matter for a giveaway.',
  },
  raid: {
    showPlatform: false,            // locked to X / Twitter
    taskUrlLabel: 'Tweet URL',
    taskUrlRequired: true,
    defaultVerification: 'manual',
    raidGoals: true,
  },
};
const typeConfig = (t) => TYPE_CONFIG[t] || { showPlatform: true };

const VERIFICATION_MODES = [
  { value: 'manual', label: 'Manual review (admin approves)' },
  { value: 'honor',  label: 'Honor-based (one-tap Verify)' },
  { value: 'screenshot', label: 'Screenshot proof' },
  { value: 'link',   label: 'Link-validity check (Pro)' },
  { value: 'auto',   label: 'Auto-verify (Telegram join)' },
];
const FIELD_TYPES = [
  { value: 'text', label: 'Text' },
  { value: 'url', label: 'URL / Link' },
  { value: 'uid', label: 'Exchange UID' },
  { value: 'wallet', label: 'Wallet address' },
  { value: 'screenshot', label: 'Screenshot' },
  { value: 'tx_hash', label: 'Transaction hash' },
  { value: 'username', label: 'Username / handle' },
];
const DURATIONS = [
  { value: 24, label: '24 hours' },
  { value: 48, label: '48 hours' },
  { value: 72, label: '3 days' },
  { value: 168, label: '7 days' },
  { value: 0, label: 'No deadline' },
];

const STATUS_COLOR = {
  draft: 'default', active: 'success', paused: 'warning',
  closed: 'default', archived: 'default',
};

const EMPTY_FORM = {
  type: 'proof_collection',
  platform: '',
  title: '',
  description: '',
  task_url: '',
  verification_mode: 'manual',
  duration_hours: 24,
  reward_xp: 0,
  reward_label: '',
  max_participants: '',
  one_per_user: true,
  pin_message: true,
  publishNow: false,
  allow_resubmit: false,
  show_leaderboard: false,   // Pro: surface a ranked board (default set per type)
  custom_fields: [],
  multitask: false,   // Pro: campaign holds several sub-tasks
  sequential_tasks: false,  // multi-task: lock each task until the previous is done
  tasks: [],
  raid_goals: {},     // raid type: { likes, retweets, comments, follows }
  social_targets: {}, // social_task: per-action quota { likes, retweets, comments, quotes, follows }
  show_targets: false, // social_task: show the targets/quota live in the group post
};

// Social-task action targets (stored under settings.social_targets). Mirrors
// RAID_GOALS minus none — same provable set; "likes" is honor-only (uncountable).
const SOCIAL_TARGETS = RAID_GOALS;
// Goal-key (plural) → backend per-action key (singular), matching engagement.GOAL_ACTIONS.
const ACTION_KEYS = { likes: 'like', retweets: 'retweet', comments: 'comment', quotes: 'quote', follows: 'follow' };

// Default example/format hint by proof type — pre-fills the helper shown to users.
const EXAMPLE_PLACEHOLDER = {
  text: 'e.g. your answer',
  url: 'https://x.com/yourpost/status/123',
  uid: '123456789 or ABC123',
  wallet: '0x… or your chain address',
  screenshot: '',
  tx_hash: '0x… transaction hash',
  username: '@username',
};

// Type is chosen up-front (via the Create ▾ menu), so the wizard no longer asks
// for it — it opens straight on the task definition. Platform now lives in step 1.
const WIZARD_STEPS = ['Task & Proof', 'Schedule & Reward'];

const EMPTY_TASK = { title: '', type: 'social_task', platform: '', task_url: '', verification_mode: 'manual', reward_xp: 0, reward_label: '', custom_fields: [] };

// Mirrors backend engagement._leaderboard_default_on: a ranked board is meaningful
// for competitive / XP-bearing campaigns, not one-shot collection (UID/wallet/proof).
const leaderboardDefaultOn = (c) =>
  (parseInt(c.reward_xp) || 0) > 0 || (c.tasks?.length || 0) > 0 || ['social_task', 'raid'].includes(c.type);

// Resolve the effective "show leaderboard" state from a campaign's saved settings,
// falling back to the intelligent default when the owner hasn't set a preference.
const leaderboardSettingFor = (c) => {
  const pref = (c.settings || {}).leaderboard;
  return pref === true ? true : pref === false ? false : leaderboardDefaultOn(c);
};

// Reusable proof-fields editor — used for campaign-level fields and per task.
function ProofFieldsEditor({ fields, onChange }) {
  const add = () => onChange([...fields, { label: '', field_type: 'text', required: true, example: '' }]);
  const upd = (i, k, v) => onChange(fields.map((f, idx) => (idx === i ? { ...f, [k]: v } : f)));
  const del = (i) => onChange(fields.filter((_, idx) => idx !== i));
  return (
    <>
      {fields.map((f, i) => (
        <Box key={i} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, p: 1.5 }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <TextField size="small" label="Prompt" placeholder="Submit your Bitget UID" value={f.label}
              onChange={(e) => upd(i, 'label', e.target.value)} sx={{ flex: 1 }} />
            <FormControl size="small" sx={{ minWidth: 130 }}>
              <Select value={f.field_type} onChange={(e) => upd(i, 'field_type', e.target.value)}>
                {FIELD_TYPES.map((t) => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
              </Select>
            </FormControl>
            <Tooltip title={f.required ? 'Required' : 'Optional'}>
              <Switch size="small" checked={f.required} onChange={(e) => upd(i, 'required', e.target.checked)} />
            </Tooltip>
            <IconButton size="small" color="error" onClick={() => del(i)}><Delete fontSize="small" /></IconButton>
          </Box>
          {f.field_type !== 'screenshot' && (
            <TextField size="small" fullWidth sx={{ mt: 1 }}
              label="Example / format (optional, shown to users)"
              placeholder={EXAMPLE_PLACEHOLDER[f.field_type] || ''}
              value={f.example || ''}
              onChange={(e) => upd(i, 'example', e.target.value)} />
          )}
        </Box>
      ))}
      <Button size="small" startIcon={<Add />} onClick={add} sx={{ alignSelf: 'flex-start' }}>
        Add proof field
      </Button>
    </>
  );
}

// Multi-task editor — each task carries its own type/platform/verification/reward
// and proof fields. (Pro feature; backend rejects >1 task for free plans.)
function TasksEditor({ tasks, onChange }) {
  const add = () => onChange([...tasks, { ...EMPTY_TASK }]);
  const upd = (i, k, v) => onChange(tasks.map((t, idx) => (idx === i ? { ...t, [k]: v } : t)));
  const del = (i) => onChange(tasks.filter((_, idx) => idx !== i));
  return (
    <Stack spacing={2}>
      <Typography variant="caption" color="text.secondary">
        Members complete each task separately and earn that task's XP. Each task has its own
        verification and proof fields.
      </Typography>
      {tasks.map((t, i) => (
        <Box key={i} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, p: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="subtitle2" fontWeight={600}>Task {i + 1}</Typography>
            <IconButton size="small" color="error" onClick={() => del(i)}><Delete fontSize="small" /></IconButton>
          </Box>
          <Stack spacing={1.5}>
            <TextField size="small" fullWidth label="Task title" value={t.title}
              onChange={(e) => upd(i, 'title', e.target.value)} />
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <FormControl size="small" sx={{ minWidth: 150, flex: 1 }}>
                <InputLabel>Type</InputLabel>
                <Select value={t.type} label="Type" onChange={(e) => upd(i, 'type', e.target.value)}>
                  {TYPES.map((x) => <MenuItem key={x.value} value={x.value}>{x.emoji} {x.label}</MenuItem>)}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 130, flex: 1 }}>
                <InputLabel>Platform</InputLabel>
                <Select value={t.platform} label="Platform" onChange={(e) => upd(i, 'platform', e.target.value)}>
                  {PLATFORMS.map((p) => <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>)}
                </Select>
              </FormControl>
            </Box>
            <FormControl size="small" fullWidth>
              <InputLabel>Verification</InputLabel>
              <Select value={t.verification_mode} label="Verification" onChange={(e) => upd(i, 'verification_mode', e.target.value)}>
                {VERIFICATION_MODES.map((v) => <MenuItem key={v.value} value={v.value}>{v.label}</MenuItem>)}
              </Select>
            </FormControl>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <TextField size="small" type="number" label="XP" value={t.reward_xp}
                onChange={(e) => upd(i, 'reward_xp', e.target.value)} inputProps={{ min: 0 }} sx={{ width: 110 }} />
              <TextField size="small" label="Task link (optional)" placeholder="https://x.com/..." value={t.task_url}
                onChange={(e) => upd(i, 'task_url', e.target.value)} sx={{ flex: 1, minWidth: 160 }} />
            </Box>
            <Divider textAlign="left"><Typography variant="caption">Proof fields</Typography></Divider>
            <ProofFieldsEditor fields={t.custom_fields || []} onChange={(v) => upd(i, 'custom_fields', v)} />
          </Stack>
        </Box>
      ))}
      <Button size="small" variant="outlined" startIcon={<Add />} onClick={add} sx={{ alignSelf: 'flex-start' }}>
        Add task
      </Button>
    </Stack>
  );
}

// Click-to-view proof screenshot. The image lives on Telegram's servers and is
// fetched on demand (one request per click) as a blob, then shown in a lightbox.
function ScreenshotViewer({ botId, groupId, campaignId, submissionId }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const view = async () => {
    setOpen(true);
    if (url || loading) return;
    setLoading(true); setErr(null);
    try {
      const res = await engagement.submissionFile(botId, groupId, campaignId, submissionId);
      setUrl(URL.createObjectURL(res.data));
    } catch (e) {
      setErr(e.response?.status === 404
        ? 'Image unavailable — the bot may be offline or the file expired on Telegram.'
        : 'Failed to load image.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  return (
    <>
      <Button size="small" variant="text" startIcon={<Visibility fontSize="small" />}
        onClick={view} sx={{ textTransform: 'none', p: 0, minWidth: 0 }}>
        View screenshot
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="md">
        <DialogTitle>Submitted screenshot</DialogTitle>
        <DialogContent>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>
          ) : err ? (
            <Alert severity="warning">{err}</Alert>
          ) : url ? (
            <Box component="img" src={url} alt="Submitted proof"
              sx={{ maxWidth: '100%', maxHeight: '70vh', display: 'block', mx: 'auto', borderRadius: 1 }} />
          ) : null}
        </DialogContent>
        <DialogActions>
          {url && <Button href={url} target="_blank" rel="noopener noreferrer">Open full size</Button>}
          <Button onClick={() => setOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default function CampaignManager({ botId, groupId, userTier = 'free' }) {
  const isPaid = userTier && userTier !== 'free';
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createType, setCreateType] = useState(null);   // non-null => wizard open, pre-set to this type
  const [createAnchor, setCreateAnchor] = useState(null); // Create ▾ menu anchor
  const [typeFilter, setTypeFilter] = useState('all');    // list filter chip
  const [manageId, setManageId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await engagement.list(botId, groupId);
      setCampaigns(res.data.campaigns || []);
    } catch {
      toast.error('Failed to load campaigns');
    } finally {
      setLoading(false);
    }
  }, [botId, groupId]);

  useEffect(() => { load(); }, [load]);

  const totals = campaigns.reduce((acc, c) => {
    acc.total += 1;
    if (c.status === 'active') acc.active += 1;
    acc.submissions += c.submissions_total || 0;
    acc.pending += c.submissions_pending || 0;
    return acc;
  }, { total: 0, active: 0, submissions: 0, pending: 0 });

  // Per-type counts for the filter chips (total + active).
  const byType = TYPES.reduce((m, t) => {
    const list = campaigns.filter((c) => c.type === t.value);
    m[t.value] = { total: list.length, active: list.filter((c) => c.status === 'active').length };
    return m;
  }, {});

  const visibleCampaigns = typeFilter === 'all'
    ? campaigns
    : campaigns.filter((c) => c.type === typeFilter);

  const openCreate = (type) => { setCreateAnchor(null); setCreateType(type); };

  const activeType = TYPES.find((t) => t.value === typeFilter);
  // Create button is context-aware: on a specific type tab it creates that type
  // directly; on "All campaigns" it opens the type picker menu.
  const handleCreateClick = (e) => {
    if (typeFilter === 'all') setCreateAnchor(e.currentTarget);
    else openCreate(typeFilter);
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Box>
          <Typography variant="h6" fontWeight={600}>Engagement Campaigns</Typography>
          <Typography variant="body2" color="text.secondary">
            Run social tasks, content submissions and proof collection. Members participate from Telegram.
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<Add />}
          endIcon={typeFilter === 'all' ? <ArrowDropDown /> : undefined}
          onClick={handleCreateClick}>
          {activeType ? `Create ${activeType.label}` : 'Create'}
        </Button>
        <Menu anchorEl={createAnchor} open={!!createAnchor} onClose={() => setCreateAnchor(null)}>
          {TYPES.map((t) => (
            <MenuItem key={t.value} onClick={() => openCreate(t.value)}>
              <Box component="span" sx={{ mr: 1 }}>{t.emoji}</Box> {t.label}
            </MenuItem>
          ))}
        </Menu>
      </Box>

      {/* Persistent type tabs — All campaigns + one tab per campaign type. Always
          visible so an admin can jump straight to (and create) a single type. */}
      <Tabs
        value={typeFilter}
        onChange={(_, v) => setTypeFilter(v)}
        variant="scrollable"
        scrollButtons="auto"
        allowScrollButtonsMobile
        sx={{
          mb: 2, borderBottom: 1, borderColor: 'divider', minHeight: 38,
          // Compact so all six tabs fit on one row on desktop; scroll on small screens.
          '& .MuiTab-root': {
            minHeight: 38, minWidth: 0, px: 1.25, fontSize: '0.78rem', textTransform: 'none',
          },
        }}
      >
        <Tab value="all" label={`All campaigns (${totals.total})`} />
        {TYPES.map((t) => (
          <Tab
            key={t.value}
            value={t.value}
            label={`${t.emoji} ${t.label} (${byType[t.value]?.total || 0})`}
          />
        ))}
      </Tabs>

      {isPaid ? (
        <Alert severity="success" sx={{ mb: 2 }}>
          Your plan: <strong style={{ textTransform: 'capitalize' }}>{userTier}</strong> — multiple campaigns,
          link-validity checks, advanced fields, winner picker and bulk export are all unlocked.
        </Alert>
      ) : (
        <Alert severity="info" sx={{ mb: 2 }}>
          Free plan: 1 active campaign, manual/honor proof, Telegram-join auto-verify.
          Pro unlocks multiple campaigns, link-validity checks, advanced fields, winner picker and bulk export.
        </Alert>
      )}

      {campaigns.length > 0 && (
        <Grid container spacing={2} sx={{ mb: 2 }}>
          {[
            { label: 'Campaigns', value: totals.total },
            { label: 'Active', value: totals.active, color: 'success.main' },
            { label: 'Submissions', value: totals.submissions },
            { label: 'Pending Review', value: totals.pending, color: 'warning.main' },
          ].map((s) => (
            <Grid item xs={6} sm={3} key={s.label}>
              <Card variant="outlined">
                <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                  <Typography variant="caption" color="text.secondary">{s.label}</Typography>
                  <Typography variant="h5" fontWeight={700} color={s.color || 'text.primary'}>{s.value}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>
      ) : campaigns.length === 0 ? (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 4 }}>
            <CampaignIcon sx={{ fontSize: 40, color: 'text.disabled', mb: 1 }} />
            <Typography color="text.secondary" sx={{ mb: 2 }}>
              {activeType ? `No ${activeType.label} campaigns yet. Create one to engage your community.`
                          : 'No campaigns yet. Create one to engage your community.'}
            </Typography>
            <Button variant="contained" startIcon={<Add />}
              endIcon={typeFilter === 'all' ? <ArrowDropDown /> : undefined}
              onClick={handleCreateClick}>
              {activeType ? `Create ${activeType.label}` : 'Create'}
            </Button>
          </CardContent>
        </Card>
      ) : visibleCampaigns.length === 0 ? (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 4 }}>
            <CampaignIcon sx={{ fontSize: 40, color: 'text.disabled', mb: 1 }} />
            <Typography color="text.secondary" sx={{ mb: 2 }}>
              No {(TYPES.find((t) => t.value === typeFilter) || {}).label} campaigns yet.
            </Typography>
            <Button variant="contained" startIcon={<Add />} onClick={() => openCreate(typeFilter)}>
              Create {(TYPES.find((t) => t.value === typeFilter) || {}).label}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ '& th': { fontWeight: 700, whiteSpace: 'nowrap' } }}>
                <TableCell>Title</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Group post</TableCell>
                <TableCell align="right">Verified</TableCell>
                <TableCell align="right">Pending</TableCell>
                <TableCell align="right">Total</TableCell>
                <TableCell>Deadline</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleCampaigns.map((c) => (
                <CampaignRow
                  key={c.id} c={c} botId={botId} groupId={groupId}
                  onChanged={load} onManage={() => setManageId(c.id)}
                />
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {createType && (
        <CampaignWizard
          botId={botId} groupId={groupId} initialType={createType} isPaid={isPaid}
          onClose={() => setCreateType(null)}
          onCreated={() => { setCreateType(null); load(); }}
        />
      )}
      {manageId != null && (
        <CampaignManageDialog
          botId={botId} groupId={groupId} campaignId={manageId}
          onClose={() => setManageId(null)}
          onChanged={load}
        />
      )}
    </Box>
  );
}

// ── Row + lifecycle menu ──────────────────────────────────────────────────────

function PostStatusCell({ c, botId, groupId, onChanged }) {
  const [posting, setPosting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const map = {
    posted: { label: 'Posted', color: 'success' },
    failed: { label: 'Failed', color: 'error' },
    posting: { label: 'Posting…', color: 'warning' },
    none: { label: 'Not posted', color: 'default' },
  };
  const meta = map[c.post_status] || map.none;
  const canRetry = c.status === 'active' && c.post_status !== 'posted' && c.post_status !== 'posting';
  const canDelete = c.post_status === 'posted' && c.telegram_message_id;

  const doPost = async () => {
    setPosting(true);
    try {
      const res = await engagement.post(botId, groupId, c.id);
      const ps = res.data.campaign?.post_status;
      if (ps === 'posted') toast.success('Posted to group');
      else toast.error(res.data.campaign?.post_error || 'Post failed — will retry');
      onChanged();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to post');
    } finally {
      setPosting(false);
    }
  };

  const doDelete = async () => {
    setDeleting(true);
    try {
      await engagement.deletePost(botId, groupId, c.id);
      toast.success('Group post deleted');
      setConfirmDelete(false);
      onChanged();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to delete post');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, whiteSpace: 'nowrap' }}>
      <Tooltip title={c.post_error || (c.posted_at ? `Posted ${new Date(c.posted_at).toLocaleString()}` : '')}>
        <Chip size="small" label={meta.label} color={meta.color} variant={meta.color === 'default' ? 'outlined' : 'filled'} />
      </Tooltip>
      {canRetry && (
        <Tooltip title="Post to group / retry">
          <span>
            <IconButton size="small" onClick={doPost} disabled={posting}>
              {posting ? <CircularProgress size={14} /> : (c.post_status === 'failed' ? <Replay fontSize="small" /> : <Send fontSize="small" />)}
            </IconButton>
          </span>
        </Tooltip>
      )}
      {canDelete && (
        <Tooltip title="Delete the group post">
          <span>
            <IconButton size="small" color="error" onClick={() => setConfirmDelete(true)} disabled={deleting}>
              {deleting ? <CircularProgress size={14} /> : <DeleteOutline fontSize="small" />}
            </IconButton>
          </span>
        </Tooltip>
      )}
      <Dialog open={confirmDelete} onClose={() => !deleting && setConfirmDelete(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete group post?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            This removes the announcement message from the Telegram group. Submissions and
            rewards are kept, and you can post it again afterwards. Telegram may refuse to
            delete messages older than 48 hours.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(false)} disabled={deleting}>Cancel</Button>
          <Button color="error" variant="contained" onClick={doDelete} disabled={deleting}>
            {deleting ? <CircularProgress size={20} color="inherit" /> : 'Delete post'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// Collapse a long title to a few words; click to expand the full text inline.
// Long titles were wrapping into many rows and making the whole table look messy.
const TITLE_PREVIEW_CHARS = 38;
function TruncatedTitle({ title }) {
  const [open, setOpen] = useState(false);
  const full = title || '';
  const isLong = full.length > TITLE_PREVIEW_CHARS;
  if (!isLong) {
    return <Typography variant="body2" fontWeight={500}>{full || '—'}</Typography>;
  }
  const preview = full.slice(0, TITLE_PREVIEW_CHARS).trimEnd();
  return (
    <Tooltip title={open ? '' : full} placement="top-start">
      <Typography
        variant="body2"
        fontWeight={500}
        onClick={() => setOpen((v) => !v)}
        sx={{ cursor: 'pointer', maxWidth: 240, wordBreak: 'break-word' }}
      >
        {open ? full : `${preview}…`}
        <Typography component="span" variant="caption" color="primary.main" sx={{ ml: 0.5, whiteSpace: 'nowrap' }}>
          {open ? 'less' : 'more'}
        </Typography>
      </Typography>
    </Tooltip>
  );
}

function CampaignRow({ c, botId, groupId, onChanged, onManage }) {
  const [anchor, setAnchor] = useState(null);
  const [editOpen, setEditOpen] = useState(false);

  const act = async (action) => {
    setAnchor(null);
    try {
      await engagement.update(botId, groupId, c.id, { action });
      toast.success(`Campaign ${action}d`);
      onChanged();
    } catch (e) {
      toast.error(e.response?.data?.error || `Failed to ${action}`);
    }
  };

  const lifecycle = [
    c.status !== 'active' && { action: 'publish', label: 'Publish / Activate' },
    c.status === 'active' && { action: 'pause', label: 'Pause' },
    (c.status === 'paused' || c.status === 'closed') && { action: 'reopen', label: 'Reopen' },
    c.status !== 'closed' && c.status !== 'archived' && { action: 'close', label: 'Close' },
    c.status !== 'archived' && { action: 'archive', label: 'Archive' },
  ].filter(Boolean);

  return (
    <TableRow hover sx={{ opacity: c.status === 'archived' ? 0.55 : 1 }}>
      <TableCell sx={{ verticalAlign: 'top' }}>
        <TruncatedTitle title={c.title} />
        {c.platform && <Typography variant="caption" color="text.secondary" display="block">{c.platform}</Typography>}
      </TableCell>
      <TableCell>
        <Typography variant="caption">{(TYPES.find(t => t.value === c.type) || {}).label || c.type}</Typography>
        {c.is_multitask && (
          <Chip size="small" variant="outlined" label={`${c.tasks?.length || 0} tasks`} sx={{ ml: 0.5, height: 18 }} />
        )}
      </TableCell>
      <TableCell><Chip size="small" label={c.status} color={STATUS_COLOR[c.status] || 'default'} /></TableCell>
      <TableCell><PostStatusCell c={c} botId={botId} groupId={groupId} onChanged={onChanged} /></TableCell>
      <TableCell align="right">{c.submissions_verified ?? 0}</TableCell>
      <TableCell align="right">{c.submissions_pending ?? 0}</TableCell>
      <TableCell align="right">{c.submissions_total ?? 0}</TableCell>
      <TableCell>
        <Typography variant="caption" sx={{ whiteSpace: 'nowrap' }}>
          {c.ends_at ? new Date(c.ends_at).toLocaleString() : '—'}
        </Typography>
      </TableCell>
      <TableCell align="right">
        <Tooltip title="Manage & review"><IconButton size="small" onClick={onManage}><Visibility fontSize="small" /></IconButton></Tooltip>
        <IconButton size="small" onClick={(e) => setAnchor(e.currentTarget)}><MoreVert fontSize="small" /></IconButton>
        <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
          <MenuItem onClick={() => { setAnchor(null); setEditOpen(true); }}>Edit campaign</MenuItem>
          <Divider />
          {lifecycle.map((l) => (
            <MenuItem key={l.action} onClick={() => act(l.action)}>{l.label}</MenuItem>
          ))}
        </Menu>
      </TableCell>
      {editOpen && (
        <CampaignEditDialog
          botId={botId} groupId={groupId} campaign={c}
          hasSubmissions={(c.submissions_total || 0) > 0}
          onClose={() => setEditOpen(false)}
          onSaved={() => { setEditOpen(false); onChanged(); }}
        />
      )}
    </TableRow>
  );
}

// ── Create wizard ─────────────────────────────────────────────────────────────

function CampaignWizard({ botId, groupId, initialType, isPaid = false, onClose, onCreated }) {
  const [step, setStep] = useState(0);
  const cfg0 = typeConfig(initialType);
  const [form, setForm] = useState({
    ...EMPTY_FORM,
    type: initialType || EMPTY_FORM.type,
    platform: initialType === 'raid' ? 'x' : EMPTY_FORM.platform,
    platform_other: '',
    // Per-type default verification (honor for social/giveaway, link for content…).
    verification_mode: cfg0.defaultVerification || EMPTY_FORM.verification_mode,
    // Content submissions always collect a link, so seed a required URL field.
    custom_fields: cfg0.autoUrlField
      ? [{ label: 'Your content link', field_type: 'url', required: true, example: 'https://...' }]
      : EMPTY_FORM.custom_fields,
    // Intelligent default: rank competitive types; off for one-shot collection.
    show_leaderboard: ['social_task', 'raid'].includes(initialType),
    auto_verify_x: false,   // raid only, Pro/Enterprise
  });
  const [saving, setSaving] = useState(false);

  const typeMeta = TYPES.find((t) => t.value === form.type) || {};
  const cfg = typeConfig(form.type);

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  // Resolve the platform we persist: raid is locked to X, types without a platform
  // store null, and "Other" sends the free-text the owner typed.
  const resolvedPlatform = () => {
    if (form.type === 'raid') return 'x';
    if (!cfg.showPlatform) return null;
    if (form.platform === 'other') return form.platform_other.trim() || null;
    return form.platform || null;
  };

  const canNext = () => {
    if (step === 0) {
      if (!form.title.trim()) return false;
      if (form.multitask) return form.tasks.some((t) => (t.title || '').trim());
      if (cfg.taskUrlRequired && !form.task_url.trim()) return false;
      return true;
    }
    return true;
  };

  const submit = async () => {
    if (!form.title.trim()) { toast.error('Title is required'); setStep(0); return; }
    if (form.multitask && !form.tasks.some((t) => (t.title || '').trim())) {
      toast.error('Add at least one task'); setStep(0); return;
    }
    if (!form.multitask && cfg.taskUrlRequired && !form.task_url.trim()) {
      toast.error(`${cfg.taskUrlLabel || 'Link'} is required`); setStep(0); return;
    }
    setSaving(true);
    // Clean proof fields. The per-action DM verify flow now collects the X handle
    // once and reuses it (SocialIdentity), so we no longer inject a username field.
    const buildCustomFields = () =>
      form.custom_fields
        .filter((f) => f.label.trim())
        .map((f) => ({
          label: f.label.trim(),
          field_type: f.field_type,
          required: f.required,
          example: (f.example || '').trim() || null,
        }));
    try {
      const payload = {
        type: form.type,
        platform: resolvedPlatform(),
        title: form.title.trim(),
        description: form.description || null,
        task_url: form.task_url || null,
        verification_mode: form.verification_mode,
        reward_xp: parseInt(form.reward_xp) || 0,
        reward_label: form.reward_label || null,
        max_participants: form.max_participants ? parseInt(form.max_participants) : null,
        one_per_user: form.one_per_user,
        pin_message: form.pin_message,
        status: form.publishNow ? 'active' : 'draft',
        settings: {
          allow_resubmit: !!form.allow_resubmit,
          leaderboard: !!form.show_leaderboard,
          ...(form.type === 'raid'
            ? {
                raid_goals: RAID_GOALS.reduce((acc, g) => {
                  const n = parseInt(form.raid_goals[g.key]);
                  if (n > 0) acc[g.key] = n;
                  return acc;
                }, {}),
                ...(isPaid && form.auto_verify_x ? { auto_verify_x: true } : {}),
              }
            : {}),
          ...(form.type === 'social_task'
            ? {
                social_targets: SOCIAL_TARGETS.reduce((acc, g) => {
                  const n = parseInt(form.social_targets[g.key]);
                  if (n > 0) acc[g.key] = n;
                  return acc;
                }, {}),
                show_targets: !!form.show_targets,
                ...(isPaid && form.auto_verify_x && form.platform === 'x' ? { auto_verify_x: true } : {}),
              }
            : {}),
          ...(form.multitask && form.sequential_tasks ? { sequential_tasks: true } : {}),
        },
        custom_fields: form.multitask ? [] : buildCustomFields(),
      };
      if (form.multitask) {
        payload.tasks = form.tasks
          .filter((t) => (t.title || '').trim())
          .map((t) => ({
            title: t.title.trim(),
            type: t.type,
            platform: t.platform || null,
            task_url: t.task_url || null,
            verification_mode: t.verification_mode,
            reward_xp: parseInt(t.reward_xp) || 0,
            reward_label: t.reward_label || null,
            custom_fields: (t.custom_fields || [])
              .filter((f) => f.label.trim())
              .map((f) => ({
                label: f.label.trim(),
                field_type: f.field_type,
                required: f.required,
                example: (f.example || '').trim() || null,
              })),
          }));
      }
      if (form.duration_hours) payload.duration_hours = form.duration_hours;
      await engagement.create(botId, groupId, payload);
      toast.success(form.publishNow ? 'Campaign created & activated' : 'Campaign saved as draft');
      onCreated();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to create campaign');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Box component="span" sx={{ mr: 1 }}>{typeMeta.emoji}</Box>
        Create {typeMeta.label || 'Campaign'}
      </DialogTitle>
      <DialogContent>
        <Stepper activeStep={step} sx={{ mb: 3, mt: 1 }} alternativeLabel>
          {WIZARD_STEPS.map((s) => <Step key={s}><StepLabel>{s}</StepLabel></Step>)}
        </Stepper>

        {step === 0 && (
          <Stack spacing={2}>
            {typeMeta.help && (
              <Typography variant="caption" color="text.secondary">{typeMeta.help}</Typography>
            )}
            <TextField fullWidth label="Title" value={form.title} onChange={(e) => set('title', e.target.value)} />

            <FormControlLabel
              control={<Switch checked={form.multitask} onChange={(e) => set('multitask', e.target.checked)} />}
              label="Multiple tasks (Pro) — one campaign, several tasks"
            />

            {form.multitask ? (
              <Stack spacing={2}>
                <TextField fullWidth multiline minRows={2} label="Campaign intro / description"
                  value={form.description} onChange={(e) => set('description', e.target.value)} />
                <Divider textAlign="left"><Typography variant="caption">Tasks</Typography></Divider>
                <TasksEditor tasks={form.tasks} onChange={(v) => set('tasks', v)} />
                <FormControlLabel
                  control={<Switch checked={form.sequential_tasks} onChange={(e) => set('sequential_tasks', e.target.checked)} />}
                  label="Sequential — lock each task until the previous one is completed"
                />
              </Stack>
            ) : (
              <>
                {cfg.showPlatform && (
                  <>
                    <FormControl fullWidth>
                      <InputLabel>{cfg.platformRequired ? 'Platform *' : 'Platform'}</InputLabel>
                      <Select value={form.platform} label={cfg.platformRequired ? 'Platform *' : 'Platform'}
                        onChange={(e) => set('platform', e.target.value)}>
                        {PLATFORMS.map((p) => <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>)}
                      </Select>
                    </FormControl>
                    {form.platform === 'other' && (
                      <TextField fullWidth label="Platform name (shown to members)"
                        placeholder="e.g. Discord, TikTok, Reddit"
                        value={form.platform_other} onChange={(e) => set('platform_other', e.target.value)} />
                    )}
                  </>
                )}
                <TextField fullWidth multiline minRows={2} label="Instructions / Description"
                  value={form.description} onChange={(e) => set('description', e.target.value)} />
                <TextField fullWidth required={!!cfg.taskUrlRequired}
                  label={cfg.taskUrlLabel || 'Task Link (optional)'}
                  placeholder="https://x.com/..." value={form.task_url} onChange={(e) => set('task_url', e.target.value)} />
                {form.type === 'raid' && (
                  <Box>
                    <Typography variant="caption" color="text.secondary">Raid goals (shown as targets in the group post)</Typography>
                    <Grid container spacing={1} sx={{ mt: 0.5 }}>
                      {RAID_GOALS.map((g) => (
                        <Grid item xs={6} key={g.key}>
                          <TextField fullWidth size="small" type="number" label={g.label}
                            value={form.raid_goals[g.key] || ''}
                            onChange={(e) => set('raid_goals', { ...form.raid_goals, [g.key]: e.target.value })}
                            inputProps={{ min: 0 }} />
                        </Grid>
                      ))}
                    </Grid>
                    <FormControlLabel
                      sx={{ mt: 1 }}
                      control={
                        <Switch
                          checked={isPaid && form.auto_verify_x}
                          disabled={!isPaid}
                          onChange={(e) => set('auto_verify_x', e.target.checked)}
                        />
                      }
                      label="Auto-verify on X (Pro) — confirm likes / retweets / comments / follows in real time"
                    />
                    {form.auto_verify_x && isPaid && (
                      <Typography variant="caption" color="text.secondary" display="block">
                        Members are asked for their X @username so the bot can verify automatically.
                        Retweets, comments, quote-tweets and follows verify in real time; <strong>likes
                        can’t be auto-verified</strong> (X keeps likes private) so a raid that includes a
                        likes goal stays pending for your manual review.
                      </Typography>
                    )}
                    {!isPaid && (
                      <Typography variant="caption" color="text.secondary" display="block">
                        Real-time X verification is a Pro/Enterprise feature. You can still run the raid
                        with manual proof review.
                      </Typography>
                    )}
                  </Box>
                )}
                {form.type === 'social_task' && (
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Targets (optional) — how many of each action you want
                    </Typography>
                    <Grid container spacing={1} sx={{ mt: 0.5 }}>
                      {SOCIAL_TARGETS.map((g) => (
                        <Grid item xs={6} key={g.key}>
                          <TextField fullWidth size="small" type="number" label={g.label}
                            value={form.social_targets[g.key] || ''}
                            onChange={(e) => set('social_targets', { ...form.social_targets, [g.key]: e.target.value })}
                            inputProps={{ min: 0 }} />
                        </Grid>
                      ))}
                    </Grid>
                    <FormControlLabel
                      sx={{ mt: 1 }}
                      control={<Switch checked={form.show_targets} onChange={(e) => set('show_targets', e.target.checked)} />}
                      label="Show targets publicly — display a live quota in the group post"
                    />
                    <Typography variant="caption" color="text.secondary" display="block">
                      {form.show_targets
                        ? 'The group post shows each target and updates as people are verified (e.g. “40 reposts left”). Likes are honor-based and counted by verified submissions — X keeps real likes private.'
                        : 'Targets stay private — you’ll see verified progress in Manage. Turn this on to show a live countdown to members.'}
                    </Typography>
                    {form.platform === 'x' && (
                      <>
                        <FormControlLabel
                          sx={{ mt: 1 }}
                          control={
                            <Switch checked={isPaid && form.auto_verify_x} disabled={!isPaid}
                              onChange={(e) => set('auto_verify_x', e.target.checked)} />
                          }
                          label="Auto-verify on X (Pro) — check reposts / comments / quotes / follows in real time"
                        />
                        <Typography variant="caption" color="text.secondary" display="block">
                          {isPaid
                            ? 'Members do each action in the bot DM and tap Verify; reposts, comments, quotes and follows are checked live, likes are accepted automatically (X keeps likes private). Off → everything goes to manual review.'
                            : 'Real-time X verification is a Pro/Enterprise feature. On the free plan members still do the actions in the DM, but you approve them manually.'}
                        </Typography>
                      </>
                    )}
                  </Box>
                )}
                <FormControl fullWidth>
                  <InputLabel>Verification</InputLabel>
                  <Select value={form.verification_mode} label="Verification" onChange={(e) => set('verification_mode', e.target.value)}>
                    {VERIFICATION_MODES.map((v) => <MenuItem key={v.value} value={v.value}>{v.label}</MenuItem>)}
                  </Select>
                </FormControl>

                <Divider textAlign="left"><Typography variant="caption">Proof fields</Typography></Divider>
                <Typography variant="caption" color="text.secondary">
                  {cfg.proofHint || 'Ask participants for proof (UID, link, wallet, screenshot…). The bot collects each field privately and validates the format before accepting it.'}
                </Typography>
                <ProofFieldsEditor fields={form.custom_fields} onChange={(v) => set('custom_fields', v)} />
              </>
            )}
          </Stack>
        )}

        {step === 1 && (
          <Stack spacing={2}>
            <FormControl fullWidth>
              <InputLabel>Deadline</InputLabel>
              <Select value={form.duration_hours} label="Deadline" onChange={(e) => set('duration_hours', e.target.value)}>
                {DURATIONS.map((d) => <MenuItem key={d.value} value={d.value}>{d.label}</MenuItem>)}
              </Select>
            </FormControl>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <TextField fullWidth type="number" label="XP Reward" value={form.reward_xp}
                  onChange={(e) => set('reward_xp', e.target.value)} inputProps={{ min: 0 }} />
              </Grid>
              <Grid item xs={6}>
                <TextField fullWidth label="Reward Label" placeholder="Giveaway entry"
                  value={form.reward_label} onChange={(e) => set('reward_label', e.target.value)} />
              </Grid>
            </Grid>
            <TextField fullWidth type="number" label="Max participants (optional)"
              value={form.max_participants} onChange={(e) => set('max_participants', e.target.value)} inputProps={{ min: 1 }} />
            <FormControlLabel control={<Switch checked={form.one_per_user} onChange={(e) => set('one_per_user', e.target.checked)} />}
              label="One submission per user" />
            <FormControlLabel control={<Switch checked={form.allow_resubmit} onChange={(e) => set('allow_resubmit', e.target.checked)} />}
              label="Allow resubmission after rejection" />
            <FormControlLabel control={<Switch checked={form.pin_message} onChange={(e) => set('pin_message', e.target.checked)} />}
              label="Pin the group announcement" />
            <FormControlLabel control={<Switch checked={form.show_leaderboard} onChange={(e) => set('show_leaderboard', e.target.checked)} />}
              label="Show leaderboard (Pro) — rank participants by XP / tasks completed" />
            <FormControlLabel control={<Switch checked={form.publishNow} onChange={(e) => set('publishNow', e.target.checked)} />}
              label="Activate now (otherwise saved as draft)" />
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        {step > 0 && <Button onClick={() => setStep(step - 1)}>Back</Button>}
        {step < WIZARD_STEPS.length - 1
          ? <Button variant="contained" disabled={!canNext()} onClick={() => setStep(step + 1)}>Next</Button>
          : <Button variant="contained" disabled={saving} onClick={submit}>
              {saving ? <CircularProgress size={20} color="inherit" /> : 'Create'}
            </Button>}
      </DialogActions>
    </Dialog>
  );
}

// ── Manage / review dialog ────────────────────────────────────────────────────

function CampaignManageDialog({ botId, groupId, campaignId, onClose, onChanged }) {
  const [campaign, setCampaign] = useState(null);
  const [subs, setSubs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [winners, setWinners] = useState([]);
  const [rejectFor, setRejectFor] = useState(null);  // submission pending a reject reason
  const [rejectReason, setRejectReason] = useState('');
  const [tab, setTab] = useState(0);                 // 0 = Submissions, 1 = Leaderboard
  const [editing, setEditing] = useState(false);     // edit-campaign dialog open

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cRes, sRes] = await Promise.all([
        engagement.get(botId, groupId, campaignId),
        engagement.listSubmissions(botId, groupId, campaignId),
      ]);
      setCampaign(cRes.data.campaign);
      setSubs(sRes.data.submissions || []);
      setWinners((cRes.data.campaign.settings || {}).winners || []);
    } catch {
      toast.error('Failed to load campaign');
    } finally {
      setLoading(false);
    }
  }, [botId, groupId, campaignId]);

  useEffect(() => { load(); }, [load]);

  const review = async (subId, action, reason) => {
    try {
      await engagement.reviewSubmission(botId, groupId, campaignId, subId, { action, reason });
      toast.success(action === 'approve' ? 'Approved' : 'Rejected');
      setRejectFor(null);
      setRejectReason('');
      load();
      onChanged?.();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed');
    }
  };

  const tasks = campaign?.tasks || [];
  const isMulti = tasks.length > 0;
  const taskTitle = (tid) => (tasks.find((t) => t.id === tid) || {}).title || (tid ? `Task ${tid}` : '—');
  // Field map spans campaign-level + all task-level fields (multi-task safe).
  const fieldMap = [...(campaign?.custom_fields || []), ...tasks.flatMap((t) => t.custom_fields || [])]
    .reduce((m, f) => { m[f.key] = f; return m; }, {});
  const FIELD_TYPE_LABEL = FIELD_TYPES.reduce((m, t) => { m[t.value] = t.label; return m; }, {});

  const exportCsv = async () => {
    try {
      const res = await engagement.exportCsv(botId, groupId, campaignId);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `campaign_${campaignId}_submissions.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      toast.error('Export failed');
    }
  };

  const pickWinners = async () => {
    const verified = subs.filter((s) => s.status === 'verified');
    if (verified.length === 0) { toast.info('No verified submissions to pick from'); return; }
    const count = Math.min(3, verified.length);
    const shuffled = [...verified].sort(() => Math.random() - 0.5).slice(0, count);
    const picked = shuffled.map((s) => ({ id: s.id, telegram_user_id: s.telegram_user_id, telegram_username: s.telegram_username }));
    try {
      const mergedSettings = { ...(campaign.settings || {}), winners: picked };
      await engagement.update(botId, groupId, campaignId, { settings: mergedSettings });
      setWinners(picked);
      toast.success(`Picked ${picked.length} winner(s)`);
    } catch {
      toast.error('Failed to save winners');
    }
  };

  const renderPayload = (s) => {
    const allEntries = Object.entries(s.payload || {}).filter(([, v]) => v !== '' && v != null && v !== '[screenshot]');
    // Per-action verify submissions store a structured { action: {status} } map.
    const actionsMap = (s.payload || {}).actions;
    const entries = allEntries.filter(([k]) => k !== 'actions');
    if (entries.length === 0 && !actionsMap && !s.file_id) return <Typography variant="caption" color="text.disabled">—</Typography>;
    return (
      <Box>
        {actionsMap && typeof actionsMap === 'object' && (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 0.5 }}>
            {SOCIAL_TARGETS.map((g) => {
              const st = (actionsMap[ACTION_KEYS[g.key]] || {}).status;
              if (!st) return null;
              const color = st === 'verified' ? 'success' : st === 'failed' ? 'error' : 'default';
              return <Chip key={g.key} size="small" color={color} variant="outlined" label={`${g.label}: ${st}`} />;
            })}
          </Box>
        )}
        {entries.map(([k, v]) => {
          const f = fieldMap[k];
          const typeLabel = f ? (FIELD_TYPE_LABEL[f.field_type] || f.field_type) : null;
          const label = f ? f.label : k;
          return (
            <Typography key={k} variant="caption" display="block">
              <strong>{label}{typeLabel ? ` (${typeLabel})` : ''}:</strong> {String(v)}
            </Typography>
          );
        })}
        {s.file_id && (
          <ScreenshotViewer botId={botId} groupId={groupId} campaignId={campaignId} submissionId={s.id} />
        )}
      </Box>
    );
  };

  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        {campaign ? campaign.title : 'Campaign'}
        {campaign && <Chip size="small" label={campaign.status} color={STATUS_COLOR[campaign.status] || 'default'} sx={{ ml: 1 }} />}
      </DialogTitle>
      <DialogContent>
        {loading || !campaign ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>
        ) : (
          <>
            <Stack direction="row" spacing={2} sx={{ mb: 2, flexWrap: 'wrap' }}>
              <Typography variant="body2"><strong>Type:</strong> {campaign.type}</Typography>
              {campaign.platform && <Typography variant="body2"><strong>Platform:</strong> {campaign.platform}</Typography>}
              <Typography variant="body2"><strong>Verification:</strong> {campaign.verification_mode}</Typography>
              {campaign.reward_xp ? <Typography variant="body2"><strong>XP:</strong> {campaign.reward_xp}</Typography> : null}
              {campaign.reward_label && <Typography variant="body2"><strong>Reward:</strong> {campaign.reward_label}</Typography>}
              {campaign.ends_at && <Typography variant="body2"><strong>Ends:</strong> {new Date(campaign.ends_at).toLocaleString()}</Typography>}
            </Stack>

            <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
              <Button size="small" variant="outlined" startIcon={<Edit />} onClick={() => setEditing(true)}>Edit</Button>
              <Button size="small" startIcon={<Download />} onClick={exportCsv}>Export CSV</Button>
              <Button size="small" startIcon={<EmojiEvents />} onClick={pickWinners}>Pick Winners</Button>
            </Stack>

            {winners.length > 0 && (
              <Alert severity="success" icon={<EmojiEvents fontSize="inherit" />} sx={{ mb: 2 }}>
                Winners: {winners.map((w) => w.telegram_username ? `@${w.telegram_username}` : w.telegram_user_id).join(', ')}
              </Alert>
            )}

            {campaign.status === 'active' && campaign.post_status !== 'posted' && (
              <Alert
                severity={campaign.post_status === 'failed' ? 'error' : 'warning'}
                sx={{ mb: 2 }}
                action={
                  <Button color="inherit" size="small" startIcon={<Send />} onClick={async () => {
                    try {
                      const res = await engagement.post(botId, groupId, campaignId);
                      const ps = res.data.campaign?.post_status;
                      if (ps === 'posted') toast.success('Posted to group'); else toast.error('Post failed — will retry');
                      load(); onChanged?.();
                    } catch (e) { toast.error(e.response?.data?.error || 'Failed to post'); }
                  }}>Post to group</Button>
                }
              >
                {campaign.post_status === 'failed'
                  ? `Group post failed: ${campaign.post_error || 'unknown error'}`
                  : 'This campaign has not been posted to the group yet.'}
              </Alert>
            )}
            {campaign.post_status === 'posted' && campaign.posted_at && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
                <Typography variant="caption" color="text.secondary">
                  Posted to group {new Date(campaign.posted_at).toLocaleString()}
                  {campaign.telegram_message_id ? ` · msg #${campaign.telegram_message_id}` : ''}
                </Typography>
                {campaign.telegram_message_id && (
                  <Button size="small" color="error" startIcon={<DeleteOutline />} onClick={async () => {
                    if (!window.confirm('Delete the group announcement message from Telegram? Submissions are kept and you can repost afterwards.')) return;
                    try {
                      await engagement.deletePost(botId, groupId, campaignId);
                      toast.success('Group post deleted');
                      load(); onChanged?.();
                    } catch (e) { toast.error(e.response?.data?.error || 'Failed to delete post'); }
                  }}>Delete post</Button>
                )}
              </Box>
            )}

            <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}>
              <Tab label={`Submissions (${subs.length})`} />
              <Tab icon={<EmojiEvents fontSize="small" />} iconPosition="start" label="Leaderboard" />
            </Tabs>

            {tab === 1 ? (
              <CampaignLeaderboard botId={botId} groupId={groupId} campaignId={campaignId} />
            ) : subs.length === 0 ? (
              <Typography variant="body2" color="text.secondary">No submissions yet.</Typography>
            ) : (
              <TableContainer component={Paper} variant="outlined" sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ '& th': { fontWeight: 700, whiteSpace: 'nowrap' } }}>
                      <TableCell>User</TableCell>
                      {isMulti && <TableCell>Task</TableCell>}
                      <TableCell>Proof</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Submitted</TableCell>
                      <TableCell align="right">Review</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {subs.map((s) => (
                      <TableRow key={s.id} hover>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                            <Typography variant="body2">{s.telegram_username ? `@${s.telegram_username}` : `User ${s.telegram_user_id}`}</Typography>
                            {s.flagged && (
                              <Tooltip title={s.flag_reason || 'Flagged for review'}>
                                <Chip size="small" color="warning" label="⚠ dup" />
                              </Tooltip>
                            )}
                          </Box>
                          <Typography variant="caption" color="text.secondary">ID: {s.telegram_user_id}</Typography>
                        </TableCell>
                        {isMulti && (
                          <TableCell><Typography variant="caption">{taskTitle(s.task_id)}</Typography></TableCell>
                        )}
                        <TableCell>{renderPayload(s)}</TableCell>
                        <TableCell>
                          <Chip size="small" label={s.status}
                            color={s.status === 'verified' ? 'success' : s.status === 'rejected' ? 'error' : 'warning'} />
                          {s.rewarded && (
                            <Typography variant="caption" display="block" color="success.main">
                              +{s.task_id ? ((tasks.find((t) => t.id === s.task_id) || {}).reward_xp || 0) : campaign.reward_xp} XP
                            </Typography>
                          )}
                          {s.reviewed_at && (
                            <Typography variant="caption" display="block" color="text.secondary">
                              by {s.reviewed_by || '—'}
                            </Typography>
                          )}
                          {s.status === 'rejected' && s.review_reason && (
                            <Typography variant="caption" display="block" color="error.main">{s.review_reason}</Typography>
                          )}
                          {s.notify_status === 'sent' && <Typography variant="caption" display="block" color="text.secondary">🔔 user notified</Typography>}
                          {s.notify_status === 'failed' && (
                            <Tooltip title={s.notify_error || 'User blocked/never started the bot'}>
                              <Typography variant="caption" display="block" color="warning.main">🔕 notify failed</Typography>
                            </Tooltip>
                          )}
                        </TableCell>
                        <TableCell><Typography variant="caption" sx={{ whiteSpace: 'nowrap' }}>{new Date(s.created_at).toLocaleString()}</Typography></TableCell>
                        <TableCell align="right">
                          <Tooltip title={s.status === 'verified' ? 'Approved' : 'Approve'}>
                            <span>
                              <IconButton size="small" color="success" disabled={s.status === 'verified'} onClick={() => review(s.id, 'approve')}><CheckCircle fontSize="small" /></IconButton>
                            </span>
                          </Tooltip>
                          <Tooltip title={s.status === 'rejected' ? 'Rejected' : 'Reject'}>
                            <span>
                              <IconButton size="small" color="error" disabled={s.status === 'rejected'} onClick={() => { setRejectFor(s); setRejectReason(s.review_reason || ''); }}><Cancel fontSize="small" /></IconButton>
                            </span>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>

      <Dialog open={!!rejectFor} onClose={() => setRejectFor(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Reject submission</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            The participant is notified with this reason (if they’ve started the bot). No XP is credited.
          </Typography>
          <TextField
            autoFocus fullWidth multiline minRows={2} label="Reason (optional)"
            value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
            placeholder="e.g. UID does not match — please resend"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejectFor(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={() => review(rejectFor.id, 'reject', rejectReason)}>Reject</Button>
        </DialogActions>
      </Dialog>

      {editing && campaign && (
        <CampaignEditDialog
          botId={botId} groupId={groupId} campaign={campaign}
          hasSubmissions={subs.length > 0}
          onClose={() => setEditing(false)}
          onSaved={() => { setEditing(false); load(); onChanged?.(); }}
        />
      )}
    </Dialog>
  );
}

// ── Edit existing campaign ─────────────────────────────────────────────────────

function CampaignEditDialog({ botId, groupId, campaign, hasSubmissions, onClose, onSaved }) {
  const tasks0 = campaign.tasks || [];
  const isMulti = tasks0.length > 0;
  // Tasks / proof fields are locked once members have submitted (backend refuses to
  // replace tasks with existing submissions — protects their data). Details,
  // reward, deadline and visibility stay editable.
  const structureLocked = hasSubmissions;
  const cfgE = typeConfig(campaign.type);
  // A saved platform that isn't one of the preset values is a custom "Other" name.
  const knownPlatform = !campaign.platform || PLATFORMS.some((p) => p.value === campaign.platform);

  const [form, setForm] = useState({
    title: campaign.title || '',
    description: campaign.description || '',
    platform: knownPlatform ? (campaign.platform || '') : 'other',
    platform_other: knownPlatform ? '' : (campaign.platform || ''),
    task_url: campaign.task_url || '',
    verification_mode: campaign.verification_mode || 'manual',
    reward_xp: campaign.reward_xp || 0,
    reward_label: campaign.reward_label || '',
    ends_at: campaign.ends_at ? String(campaign.ends_at).slice(0, 16) : '',
    max_participants: campaign.max_participants || '',
    one_per_user: !!campaign.one_per_user,
    pin_message: !!campaign.pin_message,
    allow_resubmit: !!(campaign.settings || {}).allow_resubmit,
    show_leaderboard: leaderboardSettingFor(campaign),
    multitask: isMulti,
    custom_fields: (campaign.custom_fields || []).map((f) => ({
      label: f.label, field_type: f.field_type, required: f.required, example: f.example || '',
    })),
    tasks: tasks0.map((t) => ({
      title: t.title, type: t.type, platform: t.platform || '', task_url: t.task_url || '',
      verification_mode: t.verification_mode, reward_xp: t.reward_xp || 0, reward_label: t.reward_label || '',
      custom_fields: (t.custom_fields || []).map((f) => ({
        label: f.label, field_type: f.field_type, required: f.required, example: f.example || '',
      })),
    })),
    raid_goals: (campaign.settings || {}).raid_goals || {},
    social_targets: (campaign.settings || {}).social_targets || {},
    show_targets: !!(campaign.settings || {}).show_targets,
    auto_verify_x: !!(campaign.settings || {}).auto_verify_x,
    sequential_tasks: !!(campaign.settings || {}).sequential_tasks,
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const save = async () => {
    if (!form.title.trim()) { toast.error('Title is required'); return; }
    setSaving(true);
    try {
      const cleanFields = (arr) => (arr || []).filter((f) => f.label.trim()).map((f) => ({
        label: f.label.trim(), field_type: f.field_type, required: f.required,
        example: (f.example || '').trim() || null,
      }));
      const payload = {
        title: form.title.trim(),
        description: form.description || null,
        task_url: form.task_url || null,
        platform: !cfgE.showPlatform ? (campaign.platform || null)
          : form.platform === 'other' ? (form.platform_other.trim() || null)
          : (form.platform || null),
        verification_mode: form.verification_mode,
        reward_xp: parseInt(form.reward_xp) || 0,
        reward_label: form.reward_label || null,
        max_participants: form.max_participants ? parseInt(form.max_participants) : null,
        one_per_user: form.one_per_user,
        pin_message: form.pin_message,
        ends_at: form.ends_at || null,
        // Merge settings so we never drop winners / verify_chat / branding flags.
        settings: {
          ...(campaign.settings || {}),
          allow_resubmit: !!form.allow_resubmit,
          leaderboard: !!form.show_leaderboard,
          ...(campaign.type === 'raid'
            ? {
                raid_goals: RAID_GOALS.reduce((acc, g) => {
                  const n = parseInt(form.raid_goals[g.key]);
                  if (n > 0) acc[g.key] = n;
                  return acc;
                }, {}),
              }
            : {}),
          ...(campaign.type === 'social_task'
            ? {
                social_targets: SOCIAL_TARGETS.reduce((acc, g) => {
                  const n = parseInt(form.social_targets[g.key]);
                  if (n > 0) acc[g.key] = n;
                  return acc;
                }, {}),
                show_targets: !!form.show_targets,
                auto_verify_x: campaign.platform === 'x' ? !!form.auto_verify_x : false,
              }
            : {}),
          ...(isMulti ? { sequential_tasks: !!form.sequential_tasks } : {}),
        },
      };
      // Only touch tasks / fields when they're editable (no submissions yet).
      if (!structureLocked) {
        if (form.multitask) {
          payload.custom_fields = [];
          payload.tasks = form.tasks.filter((t) => (t.title || '').trim()).map((t) => ({
            title: t.title.trim(), type: t.type, platform: t.platform || null,
            task_url: t.task_url || null, verification_mode: t.verification_mode,
            reward_xp: parseInt(t.reward_xp) || 0, reward_label: t.reward_label || null,
            custom_fields: cleanFields(t.custom_fields),
          }));
        } else {
          payload.custom_fields = cleanFields(form.custom_fields);
        }
      }
      await engagement.update(botId, groupId, campaign.id, payload);
      toast.success('Campaign updated');
      onSaved();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to update campaign');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Edit campaign</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {structureLocked && (
            <Alert severity="info">
              This campaign has submissions, so its {isMulti ? 'tasks' : 'proof fields'} are locked to
              protect existing data. You can still edit the details, reward, deadline and visibility.
            </Alert>
          )}
          <TextField fullWidth label="Title" value={form.title} onChange={(e) => set('title', e.target.value)} />
          <TextField fullWidth multiline minRows={2} label={isMulti ? 'Campaign intro / description' : 'Instructions / Description'}
            value={form.description} onChange={(e) => set('description', e.target.value)} />

          {!isMulti && (
            <>
              {cfgE.showPlatform && (
                <>
                  <FormControl fullWidth>
                    <InputLabel>Platform</InputLabel>
                    <Select value={form.platform} label="Platform" onChange={(e) => set('platform', e.target.value)}>
                      {PLATFORMS.map((p) => <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>)}
                    </Select>
                  </FormControl>
                  {form.platform === 'other' && (
                    <TextField fullWidth label="Platform name (shown to members)"
                      placeholder="e.g. Discord, TikTok, Reddit"
                      value={form.platform_other} onChange={(e) => set('platform_other', e.target.value)} />
                  )}
                </>
              )}
              <TextField fullWidth label={cfgE.taskUrlLabel || 'Task Link (optional)'}
                placeholder="https://x.com/..." value={form.task_url} onChange={(e) => set('task_url', e.target.value)} />
              <FormControl fullWidth>
                <InputLabel>Verification</InputLabel>
                <Select value={form.verification_mode} label="Verification" onChange={(e) => set('verification_mode', e.target.value)}>
                  {VERIFICATION_MODES.map((v) => <MenuItem key={v.value} value={v.value}>{v.label}</MenuItem>)}
                </Select>
              </FormControl>
            </>
          )}

          {campaign.type === 'raid' && (
            <Box>
              <Typography variant="caption" color="text.secondary">Raid goals (shown as targets in the group post)</Typography>
              <Grid container spacing={1} sx={{ mt: 0.5 }}>
                {RAID_GOALS.map((g) => (
                  <Grid item xs={6} key={g.key}>
                    <TextField fullWidth size="small" type="number" label={g.label}
                      value={form.raid_goals[g.key] || ''}
                      onChange={(e) => set('raid_goals', { ...form.raid_goals, [g.key]: e.target.value })}
                      inputProps={{ min: 0 }} />
                  </Grid>
                ))}
              </Grid>
            </Box>
          )}

          {campaign.type === 'social_task' && (
            <Box>
              <Typography variant="caption" color="text.secondary">Targets (optional) — how many of each action you want</Typography>
              <Grid container spacing={1} sx={{ mt: 0.5 }}>
                {SOCIAL_TARGETS.map((g) => (
                  <Grid item xs={6} key={g.key}>
                    <TextField fullWidth size="small" type="number" label={g.label}
                      value={form.social_targets[g.key] || ''}
                      onChange={(e) => set('social_targets', { ...form.social_targets, [g.key]: e.target.value })}
                      inputProps={{ min: 0 }} />
                  </Grid>
                ))}
              </Grid>
              <FormControlLabel
                sx={{ mt: 1 }}
                control={<Switch checked={form.show_targets} onChange={(e) => set('show_targets', e.target.checked)} />}
                label="Show targets publicly — display a live quota in the group post" />
              {campaign.platform === 'x' && (
                <FormControlLabel
                  control={<Switch checked={form.auto_verify_x} onChange={(e) => set('auto_verify_x', e.target.checked)} />}
                  label="Auto-verify on X (Pro) — check reposts / comments / quotes / follows in real time" />
              )}
            </Box>
          )}

          <Grid container spacing={2}>
            <Grid item xs={6}>
              <TextField fullWidth type="number" label="XP Reward" value={form.reward_xp}
                onChange={(e) => set('reward_xp', e.target.value)} inputProps={{ min: 0 }} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Reward Label" placeholder="Giveaway entry"
                value={form.reward_label} onChange={(e) => set('reward_label', e.target.value)} />
            </Grid>
          </Grid>
          <TextField fullWidth type="datetime-local" label="Deadline (UTC)" InputLabelProps={{ shrink: true }}
            value={form.ends_at} onChange={(e) => set('ends_at', e.target.value)}
            helperText="Leave empty for no deadline." />
          <TextField fullWidth type="number" label="Max participants (optional)"
            value={form.max_participants} onChange={(e) => set('max_participants', e.target.value)} inputProps={{ min: 1 }} />

          <FormControlLabel control={<Switch checked={form.one_per_user} onChange={(e) => set('one_per_user', e.target.checked)} />}
            label="One submission per user" />
          <FormControlLabel control={<Switch checked={form.allow_resubmit} onChange={(e) => set('allow_resubmit', e.target.checked)} />}
            label="Allow resubmission after rejection" />
          <FormControlLabel control={<Switch checked={form.pin_message} onChange={(e) => set('pin_message', e.target.checked)} />}
            label="Pin the group announcement" />
          <FormControlLabel control={<Switch checked={form.show_leaderboard} onChange={(e) => set('show_leaderboard', e.target.checked)} />}
            label="Show leaderboard (Pro) — rank participants by XP / tasks completed" />

          {!structureLocked && !isMulti && (
            <>
              <Divider textAlign="left"><Typography variant="caption">Proof fields</Typography></Divider>
              <ProofFieldsEditor fields={form.custom_fields} onChange={(v) => set('custom_fields', v)} />
            </>
          )}
          {isMulti && (
            <FormControlLabel
              control={<Switch checked={form.sequential_tasks} onChange={(e) => set('sequential_tasks', e.target.checked)} />}
              label="Sequential — lock each task until the previous one is completed" />
          )}
          {!structureLocked && isMulti && (
            <>
              <Divider textAlign="left"><Typography variant="caption">Tasks</Typography></Divider>
              <TasksEditor tasks={form.tasks} onChange={(v) => set('tasks', v)} />
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={saving}>
          {saving ? <CircularProgress size={20} color="inherit" /> : 'Save changes'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Per-campaign leaderboard (Pro) ──────────────────────────────────────────────

const RANK_MEDAL = { 1: '🥇', 2: '🥈', 3: '🥉' };

function CampaignLeaderboard({ botId, groupId, campaignId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true); setLocked(false); setError(null);
      try {
        const res = await engagement.leaderboard(botId, groupId, campaignId, { limit: 100 });
        if (active) setData(res.data);
      } catch (e) {
        if (!active) return;
        if (e.response?.status === 403) setLocked(true);
        else setError(e.response?.data?.error || 'Failed to load leaderboard');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [botId, groupId, campaignId]);

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>;
  if (locked) {
    return (
      <Alert severity="info" icon={<EmojiEvents fontSize="inherit" />}>
        Per-campaign leaderboards are a <strong>Pro</strong> feature. Upgrade to rank participants
        by verified submissions and XP earned — your members see their own rank too.
      </Alert>
    );
  }
  if (error) return <Alert severity="error">{error}</Alert>;

  const entries = data?.entries || [];
  if (entries.length === 0) {
    return <Typography variant="body2" color="text.secondary">No verified participants yet.</Typography>;
  }

  return (
    <>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
        {data.total_participants} participant(s) · ranked by verified submissions
        {data.reward_xp ? `, ${data.reward_xp} XP each` : ''}.
      </Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ overflowX: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ '& th': { fontWeight: 700, whiteSpace: 'nowrap' } }}>
              <TableCell align="right">#</TableCell>
              <TableCell>Participant</TableCell>
              <TableCell align="right">Verified</TableCell>
              <TableCell align="right">XP earned</TableCell>
              <TableCell>First completed</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {entries.map((e) => (
              <TableRow key={e.telegram_user_id} hover>
                <TableCell align="right">
                  <Typography variant="body2" fontWeight={e.rank <= 3 ? 700 : 400}>
                    {RANK_MEDAL[e.rank] || e.rank}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {e.telegram_username ? `@${e.telegram_username}` : `User ${e.telegram_user_id}`}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">ID: {e.telegram_user_id}</Typography>
                </TableCell>
                <TableCell align="right">{e.verified_count}</TableCell>
                <TableCell align="right">{e.xp_earned ? `+${e.xp_earned}` : '—'}</TableCell>
                <TableCell>
                  <Typography variant="caption" sx={{ whiteSpace: 'nowrap' }}>
                    {e.first_verified_at ? new Date(e.first_verified_at).toLocaleString() : '—'}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}
