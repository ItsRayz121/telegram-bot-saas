import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Typography, Tabs, Tab, Grid, Avatar, Stack,
  List, ListItem, ListItemText, Chip, CircularProgress, Alert, Button,
  IconButton, Tooltip,
} from '@mui/material';
import {
  ArrowBack, Save, Schedule, Shield, People, Forum as ForumIcon,
  SmartToy, Bolt, Assessment, Settings as SettingsIcon, Refresh,
} from '@mui/icons-material';
import guildizerApi from '../../services/guildizerApi';
import { GuildizerUiPrefsProvider } from '../../context/GuildizerUiPrefsContext';
import GuildizerCollapsibleCard from '../../components/guildizer/GuildizerCollapsibleCard';
import { SaveBarContext } from './tabs/saveBar';
import SettingsTab from './tabs/SettingsTab';
import CommandsTab from './tabs/CommandsTab';
import ProtectionTab from './tabs/ProtectionTab';
import LevelingTab from './tabs/LevelingTab';
import CampaignsTab from './tabs/CampaignsTab';
import BillingTab from './tabs/BillingTab';
import MembersTab from './tabs/MembersTab';
import AnalyticsTab from './tabs/AnalyticsTab';
import TeamTab from './tabs/TeamTab';
import {
  SchedulerSubtab, AutoReplySubtab, PollsSubtab, ForwardingSubtab,
  WorkflowsSubtab, WebhooksSubtab, ThreadsSubtab,
} from './tabs/AutomationSubtabs';
import {
  RaidsSubtab, InviteLinksSubtab, TicketsSubtab, StarboardSubtab, BoostsSubtab,
  EventsSubtab,
} from './tabs/EngagementSubtabs';
import { KnowledgeBaseSubtab } from './tabs/AiSubtabs';
import SelfRolesSubtab from './tabs/SelfRolesSubtab';
import {
  LeaderboardSubtab, AuditLogSubtab, WarningsSubtab, DigestSubtab, AIActivitySubtab,
} from './tabs/AnalyticsSubtabs';

// Discord channel type enum → label (common ones).
const CHANNEL_TYPES = { 0: 'Text', 2: 'Voice', 4: 'Category', 5: 'Announcement', 13: 'Stage', 15: 'Forum' };

// Telegizer-parity IA: 6 grouped management tabs (Moderation … Analytics) in the
// exact order + subtab structure of the Telegram group dashboard, followed by a
// trailing "Settings" pill that gathers the Guildizer-only server-admin extras
// (Overview / Commands / Team / Billing) as sub-tabs. Settings sits last because
// it is configure-once setup, not day-to-day operation; the 6 shared category
// pills lead and match the Telegizer category pills 1:1.
const AREAS = [
  { label: 'Moderation', icon: Shield, subs: ['AutoMod', 'Behavior', 'Reports'] },
  { label: 'Members', icon: People, subs: ['Verification', 'Welcome', 'XP & Roles', 'Self-roles'] },
  { label: 'Engagement', icon: ForumIcon, subs: ['Raids', 'Invite Links', 'Campaigns', 'Tickets', 'Starboard', 'Boosts', 'Events'] },
  { label: 'AI & Integrations', icon: SmartToy, subs: ['Knowledge Base', 'Escalation'] },
  // Telegizer Automation order is Scheduler · Auto Reply · Polls · Forwarding · Workflows · Webhooks;
  // the Discord-only "Threads" subtab trails so the shared subtabs keep Telegizer's order/positions.
  { label: 'Automation', icon: Bolt, subs: ['Scheduler', 'Auto Reply', 'Polls', 'Forwarding', 'Workflows', 'Webhooks', 'Threads'] },
  // Telegizer Analytics lands on "Members" first; the Guildizer-only "Overview" trails so the
  // default landing subtab and the shared subtab order both match Telegizer 1:1.
  { label: 'Analytics', icon: Assessment, subs: ['Members', 'Leaderboard', 'Audit Log', 'Warnings', 'Digest', 'AI Activity', 'Overview'] },
  { label: 'Settings', icon: SettingsIcon, subs: ['Overview', 'Commands', 'Team', 'Billing'] },
];

