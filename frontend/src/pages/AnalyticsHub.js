import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Typography, Tabs, Tab, Card, CardContent, Grid,
  CircularProgress, Alert, Button, FormControl, InputLabel,
  Select, MenuItem, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Chip,
} from '@mui/material';
import {
  BarChart as BarChartIcon, Groups, Tv,
  PersonAdd, Shield, Bolt, OpenInNew, Psychology,
  CheckBox, LibraryBooks, Notes, Link, NotificationsActive,
} from '@mui/icons-material';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import {
  analytics as analyticsApi, telegramGroups as groupsApi, channels as chApi, auth,
  assistant as assistantApi, hub, notes as notesApi, workspaceKnowledge as knowledgeApi,
} from '../services/api';

const CHART_STYLE = { background: '#161b22', border: '1px solid #30363d' };

function StatCard({ icon, label, value, color = 'primary.main' }) {
  return (
    <Card variant="outlined">
      <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, py: '14px !important' }}>
        <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: `${color}22`, flexShrink: 0 }}>
          {React.cloneElement(icon, { sx: { color, fontSize: 20 } })}
        </Box>
        <Box>
          <Typography variant="h5" fontWeight={700} lineHeight={1.1}>{value ?? 0}</Typography>
          <Typography variant="body2" color="text.secondary" fontSize="0.8rem">{label}</Typography>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab({ isPro }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await analyticsApi.getOfficialOverview({ days });
      setData(d.analytics);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  const summary = data?.summary || {};
  const topGroups = data?.top_groups || [];
  const eventsByType = data?.events_by_type || {};
  const EVENT_LABELS = {
    member_joined: 'Joined', verification_passed: 'Verified',
    verification_failed: 'Failed', automod_action: 'AutoMod',
    command_triggered: 'Commands',
  };
  const eventBarData = Object.entries(eventsByType)
    .map(([type, count]) => ({ type: EVENT_LABELS[type] || type, count }))
    .sort((a, b) => b.count - a.count).slice(0, 8);

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: { xs: 90, sm: 110 } }}>
          <InputLabel>Range</InputLabel>
          <Select value={days} label="Range" onChange={e => setDays(e.target.value)}>
            <MenuItem value={7}>7 days</MenuItem>
            <MenuItem value={14}>14 days</MenuItem>
            <MenuItem value={30}>30 days</MenuItem>
            {isPro && <MenuItem value={90}>90 days</MenuItem>}
          </Select>
        </FormControl>
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={32} /></Box>
      ) : !data ? (
        <Alert severity="info">No analytics data yet. Connect groups to the bot first.</Alert>
      ) : (
        <>
          <Grid container spacing={2} mb={3}>
            <Grid item xs={6} md={3}>
              <StatCard icon={<Groups />} label="Linked Groups" value={data.total_groups} color="#2196f3" />
            </Grid>
            <Grid item xs={6} md={3}>
              <StatCard icon={<PersonAdd />} label="Members Joined" value={summary.member_joins} color="#4caf50" />
            </Grid>
            <Grid item xs={6} md={3}>
              <StatCard icon={<Shield />} label="AutoMod Actions" value={summary.automod_actions} color="#f44336" />
            </Grid>
            <Grid item xs={6} md={3}>
              <StatCard icon={<Bolt />} label="Commands Used" value={summary.commands_used} color="#7c4dff" />
            </Grid>
          </Grid>

          <Grid container spacing={2}>
            <Grid item xs={12} md={7}>
              <Card variant="outlined">
                <CardContent>
                  <Typography fontWeight={600} mb={2}>Events by Type</Typography>
                  {!isPro ? (
                    <Box sx={{ textAlign: 'center', py: 4 }}>
                      <Typography color="text.secondary" fontSize="0.84rem" mb={1}>Events breakdown available on Pro.</Typography>
                      <Button variant="outlined" size="small" onClick={() => navigate('/billing')}>Upgrade</Button>
                    </Box>
                  ) : eventBarData.length === 0 ? (
                    <Typography color="text.secondary" fontSize="0.84rem">No events in this period.</Typography>
                  ) : (
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={eventBarData} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" stroke="#30363d" horizontal={false} />
                        <XAxis type="number" tick={{ fontSize: 11, fill: '#8b949e' }} allowDecimals={false} />
                        <YAxis type="category" dataKey="type" tick={{ fontSize: 11, fill: '#8b949e' }} width={110} />
                        <Tooltip contentStyle={CHART_STYLE} />
                        <Bar dataKey="count" fill="#2196f3" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={5}>
              <Card variant="outlined" sx={{ height: '100%' }}>
                <CardContent>
                  <Typography fontWeight={600} mb={2}>Most Active Groups</Typography>
                  {topGroups.length === 0 ? (
                    <Typography color="text.secondary" fontSize="0.84rem">No activity yet.</Typography>
                  ) : (
                    <TableContainer sx={{ overflowX: 'auto' }}>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Group</TableCell>
                            <TableCell align="right">Events</TableCell>
                            <TableCell />
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {topGroups.map(g => (
                            <TableRow key={g.group_id} hover>
                              <TableCell>
                                <Typography fontSize="0.82rem" noWrap sx={{ maxWidth: 140 }}>{g.title || g.group_id}</Typography>
                              </TableCell>
                              <TableCell align="right">
                                <Typography fontSize="0.82rem" fontWeight={600}>{g.events}</Typography>
                              </TableCell>
                              <TableCell>
                                <Button size="small" sx={{ fontSize: '0.7rem', px: 0.5 }}
                                  onClick={() => navigate(`/groups/${g.group_id}/analytics`)}>
                                  View
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </>
      )}
    </Box>
  );
}

// ── Groups Tab ────────────────────────────────────────────────────────────────

function GroupsTab() {
  const navigate = useNavigate();
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    groupsApi.list().then(({ data }) => setGroups(data.groups || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={32} /></Box>;

  if (groups.length === 0) {
    return (
      <Alert severity="info" action={<Button onClick={() => navigate('/groups')} size="small">My Groups</Button>}>
        No groups connected. Add the bot to a Telegram group first.
      </Alert>
    );
  }

  return (
    <Grid container spacing={2}>
      {groups.map(g => (
        <Grid item xs={12} sm={6} md={4} key={g.id}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                <Typography fontWeight={600} fontSize="0.92rem" sx={{ flex: 1, mr: 1 }} noWrap>
                  {g.title || g.telegram_group_id}
                </Typography>
                <Chip
                  label={g.bot_status || 'unknown'}
                  size="small"
                  color={g.bot_status === 'active' ? 'success' : 'default'}
                  sx={{ fontSize: '0.65rem', height: 18 }}
                />
              </Box>
              <Typography fontSize="0.78rem" color="text.secondary" mb={1.5}>
                {g.member_count ? `${g.member_count.toLocaleString()} members` : 'Members unknown'}
              </Typography>
              <Button
                size="small"
                variant="outlined"
                endIcon={<OpenInNew sx={{ fontSize: 13 }} />}
                onClick={() => navigate(`/groups/${g.telegram_group_id}/analytics`)}
                fullWidth
              >
                View Analytics
              </Button>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}

// ── Channels Tab ──────────────────────────────────────────────────────────────

function ChannelsTab() {
  const navigate = useNavigate();
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    chApi.list().then(({ data }) => setChannels(data.channels || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={32} /></Box>;

  if (channels.length === 0) {
    return (
      <Alert severity="info" action={<Button onClick={() => navigate('/channels')} size="small">My Channels</Button>}>
        No channels connected yet.
      </Alert>
    );
  }

  return (
    <Grid container spacing={2}>
      {channels.map(ch => (
        <Grid item xs={12} sm={6} md={4} key={ch.id}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Tv fontSize="small" color="primary" />
                <Typography fontWeight={600} fontSize="0.92rem" noWrap sx={{ flex: 1 }}>
                  {ch.title || ch.telegram_channel_id}
                </Typography>
              </Box>
              <Typography fontSize="0.78rem" color="text.secondary" mb={1.5}>
                {ch.subscriber_count ? `${ch.subscriber_count.toLocaleString()} subscribers` : 'Subscribers unknown'}
              </Typography>
              <Button
                size="small"
                variant="outlined"
                endIcon={<OpenInNew sx={{ fontSize: 13 }} />}
                onClick={() => navigate(`/channels/${ch.id}`)}
                fullWidth
              >
                View Analytics
              </Button>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}

// ── Assistant Tab ──────────────────────────────────────────────────────────────

function AssistantTab() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    const sevenDaysAgo = new Date(Date.now() - 7 * 86400000);
    Promise.all([
      hub.listTasks().catch(() => ({ data: { tasks: [] } })),
      notesApi.list().catch(() => ({ data: { notes: [] } })),
      knowledgeApi.list().catch(() => ({ data: { documents: [] } })),
      assistantApi.getAutoReplyLogs().catch(() => ({ data: { logs: [] } })),
      hub.listReminders().catch(() => ({ data: { reminders: [] } })),
    ]).then(([tRes, nRes, kRes, aRes, rRes]) => {
      const tasks = tRes.data.tasks || [];
      const notes = nRes.data.notes || [];
      const docs = kRes.data.documents || [];
      const logs = aRes.data.logs || [];
      const reminders = rRes.data.reminders || [];
      const recentTriggers = logs.filter(l => new Date(l.triggered_at) >= sevenDaysAgo).length;
      setStats({
        tasks: { total: tasks.length, done: tasks.filter(t => t.status === 'done').length },
        notes: { total: notes.length, ai: notes.filter(n => n.source === 'ai').length },
        docs: docs.length,
        triggers7d: recentTriggers,
        reminders: { total: reminders.length },
      });
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={32} /></Box>;
  if (!stats) return null;

  const items = [
    { icon: <CheckBox />, label: 'Total Tasks', value: stats.tasks.total, sub: `${stats.tasks.done} done`, path: '/workspace/tasks', color: 'primary.main' },
    { icon: <Notes />, label: 'Notes', value: stats.notes.total, sub: `${stats.notes.ai} AI-generated`, path: '/workspace/notes', color: 'success.main' },
    { icon: <LibraryBooks />, label: 'Knowledge Docs', value: stats.docs, sub: null, path: '/workspace/knowledge', color: 'warning.main' },
    { icon: <Link />, label: 'Auto-Reply Triggers (7d)', value: stats.triggers7d, sub: null, path: '/workspace/smart-links', color: 'secondary.main' },
    { icon: <NotificationsActive />, label: 'Reminders', value: stats.reminders.total, sub: null, path: '/workspace/reminders', color: 'error.main' },
  ];

  return (
    <Box>
      <Typography fontSize="0.85rem" color="text.secondary" mb={2.5}>
        Summary of your Echo Assistant activity across tasks, notes, knowledge, and automation.
      </Typography>
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {items.map(item => (
          <Grid item xs={12} sm={6} md={4} key={item.label}>
            <Card variant="outlined" sx={{ cursor: 'pointer', '&:hover': { borderColor: 'primary.main' } }}
              onClick={() => navigate(item.path)}>
              <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, py: '14px !important' }}>
                <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: `${item.color}22`, flexShrink: 0 }}>
                  {React.cloneElement(item.icon, { sx: { color: item.color, fontSize: 20 } })}
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="h5" fontWeight={700} lineHeight={1.1}>{item.value}</Typography>
                  <Typography variant="body2" color="text.secondary" fontSize="0.8rem">{item.label}</Typography>
                  {item.sub && <Typography variant="caption" color="text.disabled">{item.sub}</Typography>}
                </Box>
                <OpenInNew sx={{ fontSize: 14, color: 'text.disabled' }} />
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
      <Alert severity="info" icon={<Psychology />}
        action={<Button size="small" onClick={() => navigate('/ark')}>Go to Echo</Button>}>
        Detailed per-group extraction stats are in the Echo workspace.
      </Alert>
    </Box>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

const TAB_MAP = { groups: 1, channels: 2, assistant: 3 };

export default function AnalyticsHub() {
  const [searchParams] = useSearchParams();
  const initialTab = TAB_MAP[searchParams.get('tab')] ?? 0;
  const [tab, setTab] = useState(initialTab);
  const [isPro, setIsPro] = useState(false);

  useEffect(() => {
    const t = TAB_MAP[searchParams.get('tab')] ?? 0;
    setTab(t);
  }, [searchParams]);

  useEffect(() => {
    auth.getMe().then(({ data }) => {
      const tier = data.user?.subscription_tier || 'free';
      setIsPro(tier === 'pro' || tier === 'enterprise');
    }).catch(() => {});
  }, []);

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 900, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <BarChartIcon sx={{ fontSize: 26, color: 'primary.main' }} />
        <Typography variant="h5" fontWeight={700}>Analytics</Typography>
      </Box>
      <Typography color="text.secondary" fontSize="0.88rem" mb={2.5}>
        Activity across all your groups and channels
      </Typography>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}>
        <Tab label="Overview" />
        <Tab label="Groups" />
        <Tab label="Channels" />
        <Tab label="Assistant" icon={<Psychology sx={{ fontSize: 15 }} />} iconPosition="start"
          sx={{ textTransform: 'none', minHeight: 40 }} />
      </Tabs>

      {tab === 0 && <OverviewTab isPro={isPro} />}
      {tab === 1 && <GroupsTab />}
      {tab === 2 && <ChannelsTab />}
      {tab === 3 && <AssistantTab />}
    </Box>
  );
}
