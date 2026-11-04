import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Box, Typography, TextField, MenuItem, Chip, CircularProgress, Alert, Stack, IconButton, Tooltip,
  Drawer, Avatar, Button, CardActionArea, InputAdornment, useMediaQuery,
} from '@mui/material';
import { Refresh, Search, Close, Groups, Shield, Extension } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

// Settings → Overview → Roles: "Option B — Role Cards". Read-only discovery + member
// inspection. It never edits a role or a member; "Manage role" links to the Role Hub.
const SORTS = [
  ['members_desc', 'Most members'],
  ['members_asc', 'Fewest members'],
  ['hierarchy', 'Discord hierarchy'],
  ['name', 'A–Z'],
];
const TYPES = [['all', 'All'], ['community', 'Community'], ['staff', 'Staff / privileged'], ['integration', 'Integration']];
const CAT = {
  community: { label: 'Community', icon: <Groups sx={{ fontSize: 14 }} />, color: 'default' },
  staff: { label: 'Staff / privileged', icon: <Shield sx={{ fontSize: 14 }} />, color: 'warning' },
  integration: { label: 'Integration', icon: <Extension sx={{ fontSize: 14 }} />, color: 'info' },
};
const fmt = (n) => (n == null ? '—' : n.toLocaleString());

export function MemberDrawer({ guildId, role, onClose, onManage }) {
  const mobile = useMediaQuery('(max-width:600px)');
  const [q, setQ] = useState('');
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('complete');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const seq = useRef(0);

  const load = useCallback((p, query, append) => {
    const mine = ++seq.current;
    setLoading(true); setErr(null);
    return guildizerApi.get(`/api/guilds/${guildId}/roles/${role.id}/members`, { params: { q: query, page: p, limit: 25 } })
      .then(({ data }) => {
        if (mine !== seq.current) return;            // a newer search superseded this one
        setRows((r) => (append ? [...r, ...data.members] : data.members));
        setTotal(data.total); setPage(p); setStatus(data.status);
      })
      .catch((e) => {
        if (mine !== seq.current) return;
        setErr(e?.response?.data?.error === 'members_unavailable'
          ? "Discord wouldn't list this server's members. Check the Server Members intent is on for the bot."
          : "Couldn't load members.");
      })
      .finally(() => { if (mine === seq.current) setLoading(false); });
  }, [guildId, role.id]);

  useEffect(() => {
    const t = setTimeout(() => load(1, q.trim(), false), q ? 300 : 0);
    return () => clearTimeout(t);
  }, [q, load]);

  return (
    <Drawer anchor="right" open onClose={onClose}
      PaperProps={{ sx: { width: mobile ? '100%' : 400, maxWidth: '100%' } }}
      ModalProps={{ keepMounted: false }}>
      <Box role="dialog" aria-label={`Members with the ${role.name} role`} sx={{ p: 2, display: 'flex', flexDirection: 'column', height: '100%' }}>
        <Stack direction="row" alignItems="center" spacing={1} mb={1}>
          <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: role.color || '#99aab5', flexShrink: 0 }} aria-hidden />
          <Typography variant="h6" noWrap sx={{ flex: 1 }}>{role.name}</Typography>
          <IconButton onClick={onClose} aria-label="Close member list"><Close /></IconButton>
        </Stack>
        <Typography variant="body2" color="text.secondary" mb={1}>
          {total == null ? 'Loading…' : `${fmt(total)} member${total === 1 ? '' : 's'}`}
          {status === 'partial' && ' · list may be incomplete (very large server)'}
        </Typography>
        <TextField size="small" placeholder="Search name, username or ID" value={q} onChange={(e) => setQ(e.target.value)}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
          inputProps={{ 'aria-label': 'Search members in this role' }} />
        {err && <Alert severity="warning" sx={{ mt: 1.5 }} action={<Button size="small" onClick={() => load(1, q.trim(), false)}>Retry</Button>}>{err}</Alert>}
        <Box sx={{ flex: 1, overflowY: 'auto', mt: 1 }}>
          {!err && !loading && rows.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
              {q ? 'No one matches that search.' : 'Nobody holds this role.'}
            </Typography>
          )}
          {rows.map((m) => (
            <Stack key={m.id} direction="row" spacing={1.25} alignItems="center" sx={{ py: 0.75 }}>
              <Avatar src={m.avatar_url} alt="" sx={{ width: 32, height: 32 }} />
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2" noWrap>{m.display}{m.bot && <Chip size="small" label="BOT" sx={{ ml: 0.75, height: 16, fontSize: 10 }} />}</Typography>
                <Typography variant="caption" color="text.secondary" noWrap display="block">@{m.username} · {m.id}</Typography>
              </Box>
            </Stack>
          ))}
          {loading && <Box sx={{ textAlign: 'center', py: 2 }}><CircularProgress size={20} /></Box>}
          {!loading && total != null && rows.length < total && (
            <Button fullWidth size="small" onClick={() => load(page + 1, q.trim(), true)}>Load more ({fmt(total - rows.length)} left)</Button>
          )}
        </Box>
        {onManage && !role.managed && !role.everyone && (
          <Button sx={{ mt: 1 }} variant="outlined" size="small" onClick={() => onManage(role)}>Manage role</Button>
        )}
        {role.managed && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
            Integration role: managed by Discord or the app that owns it, so it can only be inspected here.
          </Typography>
        )}
      </Box>
    </Drawer>
  );
}

