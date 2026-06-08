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
  Add, Delete, MoreVert, Download, EmojiEvents, Campaign as CampaignIcon,
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
  custom_fields: [],
  multitask: false,   // Pro: campaign holds several sub-tasks
  tasks: [],
  raid_goals: {},     // raid type: { likes, retweets, comments, follows }
};

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

export default function CampaignManager({ botId, groupId }) {
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

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Box>
          <Typography variant="h6" fontWeight={600}>Engagement Campaigns</Typography>
          <Typography variant="body2" color="text.secondary">
            Run social tasks, content submissions and proof collection. Members participate from Telegram.
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<Add />} endIcon={<ArrowDropDown />}
          onClick={(e) => setCreateAnchor(e.currentTarget)}>
          Create
        </Button>
        <Menu anchorEl={createAnchor} open={!!createAnchor} onClose={() => setCreateAnchor(null)}>
          {TYPES.map((t) => (
            <MenuItem key={t.value} onClick={() => openCreate(t.value)}>
              <Box component="span" sx={{ mr: 1 }}>{t.emoji}</Box> {t.label}
            </MenuItem>
          ))}
        </Menu>
      </Box>

      {/* Type filter chips — one click to scope the list, no drill-down.
          Hidden until at least one campaign exists (matches the stats grid). */}
      {campaigns.length > 0 && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
          <Chip
            label={`All (${totals.total})`}
            color={typeFilter === 'all' ? 'primary' : 'default'}
            variant={typeFilter === 'all' ? 'filled' : 'outlined'}
            onClick={() => setTypeFilter('all')}
            size="small"
          />
          {TYPES.map((t) => (
            <Chip
              key={t.value}
              label={`${t.emoji} ${t.chip} (${byType[t.value]?.total || 0})`}
              color={typeFilter === t.value ? 'primary' : 'default'}
              variant={typeFilter === t.value ? 'filled' : 'outlined'}
              onClick={() => setTypeFilter(t.value)}
              size="small"
            />
          ))}
        </Box>
      )}

      <Alert severity="info" sx={{ mb: 2 }}>
        Free plan: 1 active campaign, manual/honor proof, Telegram-join auto-verify.
        Pro unlocks multiple campaigns, link-validity checks, advanced fields, winner picker and bulk export.
      </Alert>

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
            <Typography color="text.secondary" sx={{ mb: 2 }}>No campaigns yet. Create one to engage your community.</Typography>
            <Button variant="contained" startIcon={<Add />} endIcon={<ArrowDropDown />}
              onClick={(e) => setCreateAnchor(e.currentTarget)}>
              Create
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
          botId={botId} groupId={groupId} initialType={createType}
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
  const map = {
    posted: { label: 'Posted', color: 'success' },
    failed: { label: 'Failed', color: 'error' },
    posting: { label: 'Posting…', color: 'warning' },
    none: { label: 'Not posted', color: 'default' },
  };
  const meta = map[c.post_status] || map.none;
  const canRetry = c.status === 'active' && c.post_status !== 'posted' && c.post_status !== 'posting';

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
    </Box>
  );
}

function CampaignRow({ c, botId, groupId, onChanged, onManage }) {
  const [anchor, setAnchor] = useState(null);

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
      <TableCell>
        <Typography variant="body2" fontWeight={500}>{c.title}</Typography>
        {c.platform && <Typography variant="caption" color="text.secondary">{c.platform}</Typography>}
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
          {lifecycle.map((l) => (
            <MenuItem key={l.action} onClick={() => act(l.action)}>{l.label}</MenuItem>
          ))}
        </Menu>
      </TableCell>
    </TableRow>
  );
}

// ── Create wizard ─────────────────────────────────────────────────────────────

function CampaignWizard({ botId, groupId, initialType, onClose, onCreated }) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    ...EMPTY_FORM,
    type: initialType || EMPTY_FORM.type,
    platform: initialType === 'raid' ? 'x' : EMPTY_FORM.platform,
  });
  const [saving, setSaving] = useState(false);

  const typeMeta = TYPES.find((t) => t.value === form.type) || {};

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const canNext = () => {
    if (step === 0) {
      if (!form.title.trim()) return false;
      if (form.multitask) return form.tasks.some((t) => (t.title || '').trim());
      return true;
    }
    return true;
  };

  const submit = async () => {
    if (!form.title.trim()) { toast.error('Title is required'); setStep(0); return; }
    if (form.multitask && !form.tasks.some((t) => (t.title || '').trim())) {
      toast.error('Add at least one task'); setStep(0); return;
    }
    setSaving(true);
    try {
      const payload = {
        type: form.type,
        platform: form.platform || null,
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
          ...(form.type === 'raid'
            ? {
                raid_goals: RAID_GOALS.reduce((acc, g) => {
                  const n = parseInt(form.raid_goals[g.key]);
                  if (n > 0) acc[g.key] = n;
                  return acc;
                }, {}),
              }
            : {}),
        },
        custom_fields: form.multitask ? [] : form.custom_fields
          .filter((f) => f.label.trim())
          .map((f) => ({
            label: f.label.trim(),
            field_type: f.field_type,
            required: f.required,
            example: (f.example || '').trim() || null,
          })),
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
              </Stack>
            ) : (
              <>
                <FormControl fullWidth>
                  <InputLabel>Platform</InputLabel>
                  <Select value={form.platform} label="Platform" onChange={(e) => set('platform', e.target.value)}>
                    {PLATFORMS.map((p) => <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>)}
                  </Select>
                </FormControl>
                <TextField fullWidth multiline minRows={2} label="Instructions / Description"
                  value={form.description} onChange={(e) => set('description', e.target.value)} />
                <TextField fullWidth label={form.type === 'raid' ? 'Tweet URL' : 'Task Link (optional)'}
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
                  Ask participants for proof (UID, link, wallet, screenshot…). The bot collects each
                  field privately and validates the format before accepting it.
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
    const entries = Object.entries(s.payload || {}).filter(([, v]) => v !== '' && v != null && v !== '[screenshot]');
    if (entries.length === 0 && !s.file_id) return <Typography variant="caption" color="text.disabled">—</Typography>;
    return (
      <Box>
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
        {s.file_id && <Typography variant="caption" color="text.secondary">📎 screenshot attached</Typography>}
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
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                Posted to group {new Date(campaign.posted_at).toLocaleString()}
                {campaign.telegram_message_id ? ` · msg #${campaign.telegram_message_id}` : ''}
              </Typography>
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
