import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel,
  Pagination, Paper, Stack, Switch, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TextField, Typography,
} from '@mui/material';
import { toast } from 'react-toastify';
import { settings } from '../../services/api';
import {
  BreakdownBars, EmptyNote, InsightError, Loading, Panel, PeriodChips, StatGrid, StatTile, TableCols, TrendChart, fixedTableSx, useInsight,
} from './shared';

// The activity log records three outcomes. There is no "pending" state and no
// success score in the data, so none is shown.
const OUTCOME = {
  ok: { label: 'Completed', color: 'success' },
  skipped: { label: 'Skipped', color: 'default' },
  failed: { label: 'Failed', color: 'error' },
};
const CATEGORIES = ['moderation', 'knowledge', 'engagement', 'automation', 'analytics'];
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function OutcomeChip({ status }) {
  const o = OUTCOME[status] || { label: status || 'Unknown', color: 'default' };
  return <Chip size="small" label={o.label} color={o.color} variant={o.color === 'default' ? 'outlined' : 'filled'} />;
}

function Field({ label, children }) {
  if (children === null || children === undefined || children === '') return null;
  return (
    <Box sx={{ mb: 1.5 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{label}</Typography>
      <Typography variant="body2" component="div" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{children}</Typography>
    </Box>
  );
}

function InspectDialog({ event: e, botId, groupId, fmt, onClose, onSaved }) {
  const meta = e?.meta || {};
  const fb = meta.feedback || null;
  const isKnowledge = e?.category === 'knowledge';
  const [rating, setRating] = useState(fb?.rating || '');
  const [note, setNote] = useState(fb?.note || '');
  const [corrected, setCorrected] = useState(meta.answer || '');
  const [saveToKb, setSaveToKb] = useState(isKnowledge);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  if (!e) return null;
  const submit = async () => {
    setSaving(true); setErr(null);
    try {
      const res = await settings.submitAiActivityFeedback(botId, groupId, e.id, {
        rating, note, corrected_answer: isKnowledge ? corrected : '', save_to_kb: isKnowledge && saveToKb,
      });
      toast.success(res.data?.saved_to_kb ? 'Saved - the bot will use your improved answer next time' : 'Feedback saved');
      onSaved?.();
      onClose();
    } catch (error) {
      // keep everything typed so nothing is lost
      setErr(error?.response?.data?.error || 'Failed to save feedback. Your text is still here - try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={() => !saving && onClose()} maxWidth="sm" fullWidth aria-labelledby="ai-inspect-title">
      <DialogTitle id="ai-inspect-title">{e.action}</DialogTitle>
      <DialogContent dividers>
        <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
          <OutcomeChip status={e.status} />
          <Chip size="small" variant="outlined" label={cap(e.category)} />
          {e.source && <Chip size="small" variant="outlined" label={`Source: ${e.source.replace(/_/g, ' ')}`} />}
        </Stack>
        <Field label="When">{fmt(e.created_at)}</Field>
        <Field label="About">{e.target}</Field>
        <Field label={isKnowledge ? 'Original question' : 'Input / reason'}>{e.detail}</Field>
        <Field label="Original message">{meta.message}</Field>
        <Field label={isKnowledge ? 'Answer given' : 'Result'}>{meta.answer}</Field>
        {meta.reason && meta.reason !== e.detail && <Field label="Reason recorded">{meta.reason}</Field>}
        {typeof meta.confidence === 'number' && (
          <Field label="Knowledge match confidence (as recorded by the bot)">{meta.confidence}</Field>
        )}
        {isKnowledge && !meta.answer && (
          <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic', display: 'block', mb: 1.5 }}>
            No stored answer - either it was logged before answers were captured, or none was sent.
          </Typography>
        )}
        {fb && (
          <Field label="Existing feedback">
            {[fb.rating && (fb.rating === 'good' ? '👍 Good' : '👎 Needs work'), fb.note, fb.reviewed_by && `by ${fb.reviewed_by}`].filter(Boolean).join(' · ')}
          </Field>
        )}

        <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Improve / feedback</Typography>
          <Box sx={{ display: 'flex', gap: 1, mb: 1.5 }}>
            <Button variant={rating === 'good' ? 'contained' : 'outlined'} color="success" size="small" aria-pressed={rating === 'good'} onClick={() => setRating('good')}>👍 Good</Button>
            <Button variant={rating === 'bad' ? 'contained' : 'outlined'} color="warning" size="small" aria-pressed={rating === 'bad'} onClick={() => setRating('bad')}>👎 Needs work</Button>
          </Box>
          {isKnowledge && (
            <>
              <TextField label="Improved answer" fullWidth multiline minRows={3} value={corrected} onChange={(ev) => setCorrected(ev.target.value)}
                helperText="Edit the answer to be more accurate." sx={{ mb: 1 }} />
              <FormControlLabel control={<Switch checked={saveToKb} onChange={(ev) => setSaveToKb(ev.target.checked)} />}
                label="Teach the bot - use this answer for the next matching question" />
            </>
          )}
          <TextField label="Note (optional)" fullWidth multiline minRows={2} value={note} onChange={(ev) => setNote(ev.target.value)} sx={{ mt: 1 }}
            placeholder={isKnowledge ? 'Why was the answer wrong?' : 'e.g. this removal was a mistake'} />
          {err && <Typography role="alert" variant="body2" color="error" sx={{ mt: 1 }}>{err}</Typography>}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Close</Button>
        <Button variant="contained" onClick={submit} disabled={saving || (!rating && !note.trim() && !corrected.trim())}>
          {saving ? <CircularProgress size={20} /> : 'Save feedback'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function AIActivityPanel({ botId, groupId, fmt, refreshKey }) {
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [feed, setFeed] = useState({ data: null, loading: true, error: null });
  const [inspect, setInspect] = useState(null);
  const [rk, setRk] = useState(0);
  const overview = useInsight(botId, groupId, 'ai-overview', { days: 30, _r: `${refreshKey}-${rk}` });

  const load = useCallback(async () => {
    setFeed((f) => ({ ...f, loading: true, error: null }));
    try {
      const r = await settings.getAIActivity(botId, groupId, {
        page, category: category || undefined, status: status || undefined,
      });
      setFeed({ data: r.data, loading: false, error: null });
    } catch (e) {
      setFeed((f) => ({ data: f.data, loading: false, error: e?.response?.data?.error || 'Could not load AI activity' }));
    }
  }, [botId, groupId, page, category, status]);
  useEffect(() => { load(); }, [load, refreshKey, rk]);

  const o = overview.data;
  const m = feed.data?.metrics || {};
  const catRows = CATEGORIES.map((c) => ({ label: cap(c), count: o?.by_category?.[c] || 0, key: c }));
  const setFilter = (fn) => (v) => { setPage(1); fn(v); };

  return (
    <>
      {overview.error && !o ? <InsightError message={overview.error} onRetry={overview.reload} /> : (
        <>
          <StatGrid min={130}>
            <StatTile label="AI actions today" value={feed.data ? m.today : undefined} loading={!feed.data && feed.loading} hint="Last 24 hours" />
            <StatTile label="This week" value={feed.data ? m.week : undefined} loading={!feed.data && feed.loading} hint="Last 7 days" />
            <StatTile label="This month" value={feed.data ? m.month : undefined} loading={!feed.data && feed.loading} hint="Last 30 days" />
            <StatTile label="All recorded" value={feed.data ? m.total : undefined} loading={!feed.data && feed.loading} hint="Since logging began" />
          </StatGrid>
          <StatGrid min={130}>
            {Object.entries(OUTCOME).map(([k, v]) => (
              <StatTile key={k} label={`${v.label} · 30 days`} value={o?.by_status?.[k]} loading={overview.loading && !o}
                tone={k === 'failed' && o?.by_status?.failed ? 'error.main' : undefined}
                selected={status === k} onClick={() => setFilter(setStatus)(status === k ? '' : k)}
                hint={status === k ? 'Filtering the feed' : 'Select to filter the feed'} />
            ))}
          </StatGrid>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '3fr 2fr' }, mb: 2 }}>
            <Panel title="AI activity over time" subtitle="All outcomes · last 30 days" sx={{ mb: 0 }}>
              <TrendChart series={o?.series || []} keys={[{ key: 'count', label: 'AI actions', color: '#9d6cf7' }]} height={150}
                emptyText={overview.loading && !o ? 'Loading…' : 'No AI activity in the last 30 days.'} />
            </Panel>
            <Panel title="By category" subtitle="Last 30 days · select to filter the feed" sx={{ mb: 0 }}>
              <BreakdownBars rows={catRows} activeLabel={category ? cap(category) : undefined} color="secondary.main"
                onPick={(label) => { const c = label.toLowerCase(); setFilter(setCategory)(category === c ? '' : c); }} />
              {o && (o.feedback.good > 0 || o.feedback.bad > 0) && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
                  Admin feedback: {o.feedback.good} 👍 · {o.feedback.bad} 👎
                </Typography>
              )}
            </Panel>
          </Box>
        </>
      )}

      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mb: 1.5 }}>
        <PeriodChips value={category || 'all'} ariaLabel="AI activity category"
          options={[{ key: 'all', label: 'All' }, ...CATEGORIES.map((c) => ({ key: c, label: `${cap(c)} (${o?.by_category?.[c] ?? feed.data?.by_category?.[c] ?? 0})` }))]}
          onChange={(k) => setFilter(setCategory)(k === 'all' ? '' : k)} />
        {status && <Chip size="small" onDelete={() => setFilter(setStatus)('')} label={`Outcome: ${OUTCOME[status].label}`} />}
        <Button size="small" onClick={() => setRk((n) => n + 1)} disabled={feed.loading}>Refresh</Button>
      </Box>

      <Panel sx={{ mb: 0 }}>
        {feed.error && !feed.data ? <InsightError message={feed.error} onRetry={load} /> :
          feed.loading && !feed.data ? <Loading label="Loading activity…" /> :
          !feed.data?.events?.length ? (
            <EmptyNote>
              {category || status ? 'No AI activity matches these filters.'
                : 'No AI activity recorded yet. As the bot moderates, answers questions and runs automations, those actions appear here.'}
            </EmptyNote>
          ) : (
            <>
              {feed.error && <InsightError message={`${feed.error} - showing the last loaded page.`} onRetry={load} />}
              <TableContainer component={Paper} variant="outlined" aria-busy={feed.loading}>
                <Table size="medium" sx={{ ...fixedTableSx, tableLayout: { xs: 'auto', md: 'fixed' }, minWidth: { md: 860 } }}>
                  <TableCols widths={['38%', '12%', '12%', '18%', '20%']} />
                  <TableHead>
                    <TableRow>
                      <TableCell>Action</TableCell>
                      <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Category</TableCell>
                      <TableCell>Outcome</TableCell>
                      <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>When</TableCell>
                      <TableCell align="right">Details</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {feed.data.events.map((e) => (
                      <TableRow key={e.id} hover>
                        <TableCell>
                          <Typography variant="body2" fontWeight={600} sx={{ overflowWrap: 'anywhere' }} title={e.action}>{e.action}</Typography>
                          {(e.target || e.detail) && (
                            <Typography variant="caption" color="text.secondary" title={e.detail || ''}
                              sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', overflowWrap: 'anywhere' }}>
                              {[e.target, e.detail].filter(Boolean).join(' · ')}
                            </Typography>
                          )}
                          <Typography variant="caption" color="text.secondary" sx={{ display: { xs: 'block', md: 'none' } }}>{fmt(e.created_at)}</Typography>
                          {e.meta?.feedback?.rating && (
                            <Typography variant="caption" sx={{ display: 'block' }}>{e.meta.feedback.rating === 'good' ? '👍 reviewed' : '👎 flagged'}</Typography>
                          )}
                        </TableCell>
                        <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}><Chip size="small" variant="outlined" label={cap(e.category)} /></TableCell>
                        <TableCell><OutcomeChip status={e.status} /></TableCell>
                        <TableCell sx={{ display: { xs: 'none', md: 'table-cell' }, whiteSpace: 'nowrap' }}>{fmt(e.created_at)}</TableCell>
                        <TableCell align="right">
                          <Button size="small" onClick={() => setInspect(e)} aria-label={`Inspect: ${e.action}`}>Inspect</Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              {feed.data.pages > 1 && (
                <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                  <Pagination count={feed.data.pages} page={page} onChange={(_, p) => setPage(p)} color="primary" />
                </Box>
              )}
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                Outcomes shown are what the bot recorded: completed, skipped or failed. Actions aren't tracked as pending.
              </Typography>
            </>
          )}
      </Panel>

      {inspect && (
        <InspectDialog key={inspect.id} event={inspect} botId={botId} groupId={groupId} fmt={fmt}
          onClose={() => setInspect(null)} onSaved={() => setRk((n) => n + 1)} />
      )}
    </>
  );
}
