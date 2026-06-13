// Routed Guildizer admin custom-bot detail — opens inside the admin shell
// (nested under /guildizer/admin). White-label fleet drill-down on guildizerApi.
// Tabs: Overview, Owner, Linked Servers, Health, Errors, Actions.
import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Typography, Tabs, Tab, Card, CardContent, Grid, Avatar, Stack, Chip,
  Button, CircularProgress, Alert, Table, TableHead, TableBody, TableRow, TableCell,
  List, ListItem, ListItemText,
} from '@mui/material';
import { ArrowBack, Groups, CheckCircle, Cancel } from '@mui/icons-material';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as ReTooltip, Legend,
} from 'recharts';
import guildizerApi from '../../../services/guildizerApi';
import {
  StatCard, Field, StatusChip, EmptyRow, fmtDate, fmtDateTime,
} from '../../../components/guildizer/GuildizerAdminKit';
import { guildizerAdminPath } from '../../../config/guildizerAdminNav';
import { PALETTE } from '../../../theme';

const PAGE_SX = { maxWidth: 1200, mx: 'auto', px: { xs: 2, md: 3 }, py: 2.5 };
const TABS = ['Overview', 'Owner', 'Linked Servers', 'Health', 'Errors', 'Actions'];

export default function GuildizerAdminCustomBotDetail() {
  const { botId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState(0);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    guildizerApi.get(`/api/admin/custom-bots/${botId}`)
      .then(({ data: d }) => setData(d))
      .catch((e) => setError(e?.response?.status === 404 ? 'Bot not found.' : 'Failed to load bot.'));
  }, [botId]);
  useEffect(() => { load(); }, [load]);

  const setStatus = async (status) => {
    setBusy(true);
    try { await guildizerApi.post(`/api/admin/custom-bots/${botId}/status`, { status }); load(); }
    finally { setBusy(false); }
  };

  const back = () => navigate(guildizerAdminPath('bots'));

  if (error) {
    return (
      <Box sx={PAGE_SX}>
        <Button startIcon={<ArrowBack />} onClick={back} sx={{ mb: 2 }}>Back to Custom Bots</Button>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }
  if (!data) {
    return <Box sx={{ ...PAGE_SX, display: 'grid', placeItems: 'center', minHeight: 240 }}><CircularProgress /></Box>;
  }

  const b = data.bot;
  return (
    <Box sx={PAGE_SX}>
      <Button startIcon={<ArrowBack />} onClick={back} sx={{ mb: 2 }}>Back to Custom Bots</Button>

      <Card variant="outlined" sx={{ mb: 2.5 }}><CardContent>
        <Stack direction="row" spacing={2} alignItems="center">
          <Avatar src={b.avatar_url || undefined} sx={{ width: 56, height: 56 }}>
            {(b.bot_username || '?').slice(0, 1).toUpperCase()}
          </Avatar>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h6" fontWeight={800} noWrap>@{b.bot_username || b.bot_user_id}</Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              App <Box component="span" sx={{ fontFamily: 'monospace' }}>{b.application_id}</Box>
            </Typography>
          </Box>
          <Box sx={{ flex: 1 }} />
          <StatusChip label={b.status} />
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
            <Grid item xs={6} sm={4}><StatCard value={data.linked_guilds.length} label="Linked servers" icon={Groups} color={PALETTE.blue} /></Grid>
            <Grid item xs={6} sm={4}><StatCard value={b.intents_ok ? 'OK' : 'Missing'} label="Privileged intents" color={b.intents_ok ? PALETTE.green : PALETTE.red} /></Grid>
            <Grid item xs={6} sm={4}><StatCard value={data.errors.length} label="Recent errors" color={PALETTE.amber} /></Grid>
          </Grid>
          <Card variant="outlined"><CardContent>
            <Grid container spacing={2}>
              <Grid item xs={6} sm={4}><Field label="Username" value={b.bot_username} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Bot user ID" value={b.bot_user_id} mono /></Grid>
              <Grid item xs={6} sm={4}><Field label="Application ID" value={b.application_id} mono /></Grid>
              <Grid item xs={6} sm={4}><Field label="Members intent" value={b.intents_members ? 'On' : 'Off'} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Message-content intent" value={b.intents_message_content ? 'On' : 'Off'} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Last online" value={b.last_online_at ? fmtDateTime(b.last_online_at) : 'never'} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Added" value={fmtDate(b.created_at)} /></Grid>
              {b.error_detail && <Grid item xs={12}><Field label="Error detail" value={b.error_detail} /></Grid>}
            </Grid>
          </CardContent></Card>
        </>
      )}

      {/* Owner */}
      {tab === 1 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1.5}>Owner</Typography>
          {data.owner ? (
            <Stack direction="row" spacing={2} alignItems="center">
              <Avatar src={data.owner.avatar_url || undefined}>{(data.owner.username || '?').slice(0, 1).toUpperCase()}</Avatar>
              <Box>
                <Typography variant="body1" fontWeight={600}>@{data.owner.username}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>{data.owner.id}</Typography>
              </Box>
              <Box sx={{ flex: 1 }} />
              <Button size="small" onClick={() => navigate(`/guildizer/admin/access/users/${data.owner.id}`)}>View user</Button>
            </Stack>
          ) : <Typography variant="body2" color="text.secondary">Owner record not found.</Typography>}
        </CardContent></Card>
      )}

      {/* Linked Servers */}
      {tab === 2 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Linked servers ({data.linked_guilds.length})</Typography>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>Server</TableCell><TableCell align="right">Members</TableCell><TableCell>Plan</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {data.linked_guilds.length === 0 && <EmptyRow colSpan={3} label="No linked servers." />}
              {data.linked_guilds.map((gd) => (
                <TableRow key={gd.id} hover sx={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/guildizer/admin/bots/servers/${gd.id}`)}>
                  <TableCell>{gd.name || gd.id}</TableCell>
                  <TableCell align="right">{gd.member_count}</TableCell>
                  <TableCell><Chip size="small" variant="outlined" label={gd.plan}
                    color={gd.plan === 'pro' ? 'success' : 'default'} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent></Card>
      )}

      {/* Health */}
      {tab === 3 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1.5}>Connection health · last 14d</Typography>
          <Box sx={{ height: 240, mb: 2 }}>
            {data.daily.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.daily} margin={{ top: 6, right: 12, bottom: 0, left: -16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="day" tick={{ fontSize: 10 }} stroke="rgba(255,255,255,0.4)" tickFormatter={(d) => d.slice(5)} />
                  <YAxis tick={{ fontSize: 11 }} stroke="rgba(255,255,255,0.4)" allowDecimals={false} />
                  <ReTooltip contentStyle={{ background: '#1a1d29', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Area type="monotone" dataKey="connect" stroke={PALETTE.green} fillOpacity={0} strokeWidth={2} />
                  <Area type="monotone" dataKey="disconnect" stroke={PALETTE.amber} fillOpacity={0} strokeWidth={2} />
                  <Area type="monotone" dataKey="error" stroke={PALETTE.red} fillOpacity={0} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <Box sx={{ height: '100%', display: 'grid', placeItems: 'center' }}>
                <Typography variant="body2" color="text.secondary">No health events in the last 14 days.</Typography>
              </Box>
            )}
          </Box>
          <List dense>
            {data.events.slice(0, 20).map((e) => (
              <ListItem key={e.id} disableGutters
                secondaryAction={<Typography variant="caption" color="text.disabled">{fmtDateTime(e.created_at)}</Typography>}>
                <Chip size="small" variant="outlined" sx={{ mr: 1 }}
                  color={e.event === 'connect' ? 'success' : e.event === 'disconnect' ? 'warning' : 'error'}
                  label={e.event} />
                <ListItemText primary={e.detail || '—'} primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
            {data.events.length === 0 && <Typography variant="body2" color="text.secondary">No events.</Typography>}
          </List>
        </CardContent></Card>
      )}

      {/* Errors */}
      {tab === 4 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Error history</Typography>
          {data.errors.length === 0
            ? <Typography variant="body2" color="text.secondary">No errors recorded. 🎉</Typography>
            : (
              <List dense>
                {data.errors.map((e) => (
                  <ListItem key={e.id} disableGutters
                    secondaryAction={<Typography variant="caption" color="text.disabled">{fmtDateTime(e.created_at)}</Typography>}>
                    <Chip size="small" variant="outlined" color="error" label={e.event} sx={{ mr: 1 }} />
                    <ListItemText primary={e.detail || '—'} primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
                  </ListItem>
                ))}
              </List>
            )}
        </CardContent></Card>
      )}

      {/* Actions */}
      {tab === 5 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1.5}>Fleet actions</Typography>
          <Stack direction="row" spacing={1}>
            <Button variant="contained" color="success" startIcon={<CheckCircle />}
              disabled={busy || b.status === 'active'} onClick={() => setStatus('active')}>
              Enable
            </Button>
            <Button variant="outlined" color="error" startIcon={<Cancel />}
              disabled={busy || b.status === 'disabled'} onClick={() => setStatus('disabled')}>
              Disable
            </Button>
          </Stack>
          <Typography variant="caption" color="text.secondary" display="block" mt={1.5}>
            Disabling stops the fleet worker from running a gateway client for this bot. The owner can re-enable it from their dashboard.
          </Typography>
        </CardContent></Card>
      )}
    </Box>
  );
}
