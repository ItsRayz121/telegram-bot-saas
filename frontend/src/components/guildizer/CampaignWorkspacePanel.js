import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControlLabel, MenuItem, Pagination, Select, Stack, Switch, Tab, Tabs, TextField, Tooltip,
  Typography, LinearProgress,
} from '@mui/material';
import { CheckCircle, Cancel, WarningAmber } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { guildizerCampaignWorkspace as ws, guildizerEngagement as engagement } from '../../services/guildizerApi';

const fmt = (iso) => (iso ? new Date(iso).toLocaleString() : '—');

function Tile({ label, value, hint, color }) {
  return (
    <Box sx={{ flex: '1 1 140px', border: 1, borderColor: 'divider', borderRadius: 1, p: 1.25 }}>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h5" fontWeight={700} color={color || 'text.primary'}>{value}</Typography>
      {hint && <Typography variant="caption" color="text.secondary">{hint}</Typography>}
    </Box>
  );
}

/** Two honest series: submissions (by sent time) and decisions (by review time). */
function Series({ series }) {
  const max = Math.max(1, ...series.flatMap((d) => [d.submitted, d.decisions]));
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: 70 }} role="img"
      aria-label="Submissions and review decisions per day">
      {series.map((d) => (
        <Tooltip key={d.date} title={`${d.date}: ${d.submitted} submitted, ${d.decisions} decisions`}>
          <Box sx={{ flex: 1, display: 'flex', alignItems: 'flex-end', gap: '1px', height: '100%' }}>
            <Box sx={{ flex: 1, bgcolor: 'primary.main', height: `${(d.submitted / max) * 100}%`, minHeight: d.submitted ? 2 : 0 }} />
            <Box sx={{ flex: 1, bgcolor: 'success.main', height: `${(d.decisions / max) * 100}%`, minHeight: d.decisions ? 2 : 0 }} />
          </Box>
        </Tooltip>
      ))}
    </Box>
  );
}

function Overview({ guildId, onOpenCampaign, onChanged }) {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    setData(null);
    ws.overview(guildId, { days }).then((r) => { if (live) { setData(r.data); setError(''); } })
      .catch(() => { if (live) setError('Could not load the overview.'); });
    return () => { live = false; };
  }, [guildId, days, onChanged]);

  if (error) return <Alert severity="error">{error}</Alert>;
  if (!data) return <Box sx={{ display: 'grid', placeItems: 'center', py: 3 }}><CircularProgress size={24} /></Box>;
  const t = data.totals;
  return (
    <Box>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
        <Tile label="Active campaigns" value={t.active_campaigns} hint={`${t.campaigns_total} in total`} />
        <Tile label="Pending review" value={t.pending_review} color={t.pending_review ? 'warning.main' : undefined} />
        <Tile label="Approved submissions" value={t.approved_submissions}
          hint={`${t.approved_unique_participants} different people`} color="success.main" />
        <Tile label="Rejected" value={t.rejected_submissions} />
      </Stack>

      {data.attention.length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="subtitle2" fontWeight={700} mb={0.5}>Needs attention</Typography>
          {data.attention.map((a, i) => (
            <Box key={`${a.kind}-${a.campaign_id || i}`} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.25 }}>
              <WarningAmber fontSize="small" color="warning" />
              <Typography variant="body2" sx={{ flex: 1 }}>
                {a.title ? <strong>{a.title}: </strong> : null}{a.detail}
              </Typography>
              {a.campaign_id && <Button size="small" onClick={() => onOpenCampaign(a.campaign_id)}>Open</Button>}
            </Box>
          ))}
        </Box>
      )}

      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Typography variant="subtitle2" fontWeight={700}>
          Activity <Typography component="span" variant="caption" color="text.secondary">
            ({data.series_totals.submitted} submitted, {data.series_totals.decisions} decisions)
          </Typography>
        </Typography>
        <Select size="small" value={days} onChange={(e) => setDays(e.target.value)} inputProps={{ 'aria-label': 'Range' }}>
          {[7, 14, 30, 90].map((d) => <MenuItem key={d} value={d}>Last {d} days</MenuItem>)}
        </Select>
      </Box>
      <Series series={data.series} />
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
        <Box component="span" sx={{ color: 'primary.main' }}>■</Box> submitted{' '}
        <Box component="span" sx={{ color: 'success.main' }}>■</Box> review decisions. {data.series_note}
      </Typography>

      {data.running.length > 0 && (
        <>
          <Typography variant="subtitle2" fontWeight={700} mb={0.5}>Running now</Typography>
          {data.running.map((c) => {
            const p = c.progress?.participants;
            return (
              <Box key={c.id} sx={{ py: 0.75, borderTop: 1, borderColor: 'divider' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <Typography variant="body2" fontWeight={700} sx={{ flex: '1 1 160px' }} noWrap>{c.title}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {c.counts.total} submitted · {c.counts.pending} pending · {c.counts.verified} approved
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {c.ends_at ? `ends ${fmt(c.ends_at)}` : 'no deadline'}
                  </Typography>
                  <Button size="small" onClick={() => onOpenCampaign(c.id)}>Manage</Button>
                </Box>
                {p && (
                  <Box sx={{ mt: 0.5 }}>
                    <LinearProgress variant="determinate" value={Math.min(100, (p.done / p.target) * 100)} />
                    <Typography variant="caption" color="text.secondary">
                      {p.done} of {p.target} participants approved
                    </Typography>
                  </Box>
                )}
              </Box>
            );
          })}
        </>
      )}
    </Box>
  );
}

