/**
 * /hub/official/:tab — Official bot workspace.
 * Sprint 4: Overview, Tasks, Reminders, Notes tabs are fully live.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Box, Tabs, Tab, Typography, Chip, Button, CircularProgress,
  Card, CardContent, Switch, FormControlLabel, Divider, Select, MenuItem,
  FormControl, InputLabel, FormHelperText, TextField, Alert, Dialog,
  DialogTitle, DialogContent, DialogActions, IconButton, Grid, Tooltip,
} from '@mui/material';
import {
  ArrowBack, SmartToy, Add, Delete, Edit, CheckCircleOutline,
  AccessTime, CalendarToday, Settings as SettingsIcon, FilterList, LinkOff,
  EventOutlined, VideocamOutlined, PeopleOutline, EventBusy,
} from '@mui/icons-material';
import { hub, googleCalendar } from '../services/api';
import BotTokenConnectModal from '../components/shared/BotTokenConnectModal';
import AddToGroupFlow from '../components/hub/AddToGroupFlow';
import GroupSettingsOverlay from '../components/hub/GroupSettingsOverlay';
import { getTabsForBot } from '../config/assistantHubRegistry';
import TimezoneSelect from '../components/TimezoneSelect';

// Official bot always shows all non-customOnly tabs.
const TABS = getTabsForBot(true).map(t => ({ label: t.label, value: t.key }));

// ── Shared date formatter ─────────────────────────────────────────────────────
function fmtDate(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch { return iso; }
}

// Compact "x ago" relative time for the extraction-health banner.
function timeAgo(iso) {
  if (!iso) return 'never';
  try {
    const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return 'just now';
    const m = Math.floor(s / 60); if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  } catch { return iso; }
}

// Backend serialises Hub datetimes as naive UTC (no trailing Z). When a `tz`
// (IANA name) is supplied we treat the value as UTC and render it in that zone,
// so meetings/reminders show the user's local wall-clock time consistently with
// the Telegram DMs, digest and Google Calendar.
function _asUtc(iso) {
  return (iso.includes('T') && !iso.endsWith('Z') && !iso.includes('+')) ? iso + 'Z' : iso;
}

function fmtDateTime(iso, tz) {
  if (!iso) return null;
  try {
    const d = new Date(tz ? _asUtc(iso) : iso);
    return d.toLocaleString('en-GB', {
      day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
      ...(tz ? { timeZone: tz } : {}),
    });
  } catch { return iso; }
}

function isOverdue(isoDate) {
  if (!isoDate) return false;
  // Treat naive datetimes as UTC so the comparison is timezone-independent.
  return new Date(_asUtc(isoDate)) < new Date();
}

// ── Timezone-correct <input type="datetime-local"> <-> stored UTC ───────────────
// Stored values are naive-UTC (no Z). The datetime-local input shows wall-clock
// time in the user's SELECTED zone (tz), so we convert in both directions through
// that zone — never relying on the browser's own timezone matching.
function _tzOffsetMs(date, tz) {
  // ms to add to a UTC instant to get the wall-clock reading in `tz`.
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone: tz, hour12: false,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
  const p = {};
  dtf.formatToParts(date).forEach(x => { if (x.type !== 'literal') p[x.type] = x.value; });
  const asUTC = Date.UTC(+p.year, +p.month - 1, +p.day, +(p.hour % 24), +p.minute, +p.second);
  return asUTC - date.getTime();
}

function utcToLocalInput(iso, tz) {
  if (!iso) return '';
  const d = new Date(_asUtc(iso));
  if (isNaN(d.getTime())) return '';
  if (!tz) return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const offset = _tzOffsetMs(d, tz);
  return new Date(d.getTime() + offset).toISOString().slice(0, 16);
}

function localInputToUtcIso(input, tz) {
  if (!input) return null;
  if (!tz) return new Date(input).toISOString();
  // `input` ("YYYY-MM-DDTHH:mm") is wall-clock time in tz. Treat it as if UTC, then
  // back out the zone offset (twice, so a DST boundary settles correctly).
  const naive = new Date(input + ':00Z').getTime();
  let utc = naive;
  for (let i = 0; i < 2; i++) utc = naive - _tzOffsetMs(new Date(utc), tz);
  return new Date(utc).toISOString();
}

// ── Root component ─────────────────────────────────────────────────────────────

export default function HubWorkspace() {
  const navigate = useNavigate();
  const { tab = 'overview' } = useParams();
  const [botData, setBotData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [groups, setGroups] = useState([]);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [botRegOpen, setBotRegOpen] = useState(false);
  const [, setAllBots] = useState([]);
  const plan = (() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}').subscription_tier || 'free'; } catch { return 'free'; }
  })();

  useEffect(() => {
    hub.getOfficialBot()
      .then(r => setBotData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
    hub.listOfficialGroups()
      .then(r => {
        const g = r.data.groups || [];
        setGroups(g);
        if (g.length === 0 && !localStorage.getItem('hub_onboarding_done')) {
          setOnboardingOpen(true);
        }
      })
      .catch(() => {});
  }, []);

  const handleTabChange = (_, newTab) => navigate(`/ark/official/${newTab}`);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <Box sx={{ px: { xs: 2, sm: 3 }, pt: 2, pb: 0, borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Button size="small" startIcon={<ArrowBack sx={{ fontSize: 15 }} />} onClick={() => navigate('/ark')}
            sx={{ minWidth: 0, color: 'text.secondary', fontWeight: 400, px: 0.5 }}>Hub</Button>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1, minWidth: 0 }}>
            <SmartToy sx={{ fontSize: 20, color: 'primary.main', flexShrink: 0 }} />
            {loading ? <CircularProgress size={16} /> : (
              <>
                <Typography variant="subtitle1" fontWeight={700} noWrap>
                  {botData?.display_name || 'Official Telegizer Assistant'}
                </Typography>
                <Chip label="Active" size="small" sx={{ bgcolor: 'success.main', color: '#fff', height: 18, fontSize: '0.65rem', flexShrink: 0 }} />
                <Typography variant="caption" color="text.secondary" noWrap sx={{ flexShrink: 0 }}>
                  @{botData?.telegram_bot_username || 'telegizer_bot'} · {groups.length || (botData?.group_count ?? 0)} groups
                </Typography>
              </>
            )}
          </Box>
        </Box>
        <Tabs value={TABS.find(t => t.value === tab) ? tab : 'overview'} onChange={handleTabChange}
          variant="scrollable" scrollButtons="auto" allowScrollButtonsMobile
          sx={{ minHeight: 38, '& .MuiTab-root': { minHeight: 38, fontSize: '0.8rem', py: 0, px: 1.5, textTransform: 'none' } }}>
          {TABS.map(t => <Tab key={t.value} label={t.label} value={t.value} />)}
        </Tabs>
      </Box>

      {/* Tab content */}
      <Box sx={{ flex: 1, overflow: 'auto', p: { xs: 2, sm: 3 } }}>
        {/* botId is intentionally null for the official Echo bot: every downstream
            `botId ? … : …` (data calls and navigation) treats falsy as "official".
            Passing the literal "official" string broke _resolve_bot lookups (404)
            and the settings/navigation ternaries. */}
        <TabContent tab={tab} botData={botData} groups={groups} setGroups={setGroups} botId={null} />
      </Box>

      <BotTokenConnectModal
        open={botRegOpen}
        mode="assistant_hub"
        plan={plan}
        onClose={() => setBotRegOpen(false)}
        onConnected={(newBot) => {
          setAllBots(prev => [...prev, newBot]);
          setBotRegOpen(false);
        }}
      />

      <OnboardingFlow
        open={onboardingOpen}
        onClose={() => {
          localStorage.setItem('hub_onboarding_done', '1');
          setOnboardingOpen(false);
        }}
      />
    </Box>
  );
}

// ── Tab dispatcher ─────────────────────────────────────────────────────────────
export function TabContent({ tab, botData, groups, setGroups, botId }) {
  // The user's Hub timezone — all meeting/reminder times are stored as UTC and
  // rendered in this zone (matching the AI extraction, DMs and calendar).
  const [tz, setTz] = useState('UTC');
  useEffect(() => {
    hub.getMemoryGlobal().then(r => setTz(r.data?.timezone || 'UTC')).catch(() => {});
  }, []);
  switch (tab) {
    case 'overview':   return <HubOverview botData={botData} groups={groups} setGroups={setGroups} botId={botId} tz={tz} />;
    case 'notes':      return <HubNotes groups={groups} botId={botId} />;
    case 'reminders':  return <HubReminders groups={groups} botId={botId} tz={tz} />;
    case 'meetings':   return <HubMeetings groups={groups} botId={botId} tz={tz} />;
    case 'tasks':      return <HubTasks groups={groups} botId={botId} />;
    case 'templates':  return <HubTemplates botId={botId} />;
    case 'knowledge':  return <HubKnowledge botId={botId} />;
    case 'automation': return <HubAutomation />;
    case 'settings':   return <HubSettings botData={botData} groups={groups} setGroups={setGroups} botId={botId} />;
    default:           return <TabComingSoon tab={tab} />;
  }
}

function TabComingSoon({ tab }) {
  return (
    <Box sx={{ maxWidth: 480, pt: 4, textAlign: 'center' }}>
      <Typography variant="h6" gutterBottom sx={{ textTransform: 'capitalize' }}>{tab}</Typography>
      <Typography variant="body2" color="text.secondary">
        This tab is registered but not yet implemented. Add a <code>case '{tab}'</code> in <code>TabContent</code> to activate it.
      </Typography>
    </Box>
  );
}

