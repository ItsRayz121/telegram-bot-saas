import React, { useMemo, useState } from 'react';
import {
  Alert, Avatar, Box, Button, InputAdornment, MenuItem, Pagination, Select, TextField,
  ToggleButton, ToggleButtonGroup, Typography,
} from '@mui/material';
import { EmojiEvents, Groups, PersonAdd, Bolt, Search, Save } from '@mui/icons-material';
import DailyBars from '../charts/DailyBars';
import { Kpi, DashPanel, ShareRow, dashCard, initial, pct } from '../charts/DashCards';

const PAGE = 10;
const num = (n) => Number(n || 0).toLocaleString();
const card = dashCard;
const Panel = DashPanel;
const ini = initial;
function Person({ name, size = 28 }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
      <Avatar sx={{ width: size, height: size, fontSize: size * 0.45, bgcolor: 'primary.main', flexShrink: 0 }}>{ini(name)}</Avatar>
      <Typography variant="body2" noWrap>{name || 'unknown'}</Typography>
    </Box>
  );
}

export default function ReferralDashboard({ data, xp, setXp, onSave, saving, saved, xpError }) {
  const [range, setRange] = useState(14);
  const [q, setQ] = useState('');
  const [tableRange, setTableRange] = useState(0);
  const [page, setPage] = useState(1);

  const leaders = data.leaderboard || [];
  const recent = useMemo(() => data.recent || [], [data.recent]);
  const total = data.total_joins ?? recent.length;
  const top = leaders[0];
  const activeInviters = data.active_inviters ?? leaders.length;

  const daily = useMemo(() => {
    if (Array.isArray(data.daily)) return data.daily;
    // Older backend without the daily series: derive it from the recent joins we do have.
    const m = {};
    recent.forEach((r) => { const d = (r.created_at || '').slice(0, 10); if (d) m[d] = (m[d] || 0) + 1; });
    const out = [];
    for (let i = 29; i >= 0; i -= 1) {
      const d = new Date(Date.now() - i * 864e5).toISOString().slice(0, 10);
      out.push({ day: d, joins: m[d] || 0 });
    }
    return out;
  }, [data.daily, recent]);
  const series = daily.slice(-range);
  const rangeTotal = series.reduce((a, d) => a + d.joins, 0);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const cutoff = tableRange ? Date.now() - tableRange * 864e5 : 0;
    return recent.filter((r) => (!cutoff || new Date(r.created_at).getTime() >= cutoff)
      && (!needle || [r.joiner_name, r.joiner_id, r.inviter_name, r.code].some((v) => String(v || '').toLowerCase().includes(needle))));
  }, [recent, q, tableRange]);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const cur = Math.min(page, pages);
  const shown = rows.slice((cur - 1) * PAGE, cur * PAGE);

  const xpNum = Number(xp);
  const xpInvalid = xp === '' || !Number.isInteger(xpNum) || xpNum < 0 || xpNum > 1000;

  return (
    <Box sx={{ display: 'grid', gap: 2 }}>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' } }}>
        <Kpi icon={<Groups />} tone="#3BA55D" label="Referral joins" value={num(total)} hint="Via tracked invites" />
        <Kpi icon={<EmojiEvents />} tone="#9d6cf7" label="Top inviter" value={top ? num(top.joins) : '—'}
          hint={top ? `${top.inviter_name || top.inviter_id} · ${pct(top.joins, total)} of joins` : 'No inviters yet'} />
        <Kpi icon={<PersonAdd />} tone="#3d8ef8" label="Active inviters" value={num(activeInviters)} hint="With recorded joins" />
        <Kpi icon={<Bolt />} tone="#FAA61A" label="XP per referral" value={`${num(data.xp_per_referral)} XP`} hint="Current setting" />
      </Box>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0,1fr))', xl: '3fr 4fr 5fr' } }}>
        <Panel title="Referral rewards">
          <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
            The bot tracks which invite each member joined through. Members create their own tracked link with /invitelink.
          </Typography>
          <TextField type="number" size="small" fullWidth label="XP per successful referral" value={xp}
            error={xpInvalid} helperText={xpInvalid ? 'Enter a whole number from 0 to 1000.' : ' '}
            inputProps={{ min: 0, max: 1000, step: 1 }} onChange={(e) => setXp(e.target.value)} />
          <Button variant="contained" startIcon={<Save />} disabled={saving || xpInvalid} onClick={onSave} sx={{ mt: 0.5 }}>
            {saving ? 'Saving…' : 'Save changes'}
          </Button>
          {saved && <Alert severity="success" sx={{ mt: 1.5 }}>Saved.</Alert>}
          {xpError && <Alert severity="error" sx={{ mt: 1.5 }}>{xpError}</Alert>}
        </Panel>

        <Panel title="Top inviters" action={<Typography variant="caption" color="text.secondary">Total: {num(total)} joins</Typography>}>
          {leaders.length === 0 && <Typography variant="body2" color="text.secondary">No tracked invites yet.</Typography>}
          {leaders.slice(0, 10).map((r, i) => (
            <ShareRow key={r.inviter_id} index={i} name={r.inviter_name || r.inviter_id} count={r.joins} total={total} />
          ))}
        </Panel>

        <Panel title="Referral activity · joins per day" action={(
          <ToggleButtonGroup size="small" exclusive value={range} onChange={(_, v) => v && setRange(v)} aria-label="Range">
            <ToggleButton value={7}>7D</ToggleButton><ToggleButton value={14}>14D</ToggleButton><ToggleButton value={30}>30D</ToggleButton>
          </ToggleButtonGroup>
        )}>
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Total {num(rangeTotal)} joins · Avg {(rangeTotal / Math.max(1, series.length)).toFixed(1)}/day
          </Typography>
          <DailyBars series={series} dateKey="day" keys={[{ key: 'joins', label: 'Joins', color: '#7c6cf0' }]} />
        </Panel>
      </Box>

      <Box sx={card}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1.5, flexWrap: 'wrap', mb: 1.5 }}>
          <Box>
            <Typography fontWeight={700}>Recent joins via invites</Typography>
            <Typography variant="caption" color="text.secondary">The latest members to join and which invite brought them in.</Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <TextField size="small" placeholder="Search member or inviter…" value={q}
              onChange={(e) => { setQ(e.target.value); setPage(1); }}
              InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
            <Select size="small" value={tableRange} onChange={(e) => { setTableRange(e.target.value); setPage(1); }} inputProps={{ 'aria-label': 'Date range' }}>
              <MenuItem value={0}>All loaded</MenuItem><MenuItem value={7}>Last 7 days</MenuItem>
              <MenuItem value={14}>Last 14 days</MenuItem><MenuItem value={30}>Last 30 days</MenuItem>
            </Select>
          </Box>
        </Box>
        <Box sx={{ overflowX: 'auto' }}>
          <Box component="table" sx={{
            width: '100%', minWidth: 560, borderCollapse: 'collapse',
            '& th': { textAlign: 'left', fontSize: 12, color: 'text.secondary', fontWeight: 600, p: 1 },
            '& td': { p: 1, borderTop: 1, borderColor: 'divider' },
            '& tbody tr:hover': { bgcolor: 'action.hover' },
          }}>
            <thead><tr><th>#</th><th>Member</th><th>Invited by</th><th>Invite code</th><th>Joined at</th></tr></thead>
            <tbody>
              {shown.map((r, i) => (
                <tr key={r.id}>
                  <td><Typography variant="caption" color="text.secondary">{(cur - 1) * PAGE + i + 1}</Typography></td>
                  <td><Person name={r.joiner_name || r.joiner_id} /></td>
                  <td>{r.inviter_name ? <Person name={r.inviter_name} /> : <Typography variant="body2" color="text.secondary">unknown</Typography>}</td>
                  <td>{r.code ? <Box component="code" sx={{ px: 1, py: 0.25, borderRadius: 1, border: 1, borderColor: 'divider', fontSize: 12 }}>{r.code}</Box> : '—'}</td>
                  <td><Typography variant="body2" noWrap>{r.created_at ? new Date(r.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—'}</Typography></td>
                </tr>
              ))}
            </tbody>
          </Box>
        </Box>
        {shown.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
            {recent.length === 0 ? 'No joins via tracked invites yet.' : 'No joins match your search or date range.'}
          </Typography>
        )}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1.5, flexWrap: 'wrap', gap: 1 }}>
          <Typography variant="caption" color="text.secondary">
            Showing {rows.length ? `${(cur - 1) * PAGE + 1}–${(cur - 1) * PAGE + shown.length}` : 0} of {num(rows.length)}
            {total > recent.length ? ` · latest ${num(recent.length)} of ${num(total)} joins loaded` : ''}
          </Typography>
          {pages > 1 && <Pagination size="small" count={pages} page={cur} onChange={(_, p) => setPage(p)} />}
        </Box>
      </Box>
    </Box>
  );
}
