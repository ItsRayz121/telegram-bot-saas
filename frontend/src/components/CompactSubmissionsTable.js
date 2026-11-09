// Standard compact, spreadsheet-style submissions table.
//
// Shared by Telegizer (official + custom bots) and Guildizer (Discord). Pages map their
// own submission model into the normalized row shape below (an "adapter") and pass it
// in; everything visual / interactive lives here so every campaign looks the same.
//
//   row = {
//     id, userName ('@name' or ''), userId, taskTitle, proofUrl, proofText, proofExtra,
//     status ('pending'|'verified'|'rejected'), xp (number|null), createdAt (ISO),
//     flagged, flagReason, reviewedBy, reviewedAt, reviewReason,
//     notifyStatus ('sent'|'failed'|null), notifyError, raw (original submission)
//   }
//
// Props: rows, showTask, onApprove(row), onReject(row), renderDetail(row), emptyText.
// Review metadata ("by 1", "user notified") is NOT shown in the row any more — it lives
// in the expandable detail panel (and a tooltip on the status badge).
import React, { useMemo, useState } from 'react';
import {
  Box, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TablePagination,
  TableSortLabel, IconButton, Tooltip, Typography, TextField, MenuItem, Link, Collapse,
  Dialog, DialogTitle, DialogContent, DialogActions, Button, InputAdornment,
} from '@mui/material';
import CheckCircle from '@mui/icons-material/CheckCircle';
import Cancel from '@mui/icons-material/Cancel';
import ExpandMore from '@mui/icons-material/ExpandMore';
import ChevronRight from '@mui/icons-material/ChevronRight';
import Search from '@mui/icons-material/Search';
import WarningAmber from '@mui/icons-material/WarningAmber';

const STATUS_RANK = { pending: 0, verified: 1, rejected: 2 };
const STATUS_COLOR = { verified: 'success', rejected: 'error', pending: 'warning' };
const STATUS_LABEL = { verified: 'Verified', rejected: 'Rejected', pending: 'Pending' };

const fmtDate = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
};

const cellSx = { py: 0.5, px: 1, fontSize: '0.78rem', lineHeight: 1.25, borderColor: 'divider', whiteSpace: 'nowrap' };
const clip = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' };

export function StatusBadge({ status, xp }) {
  const c = STATUS_COLOR[status] || 'warning';
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
      <Box component="span" sx={{
        px: 0.9, py: '1px', borderRadius: '10px', fontSize: '0.68rem', fontWeight: 700, lineHeight: 1.5,
        color: (t) => t.palette.getContrastText(t.palette[c].main), bgcolor: `${c}.main`,
      }}>{STATUS_LABEL[status] || status}</Box>
      {status === 'verified' && xp > 0 && (
        <Typography component="span" sx={{ fontSize: '0.74rem', fontWeight: 600, color: 'success.main' }}>+{xp} XP</Typography>
      )}
    </Box>
  );
}

