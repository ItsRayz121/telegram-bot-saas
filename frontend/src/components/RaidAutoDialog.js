// "Continuous raids": when the owner's X account posts a new ORIGINAL tweet, start a raid in
// this group/server by itself. One dialog shared by Telegizer and Guildizer; the data calls
// come from the workspace (`api`), the Discord channel list from `channels`.
//
// The rules are enforced by the backend (raid_auto.py): the account is checked every 12 hours,
// one X account per owner, original posts only, Pro/Enterprise only.
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControl,
  InputLabel, MenuItem, Select, Stack, Switch, TextField, Typography,
} from '@mui/material';
import { toast } from 'react-toastify';
import { HelpTip } from './TaskXOptions';

const GOALS = [['likes', 'Likes'], ['retweets', 'Reposts'], ['comments', 'Comments'], ['quotes', 'Quotes']];
const ACTIONS = { likes: 'like', retweets: 'retweet', comments: 'comment', quotes: 'quote' };
const DURATIONS = [[6, '6 hours'], [12, '12 hours'], [24, '24 hours'], [48, '2 days'], [72, '3 days'], [168, '7 days']];
const DEFAULT = {
  x_handle: '', channel_id: '', enabled: true,
  goals: { likes: { min: 10, max: 20 }, retweets: { min: 5, max: 10 }, comments: { min: '', max: '' }, quotes: { min: '', max: '' } },
  xp: {}, duration_hours: 24, pin_message: false, max_per_day: 2, auto_verify_x: true,
};

const when = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '-');

function fromServer(a) {
  if (!a) return { ...DEFAULT };
  const t = a.template || {};
  const goals = {};
  GOALS.forEach(([k]) => { goals[k] = t.goals?.[k] ? { min: t.goals[k].min, max: t.goals[k].max } : { min: '', max: '' }; });
  const xp = {};
  Object.entries(ACTIONS).forEach(([k, act]) => { if (t.action_xp?.[act]) xp[k] = t.action_xp[act]; });
  return {
    x_handle: `@${a.x_handle}`, channel_id: a.channel_id || '', enabled: a.enabled, goals, xp,
    duration_hours: t.duration_hours || 24, pin_message: !!t.pin_message, max_per_day: t.max_per_day || 2,
    auto_verify_x: t.auto_verify_x !== false,
  };
}

function toServer(f) {
  const goals = {};
  GOALS.forEach(([k]) => {
    const lo = parseInt(f.goals[k].min, 10);
    const hi = parseInt(f.goals[k].max, 10);
    const max = Number.isFinite(hi) ? hi : lo;
    const min = Number.isFinite(lo) ? lo : max;
    if (max > 0) goals[k] = { min, max };
  });
  const action_xp = {};
  Object.entries(ACTIONS).forEach(([k, act]) => { const n = parseInt(f.xp[k], 10); if (n > 0) action_xp[act] = n; });
  return {
    x_handle: f.x_handle, channel_id: f.channel_id || undefined, enabled: f.enabled,
    template: { goals, action_xp, duration_hours: f.duration_hours, pin_message: f.pin_message, max_per_day: f.max_per_day, auto_verify_x: f.auto_verify_x },
  };
}

