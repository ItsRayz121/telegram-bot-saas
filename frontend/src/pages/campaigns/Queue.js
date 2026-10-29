import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, FormControlLabel,
  IconButton, InputAdornment, InputLabel, MenuItem, Pagination, Paper, Select, Stack, Switch, TextField, Tooltip, Typography,
} from '@mui/material';
import { ArrowBack, Cancel, CheckCircle, Refresh, Search } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { engagement, engagementWs } from '../../services/api';
import { ScreenshotViewer } from '../../components/CampaignManager';
import { EmptyNote, InsightError, Loading, memberProfilePath } from '../../components/analytics/shared';
import { Freshness, SOURCE_LABEL, SUB_COLOR, SUB_LABEL, TYPE_LABEL, fmtTime, useWorkspace, usePolled } from './common';

const FIELD_TYPE = { text: 'Text', url: 'Link', uid: 'Exchange UID', wallet: 'Wallet address', screenshot: 'Screenshot', tx_hash: 'Transaction hash', username: 'Username' };

function who(s) { return s.telegram_username ? `@${s.telegram_username}` : `User ${s.telegram_user_id}`; }

function Proof({ s, ws }) {
  const entries = Object.entries(s.payload || {}).filter(([k, v]) => k !== 'actions' && v !== '' && v != null && v !== '[screenshot]');
  const actions = (s.payload || {}).actions;
  return (
    <Box>
      <Typography variant="overline" color="text.secondary">Submitted proof</Typography>
      {actions && typeof actions === 'object' && (
        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ my: 0.75 }}>
          {Object.entries(actions).map(([k, v]) => {
            const st = (v || {}).status;
            return <Chip key={k} size="small" variant="outlined" color={st === 'verified' ? 'success' : st === 'failed' ? 'error' : 'default'} label={`${k}: ${st || 'unknown'}`} />;
          })}
        </Stack>
      )}
      {entries.length === 0 && !s.has_file && !actions && <Typography variant="body2" color="text.secondary">No proof fields were submitted.</Typography>}
      <Box component="dl" sx={{ m: 0, display: 'grid', gap: 1 }}>
        {entries.map(([k, v]) => {
          const f = s.field_labels?.[k];
          const isUrl = typeof v === 'string' && /^https?:\/\//i.test(v);
          return (
            <Box key={k}>
              <Typography component="dt" variant="caption" color="text.secondary">{f ? `${f.label} (${FIELD_TYPE[f.field_type] || f.field_type})` : k}</Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0, wordBreak: 'break-word', fontFamily: f && ['uid', 'wallet', 'tx_hash'].includes(f.field_type) ? 'monospace' : undefined }}>
                {isUrl ? <a href={v} target="_blank" rel="noopener noreferrer">{v}</a> : String(v)}
              </Typography>
            </Box>
          );
        })}
      </Box>
      {s.has_file && (
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Screenshot</Typography>
          <ScreenshotViewer botId={ws.botId} groupId={ws.groupId} campaignId={s.campaign_id} submissionId={s.id} />
        </Box>
      )}
    </Box>
  );
}