export default function RoleDirectory({ guildId, onManage }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState('');
  const [sort, setSort] = useState('members_desc');
  const [type, setType] = useState('all');
  const [open, setOpen] = useState(null);

  const load = useCallback((refresh = false) => {
    setBusy(true);
    return guildizerApi.get(`/api/guilds/${guildId}/roles/overview`, { params: refresh ? { refresh: 1 } : {} })
      .then(({ data: d }) => { setData(d); setErr(null); })
      .catch(() => setErr("Couldn't load roles."))
      .finally(() => setBusy(false));
  }, [guildId]);
  useEffect(() => { load(); }, [load]);

  const cards = useMemo(() => {
    const list = (data?.roles || []).filter((r) => !r.everyone
      && (type === 'all' || r.category === type)
      && (!q.trim() || r.name.toLowerCase().includes(q.trim().toLowerCase())));
    const cmp = {
      members_desc: (a, b) => (b.member_count ?? -1) - (a.member_count ?? -1) || a.name.localeCompare(b.name),
      members_asc: (a, b) => (a.member_count ?? 1e9) - (b.member_count ?? 1e9) || a.name.localeCompare(b.name),
      hierarchy: (a, b) => b.position - a.position,
      name: (a, b) => a.name.localeCompare(b.name),
    }[sort];
    return [...list].sort(cmp);
  }, [data, q, sort, type]);

  if (err && !data) return <Alert severity="warning" action={<Button size="small" onClick={() => load()}>Retry</Button>}>{err}</Alert>;
  if (!data) return <Box sx={{ py: 3, textAlign: 'center' }}><CircularProgress size={22} /></Box>;

  const roleCount = data.roles.filter((r) => !r.everyone).length;
  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
        <TextField size="small" placeholder="Search roles" value={q} onChange={(e) => setQ(e.target.value)} sx={{ flex: '1 1 160px', minWidth: 140 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
          inputProps={{ 'aria-label': 'Search roles' }} />
        <TextField select size="small" label="Sort" value={sort} onChange={(e) => setSort(e.target.value)} sx={{ minWidth: 150 }}>
          {SORTS.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Type" value={type} onChange={(e) => setType(e.target.value)} sx={{ minWidth: 150 }}>
          {TYPES.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
        </TextField>
        <Tooltip title="Re-read members from Discord"><span>
          <IconButton onClick={() => load(true)} disabled={busy} aria-label="Refresh roles and member counts">
            {busy ? <CircularProgress size={18} /> : <Refresh />}
          </IconButton>
        </span></Tooltip>
      </Stack>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        {roleCount} roles{data.totals ? ` · ${fmt(data.totals.members)} members${data.bots_included ? '' : ' (bots not counted)'}` : ''}
        {' · '}a member can hold several roles, so counts don&apos;t add up to the total.
      </Typography>
      {data.status === 'unavailable' && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          Member counts are unavailable: Discord wouldn&apos;t list members (is the <b>Server Members</b> intent on, and is the bot in the server?). Roles are shown without counts.
        </Alert>
      )}
      {data.status === 'partial' && (
        <Alert severity="info" sx={{ mb: 1.5 }}>This is a very large server — counts cover the first 10,000 members only and may be low.</Alert>
      )}
      {cards.length === 0 && <Typography variant="body2" color="text.secondary">No roles match.</Typography>}
      <Box sx={{ display: 'grid', gap: 1.25, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' } }}>
        {cards.map((r) => {
          const cat = CAT[r.category] || CAT.community;
          return (
            <CardActionArea key={r.id} onClick={() => setOpen(r)} aria-label={`${r.name}, ${r.member_count == null ? 'member count unavailable' : `${r.member_count} members`}. Open member list`}
              sx={{
                borderRadius: 2, border: '1px solid', borderColor: 'divider', borderLeft: `4px solid ${r.color || '#99aab5'}`,
                p: 1.5, bgcolor: 'background.paper', '&:hover': { borderColor: 'primary.main' }, '&.Mui-focusVisible': { outline: '2px solid', outlineColor: 'primary.main' },
              }}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Typography variant="subtitle2" noWrap sx={{ color: r.color || 'text.primary' }}>{r.name}</Typography>
                  <Chip size="small" icon={cat.icon} label={cat.label} color={cat.color} variant="outlined" sx={{ mt: 0.5, height: 20, fontSize: 11 }} />
                </Box>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography variant="h5" fontWeight={700} lineHeight={1}>{fmt(r.member_count)}</Typography>
                  <Typography variant="caption" color="text.secondary">members</Typography>
                </Box>
              </Stack>
            </CardActionArea>
          );
        })}
      </Box>
      {open && <MemberDrawer guildId={guildId} role={open} onClose={() => setOpen(null)} onManage={onManage} />}
    </Box>
  );
}
