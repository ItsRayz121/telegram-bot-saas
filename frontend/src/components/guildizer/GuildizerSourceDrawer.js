import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Divider, Drawer, IconButton, InputAdornment,
  List, ListItem, ListItemText, TextField, Tooltip, Typography,
} from '@mui/material';
import { Close, Search } from '@mui/icons-material';
import { toast } from 'react-toastify';
import guildizerApi from '../../services/guildizerApi';

const STATUS = {
  ok: { label: 'Up to date', color: 'success' },
  partial: { label: 'Incomplete import', color: 'warning' },
  stale: { label: 'Stale: last sync failed or is old', color: 'warning' },
  unavailable: { label: 'Unavailable', color: 'default' },
};

export const SCHEDULE_LABEL = { manual: 'Manual', daily: 'Daily', every_3_days: 'Every 3 days', weekly: 'Weekly' };

const fmt = (iso) => (iso ? new Date(iso).toLocaleString() : null);

/** Splits `text` around case-insensitive matches of `q` into React text nodes. React
 *  escapes every string child, so scraped HTML/markup is displayed, never executed. */
function highlight(text, q) {
  if (!q) return text;
  const lower = text.toLowerCase();
  const needle = q.toLowerCase();
  const out = [];
  let from = 0;
  let idx = lower.indexOf(needle, from);
  let n = 0;
  while (idx !== -1 && n < 500) {
    if (idx > from) out.push(text.slice(from, idx));
    out.push(<mark key={idx}>{text.slice(idx, idx + needle.length)}</mark>);
    from = idx + needle.length;
    idx = lower.indexOf(needle, from);
    n += 1;
  }
  out.push(text.slice(from));
  return out;
}

function DateRow({ label, value, unknown = 'Not available' }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, py: 0.25 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="body2" sx={{ textAlign: 'right' }}>{fmt(value) || unknown}</Typography>
    </Box>
  );
}

/**
 * "View extracted text" for a Guildizer knowledge source: the exact text it adds to
 * answers, plus status, dates, counts and version history. Opening it reads STORED
 * rows only; it never triggers a provider fetch or an AI request. Restoring an older
 * version is an explicit button (it re-indexes that stored text).
 */
