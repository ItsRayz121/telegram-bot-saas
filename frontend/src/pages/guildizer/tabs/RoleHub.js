import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box, Typography, TextField, Chip, CircularProgress, Alert, Stack, IconButton, Button, Tooltip, InputAdornment,
  Dialog, DialogTitle, DialogContent, DialogActions, ToggleButtonGroup, ToggleButton, FormControlLabel, Switch,
} from '@mui/material';
import { Refresh, Search, Add, Lock } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import { MemberDrawer } from './RoleDirectory';
import RoleApplications from './RoleApplications';
import ApprovalQueue from './ApprovalQueue';
import RoleHistory from './RoleHistory';

// Members → Roles: "Option A — Compact Role Hub". One searchable list of the server's
// real roles and HOW each one is given out. It reads the same settings the Welcome
// auto-roles, Self-roles and XP & Roles tabs write — it does not keep a second copy —
// so changing a role's wiring still happens there; the hub links straight to it.
const FILTERS = [
  ['all', 'All'], ['self', 'Self-select'], ['auto', 'Auto on join'], ['level', 'Level reward'], ['unused', 'Not assigned by Guildizer'],
];
const ERR = {
  already_exists: 'A role with that name already exists.',
  name_required: 'Give the role a name.',
  bad_name: "That name can't be used.",
  missing_permission: 'Guildizer needs the Manage Roles permission.',
  role_limit: 'Discord refused (the server may be at its 250-role limit).',
  discord_error: 'Discord rejected it. Try again.',
};
const fmt = (n) => (n == null ? '—' : n.toLocaleString());

export function CreateRoleDialog({ guildId, open, onClose, onCreated }) {
  const [name, setName] = useState('');
  const [color, setColor] = useState('#5865F2');
  const [hoist, setHoist] = useState(false);
  const [mentionable, setMentionable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  async function submit() {
    setBusy(true); setErr(null);
    try {
      const { data } = await guildizerApi.post(`/api/guilds/${guildId}/roles/create`, { name, color, hoist, mentionable });
      onCreated?.(data.role); setName(''); onClose();
    } catch (e) {
      const code = e?.response?.data?.error;
      if (code === 'already_exists') onCreated?.(e.response.data.role, true);
      setErr(ERR[code] || "Couldn't create the role.");
    } finally { setBusy(false); }
  }
  return (
    <Dialog open={open} onClose={() => !busy && onClose()} fullWidth maxWidth="xs">
      <DialogTitle>Create Discord role</DialogTitle>
      <DialogContent>
        <TextField autoFocus size="small" fullWidth sx={{ mt: 1 }} label="Role name" value={name} inputProps={{ maxLength: 100 }}
          onChange={(e) => setName(e.target.value)} placeholder="e.g. Active Contributor" />
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mt: 2 }}>
          <Typography variant="body2">Colour</Typography>
          <input type="color" value={color} onChange={(e) => setColor(e.target.value)} aria-label="Role colour"
            style={{ width: 48, height: 32, border: 0, background: 'transparent', cursor: 'pointer' }} />
        </Stack>
        <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
          <FormControlLabel control={<Switch size="small" checked={hoist} onChange={(e) => setHoist(e.target.checked)} />} label="Show separately in the member list" />
          <FormControlLabel control={<Switch size="small" checked={mentionable} onChange={(e) => setMentionable(e.target.checked)} />} label="Anyone can @mention" />
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block" mt={1.5}>
          Created through Discord with <b>no permissions</b> — a plain badge. Move it in Server Settings → Roles
          if you want it positioned differently.
        </Typography>
        {err && <Alert severity="error" sx={{ mt: 1.5 }}>{err}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="contained" onClick={submit} disabled={busy || !name.trim()}>{busy ? 'Creating…' : 'Create role'}</Button>
      </DialogActions>
    </Dialog>
  );
}

function WiredChips({ usage }) {
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
      {usage.self_role_menus.length > 0 && <Chip size="small" variant="outlined" color="primary" label={`Self-select · ${usage.self_role_menus.length} menu${usage.self_role_menus.length > 1 ? 's' : ''}`} />}
      {usage.auto_role && <Chip size="small" variant="outlined" color="success" label="Auto on join" />}
      {usage.level_rewards.length > 0 && <Chip size="small" variant="outlined" color="info" label={`Level ${[...usage.level_rewards].sort((a, b) => a - b).join(', ')}`} />}
    </Stack>
  );
}

