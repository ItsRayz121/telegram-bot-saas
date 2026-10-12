import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, IconButton, MenuItem, Select, Stack, Switch,
  TextField, Tooltip, Typography,
} from '@mui/material';
import { Add, Delete, Sync, Article } from '@mui/icons-material';
import { toast } from 'react-toastify';
import guildizerApi from '../../services/guildizerApi';
import GuildizerSourceDrawer, { SCHEDULE_LABEL } from './GuildizerSourceDrawer';

const TYPE_LABEL = { website: 'Website', twitter: 'X', youtube: 'YouTube' };
const STATE_CHIP = {
  success: { label: 'Synced', color: 'success' },
  partial: { label: 'Partial', color: 'warning' },
  error: { label: 'Last sync failed', color: 'error' },
};
const fmt = (iso) => (iso ? new Date(iso).toLocaleString() : null);

/**
 * External knowledge sources (website / X / YouTube) for the Guildizer assistant.
 * Nothing is fetched until you press Sync now or choose a schedule; Manual is the
 * default. Pro feature (also enforced by the server).
 */
export default function GuildizerKnowledgeSources({ guildId }) {
  const [state, setState] = useState({ loading: true, sources: [], pro: true, enabled: true, max: 10 });
  const [url, setUrl] = useState('');
  const [adding, setAdding] = useState(false);
  const [syncing, setSyncing] = useState(null);
  const [drawer, setDrawer] = useState(null);
  const base = `/api/guilds/${guildId}/knowledge/sources`;

  const load = useCallback(async () => {
    try {
      const { data } = await guildizerApi.get(base);
      setState({ loading: false, sources: data.sources, pro: data.pro, enabled: data.enabled, max: data.max_sources });
    } catch {
      setState((s) => ({ ...s, loading: false }));
      toast.error('Could not load knowledge sources.');
    }
  }, [base]);

  useEffect(() => { load(); }, [load]);

  const err = (e, fallback) => e.response?.data?.message || e.response?.data?.error || fallback;

  async function add() {
    setAdding(true);
    try {
      await guildizerApi.post(base, { url });
      setUrl('');
      await load();
    } catch (e) { toast.error(err(e, 'Could not add that source.')); }
    setAdding(false);
  }

  async function patch(src, body) {
    try {
      await guildizerApi.patch(`${base}/${src.id}`, body);
      await load();
    } catch (e) { toast.error(err(e, 'Could not update the source.')); }
  }

  async function syncNow(src) {
    setSyncing(src.id);
    try {
      const { data } = await guildizerApi.post(`${base}/${src.id}/sync`);
      toast.success(data.unchanged ? 'Checked: nothing changed.' : data.partial ? 'Synced (partial import).' : 'Synced.');
    } catch (e) {
      toast.error(err(e, 'Sync failed.'));
    }
    setSyncing(null);
    await load();
  }

  async function remove(src) {
    try { await guildizerApi.delete(`${base}/${src.id}`); await load(); } catch (e) { toast.error(err(e, 'Could not remove it.')); }
  }

  if (state.loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 2 }}><CircularProgress size={22} /></Box>;

  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={600} mb={0.5}>External sources</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
        Let the assistant learn from a website, an X account or a YouTube channel. Nothing is fetched until you
        press Sync now or pick a schedule. Answers state which source they come from, and an older version can be
        restored at any time.
      </Typography>
      {!state.pro && <Alert severity="info" sx={{ mb: 1.5 }}>External sources are a Pro feature.</Alert>}
      {!state.enabled && <Alert severity="warning" sx={{ mb: 1.5 }}>Source syncing is temporarily paused by the platform.</Alert>}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} mb={1.5}>
        <TextField size="small" fullWidth label="Website, X or YouTube link" value={url}
          placeholder="https://example.com/docs or https://x.com/yourproject"
          onChange={(e) => setUrl(e.target.value)} disabled={!state.pro} inputProps={{ maxLength: 500 }} />
        <Button variant="contained" startIcon={<Add />} onClick={add}
          disabled={adding || !url.trim() || !state.pro || state.sources.length >= state.max}>
          Add source
        </Button>
      </Stack>

      {state.sources.length === 0 && (
        <Typography variant="body2" color="text.secondary">No external sources yet.</Typography>
      )}
      {state.sources.map((s) => {
        const chip = STATE_CHIP[s.last_sync_status];
        return (
          <Box key={s.id} sx={{ py: 1.25, borderTop: 1, borderColor: 'divider' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <Box sx={{ minWidth: 0, flex: '1 1 220px' }}>
                <Typography variant="body2" fontWeight={700} noWrap>{s.label || s.url}</Typography>
                <Typography variant="caption" color="text.secondary" noWrap display="block">
                  {TYPE_LABEL[s.source_type] || s.source_type} · {s.url}
                </Typography>
              </Box>
              <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
                {chip && <Chip size="small" color={chip.color} label={chip.label} />}
                {s.schedule_paused_reason && <Chip size="small" color="warning" label="Schedule paused" />}
                <Select size="small" value={s.sync_schedule} sx={{ minWidth: 130 }}
                  onChange={(e) => patch(s, { sync_schedule: e.target.value })} disabled={!state.pro}
                  inputProps={{ 'aria-label': 'Sync schedule' }}>
                  {Object.entries(SCHEDULE_LABEL).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
                </Select>
                <Tooltip title={s.enabled ? 'Used in answers' : 'Disabled: not used in answers'}>
                  <Switch size="small" checked={s.enabled} onChange={(e) => patch(s, { enabled: e.target.checked })} />
                </Tooltip>
                <Button size="small" variant="outlined" startIcon={syncing === s.id ? <CircularProgress size={14} /> : <Sync />}
                  disabled={syncing === s.id || !s.enabled || !state.pro || !state.enabled} onClick={() => syncNow(s)}>
                  Sync now
                </Button>
                <Tooltip title="View extracted text">
                  <IconButton size="small" onClick={() => setDrawer(s)} aria-label="View extracted text"><Article fontSize="small" /></IconButton>
                </Tooltip>
                <IconButton size="small" color="error" onClick={() => remove(s)} aria-label="Remove source"><Delete fontSize="small" /></IconButton>
              </Stack>
            </Box>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
              {s.last_success_at ? `Last synced ${fmt(s.last_success_at)}` : 'Never synced'}
              {s.next_sync_at ? ` · next ${fmt(s.next_sync_at)}` : ''}
              {s.last_sync_error ? ` · ${s.last_sync_error}` : ''}
            </Typography>
          </Box>
        );
      })}

      <GuildizerSourceDrawer open={!!drawer} onClose={() => setDrawer(null)} guildId={guildId}
        source={drawer} onChanged={load} />
    </Box>
  );
}