export default function RaidAutoDialog({ open, onClose, api, channels = null, noun = 'group' }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [form, setForm] = useState(DEFAULT);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    api.get()
      .then((r) => { setState({ loading: false, data: r.data, error: null }); setForm(fromServer(r.data.automation)); })
      .catch((e) => setState({ loading: false, data: null, error: e.response?.data?.error || 'Could not load continuous raids.' }));
  }, [api]);
  useEffect(() => { if (open) { setNote(null); load(); } }, [open, load]);

  const d = state.data;
  const a = d?.automation;
  const paid = !!d?.is_paid;
  const canEdit = d?.can_edit !== false;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setGoal = (k, side, v) => setForm((f) => ({ ...f, goals: { ...f.goals, [k]: { ...f.goals[k], [side]: v } } }));
  const needsChannel = channels !== null;

  const act = async (fn, okMsg) => {
    setBusy(true);
    try {
      const r = await fn();
      setState({ loading: false, data: r.data, error: null });
      setForm(fromServer(r.data.automation));
      if (okMsg) toast.success(okMsg);
      return r.data;
    } catch (e) {
      toast.error(e.response?.data?.error || 'That did not work');
      return null;
    } finally { setBusy(false); }
  };

  const save = () => act(() => api.save(toServer(form)), 'Continuous raids saved');
  const remove = () => act(() => api.remove(), 'Continuous raids removed');
  const check = async () => {
    const r = await act(() => api.check());
    if (r?.result) {
      setNote(r.result.status !== 'ok' ? { severity: 'warning', text: r.result.error || 'The check failed.' }
        : r.result.started ? { severity: 'success', text: `Started ${r.result.started} raid${r.result.started > 1 ? 's' : ''}.` }
          : { severity: 'info', text: 'Checked: no new original posts to raid.' });
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        Continuous raids <Chip size="small" label="Pro" variant="outlined" color={paid ? 'default' : 'warning'} />
        <HelpTip text={`When your X account posts a new original post (not a reply, repost or quote), a raid starts in this ${noun} by itself. Your account is checked once every 12 hours, which keeps API usage low. Needs a Twitter API key and a Pro or Enterprise plan. One X account per owner.`} />
      </DialogTitle>
      <DialogContent>
        {state.loading && !d ? <Box sx={{ py: 4, textAlign: 'center' }}><CircularProgress size={24} /></Box> : state.error ? (
          <Alert severity="warning">{state.error}</Alert>
        ) : (
          <Stack spacing={2} sx={{ mt: 1 }}>
            {!paid && <Alert severity="info">Continuous raids need a Pro or Enterprise plan. Upgrade to turn this on.</Alert>}
            {paid && d.x_status !== 'live' && (
              <Alert severity="warning">No working Twitter API key was found, so nothing can be checked yet. Add one under Tools, X (Twitter) verification.</Alert>
            )}
            {!canEdit && <Alert severity="info">Only the owner can change this.</Alert>}
            {note && <Alert severity={note.severity} onClose={() => setNote(null)}>{note.text}</Alert>}
            {a?.last_error && <Alert severity="warning">Last check: {a.last_error}</Alert>}

            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Typography variant="body2">Start raids automatically</Typography>
              <Switch checked={form.enabled} onChange={(e) => set('enabled', e.target.checked)} disabled={!paid || !canEdit} />
            </Stack>
            <TextField label="X account to follow" placeholder="@YourProject" value={form.x_handle} disabled={!paid || !canEdit}
              onChange={(e) => set('x_handle', e.target.value)} helperText="Only its new original posts start raids." />
            {needsChannel && (
              <FormControl fullWidth disabled={!paid || !canEdit}>
                <InputLabel>Post raids in</InputLabel>
                <Select value={form.channel_id} label="Post raids in" onChange={(e) => set('channel_id', e.target.value)}>
                  {channels.map((c) => <MenuItem key={c.id} value={String(c.id)}>#{c.name}</MenuItem>)}
                </Select>
              </FormControl>
            )}

            <Box>
              <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.5 }}>
                Targets per raid
                <HelpTip text="Use the same number in Min and Max for a fixed target, or a range (for example 10 to 20) to pick a random number for every raid. Leave a row empty to skip that action." />
              </Typography>
              <Stack spacing={1}>
                {GOALS.map(([k, label]) => (
                  <Stack key={k} direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2" sx={{ width: 90 }}>{label}</Typography>
                    <TextField size="small" type="number" label="Min" value={form.goals[k].min} sx={{ width: 100 }} disabled={!paid || !canEdit}
                      inputProps={{ min: 0 }} onChange={(e) => setGoal(k, 'min', e.target.value)} />
                    <TextField size="small" type="number" label="Max" value={form.goals[k].max} sx={{ width: 100 }} disabled={!paid || !canEdit}
                      inputProps={{ min: 0 }} onChange={(e) => setGoal(k, 'max', e.target.value)} />
                    <TextField size="small" type="number" label="XP each" value={form.xp[k] || ''} sx={{ width: 100 }} disabled={!paid || !canEdit}
                      inputProps={{ min: 0 }} onChange={(e) => set('xp', { ...form.xp, [k]: e.target.value })} />
                  </Stack>
                ))}
              </Stack>
            </Box>

            <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
              <FormControl size="small" sx={{ minWidth: 150 }} disabled={!paid || !canEdit}>
                <InputLabel>Raid lasts</InputLabel>
                <Select value={form.duration_hours} label="Raid lasts" onChange={(e) => set('duration_hours', e.target.value)}>
                  {DURATIONS.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 150 }} disabled={!paid || !canEdit}>
                <InputLabel>Most raids per day</InputLabel>
                <Select value={form.max_per_day} label="Most raids per day" onChange={(e) => set('max_per_day', e.target.value)}>
                  {[1, 2, 3, 4, 5].map((n) => <MenuItem key={n} value={n}>{n}</MenuItem>)}
                </Select>
              </FormControl>
            </Stack>
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Typography variant="body2">Pin each raid post</Typography>
              <Switch checked={form.pin_message} onChange={(e) => set('pin_message', e.target.checked)} disabled={!paid || !canEdit} />
            </Stack>
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                Verify actions automatically
                <HelpTip text="Reposts, comments and quotes are checked through the X API. Likes cannot be read from X, so they stay honor-based." />
              </Typography>
              <Switch checked={form.auto_verify_x} onChange={(e) => set('auto_verify_x', e.target.checked)} disabled={!paid || !canEdit} />
            </Stack>

            {a && (
              <Typography variant="caption" color="text.secondary">
                Checked every {d.limits.interval_hours} hours. Last check: {when(a.last_polled_at)}. Next check: {a.enabled ? when(a.next_poll_at) : 'paused'}.
                Raids started: {a.raids_started}.
              </Typography>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap' }}>
        {a && canEdit && <Button color="error" onClick={remove} disabled={busy}>Remove</Button>}
        {a && canEdit && <Button onClick={check} disabled={busy || !paid}>Check now</Button>}
        <Box sx={{ flex: 1 }} />
        <Button onClick={onClose}>Close</Button>
        <Button variant="contained" onClick={save} disabled={busy || !paid || !canEdit || !form.x_handle.trim()}>
          {busy ? <CircularProgress size={18} color="inherit" /> : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