export default function GuildizerSourceDrawer({ open, onClose, guildId, source, onChanged }) {
  const [data, setData] = useState(null);
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [q, setQ] = useState('');
  const [restoring, setRestoring] = useState(null);
  const sourceId = source?.id;
  const base = `/api/guilds/${guildId}/knowledge/sources/${sourceId}`;

  const load = useCallback(async () => {
    if (!sourceId) return;
    setLoading(true);
    setError('');
    try {
      const [p, v] = await Promise.all([
        guildizerApi.get(`${base}/preview`),
        guildizerApi.get(`${base}/versions`),
      ]);
      setData(p.data);
      setVersions(v.data.versions || []);
    } catch (e) {
      setData(null);
      setError(e.response?.data?.error || 'Could not load the stored text for this source.');
    } finally {
      setLoading(false);
    }
  }, [base, sourceId]);

  useEffect(() => {
    if (open) { setQ(''); load(); }
  }, [open, load]);

  const matchCount = useMemo(() => {
    if (!data?.text || !q.trim()) return 0;
    return data.text.toLowerCase().split(q.trim().toLowerCase()).length - 1;
  }, [data, q]);

  const restore = async (v) => {
    setRestoring(v.id);
    try {
      const res = await guildizerApi.post(`${base}/versions/${v.id}/activate`);
      toast.success(`Version ${v.version_no} restored`);
      if (onChanged) onChanged(res.data.source);
      await load();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Could not restore that version');
    } finally {
      setRestoring(null);
    }
  };

  const st = STATUS[data?.status] || STATUS.unavailable;
  const d = data?.dates || {};

  return (
    <Drawer anchor="right" open={open} onClose={onClose}
      PaperProps={{ sx: { width: { xs: '100%', sm: 520 }, maxWidth: '100%' }, 'aria-label': 'Extracted source text' }}>
      <Box sx={{ p: 2, display: 'flex', alignItems: 'flex-start', gap: 1 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="h6" fontWeight={700} noWrap>{source?.label || source?.url}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'break-all' }}>{source?.url}</Typography>
        </Box>
        <IconButton onClick={onClose} aria-label="Close extracted text"><Close /></IconButton>
      </Box>
      <Divider />

      <Box sx={{ p: 2, overflowY: 'auto', flex: 1 }}>
        {loading && !data ? (
          <Box sx={{ display: 'grid', placeItems: 'center', py: 6 }}><CircularProgress /></Box>
        ) : error ? (
          <Alert severity="error" action={<Button color="inherit" size="small" onClick={load}>Retry</Button>}>{error}</Alert>
        ) : data && (
          <>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1.5 }}>
              <Chip size="small" color={st.color} label={st.label} />
              {data.source?.enabled === false && <Chip size="small" label="Disabled: not used in answers" />}
              <Chip size="small" variant="outlined" label={`Schedule: ${SCHEDULE_LABEL[data.source?.sync_schedule] || 'Manual'}`} />
              {data.active_version && <Chip size="small" variant="outlined" label={`Active version ${data.active_version.version_no}`} />}
            </Box>

            {data.last_error && (
              <Alert severity={data.available ? 'warning' : 'error'} sx={{ mb: 1.5 }}>
                {data.available ? 'The last sync failed, so the previous version is still being used. ' : ''}
                {data.last_error}
              </Alert>
            )}
            {data.schedule_paused_reason && <Alert severity="warning" sx={{ mb: 1.5 }}>{data.schedule_paused_reason}</Alert>}
            {data.active_version?.is_partial && (
              <Alert severity="info" sx={{ mb: 1.5 }}>
                This is a partial import (a page limit ended it early). The next sync continues from where it stopped.
              </Alert>
            )}

            <Box sx={{ mb: 2 }}>
              <DateRow label="Last attempt" value={d.last_attempt} unknown="Never" />
              <DateRow label="Last successful fetch" value={d.last_success} unknown="Never" />
              <DateRow label="Published / updated (as reported by the source)" value={d.published} unknown="Unknown" />
              <DateRow label="Indexed" value={d.indexed} unknown="Not recorded" />
              {d.next_sync && <DateRow label="Next scheduled sync" value={d.next_sync} />}
              {d.next_available && <DateRow label="Can be synced again" value={d.next_available} />}
              <Box sx={{ display: 'flex', justifyContent: 'space-between', py: 0.25 }}>
                <Typography variant="body2" color="text.secondary">Size</Typography>
                <Typography variant="body2">{data.char_count.toLocaleString()} characters · {data.chunk_count} chunks</Typography>
              </Box>
            </Box>

            {!data.available ? (
              <Alert severity="info">
                Unavailable: no extracted text is stored for this source yet. Run a sync to fetch it.
              </Alert>
            ) : (
              <>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                  This is the exact text the assistant searches when answering
                  {data.reconstructed_from_chunks ? ' (rebuilt from the indexed chunks; this source was synced before versions were stored)' : ''}.
                </Typography>
                <TextField
                  size="small" fullWidth placeholder="Search this text" value={q}
                  onChange={(e) => setQ(e.target.value)} sx={{ mb: 1 }}
                  inputProps={{ 'aria-label': 'Search extracted text' }}
                  InputProps={{ startAdornment: (<InputAdornment position="start"><Search fontSize="small" /></InputAdornment>) }}
                  helperText={q.trim() ? `${matchCount} match${matchCount === 1 ? '' : 'es'}` : ' '}
                />
                <Box component="pre" tabIndex={0} aria-label="Extracted text" sx={{
                  m: 0, p: 1.5, bgcolor: 'action.hover', borderRadius: 1, maxHeight: '45vh', overflow: 'auto',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit', fontSize: 13.5, lineHeight: 1.5,
                  '& mark': { bgcolor: 'warning.light', color: 'inherit' },
                }}>
                  {highlight(data.text, q.trim())}
                </Box>
                {data.truncated && (
                  <Typography variant="caption" color="text.secondary">Showing the first 60,000 characters.</Typography>
                )}
              </>
            )}

            {versions.length > 1 && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="subtitle2" fontWeight={700}>Version history</Typography>
                <Typography variant="caption" color="text.secondary">
                  Only the active version is used for answers. Older versions are kept for audit and rollback.
                </Typography>
                <List dense disablePadding>
                  {versions.map((v) => (
                    <ListItem key={v.id} disableGutters
                      secondaryAction={v.status === 'active' ? <Chip size="small" color="success" label="Active" /> : (
                        <Tooltip title="Re-index this stored version and make it active">
                          <span>
                            <Button size="small" disabled={restoring === v.id} onClick={() => restore(v)}>
                              {restoring === v.id ? 'Restoring…' : 'Restore'}
                            </Button>
                          </span>
                        </Tooltip>
                      )}>
                      <ListItemText
                        primary={`Version ${v.version_no}${v.is_partial ? ' (partial)' : ''}`}
                        secondary={`Fetched ${fmt(v.fetched_at) || 'unknown'} · ${v.char_count.toLocaleString()} chars${v.published_at ? ` · published ${fmt(v.published_at)}` : ' · publication date unknown'}`} />
                    </ListItem>
                  ))}
                </List>
              </Box>
            )}
          </>
        )}
      </Box>
    </Drawer>
  );
}