// ── Overview ───────────────────────────────────────────────────────────────────
// Extraction-health banner — shows whether Echo is actually reading + extracting
// (green Active / red Stalled / grey Idle), so a silent failure is visible instead
// of looking like an empty Hub. Official bot only; auto-refreshes every 60s.
function HubHealthBanner() {
  const [h, setH] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    hub.getExtractionHealth()
      .then(r => setH(r.data))
      .catch(() => setH(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  if (loading && !h) return null;
  if (!h) return null;

  const cfg = ({
    active:  { color: 'success', label: '🟢 Active',  help: "Echo is reading your groups and extracting items." },
    stalled: { color: 'error',   label: '🔴 Stalled', help: "Messages are buffered but extraction hasn't run recently — items may be delayed." },
    idle:    { color: 'default', label: '⚪ Idle',     help: 'No new messages to process right now.' },
  })[h.status] || { color: 'default', label: 'Unknown', help: '' };

  const items = h.items_last_24h?.total ?? 0;

  // Root-cause diagnosis — most actionable problem wins. Each line tells the user
  // exactly what to fix, so a dead Hub explains itself instead of showing a blank page.
  let diagnosis = null;
  if (h.bot_running === false) {
    diagnosis = {
      severity: 'error',
      text: 'Echo is offline on the server — ECHO_BOT_TOKEN is not set (or wrong) on the web service, so no group messages can be received. Check Railway → web service → Variables.',
    };
  } else if (h.ai_key_configured === false) {
    diagnosis = {
      severity: 'error',
      text: "No AI key is configured, so extraction can't run. Add one in Settings → AI, or set the platform key.",
    };
  } else if (h.status === 'idle' && h.buffered_messages === 0) {
    diagnosis = {
      severity: 'info',
      text: 'No messages received yet. Telegram never replays old messages to a bot — send a NEW message in the group, and make sure Echo is an admin (or has Group Privacy turned off in BotFather).',
    };
  } else if (h.last_error) {
    diagnosis = { severity: 'warning', text: `Last extraction failed: ${h.last_error}` };
  }

  return (
    <Card variant="outlined" sx={{ mb: 2, ...(h.status === 'stalled' ? { borderColor: 'error.main' } : {}) }}>
      <CardContent sx={{ p: '12px !important' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          <Chip size="small" color={cfg.color} label={cfg.label} />
          <Typography variant="body2" color="text.secondary" sx={{ flex: 1, minWidth: 180 }}>
            {cfg.help}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
            Last run {timeAgo(h.last_extraction_at)} · {h.buffered_messages} buffered · {items} item{items !== 1 ? 's' : ''}/24h
          </Typography>
        </Box>
        {diagnosis && (
          <Alert severity={diagnosis.severity} sx={{ mt: 1.5, py: 0, fontSize: '0.8rem' }}>
            {diagnosis.text}
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

function HubOverview({ botData, groups, setGroups, botId, tz }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [groupFilter, setGroupFilter] = useState('');
  const [overlayGroup, setOverlayGroup] = useState(null);
  const [unlinkTarget, setUnlinkTarget] = useState(null);
  const [unlinkDeleteData, setUnlinkDeleteData] = useState(false);
  const [unlinkLoading, setUnlinkLoading] = useState(false);
  const [unlinkError, setUnlinkError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    hub.getOverview(groupFilter || null, botId || null)
      .then(r => setData(r.data))
      .catch(() => { setData(null); setLoadError(true); })
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupFilter]);

  useEffect(() => { load(); }, [load]);

  const groupCount = data?.group_count ?? botData?.group_count ?? 0;

  // Overlay edits propagate to the shared groups array (when available).
  const handleGroupUpdated = (updated) =>
    setGroups?.(prev => prev.map(g => g.id === updated.id ? { ...g, ...updated } : g));
  const handleGroupDisconnected = (groupId) => {
    setGroups?.(prev => prev.filter(g => g.id !== groupId));
    if (groupFilter === groupId) setGroupFilter('');
  };

  const handleUnlink = async () => {
    if (!unlinkTarget) return;
    setUnlinkLoading(true); setUnlinkError(null);
    try {
      await hub.disconnectGroup(unlinkTarget.id, unlinkDeleteData);
      handleGroupDisconnected(unlinkTarget.id);
      setUnlinkTarget(null);
      setUnlinkDeleteData(false);
      load();
    } catch (e) {
      setUnlinkError(e?.response?.data?.error || 'Failed to unlink group.');
    }
    setUnlinkLoading(false);
  };

  if (!loading && groupCount === 0 && groups.length === 0) {
    return (
      <EmptyState icon="🤖" title="Add the Telegizer bot to your private groups to get started."
        body="The assistant will silently observe and surface tasks, decisions, and meetings here."
        action={<Button variant="contained" size="small" onClick={() => navigate(botId ? `/ark/bots/${botId}/settings` : '/ark/official/settings')}>+ Add to Group</Button>}
      />
    );
  }

  const activeGroup = groupFilter ? groups.find(g => g.id === groupFilter) : null;

  return (
    <Box sx={{ maxWidth: 900 }}>
      {/* Extraction health — official bot only (endpoint resolves the official bot). */}
      {!botId && <HubHealthBanner />}

      {/* Connected groups — card grid (parity with the Groups / Servers dashboards),
          so each group is directly accessible from the Hub landing page. */}
      {groups.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1, flexWrap: 'wrap', gap: 1 }}>
            <SectionHeader label={`Your Groups (${groups.length})`} />
            <Button size="small" startIcon={<Add sx={{ fontSize: 16 }} />}
              onClick={() => navigate(botId ? `/ark/bots/${botId}/settings` : '/ark/official/settings')}>
              Add to Group
            </Button>
          </Box>
          <Grid container spacing={2}>
            {groups.map(g => (
              <Grid item xs={12} sm={6} lg={groups.length > 2 ? 4 : 6} key={g.id}>
                <EchoGroupCard
                  group={g}
                  selected={groupFilter === g.id}
                  onViewItems={() => setGroupFilter(prev => prev === g.id ? '' : g.id)}
                  onManage={() => setOverlayGroup(g)}
                  onUnlink={() => { setUnlinkTarget(g); setUnlinkDeleteData(false); setUnlinkError(null); }}
                />
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      <Box sx={{ maxWidth: 700 }}>
      <SectionHeader label={activeGroup ? `Activity — ${activeGroup.display_name || activeGroup.group_name}` : 'Activity — All Groups'} />

      {/* Group filter */}
      {groups.length > 1 && (
        <FormControl size="small" sx={{ mb: 2, minWidth: 180 }}>
          <InputLabel>Filter by group</InputLabel>
          <Select value={groupFilter} label="Filter by group" onChange={e => setGroupFilter(e.target.value)}>
            <MenuItem value="">All groups</MenuItem>
            {groups.map(g => <MenuItem key={g.id} value={g.id}>{g.group_name || g.id}</MenuItem>)}
          </Select>
        </FormControl>
      )}

      {loading ? (
        <Box sx={{ textAlign: 'center', py: 6 }}><CircularProgress /></Box>
      ) : loadError ? (
        <Alert severity="error" sx={{ mb: 2 }}
          action={<Button color="inherit" size="small" onClick={load}>Retry</Button>}>
          Couldn't load activity. Please try again.
        </Alert>
      ) : (
        <>
          {data?.new_inbox_items > 0 && (
            <Alert severity="info" sx={{ mb: 2 }}>
              {data.new_inbox_items} new item{data.new_inbox_items !== 1 ? 's' : ''} extracted from your groups.
            </Alert>
          )}

          {/* Tasks */}
          <OverviewSection title="Tasks" count={data?.tasks?.length} emptyText="No pending tasks.">
            {data?.tasks?.map(t => (
              <ItemRow key={t.id}
                label={t.title}
                meta={[t.assignee_name, t.due_date && <span style={{ color: isOverdue(t.due_date) ? '#f44336' : undefined }}>{fmtDate(t.due_date)}</span>]}
                badge={t.priority !== 'normal' ? t.priority : null}
                badgeColor={t.priority === 'high' ? 'error' : 'default'}
                onConfirm={() => hub.updateTask(t.id, { status: 'confirmed' }).then(() => load())}
              />
            ))}
          </OverviewSection>

          {/* Meetings */}
          <OverviewSection title="Upcoming Meetings" count={data?.meetings?.length} emptyText="No upcoming meetings.">
            {data?.meetings?.map(m => (
              <ItemRow key={m.id}
                label={m.title || 'Meeting'}
                meta={[fmtDateTime(m.scheduled_at, tz), m.participants?.length ? `${m.participants.join(', ')}` : null]}
                onDismiss={() => hub.dismissMeeting(m.id).then(() => load())}
              />
            ))}
          </OverviewSection>

          {/* Decisions */}
          <OverviewSection title="Recent Decisions" count={data?.decisions?.length} emptyText="No decisions captured yet.">
            {data?.decisions?.map(d => (
              <ItemRow key={d.id}
                label={d.content}
                meta={[d.made_by, fmtDate(d.created_at)]}
                onDismiss={() => hub.dismissDecision(d.id).then(() => load())}
              />
            ))}
          </OverviewSection>

          {/* Reminders */}
          <OverviewSection title="Upcoming Reminders" count={data?.reminders?.length} emptyText="No reminders scheduled.">
            {data?.reminders?.map(r => (
              <ItemRow key={r.id}
                label={r.content}
                meta={[fmtDateTime(r.remind_at, tz)]}
              />
            ))}
          </OverviewSection>
        </>
      )}
      </Box>

      <GroupSettingsOverlay open={Boolean(overlayGroup)} group={overlayGroup}
        onClose={() => setOverlayGroup(null)}
        onUpdated={handleGroupUpdated} onDisconnected={handleGroupDisconnected} />

      {/* Unlink confirmation */}
      <Dialog open={Boolean(unlinkTarget)} onClose={() => !unlinkLoading && setUnlinkTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Unlink group?</DialogTitle>
        <DialogContent>
          {unlinkError && <Alert severity="error" sx={{ mb: 2 }}>{unlinkError}</Alert>}
          <Typography variant="body2">
            Disconnect <strong>{unlinkTarget?.display_name || unlinkTarget?.group_name}</strong>? Echo will leave the group
            (if it's still a member) and stop observing it.
          </Typography>
          <FormControlLabel
            sx={{ mt: 1.5 }}
            control={<Switch size="small" checked={unlinkDeleteData} onChange={e => setUnlinkDeleteData(e.target.checked)} />}
            label={<Typography variant="body2">Also delete all items extracted from this group</Typography>}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setUnlinkTarget(null)} color="inherit" size="small" disabled={unlinkLoading}>Cancel</Button>
          <Button onClick={handleUnlink} variant="contained" color="error" size="small" disabled={unlinkLoading}>
            {unlinkLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Unlink
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Echo group card ──────────────────────────────────────────────────────────
// Card-grid representation of a connected group, matching the Groups / Servers
// dashboards so each group is directly accessible from the Hub landing page.
function EchoGroupCard({ group, selected, onViewItems, onManage, onUnlink }) {
  const name = group.display_name || group.group_name || `Group ${group.telegram_group_id}`;
  const paused = !group.is_active;
  const planLimited = group.pause_reason === 'plan_limit';
  const extracts = [
    group.extract_tasks && 'Tasks',
    group.extract_reminders && 'Reminders',
    group.extract_decisions && 'Decisions',
    group.extract_meetings && 'Meetings',
  ].filter(Boolean);

  return (
    <Card sx={{
      height: '100%',
      borderColor: selected ? 'primary.main' : undefined,
      borderWidth: selected ? 2 : undefined,
      transition: 'box-shadow .15s, border-color .15s',
      '&:hover': { boxShadow: 4 },
    }} variant="outlined">
      <CardContent>
        {/* Title + status */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6" noWrap fontWeight={600} sx={{ fontSize: '1rem' }}>{name}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
              ID: {group.telegram_group_id}
            </Typography>
          </Box>
          {planLimited
            ? <Chip label="Plan limit" size="small" color="warning" sx={{ flexShrink: 0 }} />
            : paused
              ? <Chip label="Paused" size="small" sx={{ flexShrink: 0 }} />
              : <Chip label="Active" size="small" color="success" sx={{ flexShrink: 0 }} />}
        </Box>

        <Divider sx={{ my: 1.5 }} />

        {/* Bot type + last activity */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
          <Box>
            <Typography variant="caption" color="text.secondary">Assistant</Typography>
            <Typography variant="body2" fontWeight={500}>🔵 Echo</Typography>
          </Box>
          <Box sx={{ textAlign: 'right' }}>
            <Typography variant="caption" color="text.secondary" display="block">Last activity</Typography>
            <Typography variant="body2" fontWeight={500}>{timeAgo(group.last_batch_at)}</Typography>
          </Box>
        </Box>

        {/* What Echo extracts here */}
        {extracts.length > 0 && (
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mb: 1.5 }}>
            {extracts.map(e => (
              <Chip key={e} label={e} size="small" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />
            ))}
          </Box>
        )}

        {/* Actions */}
        <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap' }}>
          <Tooltip title={selected ? 'Showing this group below — click to show all' : 'Show only this group\'s items below'}>
            <Button size="small" variant={selected ? 'contained' : 'outlined'} startIcon={<FilterList />}
              onClick={onViewItems} sx={{ flex: 1 }}>
              {selected ? 'Viewing' : 'View Items'}
            </Button>
          </Tooltip>
          <Button size="small" variant="outlined" startIcon={<SettingsIcon />} onClick={onManage} sx={{ flex: 1 }}>
            Manage
          </Button>
          <Tooltip title="Disconnect this group from Echo">
            <Button size="small" variant="outlined" color="error" startIcon={<LinkOff />} onClick={onUnlink} sx={{ flex: 1 }}>
              Unlink
            </Button>
          </Tooltip>
        </Box>
      </CardContent>
    </Card>
  );
}

function OverviewSection({ title, count, emptyText, children }) {
  return (
    <Box sx={{ mb: 3 }}>
      <SectionHeader label={title} />
      <Card variant="outlined">
        <CardContent sx={{ p: '12px !important' }}>
          {!count ? (
            <Typography variant="body2" color="text.secondary">{emptyText}</Typography>
          ) : children}
        </CardContent>
      </Card>
    </Box>
  );
}

function ItemRow({ label, meta = [], badge, badgeColor, onConfirm, onDismiss }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-start', py: 0.75, gap: 1, '&:not(:last-child)': { borderBottom: '1px solid', borderColor: 'divider' } }}>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" fontWeight={500} noWrap>{label}</Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 0.25 }}>
          {meta.filter(Boolean).map((m, i) => (
            <Typography key={i} variant="caption" color="text.secondary">{m}</Typography>
          ))}
          {badge && <Chip label={badge} size="small" color={badgeColor} sx={{ height: 16, fontSize: '0.6rem' }} />}
        </Box>
      </Box>
      <Box sx={{ display: 'flex', gap: 0.5, flexShrink: 0 }}>
        {onConfirm && (
          <IconButton size="small" onClick={onConfirm} title="Confirm">
            <CheckCircleOutline sx={{ fontSize: 16, color: 'success.main' }} />
          </IconButton>
        )}
        {onDismiss && (
          <IconButton size="small" onClick={onDismiss} title="Dismiss">
            <Delete sx={{ fontSize: 16, color: 'text.disabled' }} />
          </IconButton>
        )}
      </Box>
    </Box>
  );
}

// ── Tasks tab ──────────────────────────────────────────────────────────────────
function HubTasks({ groups, botId }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('pending');
  const [groupFilter, setGroupFilter] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editTask, setEditTask] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    hub.listTasks({ status: statusFilter || undefined, group_id: groupFilter || undefined, ...(botId ? { bot_id: botId } : {}) })
      .then(r => setTasks(r.data.tasks || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, groupFilter]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    await hub.deleteTask(deleteTarget.id);
    setDeleteLoading(false);
    setDeleteTarget(null);
    load();
  };

  const handleStatusChange = async (task, newStatus) => {
    await hub.updateTask(task.id, { status: newStatus });
    load();
  };

  return (
    <Box sx={{ maxWidth: 700 }}>
      {/* Filters + add button */}
      <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Status</InputLabel>
          <Select value={statusFilter} label="Status" onChange={e => setStatusFilter(e.target.value)}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="pending">Pending</MenuItem>
            <MenuItem value="confirmed">Confirmed</MenuItem>
            <MenuItem value="done">Done</MenuItem>
            <MenuItem value="dismissed">Dismissed</MenuItem>
          </Select>
        </FormControl>
        {groups.length > 1 && (
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Group</InputLabel>
            <Select value={groupFilter} label="Group" onChange={e => setGroupFilter(e.target.value)}>
              <MenuItem value="">All groups</MenuItem>
              {groups.map(g => <MenuItem key={g.id} value={g.id}>{g.group_name || g.id}</MenuItem>)}
            </Select>
          </FormControl>
        )}
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" size="small" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
          New Task
        </Button>
      </Box>

      {/* Task list */}
      {loading ? (
        <Box sx={{ textAlign: 'center', py: 6 }}><CircularProgress /></Box>
      ) : tasks.length === 0 ? (
        <EmptyState icon="✅" title="No tasks yet."
          body="Tasks will appear here once extracted from group messages, or create one manually."
          action={<Button variant="outlined" size="small" onClick={() => setCreateOpen(true)}>+ New Task</Button>}
        />
      ) : (
        <Card variant="outlined">
          {tasks.map((t, i) => (
            <Box key={t.id}>
              <Box sx={{ display: 'flex', alignItems: 'flex-start', px: 2, py: 1.25, gap: 1 }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
                    <Typography variant="body2" fontWeight={500}>{t.title}</Typography>
                    <TaskStatusChip status={t.status} />
                    {t.priority === 'high' && <Chip label="high" size="small" color="error" sx={{ height: 16, fontSize: '0.6rem' }} />}
                    {t.source === 'extracted' && <Chip label="AI" size="small" sx={{ height: 16, fontSize: '0.6rem', bgcolor: 'primary.main', color: '#fff' }} />}
                  </Box>
                  <Box sx={{ display: 'flex', gap: 1.5, mt: 0.25, flexWrap: 'wrap' }}>
                    {t.assignee_name && <Typography variant="caption" color="text.secondary">{t.assignee_name}</Typography>}
                    {t.due_date && (
                      <Typography variant="caption" sx={{ color: isOverdue(t.due_date) ? 'error.main' : 'text.secondary' }}>
                        <CalendarToday sx={{ fontSize: 10, mr: 0.25 }} />{fmtDate(t.due_date)}
                      </Typography>
                    )}
                  </Box>
                </Box>
                <Box sx={{ display: 'flex', gap: 0.25, flexShrink: 0 }}>
                  {t.status === 'pending' && (
                    <IconButton size="small" title="Mark confirmed" onClick={() => handleStatusChange(t, 'confirmed')}>
                      <CheckCircleOutline sx={{ fontSize: 16, color: 'success.main' }} />
                    </IconButton>
                  )}
                  {t.status !== 'done' && (
                    <IconButton size="small" title="Mark done" onClick={() => handleStatusChange(t, 'done')}>
                      <CheckCircleOutline sx={{ fontSize: 16, color: 'text.disabled' }} />
                    </IconButton>
                  )}
                  <IconButton size="small" title="Edit" onClick={() => setEditTask(t)}>
                    <Edit sx={{ fontSize: 15 }} />
                  </IconButton>
                  <IconButton size="small" title="Delete" onClick={() => setDeleteTarget(t)}>
                    <Delete sx={{ fontSize: 15 }} />
                  </IconButton>
                </Box>
              </Box>
              {i < tasks.length - 1 && <Divider />}
            </Box>
          ))}
        </Card>
      )}

      <TaskModal open={createOpen || Boolean(editTask)} task={editTask}
        onClose={() => { setCreateOpen(false); setEditTask(null); }}
        onSaved={() => { setCreateOpen(false); setEditTask(null); load(); }}
        groups={groups} botId={botId}
      />

      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete task?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">Delete <strong>{deleteTarget?.title}</strong>? This cannot be undone.</Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleteTarget(null)} color="inherit" size="small">Cancel</Button>
          <Button onClick={handleDelete} variant="contained" color="error" size="small" disabled={deleteLoading}>
            {deleteLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

function TaskStatusChip({ status }) {
  const map = { pending: ['Pending', 'default'], confirmed: ['Confirmed', 'info'], done: ['Done', 'success'], dismissed: ['Dismissed', 'default'] };
  const [label, color] = map[status] || ['Unknown', 'default'];
  return <Chip label={label} size="small" color={color} sx={{ height: 16, fontSize: '0.6rem' }} />;
}

// ── Reminders tab ──────────────────────────────────────────────────────────────
function HubReminders({ groups, botId, tz }) {
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('upcoming');
  const [groupFilter, setGroupFilter] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editReminder, setEditReminder] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    hub.listReminders({ filter: filter || undefined, group_id: groupFilter || undefined, ...(botId ? { bot_id: botId } : {}) })
      .then(r => setReminders(r.data.reminders || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, groupFilter]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    await hub.deleteReminder(deleteTarget.id);
    setDeleteLoading(false);
    setDeleteTarget(null);
    load();
  };

  return (
    <Box sx={{ maxWidth: 700 }}>
      <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Filter</InputLabel>
          <Select value={filter} label="Filter" onChange={e => setFilter(e.target.value)}>
            <MenuItem value="upcoming">Upcoming</MenuItem>
            <MenuItem value="overdue">Overdue</MenuItem>
            <MenuItem value="">All</MenuItem>
          </Select>
        </FormControl>
        {groups.length > 1 && (
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Group</InputLabel>
            <Select value={groupFilter} label="Group" onChange={e => setGroupFilter(e.target.value)}>
              <MenuItem value="">All groups</MenuItem>
              {groups.map(g => <MenuItem key={g.id} value={g.id}>{g.group_name || g.id}</MenuItem>)}
            </Select>
          </FormControl>
        )}
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" size="small" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
          New Reminder
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ textAlign: 'center', py: 6 }}><CircularProgress /></Box>
      ) : reminders.length === 0 ? (
        <EmptyState icon="🔔" title="No reminders scheduled."
          body="Reminders extracted from group discussions will appear here."
          action={<Button variant="outlined" size="small" onClick={() => setCreateOpen(true)}>+ New Reminder</Button>}
        />
      ) : (
        <Card variant="outlined">
          {reminders.map((r, i) => (
            <Box key={r.id}>
              <Box sx={{ display: 'flex', alignItems: 'flex-start', px: 2, py: 1.25, gap: 1 }}>
                <AccessTime sx={{ fontSize: 16, color: isOverdue(r.remind_at) ? 'error.main' : 'text.secondary', mt: 0.25, flexShrink: 0 }} />
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" fontWeight={500}>{r.content}</Typography>
                  <Typography variant="caption" sx={{ color: isOverdue(r.remind_at) ? 'error.main' : 'text.secondary' }}>
                    {fmtDateTime(r.remind_at, tz)}{isOverdue(r.remind_at) ? ' · overdue' : ''}
                  </Typography>
                  {r.source === 'extracted' && (
                    <Chip label="AI" size="small" sx={{ ml: 1, height: 14, fontSize: '0.58rem', bgcolor: 'primary.main', color: '#fff' }} />
                  )}
                </Box>
                <Box sx={{ display: 'flex', gap: 0.25, flexShrink: 0 }}>
                  <IconButton size="small" onClick={() => setEditReminder(r)}><Edit sx={{ fontSize: 15 }} /></IconButton>
                  <IconButton size="small" onClick={() => setDeleteTarget(r)}><Delete sx={{ fontSize: 15 }} /></IconButton>
                </Box>
              </Box>
              {i < reminders.length - 1 && <Divider />}
            </Box>
          ))}
        </Card>
      )}

      <ReminderModal open={createOpen || Boolean(editReminder)} reminder={editReminder}
        onClose={() => { setCreateOpen(false); setEditReminder(null); }}
        onSaved={() => { setCreateOpen(false); setEditReminder(null); load(); }}
        groups={groups} botId={botId}
      />

      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete reminder?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">Delete this reminder? This cannot be undone.</Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleteTarget(null)} color="inherit" size="small">Cancel</Button>
          <Button onClick={handleDelete} variant="contained" color="error" size="small" disabled={deleteLoading}>
            {deleteLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Meetings tab ───────────────────────────────────────────────────────────────
// Surfaces meetings Echo extracts from connected groups (HubMeeting store — the
// same data shown on the Overview "Upcoming Meetings" card). Read + dismiss only;
// these are AI-extracted, not manually created. Undated meetings (where the AI
// couldn't pin a date) get their own "Needs a date" filter so they're not lost.
function gcalUrl({ title, startIso, durationMins = 60, description = '' }) {
  // startIso is naive UTC from the backend — treat it as UTC, not browser-local.
  const dt = new Date(_asUtc(startIso));
  const pad = n => String(n).padStart(2, '0');
  const fmt = d =>
    `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}00Z`;
  const end = new Date(dt.getTime() + durationMins * 60000);
  const params = new URLSearchParams({ action: 'TEMPLATE', text: title || 'Meeting', dates: `${fmt(dt)}/${fmt(end)}`, details: description });
  return `https://calendar.google.com/calendar/render?${params}`;
}

function HubMeetings({ groups, botId, tz }) {
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('upcoming');
  const [groupFilter, setGroupFilter] = useState('');
  const [dismissTarget, setDismissTarget] = useState(null);
  const [dismissLoading, setDismissLoading] = useState(false);
  const [cal, setCal] = useState(null);      // {connected, configured, email, auto_sync_meetings, last_sync_error}
  const [syncingId, setSyncingId] = useState(null);
  const [syncError, setSyncError] = useState(null);   // {message, reconnect}
  const [editTarget, setEditTarget] = useState(undefined);  // undefined=closed, null=new, obj=edit

  const load = useCallback(() => {
    setLoading(true);
    hub.listMeetings({ group_id: groupFilter || undefined, ...(botId ? { bot_id: botId } : {}) })
      .then(r => setMeetings(r.data.meetings || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupFilter]);

  const loadCal = useCallback(() => {
    googleCalendar.status()
      .then(r => setCal(r.data))
      .catch(() => setCal({ connected: false, configured: false }));
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadCal(); }, [loadCal]);

  const connectCalendar = async () => {
    try {
      const { data } = await googleCalendar.getAuthUrl();
      window.location.href = data.auth_url;
    } catch { /* not configured on this server */ }
  };

  const toggleAutoSync = async (val) => {
    setCal(c => ({ ...c, auto_sync_meetings: val }));
    try { await googleCalendar.updateSettings({ auto_sync_meetings: val }); }
    catch { loadCal(); }
  };

  const syncToCalendar = async (m) => {
    setSyncingId(m.id);
    setSyncError(null);
    try {
      await googleCalendar.syncHubMeeting(m.id);
      setMeetings(prev => prev.map(x => x.id === m.id ? { ...x, calendar_pushed: true } : x));
      setCal(c => c ? { ...c, last_sync_error: null } : c);
    } catch (e) {
      const data = e?.response?.data || {};
      setSyncError({
        message: data.error || 'Couldn’t add this meeting to Google Calendar. Please try again.',
        reconnect: !!data.reconnect_required,
      });
    } finally { setSyncingId(null); }
  };

  const handleDismiss = async () => {
    if (!dismissTarget) return;
    setDismissLoading(true);
    try { await hub.dismissMeeting(dismissTarget.id); } catch { /* noop */ }
    setMeetings(prev => prev.filter(m => m.id !== dismissTarget.id));
    setDismissLoading(false);
    setDismissTarget(null);
  };

  // After a create/edit save, fold the returned row in and surface any sync issue.
  const handleSaved = (resp) => {
    const saved = resp?.meeting;
    if (saved) {
      setMeetings(prev => {
        const exists = prev.some(m => m.id === saved.id);
        return exists ? prev.map(m => m.id === saved.id ? saved : m) : [...prev, saved];
      });
    }
    if (resp?.sync_error) {
      setSyncError({ message: resp.sync_error, reconnect: !!resp.reconnect_required });
      loadCal();
    }
    setEditTarget(undefined);
  };

  const groupName = (id) => {
    const g = groups.find(x => String(x.id) === String(id));
    return g ? (g.group_name || g.id) : null;
  };

  // Endpoint returns all non-dismissed meetings (past + future + undated);
  // bucket them client-side so the filter switches views without a refetch.
  const now = Date.now();
  const bucketOf = (m) => {
    if (!m.scheduled_at) return 'undated';
    return new Date(_asUtc(m.scheduled_at)).getTime() < now ? 'past' : 'upcoming';
  };
  const counts = meetings.reduce((acc, m) => { acc[bucketOf(m)] = (acc[bucketOf(m)] || 0) + 1; return acc; }, {});
  let visible = meetings.filter(m => !filter || bucketOf(m) === filter);
  // Backend sorts scheduled_at asc; past reads better most-recent-first.
  if (filter === 'past') visible = [...visible].reverse();
  const otherCount = (counts.undated || 0) + (counts.past || 0);

  return (
    <Box sx={{ maxWidth: 700 }}>
      {/* Google Calendar connection + auto-sync */}
      {cal && cal.configured && (
        <Box sx={{ mb: 2 }}>
          {cal.connected ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', p: 1.25, border: '1px solid', borderColor: 'divider', borderRadius: 1, bgcolor: 'action.hover' }}>
              <CalendarToday sx={{ fontSize: 16, color: 'success.main', flexShrink: 0 }} />
              <Typography variant="caption" sx={{ fontWeight: 600 }}>Google Calendar connected</Typography>
              {cal.email && <Typography variant="caption" color="text.secondary" noWrap>· {cal.email}</Typography>}
              <Box sx={{ flex: 1 }} />
              <FormControlLabel
                sx={{ mr: 0 }}
                control={<Switch size="small" checked={!!cal.auto_sync_meetings} onChange={e => toggleAutoSync(e.target.checked)} />}
                label={<Typography variant="caption">Auto-sync new meetings</Typography>}
              />
            </Box>
          ) : (
            <Button size="small" variant="outlined" startIcon={<CalendarToday sx={{ fontSize: 15 }} />} onClick={connectCalendar}>
              Connect Google Calendar
            </Button>
          )}
          {/* Persisted sync failure (e.g. expired Google grant) — surfaced so the
              user knows WHY meetings stopped syncing instead of silently failing. */}
          {cal.connected && cal.last_sync_error && (
            <Alert severity="warning" sx={{ mt: 1, py: 0, fontSize: '0.78rem' }}
              action={
                cal.last_sync_error.toLowerCase().includes('reconnect') ? (
                  <Button color="inherit" size="small" onClick={connectCalendar}>Reconnect</Button>
                ) : null
              }>
              {cal.last_sync_error.replace(/^reconnect_required:\s*/i, '')}
            </Alert>
          )}
        </Box>
      )}

      {/* Transient error from a manual "Add to Google Calendar" click. */}
      {syncError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setSyncError(null)}
          action={syncError.reconnect ? <Button color="inherit" size="small" onClick={connectCalendar}>Reconnect</Button> : null}>
          {syncError.message}
        </Alert>
      )}

      <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>Filter</InputLabel>
          <Select value={filter} label="Filter" onChange={e => setFilter(e.target.value)}>
            <MenuItem value="upcoming">Upcoming{counts.upcoming ? ` (${counts.upcoming})` : ''}</MenuItem>
            <MenuItem value="undated">Needs a date{counts.undated ? ` (${counts.undated})` : ''}</MenuItem>
            <MenuItem value="past">Past{counts.past ? ` (${counts.past})` : ''}</MenuItem>
            <MenuItem value="">All</MenuItem>
          </Select>
        </FormControl>
        {groups.length > 1 && (
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Group</InputLabel>
            <Select value={groupFilter} label="Group" onChange={e => setGroupFilter(e.target.value)}>
              <MenuItem value="">All groups</MenuItem>
              {groups.map(g => <MenuItem key={g.id} value={g.id}>{g.group_name || g.id}</MenuItem>)}
            </Select>
          </FormControl>
        )}
        <Box sx={{ flex: 1 }} />
        <Button size="small" variant="contained" startIcon={<Add sx={{ fontSize: 16 }} />} onClick={() => setEditTarget(null)}>
          New meeting
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ textAlign: 'center', py: 6 }}><CircularProgress /></Box>
      ) : visible.length === 0 ? (
        <EmptyState icon="📅"
          title={filter === 'upcoming' ? 'No upcoming meetings.' : 'No meetings here.'}
          body={filter === 'upcoming' && otherCount
            ? `Nothing upcoming — but you have ${otherCount} other meeting${otherCount > 1 ? 's' : ''}. Check "Needs a date" or "Past".`
            : "Meetings Echo spots in your group discussions show up here automatically — including ones it couldn't pin a date on."}
        />
      ) : (
        <Card variant="outlined">
          {visible.map((m, i) => {
            const undated = !m.scheduled_at;
            const past = !undated && new Date(_asUtc(m.scheduled_at)).getTime() < now;
            const gname = groupName(m.source_group_id);
            return (
              <Box key={m.id}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', px: 2, py: 1.25, gap: 1 }}>
                  {undated
                    ? <EventBusy sx={{ fontSize: 17, color: 'warning.main', mt: 0.25, flexShrink: 0 }} />
                    : <EventOutlined sx={{ fontSize: 17, color: past ? 'text.disabled' : 'primary.main', mt: 0.25, flexShrink: 0 }} />}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" fontWeight={500}>{m.title || 'Untitled meeting'}</Typography>
                    <Typography variant="caption" sx={{ color: undated ? 'warning.main' : (past ? 'text.disabled' : 'text.secondary') }}>
                      {undated ? 'No date set — add a date to sync it to Calendar' : `${fmtDateTime(m.scheduled_at, tz)}${past ? ' · past' : ''}`}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 0.75, mt: 0.75, flexWrap: 'wrap', alignItems: 'center' }}>
                      {gname && (
                        <Chip label={gname} size="small" variant="outlined" sx={{ height: 16, fontSize: '0.6rem' }} />
                      )}
                      {Array.isArray(m.participants) && m.participants.length > 0 && (
                        <Chip icon={<PeopleOutline sx={{ fontSize: '0.7rem !important' }} />} label={m.participants.join(', ')}
                          size="small" variant="outlined" sx={{ height: 16, fontSize: '0.6rem' }} />
                      )}
                      {m.meeting_url && (
                        <Chip icon={<VideocamOutlined sx={{ fontSize: '0.7rem !important' }} />} label="Join link"
                          size="small" clickable component="a" href={m.meeting_url} target="_blank" rel="noopener noreferrer"
                          sx={{ height: 16, fontSize: '0.6rem', bgcolor: 'primary.main', color: '#fff', '& .MuiChip-icon': { color: '#fff' } }} />
                      )}
                      {!undated && (
                        cal && cal.connected ? (
                          m.calendar_pushed ? (
                            <Chip icon={<CheckCircleOutline sx={{ fontSize: '0.72rem !important' }} />} label="On Calendar"
                              size="small" sx={{ height: 16, fontSize: '0.6rem', bgcolor: 'success.main', color: '#fff', '& .MuiChip-icon': { color: '#fff' } }} />
                          ) : (
                            <Button size="small" variant="outlined" disabled={syncingId === m.id} onClick={() => syncToCalendar(m)}
                              startIcon={syncingId === m.id ? <CircularProgress size={11} /> : <CalendarToday sx={{ fontSize: 13, color: '#4285f4' }} />}
                              sx={{ fontSize: '0.65rem', borderColor: '#4285f4', color: '#4285f4', py: 0, px: 0.75, minWidth: 0 }}>
                              {syncingId === m.id ? 'Syncing…' : 'Add to Google Calendar'}
                            </Button>
                          )
                        ) : (
                          <Button size="small" component="a" target="_blank" rel="noopener noreferrer"
                            href={gcalUrl({ title: m.title, startIso: m.scheduled_at, description: (m.participants || []).length ? `With: ${m.participants.join(', ')}` : '' })}
                            startIcon={<CalendarToday sx={{ fontSize: 13, color: '#4285f4' }} />}
                            sx={{ fontSize: '0.65rem', borderColor: '#4285f4', color: '#4285f4', py: 0, px: 0.75, minWidth: 0 }} variant="outlined">
                            Add to Calendar
                          </Button>
                        )
                      )}
                    </Box>
                  </Box>
                  <Tooltip title="Edit details">
                    <IconButton size="small" onClick={() => setEditTarget(m)} sx={{ flexShrink: 0 }}>
                      <Edit sx={{ fontSize: 15 }} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Dismiss">
                    <IconButton size="small" onClick={() => setDismissTarget(m)} sx={{ flexShrink: 0 }}>
                      <Delete sx={{ fontSize: 15 }} />
                    </IconButton>
                  </Tooltip>
                </Box>
                {i < visible.length - 1 && <Divider />}
              </Box>
            );
          })}
        </Card>
      )}

      <Dialog open={Boolean(dismissTarget)} onClose={() => setDismissTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Dismiss meeting?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">Remove this meeting from your Hub? It won't be deleted from the original chat.</Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDismissTarget(null)} color="inherit" size="small">Cancel</Button>
          <Button onClick={handleDismiss} variant="contained" color="error" size="small" disabled={dismissLoading}>
            {dismissLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Dismiss
          </Button>
        </DialogActions>
      </Dialog>

      <MeetingModal
        open={editTarget !== undefined}
        meeting={editTarget || null}
        groups={groups}
        botId={botId}
        tz={tz}
        cal={cal}
        onClose={() => setEditTarget(undefined)}
        onSaved={handleSaved}
      />
    </Box>
  );
}

function MeetingModal({ open, meeting, groups, botId, tz, cal, onClose, onSaved }) {
  const [title, setTitle] = useState('');
  const [when, setWhen] = useState('');         // datetime-local wall time in tz
  const [participants, setParticipants] = useState('');
  const [url, setUrl] = useState('');
  const [groupId, setGroupId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;
    if (meeting) {
      setTitle(meeting.title && meeting.title !== 'Meeting' ? meeting.title : '');
      setWhen(utcToLocalInput(meeting.scheduled_at, tz));
      setParticipants(Array.isArray(meeting.participants) ? meeting.participants.join(', ') : '');
      setUrl(meeting.meeting_url || '');
      setGroupId(meeting.source_group_id || '');
    } else {
      setTitle(''); setWhen(''); setParticipants(''); setUrl(''); setGroupId('');
    }
    setError(null);
  }, [meeting, open, tz]);

  const handleSave = async () => {
    if (url && !/^https?:\/\//i.test(url.trim())) { setError('Link must start with http:// or https://'); return; }
    setSaving(true); setError(null);
    const payload = {
      title: title.trim() || 'Meeting',
      scheduled_at: when ? localInputToUtcIso(when, tz) : null,
      participants: participants.split(',').map(s => s.trim()).filter(Boolean),
      meeting_url: url.trim() || null,
      source_group_id: groupId || null,
      ...(botId ? { bot_id: botId } : {}),
    };
    try {
      const r = meeting ? await hub.updateMeeting(meeting.id, payload) : await hub.createMeeting(payload);
      onSaved(r.data);
    } catch (e) {
      setError(e?.response?.data?.error || 'Couldn’t save the meeting. Please try again.');
    } finally { setSaving(false); }
  };

  const willSync = cal && cal.connected && (meeting?.calendar_pushed || cal.auto_sync_meetings);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>{meeting ? 'Edit meeting' : 'New meeting'}
        <IconButton onClick={onClose} size="small" sx={{ position: 'absolute', right: 8, top: 8 }}>✕</IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <TextField label="Title" size="small" fullWidth sx={{ mb: 1.5 }} placeholder="Meeting"
          value={title} onChange={e => setTitle(e.target.value)} inputProps={{ maxLength: 255 }} />
        <TextField label="Date & time" type="datetime-local" size="small" fullWidth sx={{ mb: 0.5 }}
          value={when} onChange={e => setWhen(e.target.value)} InputLabelProps={{ shrink: true }} />
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
          {tz ? `In your timezone (${tz}).` : ''} A date & time is all that’s needed to sync to Google Calendar.
        </Typography>
        <TextField label="Participants (comma-separated)" size="small" fullWidth sx={{ mb: 1.5 }}
          value={participants} onChange={e => setParticipants(e.target.value)} placeholder="Alice, Bob" />
        <TextField label="Join link (optional)" size="small" fullWidth sx={{ mb: 1.5 }}
          value={url} onChange={e => setUrl(e.target.value)} placeholder="https://meet.google.com/…" />
        {groups.length > 0 && (
          <FormControl size="small" fullWidth>
            <InputLabel>Group (optional)</InputLabel>
            <Select value={groupId} label="Group (optional)" onChange={e => setGroupId(e.target.value)}>
              <MenuItem value="">None</MenuItem>
              {groups.map(g => <MenuItem key={g.id} value={g.id}>{g.group_name || g.id}</MenuItem>)}
            </Select>
          </FormControl>
        )}
        {willSync && (
          <Typography variant="caption" color="success.main" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 1.5 }}>
            <CheckCircleOutline sx={{ fontSize: 14 }} />
            {meeting?.calendar_pushed ? 'Changes will update the Google Calendar event.' : 'This will be added to your Google Calendar.'}
          </Typography>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} size="small" color="inherit">Cancel</Button>
        <Button onClick={handleSave} variant="contained" size="small" disabled={saving}>
          {saving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Notes tab ──────────────────────────────────────────────────────────────────
function HubNotes({ groups, botId }) {
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState('');
  const [groupFilter, setGroupFilter] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editNote, setEditNote] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    hub.listNotes({ source: sourceFilter || undefined, group_id: groupFilter || undefined, ...(botId ? { bot_id: botId } : {}) })
      .then(r => setNotes(r.data.notes || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceFilter, groupFilter]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    await hub.deleteNote(deleteTarget.id);
    setDeleteLoading(false);
    setDeleteTarget(null);
    load();
  };

  return (
    <Box sx={{ maxWidth: 700 }}>
      <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Source</InputLabel>
          <Select value={sourceFilter} label="Source" onChange={e => setSourceFilter(e.target.value)}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="manual">Manual</MenuItem>
            <MenuItem value="extracted">AI Extracted</MenuItem>
          </Select>
        </FormControl>
        {groups.length > 1 && (
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Group</InputLabel>
            <Select value={groupFilter} label="Group" onChange={e => setGroupFilter(e.target.value)}>
              <MenuItem value="">All groups</MenuItem>
              {groups.map(g => <MenuItem key={g.id} value={g.id}>{g.group_name || g.id}</MenuItem>)}
            </Select>
          </FormControl>
        )}
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" size="small" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
          New Note
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ textAlign: 'center', py: 6 }}><CircularProgress /></Box>
      ) : notes.length === 0 ? (
        <EmptyState icon="📝" title="No notes yet."
          body="I'll extract them from group discussions. You can also add notes manually."
          action={<Button variant="outlined" size="small" onClick={() => setCreateOpen(true)}>+ New Note</Button>}
        />
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {notes.map(n => (
            <Card key={n.id} variant="outlined">
              <CardContent sx={{ p: '12px !important' }}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{n.content}</Typography>
                    <Box sx={{ display: 'flex', gap: 0.75, mt: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                      <Chip
                        label={n.source === 'extracted' ? 'AI' : 'Manual'}
                        size="small"
                        sx={{ height: 16, fontSize: '0.6rem', bgcolor: n.source === 'extracted' ? 'primary.main' : 'action.selected', color: n.source === 'extracted' ? '#fff' : 'text.primary' }}
                      />
                      {(n.tags || []).map(tag => (
                        <Chip key={tag} label={tag} size="small" variant="outlined" sx={{ height: 16, fontSize: '0.6rem' }} />
                      ))}
                      <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>{fmtDate(n.created_at)}</Typography>
                    </Box>
                  </Box>
                  <Box sx={{ display: 'flex', gap: 0.25, flexShrink: 0 }}>
                    <IconButton size="small" onClick={() => setEditNote(n)}><Edit sx={{ fontSize: 15 }} /></IconButton>
                    <IconButton size="small" onClick={() => setDeleteTarget(n)}><Delete sx={{ fontSize: 15 }} /></IconButton>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          ))}
        </Box>
      )}

      <NoteModal open={createOpen || Boolean(editNote)} note={editNote}
        onClose={() => { setCreateOpen(false); setEditNote(null); }}
        onSaved={() => { setCreateOpen(false); setEditNote(null); load(); }}
        groups={groups} botId={botId}
      />

      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete note?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">Delete this note? This cannot be undone.</Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleteTarget(null)} color="inherit" size="small">Cancel</Button>
          <Button onClick={handleDelete} variant="contained" color="error" size="small" disabled={deleteLoading}>
            {deleteLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Templates tab ──────────────────────────────────────────────────────────────
function HubTemplates({ botId }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTemplate, setEditTemplate] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [error, setError] = useState(null);
  const [limits, setLimits] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([hub.listTemplates(botId || null), hub.getLimits()])
      .then(([tRes, lRes]) => {
        setTemplates(tRes.data.templates || []);
        setLimits(lRes.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);

  const planLimit = limits?.limits?.templates_per_bot ?? 5;
  const unlimited = planLimit === -1;
  const atLimit = !unlimited && templates.length >= planLimit;

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await hub.deleteTemplate(deleteTarget.id);
      setDeleteTarget(null);
      load();
    } catch (e) {
      setError(e?.response?.data?.error || 'Failed to delete.');
    }
    setDeleteLoading(false);
  };

  return (
    <Box sx={{ maxWidth: 700 }}>
      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}

      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 1 }}>
        {!unlimited && (
          <Typography variant="caption" color={atLimit ? 'error.main' : 'text.secondary'} sx={{ flex: 1 }}>
            {templates.length} / {planLimit} templates{atLimit ? ' — limit reached' : ''}
            {atLimit && <Typography component="span" variant="caption" sx={{ ml: 1, color: 'primary.main', cursor: 'pointer' }} onClick={() => window.open('/pricing', '_blank')}>Upgrade</Typography>}
          </Typography>
        )}
        {!atLimit ? (
          <Button variant="contained" size="small" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
            New Template
          </Button>
        ) : (
          <Button variant="outlined" size="small" disabled>New Template</Button>
        )}
      </Box>

      {loading ? (
        <Box sx={{ textAlign: 'center', py: 6 }}><CircularProgress /></Box>
      ) : templates.length === 0 ? (
        <EmptyState icon="📋" title="No templates yet."
          body="Create reusable content blocks and dispatch them into groups with /assist [name]."
          action={<Button variant="outlined" size="small" onClick={() => setCreateOpen(true)}>+ New Template</Button>}
        />
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {templates.map(t => (
            <Card key={t.id} variant="outlined">
              <CardContent sx={{ p: '12px 16px !important' }}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                      <Typography variant="body2" fontWeight={700} sx={{ fontFamily: 'monospace', bgcolor: 'action.selected', px: 0.75, py: 0.25, borderRadius: 0.75, fontSize: '0.78rem' }}>
                        /assist {t.name}
                      </Typography>
                      <Chip
                        label={`Used ${t.use_count} time${t.use_count !== 1 ? 's' : ''}`}
                        size="small"
                        variant="outlined"
                        sx={{ height: 18, fontSize: '0.6rem' }}
                      />
                      {t.last_used_at && (
                        <Typography variant="caption" color="text.secondary">
                          Last used {fmtDate(t.last_used_at)}
                        </Typography>
                      )}
                    </Box>
                    <Typography variant="body2" color="text.secondary"
                      sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', mt: 0.5,
                        display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {t.content}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', gap: 0.25, flexShrink: 0 }}>
                    <IconButton size="small" title="Edit" onClick={() => setEditTemplate(t)}>
                      <Edit sx={{ fontSize: 15 }} />
                    </IconButton>
                    <IconButton size="small" title="Delete" onClick={() => setDeleteTarget(t)}>
                      <Delete sx={{ fontSize: 15 }} />
                    </IconButton>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          ))}
        </Box>
      )}

      <TemplateModal
        open={createOpen || Boolean(editTemplate)}
        template={editTemplate}
        onClose={() => { setCreateOpen(false); setEditTemplate(null); }}
        onSaved={() => { setCreateOpen(false); setEditTemplate(null); load(); }}
        botId={botId}
      />

      {/* Delete confirmation */}
      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete template?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Delete <strong>/assist {deleteTarget?.name}</strong>? This cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleteTarget(null)} size="small" color="inherit">Cancel</Button>
          <Button onClick={handleDelete} variant="contained" color="error" size="small" disabled={deleteLoading}>
            {deleteLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── TemplateModal ──────────────────────────────────────────────────────────────
function TemplateModal({ open, template, onClose, onSaved, botId }) {
  const [name, setName] = useState('');
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) {
      setName(template?.name || '');
      setContent(template?.content || '');
      setError('');
    }
  }, [open, template]);

  async function handleSave() {
    if (!name.trim()) { setError('Name is required.'); return; }
    if (!content.trim()) { setError('Content is required.'); return; }
    setSaving(true);
    setError('');
    try {
      if (template) {
        await hub.updateTemplate(template.id, { name: name.trim(), content: content.trim() });
      } else {
        await hub.createTemplate({ name: name.trim(), content: content.trim(), ...(botId ? { bot_id: botId } : {}) });
      }
      onSaved();
    } catch (e) {
      setError(e?.response?.data?.error || 'Failed to save template.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{template ? 'Edit Template' : 'New Template'}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        <TextField
          label="Template name"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="e.g. standup, agenda, weekly-update"
          helperText='Used as /assist {name} in your group'
          fullWidth
          size="small"
        />
        <TextField
          label="Content"
          value={content}
          onChange={e => setContent(e.target.value)}
          multiline
          minRows={5}
          fullWidth
          size="small"
          placeholder="Enter the template text that will be sent to the group…"
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} color="inherit" size="small">Cancel</Button>
        <Button onClick={handleSave} variant="contained" size="small" disabled={saving}>
          {saving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}
          {template ? 'Save changes' : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Knowledge Cards tab ────────────────────────────────────────────────────────
function HubKnowledge({ botId }) {
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [limits, setLimits] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editCard, setEditCard] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([hub.listKnowledge(botId || null), hub.getLimits()])
      .then(([cRes, lRes]) => {
        setCards(cRes.data.cards || []);
        setLimits(lRes.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);

  const planLimit = limits?.limits?.knowledge_cards_per_bot ?? 10;
  const unlimited = planLimit === -1;
  const atLimit = !unlimited && cards.length >= planLimit;

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await hub.deleteKnowledge(deleteTarget.id);
      setCards(prev => prev.filter(c => c.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch { setError('Delete failed'); }
    finally { setDeleteLoading(false); }
  };

  return (
    <Box sx={{ maxWidth: 700 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Box>
          <Typography variant="subtitle1" fontWeight={700}>Knowledge Cards</Typography>
          <Typography variant="caption" color="text.secondary">
            Answers your bot can give when @mentioned in groups.
            {!unlimited && ` ${cards.length}/${planLimit} used`}
          </Typography>
        </Box>
        <Button
          variant="contained" size="small" startIcon={<Add />}
          disabled={atLimit}
          onClick={() => { setEditCard(null); setModalOpen(true); }}
        >
          New Card
        </Button>
      </Box>

      {atLimit && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Plan limit reached ({planLimit} cards). Upgrade to add more.
        </Alert>
      )}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ textAlign: 'center', py: 6 }}><CircularProgress /></Box>
      ) : cards.length === 0 ? (
        <EmptyState icon="🧠" title="No knowledge cards yet."
          body="Add cards with answers your bot can use when someone @mentions it in a group."
          action={<Button variant="contained" size="small" onClick={() => setModalOpen(true)}>+ Add Card</Button>}
        />
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {cards.map(card => (
            <Card key={card.id} variant="outlined">
              <CardContent sx={{ pb: '12px !important' }}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="subtitle2" fontWeight={700} noWrap>{card.title}</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{
                      mt: 0.5, overflow: 'hidden', display: '-webkit-box',
                      WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                    }}>
                      {card.content}
                    </Typography>
                    {card.tags?.length > 0 && (
                      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 1 }}>
                        {card.tags.map(tag => (
                          <Chip key={tag} label={tag} size="small" variant="outlined" sx={{ height: 18, fontSize: '0.65rem' }} />
                        ))}
                      </Box>
                    )}
                  </Box>
                  <Box sx={{ display: 'flex', gap: 0.5, flexShrink: 0 }}>
                    <Chip label={`${card.use_count} uses`} size="small" sx={{ height: 20, fontSize: '0.65rem' }} />
                    <IconButton size="small" onClick={() => { setEditCard(card); setModalOpen(true); }}>
                      <Edit sx={{ fontSize: 16 }} />
                    </IconButton>
                    <IconButton size="small" color="error" onClick={() => setDeleteTarget(card)}>
                      <Delete sx={{ fontSize: 16 }} />
                    </IconButton>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          ))}
        </Box>
      )}

      <KnowledgeCardModal
        open={modalOpen}
        card={editCard}
        botId={botId}
        onClose={() => { setModalOpen(false); setEditCard(null); }}
        onSaved={(saved) => {
          if (editCard) {
            setCards(prev => prev.map(c => c.id === saved.id ? saved : c));
          } else {
            setCards(prev => [saved, ...prev]);
          }
          setModalOpen(false);
          setEditCard(null);
        }}
      />

      {/* Delete confirmation */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete Knowledge Card?</DialogTitle>
        <DialogContent>
          <Typography>Delete <strong>{deleteTarget?.title}</strong>? This cannot be undone.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button onClick={handleDelete} color="error" disabled={deleteLoading} variant="contained">
            {deleteLoading ? <CircularProgress size={16} /> : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

function KnowledgeCardModal({ open, card, onClose, onSaved, botId }) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      setTitle(card?.title || '');
      setContent(card?.content || '');
      setTagsInput((card?.tags || []).join(', '));
      setError(null);
    }
  }, [open, card]);

  const handleSave = async () => {
    if (!title.trim()) { setError('Title is required'); return; }
    if (!content.trim()) { setError('Content is required'); return; }
    setSaving(true);
    setError(null);
    const tags = tagsInput.split(',').map(t => t.trim()).filter(Boolean);
    try {
      let res;
      if (card) {
        res = await hub.updateKnowledge(card.id, { title, content, tags });
        onSaved(res.data.card);
      } else {
        res = await hub.createKnowledge({ title, content, tags, ...(botId ? { bot_id: botId } : {}) });
        onSaved(res.data.card);
      }
    } catch (e) {
      const detail = e.response?.data?.error;
      setError(detail === 'plan_limit' ? 'Plan limit reached. Upgrade to add more cards.' : 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{card ? 'Edit Knowledge Card' : 'New Knowledge Card'}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '12px !important' }}>
        {error && <Alert severity="error">{error}</Alert>}
        <TextField label="Title" value={title} onChange={e => setTitle(e.target.value)}
          size="small" required inputProps={{ maxLength: 100 }}
          helperText="e.g. Refund Policy, Pricing, Hours" />
        <TextField label="Answer / Content" value={content} onChange={e => setContent(e.target.value)}
          multiline rows={5} size="small" required inputProps={{ maxLength: 2000 }}
          helperText={`${content.length}/2000`} />
        <TextField label="Tags (comma separated)" value={tagsInput} onChange={e => setTagsInput(e.target.value)}
          size="small" helperText="e.g. pricing, support, faq" />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleSave} variant="contained" disabled={saving}>
          {saving ? <CircularProgress size={16} /> : (card ? 'Save' : 'Create')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Automation tab ─────────────────────────────────────────────────────────────
function HubAutomation() {
  const [automations, setAutomations] = useState([]);
  const [digest, setDigest] = useState({ enabled: false, time: '21:00', format: 'compact' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    hub.getAutomations()
      .then(r => {
        setAutomations(r.data.automations || []);
        setDigest(r.data.digest || { enabled: false, time: '21:00', format: 'compact' });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = async (code, value) => {
    setAutomations(prev => prev.map(a => a.code === code ? { ...a, is_enabled: value } : a));
    try {
      await hub.updateAutomations({ automations: { [code]: value } });
    } catch (_) {}
  };

  const handleSaveDigest = async () => {
    setSaving(true);
    try {
      await hub.updateAutomations({ digest });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (_) {}
    setSaving(false);
  };

  if (loading) return <Box sx={{ py: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  return (
    <Box sx={{ maxWidth: 640 }}>
      {/* Daily Digest */}
      <SectionHeader label="Daily Digest" />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Send a daily summary to your Telegram DM
          </Typography>
          <FormControlLabel
            control={<Switch checked={digest.enabled} size="small"
              onChange={e => setDigest(d => ({ ...d, enabled: e.target.checked }))} />}
            label={<Typography variant="body2">{digest.enabled ? 'Enabled' : 'Disabled'}</Typography>}
          />
          {digest.enabled && (
            <Box sx={{ mt: 2, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Time</InputLabel>
                <Select value={digest.time} label="Time" onChange={e => setDigest(d => ({ ...d, time: e.target.value }))}>
                  {['07:00','08:00','09:00','12:00','18:00','20:00','21:00','22:00'].map(t => (
                    <MenuItem key={t} value={t}>{t}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Format</InputLabel>
                <Select value={digest.format} label="Format" onChange={e => setDigest(d => ({ ...d, format: e.target.value }))}>
                  <MenuItem value="compact">Compact</MenuItem>
                  <MenuItem value="detailed">Detailed</MenuItem>
                </Select>
              </FormControl>
            </Box>
          )}
          <Box sx={{ mt: 2 }}>
            <Button variant="outlined" size="small" onClick={handleSaveDigest} disabled={saving}>
              {saved ? '✓ Saved' : saving ? <CircularProgress size={14} /> : 'Save'}
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* Smart Triggers */}
      <SectionHeader label="Smart Triggers" />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent sx={{ pb: '12px !important' }}>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Automated behaviors when specific events are detected
          </Typography>
          {automations.map((a, i) => (
            <Box key={a.code}>
              <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}>
                <Box>
                  <Typography variant="body2" fontWeight={500}>{a.name}</Typography>
                  <Typography variant="caption" color="text.secondary">{a.description}</Typography>
                </Box>
                <Switch checked={a.is_enabled} size="small" sx={{ flexShrink: 0 }}
                  onChange={e => handleToggle(a.code, e.target.checked)} />
              </Box>
              {i < automations.length - 1 && <Divider sx={{ my: 1.5 }} />}
            </Box>
          ))}
        </CardContent>
      </Card>

      {/* Forwarding — Coming V1.5 */}
      <SectionHeader label="Forwarding" />
      <Card variant="outlined" sx={{ borderStyle: 'dashed', borderColor: 'divider', bgcolor: 'transparent' }}>
        <CardContent>
          <Typography variant="body2" color="text.secondary">
            Forward extracted summaries to another Telegram chat — Coming in V1.5
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}

// ── Settings tab ───────────────────────────────────────────────────────────────
// One-time Google Calendar connection + auto-sync, lives in the Settings tab.
function GoogleCalendarSettingsCard() {
  const [cal, setCal] = useState(null);   // {connected, configured, email, auto_sync_meetings}
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    googleCalendar.status()
      .then(r => setCal(r.data))
      .catch(() => setCal({ connected: false, configured: false }));
  }, []);
  useEffect(() => { load(); }, [load]);

  const connect = async () => {
    setBusy(true);
    try { const { data } = await googleCalendar.getAuthUrl(); window.location.href = data.auth_url; }
    catch { setBusy(false); }
  };
  const disconnect = async () => {
    if (!window.confirm('Disconnect Google Calendar? New meetings will stop syncing.')) return;
    setBusy(true);
    try { await googleCalendar.disconnect(); setCal({ connected: false, configured: true }); }
    catch { /* noop */ }
    finally { setBusy(false); }
  };
  const toggleAutoSync = async (val) => {
    setCal(c => ({ ...c, auto_sync_meetings: val }));
    try { await googleCalendar.updateSettings({ auto_sync_meetings: val }); } catch { load(); }
  };

  if (!cal) return <Card variant="outlined" sx={{ mb: 3 }}><CardContent><CircularProgress size={20} /></CardContent></Card>;

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        {!cal.configured ? (
          <Typography variant="body2" color="text.secondary">
            Google Calendar isn't configured on this server yet.
          </Typography>
        ) : cal.connected ? (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1 }}>
              <CheckCircleOutline sx={{ fontSize: 18, color: 'success.main', flexShrink: 0 }} />
              <Typography variant="body2" fontWeight={600}>Connected</Typography>
              {cal.email && <Typography variant="caption" color="text.secondary" noWrap>· {cal.email}</Typography>}
              <Box sx={{ flex: 1 }} />
              <Button size="small" color="error" startIcon={<LinkOff sx={{ fontSize: 15 }} />} onClick={disconnect} disabled={busy}>
                Disconnect
              </Button>
            </Box>
            <FormControlLabel sx={{ mt: 0.5 }}
              control={<Switch size="small" checked={!!cal.auto_sync_meetings} onChange={e => toggleAutoSync(e.target.checked)} />}
              label={<Typography variant="body2">Auto-add new meetings to my Google Calendar</Typography>}
            />
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              One tidy event per meeting, with reminders 1 day / 3 hr / 1 hr / 10 min before. Telegram reminders are sent separately.
            </Typography>
            {cal.last_sync_error && (
              <Alert severity="warning" sx={{ mt: 1.5, fontSize: '0.8rem' }}
                action={cal.last_sync_error.toLowerCase().includes('reconnect')
                  ? <Button color="inherit" size="small" onClick={connect} disabled={busy}>Reconnect</Button>
                  : null}>
                {cal.last_sync_error.replace(/^reconnect_required:\s*/i, '')}
              </Alert>
            )}
          </>
        ) : (
          <>
            <Typography variant="body2" color="text.secondary" mb={1.5}>
              Connect once — meetings Echo finds in your groups are then added to your Google Calendar automatically.
            </Typography>
            <Button variant="contained" size="small" startIcon={<CalendarToday sx={{ fontSize: 15 }} />} onClick={connect} disabled={busy}>
              {busy ? 'Connecting…' : 'Connect Google Calendar'}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function HubSettings({ botData, groups, setGroups, botId = null }) {
  const [, setSettings] = useState(null);
  const [personality, setPersonality] = useState('');
  const [language, setLanguage] = useState('en');
  const [sensitivity, setSensitivity] = useState('standard');
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState(null);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [overlayGroup, setOverlayGroup] = useState(null);
  const [addFlowOpen, setAddFlowOpen] = useState(false);
  const [retention, setRetention] = useState('72');
  const [retentionSaving, setRetentionSaving] = useState(false);
  const [deleteAllOpen, setDeleteAllOpen] = useState(false);
  const [deleteAllConfirm, setDeleteAllConfirm] = useState('');
  const [deleteAllLoading, setDeleteAllLoading] = useState(false);
  const [deleteAllError, setDeleteAllError] = useState(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [memoryCounts, setMemoryCounts] = useState({ people: 0, projects: 0 });
  const [limits, setLimits] = useState(null);
  // Custom bots management
  const [customBots, setCustomBots] = useState([]);
  const [botToDelete, setBotToDelete] = useState(null);
  const [deleteBotConfirm, setDeleteBotConfirm] = useState('');
  const [deleteBotLoading, setDeleteBotLoading] = useState(false);
  const [deleteBotError, setDeleteBotError] = useState(null);

  useEffect(() => {
    hub.getOfficialSettings()
      .then(r => {
        const s = r.data.settings || {};
        setSettings(s);
        setPersonality(s.ai_personality_note || '');
        setLanguage(s.response_language || 'en');
        setSensitivity(s.extraction_sensitivity || 'standard');
        setRetention(String(s.buffer_retention_hours || s.buffer_ttl_hours || 72));
      })
      .catch(() => {});
    // Load memory counts + plan limits
    Promise.all([hub.getLimits(), hub.listMemoryPeople(), hub.listMemoryProjects()])
      .then(([limRes, peopleRes, projectsRes]) => {
        setLimits(limRes.data);
        setMemoryCounts({
          people: (peopleRes.data.people || []).length,
          projects: (projectsRes.data.projects || []).length,
        });
      })
      .catch(() => {});
    // Load custom bots registered in hub
    hub.listBots()
      .then(r => setCustomBots((r.data.bots || []).filter(b => b.bot_type === 'custom')))
      .catch(() => {});
  }, []);

  const handleSaveAI = async () => {
    setSettingsSaving(true); setSettingsError(null); setSettingsSaved(false);
    try {
      await hub.updateOfficialSettings({ ai_personality_note: personality || null, response_language: language, extraction_sensitivity: sensitivity });
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2500);
    } catch (e) { setSettingsError(e?.response?.data?.error || 'Failed to save.'); }
    setSettingsSaving(false);
  };

  const handleRetentionChange = async (val) => {
    setRetention(val); setRetentionSaving(true);
    try { await hub.updateRetention(Number(val)); } catch (_) {}
    setRetentionSaving(false);
  };

  const handleExport = async () => {
    setExportLoading(true);
    try {
      const r = await hub.exportData();
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'hub-export.json'; a.click();
      URL.revokeObjectURL(url);
    } catch (_) {}
    setExportLoading(false);
  };

  const handleDeleteAll = async () => {
    if (deleteAllConfirm !== 'DELETE') return;
    setDeleteAllLoading(true); setDeleteAllError(null);
    try { await hub.deleteAll(); setDeleteAllOpen(false); setGroups([]); }
    catch (e) { setDeleteAllError(e?.response?.data?.error || 'Failed to delete.'); }
    setDeleteAllLoading(false);
  };

  const handleGroupUpdated = (updated) => setGroups(prev => prev.map(g => g.id === updated.id ? { ...g, ...updated } : g));
  const handleGroupDisconnected = (groupId) => setGroups(prev => prev.filter(g => g.id !== groupId));
  const handleGroupConnected = (newGroup) => setGroups(prev => [...prev, newGroup]);

  const handleDeleteBot = async () => {
    if (!botToDelete || deleteBotConfirm !== botToDelete.display_name) return;
    setDeleteBotLoading(true); setDeleteBotError(null);
    try {
      await hub.deleteBot(botToDelete.id);
      setCustomBots(prev => prev.filter(b => b.id !== botToDelete.id));
      setBotToDelete(null); setDeleteBotConfirm('');
    } catch (e) {
      setDeleteBotError(e?.response?.data?.error || 'Failed to delete bot.');
    }
    setDeleteBotLoading(false);
  };

  return (
    <Box sx={{ maxWidth: 640 }}>
      <SectionHeader label="AI Assistant" />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          {settingsError && <Alert severity="error" sx={{ mb: 2 }}>{settingsError}</Alert>}
          {settingsSaved && <Alert severity="success" sx={{ mb: 2 }}>Settings saved.</Alert>}
          <TextField label="Personality Note" multiline rows={3} fullWidth size="small"
            placeholder="e.g. I'm a founder focused on growth. Keep extractions focused on action items and decisions."
            value={personality} inputProps={{ maxLength: 200 }}
            helperText="Max 200 chars · Applied to all extractions for this bot"
            sx={{ mb: 2 }} onChange={e => setPersonality(e.target.value)} />
          <FormControl size="small" fullWidth sx={{ mb: 2 }}>
            <InputLabel>Response Language</InputLabel>
            <Select value={language} label="Response Language" onChange={e => setLanguage(e.target.value)}>
              <MenuItem value="en">English</MenuItem>
              <MenuItem value="ar">Arabic</MenuItem>
              <MenuItem value="es">Spanish</MenuItem>
              <MenuItem value="fr">French</MenuItem>
            </Select>
          </FormControl>
          <Typography variant="body2" fontWeight={500} gutterBottom>Extraction Sensitivity</Typography>
          <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
            {['minimal', 'standard', 'aggressive'].map(v => (
              <Button key={v} size="small" variant={sensitivity === v ? 'contained' : 'outlined'}
                sx={{ textTransform: 'capitalize' }} onClick={() => setSensitivity(v)}>{v}</Button>
            ))}
          </Box>
          <Button variant="contained" size="small" onClick={handleSaveAI} disabled={settingsSaving}>
            {settingsSaving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Save AI Settings
          </Button>
        </CardContent>
      </Card>

      <SectionHeader label="Google Calendar" />
      <GoogleCalendarSettingsCard />

      <SectionHeader label="Connected Groups" />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          {groups.length === 0 ? (
            <Typography variant="body2" color="text.secondary" mb={1.5}>No groups connected yet.</Typography>
          ) : (
            groups.map((g, i) => (
              <Box key={g.id}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', py: 0.75 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
                    <Box sx={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, bgcolor: g.is_active ? 'success.main' : 'text.disabled' }} />
                    <Typography variant="body2" noWrap>{g.display_name || g.group_name || `Group ${g.telegram_group_id}`}</Typography>
                    {g.pause_reason === 'plan_limit' && <Chip label="Plan limit" size="small" sx={{ height: 16, fontSize: '0.6rem', bgcolor: 'warning.main', color: '#fff', flexShrink: 0 }} />}
                    {!g.is_active && g.pause_reason !== 'plan_limit' && <Chip label="Paused" size="small" sx={{ height: 16, fontSize: '0.6rem', flexShrink: 0 }} />}
                  </Box>
                  <Button size="small" variant="outlined" sx={{ fontSize: '0.72rem', flexShrink: 0, ml: 1 }} onClick={() => setOverlayGroup(g)}>
                    Settings
                  </Button>
                </Box>
                {i < groups.length - 1 && <Divider />}
              </Box>
            ))
          )}
          <Button variant="outlined" size="small" startIcon={<span style={{ fontSize: '1rem', lineHeight: 1 }}>+</span>}
            sx={{ mt: groups.length > 0 ? 1.5 : 0 }} onClick={() => setAddFlowOpen(true)}>
            Add to Group
          </Button>
        </CardContent>
      </Card>

      <SectionHeader label="Memory" />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="body2" color="text.secondary" mb={1.5}>
            Global memory is shared across all your bots and injected into every extraction.
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, mb: 1.5, flexWrap: 'wrap' }}>
            <Box>
              <Typography variant="caption" color="text.secondary">People</Typography>
              <Typography variant="body2" fontWeight={500}>
                {memoryCounts.people}
                {limits && limits.limits?.memory_people !== -1 && (
                  <Typography component="span" variant="caption" color={memoryCounts.people >= (limits.limits?.memory_people || 5) ? 'error.main' : 'text.secondary'}>
                    {' '}/ {limits.limits?.memory_people}
                  </Typography>
                )}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Projects</Typography>
              <Typography variant="body2" fontWeight={500}>
                {memoryCounts.projects}
                {limits && limits.limits?.memory_projects !== -1 && (
                  <Typography component="span" variant="caption" color={memoryCounts.projects >= (limits.limits?.memory_projects || 3) ? 'error.main' : 'text.secondary'}>
                    {' '}/ {limits.limits?.memory_projects}
                  </Typography>
                )}
              </Typography>
            </Box>
          </Box>
          <Button variant="outlined" size="small" onClick={() => setMemoryOpen(true)}>Edit Memory →</Button>
        </CardContent>
      </Card>

      {customBots.length > 0 && (
        <>
          <SectionHeader label="Custom Bots" />
          <Card variant="outlined" sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="body2" color="text.secondary" mb={1.5}>
                Custom bots registered in your hub. Deleting removes the integration and stops the bot.
              </Typography>
              {customBots.map((bot, i) => (
                <Box key={bot.id}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', py: 0.75 }}>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="body2" noWrap fontWeight={500}>{bot.display_name || `Bot ${bot.id}`}</Typography>
                      <Typography variant="caption" color="text.secondary">@{bot.telegram_bot_username || '—'}</Typography>
                      {bot.custom_bot_id && (
                        <Chip
                          label="Also in Group Management"
                          size="small"
                          color="primary"
                          variant="outlined"
                          sx={{ mt: 0.5, fontSize: '0.7rem', display: 'block', width: 'fit-content' }}
                        />
                      )}
                    </Box>
                    <Button size="small" color="error" variant="outlined" sx={{ fontSize: '0.72rem', flexShrink: 0, ml: 1 }}
                      onClick={() => { setBotToDelete(bot); setDeleteBotConfirm(''); setDeleteBotError(null); }}>
                      Delete
                    </Button>
                  </Box>
                  {i < customBots.length - 1 && <Divider />}
                </Box>
              ))}
            </CardContent>
          </Card>
        </>
      )}

      <SectionHeader label="Notifications" />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <FormControlLabel control={<Switch defaultChecked size="small" />}
            label={<Typography variant="body2">Telegram DM alerts</Typography>} />
        </CardContent>
      </Card>

      <SectionHeader label="Privacy & Data" />
      <Card variant="outlined">
        <CardContent>
          <FormControl size="small" sx={{ mb: 2, minWidth: 180 }}>
            <InputLabel>Message retention</InputLabel>
            <Select value={retention} label="Message retention" disabled={retentionSaving}
              onChange={e => handleRetentionChange(e.target.value)}>
              <MenuItem value="24">24 hours</MenuItem>
              <MenuItem value="48">48 hours</MenuItem>
              <MenuItem value="72">72 hours</MenuItem>
            </Select>
            <FormHelperText>Raw message buffer TTL{retentionSaving ? ' — saving…' : ''}</FormHelperText>
          </FormControl>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Button variant="outlined" size="small" onClick={handleExport} disabled={exportLoading}>
              {exportLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Export data
            </Button>
            <Button variant="outlined" size="small" color="error" onClick={() => setDeleteAllOpen(true)}>Delete all data</Button>
          </Box>
        </CardContent>
      </Card>

      <AddToGroupFlow open={addFlowOpen} onClose={() => setAddFlowOpen(false)} onGroupConnected={handleGroupConnected}
        botId={botId} botUsername={botData?.telegram_bot_username || null} />
      <GroupSettingsOverlay open={Boolean(overlayGroup)} group={overlayGroup} onClose={() => setOverlayGroup(null)}
        onUpdated={handleGroupUpdated} onDisconnected={handleGroupDisconnected} />
      <MemoryOverlay
        open={memoryOpen}
        onClose={() => {
          setMemoryOpen(false);
          // Refresh counts after closing
          Promise.all([hub.listMemoryPeople(), hub.listMemoryProjects()])
            .then(([pRes, prRes]) => setMemoryCounts({
              people: (pRes.data.people || []).length,
              projects: (prRes.data.projects || []).length,
            })).catch(() => {});
        }}
        limits={limits}
      />

      <Dialog open={deleteAllOpen} onClose={() => setDeleteAllOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete all Hub data?</DialogTitle>
        <DialogContent>
          {deleteAllError && <Alert severity="error" sx={{ mb: 2 }}>{deleteAllError}</Alert>}
          <Typography variant="body2" color="text.secondary" mb={2}>
            This permanently deletes all digests, tasks, reminders, notes, decisions, meetings, and memory records.
          </Typography>
          <TextField label='Type "DELETE" to confirm' size="small" fullWidth
            value={deleteAllConfirm} onChange={e => setDeleteAllConfirm(e.target.value)} />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => { setDeleteAllOpen(false); setDeleteAllConfirm(''); }} size="small" color="inherit">Cancel</Button>
          <Button onClick={handleDeleteAll} variant="contained" color="error" size="small"
            disabled={deleteAllConfirm !== 'DELETE' || deleteAllLoading}>
            {deleteAllLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Delete all
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(botToDelete)} onClose={() => setBotToDelete(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete {botToDelete?.display_name || 'this bot'}?</DialogTitle>
        <DialogContent>
          {deleteBotError && <Alert severity="error" sx={{ mb: 2 }}>{deleteBotError}</Alert>}
          <Typography variant="body2" color="text.secondary" mb={2}>
            This permanently removes the bot integration, stops the webhook, and cannot be undone.
            The bot will stop responding in all linked groups.
          </Typography>
          <TextField
            label={`Type "${botToDelete?.display_name || 'the bot name'}" to confirm`}
            size="small" fullWidth
            value={deleteBotConfirm}
            onChange={e => setDeleteBotConfirm(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setBotToDelete(null)} size="small" color="inherit">Cancel</Button>
          <Button onClick={handleDeleteBot} variant="contained" color="error" size="small"
            disabled={deleteBotConfirm !== (botToDelete?.display_name || '') || deleteBotLoading}>
            {deleteBotLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Delete Bot
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Create/Edit Modals ─────────────────────────────────────────────────────────

function TaskModal({ open, task, onClose, onSaved, groups, botId }) {
  const [title, setTitle] = useState('');
  const [assignee, setAssignee] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [priority, setPriority] = useState('normal');
  const [groupId, setGroupId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (task) {
      setTitle(task.title || '');
      setAssignee(task.assignee_name || '');
      setDueDate(task.due_date || '');
      setPriority(task.priority || 'normal');
      setGroupId(task.source_group_id || '');
    } else {
      setTitle(''); setAssignee(''); setDueDate(''); setPriority('normal'); setGroupId('');
    }
    setError(null);
  }, [task, open]);

  const handleSave = async () => {
    if (!title.trim()) { setError('Title is required'); return; }
    setSaving(true); setError(null);
    try {
      const data = { title: title.trim(), assignee_name: assignee || null, due_date: dueDate || null, priority, source_group_id: groupId || null, ...(botId ? { bot_id: botId } : {}) };
      if (task) { await hub.updateTask(task.id, data); }
      else { await hub.createTask(data); }
      onSaved();
    } catch (e) { setError(e?.response?.data?.error || 'Failed to save.'); }
    setSaving(false);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>{task ? 'Edit Task' : 'New Task'}
        <IconButton onClick={onClose} size="small" sx={{ position: 'absolute', right: 8, top: 8 }}>✕</IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <TextField label="Title" size="small" fullWidth sx={{ mb: 1.5 }} value={title} onChange={e => setTitle(e.target.value)} inputProps={{ maxLength: 500 }} />
        <TextField label="Assignee" size="small" fullWidth sx={{ mb: 1.5 }} value={assignee} onChange={e => setAssignee(e.target.value)} />
        <TextField label="Due date" type="date" size="small" fullWidth sx={{ mb: 1.5 }} value={dueDate} onChange={e => setDueDate(e.target.value)} InputLabelProps={{ shrink: true }} />
        <FormControl size="small" fullWidth sx={{ mb: 1.5 }}>
          <InputLabel>Priority</InputLabel>
          <Select value={priority} label="Priority" onChange={e => setPriority(e.target.value)}>
            <MenuItem value="low">Low</MenuItem>
            <MenuItem value="normal">Normal</MenuItem>
            <MenuItem value="high">High</MenuItem>
          </Select>
        </FormControl>
        {groups.length > 0 && (
          <FormControl size="small" fullWidth>
            <InputLabel>Group (optional)</InputLabel>
            <Select value={groupId} label="Group (optional)" onChange={e => setGroupId(e.target.value)}>
              <MenuItem value="">None</MenuItem>
              {groups.map(g => <MenuItem key={g.id} value={g.id}>{g.group_name || g.id}</MenuItem>)}
            </Select>
          </FormControl>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} size="small" color="inherit">Cancel</Button>
        <Button onClick={handleSave} variant="contained" size="small" disabled={saving}>
          {saving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ReminderModal({ open, reminder, onClose, onSaved, groups, botId }) {
  const [content, setContent] = useState('');
  const [remindAt, setRemindAt] = useState('');
  const [groupId, setGroupId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (reminder) {
      setContent(reminder.content || '');
      setRemindAt(reminder.remind_at ? reminder.remind_at.slice(0, 16) : '');
      setGroupId(reminder.source_group_id || '');
    } else {
      setContent(''); setRemindAt(''); setGroupId('');
    }
    setError(null);
  }, [reminder, open]);

  const handleSave = async () => {
    if (!content.trim() || !remindAt) { setError('Content and remind time are required'); return; }
    setSaving(true); setError(null);
    try {
      const data = { content: content.trim(), remind_at: new Date(remindAt).toISOString(), source_group_id: groupId || null, ...(botId ? { bot_id: botId } : {}) };
      if (reminder) { await hub.updateReminder(reminder.id, data); }
      else { await hub.createReminder(data); }
      onSaved();
    } catch (e) { setError(e?.response?.data?.error || 'Failed to save.'); }
    setSaving(false);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>{reminder ? 'Edit Reminder' : 'New Reminder'}
        <IconButton onClick={onClose} size="small" sx={{ position: 'absolute', right: 8, top: 8 }}>✕</IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <TextField label="What to remind?" size="small" fullWidth sx={{ mb: 1.5 }} multiline rows={2}
          value={content} onChange={e => setContent(e.target.value)} inputProps={{ maxLength: 500 }} />
        <TextField label="Remind at" type="datetime-local" size="small" fullWidth sx={{ mb: 1.5 }}
          value={remindAt} onChange={e => setRemindAt(e.target.value)} InputLabelProps={{ shrink: true }} />
        {groups.length > 0 && (
          <FormControl size="small" fullWidth>
            <InputLabel>Group (optional)</InputLabel>
            <Select value={groupId} label="Group (optional)" onChange={e => setGroupId(e.target.value)}>
              <MenuItem value="">None</MenuItem>
              {groups.map(g => <MenuItem key={g.id} value={g.id}>{g.group_name || g.id}</MenuItem>)}
            </Select>
          </FormControl>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} size="small" color="inherit">Cancel</Button>
        <Button onClick={handleSave} variant="contained" size="small" disabled={saving}>
          {saving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function NoteModal({ open, note, onClose, onSaved, groups, botId }) {
  const [content, setContent] = useState('');
  const [tags, setTags] = useState('');
  const [groupId, setGroupId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (note) {
      setContent(note.content || '');
      setTags((note.tags || []).join(', '));
      setGroupId(note.source_group_id || '');
    } else {
      setContent(''); setTags(''); setGroupId('');
    }
    setError(null);
  }, [note, open]);

  const handleSave = async () => {
    if (!content.trim()) { setError('Content is required'); return; }
    setSaving(true); setError(null);
    try {
      const parsedTags = tags.split(',').map(t => t.trim()).filter(Boolean);
      const data = { content: content.trim(), tags: parsedTags, source_group_id: groupId || null, ...(botId ? { bot_id: botId } : {}) };
      if (note) { await hub.updateNote(note.id, data); }
      else { await hub.createNote(data); }
      onSaved();
    } catch (e) { setError(e?.response?.data?.error || 'Failed to save.'); }
    setSaving(false);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>{note ? 'Edit Note' : 'New Note'}
        <IconButton onClick={onClose} size="small" sx={{ position: 'absolute', right: 8, top: 8 }}>✕</IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <TextField label="Note" size="small" fullWidth multiline rows={4} sx={{ mb: 1.5 }}
          value={content} onChange={e => setContent(e.target.value)} inputProps={{ maxLength: 2000 }} />
        <TextField label="Tags (comma separated)" size="small" fullWidth sx={{ mb: 1.5 }}
          value={tags} onChange={e => setTags(e.target.value)} placeholder="decision, action, link" />
        {groups.length > 0 && (
          <FormControl size="small" fullWidth>
            <InputLabel>Group (optional)</InputLabel>
            <Select value={groupId} label="Group (optional)" onChange={e => setGroupId(e.target.value)}>
              <MenuItem value="">None</MenuItem>
              {groups.map(g => <MenuItem key={g.id} value={g.id}>{g.group_name || g.id}</MenuItem>)}
            </Select>
          </FormControl>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} size="small" color="inherit">Cancel</Button>
        <Button onClick={handleSave} variant="contained" size="small" disabled={saving}>
          {saving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Shared helpers ─────────────────────────────────────────────────────────────
function SectionHeader({ label }) {
  return (
    <Typography variant="caption" fontWeight={700} color="text.disabled"
      sx={{ display: 'block', mb: 1, textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: '0.68rem' }}>
      {label}
    </Typography>
  );
}

function EmptyState({ icon, title, body, action }) {
  return (
    <Box sx={{ textAlign: 'center', py: 8, maxWidth: 440, mx: 'auto' }}>
      {icon && <Typography fontSize="2.5rem" mb={1.5}>{icon}</Typography>}
      <Typography variant="body1" fontWeight={600} gutterBottom>{title}</Typography>
      {body && <Typography variant="body2" color="text.secondary" mb={action ? 3 : 0}>{body}</Typography>}
      {action}
    </Box>
  );
}

// ── MemoryOverlay ──────────────────────────────────────────────────────────────
function MemoryOverlay({ open, onClose, limits }) {
  const [activeSection, setActiveSection] = useState('global');
  const [globalData, setGlobalData] = useState({ preferred_name: '', company_name: '', role: '', timezone: 'UTC', current_priorities: [], free_notes: '' });
  const [people, setPeople] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [editPerson, setEditPerson] = useState(null);
  const [editProject, setEditProject] = useState(null);
  const [personFormOpen, setPersonFormOpen] = useState(false);
  const [projectFormOpen, setProjectFormOpen] = useState(false);
  const [prioritiesText, setPrioritiesText] = useState('');

  const planPeopleLimit = limits?.limits?.memory_people ?? 5;
  const planProjectsLimit = limits?.limits?.memory_projects ?? 3;
  const unlimitedPeople = planPeopleLimit === -1;
  const unlimitedProjects = planProjectsLimit === -1;

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError('');
    Promise.all([hub.getMemoryGlobal(), hub.listMemoryPeople(), hub.listMemoryProjects()])
      .then(([gRes, pRes, prRes]) => {
        const g = gRes.data.global || {};
        setGlobalData({
          preferred_name: g.preferred_name || '',
          company_name: g.company_name || '',
          role: g.role || '',
          timezone: g.timezone || 'UTC',
          current_priorities: g.current_priorities || [],
          free_notes: g.free_notes || '',
        });
        setPrioritiesText((g.current_priorities || []).join('\n'));
        setPeople(pRes.data.people || []);
        setProjects(prRes.data.projects || []);
      })
      .catch(() => setError('Failed to load memory.'))
      .finally(() => setLoading(false));
  }, [open]);

  const handleSaveGlobal = async () => {
    setSaving(true); setError('');
    try {
      const priorities = prioritiesText.split('\n').map(s => s.trim()).filter(Boolean);
      await hub.updateMemoryGlobal({ ...globalData, current_priorities: priorities });
    } catch (e) { setError(e?.response?.data?.error || 'Failed to save.'); }
    setSaving(false);
  };

  const handleDeletePerson = async (id) => {
    await hub.deleteMemoryPerson(id);
    setPeople(prev => prev.filter(p => p.id !== id));
  };

  const handleDeleteProject = async (id) => {
    await hub.deleteMemoryProject(id);
    setProjects(prev => prev.filter(p => p.id !== id));
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{ sx: { height: '80vh', maxHeight: 640 } }}>
      <DialogTitle>
        Memory
        <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
          Injected into every AI extraction
        </Typography>
      </DialogTitle>
      <DialogContent dividers sx={{ display: 'flex', p: 0, overflow: 'hidden' }}>
        {/* Left nav */}
        <Box sx={{ width: 150, flexShrink: 0, borderRight: '1px solid', borderColor: 'divider', py: 1 }}>
          {[['global', 'Context'], ['people', 'People'], ['projects', 'Projects']].map(([k, label]) => (
            <Box key={k} onClick={() => setActiveSection(k)} sx={{
              px: 2, py: 1, cursor: 'pointer', fontSize: '0.85rem', fontWeight: activeSection === k ? 600 : 400,
              bgcolor: activeSection === k ? 'action.selected' : 'transparent',
              '&:hover': { bgcolor: 'action.hover' },
            }}>
              {label}
            </Box>
          ))}
        </Box>

        {/* Right content */}
        <Box sx={{ flex: 1, overflow: 'auto', p: 2.5 }}>
          {loading ? (
            <Box sx={{ textAlign: 'center', pt: 6 }}><CircularProgress /></Box>
          ) : error ? (
            <Alert severity="error">{error}</Alert>
          ) : activeSection === 'global' ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Tell the assistant who you are and what matters to you. This context is included in every extraction prompt.
              </Typography>
              <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
                <TextField label="Your name" size="small" sx={{ flex: 1, minWidth: 140 }} value={globalData.preferred_name}
                  onChange={e => setGlobalData(p => ({ ...p, preferred_name: e.target.value }))} />
                <TextField label="Company" size="small" sx={{ flex: 1, minWidth: 140 }} value={globalData.company_name}
                  onChange={e => setGlobalData(p => ({ ...p, company_name: e.target.value }))} />
              </Box>
              <TextField label="Your role" size="small" fullWidth value={globalData.role}
                onChange={e => setGlobalData(p => ({ ...p, role: e.target.value }))} />
              <Box>
                <TimezoneSelect label="Timezone" value={globalData.timezone}
                  onChange={(val) => setGlobalData(p => ({ ...p, timezone: val }))} />
                <FormHelperText>
                  Drives how Echo reads times like "in 1 hour" and how meetings, reminders,
                  digests and Google Calendar events are shown.
                </FormHelperText>
              </Box>
              <TextField label="Current priorities (one per line)" multiline minRows={3} size="small" fullWidth
                value={prioritiesText} onChange={e => setPrioritiesText(e.target.value)}
                helperText="e.g. Product launch Q3, Hiring engineering lead" />
              <TextField label="Free notes" multiline minRows={2} size="small" fullWidth value={globalData.free_notes}
                onChange={e => setGlobalData(p => ({ ...p, free_notes: e.target.value }))}
                inputProps={{ maxLength: 500 }} helperText="Max 500 chars" />
              <Box>
                <Button variant="contained" size="small" onClick={handleSaveGlobal} disabled={saving}>
                  {saving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Save context
                </Button>
              </Box>
            </Box>
          ) : activeSection === 'people' ? (
            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  People the assistant should know about.
                  {!unlimitedPeople && ` ${people.length} / ${planPeopleLimit}`}
                </Typography>
                <Button variant="outlined" size="small" startIcon={<Add />}
                  disabled={!unlimitedPeople && people.length >= planPeopleLimit}
                  onClick={() => { setEditPerson(null); setPersonFormOpen(true); }}>
                  Add person
                </Button>
              </Box>
              {!unlimitedPeople && people.length >= planPeopleLimit && (
                <Alert severity="warning" sx={{ mb: 2 }}>Plan limit reached. Upgrade to add more people.</Alert>
              )}
              {people.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No people saved yet.</Typography>
              ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {people.map(p => (
                    <Box key={p.id} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.75, px: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2" fontWeight={500}>{p.name}</Typography>
                        {p.role && <Typography variant="caption" color="text.secondary">{p.role}</Typography>}
                      </Box>
                      <IconButton size="small" onClick={() => { setEditPerson(p); setPersonFormOpen(true); }}><Edit sx={{ fontSize: 14 }} /></IconButton>
                      <IconButton size="small" onClick={() => handleDeletePerson(p.id)}><Delete sx={{ fontSize: 14 }} /></IconButton>
                    </Box>
                  ))}
                </Box>
              )}
              <PersonFormDialog
                open={personFormOpen}
                person={editPerson}
                onClose={() => setPersonFormOpen(false)}
                onSaved={(saved) => {
                  if (editPerson) {
                    setPeople(prev => prev.map(p => p.id === saved.id ? saved : p));
                  } else {
                    setPeople(prev => [...prev, saved]);
                  }
                  setPersonFormOpen(false);
                }}
              />
            </Box>
          ) : (
            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Active projects the assistant should be aware of.
                  {!unlimitedProjects && ` ${projects.length} / ${planProjectsLimit}`}
                </Typography>
                <Button variant="outlined" size="small" startIcon={<Add />}
                  disabled={!unlimitedProjects && projects.length >= planProjectsLimit}
                  onClick={() => { setEditProject(null); setProjectFormOpen(true); }}>
                  Add project
                </Button>
              </Box>
              {!unlimitedProjects && projects.length >= planProjectsLimit && (
                <Alert severity="warning" sx={{ mb: 2 }}>Plan limit reached. Upgrade to add more projects.</Alert>
              )}
              {projects.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No projects saved yet.</Typography>
              ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {projects.map(pj => (
                    <Box key={pj.id} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.75, px: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2" fontWeight={500}>{pj.name}</Typography>
                        {pj.status && <Typography variant="caption" color="text.secondary">{pj.status}</Typography>}
                        {pj.deadline && <Typography variant="caption" color="text.secondary" sx={{ ml: pj.status ? 1 : 0 }}>· Due {pj.deadline}</Typography>}
                      </Box>
                      <IconButton size="small" onClick={() => { setEditProject(pj); setProjectFormOpen(true); }}><Edit sx={{ fontSize: 14 }} /></IconButton>
                      <IconButton size="small" onClick={() => handleDeleteProject(pj.id)}><Delete sx={{ fontSize: 14 }} /></IconButton>
                    </Box>
                  ))}
                </Box>
              )}
              <ProjectFormDialog
                open={projectFormOpen}
                project={editProject}
                onClose={() => setProjectFormOpen(false)}
                onSaved={(saved) => {
                  if (editProject) {
                    setProjects(prev => prev.map(p => p.id === saved.id ? saved : p));
                  } else {
                    setProjects(prev => [...prev, saved]);
                  }
                  setProjectFormOpen(false);
                }}
              />
            </Box>
          )}
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} size="small">Done</Button>
      </DialogActions>
    </Dialog>
  );
}

function PersonFormDialog({ open, person, onClose, onSaved }) {
  const [name, setName] = useState('');
  const [role, setRole] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) {
      setName(person?.name || '');
      setRole(person?.role || '');
      setNotes(person?.notes || '');
      setError('');
    }
  }, [open, person]);

  const handleSave = async () => {
    if (!name.trim()) { setError('Name is required.'); return; }
    setSaving(true); setError('');
    try {
      let res;
      if (person) {
        res = await hub.updateMemoryPerson(person.id, { name: name.trim(), role: role.trim() || null, notes: notes.trim() || null });
        onSaved(res.data.person);
      } else {
        res = await hub.createMemoryPerson({ name: name.trim(), role: role.trim() || null, notes: notes.trim() || null });
        onSaved(res.data.person);
      }
    } catch (e) { setError(e?.response?.data?.error || 'Failed to save.'); }
    setSaving(false);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{person ? 'Edit person' : 'Add person'}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: '12px !important' }}>
        {error && <Alert severity="error">{error}</Alert>}
        <TextField label="Name" size="small" fullWidth value={name} onChange={e => setName(e.target.value)} />
        <TextField label="Role" size="small" fullWidth value={role} onChange={e => setRole(e.target.value)} placeholder="e.g. CTO, Client, Investor" />
        <TextField label="Notes" size="small" fullWidth multiline minRows={2} value={notes} onChange={e => setNotes(e.target.value)} />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} color="inherit" size="small">Cancel</Button>
        <Button onClick={handleSave} variant="contained" size="small" disabled={saving}>
          {saving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ProjectFormDialog({ open, project, onClose, onSaved }) {
  const [name, setName] = useState('');
  const [status, setStatus] = useState('');
  const [contextNotes, setContextNotes] = useState('');
  const [deadline, setDeadline] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) {
      setName(project?.name || '');
      setStatus(project?.status || '');
      setContextNotes(project?.context_notes || '');
      setDeadline(project?.deadline || '');
      setError('');
    }
  }, [open, project]);

  const handleSave = async () => {
    if (!name.trim()) { setError('Name is required.'); return; }
    setSaving(true); setError('');
    try {
      const payload = { name: name.trim(), status: status.trim() || null, context_notes: contextNotes.trim() || null, deadline: deadline || null };
      let res;
      if (project) {
        res = await hub.updateMemoryProject(project.id, payload);
        onSaved(res.data.project);
      } else {
        res = await hub.createMemoryProject(payload);
        onSaved(res.data.project);
      }
    } catch (e) { setError(e?.response?.data?.error || 'Failed to save.'); }
    setSaving(false);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{project ? 'Edit project' : 'Add project'}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: '12px !important' }}>
        {error && <Alert severity="error">{error}</Alert>}
        <TextField label="Project name" size="small" fullWidth value={name} onChange={e => setName(e.target.value)} />
        <FormControl size="small" fullWidth>
          <InputLabel>Status</InputLabel>
          <Select value={status} label="Status" onChange={e => setStatus(e.target.value)}>
            <MenuItem value="">None</MenuItem>
            <MenuItem value="active">Active</MenuItem>
            <MenuItem value="in progress">In Progress</MenuItem>
            <MenuItem value="on hold">On Hold</MenuItem>
            <MenuItem value="completed">Completed</MenuItem>
          </Select>
        </FormControl>
        <TextField label="Context notes" size="small" fullWidth multiline minRows={2} value={contextNotes} onChange={e => setContextNotes(e.target.value)} />
        <TextField label="Deadline" type="date" size="small" fullWidth value={deadline} onChange={e => setDeadline(e.target.value)} InputLabelProps={{ shrink: true }} />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} color="inherit" size="small">Cancel</Button>
        <Button onClick={handleSave} variant="contained" size="small" disabled={saving}>
          {saving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── OnboardingFlow ─────────────────────────────────────────────────────────────
function OnboardingFlow({ open, onClose }) {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);

  useEffect(() => { if (open) setStep(0); }, [open]);

  const steps = [
    {
      emoji: '👋',
      title: 'Welcome to Echo',
      body: 'Your AI-powered team memory. Connect a Telegram group and the assistant will quietly extract tasks, reminders, decisions, and meetings from every conversation — automatically.',
    },
    {
      emoji: '🧠',
      title: 'Give it context',
      body: 'Tell the assistant who you are and what projects you\'re working on. The more context it has, the more accurate the extractions. You can update this anytime in Settings → Memory.',
    },
    {
      emoji: '📡',
      title: 'Connect your first group',
      body: 'Add the official Telegizer bot to a Telegram group. It will send you a consent message before starting to observe. You can pause or disconnect at any time.',
    },
    {
      emoji: '✅',
      title: "You're all set",
      body: 'Once your first group is connected, items will start appearing in Tasks, Reminders, and Notes within a few minutes of activity. Check the Overview tab anytime.',
    },
  ];

  const current = steps[step];
  const isLast = step === steps.length - 1;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogContent sx={{ textAlign: 'center', pt: 4, pb: 2 }}>
        <Typography fontSize="3rem" mb={2}>{current.emoji}</Typography>
        <Typography variant="h6" fontWeight={700} gutterBottom>{current.title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3, lineHeight: 1.7 }}>{current.body}</Typography>
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.75, mb: 1 }}>
          {steps.map((_, i) => (
            <Box key={i} sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: i === step ? 'primary.main' : 'divider', transition: 'background 0.2s' }} />
          ))}
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3, justifyContent: 'space-between' }}>
        <Button onClick={onClose} color="inherit" size="small">Skip</Button>
        <Button
          variant="contained" size="small"
          onClick={() => {
            if (isLast) {
              onClose();
              navigate('/ark/official/settings');
            } else {
              setStep(s => s + 1);
            }
          }}
        >
          {isLast ? 'Go to Settings' : 'Next'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}


