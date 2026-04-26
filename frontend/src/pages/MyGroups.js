import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Container, Typography, Button, Card, CardContent,
  Chip, CircularProgress, Alert, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, IconButton,
  Tooltip, Grid, Divider, Paper, List, ListItem,
  ListItemIcon, ListItemText, LinearProgress,
} from '@mui/material';
import {
  Add, Groups, CheckCircle, HourglassEmpty, LinkOff,
  Settings, Refresh, ContentCopy, OpenInNew, Warning,
  Lock, Security, Cancel,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { telegramGroups, settings as settingsApi } from '../services/api';

const BOT_USERNAME = process.env.REACT_APP_BOT_USERNAME || 'telegizer_bot';

function StatusChip({ status }) {
  const map = {
    active: { label: 'Active', color: 'success' },
    pending: { label: 'Pending', color: 'warning' },
    removed: { label: 'Removed', color: 'error' },
    disabled: { label: 'Disabled', color: 'error' },
  };
  const { label, color } = map[status] || { label: status, color: 'default' };
  return <Chip label={label} color={color} size="small" />;
}

function PermScoreBadge({ perms }) {
  if (!perms) return <Chip label="Unknown" color="default" size="small" />;
  const keys = Object.keys(perms);
  if (keys.length === 0) return <Chip label="Unknown" color="default" size="small" />;
  const granted = Object.values(perms).filter(Boolean).length;
  const total = keys.length;
  if (granted === total) return <Chip label="Full Access" color="success" size="small" icon={<CheckCircle sx={{ fontSize: '14px !important' }} />} />;
  const missing = total - granted;
  return (
    <Chip
      label={`Missing ${missing}`}
      color={missing > 2 ? 'error' : 'warning'}
      size="small"
      icon={<Warning sx={{ fontSize: '14px !important' }} />}
    />
  );
}

const PERMISSION_LABELS = {
  can_delete_messages:  { label: 'Delete messages',      feature: 'AutoMod deletion' },
  can_restrict_members: { label: 'Restrict / mute users', feature: 'Mute & verification' },
  can_ban_members:      { label: 'Ban users',             feature: 'Ban actions' },
  can_pin_messages:     { label: 'Pin messages',          feature: 'Pinned announcements' },
  can_manage_topics:    { label: 'Manage topics',         feature: 'Forum/topic verification' },
  can_manage_chat:      { label: 'Manage chat',           feature: 'Admin rights management' },
  can_invite_users:     { label: 'Invite users',          feature: 'Invite link tools' },
  can_promote_members:  { label: 'Add admins',            feature: 'Grant admin rights' },
  can_change_info:      { label: 'Change group info',     feature: 'Group info updates' },
  is_anonymous:         { label: 'Anonymous admin',       feature: 'Anonymised actions' },
};

export default function MyGroups() {
  const navigate = useNavigate();
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkCode, setLinkCode] = useState('');
  const [linking, setLinking] = useState(false);
  const [unlinkTarget, setUnlinkTarget] = useState(null);

  // Permissions modal state
  const [permsGroup, setPermsGroup] = useState(null);   // group object currently shown
  const [permsData, setPermsData] = useState(null);      // live data from API
  const [permsLoading, setPermsLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await telegramGroups.list();
      setGroups(res.data.groups || []);
    } catch {
      toast.error('Failed to load groups');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleLink = async () => {
    if (!linkCode.trim()) return;
    setLinking(true);
    try {
      const res = await telegramGroups.link({ code: linkCode.trim().toUpperCase() });
      toast.success(`Group "${res.data.group.title}" linked successfully!`);
      setLinkOpen(false);
      setLinkCode('');
      load();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to link group');
    } finally {
      setLinking(false);
    }
  };

  const handleUnlink = async () => {
    if (!unlinkTarget) return;
    try {
      await telegramGroups.unlink(unlinkTarget.telegram_group_id);
      toast.success(`Group "${unlinkTarget.title}" unlinked`);
      setUnlinkTarget(null);
      load();
    } catch {
      toast.error('Failed to unlink group');
    }
  };

  const openPermissions = async (group) => {
    setPermsGroup(group);
    setPermsData(null);
    setPermsLoading(true);
    try {
      const res = await settingsApi.getBotPermissions(group.telegram_group_id);
      setPermsData(res.data);
    } catch (err) {
      setPermsData({ error: err.response?.data?.error || 'Failed to load permissions' });
    } finally {
      setPermsLoading(false);
    }
  };

  const addToGroupUrl = `https://t.me/${BOT_USERNAME}?startgroup=setup`;

  // Build permission display from live data (permsData.permissions) or
  // fall back to the cached bot_permissions on the group object.
  const buildCachedPerms = (rawPerms) => {
    if (!rawPerms) return [];
    return Object.entries(rawPerms).map(([key, granted]) => ({
      key,
      label: PERMISSION_LABELS[key]?.label || key,
      feature: PERMISSION_LABELS[key]?.feature || '',
      granted,
    }));
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', py: 4 }}>
      <Container maxWidth="lg">
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
          <Box>
            <Typography variant="h4" fontWeight={700}>My Groups</Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              Manage your Telegram groups linked to Telegizer
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <IconButton onClick={load} disabled={loading}><Refresh /></IconButton>
            <Button
              variant="outlined"
              startIcon={<OpenInNew />}
              href={addToGroupUrl}
              target="_blank"
              rel="noreferrer"
            >
              Add Bot to Group
            </Button>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setLinkOpen(true)}
            >
              Link Group
            </Button>
          </Box>
        </Box>

        {/* Setup instruction banner */}
        <Paper
          sx={{
            p: 2.5, mb: 3,
            background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
            border: '1px solid #334155',
          }}
        >
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            How to link a group
          </Typography>
          <Typography variant="body2" color="text.secondary">
            1. Add <strong>@{BOT_USERNAME}</strong> to your Telegram group as admin &nbsp;
            2. In the group, run <code>/linkgroup</code> &nbsp;
            3. Copy the code shown &nbsp;
            4. Click <strong>Link Group</strong> above and paste it
          </Typography>
        </Paper>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : groups.length === 0 ? (
          <Card sx={{ textAlign: 'center', py: 6 }}>
            <Groups sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" gutterBottom>No groups linked yet</Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              Add the Telegizer bot to your group then link it here.
            </Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setLinkOpen(true)}
            >
              Link Your First Group
            </Button>
          </Card>
        ) : (
          <Grid container spacing={2}>
            {groups.map((g) => {
              const cachedPerms = g.bot_permissions;
              const grantedCount = cachedPerms
                ? Object.values(cachedPerms).filter(Boolean).length
                : null;
              const totalCount = cachedPerms ? Object.keys(cachedPerms).length : null;

              return (
                <Grid item xs={12} md={6} key={g.telegram_group_id}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Typography variant="h6" noWrap fontWeight={600}>
                            {g.title}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                            ID: {g.telegram_group_id}
                          </Typography>
                        </Box>
                        <StatusChip status={g.bot_status} />
                      </Box>

                      <Divider sx={{ my: 1.5 }} />

                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1.5, alignItems: 'flex-end' }}>
                        <Box>
                          <Typography variant="caption" color="text.secondary">Bot Type</Typography>
                          <Typography variant="body2" fontWeight={500}>
                            {g.linked_via_bot_type === 'official' ? '🟢 Official Telegizer' : '🔵 Custom Bot'}
                          </Typography>
                        </Box>
                        <Box sx={{ ml: 'auto', textAlign: 'right' }}>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Permissions{grantedCount !== null ? ` (${grantedCount}/${totalCount})` : ''}
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', justifyContent: 'flex-end', mt: 0.25 }}>
                            <PermScoreBadge perms={cachedPerms} />
                            <Tooltip title="View detailed permissions">
                              <IconButton
                                size="small"
                                onClick={() => openPermissions(g)}
                                sx={{ p: 0.25 }}
                              >
                                <Security fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </Box>
                        </Box>
                      </Box>

                      {g.last_activity && (
                        <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
                          Last activity: {new Date(g.last_activity).toLocaleString()}
                        </Typography>
                      )}

                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <Button
                          size="small"
                          variant="contained"
                          startIcon={<Settings />}
                          onClick={() => navigate(`/my-groups/${g.telegram_group_id}`)}
                          sx={{ flex: 1 }}
                        >
                          Manage
                        </Button>
                        <Tooltip title="Unlink group">
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => setUnlinkTarget(g)}
                          >
                            <LinkOff fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              );
            })}
          </Grid>
        )}
      </Container>

      {/* ── Permissions modal ──────────────────────────────────────────────── */}
      <Dialog
        open={!!permsGroup}
        onClose={() => { setPermsGroup(null); setPermsData(null); }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Lock fontSize="small" />
          Bot Permissions — {permsGroup?.title}
        </DialogTitle>
        <DialogContent>
          {permsLoading ? (
            <Box sx={{ py: 3 }}>
              <LinearProgress />
              <Typography variant="caption" color="text.secondary" display="block" mt={1} textAlign="center">
                Checking live permissions from Telegram…
              </Typography>
            </Box>
          ) : permsData?.error ? (
            <Alert severity="error" sx={{ mb: 1 }}>{permsData.error}</Alert>
          ) : permsData ? (
            <>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Score:
                </Typography>
                <Typography variant="h6" fontWeight={700} color={
                  permsData.score === permsData.total ? 'success.main' :
                  permsData.score >= permsData.total - 2 ? 'warning.main' : 'error.main'
                }>
                  {permsData.score}/{permsData.total}
                </Typography>
                {permsData.score === permsData.total && (
                  <Chip label="Full Access" color="success" size="small" />
                )}
                {permsData.score < permsData.total && (
                  <Chip label={`Missing ${permsData.total - permsData.score}`} color="warning" size="small" />
                )}
              </Box>

              <List dense disablePadding>
                {(permsData.permissions || []).map((p) => (
                  <ListItem key={p.key} disablePadding sx={{ py: 0.4 }}>
                    <ListItemIcon sx={{ minWidth: 32 }}>
                      {p.granted
                        ? <CheckCircle color="success" fontSize="small" />
                        : <Cancel color="error" fontSize="small" />
                      }
                    </ListItemIcon>
                    <ListItemText
                      primary={p.label}
                      secondary={p.feature}
                      primaryTypographyProps={{ variant: 'body2', fontWeight: p.granted ? 400 : 600 }}
                      secondaryTypographyProps={{ variant: 'caption' }}
                    />
                  </ListItem>
                ))}
              </List>

              {permsData.score < permsData.total && (
                <Alert severity="info" icon={<Settings fontSize="small" />} sx={{ mt: 2 }}>
                  <Typography variant="caption">
                    <strong>How to fix:</strong> Open Telegram → Group → Administrators → Telegizer → enable the missing permissions above.
                  </Typography>
                </Alert>
              )}
            </>
          ) : (
            // Fall back to cached permissions while loading
            (() => {
              const cached = buildCachedPerms(permsGroup?.bot_permissions);
              if (cached.length === 0) return (
                <Typography variant="body2" color="text.secondary">No permission data available. Fetching…</Typography>
              );
              return (
                <>
                  <Alert severity="info" icon={false} sx={{ mb: 2 }}>
                    <Typography variant="caption">Showing cached permissions. Click Refresh to fetch live data.</Typography>
                  </Alert>
                  <List dense disablePadding>
                    {cached.map((p) => (
                      <ListItem key={p.key} disablePadding sx={{ py: 0.4 }}>
                        <ListItemIcon sx={{ minWidth: 32 }}>
                          {p.granted
                            ? <CheckCircle color="success" fontSize="small" />
                            : <Cancel color="error" fontSize="small" />
                          }
                        </ListItemIcon>
                        <ListItemText
                          primary={p.label}
                          secondary={p.feature}
                          primaryTypographyProps={{ variant: 'body2' }}
                          secondaryTypographyProps={{ variant: 'caption' }}
                        />
                      </ListItem>
                    ))}
                  </List>
                </>
              );
            })()
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => permsGroup && openPermissions(permsGroup)} disabled={permsLoading}>
            Refresh
          </Button>
          <Button variant="contained" onClick={() => { setPermsGroup(null); setPermsData(null); }}>
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Link group dialog */}
      <Dialog open={linkOpen} onClose={() => setLinkOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Link a Telegram Group</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            Run <code>/linkgroup</code> in your Telegram group to get a verification code, then paste it below.
          </Alert>
          <TextField
            autoFocus
            fullWidth
            label="Verification Code"
            value={linkCode}
            onChange={(e) => setLinkCode(e.target.value.toUpperCase())}
            placeholder="TLG-XXXXXXXX"
            inputProps={{ style: { fontFamily: 'monospace', letterSpacing: 2 } }}
            onKeyDown={(e) => e.key === 'Enter' && handleLink()}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLinkOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleLink}
            disabled={linking || !linkCode.trim()}
          >
            {linking ? <CircularProgress size={20} /> : 'Link Group'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Unlink confirm dialog */}
      <Dialog open={!!unlinkTarget} onClose={() => setUnlinkTarget(null)}>
        <DialogTitle>Unlink Group?</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to unlink <strong>{unlinkTarget?.title}</strong>?
            The bot will remain in the group but the group won't appear in your dashboard.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUnlinkTarget(null)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleUnlink}>Unlink</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
