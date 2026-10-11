import React, { useEffect, useState } from 'react';
import { Link as RouterLink, useLocation, useSearchParams } from 'react-router-dom';
import {
  Box, Button, Chip, CircularProgress, FormControl, InputAdornment, InputLabel, MenuItem, Pagination, Paper, Select, Stack,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TableSortLabel, TextField, Typography,
} from '@mui/material';
import { Download, Search } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { engagementWs } from '../../services/api';
import { downloadCsv, exportFilename, fetchAllPages } from '../../utils/csvExport';
import { TYPES } from '../../components/CampaignManager';
import { EmptyNote, InsightError, Loading, TableCols } from '../../components/analytics/shared';
import { Freshness, STATUS_LABEL, StatusChip, TYPE_LABEL, TypeChip, fmtTime, useWorkspace, usePolled } from './common';

const STATUSES = ['draft', 'active', 'paused', 'closed', 'archived'];

function useDebounced(value, ms = 350) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

export default function Directory() {
  const ws = useWorkspace();
  const location = useLocation();
  const [sp, setSp] = useSearchParams();
  const status = sp.get('status') || '';
  const type = sp.get('type') || '';
  const sort = sp.get('sort') || 'created_at';
  const dir = sp.get('dir') || 'desc';
  const page = Math.max(1, parseInt(sp.get('page') || '1', 10) || 1);
  const [qInput, setQInput] = useState(sp.get('q') || '');
  const q = useDebounced(qInput);
  const [exporting, setExporting] = useState(false);

  // Filters live in the URL so the page is shareable, refreshable and restores on Back.
  const update = (patch) => {
    const next = new URLSearchParams(sp);
    Object.entries(patch).forEach(([k, v]) => { if (v === '' || v == null) next.delete(k); else next.set(k, v); });
    if (!('page' in patch)) next.delete('page');
    setSp(next, { replace: true });
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if ((sp.get('q') || '') !== q) update({ q }); }, [q]);

  const params = { q: q || undefined, status: status || undefined, type: type || undefined, sort, dir, page, per_page: 20 };
  const { data, loading, error, at, stale, reload } = usePolled(
    () => engagementWs.campaigns(ws.botId, ws.groupId, params), [ws.botId, ws.groupId, q, status, type, sort, dir, page, ws.tick], { enabled: ws.ready, intervalMs: 90000 });
  const rows = data?.campaigns || [];
  const filtered = !!(q || status || type);
  const from = location.pathname + location.search;

  const sortBy = (key) => update({ sort: key, dir: sort === key && dir === 'desc' ? 'asc' : 'desc' });
  const head = (key, label, align) => (
    <TableCell align={align} sortDirection={sort === key ? dir : false}>
      <TableSortLabel active={sort === key} direction={sort === key ? dir : 'desc'} onClick={() => sortBy(key)}>{label}</TableSortLabel>
    </TableCell>
  );

  const exportFiltered = async () => {
    setExporting(true);
    try {
      const { rows: all } = await fetchAllPages(async (p) => {
        const r = await engagementWs.campaigns(ws.botId, ws.groupId, { ...params, page: p, per_page: 100 });
        return { rows: r.data.campaigns, pages: r.data.pages };
      });
      if (!all.length) { toast.info('Nothing to export for these filters'); return; }
      downloadCsv(exportFilename(ws.groupName || ws.groupId, 'campaigns', status || 'all'),
        ['Campaign ID', 'Title', 'Type', 'Status', 'Starts (UTC)', 'Ends (UTC)', 'Submitted', 'Approved', 'Pending review', 'XP per approval', 'Reward (text)', 'Group post'],
        all.map((c) => [c.id, c.title, TYPE_LABEL[c.type] || c.type, STATUS_LABEL[c.status] || c.status, c.starts_at ? `${c.starts_at}Z` : '',
          c.ends_at ? `${c.ends_at}Z` : '', c.submitted, c.approved, c.pending, c.reward_xp, c.reward_label || '', c.post_status]));
      toast.success(`Exported ${all.length} ${filtered ? 'matching ' : ''}campaign${all.length === 1 ? '' : 's'} (all pages)`);
    } catch {
      toast.error('Export failed - nothing was downloaded');
    } finally {
      setExporting(false);
    }
  };

  return (
    <Box aria-busy={loading}>
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mb: 1.5 }}>
        <TextField size="small" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Search by title…" sx={{ flex: '1 1 220px' }}
          inputProps={{ 'aria-label': 'Search campaigns by title' }}
          InputProps={{ startAdornment: (<InputAdornment position="start"><Search fontSize="small" /></InputAdornment>) }} />
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel id="c-status">Status</InputLabel>
          <Select labelId="c-status" label="Status" value={status} onChange={(e) => update({ status: e.target.value })}>
            <MenuItem value="">All statuses</MenuItem>
            {STATUSES.map((s) => <MenuItem key={s} value={s}>{STATUS_LABEL[s]}{data?.status_counts?.[s] != null ? ` (${data.status_counts[s]})` : ''}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 170 }}>
          <InputLabel id="c-type">Type</InputLabel>
          <Select labelId="c-type" label="Type" value={type} onChange={(e) => update({ type: e.target.value })}>
            <MenuItem value="">All types</MenuItem>
            {TYPES.map((t) => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
          </Select>
        </FormControl>
        <Button size="small" variant="outlined" onClick={exportFiltered} disabled={exporting || !data?.total}
          startIcon={exporting ? <CircularProgress size={14} /> : <Download fontSize="small" />}>
          {exporting ? 'Exporting…' : `Export ${filtered ? 'filtered' : 'all'} (${data?.total ?? 0})`}
        </Button>
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap', mb: 1 }}>
        <Typography variant="caption" color="text.secondary" aria-live="polite">
          {data ? `${data.total.toLocaleString()} campaign${data.total === 1 ? '' : 's'}${filtered ? ' match these filters' : ' in this group'}` : ' '}
        </Typography>
        <Freshness at={at} error={error} stale={stale} tz={ws.tz} intervalMs={90000} />
      </Box>

      {error && !data ? <InsightError message={error} onRetry={reload} /> : loading && !data ? <Loading label="Loading campaigns…" /> : rows.length === 0 ? (
        <EmptyNote>{filtered ? 'No campaigns match these filters.' : 'No campaigns yet. Use “New campaign” to create the first one.'}</EmptyNote>
      ) : (
        <>
          {/* Desktop table */}
          <TableContainer component={Paper} variant="outlined" sx={{ display: { xs: 'none', md: 'block' } }}>
            <Table size="medium" sx={{ tableLayout: 'fixed', width: '100%', minWidth: 880, '& td, & th': { px: 1.5, verticalAlign: 'middle' }, '& th': { whiteSpace: 'nowrap' } }}>
              <TableCols widths={['31%', '14%', '11%', '15%', '9%', '9%', '11%']} />
              <TableHead>
                <TableRow>
                  {head('title', 'Campaign')}
                  {head('type', 'Type')}
                  {head('status', 'Status')}
                  {head('ends_at', 'Deadline')}
                  {head('submitted', 'Submitted', 'right')}
                  {head('approved', 'Approved', 'right')}
                  {head('pending', 'Pending', 'right')}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((c) => (
                  <TableRow key={c.id} hover>
                    <TableCell>
                      <Typography component={RouterLink} to={ws.paths.detail(c.id)} state={{ from }} variant="body2" fontWeight={700}
                        sx={{ color: 'text.primary', textDecoration: 'none', wordBreak: 'break-word', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', '&:hover': { textDecoration: 'underline' } }}
                        title={c.title}>
                        {c.title}
                      </Typography>
                      {c.post_status === 'failed' && <Typography variant="caption" color="error.main">Group post failed</Typography>}
                    </TableCell>
                    <TableCell><TypeChip type={c.type} /></TableCell>
                    <TableCell><StatusChip status={c.status} /></TableCell>
                    <TableCell><Typography variant="body2">{c.ends_at ? fmtTime(c.ends_at, ws.tz, { year: undefined }) : '—'}</Typography></TableCell>
                    <TableCell align="right">{c.submitted}</TableCell>
                    <TableCell align="right">{c.approved}</TableCell>
                    <TableCell align="right">
                      {c.pending > 0
                        ? <Chip size="small" color="warning" clickable component={RouterLink} to={`${ws.paths.review}?campaign=${c.id}`} label={c.pending} aria-label={`${c.pending} pending - open review queue`} />
                        : 0}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Mobile cards */}
          <Stack spacing={1.25} sx={{ display: { xs: 'flex', md: 'none' } }}>
            {rows.map((c) => (
              <Paper key={c.id} variant="outlined" sx={{ p: 1.5 }}>
                <Typography component={RouterLink} to={ws.paths.detail(c.id)} state={{ from }} variant="subtitle2"
                  sx={{ color: 'text.primary', textDecoration: 'none', fontWeight: 700, wordBreak: 'break-word' }}>{c.title}</Typography>
                <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ my: 0.75 }}>
                  <TypeChip type={c.type} /> <StatusChip status={c.status} />
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  {c.ends_at ? `Ends ${fmtTime(c.ends_at, ws.tz, { year: undefined })}` : 'No deadline'}
                </Typography>
                <Box sx={{ display: 'flex', gap: 2, mt: 0.75, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Typography variant="body2"><strong>{c.submitted}</strong> submitted</Typography>
                  <Typography variant="body2"><strong>{c.approved}</strong> approved</Typography>
                  <Typography variant="body2" color={c.pending ? 'warning.main' : 'text.secondary'}><strong>{c.pending}</strong> pending</Typography>
                  <Box sx={{ flex: 1 }} />
                  <Button size="small" component={RouterLink} to={ws.paths.detail(c.id)} state={{ from }}>Open</Button>
                </Box>
              </Paper>
            ))}
          </Stack>

          {data.pages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
              <Pagination count={data.pages} page={page} onChange={(_, p) => update({ page: String(p) })} color="primary" />
            </Box>
          )}
        </>
      )}
    </Box>
  );
}
