import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Container, Typography, Button, Card, CardContent,
  Chip, CircularProgress, Alert, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, IconButton,
  Tooltip, Grid, Divider, Paper, List, ListItem,
  ListItemIcon, ListItemText, LinearProgress,
} from '@mui/material';
import {
  Add, Groups, CheckCircle, LinkOff, Settings, Refresh,
  OpenInNew, Warning, Lock, Security, Cancel, BarChart,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { telegramGroups, settings as settingsApi } from '../services/api';
import TopNav from '../components/TopNav';

const BOT_USERNAME = process.env.REACT_APP_BOT_USERNAME || 'telegizer_bot';

const PERMISSION_LABELS = {
  can_delete_messages:    { label: 'Delete messages',        feature: 'AutoMod deletion' },
  can_restrict_members:   { label: 'Restrict / mute / ban',  feature: 'Mute, kick & verification' },
  can_pin_messages:       { label: 'Pin messages',           feature: 'Pinned announcements' },
  can_manage_chat:        { label: 'Manage chat',            feature: 'Admin rights management' },
  can_invite_users:       { label: 'Invite users',           feature: 'Invite link tools' },
  can_promote_members:    { label: 'Add admins',             feature: 'Grant admin rights' },
  can_change_info:        { label: 'Change group info',      feature: 'Group info updates' },
  can_manage_video_chats: { label: 'Manage video chats',     feature: 'Voice chats & live streams' },
};

function StatusChip({ status }) {
  const map = {
    active:   { label: 'Active',   color: 'success' },
    pending:  { label: 'Pending',  color: 'warning' },
    removed:  { label: 'Removed',  color: 'error'   },
    disabled: { label: 'Disabled', color: 'error'   },
  };
  const { label, color } = map[status] || { label: status, color: 'default' };
  return <Chip label={label} color={color} size="small" />;
}

function PermScoreBadge({ perms, liveScore, liveTotal }) {
  // Use live data when available, else fall back to cached perms
  if (liveScore !== undefined && liveTotal !== undefined) {
    if (liveScore === liveTotal) {
      return <Chip label="Full Access" color="success" size="small" icon={<CheckCircle sx={{ fontSize: '14px !important' }} />} />;
    }
    const missing = liveTotal - liveScore;
    return (
      <Chip
        label={`Missing ${missing}`}
        color={missing > 2 ? 'error' : 'warning'}
        size="small"
        icon={<Warning sx={{ fontSize: '14px !important' }} />}
      />
    );
  }
  if (!perms || Object.keys(perms).length === 0) {
    return <Chip label="Check permissions" color="default" size="small" />;
  }
  const granted = Object.values(perms).filter(Boolean).length;
  const total = Object.keys(perms).length;
  if (granted === total) {
    return <Chip label="Full Access" color="success" size="small" icon={<CheckCircle sx={{ fontSize: '14px !important' }} />} />;
  }
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

export default function MyGroups() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const botIdFilter = searchParams.get('bot_id') ? Number(searchParams.get('bot_id')) : null;

  const [allGroups, setAllGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkCode, setLinkCode] = useState('');
  const [linking, setLinking] = useState(false);
  const [unlinkTarget, setUnlinkTarget] = useState(null);

  // Per-card live permission state: { [groupId]: { loading, data } }
  const [permsState, setPermsState] = useState({});

  // Full-screen permissions modal
  const [permsModalGroup, setPermsModalGroup] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await telegramGroups.list();
      setAllGroups(res.data.groups || []);
    } catch {
      toast.error('Failed to load groups');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // When bot_id is in the URL, show only that custom bot's groups
  const groups = useMemo(() => {
    if (!botIdFilter) return allGroups;
    return allGroups.filter((g) => g.linked_bot_id === botIdFilter);
  }, [allGroups, botIdFilter]);

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

  const refreshPermsForGroup = async (groupId) => {
    setPermsState((prev) => ({
      ...prev,
      [groupId]: { loading: true, data: prev[groupId]?.data || null },
    }));
    try {
      const res = await settingsApi.getBotPermissions(groupId);
      setPermsState((prev) => ({
        ...prev,
        [groupId]: { loading: false, data: res.data },
      }));
    } catch (err) {
      const errMsg = err.response?.data?.error || 'Failed to load permissions';
      setPermsState((prev) => ({
        ...prev,
        [groupId]: { loading: false, data: { error: errMsg } },
      }));
      toast.error(errMsg);
    }
  };

  const openPermissionsModal = async (group) => {
    setPermsModalGroup(group);
    if (!permsState[group.telegram_group_id]?.data) {
      await refreshPermsForGroup(group.telegram_group_id);
    }
  };

  const buildCachedPerms = (rawPerms) => {
    if (!rawPerms) return [];
    return Object.entries(rawPerms).map(([key, granted]) => ({
      key,
      label: PERMISSION_LABELS[key]?.label || key,
      feature: PERMISSION_LABELS[key]?.feature || '',
      granted,
    }));
  };

  const addToGroupUrl = `https://t.me/${BOT_USERNAME}?startgroup=setup`;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <TopNav
        breadcrumb={[
          { label: 'Dashboard', path: '/dashboard' },
          { label: 'My Groups' },
        ]}
        actions={
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<OpenInNew />}
              href={addToGroupUrl}
              target="_blank"
              rel="noreferrer"
            >
              Add Bot
            </Button>
            <Button
              variant="contained"
              size="small"
              startIcon={<Add />}
              onClick={() => setLinkOpen(true)}
            >
              Link Group
            </Button>
          </Box>
        }
      />

      <Container maxWidth="lg" sx={{ py: 4 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Typography variant="h4" fontWeight={700}>
              {botIdFilter ? 'Bot Groups' : 'My Groups'}
            </Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              {botIdFilter
                ? 'Groups linked to this custom bot'
                : 'All Telegram groups linked to Telegizer'}
            </Typography>
          </Box>
          <IconButton onClick={load} disabled={loading}><Refresh /></IconButton>
        </Box>

        {/* Setup banner */}
        <Paper sx={{ p: 2.5, mb: 3, background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)', border: '1px solid #334155' }}>
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            How to link a group
          </Typography>
          <Typography variant="body2" color="text.secondary">
            1. Add <strong>@{BOT_USERNAME}</strong> as admin &nbsp;
            2. Run <code>/linkgroup</code> inside the group &nbsp;
            3. Click <strong>Link Group</strong> above and paste the code
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
            <Button variant="contained" startIcon={<Add />} onClick={() => setLinkOpen(true)}>
              Link Your First Group
            </Button>
          </Card>
        ) : (
          <Grid container spacing={2}>
            {groups.map((g) => {
              const gid = g.telegram_group_id;
              const ps = permsState[gid];
              const liveData = ps?.data;
              const liveLoading = ps?.loading;

              return (
                <Grid item xs={12} md={6} key={gid}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent>
                      {/* Title + status */}
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Typography variant="h6" noWrap fontWeight={600}>{g.title}</Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                            ID: {gid}
                          </Typography>
                        </Box>
                        <StatusChip status={g.bot_status} />
                      </Box>

                      <Divider sx={{ my: 1.5 }} />

                      {/* Bot type + permissions row */}
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', mb: 1.5 }}>
                        <Box>
                          <Typography variant="caption" color="text.secondary">Bot Type</Typography>
                          <Typography variant="body2" fontWeight={500}>
                            {g.linked_via_bot_type === 'official' ? '🟢 Official Telegizer' : '🔵 Custom Bot'}
                          </Typography>
                        </Box>
                        <Box sx={{ textAlign: 'right' }}>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Permissions
                            {liveData && !liveData.error && ` (${liveData.score}/${liveData.total})`}
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', justifyContent: 'flex-end', mt: 0.25 }}>
                            {liveLoading ? (
                              <CircularProgress size={14} />
                            ) : (
                              <PermScoreBadge
                                perms={g.bot_permissions}
                                liveScore={liveData && !liveData.error ? liveData.score : undefined}
                                liveTotal={liveData && !liveData.error ? liveData.total : undefined}
                              />
                            )}
                            <Tooltip title="Refresh live permissions">
                              <IconButton
                                size="small"
                                onClick={() => refreshPermsForGroup(gid)}
                                disabled={liveLoading}
                                sx={{ p: 0.25 }}
                              >
                                {liveLoading ? <CircularProgress size={14} /> : <Refresh fontSize="small" />}
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="View detailed permissions">
                              <IconButton size="small" onClick={() => openPermissionsModal(g)} sx={{ p: 0.25 }}>
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

                      {/* Missing permissions inline warning */}
                      {liveData && !liveData.error && liveData.score < liveData.total && (
                        <Alert severity="warning" sx={{ mb: 1.5, py: 0.5, fontSize: '0.75rem' }}>
                          Missing: {(liveData.permissions || []).filter((p) => !p.granted).map((p) => p.label).join(', ')}
                        </Alert>
                      )}

                      {/* Actions */}
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <Button
                          size="small"
                          variant="contained"
                          startIcon={<Settings />}
                          onClick={() => navigate(`/my-groups/${gid}`)}
                          sx={{ flex: 1 }}
                        >
                          Manage
                        </Button>
                        <Tooltip title="View analytics">
                          <IconButton
                            size="small"
                            onClick={() => navigate(`/my-groups/${gid}/analytics`)}
                          >
                            <BarChart fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title={g.source === 'legacy' ? 'Managed via custom bot runner' : 'Unlink group'}>
                          <span>
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => setUnlinkTarget(g)}
                              disabled={g.source === 'legacy'}
                            >
                              <LinkOff fontSize="small" />
                            </IconButton>
                          </span>
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

      {/* Permissions detail modal */}
      <Dialog
        open={!!permsModalGroup}
        onClose={() => setPermsModalGroup(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Lock fontSize="small" />
          Bot Permissions — {permsModalGroup?.title}
        </DialogTitle>
        <DialogContent>
          {(() => {
            const gid = permsModalGroup?.telegram_group_id;
            const ps = permsState[gid];
            const liveLoading = ps?.loading;
            const liveData = ps?.data;

            if (liveLoading) {
              return (
                <Box sx={{ py: 3 }}>
                  <LinearProgress />
                  <Typography variant="caption" color="text.secondary" display="block" mt={1} textAlign="center">
                    Checking live permissions from Telegram…
                  </Typography>
                </Box>
              );
            }
            if (liveData?.error) {
              return <Alert severity="error">{liveData.error}</Alert>;
            }
            if (liveData?.permissions) {
              return (
                <>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
                    <Typography variant="body2" color="text.secondary">Score:</Typography>
                    <Typography variant="h6" fontWeight={700} color={
                      liveData.score === liveData.total ? 'success.main' :
                      liveData.score >= liveData.total - 2 ? 'warning.main' : 'error.main'
                    }>
                      {liveData.score}/{liveData.total}
                    </Typography>
                    {liveData.score === liveData.total
                      ? <Chip label="Full Access" color="success" size="small" />
                      : <Chip label={`Missing ${liveData.total - liveData.score}`} color="warning" size="small" />
                    }
                  </Box>
                  <List dense disablePadding>
                    {(liveData.permissions || []).map((p) => (
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
                  {liveData.score < liveData.total && (
                    <Alert severity="info" icon={<Settings fontSize="small" />} sx={{ mt: 2 }}>
                      <Typography variant="caption">
                        <strong>How to fix:</strong> Telegram → Group → Administrators → {BOT_USERNAME} → enable the missing permissions above.
                      </Typography>
                    </Alert>
                  )}
                </>
              );
            }
            // Fallback: cached
            const cached = buildCachedPerms(permsModalGroup?.bot_permissions);
            if (cached.length === 0) {
              return (
                <Typography variant="body2" color="text.secondary">
                  No permission data. Click Refresh to fetch live data.
                </Typography>
              );
            }
            return (
              <>
                <Alert severity="info" icon={false} sx={{ mb: 2 }}>
                  <Typography variant="caption">Showing cached data. Click Refresh for live status.</Typography>
                </Alert>
                <List dense disablePadding>
                  {cached.map((p) => (
                    <ListItem key={p.key} disablePadding sx={{ py: 0.4 }}>
                      <ListItemIcon sx={{ minWidth: 32 }}>
                        {p.granted ? <CheckCircle color="success" fontSize="small" /> : <Cancel color="error" fontSize="small" />}
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
          })()}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => permsModalGroup && refreshPermsForGroup(permsModalGroup.telegram_group_id)}
            disabled={permsState[permsModalGroup?.telegram_group_id]?.loading}
          >
            Refresh
          </Button>
          <Button variant="contained" onClick={() => setPermsModalGroup(null)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Link group dialog */}
      <Dialog open={linkOpen} onClose={() => setLinkOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Link a Telegram Group</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            Run <code>/linkgroup</code> in your Telegram group to get a code, then paste it below.
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
          <Button variant="contained" onClick={handleLink} disabled={linking || !linkCode.trim()}>
            {linking ? <CircularProgress size={20} /> : 'Link Group'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Unlink confirm */}
      <Dialog open={!!unlinkTarget} onClose={() => setUnlinkTarget(null)}>
        <DialogTitle>Unlink Group?</DialogTitle>
        <DialogContent>
          <Typography>
            Unlink <strong>{unlinkTarget?.title}</strong>? The bot remains in the group but it won't
            appear in your dashboard.
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
