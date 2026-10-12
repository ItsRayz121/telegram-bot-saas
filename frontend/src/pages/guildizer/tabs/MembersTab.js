import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Typography, TextField, MenuItem, CircularProgress,
  Alert, Stack, Chip, IconButton, Collapse, Button, Table, TableHead, TableBody, FormControlLabel, Switch,
  TableRow, TableCell, ToggleButtonGroup, ToggleButton, Tooltip, InputAdornment,
} from '@mui/material';
import { ExpandMore, ExpandLess, Download, Search } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import { downloadCsv } from './csv';
import InsightsStrip from '../../../components/guildizer/InsightsStrip';

const SORTS = [
  { value: 'xp', label: 'XP' },
  { value: 'messages', label: 'Messages' },
  { value: 'last_seen', label: 'Last seen' },
];
const PERIODS = [
  { value: 'all', label: 'All Time' },
  { value: '30d', label: '30 Days' },
  { value: '7d', label: '7 Days' },
  { value: '1d', label: 'Today' },
];

export default function MembersTab({ guildId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [members, setMembers] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('xp');
  const [period, setPeriod] = useState('all');
  const [warnedOnly, setWarnedOnly] = useState(false);
  const [matching, setMatching] = useState(0);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async (s = search) => {
    try {
      const { data } = await guildizerApi.get(
        `/api/guilds/${guildId}/members?search=${encodeURIComponent(s)}&sort=${sort}&period=${period}&limit=200${warnedOnly ? '&has_warnings=1' : ''}`,
      );
      setMembers(data.members); setTotal(data.total); setMatching(data.total_matching ?? data.members.length); setError(null);
    } catch { setError('Failed to load members.'); }
    setLoading(false);
  }, [guildId, search, sort, period, warnedOnly]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId, sort, period, warnedOnly]);

  const periodXp = period !== 'all';
  const xpLabel = period === '1d' ? 'XP (Today)' : period === '7d' ? 'XP (7d)' : period === '30d' ? 'XP (30d)' : 'XP';

  // Exports EVERY member matching the current search / filters, not just the rows
  // on screen: the list is walked page by page from the server.
  const exportCsv = async () => {
    setExporting(true);
    try {
      const all = [];
      for (let offset = 0; offset < 200000; offset += 200) {
        const { data } = await guildizerApi.get(
          `/api/guilds/${guildId}/members?search=${encodeURIComponent(search)}&sort=${sort}&period=${period}&limit=200&offset=${offset}${warnedOnly ? '&has_warnings=1' : ''}`,
        );
        all.push(...data.members);
        if (data.members.length < 200) break;
      }
      const headers = ['Name', 'User ID', xpLabel, 'Level', 'Warnings', 'Role', 'Status', 'Wallet', 'Wallet Address'];
      const rows = all.map((m) => [
        m.username || '', m.user_id, periodXp ? (m.xp_period ?? 0) : m.xp, m.level,
        m.warnings ?? 0, m.role || '', m.verified ? 'Verified' : 'Unverified',
        m.has_wallet ? 'Yes' : 'No', m.wallet || '',
      ]);
      downloadCsv(`members_${guildId}_${period}.csv`, headers, rows);
    } catch { setError('Export failed. Try again.'); }
    setExporting(false);
  };

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Card variant="outlined"><CardContent>
      <InsightsStrip guildId={guildId} kind="members" />
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} spacing={1} mb={1}>
        <Typography variant="h6" fontWeight={600}>Members ({total} tracked{matching !== total ? `, ${matching} shown` : ''})</Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <ToggleButtonGroup size="small" exclusive value={period} onChange={(_, v) => v && setPeriod(v)}>
            {PERIODS.map((p) => <ToggleButton key={p.value} value={p.value} sx={{ px: 1.2 }}>{p.label}</ToggleButton>)}
          </ToggleButtonGroup>
          <FormControlLabel sx={{ mr: 0 }} control={<Switch size="small" checked={warnedOnly} onChange={(e) => setWarnedOnly(e.target.checked)} />} label="With warnings" />
          <Button size="small" startIcon={<Download />} onClick={exportCsv} disabled={!members.length || exporting}>
            {exporting ? 'Exporting…' : `Export CSV (${matching})`}
          </Button>
        </Stack>
      </Stack>

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} mb={1}>
        <TextField size="small" fullWidth placeholder="Search name, @username, ID, wallet…" value={search}
          onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && load()}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
        <TextField select size="small" label="Sort by" value={sort} onChange={(e) => setSort(e.target.value)} sx={{ minWidth: 140 }}>
          {SORTS.map((s) => <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>)}
        </TextField>
      </Stack>

      {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}</Alert>}
      {members.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>No tracked members yet. Members appear here once they chat.</Typography>
      ) : (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ minWidth: 760 }}>
            <TableHead>
              <TableRow>
                <TableCell>USER</TableCell>
                <TableCell align="right">{xpLabel.toUpperCase()}</TableCell>
                <TableCell align="right">LEVEL</TableCell>
                <TableCell align="right">WARNINGS</TableCell>
                <TableCell>ROLE</TableCell>
                <TableCell>STATUS</TableCell>
                <TableCell>WALLET</TableCell>
                <TableCell>WALLET ADDRESS</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {members.map((m) => (
                <MemberRow key={m.user_id} guildId={guildId} member={m} periodXp={periodXp} onSaved={load} />
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </CardContent></Card>
  );
}

function MemberRow({ guildId, member, periodXp, onSaved }) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState(member.admin_notes || '');
  const [wallet, setWallet] = useState(member.wallet || '');
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await guildizerApi.put(`/api/guilds/${guildId}/members/${member.user_id}`, { admin_notes: notes, wallet });
      await onSaved();
    } catch { /* parent reload surfaces issues */ }
    setBusy(false);
  }

  const xp = periodXp ? (member.xp_period ?? 0) : member.xp;
  return (
    <>
      <TableRow hover sx={{ '& > td': { borderBottom: open ? 'none' : undefined } }}>
        <TableCell>
          <Typography variant="body2" fontWeight={700} noWrap>{member.username || member.user_id}</Typography>
          <Typography variant="caption" color="text.secondary">{member.user_id}</Typography>
        </TableCell>
        <TableCell align="right">{(xp || 0).toLocaleString()}</TableCell>
        <TableCell align="right">{member.level}</TableCell>
        <TableCell align="right">{member.warnings ? <Chip size="small" color="warning" label={member.warnings} /> : '0'}</TableCell>
        <TableCell>{member.role ? <Chip size="small" variant="outlined" label={member.role} /> : '—'}</TableCell>
        <TableCell><Chip size="small" variant="outlined" color={member.verified ? 'success' : 'default'} label={member.verified ? 'Verified' : 'Unverified'} /></TableCell>
        <TableCell><Chip size="small" variant="outlined" color={member.has_wallet ? 'info' : 'default'} label={member.has_wallet ? 'Yes' : 'No'} /></TableCell>
        <TableCell>
          {member.wallet
            ? <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>{member.wallet.length > 14 ? `${member.wallet.slice(0, 6)}…${member.wallet.slice(-4)}` : member.wallet}</Typography>
            : '—'}
        </TableCell>
        <TableCell padding="checkbox">
          <IconButton size="small" onClick={() => setOpen((v) => !v)}>{open ? <ExpandLess /> : <ExpandMore />}</IconButton>
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={9} sx={{ py: 0, border: 0 }}>
          <Collapse in={open} unmountOnExit>
            <Box sx={{ py: 1.5 }}>
              <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
                {member.messages} messages · {member.voice_minutes || 0} voice min · last seen {member.last_seen ? new Date(member.last_seen).toLocaleString() : 'never'}
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="flex-start">
                <TextField size="small" label="Wallet address" value={wallet} inputProps={{ maxLength: 120 }}
                  onChange={(e) => setWallet(e.target.value)} sx={{ minWidth: 240 }} />
                <TextField fullWidth multiline minRows={1} size="small" label="Admin notes"
                  value={notes} inputProps={{ maxLength: 2000 }} onChange={(e) => setNotes(e.target.value)} />
                <Button size="small" variant="outlined" disabled={busy} onClick={save}>Save</Button>
              </Stack>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}
