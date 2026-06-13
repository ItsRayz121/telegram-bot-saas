import React, { useEffect, useState } from 'react';
import { useParams, Navigate, useNavigate } from 'react-router-dom';
import {
  Box, Grid, Card, CardContent, Typography, Button, Chip, Stack, Alert,
  Table, TableHead, TableBody, TableRow, TableCell, TextField, List, ListItem, ListItemText,
  LinearProgress, ToggleButtonGroup, ToggleButton,
} from '@mui/material';
import {
  Groups, SmartToy, WorkspacePremium, People, Campaign, Verified,
  Shield, Bolt, ConstructionRounded, AttachMoney, Flag,
} from '@mui/icons-material';
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip as ReTooltip, Legend,
} from 'recharts';
import guildizerApi from '../../../services/guildizerApi';
import {
  StatCard, SectionTitle, EmptyRow, StatusChip, fmtDateTime, fmtDate, usd,
} from '../../../components/guildizer/GuildizerAdminKit';
import {
  GUILDIZER_ADMIN_CATEGORIES, findGuildizerAdminItem, DEFAULT_GUILDIZER_ADMIN_KEY,
  guildizerAdminPath,
} from '../../../config/guildizerAdminNav';
import { useGuildizerAdmin } from '../../../contexts/GuildizerAdminContext';
import { PALETTE } from '../../../theme';

const PAGE_SX = { maxWidth: 1400, mx: 'auto', px: { xs: 2, md: 3 }, py: 2.5 };

// ── Overview / Dashboard ─────────────────────────────────────────────────────
// `to` = drill-down section key (canonical path resolved via guildizerAdminPath).
const STAT_TILES = [
  { key: 'guilds_total', label: 'Servers', icon: Groups, color: PALETTE.blue, to: 'servers' },
  { key: 'guilds_with_bot', label: 'Bot installed', icon: SmartToy, color: PALETTE.cyan, to: 'servers' },
  { key: 'guilds_pro', label: 'Pro servers', icon: WorkspacePremium, color: PALETTE.green, to: 'servers' },
  { key: 'users_total', label: 'Users', icon: People, color: PALETTE.purple, to: 'users' },
  { key: 'members_total', label: 'Members', icon: People, color: PALETTE.blue, to: 'users' },
  { key: 'campaigns_active', label: 'Active campaigns', icon: Campaign, color: PALETTE.amber, to: 'campaigns' },
  { key: 'submissions_verified', label: 'Verified proofs', icon: Verified, color: PALETTE.green, to: 'proof' },
  { key: 'protection_events_total', label: 'Protection events', icon: Shield, color: PALETTE.red, to: 'event-log' },
  { key: 'subscriptions_active', label: 'Active subs', icon: WorkspacePremium, color: PALETTE.green },
  { key: 'xp_events_total', label: 'XP grants', icon: Bolt, color: PALETTE.cyan },
];

const REVENUE_TILES = [
  { key: 'mrr', label: 'MRR', color: PALETTE.green, money: true },
  { key: 'arr', label: 'ARR', color: PALETTE.green, money: true },
  { key: 'this_month', label: 'This month', color: PALETTE.blue, money: true },
  { key: 'last_month', label: 'Last month', color: PALETTE.purple, money: true },
  { key: 'total_all_time', label: 'All time', color: PALETTE.cyan, money: true },
  { key: 'active_count', label: 'Active subs', color: PALETTE.amber },
];

function ChartCard({ title, action, children, height = 240 }) {
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
          <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
          {action}
        </Stack>
        <Box sx={{ height }}>{children}</Box>
      </CardContent>
    </Card>
  );
}

