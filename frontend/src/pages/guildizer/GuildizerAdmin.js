import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Grid, Card, CardContent, Typography, Button, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, TextField, List, ListItem, ListItemText, CircularProgress, Alert, Stack,
} from '@mui/material';
import { ArrowBack } from '@mui/icons-material';
import guildizerApi from '../../services/guildizerApi';

const STAT_LABELS = {
  guilds_total: 'Servers', guilds_with_bot: 'Bot installed', guilds_pro: 'Pro servers',
  users_total: 'Users', members_total: 'Members', campaigns_total: 'Campaigns',
  campaigns_active: 'Active campaigns', submissions_total: 'Submissions',
  submissions_verified: 'Verified', protection_events_total: 'Protection events',
  xp_events_total: 'XP grants', subscriptions_active: 'Active subs',
};

export default function GuildizerAdmin() {
  const navigate = useNavigate();
  const [state, setState] = useState({ loading: true, allowed: false });
  const [overview, setOverview] = useState(null);
  const [guilds, setGuilds] = useState([]);
  const [events, setEvents] = useState([]);
  const [days, setDays] = useState(30);

  async function loadGuilds() {
    const { data } = await guildizerApi.get('/api/admin/guilds'); setGuilds(data.guilds);
  }

  useEffect(() => {
    (async () => {
      try {
        const [ov, ev] = await Promise.all([
          guildizerApi.get('/api/admin/overview'),
          guildizerApi.get('/api/admin/events?limit=40'),
        ]);
        setOverview(ov.data); setEvents(ev.data.events);
        await loadGuilds();
        setState({ loading: false, allowed: true });
      } catch (e) {
        setState({ loading: false, allowed: e?.response?.status !== 403 && e?.response?.status !== 401 ? null : false });
      }
    })();
  }, []);

  async function setPlan(guildId, plan) {
    await guildizerApi.post(`/api/admin/guilds/${guildId}/plan`, { plan, days });
    loadGuilds();
  }

  if (state.loading) return <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 320 }}><CircularProgress /></Box>;

  if (!state.allowed) {
    return (
      <Box sx={{ maxWidth: 1000, mx: 'auto', px: 3, py: 3 }}>
        <Button startIcon={<ArrowBack />} onClick={() => navigate('/guildizer')} color="inherit" sx={{ mb: 2 }}>Back</Button>
        <Alert severity={state.allowed === null ? 'error' : 'warning'}>
          {state.allowed === null ? 'Failed to load admin data.' : "You don't have Guildizer admin access."}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 1100, mx: 'auto', px: { xs: 2, md: 3 }, py: 3 }}>
      <Button startIcon={<ArrowBack />} onClick={() => navigate('/guildizer')} color="inherit" sx={{ mb: 1 }}>Back to servers</Button>
      <Typography variant="h5" fontWeight={800} mb={2}>Guildizer Admin</Typography>

      <Grid container spacing={1.5} mb={3}>
        {Object.entries(STAT_LABELS).map(([k, label]) => (
          <Grid item xs={6} sm={4} md={2} key={k}>
            <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
              <Typography variant="h6" fontWeight={800}>{overview?.[k] ?? 0}</Typography>
              <Typography variant="caption" color="text.secondary">{label}</Typography>
            </CardContent></Card>
          </Grid>
        ))}
      </Grid>

      <Card variant="outlined" sx={{ mb: 3 }}><CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
          <Typography variant="subtitle1" fontWeight={700}>Servers</Typography>
          <TextField type="number" size="small" label="Pro days" value={days} onChange={(e) => setDays(Number(e.target.value))} sx={{ width: 110 }} inputProps={{ min: 1 }} />
        </Stack>
        <Table size="small">
          <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Members</TableCell><TableCell>Plan</TableCell><TableCell align="right">Actions</TableCell></TableRow></TableHead>
          <TableBody>
            {guilds.map((g) => (
              <TableRow key={g.id} hover>
                <TableCell>{g.name}</TableCell>
                <TableCell>{g.member_count}</TableCell>
                <TableCell><Chip size="small" label={g.plan} color={g.is_pro ? 'success' : 'default'} /></TableCell>
                <TableCell align="right">
                  <Button size="small" onClick={() => setPlan(g.id, 'pro')}>Grant Pro</Button>
                  <Button size="small" color="inherit" onClick={() => setPlan(g.id, 'free')}>Free</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent></Card>

      <Grid container spacing={2} mb={3}>
        <Grid item xs={12} md={6}><AiHealthCard /></Grid>
        <Grid item xs={12} md={6}><FleetCard /></Grid>
        <Grid item xs={12} md={6}><UsageCard /></Grid>
        <Grid item xs={12} md={6}><PromoAdminCard /></Grid>
        <Grid item xs={12} md={6}><RolesCard /></Grid>
        <Grid item xs={12}><AuditLogCard /></Grid>
      </Grid>

      <Card variant="outlined"><CardContent>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Recent protection events</Typography>
        {events.length === 0 && <Typography variant="body2" color="text.secondary">No events.</Typography>}
        <List dense>
          {events.map((e) => (
            <ListItem key={e.id} disableGutters secondaryAction={<Typography variant="caption" color="text.disabled">{new Date(e.created_at).toLocaleString()}</Typography>}>
              <Chip size="small" label={e.category} sx={{ mr: 1 }} variant="outlined" />
              <ListItemText primary={`${e.action} — ${e.username ? e.username + ' · ' : ''}${e.detail || ''}`} primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
            </ListItem>
          ))}
        </List>
      </CardContent></Card>
    </Box>
  );
}


function AiHealthCard() {
  const [data, setData] = useState(null);
  const [ping, setPing] = useState(null);
  const [testing, setTesting] = useState(false);

  const load = () => guildizerApi.get('/api/admin/ai-health')
    .then(({ data: d }) => setData(d)).catch(() => setData(null));
  useEffect(() => { load(); }, []);

  const runPing = async () => {
    setTesting(true); setPing(null);
    try {
      const { data: d } = await guildizerApi.get('/api/admin/ai-health?ping=1');
      setData(d); setPing(d.ping);
    } catch {
      setPing({ ok: false, error: 'request failed' });
    } finally {
      setTesting(false);
    }
  };

  if (!data) return null;
  const provLabel = { openrouter: 'OpenRouter', openai: 'OpenAI', anthropic: 'Anthropic' };
  return (
    <Card variant="outlined"><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
        <Typography variant="subtitle1" fontWeight={700}>AI provider health</Typography>
        <Chip size="small" label={data.configured ? 'Configured' : 'No key'}
          color={data.configured ? 'success' : 'warning'} variant="outlined" />
      </Stack>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Rollup order: {data.chain.map((p) => provLabel[p] || p).join(' → ')}
      </Typography>
      <Stack direction="row" useFlexGap flexWrap="wrap" spacing={0.5} mb={1}>
        {Object.entries(data.providers).map(([key, p]) => (
          <Chip key={key} size="small" variant="outlined"
            color={p.key_set ? 'success' : 'default'}
            label={`${provLabel[key] || key}: ${p.key_set ? p.model : 'no key'}`} />
        ))}
      </Stack>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Vision (NSFW images): {data.vision.available ? `✓ ${data.vision.model}` : '✗ needs OpenAI key'}
      </Typography>
      <Button size="small" variant="contained" onClick={runPing} disabled={testing}>
        {testing ? 'Testing…' : 'Test now (live ping)'}
      </Button>
      {ping && (
        <Alert severity={ping.ok ? 'success' : 'error'} sx={{ mt: 1 }}>
          {ping.ok
            ? `Answered by ${provLabel[ping.provider_used] || ping.provider_used} (${ping.model}) in ${ping.latency_ms}ms · reply: "${ping.text}"`
            : `Failed: ${ping.error || 'no provider responded'}`}
        </Alert>
      )}
    </CardContent></Card>
  );
}

function FleetCard() {
  const [data, setData] = useState(null);
  useEffect(() => {
    guildizerApi.get('/api/admin/fleet').then(({ data: d }) => setData(d)).catch(() => {});
  }, []);
  if (!data) return null;
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>White-label fleet ({data.bots.length})</Typography>
      {data.bots.length === 0 && <Typography variant="body2" color="text.secondary">No custom bots connected.</Typography>}
      <List dense>
        {data.bots.map((b) => (
          <ListItem key={b.id} disableGutters
            secondaryAction={<Chip size="small" variant="outlined"
              color={b.status === 'active' ? 'success' : b.status === 'error' ? 'error' : 'default'} label={b.status} />}>
            <ListItemText primary={'@' + b.bot_username}
              secondary={`${b.linked_guild_count} server(s)${b.error_detail ? ' · ' + b.error_detail : ''}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
      </List>
      {data.events.length > 0 && (
        <Typography variant="caption" color="text.secondary">
          Last event: {data.events[0].event} · {new Date(data.events[0].created_at).toLocaleString()}
        </Typography>
      )}
    </CardContent></Card>
  );
}

function UsageCard() {
  const [features, setFeatures] = useState(null);
  const [ai, setAi] = useState(null);
  useEffect(() => {
    guildizerApi.get('/api/admin/feature-usage?days=14').then(({ data }) => setFeatures(data)).catch(() => {});
    guildizerApi.get('/api/admin/ai-usage?days=30').then(({ data }) => setAi(data)).catch(() => {});
  }, []);
  if (!features) return null;
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>
        Feature usage — {features.total} command runs / {features.days}d
      </Typography>
      <Stack direction="row" useFlexGap flexWrap="wrap" spacing={0.5} mb={1}>
        {features.features.slice(0, 12).map((f) => (
          <Chip key={f.feature} size="small" variant="outlined" label={`/${f.feature} · ${f.count}`} />
        ))}
        {features.features.length === 0 && <Typography variant="body2" color="text.secondary">No usage yet.</Typography>}
      </Stack>
      {ai && (
        <Typography variant="caption" color="text.secondary">
          AI ({ai.days}d): {ai.calls} calls · {ai.input_tokens + ai.output_tokens} tokens
        </Typography>
      )}
    </CardContent></Card>
  );
}

function PromoAdminCard() {
  const [codes, setCodes] = useState([]);
  const [daysFree, setDaysFree] = useState(30);
  const [maxUses, setMaxUses] = useState(10);

  const load = () => guildizerApi.get('/api/admin/promo-codes')
    .then(({ data }) => setCodes(data.codes)).catch(() => {});
  useEffect(() => { load(); }, []);

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>Promo codes</Typography>
      <Stack direction="row" spacing={1} alignItems="center" mb={1}>
        <TextField type="number" size="small" label="Days" value={daysFree}
          onChange={(e) => setDaysFree(Number(e.target.value))} sx={{ width: 90 }} />
        <TextField type="number" size="small" label="Max uses" value={maxUses}
          onChange={(e) => setMaxUses(Number(e.target.value))} sx={{ width: 100 }} />
        <Button size="small" variant="contained"
          onClick={() => guildizerApi.post('/api/admin/promo-codes', { days_free: daysFree, max_uses: maxUses }).then(load)}>
          Generate
        </Button>
      </Stack>
      <List dense>
        {codes.map((c) => (
          <ListItem key={c.id} disableGutters
            secondaryAction={c.enabled && (
              <Button size="small" color="inherit"
                onClick={() => guildizerApi.delete(`/api/admin/promo-codes/${c.id}`).then(load)}>
                Disable
              </Button>
            )}>
            <ListItemText primary={<code>{c.code}</code>}
              secondary={`${c.days_free}d free · ${c.used_count}/${c.max_uses} used${c.enabled ? '' : ' · disabled'}`} />
          </ListItem>
        ))}
        {codes.length === 0 && <Typography variant="body2" color="text.secondary">No codes yet.</Typography>}
      </List>
    </CardContent></Card>
  );
}

function RolesCard() {
  const [data, setData] = useState(null);
  const [uid, setUid] = useState('');
  const [role, setRole] = useState('support');

  const load = () => guildizerApi.get('/api/admin/roles')
    .then(({ data: d }) => setData(d)).catch(() => setData(null));
  useEffect(() => { load(); }, []);

  if (!data) return null;
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>Admin roles</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Env super admins: {data.env_super_ids.join(', ') || 'none'}. Grants below need a super admin.
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" mb={1}>
        <TextField size="small" label="Discord user ID" value={uid}
          onChange={(e) => setUid(e.target.value)} sx={{ flex: 1 }} />
        <TextField select size="small" label="Role" value={role} onChange={(e) => setRole(e.target.value)}
          SelectProps={{ native: true }} sx={{ width: 110 }}>
          <option value="support">support</option>
          <option value="super">super</option>
        </TextField>
        <Button size="small" variant="contained" disabled={!/^\d+$/.test(uid.trim())}
          onClick={() => guildizerApi.post('/api/admin/roles', { user_id: uid.trim(), role }).then(() => { setUid(''); load(); })}>
          Grant
        </Button>
      </Stack>
      <List dense>
        {data.roles.map((r) => (
          <ListItem key={r.user_id} disableGutters
            secondaryAction={(
              <Button size="small" color="inherit"
                onClick={() => guildizerApi.delete(`/api/admin/roles/${r.user_id}`).then(load)}>
                Revoke
              </Button>
            )}>
            <Chip size="small" variant="outlined" label={r.role} sx={{ mr: 1 }} />
            <ListItemText primary={r.username || r.user_id} />
          </ListItem>
        ))}
        {data.roles.length === 0 && <Typography variant="body2" color="text.secondary">No DB-granted roles.</Typography>}
      </List>
    </CardContent></Card>
  );
}

function AuditLogCard() {
  const [entries, setEntries] = useState([]);
  useEffect(() => {
    guildizerApi.get('/api/admin/audit-log').then(({ data }) => setEntries(data.entries)).catch(() => {});
  }, []);
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>Admin audit log</Typography>
      {entries.length === 0 && <Typography variant="body2" color="text.secondary">No admin actions recorded yet.</Typography>}
      <List dense>
        {entries.map((e) => (
          <ListItem key={e.id} disableGutters
            secondaryAction={<Typography variant="caption" color="text.disabled">{new Date(e.created_at).toLocaleString()}</Typography>}>
            <Chip size="small" variant="outlined" label={e.action} sx={{ mr: 1 }} />
            <ListItemText
              primary={`${e.target || ''} ${e.detail ? '— ' + e.detail : ''}`}
              secondary={`by ${e.admin_id}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
      </List>
    </CardContent></Card>
  );
}