import React, { useEffect, useState } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import {
  Box, Grid, Card, CardContent, Typography, Button, Chip, Stack, Alert,
  Table, TableHead, TableBody, TableRow, TableCell, TextField, List, ListItem, ListItemText,
} from '@mui/material';
import {
  Groups, SmartToy, WorkspacePremium, People, Campaign, Verified,
  Shield, Bolt, ConstructionRounded,
} from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import {
  StatCard, SectionTitle, EmptyRow, fmtDateTime,
} from '../../../components/guildizer/GuildizerAdminKit';
import {
  GUILDIZER_ADMIN_CATEGORIES, findGuildizerAdminItem, DEFAULT_GUILDIZER_ADMIN_KEY,
} from '../../../config/guildizerAdminNav';
import { useGuildizerAdmin } from '../../../contexts/GuildizerAdminContext';
import { PALETTE } from '../../../theme';

const PAGE_SX = { maxWidth: 1400, mx: 'auto', px: { xs: 2, md: 3 }, py: 2.5 };

// ── Overview / Dashboard ─────────────────────────────────────────────────────
const STAT_TILES = [
  { key: 'guilds_total', label: 'Servers', icon: Groups, color: PALETTE.blue },
  { key: 'guilds_with_bot', label: 'Bot installed', icon: SmartToy, color: PALETTE.cyan },
  { key: 'guilds_pro', label: 'Pro servers', icon: WorkspacePremium, color: PALETTE.green },
  { key: 'users_total', label: 'Users', icon: People, color: PALETTE.purple },
  { key: 'members_total', label: 'Members', icon: People, color: PALETTE.blue },
  { key: 'campaigns_active', label: 'Active campaigns', icon: Campaign, color: PALETTE.amber },
  { key: 'submissions_verified', label: 'Verified proofs', icon: Verified, color: PALETTE.green },
  { key: 'protection_events_total', label: 'Protection events', icon: Shield, color: PALETTE.red },
  { key: 'subscriptions_active', label: 'Active subs', icon: WorkspacePremium, color: PALETTE.green },
  { key: 'xp_events_total', label: 'XP grants', icon: Bolt, color: PALETTE.cyan },
];

