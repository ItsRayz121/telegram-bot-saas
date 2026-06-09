import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Grid, Stack, Chip, Button, CircularProgress, LinearProgress,
  Breadcrumbs, Link as MuiLink, Paper, Tooltip, Alert,
} from '@mui/material';
import {
  ArrowBack, Block, LinkOff, NetworkCheck, OpenInNew, Sync,
} from '@mui/icons-material';
import { useParams, useNavigate, Link as RouterLink } from 'react-router-dom';
import { toast } from 'react-toastify';
import { admin } from '../services/api';
import { Field, SectionTitle, fmtDate, fmtDateTime, fmtRelative } from '../components/AdminDetailKit';

// Build the best available Telegram deep-link for a group (#6).
function telegramLink(detail) {
  if (!detail) return null;
  if (detail.username) return `https://t.me/${detail.username.replace(/^@/, '')}`;
  if (detail.invite_link) return detail.invite_link;
  return null;
}

export default function AdminGroupDetail() {
  const { groupId } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await admin.getTelegramGroupDetail(groupId);
      setDetail(res.data.group);
    } catch (err) {
      toast.error(err?.response?.data?.error || 'Failed to load group');
    } finally { setLoading(false); }
  }, [groupId]);

  useEffect(() => { load(); }, [load]);

  const run = async (key, fn, okMsg) => {
    setAction(key);
    try { await fn(); if (okMsg) toast.success(okMsg); await load(); }
    catch (err) { toast.error(err?.response?.data?.error || 'Action failed'); }
    finally { setAction(''); }
  };

  const handleDisable = () => {
    if (!window.confirm(`Disable group "${detail.title}"?`)) return;
    run('disable', () => admin.disableTelegramGroup(groupId), 'Group disabled');
  };
  const handleUnlink = () => {
    if (!window.confirm(`Unlink "${detail.title}" from its owner?`)) return;
    run('unlink', () => admin.unlinkTelegramGroup(groupId), 'Group unlinked');
  };
  const handleSync = () => run('sync', () => admin.syncGroupMembers(groupId), 'Member count synced');
  const handlePing = () => {
    const isCustom = detail.linked_via_bot_type === 'custom';
    run('ping', async () => {
      const res = isCustom && detail.linked_bot_id
        ? await admin.pingCustomBot(detail.linked_bot_id)
        : await admin.pingBot({ scope: 'official' });
      const ok = res?.data?.ok;
      if (ok) toast.success('Bot reachable ✓'); else toast.warn(res?.data?.error || 'Bot ping failed');
    });
  };

  if (loading && !detail) {
    return <Box display="flex" justifyContent="center" mt={8}><CircularProgress /></Box>;
  }
  if (!detail) {
    return (
      <Box p={3}>
        <Button startIcon={<ArrowBack />} onClick={() => navigate('/admin')}>Back to Admin</Button>
        <Alert severity="error" sx={{ mt: 2 }}>Group not found.</Alert>
      </Box>
    );
  }

  const m = detail.moderation || {};
  const pm = detail.proof_metrics || {};
  const tgLink = telegramLink(detail);
  const synced = detail.members?.member_count_synced_at || detail.member_count_synced_at;

  return (
    <Box sx={{ maxWidth: 1100, mx: 'auto', p: { xs: 2, sm: 3 }, pb: 'var(--bottom-nav-clearance, 24px)' }}>
      <Breadcrumbs sx={{ mb: 1 }}>
        <MuiLink component={RouterLink} to="/admin" underline="hover" color="inherit">Admin</MuiLink>
        <MuiLink component={RouterLink} to="/admin" underline="hover" color="inherit">TG Groups</MuiLink>
        <Typography color="text.primary">{detail.title}</Typography>
      </Breadcrumbs>

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }} mb={2}>
        <Button startIcon={<ArrowBack />} onClick={() => navigate('/admin')} size="small">Back</Button>
        <Box flex={1}>
          <Typography variant="h5" fontWeight={700}>{detail.title}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>{detail.telegram_group_id}</Typography>
        </Box>
        <Chip label={detail.bot_status} size="small" color={detail.bot_status === 'active' ? 'success' : 'default'} />
        <Chip label={detail.linked_via_bot_type} size="small" variant="outlined" color={detail.linked_via_bot_type === 'official' ? 'success' : 'primary'} />
      </Stack>

      {loading && <LinearProgress sx={{ mb: 2 }} />}

      {/* Action bar */}
      <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button size="small" variant="outlined" startIcon={action === 'sync' ? <CircularProgress size={14} /> : <Sync />}
            onClick={handleSync} disabled={!!action}>Sync member count</Button>
          <Button size="small" variant="outlined" startIcon={action === 'ping' ? <CircularProgress size={14} /> : <NetworkCheck />}
            onClick={handlePing} disabled={!!action}>Ping bot</Button>
          {tgLink ? (
            <Button size="small" variant="outlined" color="info" startIcon={<OpenInNew />}
              component="a" href={tgLink} target="_blank" rel="noopener noreferrer">Open in Telegram</Button>
          ) : (
            <Tooltip title="Private group with no stored invite link. The bot can only generate one if it has invite permission.">
              <span><Button size="small" variant="outlined" startIcon={<OpenInNew />} disabled>Open in Telegram</Button></span>
            </Tooltip>
          )}
          <Box flex={1} />
          {detail.owner_user_id && (
            <Button size="small" color="warning" startIcon={<LinkOff />} onClick={handleUnlink} disabled={!!action}>Unlink</Button>
          )}
          {!detail.is_disabled && (
            <Button size="small" color="error" startIcon={<Block />} onClick={handleDisable} disabled={!!action}>Disable</Button>
          )}
        </Stack>
        {!tgLink && (
          <Typography variant="caption" color="text.disabled" display="block" mt={1}>
            Private group link unavailable. Bot cannot generate an invite link unless it has invite permission.
          </Typography>
        )}
      </Paper>

      <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
        <SectionTitle sx={{ mt: 0 }}>Overview</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><Field label="Visibility" value={detail.visibility} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Username / link" value={detail.username ? `@${detail.username}` : '—'} /></Grid>
          <Grid item xs={6} sm={3}>
            <Field label="Members (live)" value={(detail.member_count || 0).toLocaleString()} />
            <Tooltip title={synced ? `Synced ${fmtDateTime(synced)}` : 'Never synced live — estimate from join/leave events'}>
              <Typography variant="caption" color={synced ? 'text.disabled' : 'warning.main'}>
                {synced ? `synced ${fmtRelative(synced)}` : 'not synced'}
              </Typography>
            </Tooltip>
          </Grid>
          <Grid item xs={6} sm={3}><Field label="Tracked members" value={detail.members?.tracked_members ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Context" value={detail.group_context} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Linked at" value={detail.linked_at ? fmtDate(detail.linked_at) : '—'} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Last activity" value={detail.last_activity ? fmtDate(detail.last_activity) : '—'} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Commands" value={detail.command_count ?? 0} /></Grid>
        </Grid>

        <SectionTitle>Ownership</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={4}>
            <Field label="Group Owner (linked account)"
              value={detail.ownership?.owner_user_id
                ? <MuiLink component={RouterLink} to={`/admin/users/${detail.ownership.owner_user_id}`}>{detail.ownership.owner_email || detail.ownership.owner_name || `User ${detail.ownership.owner_user_id}`}</MuiLink>
                : '— (unlinked)'} />
          </Grid>
          <Grid item xs={6} sm={4}><Field label="Connected by" value={detail.ownership?.connected_by || '—'} /></Grid>
          <Grid item xs={6} sm={4}><Field label="Managed by bot" value={detail.ownership?.managed_by_bot} /></Grid>
        </Grid>
        <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>
          Telegram-side owner/admins are not synced from the Telegram API yet.
        </Typography>

        <SectionTitle>Bot Permissions</SectionTitle>
        {detail.bot_permissions && Object.keys(detail.bot_permissions).length > 0 ? (
          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            {Object.entries(detail.bot_permissions).map(([k, v]) => (
              <Chip key={k} size="small" label={k.replace(/_/g, ' ')} color={v ? 'success' : 'default'} variant={v ? 'filled' : 'outlined'} />
            ))}
          </Stack>
        ) : <Typography variant="caption" color="text.disabled">Permissions not recorded.</Typography>}

        <SectionTitle>Members & Admins</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><Field label="Members" value={(detail.member_count || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Tracked members" value={detail.members?.tracked_members ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Admins" value={detail.members?.admin_count ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Muted" value={detail.members?.muted_count ?? 0} /></Grid>
        </Grid>

        <SectionTitle>Moderation Throughput</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><Field label="Spam deleted" value={(m.spam_deleted || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Links blocked" value={(m.links_blocked || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Warnings" value={(m.warnings_issued || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Commands" value={(m.commands_used || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Muted" value={(m.muted || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Banned" value={(m.banned || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Kicked" value={(m.kicked || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Total actions" value={(m.total_actions || 0).toLocaleString()} /></Grid>
        </Grid>

        <SectionTitle>AI Moderation / Activity</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><Field label="AI checks (total)" value={(detail.ai_usage?.total || 0).toLocaleString()} /></Grid>
          {Object.entries(detail.ai_usage?.by_category || {}).map(([cat, c]) => (
            <Grid item xs={6} sm={3} key={cat}><Field label={cat} value={c} /></Grid>
          ))}
        </Grid>

        <SectionTitle>Health & Recent Errors</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><Field label="Bot status" value={detail.health?.bot_status} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Errors 24h" value={detail.health?.errors_24h ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Errors 7d" value={detail.health?.errors_7d ?? 0} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Disabled" value={detail.health?.is_disabled ? 'Yes' : 'No'} /></Grid>
        </Grid>
        {detail.health?.recent_errors?.length > 0 && (
          <Box mt={1}>
            {detail.health.recent_errors.slice(0, 6).map((e) => (
              <Typography key={e.id} variant="caption" display="block" color="error.main">
                • [{e.severity || 'info'}] {e.detail} <Typography component="span" variant="caption" color="text.disabled">({fmtDateTime(e.created_at)})</Typography>
              </Typography>
            ))}
          </Box>
        )}

        <SectionTitle>Proof Metrics (group)</SectionTitle>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><Field label="Members protected" value={(pm.members_protected || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Spam deleted" value={(pm.spam_deleted || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="Links blocked" value={(pm.links_blocked || 0).toLocaleString()} /></Grid>
          <Grid item xs={6} sm={3}><Field label="AI checks" value={(pm.ai_checks || 0).toLocaleString()} /></Grid>
        </Grid>

        {detail.recent_events?.length > 0 && (
          <>
            <SectionTitle>Recent Events</SectionTitle>
            {detail.recent_events.slice(0, 12).map((e) => (
              <Stack key={e.id} direction="row" justifyContent="space-between" py={0.4} borderBottom="1px solid" borderColor="divider">
                <Typography variant="caption">{e.event_type}: {e.message}</Typography>
                <Typography variant="caption" color="text.disabled" whiteSpace="nowrap" pl={1}>{fmtDateTime(e.created_at)}</Typography>
              </Stack>
            ))}
          </>
        )}
      </Paper>
    </Box>
  );
}
