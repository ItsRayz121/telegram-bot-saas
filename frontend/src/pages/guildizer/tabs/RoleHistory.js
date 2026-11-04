import React, { useCallback, useEffect, useState } from 'react';
import { Box, Typography, Stack, Chip, Button, CircularProgress } from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';

// Read-only award trail: who received which role and where it came from (level reward,
// self-selected, application, staff grant/revoke). Roles changed directly in Discord (or by
// another bot) show as "Changed in Discord" a few seconds after the change.
export default function RoleHistory({ guildId }) {
  const [rows, setRows] = useState(null);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = useCallback((offset = 0) => {
    setBusy(true);
    return guildizerApi.get(`/api/guilds/${guildId}/roles/history`, { params: { limit: 20, offset } })
      .then(({ data }) => { setRows((r) => (offset ? [...(r || []), ...data.events] : data.events)); setTotal(data.total); setFailed(false); })
      .catch(() => setFailed(true)).finally(() => setBusy(false));
  }, [guildId]);
  useEffect(() => { load(0); }, [load]);

  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={600} mb={0.5}>Award history</Typography>
      {failed && <Typography variant="body2" color="error">Couldn&apos;t load history.</Typography>}
      {!rows && !failed && <CircularProgress size={18} />}
      {rows && rows.length === 0 && <Typography variant="body2" color="text.secondary">No role changes recorded yet.</Typography>}
      <Stack spacing={0.5}>
        {rows?.map((e) => (
          <Stack key={e.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap
            sx={{ px: 1, py: 0.5, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
            <Chip size="small" variant="outlined" label={e.source} />
            <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }} noWrap>{e.username || e.user_id || '—'} · {e.detail}</Typography>
            <Typography variant="caption" color="text.secondary">{e.at ? new Date(e.at).toLocaleString() : ''}</Typography>
          </Stack>
        ))}
      </Stack>
      {rows && rows.length < total && <Button size="small" disabled={busy} onClick={() => load(rows.length)}>Load more</Button>}
    </Box>
  );
}