function DashboardSection() {
  const [overview, setOverview] = useState(null);
  const [guilds, setGuilds] = useState([]);
  const [events, setEvents] = useState([]);
  const [days, setDays] = useState(30);

  const loadGuilds = () => guildizerApi.get('/api/admin/guilds').then(({ data }) => setGuilds(data.guilds)).catch(() => {});
  useEffect(() => {
    guildizerApi.get('/api/admin/overview').then(({ data }) => setOverview(data)).catch(() => {});
    guildizerApi.get('/api/admin/events?limit=30').then(({ data }) => setEvents(data.events)).catch(() => {});
    loadGuilds();
  }, []);

  const setPlan = (guildId, plan) =>
    guildizerApi.post(`/api/admin/guilds/${guildId}/plan`, { plan, days }).then(loadGuilds).catch(() => {});

  return (
    <>
      <Grid container spacing={1.5} mb={3}>
        {STAT_TILES.map((t) => (
          <Grid item xs={6} sm={4} md={2.4} key={t.key}>
            <StatCard value={overview?.[t.key] ?? 0} label={t.label} icon={t.icon} color={t.color} />
          </Grid>
        ))}
      </Grid>

      <Card variant="outlined" sx={{ mb: 3 }}><CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
          <Typography variant="subtitle1" fontWeight={700}>Servers</Typography>
          <TextField type="number" size="small" label="Pro days" value={days}
            onChange={(e) => setDays(Number(e.target.value))} sx={{ width: 110 }} inputProps={{ min: 1 }} />
        </Stack>
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Name</TableCell><TableCell>Members</TableCell><TableCell>Plan</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {guilds.length === 0 && <EmptyRow colSpan={4} label="No servers yet." />}
            {guilds.map((g) => (
              <TableRow key={g.id} hover>
                <TableCell>{g.name}</TableCell>
                <TableCell>{g.member_count}</TableCell>
                <TableCell><Chip size="small" label={g.plan} color={g.is_pro ? 'success' : 'default'} variant="outlined" /></TableCell>
                <TableCell align="right">
                  <Button size="small" onClick={() => setPlan(g.id, 'pro')}>Grant Pro</Button>
                  <Button size="small" color="inherit" onClick={() => setPlan(g.id, 'free')}>Free</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent></Card>

      <Card variant="outlined"><CardContent>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Recent protection events</Typography>
        {events.length === 0 && <Typography variant="body2" color="text.secondary">No events.</Typography>}
        <List dense>
          {events.map((e) => (
            <ListItem key={e.id} disableGutters secondaryAction={<Typography variant="caption" color="text.disabled">{fmtDateTime(e.created_at)}</Typography>}>
              <Chip size="small" label={e.category} sx={{ mr: 1 }} variant="outlined" />
              <ListItemText primary={`${e.action} — ${e.username ? e.username + ' · ' : ''}${e.detail || ''}`}
                primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
            </ListItem>
          ))}
        </List>
      </CardContent></Card>
    </>
  );
}

// ── AI Management (platform/ai) ──────────────────────────────────────────────
function AiManagementSection() {
  const [data, setData] = useState(null);
  const [ping, setPing] = useState(null);
  const [testing, setTesting] = useState(false);
  const [usage, setUsage] = useState(null);

  const load = () => guildizerApi.get('/api/admin/ai-health').then(({ data: d }) => setData(d)).catch(() => {});
  useEffect(() => {
    load();
    guildizerApi.get('/api/admin/ai-usage?days=30').then(({ data: d }) => setUsage(d)).catch(() => {});
  }, []);

  const runPing = async () => {
    setTesting(true); setPing(null);
    try { const { data: d } = await guildizerApi.get('/api/admin/ai-health?ping=1'); setData(d); setPing(d.ping); }
    catch { setPing({ ok: false, error: 'request failed' }); }
    finally { setTesting(false); }
  };

  if (!data) return null;
  const provLabel = { openrouter: 'OpenRouter', openai: 'OpenAI', anthropic: 'Anthropic' };
  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={7}>
        <Card variant="outlined"><CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
            <Typography variant="subtitle1" fontWeight={700}>Provider health</Typography>
            <Chip size="small" label={data.configured ? 'Configured' : 'No key'} color={data.configured ? 'success' : 'warning'} variant="outlined" />
          </Stack>
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Rollup order: {data.chain.map((p) => provLabel[p] || p).join(' → ')}
          </Typography>
          <Stack direction="row" useFlexGap flexWrap="wrap" spacing={0.5} mb={1}>
            {Object.entries(data.providers).map(([key, p]) => (
              <Chip key={key} size="small" variant="outlined" color={p.key_set ? 'success' : 'default'}
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
      </Grid>
      <Grid item xs={12} md={5}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Token usage</Typography>
          {usage ? (
            <>
              <Typography variant="h6" fontWeight={800}>{(usage.input_tokens + usage.output_tokens).toLocaleString()}</Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                tokens over {usage.days}d · {usage.calls} calls
              </Typography>
              <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>
                in {usage.input_tokens.toLocaleString()} / out {usage.output_tokens.toLocaleString()}
              </Typography>
            </>
          ) : <Typography variant="body2" color="text.secondary">No AI usage recorded yet.</Typography>}
        </CardContent></Card>
      </Grid>
    </Grid>
  );
}

// ── Bot Health (bots/bothealth) ──────────────────────────────────────────────
function BotHealthSection() {
  const [data, setData] = useState(null);
  useEffect(() => { guildizerApi.get('/api/admin/fleet').then(({ data: d }) => setData(d)).catch(() => {}); }, []);
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
          Last event: {data.events[0].event} · {fmtDateTime(data.events[0].created_at)}
        </Typography>
      )}
    </CardContent></Card>
  );
}

// ── Feature Usage (analytics/feature-usage) ──────────────────────────────────
function FeatureUsageSection() {
  const [features, setFeatures] = useState(null);
  useEffect(() => { guildizerApi.get('/api/admin/feature-usage?days=14').then(({ data }) => setFeatures(data)).catch(() => {}); }, []);
  if (!features) return null;
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>
        Feature usage — {features.total} command runs / {features.days}d
      </Typography>
      <Stack direction="row" useFlexGap flexWrap="wrap" spacing={0.5}>
        {features.features.map((f) => (
          <Chip key={f.feature} size="small" variant="outlined" label={`/${f.feature} · ${f.count}`} />
        ))}
        {features.features.length === 0 && <Typography variant="body2" color="text.secondary">No usage yet.</Typography>}
      </Stack>
    </CardContent></Card>
  );
}

// ── AI Usage (analytics/ai-usage) ────────────────────────────────────────────
function AiUsageSection() {
  const [ai, setAi] = useState(null);
  useEffect(() => { guildizerApi.get('/api/admin/ai-usage?days=30').then(({ data }) => setAi(data)).catch(() => {}); }, []);
  if (!ai) return null;
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>AI usage — {ai.days}d</Typography>
      <Grid container spacing={1.5} mb={1}>
        <Grid item xs={4}><StatCard value={ai.calls} label="Calls" /></Grid>
        <Grid item xs={4}><StatCard value={ai.input_tokens.toLocaleString()} label="Input tokens" /></Grid>
        <Grid item xs={4}><StatCard value={ai.output_tokens.toLocaleString()} label="Output tokens" /></Grid>
      </Grid>
      <SectionTitle>Top servers by tokens</SectionTitle>
      <List dense>
        {ai.top_guilds.map((g) => (
          <ListItem key={g.guild_id} disableGutters
            secondaryAction={<Typography variant="caption">{g.tokens.toLocaleString()}</Typography>}>
            <ListItemText primary={g.guild_id} primaryTypographyProps={{ variant: 'body2' }} />
          </ListItem>
        ))}
        {ai.top_guilds.length === 0 && <Typography variant="body2" color="text.secondary">No AI usage recorded yet.</Typography>}
      </List>
    </CardContent></Card>
  );
}

