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