// Old flat-tab deep links → new area/subtab so saved URLs keep working. The
// former top-level Overview / Commands / Team / Billing tabs now live as sub-tabs
// under Settings; older flat tabs map onto their category/subtab homes.
const LEGACY_TABS = {
  Overview: ['Settings', 'Overview'],
  Commands: ['Settings', 'Commands'],
  Team: ['Settings', 'Team'],
  Billing: ['Settings', 'Billing'],
  Content: ['Automation', 'Scheduler'],
  Protection: ['Moderation', 'AutoMod'],
  Leveling: ['Members', 'XP & Roles'],
  Campaigns: ['Engagement', 'Campaigns'],
  Knowledge: ['AI & Integrations', 'Knowledge Base'],
};

export default function GuildizerServerDetail() {
  return (
    <GuildizerUiPrefsProvider>
      <GuildizerServerDetailInner />
    </GuildizerUiPrefsProvider>
  );
}

function GuildizerServerDetailInner() {
  const { guildId } = useParams();
  const navigate = useNavigate();
  // Deep-linkable: /guildizer/servers/<id>?tab=Moderation&sub=Behavior
  const [searchParams, setSearchParams] = useSearchParams();

  let tabName = searchParams.get('tab') || 'Moderation';
  let subName = searchParams.get('sub') || '';
  if (LEGACY_TABS[tabName]) [tabName, subName] = LEGACY_TABS[tabName];

  const areaIdx = Math.max(0, AREAS.findIndex((a) => a.label === tabName));
  const area = AREAS[areaIdx];
  const subs = area.subs || null;
  const subIdx = subs ? Math.max(0, subs.indexOf(subName)) : 0;
  const sub = subs ? subs[subIdx] : null;

  // Moderation (the first pill) is the default landing area, so its bare pill
  // keeps a clean URL; every area carries subs, so a pill click jumps to that
  // area's first sub-tab.
  const setTab = (label) => {
    if (label === AREAS[0].label) { setSearchParams({}, { replace: true }); return; }
    const a = AREAS.find((x) => x.label === label);
    setSearchParams(a?.subs ? { tab: label, sub: a.subs[0] } : { tab: label }, { replace: true });
  };
  const setSub = (v) => setSearchParams({ tab: area.label, sub: subs[v] }, { replace: true });

  const [state, setState] = useState({ loading: true, guild: null, error: null });

  // ── Single sticky Save bar wiring (Telegizer parity) ────────────────────────
  const saveRef = useRef(null);
  const [bar, setBar] = useState({ present: false, dirty: false, saving: false });
  const saveBar = useMemo(() => ({
    register: (fn) => { saveRef.current = fn; setBar((b) => ({ ...b, present: true })); },
    unregister: () => { saveRef.current = null; setBar({ present: false, dirty: false, saving: false }); },
    report: ({ dirty, saving }) => setBar((b) => ({ ...b, present: true, dirty, saving })),
  }), []);
  const triggerSave = useCallback(() => { if (saveRef.current) saveRef.current(); }, []);

  // The active tab drives the bar: each editable tab register()s on mount and
  // unregister()s on unmount, so switching tabs flips the button automatically.
  // (No eager reset here — a parent effect would run AFTER the new child's
  // register() and wrongly wipe it.)
  const key = sub ? `${area.label}/${sub}` : area.label;

  useEffect(() => {
    let alive = true;
    guildizerApi.get(`/api/guilds/${guildId}`)
      .then(({ data }) => { if (alive) setState({ loading: false, guild: data, error: null }); })
      .catch((e) => {
        if (!alive) return;
        const msg = e?.response?.status === 403 ? "You can't manage this server."
          : e?.response?.status === 401 ? 'Connect your Discord account first.'
          : 'Failed to load this server.';
        setState({ loading: false, guild: null, error: msg });
      });
    return () => { alive = false; };
  }, [guildId]);

  const guild = state.guild;
  const channels = guild?.channels || [];
  const roles = guild?.roles || [];

  const [resyncing, setResyncing] = useState(false);
  const resync = useCallback(async () => {
    setResyncing(true);
    try {
      const { data } = await guildizerApi.post(`/api/guilds/${guildId}/resync`);
      setState((s) => (s.guild ? { ...s, guild: { ...s.guild, channels: data.channels, roles: data.roles } } : s));
    } catch { /* leave current data in place */ }
    setResyncing(false);
  }, [guildId]);

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', px: { xs: 2, md: 3 }, py: 0 }}>
      {state.loading && <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 240 }}><CircularProgress /></Box>}
      {state.error && <Alert severity="warning" sx={{ mt: 3 }}>{state.error}</Alert>}

      {guild && (
        <SaveBarContext.Provider value={saveBar}>
          {/* ── Sticky settings header: breadcrumb · title · UTC chip · Save ── */}
          <Box
            sx={{
              position: 'sticky', top: 0, zIndex: 5,
              bgcolor: 'background.default',
              mx: { xs: -2, md: -3 }, px: { xs: 2, md: 3 }, pt: 2,
              borderBottom: '1px solid', borderColor: 'divider',
            }}
          >
            {/* Breadcrumb + identity + actions */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.25 }}>
              <IconButton edge="start" size="small" onClick={() => navigate('/guildizer')} sx={{ display: { md: 'none' } }}>
                <ArrowBack fontSize="small" />
              </IconButton>
              <Box sx={{ display: { xs: 'none', md: 'flex' }, alignItems: 'center', gap: 0.5, mr: 0.5 }}>
                <Button size="small" variant="text" onClick={() => navigate('/dashboard')}
                  sx={{ fontSize: '0.75rem', px: 1, py: 0.25, minWidth: 0, color: 'text.secondary' }}>
                  Dashboard
                </Button>
                <Box component="span" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>/</Box>
                <Button size="small" variant="text" onClick={() => navigate('/guildizer')}
                  sx={{ fontSize: '0.75rem', px: 1, py: 0.25, minWidth: 0, color: 'text.secondary' }}>
                  My Servers
                </Button>
                <Box component="span" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>/</Box>
              </Box>

              <Avatar src={guild.icon_url || undefined} variant="rounded" sx={{ width: 32, height: 32, fontWeight: 700, fontSize: 14 }}>
                {(guild.name || '?').slice(0, 2).toUpperCase()}
              </Avatar>
              <Typography variant="h6" fontWeight={700} noWrap sx={{ flexGrow: 1 }}>{guild.name}</Typography>

              <Tooltip title="Refresh channels & roles from Discord (picks up ones you just created).">
                <span>
                  <IconButton size="small" onClick={resync} disabled={resyncing} sx={{ mr: 0.25 }}>
                    {resyncing ? <CircularProgress size={16} /> : <Refresh fontSize="small" />}
                  </IconButton>
                </span>
              </Tooltip>

              <Tooltip title="Discord schedules and timestamps everywhere in UTC.">
                <Chip icon={<Schedule sx={{ fontSize: 14 }} />} label="UTC" size="small" variant="outlined"
                  sx={{ mr: 0.5, fontSize: 11, cursor: 'default', display: { xs: 'none', sm: 'inline-flex' } }} />
              </Tooltip>

              {bar.present && (
                <Button
                  variant="contained"
                  size="small"
                  startIcon={bar.saving ? <CircularProgress size={16} color="inherit" /> : <Save />}
                  onClick={triggerSave}
                  disabled={bar.saving || !bar.dirty}
                >
                  {bar.saving ? 'Saving…' : bar.dirty ? 'Save' : 'Saved'}
                </Button>
              )}
            </Box>

            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, ml: { md: 0.5 } }}>
              {guild.member_count?.toLocaleString?.() || guild.member_count || 0} members ·{' '}
              {(guild.channels || []).filter((c) => c.type !== 4).length} channels ·{' '}
              {(guild.roles || []).filter((r) => r.name !== '@everyone').length} roles
            </Typography>

            {/* Category pill nav (hand-rolled pills, Telegizer parity) */}
            <Box sx={{ position: 'relative' }}>
              <Box sx={{
                position: 'absolute', right: 0, top: 0, bottom: 0, width: 32, zIndex: 1, pointerEvents: 'none',
                background: 'linear-gradient(to right, transparent, rgba(11,22,38,0.95))',
                display: { xs: 'block', md: 'none' },
              }} />
              <Box sx={{
                display: 'flex', gap: 0.75, py: 1, overflowX: 'auto',
                '::-webkit-scrollbar': { display: 'none' }, scrollBehavior: 'smooth', WebkitOverflowScrolling: 'touch',
              }}>
                {AREAS.map(({ label, icon: Icon }) => {
                  const active = label === area.label;
                  return (
                    <Box
                      key={label}
                      onClick={() => setTab(label)}
                      sx={{
                        display: 'flex', alignItems: 'center', gap: 0.75,
                        px: 1.5, py: 0.6, borderRadius: 2, cursor: 'pointer',
                        whiteSpace: 'nowrap', userSelect: 'none',
                        bgcolor: active ? 'primary.main' : 'rgba(255,255,255,0.05)',
                        color: active ? 'white' : 'text.secondary',
                        border: '1px solid',
                        borderColor: active ? 'primary.main' : 'rgba(255,255,255,0.12)',
                        transition: 'all 0.15s ease',
                        '&:hover': { bgcolor: active ? 'primary.dark' : 'rgba(255,255,255,0.09)' },
                      }}
                    >
                      <Icon sx={{ fontSize: 15 }} />
                      <Typography variant="body2" fontWeight={active ? 700 : 500} fontSize="0.78rem">{label}</Typography>
                    </Box>
                  );
                })}
              </Box>
            </Box>

            {/* Sub-tab row */}
            {subs && (
              <Tabs value={subIdx} onChange={(_, v) => setSub(v)} variant="scrollable" scrollButtons="auto" allowScrollButtonsMobile
                sx={{ minHeight: 38, '& .MuiTab-root': { minHeight: 38, fontSize: '0.8rem', py: 0, textTransform: 'none' } }}>
                {subs.map((s) => <Tab key={s} label={s} />)}
              </Tabs>
            )}
          </Box>

          {/* ── Tab content ── */}
          <Box sx={{ pt: 3, pb: 4 }}>
            {/* SETTINGS (server-level) */}
            {key === 'Settings/Overview' && <Overview guild={guild} />}
            {key === 'Settings/Commands' && <CommandsTab guildId={guildId} />}
            {key === 'Settings/Team' && <TeamTab guildId={guildId} />}
            {key === 'Settings/Billing' && <BillingTab guildId={guildId} />}

            {/* MODERATION */}
            {key === 'Moderation/AutoMod' && <ProtectionTab guildId={guildId} channels={channels} section="automod" />}
            {key === 'Moderation/Behavior' && <ProtectionTab guildId={guildId} channels={channels} section="behavior" />}
            {key === 'Moderation/Reports' && <ProtectionTab guildId={guildId} channels={channels} section="reports" />}

            {/* MEMBERS */}
            {key === 'Members/Verification' && <ProtectionTab guildId={guildId} channels={channels} section="verification" />}
            {key === 'Members/Welcome' && <SettingsTab guildId={guildId} channels={channels} roles={roles} />}
            {key === 'Members/XP & Roles' && <LevelingTab guildId={guildId} channels={channels} roles={roles} />}
            {key === 'Members/Self-roles' && <SelfRolesSubtab guildId={guildId} channels={channels} roles={roles} />}

            {/* ENGAGEMENT */}
            {key === 'Engagement/Raids' && <RaidsSubtab guildId={guildId} channels={channels} />}
            {key === 'Engagement/Invite Links' && <InviteLinksSubtab guildId={guildId} />}
            {key === 'Engagement/Campaigns' && <CampaignsTab guildId={guildId} channels={channels} />}
            {key === 'Engagement/Tickets' && <TicketsSubtab guildId={guildId} channels={channels} roles={roles} />}
            {key === 'Engagement/Starboard' && <StarboardSubtab guildId={guildId} channels={channels} />}
            {key === 'Engagement/Boosts' && <BoostsSubtab guildId={guildId} channels={channels} roles={roles} />}
            {key === 'Engagement/Events' && <EventsSubtab guildId={guildId} channels={channels} />}

            {/* AI & INTEGRATIONS */}
            {key === 'AI & Integrations/Knowledge Base' && <KnowledgeBaseSubtab guildId={guildId} />}
            {key === 'AI & Integrations/Escalation' && <ProtectionTab guildId={guildId} channels={channels} section="escalation" />}

            {/* AUTOMATION */}
            {key === 'Automation/Scheduler' && <SchedulerSubtab guildId={guildId} channels={channels} />}
            {key === 'Automation/Auto Reply' && <AutoReplySubtab guildId={guildId} />}
            {key === 'Automation/Polls' && <PollsSubtab guildId={guildId} channels={channels} />}
            {key === 'Automation/Forwarding' && <ForwardingSubtab guildId={guildId} channels={channels} />}
            {key === 'Automation/Threads' && <ThreadsSubtab guildId={guildId} channels={channels} />}
            {key === 'Automation/Workflows' && <WorkflowsSubtab guildId={guildId} channels={channels} roles={roles} />}
            {key === 'Automation/Webhooks' && <WebhooksSubtab guildId={guildId} channels={channels} />}

            {/* ANALYTICS */}
            {key === 'Analytics/Overview' && <AnalyticsTab guildId={guildId} />}
            {key === 'Analytics/Members' && <MembersTab guildId={guildId} />}
            {key === 'Analytics/Leaderboard' && <LeaderboardSubtab guildId={guildId} />}
            {key === 'Analytics/Audit Log' && <AuditLogSubtab guildId={guildId} />}
            {key === 'Analytics/Warnings' && <WarningsSubtab guildId={guildId} />}
            {key === 'Analytics/Digest' && <DigestSubtab guildId={guildId} channels={channels} />}
            {key === 'Analytics/AI Activity' && <AIActivitySubtab guildId={guildId} />}
          </Box>
        </SaveBarContext.Provider>
      )}
    </Box>
  );
}

