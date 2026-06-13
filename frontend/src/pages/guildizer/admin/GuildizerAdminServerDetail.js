// Routed Guildizer admin server-detail page — opens inside the admin shell
// (nested under /guildizer/admin). Tabbed drill-down over one guild, on
// guildizerApi only. Tabs: Overview, Members, Protection, Campaigns, Settings.
import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Typography, Tabs, Tab, Card, CardContent, Grid, Avatar, Stack, Chip,
  Button, CircularProgress, Alert, Table, TableHead, TableBody, TableRow, TableCell,
  TextField, List, ListItem, ListItemText,
} from '@mui/material';
import {
  ArrowBack, People, Campaign as CampaignIcon, Verified, Shield, SmartToy,
} from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import {
  StatCard, Field, EmptyRow, fmtDate, fmtDateTime,
} from '../../../components/guildizer/GuildizerAdminKit';
import { guildizerAdminPath } from '../../../config/guildizerAdminNav';
import { PALETTE } from '../../../theme';

const PAGE_SX = { maxWidth: 1200, mx: 'auto', px: { xs: 2, md: 3 }, py: 2.5 };
const TABS = ['Overview', 'Members', 'Protection', 'Campaigns', 'Settings'];

export default function GuildizerAdminServerDetail() {
  const { guildId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState(0);
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    guildizerApi.get(`/api/admin/guilds/${guildId}`)
      .then(({ data: d }) => setData(d))
      .catch((e) => setError(e?.response?.status === 404 ? 'Server not found.' : 'Failed to load server.'));
  }, [guildId]);
  useEffect(() => { load(); }, [load]);

  const setPlan = async (plan) => {
    setBusy(true);
    try { await guildizerApi.post(`/api/admin/guilds/${guildId}/plan`, { plan, days }); load(); }
    finally { setBusy(false); }
  };

  const back = () => navigate(guildizerAdminPath('servers'));

  if (error) {
    return (
      <Box sx={PAGE_SX}>
        <Button startIcon={<ArrowBack />} onClick={back} sx={{ mb: 2 }}>Back to Servers</Button>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }
  if (!data) {
    return <Box sx={{ ...PAGE_SX, display: 'grid', placeItems: 'center', minHeight: 240 }}><CircularProgress /></Box>;
  }

  const gd = data.guild;
  return (
    <Box sx={PAGE_SX}>
      <Button startIcon={<ArrowBack />} onClick={back} sx={{ mb: 2 }}>Back to Servers</Button>

      <Card variant="outlined" sx={{ mb: 2.5 }}><CardContent>
        <Stack direction="row" spacing={2} alignItems="center">
          <Avatar src={gd.icon_url || undefined} sx={{ width: 56, height: 56 }}>
            {(gd.name || '?').slice(0, 1).toUpperCase()}
          </Avatar>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h6" fontWeight={800} noWrap>{gd.name || gd.id}</Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              <Box component="span" sx={{ fontFamily: 'monospace' }}>{gd.id}</Box>
              {data.owner && <> · owner @{data.owner.username}</>}
            </Typography>
          </Box>
          <Box sx={{ flex: 1 }} />
          <Stack spacing={0.5} alignItems="flex-end">
            <Chip size="small" color={gd.plan === 'pro' ? 'success' : 'default'} variant="outlined" label={gd.plan} />
            <Chip size="small" color={gd.bot_present ? 'success' : 'warning'} variant="outlined"
              label={gd.bot_present ? 'Bot present' : 'No bot'} icon={<SmartToy sx={{ fontSize: 14 }} />} />
          </Stack>
        </Stack>
      </CardContent></Card>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto"
        allowScrollButtonsMobile sx={{ mb: 2, minHeight: 40 }}>
        {TABS.map((t) => <Tab key={t} label={t} sx={{ minHeight: 40, textTransform: 'none' }} />)}
      </Tabs>

      {/* Overview */}
      {tab === 0 && (
        <>
          <Grid container spacing={1.5} mb={2.5}>
            <Grid item xs={6} sm={3}><StatCard value={data.members} label="Members" icon={People} color={PALETTE.blue} /></Grid>
            <Grid item xs={6} sm={3}><StatCard value={data.campaigns} label="Campaigns" icon={CampaignIcon} color={PALETTE.amber} /></Grid>
            <Grid item xs={6} sm={3}><StatCard value={data.submissions} label="Submissions" icon={Verified} color={PALETTE.green} /></Grid>
            <Grid item xs={6} sm={3}><StatCard value={data.protection_events} label="Protection events" icon={Shield} color={PALETTE.red} /></Grid>
          </Grid>
          <Card variant="outlined"><CardContent>
            <Grid container spacing={2}>
              <Grid item xs={6} sm={4}><Field label="Member count" value={gd.member_count} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Plan" value={gd.plan} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Plan expires" value={gd.plan_expires_at ? fmtDate(gd.plan_expires_at) : '—'} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Owner" value={data.owner ? `@${data.owner.username}` : gd.owner_id || '—'} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Bot present" value={gd.bot_present ? 'Yes' : 'No'} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Guild ID" value={gd.id} mono /></Grid>
            </Grid>
          </CardContent></Card>
        </>
      )}

      {/* Members */}
      {tab === 1 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Top members by XP</Typography>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>Member</TableCell><TableCell align="right">Level</TableCell>
              <TableCell align="right">XP</TableCell><TableCell align="right">Messages</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {data.top_members.length === 0 && <EmptyRow colSpan={4} label="No members tracked." />}
              {data.top_members.map((m) => (
                <TableRow key={m.user_id} hover>
                  <TableCell>{m.username || m.user_id}</TableCell>
                  <TableCell align="right">{m.level}</TableCell>
                  <TableCell align="right">{m.xp.toLocaleString()}</TableCell>
                  <TableCell align="right">{m.messages.toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent></Card>
      )}

      {/* Protection */}
      {tab === 2 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Recent protection events</Typography>
          {data.recent_events.length === 0
            ? <Typography variant="body2" color="text.secondary">No protection events.</Typography>
            : (
              <List dense>
                {data.recent_events.map((e) => (
                  <ListItem key={e.id} disableGutters
                    secondaryAction={<Typography variant="caption" color="text.disabled">{fmtDateTime(e.created_at)}</Typography>}>
                    <Chip size="small" variant="outlined" label={e.category} sx={{ mr: 1 }} />
                    <ListItemText primary={`${e.action || '—'} — ${e.username ? e.username + ' · ' : ''}${e.detail || ''}`}
                      primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
                  </ListItem>
                ))}
              </List>
            )}
        </CardContent></Card>
      )}

      {/* Campaigns */}
      {tab === 3 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Campaigns</Typography>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>Title</TableCell><TableCell>Type</TableCell><TableCell>Status</TableCell>
              <TableCell align="right">Submissions</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {data.campaign_list.length === 0 && <EmptyRow colSpan={4} label="No campaigns." />}
              {data.campaign_list.map((c) => (
                <TableRow key={c.id} hover>
                  <TableCell>{c.title}</TableCell>
                  <TableCell>{c.type}</TableCell>
                  <TableCell><Chip size="small" variant="outlined" label={c.status} /></TableCell>
                  <TableCell align="right">{c.submissions}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent></Card>
      )}

      {/* Settings / Actions */}
      {tab === 4 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1.5}>Plan actions</Typography>
          <Stack direction="row" spacing={1} alignItems="center" mb={1}>
            <TextField type="number" size="small" label="Pro days" value={days}
              onChange={(e) => setDays(Number(e.target.value))} sx={{ width: 110 }} inputProps={{ min: 1 }} />
            <Button variant="contained" disabled={busy} onClick={() => setPlan('pro')}>Grant Pro</Button>
            <Button color="inherit" disabled={busy} onClick={() => setPlan('free')}>Set Free</Button>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            Current plan: <b>{gd.plan}</b>{gd.plan_expires_at ? ` · expires ${fmtDate(gd.plan_expires_at)}` : ''}
          </Typography>
        </CardContent></Card>
      )}
    </Box>
  );
}