function ChartEmpty({ label }) {
  return (
    <Box sx={{ height: '100%', display: 'grid', placeItems: 'center' }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
    </Box>
  );
}

function DashboardSection() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState(null);
  const [guilds, setGuilds] = useState([]);
  const [events, setEvents] = useState([]);
  const [revenue, setRevenue] = useState(null);
  const [growth, setGrowth] = useState(null);
  const [growthDays, setGrowthDays] = useState(30);
  const [days, setDays] = useState(30);

  const loadGuilds = () => guildizerApi.get('/api/admin/guilds').then(({ data }) => setGuilds(data.guilds)).catch(() => {});
  useEffect(() => {
    guildizerApi.get('/api/admin/overview').then(({ data }) => setOverview(data)).catch(() => {});
    guildizerApi.get('/api/admin/events?limit=30').then(({ data }) => setEvents(data.events)).catch(() => {});
    guildizerApi.get('/api/admin/revenue').then(({ data }) => setRevenue(data)).catch(() => {});
    loadGuilds();
  }, []);

  useEffect(() => {
    guildizerApi.get(`/api/admin/growth?days=${growthDays}`).then(({ data }) => setGrowth(data)).catch(() => {});
  }, [growthDays]);

  const setPlan = (guildId, plan) =>
    guildizerApi.post(`/api/admin/guilds/${guildId}/plan`, { plan, days }).then(loadGuilds).catch(() => {});

  const go = (key) => key && navigate(guildizerAdminPath(key));

  return (
    <>
      <Grid container spacing={1.5} mb={3}>
        {STAT_TILES.map((t) => (
          <Grid item xs={6} sm={4} md={2.4} key={t.key}>
            <StatCard value={overview?.[t.key] ?? 0} label={t.label} icon={t.icon} color={t.color}
              onClick={t.to ? () => go(t.to) : undefined} />
          </Grid>
        ))}
      </Grid>

      {/* Revenue */}
      <SectionTitle sx={{ mt: 0 }}>Revenue</SectionTitle>
      <Grid container spacing={1.5} mb={3}>
        {REVENUE_TILES.map((t) => (
          <Grid item xs={6} sm={4} md={2} key={t.key}>
            <StatCard
              value={revenue ? (t.money ? usd(revenue[t.key]) : revenue[t.key] ?? 0) : '…'}
              label={t.label} color={t.color} icon={t.money ? AttachMoney : WorkspacePremium} />
          </Grid>
        ))}
      </Grid>

      {/* Charts */}
      <Grid container spacing={2} mb={3}>
        <Grid item xs={12} md={5}>
          <ChartCard title="Monthly revenue" height={240}>
            {revenue?.monthly_trend?.some((m) => m.revenue > 0) ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={revenue.monthly_trend} margin={{ top: 6, right: 12, bottom: 0, left: -16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke="rgba(255,255,255,0.4)" />
                  <YAxis tick={{ fontSize: 11 }} stroke="rgba(255,255,255,0.4)" />
                  <ReTooltip formatter={(v) => [usd(v), 'Revenue']}
                    contentStyle={{ background: '#1a1d29', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }} />
                  <Line type="monotone" dataKey="revenue" stroke={PALETTE.green} strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : <ChartEmpty label="No revenue recorded yet." />}
          </ChartCard>
        </Grid>
        <Grid item xs={12} md={7}>
          <ChartCard title="Activity growth" height={240}
            action={
              <ToggleButtonGroup size="small" exclusive value={growthDays}
                onChange={(_, v) => v && setGrowthDays(v)}>
                {[7, 30, 90].map((d) => <ToggleButton key={d} value={d} sx={{ px: 1.25, py: 0.25 }}>{d}d</ToggleButton>)}
              </ToggleButtonGroup>
            }>
            {growth?.series?.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={growth.series} margin={{ top: 6, right: 12, bottom: 0, left: -16 }}>
                  <defs>
                    <linearGradient id="gzMsg" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={PALETTE.blue} stopOpacity={0.5} />
                      <stop offset="95%" stopColor={PALETTE.blue} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="day" tick={{ fontSize: 10 }} stroke="rgba(255,255,255,0.4)"
                    tickFormatter={(d) => d.slice(5)} />
                  <YAxis tick={{ fontSize: 11 }} stroke="rgba(255,255,255,0.4)" />
                  <ReTooltip contentStyle={{ background: '#1a1d29', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Area type="monotone" dataKey="messages" stroke={PALETTE.blue} fill="url(#gzMsg)" strokeWidth={2} />
                  <Area type="monotone" dataKey="joins" stroke={PALETTE.green} fillOpacity={0} strokeWidth={2} />
                  <Area type="monotone" dataKey="leaves" stroke={PALETTE.red} fillOpacity={0} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : <ChartEmpty label="No activity recorded yet." />}
          </ChartCard>
        </Grid>
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

// ── Overview / Proof Metrics (overview/proof) ────────────────────────────────
function ProofMetricsSection() {
  const [pm, setPm] = useState(null);
  useEffect(() => { guildizerApi.get('/api/admin/proof-metrics?days=30').then(({ data }) => setPm(data)).catch(() => {}); }, []);
  if (!pm) return null;
  const reviewed = pm.verified + pm.rejected;
  return (
    <>
      <Grid container spacing={1.5} mb={3}>
        <Grid item xs={6} sm={4} md={2}><StatCard value={pm.total} label="Submissions" icon={Verified} color={PALETTE.blue} /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard value={pm.verified} label="Verified" icon={Verified} color={PALETTE.green} /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard value={pm.pending} label="Pending" color={PALETTE.amber} /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard value={pm.rejected} label="Rejected" color={PALETTE.red} /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard value={`${pm.approval_rate}%`} label="Approval rate" color={PALETTE.cyan} /></Grid>
        <Grid item xs={6} sm={4} md={2}><StatCard value={pm.rewards_granted.toLocaleString()} label="Rewards granted" icon={Bolt} color={PALETTE.purple} /></Grid>
      </Grid>

      <Card variant="outlined" sx={{ mb: 3 }}><CardContent>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Review funnel · last {pm.days}d ({pm.submissions_window} new)</Typography>
        {reviewed === 0
          ? <Typography variant="body2" color="text.secondary">No reviewed submissions yet.</Typography>
          : (
            <>
              <LinearProgress variant="determinate" value={pm.approval_rate}
                sx={{ height: 8, borderRadius: 4, mb: 1, '& .MuiLinearProgress-bar': { bgcolor: PALETTE.green } }} />
              <Typography variant="caption" color="text.secondary">
                {pm.verified} verified / {reviewed} reviewed
              </Typography>
            </>
          )}
      </CardContent></Card>

      <Card variant="outlined"><CardContent>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Recent submissions</Typography>
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>User</TableCell><TableCell>Campaign</TableCell><TableCell>Status</TableCell>
            <TableCell align="right">Reward</TableCell><TableCell align="right">When</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {pm.recent.length === 0 && <EmptyRow colSpan={5} label="No submissions yet." />}
            {pm.recent.map((s) => (
              <TableRow key={s.id} hover>
                <TableCell>{s.username || s.user_id}</TableCell>
                <TableCell>#{s.campaign_id}</TableCell>
                <TableCell><StatusChip label={s.status} /></TableCell>
                <TableCell align="right">{s.reward_granted || 0}</TableCell>
                <TableCell align="right"><Typography variant="caption" color="text.disabled">{fmtDateTime(s.created_at)}</Typography></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent></Card>
    </>
  );
}

// ── Overview / Reports (overview/reports) ────────────────────────────────────
function ReportsSection() {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState('');
  const load = (status) => {
    const qs = status ? `?status=${status}` : '';
    guildizerApi.get(`/api/admin/reports${qs}`).then(({ data: d }) => setData(d)).catch(() => {});
  };
  useEffect(() => { load(filter); }, [filter]);
  if (!data) return null;
  const c = data.counts;
  return (
    <>
      <Grid container spacing={1.5} mb={3}>
        <Grid item xs={6} sm={3}><StatCard value={c.total} label="Total reports" icon={Flag} color={PALETTE.blue} /></Grid>
        <Grid item xs={6} sm={3}><StatCard value={c.open} label="Open" color={PALETTE.amber} /></Grid>
        <Grid item xs={6} sm={3}><StatCard value={c.actioned} label="Actioned" color={PALETTE.green} /></Grid>
        <Grid item xs={6} sm={3}><StatCard value={c.dismissed} label="Dismissed" color={PALETTE.red} /></Grid>
      </Grid>

      <Card variant="outlined"><CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
          <Typography variant="subtitle1" fontWeight={700}>Report queue</Typography>
          <ToggleButtonGroup size="small" exclusive value={filter} onChange={(_, v) => setFilter(v ?? '')}>
            <ToggleButton value="" sx={{ px: 1.25, py: 0.25 }}>All</ToggleButton>
            <ToggleButton value="open" sx={{ px: 1.25, py: 0.25 }}>Open</ToggleButton>
            <ToggleButton value="actioned" sx={{ px: 1.25, py: 0.25 }}>Actioned</ToggleButton>
            <ToggleButton value="dismissed" sx={{ px: 1.25, py: 0.25 }}>Dismissed</ToggleButton>
          </ToggleButtonGroup>
        </Stack>
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Reporter</TableCell><TableCell>Target</TableCell><TableCell>Reason</TableCell>
            <TableCell>Status</TableCell><TableCell align="right">When</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {data.reports.length === 0 && <EmptyRow colSpan={5} label="No reports." />}
            {data.reports.map((r) => (
              <TableRow key={r.id} hover>
                <TableCell>{r.reporter_name || r.reporter_id}</TableCell>
                <TableCell>{r.target_name || r.target_id || '—'}</TableCell>
                <TableCell sx={{ maxWidth: 280 }}>
                  <Typography variant="body2" noWrap title={r.reason || ''}>{r.reason || '—'}</Typography>
                </TableCell>
                <TableCell><StatusChip label={r.status} /></TableCell>
                <TableCell align="right"><Typography variant="caption" color="text.disabled">{fmtDate(r.created_at)}</Typography></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent></Card>
    </>
  );
}

// ── Users & Access / Users (access/users) ───────────────────────────────────
function UsersSection() {
  const navigate = useNavigate();
  const [users, setUsers] = useState(null);
  const [q, setQ] = useState('');
  useEffect(() => { guildizerApi.get('/api/admin/users').then(({ data }) => setUsers(data.users)).catch(() => {}); }, []);
  if (!users) return null;
  const needle = q.trim().toLowerCase();
  const rows = needle
    ? users.filter((u) => (u.username || '').toLowerCase().includes(needle)
        || (u.global_name || '').toLowerCase().includes(needle) || String(u.id).includes(needle))
    : users;
  return (
    <Card variant="outlined"><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
        <Typography variant="subtitle1" fontWeight={700}>Users ({rows.length})</Typography>
        <TextField size="small" placeholder="Search name or ID…" value={q}
          onChange={(e) => setQ(e.target.value)} sx={{ width: 240 }} />
      </Stack>
      <Table size="small">
        <TableHead><TableRow>
          <TableCell>User</TableCell><TableCell>Discord ID</TableCell>
          <TableCell align="right">Servers</TableCell><TableCell align="right">Last login</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {rows.length === 0 && <EmptyRow colSpan={4} label="No users." />}
          {rows.map((u) => (
            <TableRow key={u.id} hover sx={{ cursor: 'pointer' }}
              onClick={() => navigate(`/guildizer/admin/access/users/${u.id}`)}>
              <TableCell>{u.global_name || u.username || u.id}</TableCell>
              <TableCell sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>{u.id}</TableCell>
              <TableCell align="right">{u.memberships}</TableCell>
              <TableCell align="right"><Typography variant="caption" color="text.disabled">{fmtDate(u.last_login_at)}</Typography></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </CardContent></Card>
  );
}

// ── Users & Access / Referrals (access/referrals) ────────────────────────────
function ReferralsSection() {
  const [data, setData] = useState(null);
  useEffect(() => { guildizerApi.get('/api/admin/referrals?days=30').then(({ data: d }) => setData(d)).catch(() => {}); }, []);
  if (!data) return null;
  return (
    <>
      <Grid container spacing={1.5} mb={3}>
        <Grid item xs={6} sm={4}><StatCard value={data.links_total} label="Invite links" color={PALETTE.blue} /></Grid>
        <Grid item xs={6} sm={4}><StatCard value={data.joins_total} label="Attributed joins" color={PALETTE.green} /></Grid>
        <Grid item xs={6} sm={4}><StatCard value={data.joins_window} label={`Joins · ${data.window_days}d`} color={PALETTE.cyan} /></Grid>
      </Grid>

      <Card variant="outlined" sx={{ mb: 3 }}><CardContent>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Top inviters</Typography>
        <List dense>
          {data.top_inviters.length === 0 && <Typography variant="body2" color="text.secondary">No referrals yet.</Typography>}
          {data.top_inviters.map((i) => (
            <ListItem key={i.inviter_id} disableGutters
              secondaryAction={<Chip size="small" variant="outlined" label={`${i.joins} joins`} />}>
              <ListItemText primary={i.inviter_name || i.inviter_id}
                primaryTypographyProps={{ variant: 'body2' }} />
            </ListItem>
          ))}
        </List>
      </CardContent></Card>

      <Card variant="outlined"><CardContent>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Recent attributed joins</Typography>
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Joiner</TableCell><TableCell>Inviter</TableCell><TableCell>Code</TableCell>
            <TableCell align="right">When</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {data.recent.length === 0 && <EmptyRow colSpan={4} label="No joins yet." />}
            {data.recent.map((j) => (
              <TableRow key={j.id} hover>
                <TableCell>{j.joiner_name || j.joiner_id}</TableCell>
                <TableCell>{j.inviter_name || j.inviter_id || '—'}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace' }}>{j.code || '—'}</TableCell>
                <TableCell align="right"><Typography variant="caption" color="text.disabled">{fmtDateTime(j.created_at)}</Typography></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent></Card>
    </>
  );
}

// ── Users & Access / Suspicious (access/suspicious) ──────────────────────────
function SuspiciousSection() {
  const [data, setData] = useState(null);
  useEffect(() => { guildizerApi.get('/api/admin/suspicious?days=14').then(({ data: d }) => setData(d)).catch(() => {}); }, []);
  if (!data) return null;
  return (
    <>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
        <Typography variant="subtitle1" fontWeight={700}>
          {data.total} suspicious events · last {data.window_days}d
        </Typography>
      </Stack>
      <Stack direction="row" useFlexGap flexWrap="wrap" spacing={0.5} mb={3}>
        {Object.entries(data.by_category).map(([cat, n]) => (
          <Chip key={cat} size="small" variant="outlined" label={`${cat} · ${n}`} />
        ))}
        {data.total === 0 && <Typography variant="body2" color="text.secondary">No suspicious activity. 🎉</Typography>}
      </Stack>

      <Card variant="outlined" sx={{ mb: 3 }}><CardContent>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Top offenders</Typography>
        <List dense>
          {data.top_offenders.length === 0 && <Typography variant="body2" color="text.secondary">None.</Typography>}
          {data.top_offenders.map((o) => (
            <ListItem key={o.user_id} disableGutters
              secondaryAction={<Chip size="small" color="error" variant="outlined" label={`${o.events} events`} />}>
              <Shield sx={{ fontSize: 16, mr: 1, color: 'text.disabled' }} />
              <ListItemText primary={o.username || o.user_id} primaryTypographyProps={{ variant: 'body2' }} />
            </ListItem>
          ))}
        </List>
      </CardContent></Card>

      <Card variant="outlined"><CardContent>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Recent events</Typography>
        <List dense>
          {data.recent.length === 0 && <Typography variant="body2" color="text.secondary">No events.</Typography>}
          {data.recent.map((e) => (
            <ListItem key={e.id} disableGutters
              secondaryAction={<Typography variant="caption" color="text.disabled">{fmtDateTime(e.created_at)}</Typography>}>
              <Chip size="small" variant="outlined" color="warning" label={e.category} sx={{ mr: 1 }} />
              <ListItemText primary={`${e.action || '—'} — ${e.username ? e.username + ' · ' : ''}${e.detail || ''}`}
                primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
            </ListItem>
          ))}
        </List>
      </CardContent></Card>
    </>
  );
}

// ── Bots & Servers / Servers (bots/servers) ─────────────────────────────────
function ServersSection() {
  const navigate = useNavigate();
  const [guilds, setGuilds] = useState(null);
  const [q, setQ] = useState('');
  useEffect(() => { guildizerApi.get('/api/admin/guilds').then(({ data }) => setGuilds(data.guilds)).catch(() => {}); }, []);
  if (!guilds) return null;
  const needle = q.trim().toLowerCase();
  const rows = needle ? guilds.filter((g2) => (g2.name || '').toLowerCase().includes(needle) || String(g2.id).includes(needle)) : guilds;
  return (
    <Card variant="outlined"><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
        <Typography variant="subtitle1" fontWeight={700}>Servers ({rows.length})</Typography>
        <TextField size="small" placeholder="Search name or ID…" value={q}
          onChange={(e) => setQ(e.target.value)} sx={{ width: 240 }} />
      </Stack>
      <Table size="small">
        <TableHead><TableRow>
          <TableCell>Name</TableCell><TableCell align="right">Members</TableCell>
          <TableCell>Plan</TableCell><TableCell>Bot</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {rows.length === 0 && <EmptyRow colSpan={4} label="No servers." />}
          {rows.map((g2) => (
            <TableRow key={g2.id} hover sx={{ cursor: 'pointer' }}
              onClick={() => navigate(`/guildizer/admin/bots/servers/${g2.id}`)}>
              <TableCell>{g2.name || g2.id}</TableCell>
              <TableCell align="right">{g2.member_count}</TableCell>
              <TableCell><Chip size="small" variant="outlined" label={g2.plan} color={g2.is_pro ? 'success' : 'default'} /></TableCell>
              <TableCell>{g2.bot_present ? '✓' : '—'}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </CardContent></Card>
  );
}

// ── Bots & Servers / Custom Bots (bots/bots) ─────────────────────────────────
function CustomBotsSection() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  useEffect(() => { guildizerApi.get('/api/admin/fleet').then(({ data: d }) => setData(d)).catch(() => {}); }, []);
  if (!data) return null;
  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>White-label fleet ({data.bots.length})</Typography>
      <Table size="small">
        <TableHead><TableRow>
          <TableCell>Bot</TableCell><TableCell align="right">Servers</TableCell>
          <TableCell>Intents</TableCell><TableCell>Status</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {data.bots.length === 0 && <EmptyRow colSpan={4} label="No custom bots connected." />}
          {data.bots.map((b) => (
            <TableRow key={b.id} hover sx={{ cursor: 'pointer' }}
              onClick={() => navigate(`/guildizer/admin/bots/bot/${b.id}`)}>
              <TableCell>@{b.bot_username}</TableCell>
              <TableCell align="right">{b.linked_guild_count}</TableCell>
              <TableCell>{b.intents_ok ? '✓' : '⚠'}</TableCell>
              <TableCell><StatusChip label={b.status} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </CardContent></Card>
  );
}

// ── Bots & Servers / Diagnostics (bots/diagnostics) ──────────────────────────
function DiagnosticsSection() {
  const [d, setD] = useState(null);
  useEffect(() => { guildizerApi.get('/api/admin/diagnostics').then(({ data }) => setD(data)).catch(() => {}); }, []);
  if (!d) return null;
  const bs = d.custom_bots_by_status || {};
  return (
    <>
      <Grid container spacing={1.5} mb={3}>
        <Grid item xs={6} sm={3}><StatCard value={d.guilds_with_bot} label="Servers with bot" icon={SmartToy} color={PALETTE.green} /></Grid>
        <Grid item xs={6} sm={3}><StatCard value={d.guilds_without_bot} label="Awaiting bot" color={PALETTE.amber} /></Grid>
        <Grid item xs={6} sm={3}><StatCard value={d.custom_bots_total} label="Custom bots" icon={SmartToy} color={PALETTE.blue} /></Grid>
        <Grid item xs={6} sm={3}><StatCard value={d.intents_issues} label="Intent issues" icon={Shield} color={d.intents_issues ? PALETTE.red : PALETTE.green} /></Grid>
      </Grid>

      <Card variant="outlined" sx={{ mb: 3 }}><CardContent>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Fleet status</Typography>
        <Stack direction="row" useFlexGap flexWrap="wrap" spacing={0.5}>
          <Chip size="small" variant="outlined" color="success" label={`active · ${bs.active || 0}`} />
          <Chip size="small" variant="outlined" label={`disabled · ${bs.disabled || 0}`} />
          <Chip size="small" variant="outlined" color="error" label={`error · ${bs.error || 0}`} />
        </Stack>
      </CardContent></Card>

      <Card variant="outlined"><CardContent>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Recent connection errors (7d)</Typography>
        {d.recent_errors.length === 0
          ? <Typography variant="body2" color="text.secondary">No connection errors. 🎉</Typography>
          : (
            <List dense>
              {d.recent_errors.map((e) => (
                <ListItem key={e.id} disableGutters
                  secondaryAction={<Typography variant="caption" color="text.disabled">{fmtDateTime(e.created_at)}</Typography>}>
                  <Chip size="small" variant="outlined" color="error" label={e.event} sx={{ mr: 1 }} />
                  <ListItemText primary={e.detail || '—'} primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
                </ListItem>
              ))}
            </List>
          )}
      </CardContent></Card>
    </>
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
  proof: ProofMetricsSection,
  reports: ReportsSection,
  users: UsersSection,
  referrals: ReferralsSection,
  suspicious: SuspiciousSection,
  servers: ServersSection,
  bots: CustomBotsSection,
  diagnostics: DiagnosticsSection,
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