// ── Backups: snapshot + non-destructive restore of roles/channels ─────────────
const BACKUP_STATUS_COLOR = {
  pending: 'default', done: 'success', failed: 'error',
  restoring: 'warning', restored: 'info', restore_failed: 'error',
};

function BackupsCard({ guildId }) {
  const [backups, setBackups] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const reload = () => guildizerApi.get(`/api/guilds/${guildId}/backups`)
    .then(({ data }) => setBackups(data.backups))
    .catch(() => { setError('Failed to load backups.'); setBackups([]); });

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { reload(); }, [guildId]);

  // Snapshots/restores finish within a loop tick — poll while one is in flight.
  const inFlight = (backups || []).some((b) => ['pending', 'restoring'].includes(b.status));
  useEffect(() => {
    if (!inFlight) return undefined;
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
    /* eslint-disable-next-line */
  }, [inFlight, guildId]);

  async function act(fn, failMsg) {
    setBusy(true); setError(null);
    try { await fn(); await reload(); } catch { setError(failMsg); }
    setBusy(false);
  }
  const create = () => act(
    () => guildizerApi.post(`/api/guilds/${guildId}/backups`, {}),
    'Could not start a backup (one may already be running).',
  );
  const restore = (b) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm('Re-apply this snapshot? Drifted roles/channels are reset and '
      + 'deleted ones recreated. Nothing is deleted.')) return;
    act(() => guildizerApi.post(`/api/guilds/${guildId}/backups/${b.id}/restore`, {}),
      'Could not start the restore.');
  };
  const remove = (b) => act(
    () => guildizerApi.delete(`/api/guilds/${guildId}/backups/${b.id}`),
    'Could not delete the backup.',
  );

  return (
    <GuildizerCollapsibleCard
      id="settings.overview.server_backups"
      title="🗄️ Server backups"
      action={(
        <Button size="small" variant="contained" disabled={busy || inFlight} onClick={create}>
          Back up now
        </Button>
      )}
    >
        <Typography variant="caption" color="text.secondary" display="block" mb={1}>
          Snapshots roles, channels and permission overwrites (up to 5 kept). Restore
          re-applies drifted settings and recreates deleted items — it never deletes
          anything. Useful after a nuke or a bad config change.
        </Typography>
        {error && <Alert severity="warning" sx={{ mb: 1 }} onClose={() => setError(null)}>{error}</Alert>}
        {(backups || []).length === 0 && backups !== null
          && <Typography variant="body2" color="text.secondary">No backups yet.</Typography>}
        <List dense disablePadding>
          {(backups || []).map((b) => (
            <ListItem key={b.id} disableGutters
              secondaryAction={(
                <Stack direction="row" spacing={1}>
                  {['done', 'restored'].includes(b.status) && (
                    <Button size="small" disabled={busy || inFlight} onClick={() => restore(b)}>Restore</Button>
                  )}
                  <Button size="small" color="inherit" disabled={busy} onClick={() => remove(b)}>Delete</Button>
                </Stack>
              )}>
              <Chip size="small" label={b.status} color={BACKUP_STATUS_COLOR[b.status] || 'default'}
                variant="outlined" sx={{ mr: 1 }} />
              <ListItemText
                primary={b.label || new Date(b.created_at).toLocaleString()}
                secondary={`${b.roles_count} roles · ${b.channels_count} channels${b.error ? ` · ${b.error}` : ''}`}
                primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
            </ListItem>
          ))}
        </List>
    </GuildizerCollapsibleCard>
  );
}