export default function CompactSubmissionsTable({
  rows, showTask = false, onApprove, onReject, renderDetail, emptyText = 'No submissions yet.',
}) {
  const [search, setSearch] = useState('');
  const [statusF, setStatusF] = useState('all');
  const [taskF, setTaskF] = useState('all');
  const [sort, setSort] = useState({ key: 'date', dir: 'desc' });
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [open, setOpen] = useState({});
  const [confirm, setConfirm] = useState(null); // row awaiting approve confirmation

  const tasks = useMemo(() => [...new Set(rows.map((r) => r.taskTitle).filter(Boolean))], [rows]);

  const view = useMemo(() => {
    const q = search.trim().toLowerCase();
    let out = rows.filter((r) => (statusF === 'all' || r.status === statusF)
      && (taskF === 'all' || r.taskTitle === taskF)
      && (!q || [r.userName, r.userId, r.taskTitle, r.proofUrl, r.proofText, r.reviewReason]
        .some((v) => v != null && String(v).toLowerCase().includes(q))));
    const dir = sort.dir === 'asc' ? 1 : -1;
    const val = {
      date: (r) => new Date(r.createdAt || 0).getTime(),
      user: (r) => (r.userName || String(r.userId || '')).toLowerCase(),
      task: (r) => (r.taskTitle || '').toLowerCase(),
      status: (r) => STATUS_RANK[r.status] ?? 9,
      xp: (r) => r.xp || 0,
    }[sort.key];
    out = [...out].sort((a, b) => {
      const x = val(a); const y = val(b);
      return (x < y ? -1 : x > y ? 1 : 0) * dir;
    });
    return out;
  }, [rows, search, statusF, taskF, sort]);

  const lastPage = Math.max(0, Math.ceil(view.length / pageSize) - 1);
  const curPage = Math.min(page, lastPage); // rows can shrink after a reload
  const pageRows = view.slice(curPage * pageSize, curPage * pageSize + pageSize);
  const toggleSort = (key) => {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'date' || key === 'xp' ? 'desc' : 'asc' }));
    setPage(0);
  };
  const SortHead = ({ k, children }) => (
    <TableSortLabel active={sort.key === k} direction={sort.key === k ? sort.dir : 'asc'} onClick={() => toggleSort(k)}
      sx={{ fontSize: 'inherit', fontWeight: 'inherit', letterSpacing: 'inherit' }}>{children}</TableSortLabel>
  );
  const colCount = 6 + (showTask ? 0 : -1) + 1; // + expander

  const headSx = { ...cellSx, py: 0.75, fontWeight: 700, fontSize: '0.68rem', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'text.secondary', bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider' };

  return (
    <Box>
      {/* single slim toolbar line — search + two filters */}
      <Box sx={{ display: 'flex', gap: 1, mb: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField size="small" placeholder="Search user, ID, task, link…" value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0); }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
          sx={{ minWidth: 220, '& .MuiInputBase-root': { height: 32, fontSize: '0.8rem' } }} />
        <TextField select size="small" value={statusF} onChange={(e) => { setStatusF(e.target.value); setPage(0); }}
          sx={{ minWidth: 120, '& .MuiInputBase-root': { height: 32, fontSize: '0.8rem' } }}>
          <MenuItem value="all">All statuses</MenuItem>
          <MenuItem value="pending">Pending</MenuItem>
          <MenuItem value="verified">Verified</MenuItem>
          <MenuItem value="rejected">Rejected</MenuItem>
        </TextField>
        {showTask && tasks.length > 1 && (
          <TextField select size="small" value={taskF} onChange={(e) => { setTaskF(e.target.value); setPage(0); }}
            sx={{ minWidth: 150, maxWidth: 260, '& .MuiInputBase-root': { height: 32, fontSize: '0.8rem' } }}>
            <MenuItem value="all">All tasks</MenuItem>
            {tasks.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
          </TextField>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
          {view.length === rows.length ? `${rows.length} submissions` : `${view.length} of ${rows.length}`}
        </Typography>
      </Box>

      <TableContainer sx={{ border: 1, borderColor: 'divider', borderRadius: 1, maxHeight: 'calc(100vh - 260px)', minHeight: 120 }}>
        <Table size="small" stickyHeader sx={{ tableLayout: 'fixed', minWidth: showTask ? 980 : 760 }}>
          <TableHead>
            <TableRow>
              <TableCell sx={{ ...headSx, width: 28, px: 0.5 }} />
              <TableCell sx={{ ...headSx, width: 150 }}><SortHead k="user">User</SortHead></TableCell>
              {showTask && <TableCell sx={{ ...headSx, width: '30%' }}><SortHead k="task">Task</SortHead></TableCell>}
              <TableCell sx={headSx}>Proof</TableCell>
              <TableCell sx={{ ...headSx, width: 168 }}><SortHead k="status">Status</SortHead>{' · '}<SortHead k="xp">XP</SortHead></TableCell>
              <TableCell sx={{ ...headSx, width: 158 }}><SortHead k="date">Submitted</SortHead></TableCell>
              <TableCell sx={{ ...headSx, width: 76 }} align="right">Review</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pageRows.length === 0 && (
              <TableRow><TableCell colSpan={colCount} sx={{ ...cellSx, textAlign: 'center', py: 3, color: 'text.secondary' }}>
                {rows.length === 0 ? emptyText : 'No submissions match these filters.'}
              </TableCell></TableRow>
            )}
            {pageRows.map((r) => {
              const isOpen = !!open[r.id];
              const audit = [
                r.reviewedAt && `Reviewed by ${r.reviewedBy || '—'}`,
                r.notifyStatus === 'sent' && 'User notified',
                r.notifyStatus === 'failed' && `Notify failed${r.notifyError ? `: ${r.notifyError}` : ''}`,
                r.status === 'rejected' && r.reviewReason && `Reason: ${r.reviewReason}`,
              ].filter(Boolean).join(' · ');
              return (
                <React.Fragment key={r.id}>
                  <TableRow hover sx={{ height: 40, cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}
                    onClick={() => setOpen((o) => ({ ...o, [r.id]: !o[r.id] }))}>
                    <TableCell sx={{ ...cellSx, px: 0.5 }}>
                      {isOpen ? <ExpandMore fontSize="small" sx={{ display: 'block', opacity: 0.6 }} />
                        : <ChevronRight fontSize="small" sx={{ display: 'block', opacity: 0.6 }} />}
                    </TableCell>
                    <TableCell sx={cellSx}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, minWidth: 0 }}>
                        <Typography noWrap sx={{ fontSize: '0.78rem', fontWeight: 700, lineHeight: 1.25 }}>
                          {r.userName || `User ${r.userId}`}
                        </Typography>
                        {r.flagged && (
                          <Tooltip title={r.flagReason || 'Flagged for review'}>
                            <WarningAmber sx={{ fontSize: 14, color: 'warning.main', flexShrink: 0 }} />
                          </Tooltip>
                        )}
                      </Box>
                      <Typography noWrap sx={{ fontSize: '0.68rem', color: 'text.secondary', lineHeight: 1.2 }}>ID: {r.userId}</Typography>
                    </TableCell>
                    {showTask && (
                      <TableCell sx={cellSx}>
                        <Tooltip title={r.taskTitle || ''} placement="top-start" enterDelay={300}>
                          <Typography component="span" sx={{ ...clip, fontSize: '0.78rem', fontWeight: 600 }}>{r.taskTitle || '—'}</Typography>
                        </Tooltip>
                      </TableCell>
                    )}
                    <TableCell sx={cellSx}>
                      {r.proofUrl ? (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
                          <Tooltip title={r.proofUrl} placement="top-start" enterDelay={300}>
                            <Link href={r.proofUrl} target="_blank" rel="noopener noreferrer" underline="hover"
                              onClick={(e) => e.stopPropagation()} sx={{ ...clip, fontSize: '0.78rem', minWidth: 0 }}>
                              {r.proofUrl}
                            </Link>
                          </Tooltip>
                          {r.proofExtra > 0 && <Typography component="span" sx={{ fontSize: '0.68rem', color: 'text.secondary', flexShrink: 0 }}>+{r.proofExtra}</Typography>}
                        </Box>
                      ) : r.proofText ? (
                        <Tooltip title={r.proofText} placement="top-start" enterDelay={300}>
                          <Typography component="span" sx={{ ...clip, fontSize: '0.78rem' }}>{r.proofText}</Typography>
                        </Tooltip>
                      ) : <Typography component="span" sx={{ fontSize: '0.78rem', color: 'text.disabled' }}>—</Typography>}
                    </TableCell>
                    <TableCell sx={cellSx}>
                      <Tooltip title={audit} placement="top-start" disableHoverListener={!audit}>
                        <span><StatusBadge status={r.status} xp={r.xp} /></span>
                      </Tooltip>
                    </TableCell>
                    <TableCell sx={cellSx}>{fmtDate(r.createdAt)}</TableCell>
                    <TableCell sx={{ ...cellSx, px: 0.5 }} align="right" onClick={(e) => e.stopPropagation()}>
                      <Tooltip title={r.status === 'verified' ? 'Approved' : 'Approve'}>
                        <span><IconButton size="small" color="success" sx={{ p: 0.25 }} disabled={r.status === 'verified'}
                          onClick={() => setConfirm(r)}><CheckCircle sx={{ fontSize: 19 }} /></IconButton></span>
                      </Tooltip>
                      <Tooltip title={r.status === 'rejected' ? 'Rejected' : 'Reject'}>
                        <span><IconButton size="small" color="error" sx={{ p: 0.25 }} disabled={r.status === 'rejected'}
                          onClick={() => onReject(r)}><Cancel sx={{ fontSize: 19 }} /></IconButton></span>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={colCount} sx={{ p: 0, border: isOpen ? undefined : 0 }}>
                      <Collapse in={isOpen} unmountOnExit>
                        <Box sx={{ px: 2, py: 1.25, bgcolor: 'action.hover', whiteSpace: 'normal' }}>
                          {audit && <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>{audit}</Typography>}
                          {r.flagged && <Typography variant="caption" color="warning.main" display="block" sx={{ mb: 1 }}>⚠ {r.flagReason || 'Flagged for review'}</Typography>}
                          {renderDetail ? renderDetail(r) : null}
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination component="div" count={view.length} page={curPage} rowsPerPage={pageSize}
        rowsPerPageOptions={[25, 50, 100]} onPageChange={(_, p) => setPage(p)}
        onRowsPerPageChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}
        sx={{ '& .MuiTablePagination-toolbar': { minHeight: 36 }, '& *': { fontSize: '0.75rem' } }} />

      <Dialog open={!!confirm} onClose={() => setConfirm(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Approve submission?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Approve the submission by <strong>{confirm?.userName || `User ${confirm?.userId}`}</strong>
            {confirm?.taskTitle ? <> for “{confirm.taskTitle}”</> : null}? Rewards are credited and the member is notified.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(null)}>Cancel</Button>
          <Button color="success" variant="contained" onClick={() => { const r = confirm; setConfirm(null); onApprove(r); }}>Approve</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

/** Shared helpers for adapters. */
const URL_RE = /https?:\/\/[^\s<>"']+/i;
export const firstUrl = (...vals) => {
  for (const v of vals) {
    if (typeof v === 'string') { const m = v.match(URL_RE); if (m) return m[0]; }
  }
  return '';
};