function Detail({ s, ws, busy, onApprove, onReject, onApproveNext, onBack, hasNext }) {
  const profile = memberProfilePath({ isOfficial: ws.isOfficial, botId: ws.rawBotId, groupId: ws.groupId, userId: s.telegram_user_id });
  const locked = ws.isViewer;
  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, md: 2 } }}>
      <Box sx={{ display: { xs: 'flex', md: 'none' }, mb: 1 }}>
        <Button size="small" startIcon={<ArrowBack />} onClick={onBack}>Back to list</Button>
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h6" sx={{ wordBreak: 'break-word' }}>
            {profile ? <Typography component={RouterLink} to={profile} variant="inherit" sx={{ color: 'inherit' }}>{who(s)}</Typography> : who(s)}
          </Typography>
          <Typography variant="caption" color="text.secondary">Telegram ID {s.telegram_user_id}</Typography>
        </Box>
        <Chip color={SUB_COLOR[s.status]} label={SUB_LABEL[s.status] || s.status} />
      </Box>
      <Box sx={{ my: 1.5, display: 'grid', gap: 0.5 }}>
        <Typography variant="body2">
          <strong>Campaign:</strong>{' '}
          <Typography component={RouterLink} to={ws.paths.detail(s.campaign_id)} variant="body2" sx={{ color: 'primary.main' }}>{s.campaign_title}</Typography>
          {' '}<Typography component="span" variant="caption" color="text.secondary">({TYPE_LABEL[s.campaign_type] || s.campaign_type}{s.campaign_status === 'closed' ? ' · closed - still reviewable' : ''}{s.task_title ? ` · task: ${s.task_title}` : ''})</Typography>
        </Typography>
        <Typography variant="body2"><strong>Submitted:</strong> {fmtTime(s.created_at, ws.tz)}</Typography>
        {s.reviewed_at && <Typography variant="body2"><strong>Decided:</strong> {fmtTime(s.reviewed_at, ws.tz)}{s.reviewed_by_name ? ` by ${s.reviewed_by_name}` : ''}</Typography>}
        {s.verification_source && <Typography variant="body2"><strong>Verification:</strong> {SOURCE_LABEL[s.verification_source]}</Typography>}
        {s.review_reason && <Typography variant="body2" color="text.secondary"><strong>Reason given:</strong> {s.review_reason}</Typography>}
      </Box>
      {s.flagged && <Alert severity="warning" sx={{ mb: 1.5 }}>Possible duplicate: {s.flag_reason || 'flagged by the anti-fraud check'}.</Alert>}
      <Proof s={s} ws={ws} />
      {locked && <Alert severity="info" sx={{ mt: 2 }}>View-only access: you can't approve or reject.</Alert>}
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 2.5, pt: 2, borderTop: 1, borderColor: 'divider' }}>
        <Button variant="contained" color="success" startIcon={busy === 'approve' ? <CircularProgress size={16} color="inherit" /> : <CheckCircle />}
          disabled={!!busy || locked || s.status === 'verified'} onClick={onApprove}>Approve</Button>
        {s.status === 'pending' && hasNext && (
          <Button variant="outlined" color="success" disabled={!!busy || locked} onClick={onApproveNext}>Approve &amp; next</Button>
        )}
        <Button variant="outlined" color="error" startIcon={<Cancel />} disabled={!!busy || locked || s.status === 'rejected'} onClick={onReject}>Reject…</Button>
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
        Approving credits the XP for the actions that passed (a raid with per-action XP pays nothing for failed actions; the member can finish them later to earn the rest). Rejecting credits nothing and notifies the member (if they have started the bot).
        If a colleague decides first, you'll be told and nothing is changed.
      </Typography>
    </Paper>
  );
}