function Overview({ guild }) {
  const channels = (guild.channels || []).filter((c) => c.type !== 4);
  const roles = (guild.roles || []).filter((r) => r.name !== '@everyone');
  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="settings.overview.channels" title="Channels">
            {channels.length === 0 && <Typography variant="body2" color="text.secondary">No channels synced yet.</Typography>}
            <List dense disablePadding>
              {channels.map((c) => (
                <ListItem key={c.id} disableGutters secondaryAction={<Chip size="small" label={CHANNEL_TYPES[c.type] || 'Channel'} />}>
                  <ListItemText primary={`# ${c.name}`} primaryTypographyProps={{ noWrap: true }} />
                </ListItem>
              ))}
            </List>
        </GuildizerCollapsibleCard>
      </Grid>
      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="settings.overview.roles" title="Roles">
            {roles.length === 0 && <Typography variant="body2" color="text.secondary">No roles synced yet.</Typography>}
            <List dense disablePadding>
              {roles.map((r) => (
                <ListItem key={r.id} disableGutters secondaryAction={r.managed ? <Chip size="small" label="Integration" /> : null}>
                  <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: r.color || '#99aab5', mr: 1.5, flexShrink: 0 }} />
                  <ListItemText primary={r.name} primaryTypographyProps={{ noWrap: true }} />
                </ListItem>
              ))}
            </List>
        </GuildizerCollapsibleCard>
      </Grid>
      <Grid item xs={12}>
        <BackupsCard guildId={guild.id} />
      </Grid>
    </Grid>
  );
}
