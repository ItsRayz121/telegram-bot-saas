// Routed Guildizer admin user-detail page — opens inside the admin shell
// (nested under /guildizer/admin). Tabbed drill-down mirroring the Telegizer
// admin user profile, 100% on guildizerApi. Tabs: Overview, Memberships,
// AI Usage, Risk, Audit, Notes.
import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Typography, Tabs, Tab, Card, CardContent, Grid, Avatar, Stack, Chip,
  Button, CircularProgress, Alert, Table, TableHead, TableBody, TableRow, TableCell,
  TextField, List, ListItem, ListItemText,
} from '@mui/material';
import {
  ArrowBack, Bolt, Shield, Verified, Save as SaveIcon,
} from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import {
  StatCard, Field, EmptyRow, SectionTitle, fmtDate, fmtDateTime,
} from '../../../components/guildizer/GuildizerAdminKit';
import { guildizerAdminPath } from '../../../config/guildizerAdminNav';
import { PALETTE } from '../../../theme';

const PAGE_SX = { maxWidth: 1200, mx: 'auto', px: { xs: 2, md: 3 }, py: 2.5 };
const TABS = ['Overview', 'Memberships', 'AI Usage', 'Risk', 'Audit', 'Notes'];

export default function GuildizerAdminUserDetail() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState(0);
  const [notes, setNotes] = useState('');
  const [savingNotes, setSavingNotes] = useState(false);

  const load = useCallback(() => {
    guildizerApi.get(`/api/admin/users/${userId}`)
      .then(({ data: d }) => { setData(d); setNotes(d.user.admin_notes || ''); })
      .catch((e) => setError(e?.response?.status === 404 ? 'User not found.' : 'Failed to load user.'));
  }, [userId]);
  useEffect(() => { load(); }, [load]);

  const saveNotes = async () => {
    setSavingNotes(true);
    try { await guildizerApi.post(`/api/admin/users/${userId}/notes`, { notes }); }
    finally { setSavingNotes(false); }
  };

  const back = () => navigate(guildizerAdminPath('users'));

  if (error) {
    return (
      <Box sx={PAGE_SX}>
        <Button startIcon={<ArrowBack />} onClick={back} sx={{ mb: 2 }}>Back to Users</Button>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }
  if (!data) {
    return <Box sx={{ ...PAGE_SX, display: 'grid', placeItems: 'center', minHeight: 240 }}><CircularProgress /></Box>;
  }

  const u = data.user;
  const ai = data.ai_usage || {};
  const sub = data.submissions || {};

  return (
    <Box sx={PAGE_SX}>
      <Button startIcon={<ArrowBack />} onClick={back} sx={{ mb: 2 }}>Back to Users</Button>

      {/* Hero */}
      <Card variant="outlined" sx={{ mb: 2.5 }}><CardContent>
        <Stack direction="row" spacing={2} alignItems="center">
          <Avatar src={u.avatar_url || undefined} sx={{ width: 56, height: 56 }}>
            {(u.username || '?').slice(0, 1).toUpperCase()}
          </Avatar>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h6" fontWeight={800} noWrap>{u.global_name || u.username || u.id}</Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              @{u.username || '—'} · <Box component="span" sx={{ fontFamily: 'monospace' }}>{u.id}</Box>
            </Typography>
          </Box>
          <Box sx={{ flex: 1 }} />
          <Stack spacing={0.5} alignItems="flex-end">
            <Chip size="small" variant="outlined" label={`${data.memberships.length} server(s)`} />
            <Typography variant="caption" color="text.disabled">Last login {fmtDate(u.last_login_at)}</Typography>
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
            <Grid item xs={6} sm={3}><StatCard value={data.memberships.length} label="Memberships" color={PALETTE.blue} /></Grid>
            <Grid item xs={6} sm={3}><StatCard value={ai.calls ?? 0} label="AI calls" icon={Bolt} color={PALETTE.cyan} /></Grid>
            <Grid item xs={6} sm={3}><StatCard value={sub.verified ?? 0} label="Verified proofs" icon={Verified} color={PALETTE.green} /></Grid>
            <Grid item xs={6} sm={3}><StatCard value={data.warnings.length} label="Warnings" icon={Shield} color={PALETTE.red} /></Grid>
          </Grid>
          <Card variant="outlined"><CardContent>
            <Grid container spacing={2}>
              <Grid item xs={6} sm={4}><Field label="Username" value={u.username} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Display name" value={u.global_name} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Discord ID" value={u.id} mono /></Grid>
              <Grid item xs={6} sm={4}><Field label="First seen" value={fmtDate(u.created_at)} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Last login" value={fmtDateTime(u.last_login_at)} /></Grid>
              <Grid item xs={6} sm={4}><Field label="Proof submissions" value={`${sub.verified ?? 0} ok / ${sub.total ?? 0}`} /></Grid>
            </Grid>
          </CardContent></Card>
        </>
      )}

      {/* Memberships */}
      {tab === 1 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Server memberships</Typography>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>Server</TableCell><TableCell>Role</TableCell><TableCell>Plan</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {data.memberships.length === 0 && <EmptyRow colSpan={3} label="No memberships." />}
              {data.memberships.map((m) => (
                <TableRow key={m.guild_id} hover>
                  <TableCell>{m.name || m.guild_id}</TableCell>
                  <TableCell>{m.is_owner ? 'Owner' : m.can_manage ? 'Manager' : 'Member'}</TableCell>
                  <TableCell><Chip size="small" variant="outlined" label={m.plan}
                    color={m.plan === 'pro' ? 'success' : 'default'} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent></Card>
      )}

      {/* AI Usage */}
      {tab === 2 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1.5}>AI token usage (all-time)</Typography>
          <Grid container spacing={1.5}>
            <Grid item xs={4}><StatCard value={ai.calls ?? 0} label="Calls" icon={Bolt} color={PALETTE.cyan} /></Grid>
            <Grid item xs={4}><StatCard value={(ai.input_tokens ?? 0).toLocaleString()} label="Input tokens" color={PALETTE.blue} /></Grid>
            <Grid item xs={4}><StatCard value={(ai.output_tokens ?? 0).toLocaleString()} label="Output tokens" color={PALETTE.purple} /></Grid>
          </Grid>
        </CardContent></Card>
      )}

      {/* Risk */}
      {tab === 3 && (
        <>
          <Card variant="outlined" sx={{ mb: 2 }}><CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>Warnings ({data.warnings.length})</Typography>
            {data.warnings.length === 0
              ? <Typography variant="body2" color="text.secondary">No warnings on record.</Typography>
              : (
                <List dense>
                  {data.warnings.map((w) => (
                    <ListItem key={w.id} disableGutters
                      secondaryAction={<Typography variant="caption" color="text.disabled">{fmtDate(w.created_at)}</Typography>}>
                      <ListItemText primary={w.reason || 'No reason'}
                        secondary={`by ${w.moderator_name || (w.moderator_id ? w.moderator_id : 'AutoMod')}`}
                        primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                  ))}
                </List>
              )}
          </CardContent></Card>
          <Card variant="outlined"><CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>Protection events ({data.protection_events.length})</Typography>
            {data.protection_events.length === 0
              ? <Typography variant="body2" color="text.secondary">No protection events.</Typography>
              : (
                <List dense>
                  {data.protection_events.map((e) => (
                    <ListItem key={e.id} disableGutters
                      secondaryAction={<Typography variant="caption" color="text.disabled">{fmtDateTime(e.created_at)}</Typography>}>
                      <Chip size="small" variant="outlined" label={e.category} sx={{ mr: 1 }} />
                      <ListItemText primary={`${e.action || '—'}${e.detail ? ' · ' + e.detail : ''}`}
                        primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
                    </ListItem>
                  ))}
                </List>
              )}
          </CardContent></Card>
        </>
      )}

      {/* Audit */}
      {tab === 4 && (
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Admin audit trail</Typography>
          {data.audit.length === 0
            ? <Typography variant="body2" color="text.secondary">No admin actions involving this user.</Typography>
            : (
              <List dense>
                {data.audit.map((a) => (
                  <ListItem key={a.id} disableGutters
                    secondaryAction={<Typography variant="caption" color="text.disabled">{fmtDateTime(a.created_at)}</Typography>}>
                    <Chip size="small" variant="outlined" label={a.action} sx={{ mr: 1 }} />
                    <ListItemText primary={`${a.target || ''}${a.detail ? ' — ' + a.detail : ''}`}
                      secondary={`by ${a.admin_id}`} primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
                  </ListItem>
                ))}
              </List>
            )}
        </CardContent></Card>
      )}

      {/* Notes */}
      {tab === 5 && (
        <Card variant="outlined"><CardContent>
          <SectionTitle sx={{ mt: 0 }}>Private admin notes</SectionTitle>
          <TextField multiline minRows={4} fullWidth value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="Internal notes about this user (visible to platform admins only)…" sx={{ mb: 1.5 }} />
          <Button variant="contained" startIcon={<SaveIcon />} onClick={saveNotes}
            disabled={savingNotes || notes === (u.admin_notes || '')}>
            {savingNotes ? 'Saving…' : 'Save notes'}
          </Button>
        </CardContent></Card>
      )}
    </Box>
  );
}
