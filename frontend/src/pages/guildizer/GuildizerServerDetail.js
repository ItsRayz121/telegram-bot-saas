import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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
import ContentTab from './tabs/ContentTab';
import AutomationTab from './tabs/AutomationTab';
import MembersTab from './tabs/MembersTab';
import AnalyticsTab from './tabs/AnalyticsTab';
import KnowledgeTab from './tabs/KnowledgeTab';

// Discord channel type enum → label (common ones).
const CHANNEL_TYPES = { 0: 'Text', 2: 'Voice', 4: 'Category', 5: 'Announcement', 13: 'Stage', 15: 'Forum' };

// Tabs grow with each integration phase.
const TABS = ['Overview', 'Settings', 'Commands', 'Content', 'Automation', 'Protection', 'Leveling', 'Campaigns', 'Members', 'Analytics', 'Knowledge', 'Billing'];

export default function GuildizerServerDetail() {
  const { guildId } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState(0);
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

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', px: { xs: 2, md: 3 }, py: 3 }}>
      <Button startIcon={<ArrowBack />} onClick={() => navigate('/guildizer')} sx={{ mb: 2 }} color="inherit">
        All servers
      </Button>

      {state.loading && <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 240 }}><CircularProgress /></Box>}
      {state.error && <Alert severity="warning">{state.error}</Alert>}

      {state.guild && (
        <>
          <Header guild={state.guild} />
          <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" allowScrollButtonsMobile sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}>
            {TABS.map((t) => <Tab key={t} label={t} />)}
          </Tabs>
          {TABS[tab] === 'Overview' && <Overview guild={state.guild} />}
          {TABS[tab] === 'Settings' && <SettingsTab guildId={guildId} channels={state.guild.channels} roles={state.guild.roles} />}
          {TABS[tab] === 'Commands' && <CommandsTab guildId={guildId} />}
          {TABS[tab] === 'Content' && <ContentTab guildId={guildId} channels={state.guild.channels} />}
          {TABS[tab] === 'Automation' && <AutomationTab guildId={guildId} channels={state.guild.channels} roles={state.guild.roles} />}
          {TABS[tab] === 'Protection' && <ProtectionTab guildId={guildId} channels={state.guild.channels} />}
          {TABS[tab] === 'Leveling' && <LevelingTab guildId={guildId} channels={state.guild.channels} />}
          {TABS[tab] === 'Campaigns' && <CampaignsTab guildId={guildId} channels={state.guild.channels} />}
          {TABS[tab] === 'Members' && <MembersTab guildId={guildId} />}
          {TABS[tab] === 'Analytics' && <AnalyticsTab guildId={guildId} />}
          {TABS[tab] === 'Knowledge' && <KnowledgeTab guildId={guildId} />}
          {TABS[tab] === 'Billing' && <BillingTab guildId={guildId} />}
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