export default function RoleHub({ guildId, onNavigate }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [sel, setSel] = useState(null);
  const [members, setMembers] = useState(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback((refresh = false) => {
    setBusy(true);
    return guildizerApi.get(`/api/guilds/${guildId}/roles/overview`, { params: refresh ? { refresh: 1 } : {} })
      .then(({ data: d }) => { setData(d); setErr(null); })
      .catch(() => setErr("Couldn't load roles."))
      .finally(() => setBusy(false));
  }, [guildId]);
  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => (data?.roles || []).filter((r) => {
    if (r.everyone) return false;
    const u = r.usage;
    const okF = filter === 'all' || (filter === 'self' && u.self_role_menus.length)
      || (filter === 'auto' && u.auto_role) || (filter === 'level' && u.level_rewards.length)
      || (filter === 'unused' && !u.self_role_menus.length && !u.auto_role && !u.level_rewards.length);
    return okF && (!q.trim() || r.name.toLowerCase().includes(q.trim().toLowerCase()));
  }), [data, q, filter]);

  if (err && !data) return <Alert severity="warning" action={<Button size="small" onClick={() => load()}>Retry</Button>}>{err}</Alert>;
  if (!data) return <Box sx={{ py: 3, textAlign: 'center' }}><CircularProgress size={22} /></Box>;

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
        <TextField size="small" placeholder="Search roles" value={q} onChange={(e) => setQ(e.target.value)} sx={{ flex: '1 1 180px' }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
          inputProps={{ 'aria-label': 'Search roles' }} />
        <Button size="small" variant="contained" startIcon={<Add />} onClick={() => setCreating(true)}>Create role</Button>
        <Tooltip title="Re-read from Discord"><span>
          <IconButton onClick={() => load(true)} disabled={busy} aria-label="Refresh roles">{busy ? <CircularProgress size={18} /> : <Refresh />}</IconButton>
        </span></Tooltip>
      </Stack>
      <ToggleButtonGroup exclusive size="small" value={filter} onChange={(_, v) => v && setFilter(v)} sx={{ mb: 1.5, flexWrap: 'wrap' }}>
        {FILTERS.map(([v, l]) => <ToggleButton key={v} value={v} sx={{ textTransform: 'none', px: 1.25 }}>{l}</ToggleButton>)}
      </ToggleButtonGroup>
      {data.status === 'unavailable' && <Alert severity="warning" sx={{ mb: 1.5 }}>Member counts unavailable — Discord wouldn&apos;t list members.</Alert>}

      {rows.length === 0 && <Typography variant="body2" color="text.secondary">No roles match.</Typography>}
      <Stack spacing={0.5}>
        {rows.map((r) => (
          <Stack key={r.id} direction="row" alignItems="center" spacing={1.25} onClick={() => setSel(r)} role="button" tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setSel(r)}
            aria-label={`${r.name}, ${fmt(r.member_count)} members. Open details`}
            sx={{ px: 1.25, py: 0.75, borderRadius: 1, border: '1px solid', borderColor: 'divider', cursor: 'pointer', '&:hover': { borderColor: 'primary.main' } }}>
            <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: r.color || '#99aab5', flexShrink: 0 }} aria-hidden />
            <Typography variant="body2" noWrap sx={{ flex: '1 1 140px', minWidth: 0 }}>{r.name}</Typography>
            <Box sx={{ display: { xs: 'none', sm: 'block' }, flex: '2 1 200px' }}><WiredChips usage={r.usage} /></Box>
            {!r.assignable && <Tooltip title={r.managed ? 'Integration role — managed by its app' : 'Carries moderation/management permissions — never auto-assigned'}><Lock fontSize="small" color="warning" /></Tooltip>}
            <Typography variant="body2" fontWeight={700} sx={{ minWidth: 44, textAlign: 'right' }}>{fmt(r.member_count)}</Typography>
          </Stack>
        ))}
      </Stack>

      <Box sx={{ mt: 3 }}>
        <RoleApplications guildId={guildId} safeRoles={(data.roles || []).filter((r) => r.assignable && !r.everyone)} />
      </Box>

      <Box sx={{ mt: 3 }}>
        <ApprovalQueue guildId={guildId} kinds={['rank']} roleName={(id) => (data.roles.find((r) => r.id === id) || {}).name || id} />
      </Box>

      <Box sx={{ mt: 3 }}><RoleHistory guildId={guildId} /></Box>

      <Dialog open={!!sel} onClose={() => setSel(null)} fullWidth maxWidth="xs">
        {sel && (
          <>
            <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: sel.color || '#99aab5' }} aria-hidden /> {sel.name}
            </DialogTitle>
            <DialogContent>
              <Typography variant="body2" color="text.secondary" mb={1}>{fmt(sel.member_count)} members · Discord role {sel.id}</Typography>
              <WiredChips usage={sel.usage} />
              {!sel.usage.self_role_menus.length && !sel.usage.auto_role && !sel.usage.level_rewards.length && (
                <Typography variant="body2" color="text.secondary">Guildizer doesn&apos;t hand this role out. Staff can still give it in Discord.</Typography>
              )}
              {(sel.usage.unlocks || []).length > 0 && (
                <Box sx={{ mt: 1 }}>
                  <Typography variant="caption" color="text.secondary">In Guildizer this role is also used for:</Typography>
                  {sel.usage.unlocks.map((u) => <Typography key={u} variant="body2">• {u}</Typography>)}
                </Box>
              )}
              {sel.usage.self_role_menus.length > 0 && <Typography variant="caption" color="text.secondary" display="block" mt={1}>Menus: {sel.usage.self_role_menus.join(', ')}</Typography>}
              {!sel.assignable && (
                <Alert severity="warning" sx={{ mt: 1.5 }}>
                  {sel.managed ? 'Integration role: managed by Discord or its app.' : 'This role carries moderation or management permissions, so Guildizer will never give it out automatically (self-roles or level rewards).'}
                </Alert>
              )}
              <Typography variant="subtitle2" mt={2} mb={0.5}>Where to change it</Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button size="small" variant="outlined" onClick={() => { setSel(null); onNavigate?.('Self-roles'); }}>Self-roles</Button>
                <Button size="small" variant="outlined" onClick={() => { setSel(null); onNavigate?.('Welcome'); }}>Auto-roles</Button>
                <Button size="small" variant="outlined" onClick={() => { setSel(null); onNavigate?.('XP & Roles'); }}>Level rewards</Button>
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => { setMembers(sel); setSel(null); }}>View members</Button>
              <Button onClick={() => setSel(null)}>Close</Button>
            </DialogActions>
          </>
        )}
      </Dialog>
      {members && <MemberDrawer guildId={guildId} role={members} onClose={() => setMembers(null)} />}
      <CreateRoleDialog guildId={guildId} open={creating} onClose={() => setCreating(false)} onCreated={() => load(true)} />
    </Box>
  );
}