// ── Roles & Access (access/roles) — super only ───────────────────────────────
function RolesSection() {
  const [data, setData] = useState(null);
  const [uid, setUid] = useState('');
  const [role, setRole] = useState('support');
  const load = () => guildizerApi.get('/api/admin/roles').then(({ data: d }) => setData(d)).catch(() => setData(null));
  useEffect(() => { load(); }, []);
  if (!data) return null;
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>Admin roles</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Env super admins: {data.env_super_ids.join(', ') || 'none'}.
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" mb={1}>
        <TextField size="small" label="Discord user ID" value={uid} onChange={(e) => setUid(e.target.value)} sx={{ flex: 1 }} />
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
            secondaryAction={<Button size="small" color="inherit"
              onClick={() => guildizerApi.delete(`/api/admin/roles/${r.user_id}`).then(load)}>Revoke</Button>}>
            <Chip size="small" variant="outlined" label={r.role} sx={{ mr: 1 }} />
            <ListItemText primary={r.username || r.user_id} />
          </ListItem>
        ))}
        {data.roles.length === 0 && <Typography variant="body2" color="text.secondary">No DB-granted roles.</Typography>}
      </List>
    </CardContent></Card>
  );
}

// ── Promo Codes (compliance/promo) ───────────────────────────────────────────
function PromoSection() {
  const [codes, setCodes] = useState([]);
  const [daysFree, setDaysFree] = useState(30);
  const [maxUses, setMaxUses] = useState(10);
  const load = () => guildizerApi.get('/api/admin/promo-codes').then(({ data }) => setCodes(data.codes)).catch(() => {});
  useEffect(() => { load(); }, []);
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>Promo codes</Typography>
      <Stack direction="row" spacing={1} alignItems="center" mb={1}>
        <TextField type="number" size="small" label="Days" value={daysFree} onChange={(e) => setDaysFree(Number(e.target.value))} sx={{ width: 90 }} />
        <TextField type="number" size="small" label="Max uses" value={maxUses} onChange={(e) => setMaxUses(Number(e.target.value))} sx={{ width: 100 }} />
        <Button size="small" variant="contained"
          onClick={() => guildizerApi.post('/api/admin/promo-codes', { days_free: daysFree, max_uses: maxUses }).then(load)}>
          Generate
        </Button>
      </Stack>
      <List dense>
        {codes.map((c) => (
          <ListItem key={c.id} disableGutters
            secondaryAction={c.enabled && (
              <Button size="small" color="inherit" onClick={() => guildizerApi.delete(`/api/admin/promo-codes/${c.id}`).then(load)}>Disable</Button>
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

// ── Audit Log (analytics/audit) ──────────────────────────────────────────────
function AuditSection() {
  const [entries, setEntries] = useState([]);
  useEffect(() => { guildizerApi.get('/api/admin/audit-log').then(({ data }) => setEntries(data.entries)).catch(() => {}); }, []);
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>Admin audit log</Typography>
      {entries.length === 0 && <Typography variant="body2" color="text.secondary">No admin actions recorded yet.</Typography>}
      <List dense>
        {entries.map((e) => (
          <ListItem key={e.id} disableGutters
            secondaryAction={<Typography variant="caption" color="text.disabled">{fmtDateTime(e.created_at)}</Typography>}>
            <Chip size="small" variant="outlined" label={e.action} sx={{ mr: 1 }} />
            <ListItemText primary={`${e.target || ''} ${e.detail ? '— ' + e.detail : ''}`} secondary={`by ${e.admin_id}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
      </List>
    </CardContent></Card>
  );
}

// ── Placeholder for sections built in later phases ───────────────────────────
function Placeholder({ label }) {
  return (
    <Card variant="outlined" sx={{ borderStyle: 'dashed' }}><CardContent sx={{ textAlign: 'center', py: 6 }}>
      <ConstructionRounded sx={{ fontSize: 40, color: 'text.disabled', mb: 1 }} />
      <Typography variant="subtitle1" fontWeight={700}>{label}</Typography>
      <Typography variant="body2" color="text.secondary">This section is part of the admin parity build and ships in an upcoming phase.</Typography>
    </CardContent></Card>
  );
}

const SECTION_COMPONENTS = {
  dashboard: DashboardSection,
  ai: AiManagementSection,
  bothealth: BotHealthSection,
  'feature-usage': FeatureUsageSection,
  'ai-usage': AiUsageSection,
  roles: RolesSection,
  promo: PromoSection,
  audit: AuditSection,
};

export default function GuildizerAdminPanel() {
  const { category, section } = useParams();
  const { can } = useGuildizerAdmin();

  const item = findGuildizerAdminItem(section);
  // Unknown / missing section → canonical default.
  if (!item) return <Navigate to={`/guildizer/admin/overview/${DEFAULT_GUILDIZER_ADMIN_KEY}`} replace />;
  // Category in URL doesn't match the item's real category → fix it.
  if (item.category !== category) return <Navigate to={`/guildizer/admin/${item.category}/${item.key}`} replace />;

  const cat = GUILDIZER_ADMIN_CATEGORIES.find((c) => c.slug === item.category);
  const Section = SECTION_COMPONENTS[item.key];

  return (
    <Box sx={PAGE_SX}>
      <Typography variant="caption" color="text.disabled" display="block" mb={0.5}>
        {cat?.label} <Box component="span" sx={{ mx: 0.5 }}>/</Box> {item.label}
      </Typography>
      <Typography variant="h5" fontWeight={800} mb={2.5}>{item.label}</Typography>

      {item.superOnly && !can(true)
        ? <Alert severity="warning">This section requires a super-admin role.</Alert>
        : Section ? <Section /> : <Placeholder label={item.label} />}
    </Box>
  );
}
