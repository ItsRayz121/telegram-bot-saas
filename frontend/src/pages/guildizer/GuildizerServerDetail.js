import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Typography, Tabs, Tab, Card, CardContent, Grid, Avatar, Stack,
  List, ListItem, ListItemText, Chip, CircularProgress, Alert, Button,
} from '@mui/material';
import { ArrowBack } from '@mui/icons-material';
import guildizerApi from '../../services/guildizerApi';
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

// Telegizer-parity IA: 6 grouped management tabs (Moderation … Analytics) with
// the exact subtab structure of the Telegram group dashboard, plus the
// server-level extras (Overview / Commands / Team / Billing).
const AREAS = [
  { label: 'Overview' },
  { label: 'Moderation', subs: ['AutoMod', 'Behavior', 'Reports'] },
  { label: 'Members', subs: ['Verification', 'Welcome', 'XP & Roles', 'Self-roles'] },
  { label: 'Engagement', subs: ['Raids', 'Invite Links', 'Campaigns', 'Tickets', 'Starboard', 'Boosts', 'Events'] },
  { label: 'AI & Integrations', subs: ['Knowledge Base', 'Escalation'] },
  { label: 'Automation', subs: ['Scheduler', 'Auto Reply', 'Polls', 'Forwarding', 'Threads', 'Workflows', 'Webhooks'] },
  { label: 'Analytics', subs: ['Overview', 'Members', 'Leaderboard', 'Audit Log', 'Warnings', 'Digest', 'AI Activity'] },
  { label: 'Commands' },
  { label: 'Team' },
  { label: 'Billing' },
];

// Old flat-tab deep links → new area/subtab so saved URLs keep working.
const LEGACY_TABS = {
  Settings: ['Members', 'Welcome'],
  Content: ['Automation', 'Scheduler'],
  Protection: ['Moderation', 'AutoMod'],
  Leveling: ['Members', 'XP & Roles'],
  Campaigns: ['Engagement', 'Campaigns'],
  Knowledge: ['AI & Integrations', 'Knowledge Base'],
};

export default function GuildizerServerDetail() {
  const { guildId } = useParams();
  const navigate = useNavigate();
  // Deep-linkable: /guildizer/servers/<id>?tab=Moderation&sub=Behavior
  const [searchParams, setSearchParams] = useSearchParams();

  let tabName = searchParams.get('tab') || 'Overview';
  let subName = searchParams.get('sub') || '';
  if (LEGACY_TABS[tabName]) [tabName, subName] = LEGACY_TABS[tabName];

  const areaIdx = Math.max(0, AREAS.findIndex((a) => a.label === tabName));
  const area = AREAS[areaIdx];
  const subs = area.subs || null;
  const subIdx = subs ? Math.max(0, subs.indexOf(subName)) : 0;
  const sub = subs ? subs[subIdx] : null;

  const setTab = (v) => setSearchParams(v === 0 ? {} : { tab: AREAS[v].label }, { replace: true });
  const setSub = (v) => setSearchParams({ tab: area.label, sub: subs[v] }, { replace: true });

  const [state, setState] = useState({ loading: true, guild: null, error: null });

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
  const key = sub ? `${area.label}/${sub}` : area.label;

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', px: { xs: 2, md: 3 }, py: 3 }}>
      <Button startIcon={<ArrowBack />} onClick={() => navigate('/guildizer')} sx={{ mb: 2 }} color="inherit">
        All servers
      </Button>

      {state.loading && <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 240 }}><CircularProgress /></Box>}
      {state.error && <Alert severity="warning">{state.error}</Alert>}

      {guild && (
        <>
          <Header guild={guild} />
          <Tabs value={areaIdx} onChange={(_, v) => setTab(v)} variant="scrollable" allowScrollButtonsMobile
            sx={{ borderBottom: 1, borderColor: 'divider' }}>
            {AREAS.map((a) => <Tab key={a.label} label={a.label} />)}
          </Tabs>
          {subs && (
            <Tabs value={subIdx} onChange={(_, v) => setSub(v)} variant="scrollable" allowScrollButtonsMobile
              sx={{ mb: 3, minHeight: 38, '& .MuiTab-root': { minHeight: 38, fontSize: '0.82rem', py: 0, textTransform: 'none' } }}>
              {subs.map((s) => <Tab key={s} label={s} />)}
            </Tabs>
          )}
          {!subs && <Box sx={{ mb: 3 }} />}

          {key === 'Overview' && <Overview guild={guild} />}

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

          {/* SERVER-LEVEL */}
          {key === 'Commands' && <CommandsTab guildId={guildId} />}
          {key === 'Team' && <TeamTab guildId={guildId} />}
          {key === 'Billing' && <BillingTab guildId={guildId} />}
        </>
      )}
    </Box>
  );
}

function Header({ guild }) {
  const initials = (guild.name || '?').slice(0, 2).toUpperCase();
  const channelCount = (guild.channels || []).filter((c) => c.type !== 4).length;
  const roleCount = (guild.roles || []).filter((r) => r.name !== '@everyone').length;
  return (
    <Stack direction="row" spacing={2} alignItems="center" mb={2}>
      <Avatar src={guild.icon_url || undefined} variant="rounded" sx={{ width: 56, height: 56, fontWeight: 700 }}>
        {initials}
      </Avatar>
      <Box>
        <Typography variant="h5" fontWeight={800}>{guild.name}</Typography>
        <Typography variant="body2" color="text.secondary">
          {guild.member_count} members · {channelCount} channels · {roleCount} roles
        </Typography>
      </Box>
    </Stack>
  );
}

function Overview({ guild }) {
  const channels = (guild.channels || []).filter((c) => c.type !== 4);
  const roles = (guild.roles || []).filter((r) => r.name !== '@everyone');
  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={6}>
        <Card variant="outlined">
          <CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>Channels</Typography>
            {channels.length === 0 && <Typography variant="body2" color="text.secondary">No channels synced yet.</Typography>}
            <List dense disablePadding>
              {channels.map((c) => (
                <ListItem key={c.id} disableGutters secondaryAction={<Chip size="small" label={CHANNEL_TYPES[c.type] || 'Channel'} />}>
                  <ListItemText primary={`# ${c.name}`} primaryTypographyProps={{ noWrap: true }} />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card variant="outlined">
          <CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>Roles</Typography>
            {roles.length === 0 && <Typography variant="body2" color="text.secondary">No roles synced yet.</Typography>}
            <List dense disablePadding>
              {roles.map((r) => (
                <ListItem key={r.id} disableGutters secondaryAction={r.managed ? <Chip size="small" label="Integration" /> : null}>
                  <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: r.color || '#99aab5', mr: 1.5, flexShrink: 0 }} />
                  <ListItemText primary={r.name} primaryTypographyProps={{ noWrap: true }} />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}
