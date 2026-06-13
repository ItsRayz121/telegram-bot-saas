// Routed Guildizer admin campaign-detail page — opens inside the admin shell
// (nested under /guildizer/admin). On guildizerApi only.
// Tabs: Overview, Tasks, Submissions.
import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Typography, Tabs, Tab, Card, CardContent, Grid, Stack, Chip,
  Button, CircularProgress, Alert, Table, TableHead, TableBody, TableRow, TableCell,
  LinearProgress, List, ListItem, ListItemText,
} from '@mui/material';
import { ArrowBack, Verified, Bolt } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import {
  StatCard, Field, StatusChip, EmptyRow, fmtDateTime,
} from '../../../components/guildizer/GuildizerAdminKit';
import { guildizerAdminPath } from '../../../config/guildizerAdminNav';
import { PALETTE } from '../../../theme';

const PAGE_SX = { maxWidth: 1100, mx: 'auto', px: { xs: 2, md: 3 }, py: 2.5 };
const TABS = ['Overview', 'Tasks', 'Submissions'];

export default function GuildizerAdminCampaignDetail() {
  const { campaignId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState(0);

  const load = useCallback(() => {
    guildizerApi.get(`/api/admin/campaigns/${campaignId}`)
      .then(({ data: d }) => setData(d))
      .catch((e) => setError(e?.response?.status === 404 ? 'Campaign not found.' : 'Failed to load campaign.'));
  }, [campaignId]);
  useEffect(() => { load(); }, [load]);

  const back = () => navigate(guildizerAdminPath('campaigns'));

  if (error) {
    return (
      <Box sx={PAGE_SX}>
        <Button startIcon={<ArrowBack />} onClick={back} sx={{ mb: 2 }}>Back to Campaigns</Button>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }
  if (!data) {
    return <Box sx={{ ...PAGE_SX, display: 'grid', placeItems: 'center', minHeight: 240 }}><CircularProgress /></Box>;
  }

  const c = data.campaign;
  const sub = data.submissions || {};
  const reviewed = (sub.verified || 0) + (sub.rejected || 0);
  const rate = reviewed ? Math.round((sub.verified / reviewed) * 100) : 0;

  return (
    <Box sx={PAGE_SX}>
      <Button startIcon={<ArrowBack />} onClick={back} sx={{ mb: 2 }}>Back to Campaigns</Button>

      <Card variant="outlined" sx={{ mb: 2.5 }}><CardContent>
        <Stack direction="row" spacing={2} alignItems="center">
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="h6" fontWeight={800} noWrap>{c.title}</Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              {c.type} · {data.guild?.name || c.guild_id}
            </Typography>
          </Box>
          <StatusChip label={c.status} />
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
            <Grid item xs={6} sm={3}><StatCard value={sub.total ?? 0} label="Submissions" icon={Verified} color={PALETTE.blue} /></Grid>
            <Grid item xs={6} sm={3}><StatCard value={sub.verified ?? 0} label="Verified" icon={Verified} color={PALETTE.green} /></Grid>
            <Grid item xs={6} sm={3}><StatCard value={sub.pending ?? 0} label="Pending" color={PALETTE.amber} /></Grid>
            <Grid item xs={6} sm={3}><StatCard value={`${rate}%`} label="Approval rate" color={PALETTE.cyan} /></Grid>
          </Grid>
          {reviewed > 0 && (
            <LinearProgress variant="determinate" value={rate}
              sx={{ height: 8, borderRadius: 4, mb: 2.5, '& .MuiLinearProgress-bar': { bgcolor: PALETTE.green } }} />
          )}
          <Card variant="outlined"><CardContent>
            {c.description && <Typography variant="body2" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{c.description}</Typography>}
            <Grid container spacing={2}>
              <Grid item xs={6} sm={4}><Field label="Verification" value={c.verification_mode} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Reward XP" value={c.reward_xp} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Reward label" value={c.reward_label} /></Grid>
              <Grid item xs={6} sm={4}><Field label="One per user" value={c.one_per_user ? 'Yes' : 'No'} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Post status" value={c.post_status} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Task URL" value={c.task_url} /></Grid>
            </Grid>
          </CardContent></Card>
        </>
      )}

      {/* Tasks */}
      {tab === 1 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Tasks</Typography>
          {(!c.tasks || c.tasks.length === 0)
            ? <Typography variant="body2" color="text.secondary">Single-task campaign (no sub-tasks).</Typography>
            : (
              <List dense>
                {c.tasks.map((t) => (
                  <ListItem key={t.id} disableGutters
                    secondaryAction={<Chip size="small" variant="outlined" icon={<Bolt sx={{ fontSize: 14 }} />} label={`${t.reward_xp} XP`} />}>
                    <ListItemText primary={t.title}
                      secondary={`${t.type} · ${t.verification_mode}`}
                      primaryTypographyProps={{ variant: 'body2' }} />
                  </ListItem>
                ))}
              </List>
            )}
        </CardContent></Card>
      )}

      {/* Submissions */}
      {tab === 2 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Recent submissions</Typography>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>User</TableCell><TableCell>Status</TableCell>
              <TableCell align="right">Reward</TableCell><TableCell align="right">When</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {data.recent.length === 0 && <EmptyRow colSpan={4} label="No submissions." />}
              {data.recent.map((s) => (
                <TableRow key={s.id} hover>
                  <TableCell>{s.username || s.user_id}</TableCell>
                  <TableCell><StatusChip label={s.status} /></TableCell>
                  <TableCell align="right">{s.reward_granted || 0}</TableCell>
                  <TableCell align="right"><Typography variant="caption" color="text.disabled">{fmtDateTime(s.created_at)}</Typography></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent></Card>
      )}
    </Box>
  );
}