function Queue({ guildId, onChanged }) {
  const [filters, setFilters] = useState({ status: 'pending', campaign_id: '', q: '', flagged: false, sort: 'oldest' });
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [camps, setCamps] = useState([]);
  const [reject, setReject] = useState(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const params = { ...filters, flagged: filters.flagged ? 'true' : '', page, per_page: 15 };
      Object.keys(params).forEach((k) => (params[k] === '' || params[k] == null) && delete params[k]);
      const r = await ws.queue(guildId, params);
      setData(r.data);
    } catch { toast.error('Could not load the review queue.'); }
  }, [guildId, filters, page]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    ws.campaigns(guildId, { per_page: 100, sort: 'title', dir: 'asc' }).then((r) => setCamps(r.data.campaigns)).catch(() => {});
  }, [guildId]);

  const set = (patch) => { setPage(1); setFilters((f) => ({ ...f, ...patch })); };

  async function decide(sub, action, why) {
    setBusy(true);
    try {
      // expected_status makes the server apply this only if nobody else got there first.
      await engagement.reviewSubmission(guildId, sub.campaign_id, sub.id,
        { action, reason: why, expected_status: sub.status });
      toast.success(action === 'approve' ? 'Approved' : 'Rejected');
      setReject(null); setReason('');
      onChanged?.();
    } catch (e) {
      if (e.response?.status === 409) toast.warn('Someone else already reviewed this one. Refreshed.');
      else toast.error(e.response?.data?.message || e.response?.data?.error || 'Failed');
      setReject(null);
    }
    setBusy(false);
    load();
  }

  return (
    <Box>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mb: 1.5 }}>
        <Select size="small" value={filters.status} onChange={(e) => set({ status: e.target.value })} inputProps={{ 'aria-label': 'Status' }}>
          <MenuItem value="pending">Pending</MenuItem>
          <MenuItem value="verified">Approved</MenuItem>
          <MenuItem value="rejected">Rejected</MenuItem>
          <MenuItem value="all">All</MenuItem>
        </Select>
        <Select size="small" displayEmpty value={filters.campaign_id} onChange={(e) => set({ campaign_id: e.target.value })}
          inputProps={{ 'aria-label': 'Campaign' }} sx={{ minWidth: 180 }}>
          <MenuItem value="">All campaigns</MenuItem>
          {camps.map((c) => <MenuItem key={c.id} value={String(c.id)}>{c.title}</MenuItem>)}
        </Select>
        <TextField size="small" label="Search member" value={filters.q} onChange={(e) => set({ q: e.target.value })} />
        <Select size="small" value={filters.sort} onChange={(e) => set({ sort: e.target.value })} inputProps={{ 'aria-label': 'Sort' }}>
          <MenuItem value="oldest">Oldest first</MenuItem>
          <MenuItem value="newest">Newest first</MenuItem>
        </Select>
        <FormControlLabel control={<Switch size="small" checked={filters.flagged} onChange={(e) => set({ flagged: e.target.checked })} />}
          label="Flagged only" />
      </Stack>

      {!data ? <Box sx={{ display: 'grid', placeItems: 'center', py: 3 }}><CircularProgress size={24} /></Box> : (
        <>
          <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
            {data.total} submission{data.total === 1 ? '' : 's'}. Waiting more than {data.stale_review_hours} hours is marked.
          </Typography>
          {data.submissions.length === 0 && <Typography variant="body2" color="text.secondary">Nothing here.</Typography>}
          {data.submissions.map((s) => {
            const proof = (s.proof && (s.proof.value || Object.values(s.proof).filter((v) => typeof v === 'string').join(' · '))) || '';
            return (
              <Box key={s.id} sx={{ py: 1, borderTop: 1, borderColor: 'divider' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <Box sx={{ flex: '1 1 220px', minWidth: 0 }}>
                    <Typography variant="body2" fontWeight={700} noWrap>{s.username || s.user_id}</Typography>
                    <Typography variant="caption" color="text.secondary" noWrap display="block">
                      {s.campaign_title} · sent {fmt(s.created_at)}
                    </Typography>
                  </Box>
                  {s.flagged && <Tooltip title={s.flag_reason || 'Possible duplicate'}><Chip size="small" color="warning" label="Flagged" /></Tooltip>}
                  {s.waiting_long && <Chip size="small" color="error" variant="outlined" label={`Waiting ${Math.round(s.waiting_hours)} h`} />}
                  {s.status !== 'pending' && (
                    <Chip size="small" color={s.status === 'verified' ? 'success' : 'default'}
                      label={s.status === 'verified' ? `Approved${s.verification_source ? ` (${s.verification_source})` : ''}` : 'Rejected'} />
                  )}
                  {s.status === 'pending' && (
                    <>
                      <Button size="small" color="success" startIcon={<CheckCircle />} disabled={busy} onClick={() => decide(s, 'approve')}>Approve</Button>
                      <Button size="small" color="error" startIcon={<Cancel />} disabled={busy} onClick={() => { setReject(s); setReason(''); }}>Reject</Button>
                    </>
                  )}
                </Box>
                {proof && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: 'break-word' }}>{proof}</Typography>}
                {s.file_url && <Button size="small" href={s.file_url} target="_blank" rel="noopener noreferrer">Open screenshot</Button>}
              </Box>
            );
          })}
          {data.pages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1.5 }}>
              <Pagination count={data.pages} page={page} onChange={(_, p) => setPage(p)} size="small" />
            </Box>
          )}
        </>
      )}

      <Dialog open={!!reject} onClose={() => setReject(null)} fullWidth maxWidth="xs">
        <DialogTitle>Reject {reject?.username || 'submission'}</DialogTitle>
        <DialogContent>
          <TextField autoFocus fullWidth multiline minRows={2} margin="dense" label="Reason (shown to the member)"
            value={reason} inputProps={{ maxLength: 500 }} onChange={(e) => setReason(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReject(null)}>Cancel</Button>
          <Button color="error" variant="contained" disabled={busy} onClick={() => decide(reject, 'reject', reason)}>Reject</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

/** Overview and cross-campaign review queue. Read-only views plus guarded review. */
export default function CampaignWorkspacePanel({ guildId, onOpenCampaign, onChanged }) {
  const [tab, setTab] = useState('overview');
  const [stamp, setStamp] = useState(0);
  const changed = useCallback(() => { setStamp((n) => n + 1); onChanged?.(); }, [onChanged]);
  return (
    <Box>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 1.5, minHeight: 36, '& .MuiTab-root': { minHeight: 36, textTransform: 'none' } }}>
        <Tab value="overview" label="Overview" />
        <Tab value="queue" label="Review queue" />
      </Tabs>
      {tab === 'overview'
        ? <Overview guildId={guildId} onOpenCampaign={onOpenCampaign} onChanged={stamp} />
        : <Queue guildId={guildId} onChanged={changed} />}
    </Box>
  );
}