export default function Queue() {
  const ws = useWorkspace();
  const [sp, setSp] = useSearchParams();
  const status = sp.get('status') || 'pending';
  const campaign = sp.get('campaign') || '';
  const flagged = sp.get('flagged') === 'true';
  const sort = sp.get('sort') || 'oldest';
  const page = Math.max(1, parseInt(sp.get('page') || '1', 10) || 1);
  const itemId = parseInt(sp.get('item') || '', 10) || null;
  const [qInput, setQInput] = useState(sp.get('q') || '');
  const [q, setQ] = useState(qInput);
  useEffect(() => { const t = setTimeout(() => setQ(qInput), 350); return () => clearTimeout(t); }, [qInput]);

  const update = useCallback((patch, keepPage) => {
    const next = new URLSearchParams(sp);
    Object.entries(patch).forEach(([k, v]) => { if (v === '' || v == null || v === false) next.delete(k); else next.set(k, String(v)); });
    if (!keepPage && !('page' in patch)) next.delete('page');
    setSp(next, { replace: true });
  }, [sp, setSp]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if ((sp.get('q') || '') !== q) update({ q, item: '' }); }, [q]);

  const params = { status, campaign_id: campaign || undefined, q: q || undefined, flagged: flagged ? 'true' : undefined, sort, page, per_page: 25 };
  const { data, loading, error, at, stale, reload } = usePolled(
    () => engagementWs.queue(ws.botId, ws.groupId, params), [ws.botId, ws.groupId, status, campaign, q, flagged, sort, page, ws.tick], { enabled: ws.ready, intervalMs: 60000 });
  const items = useMemo(() => data?.items || [], [data]);
  const selected = items.find((i) => i.id === itemId) || null;
  const idx = selected ? items.indexOf(selected) : -1;
  const [busy, setBusy] = useState('');
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [rejectErr, setRejectErr] = useState('');
  const inflight = useRef(false);

  // Keep a valid selection: first item on desktop when nothing is chosen.
  useEffect(() => {
    if (data && !itemId && items.length && window.matchMedia('(min-width:900px)').matches) update({ item: items[0].id }, true);
  }, [data, itemId, items, update]);

  // On a phone the detail opens below the filters: bring it into view when a submission is picked.
  useEffect(() => {
    if (itemId && !window.matchMedia('(min-width:900px)').matches) window.scrollTo({ top: 0, behavior: 'auto' });
  }, [itemId]);

  const decide = async (action, why, advance) => {
    if (!selected || inflight.current) return false;       // ignore double clicks while a request is out
    inflight.current = true;
    setBusy(action);
    const nextItem = advance ? items[idx + 1] : null;
    try {
      await engagement.reviewSubmission(ws.botId, ws.groupId, selected.campaign_id, selected.id, {
        action, reason: why || undefined, expected_status: selected.status,
      });
      toast.success(action === 'approve' ? `Approved ${who(selected)}` : `Rejected ${who(selected)}`);
      ws.bump();                                                // refresh counts everywhere (queue, overview, directory)
      if (advance && nextItem) update({ item: nextItem.id }, true); else if (status === 'pending') update({ item: '' }, true);
      return true;
    } catch (e) {
      const code = e.response?.data?.code;
      if (code === 'STALE_SUBMISSION') {
        toast.warn(e.response.data.error);
        ws.bump();                                              // show what the colleague decided
        return 'stale';
      }
      toast.error(e.response?.data?.error || 'Could not save the decision - nothing was changed');
      return false;
    } finally {
      inflight.current = false;
      setBusy('');
    }
  };

  const confirmReject = async () => {
    setRejectErr('');
    const ok = await decide('reject', reason.trim());
    if (ok === true || ok === 'stale') { setRejecting(false); setReason(''); }
    else setRejectErr('The decision was not saved. Your note is still here - try again.');   // keep unsent feedback
  };

  const list = (
    <Box sx={{ display: { xs: itemId && selected ? 'none' : 'block', md: 'block' } }}>
      {loading && !data ? <Loading label="Loading submissions…" /> : items.length === 0 ? (
        <EmptyNote>{status === 'pending' && !campaign && !q ? 'Nothing is waiting for review. Nice work.' : 'No submissions match these filters.'}</EmptyNote>
      ) : (
        <Stack spacing={0.75} component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label="Submissions">
          {items.map((s) => (
            <Box component="li" key={s.id}>
              <Paper variant="outlined" component="button" type="button" onClick={() => update({ item: s.id }, true)} aria-current={s.id === itemId}
                sx={{
                  all: 'unset', boxSizing: 'border-box', display: 'block', width: '100%', cursor: 'pointer', p: 1.25, borderRadius: 1,
                  border: '1px solid', borderColor: s.id === itemId ? 'primary.main' : 'divider', bgcolor: s.id === itemId ? 'action.selected' : 'background.paper',
                  '&:hover': { bgcolor: 'action.hover' }, '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: 2 },
                }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                  <Typography variant="body2" fontWeight={700} noWrap>{who(s)}</Typography>
                  <Chip size="small" color={SUB_COLOR[s.status]} variant={s.status === 'pending' ? 'filled' : 'outlined'} label={SUB_LABEL[s.status]} />
                </Box>
                <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>{s.campaign_title}{s.task_title ? ` · ${s.task_title}` : ''}</Typography>
                <Typography variant="caption" color="text.secondary">{fmtTime(s.created_at, ws.tz, { year: undefined })}{s.flagged ? ' · ⚠ possible duplicate' : ''}</Typography>
              </Paper>
            </Box>
          ))}
        </Stack>
      )}
      {data?.pages > 1 && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1.5 }}>
          <Pagination size="small" count={data.pages} page={page} onChange={(_, p) => update({ page: p, item: '' }, true)} color="primary" />
        </Box>
      )}
    </Box>
  );

  return (
    <Box aria-busy={loading}>
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mb: 1.5 }}>
        <TextField size="small" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Search member or campaign…" sx={{ flex: '1 1 200px' }}
          inputProps={{ 'aria-label': 'Search submissions' }}
          InputProps={{ startAdornment: (<InputAdornment position="start"><Search fontSize="small" /></InputAdornment>) }} />
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel id="q-status">Status</InputLabel>
          <Select labelId="q-status" label="Status" value={status} onChange={(e) => update({ status: e.target.value, item: '' })}>
            <MenuItem value="pending">Pending review</MenuItem>
            <MenuItem value="verified">Approved</MenuItem>
            <MenuItem value="rejected">Rejected</MenuItem>
            <MenuItem value="all">All</MenuItem>
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 190, maxWidth: 260 }}>
          <InputLabel id="q-camp">Campaign</InputLabel>
          <Select labelId="q-camp" label="Campaign" value={campaign} onChange={(e) => update({ campaign: e.target.value, item: '' })}>
            <MenuItem value="">All campaigns</MenuItem>
            {(data?.campaigns || []).map((c) => <MenuItem key={c.id} value={String(c.id)}>{c.title}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel id="q-sort">Order</InputLabel>
          <Select labelId="q-sort" label="Order" value={sort} onChange={(e) => update({ sort: e.target.value })}>
            <MenuItem value="oldest">Oldest first</MenuItem>
            <MenuItem value="newest">Newest first</MenuItem>
          </Select>
        </FormControl>
        <FormControlLabel control={<Switch size="small" checked={flagged} onChange={(e) => update({ flagged: e.target.checked })} />} label="Flagged only" />
        <Tooltip title="Refresh"><span><IconButton onClick={reload} disabled={loading} aria-label="Refresh queue"><Refresh /></IconButton></span></Tooltip>
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap', mb: 1 }}>
        <Typography variant="caption" color="text.secondary" aria-live="polite">
          {data ? `${data.total.toLocaleString()} shown · ${data.pending_total.toLocaleString()} pending in this group` : ' '}
        </Typography>
        <Freshness at={at} error={error} stale={stale} tz={ws.tz} />
      </Box>

      {error && !data ? <InsightError message={error} onRetry={reload} /> : (
        <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'minmax(280px, 1fr) minmax(0, 1.6fr)' }, alignItems: 'start' }}>
          {list}
          <Box sx={{ display: { xs: itemId && selected ? 'block' : 'none', md: 'block' }, position: { md: 'sticky' }, top: { md: 12 } }}>
            {selected ? (
              <Detail
                s={selected} ws={ws} busy={busy} hasNext={idx >= 0 && idx < items.length - 1}
                onBack={() => update({ item: '' }, true)}
                onApprove={() => decide('approve', null, false)}
                onApproveNext={() => decide('approve', null, true)}
                onReject={() => { setReason(selected.review_reason || ''); setRejectErr(''); setRejecting(true); }}
              />
            ) : (
              <Paper variant="outlined" sx={{ p: 3, display: { xs: 'none', md: 'block' } }}><EmptyNote>Select a submission to see its proof.</EmptyNote></Paper>
            )}
          </Box>
        </Box>
      )}

      <Dialog open={rejecting} onClose={() => !busy && setRejecting(false)} maxWidth="xs" fullWidth aria-labelledby="reject-title">
        <DialogTitle id="reject-title">Reject {selected ? who(selected) : 'submission'}?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            The member is told this reason (if they've started the bot). No XP is credited. Rejection is final for this submission unless you approve it later.
          </Typography>
          <TextField autoFocus fullWidth multiline minRows={2} label="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. UID does not match - please resend" error={!!rejectErr} helperText={rejectErr || ' '} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejecting(false)} disabled={!!busy}>Cancel</Button>
          <Button color="error" variant="contained" onClick={confirmReject} disabled={!!busy}>
            {busy === 'reject' ? <CircularProgress size={20} color="inherit" /> : 'Reject'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
