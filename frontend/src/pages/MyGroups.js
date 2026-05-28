import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Container, Typography, Button, Card, CardContent,
  Chip, CircularProgress, Alert, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, IconButton,
  Tooltip, Grid, Divider, Paper, List, ListItem,
  ListItemIcon, ListItemText, LinearProgress, Collapse,
} from '@mui/material';
import {
  Add, Groups, CheckCircle, LinkOff, Settings, Refresh,
  OpenInNew, Warning, Lock, Security, Cancel, BarChart,
  HelpOutline, ExpandMore, ExpandLess, ArrowBack,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { telegramGroups, bots as botsApi, settings as settingsApi } from '../services/api';
import { track } from '../services/analytics';
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

function PermScoreBadge({ perms, liveScore, liveTotal, isCustomBot, botStatus }) {
  // Use live data when available
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
  // Cached perms present
  if (perms && Object.keys(perms).length > 0) {
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
  // Custom bot with active status — permissions managed by the bot itself
  if (isCustomBot && botStatus === 'active') {
    return <Chip label="Bot Active" color="success" size="small" icon={<CheckCircle sx={{ fontSize: '14px !important' }} />} />;
  }
  return <Chip label="Check permissions" color="default" size="small" />;
}

export default function MyGroups() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const botIdFilter = searchParams.get('bot_id') ? Number(searchParams.get('bot_id')) : null;
  const botTypeFilter = searchParams.get('bot_type'); // 'official' | null

  const [allGroups, setAllGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkCode, setLinkCode] = useState('');
  const [linking, setLinking] = useState(false);
  const [unlinkTarget, setUnlinkTarget] = useState(null);
  const [hubConflictOpen, setHubConflictOpen] = useState(false);

  // Per-card live permission state: { [groupId]: { loading, data } }
  const [permsState, setPermsState] = useState({});

  // Guide collapsed by default when groups exist, expanded when empty
  const [guideOpen, setGuideOpen] = useState(false);

  // Full-screen permissions modal
  const [permsModalGroup, setPermsModalGroup] = useState(null);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setLoadError(false);
    // Retry once after a short delay to handle Railway cold-start / transient errors
    try {
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const res = await telegramGroups.list();
          setAllGroups(res.data.groups || []);
          setLoadError(false);
          return;
        } catch (err) {
          if (process.env.NODE_ENV === 'development') {
            console.error('[MyGroups] load attempt', attempt + 1, err?.response?.status, err?.response?.data || err?.message);
          }
          if (attempt === 0) {
            // Wait 1.5 s before retrying (covers Railway cold start)
            await new Promise((r) => setTimeout(r, 1500));
          } else {
            setLoadError(true);
            toast.error(`Failed to load groups (${err?.response?.status || 'network error'})`);
          }
        }
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // When bot_id is in the URL, show only that custom bot's groups
  const groups = useMemo(() => {
    if (botIdFilter) return allGroups.filter((g) => g.linked_bot_id === botIdFilter);
    if (botTypeFilter === 'official')
      return allGroups.filter(
        (g) => (g.linked_via_bot_type === 'official' || !g.linked_via_bot_type) && !g.linked_bot_id
      );
    return allGroups;
  }, [allGroups, botIdFilter, botTypeFilter]);

  const handleLink = async () => {
    if (!linkCode.trim()) return;
    setLinking(true);
    try {
      const res = await telegramGroups.link({ code: linkCode.trim().toUpperCase() });
      toast.success(`Group "${res.data.group.title}" linked successfully!`);
      track('first_group_linked');
      setLinkOpen(false);
      setLinkCode('');
      load({ silent: true });
    } catch (err) {
      if (err.response?.data?.code === 'HUB_GROUP_CONFLICT') {
        setLinkOpen(false);
        setHubConflictOpen(true);
      } else {
        toast.error(err.response?.data?.error || 'Failed to link group');
      }
    } finally {
      setLinking(false);
    }
  };

  const handleUnlink = async () => {
    if (!unlinkTarget) return;
    try {
      if (unlinkTarget.source === 'legacy' && unlinkTarget.legacy_bot_id) {
        await botsApi.disconnectGroup(unlinkTarget.legacy_bot_id, unlinkTarget.id);
      } else {
        await telegramGroups.unlink(unlinkTarget.telegram_group_id);
      }
      toast.success(`Group "${unlinkTarget.title}" unlinked`);
      setUnlinkTarget(null);
      load({ silent: true });
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
    <Box>
      <TopNav hasSidebar
        breadcrumb={
          botTypeFilter === 'official'
            ? [
                { label: 'Dashboard', path: '/dashboard' },
                { label: 'Official Telegizer Bot', path: '/dashboard' },
                { label: 'Groups' },
              ]
            : [
                { label: 'Dashboard', path: '/dashboard' },
                { label: 'My Groups' },
              ]
        }
        actions={
          <Box sx={{ display: 'flex', gap: 1 }}>
            {botTypeFilter === 'official' ? (
              <Button
                variant="outlined"
                size="small"
                startIcon={<ArrowBack />}
                onClick={() => navigate('/dashboard')}
              >
                Back to Dashboard
              </Button>
            ) : (
              <>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<OpenInNew />}
                  href={addToGroupUrl}
                  target="_blank"
                  rel="noopener noreferrer"
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
              </>
            )}
          </Box>
        }
      />

      <Container maxWidth="xl" sx={{ py: 2.5 }}>
        {/* Filter context banner — shown only when scoped to a bot */}
        {botTypeFilter === 'official' && (
          <Alert
            severity="info"
            icon={<Groups fontSize="small" />}
            sx={{ mb: 2, borderRadius: 2, alignItems: 'center' }}
            action={
              <Button size="small" startIcon={<ArrowBack />} onClick={() => navigate('/dashboard')}>
                Back
              </Button>
            }
          >
            Showing groups connected to <strong>Official Telegizer Bot (@{BOT_USERNAME})</strong> only.{' '}
            <Button size="small" sx={{ p: 0, minWidth: 0, textTransform: 'none', fontWeight: 600 }} onClick={() => navigate('/groups')}>
              View all groups
            </Button>
          </Alert>
        )}

        {/* Compact toolbar row: refresh + collapsible guide */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <IconButton size="small" onClick={load} disabled={loading}>
            <Refresh fontSize="small" />
          </IconButton>
          <Button
            size="small"
            variant="text"
            startIcon={<HelpOutline fontSize="small" />}
            endIcon={guideOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
            onClick={() => setGuideOpen(o => !o)}
            sx={{ color: 'text.secondary', textTransform: 'none', fontSize: '0.8rem' }}
          >
            How to link a group?
          </Button>
        </Box>

        {/* Collapsible guide */}
        <Collapse in={guideOpen || (!loading && groups.length === 0 && !loadError)}>
          <Paper sx={{ px: 2, py: 1.5, mb: 2, background: 'linear-gradient(135deg, rgba(61,142,248,0.07) 0%, rgba(11,22,38,0.9) 100%)', border: '1px solid rgba(61,142,248,0.2)', borderRadius: 2 }}>
            <Typography variant="body2" color="text.secondary">
              1. Add <strong>@{BOT_USERNAME}</strong> as admin &nbsp;·&nbsp;
              2. Run <code>/linkgroup</code> inside the group &nbsp;·&nbsp;
              3. Click <strong>Link Group</strong> above and paste the code
            </Typography>
          </Paper>
        </Collapse>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : loadError ? (
          <Card sx={{ textAlign: 'center', py: 6 }}>
            <Warning sx={{ fontSize: 64, color: 'warning.main', mb: 2 }} />
            <Typography variant="h6" gutterBottom>Couldn't load your groups</Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              A network or server error occurred. Your groups are not gone — please try again.
            </Typography>
            <Button variant="contained" startIcon={<Refresh />} onClick={() => load()}>
              Retry
            </Button>
          </Card>
        ) : groups.length === 0 ? (
          <Card
            sx={{
              textAlign: 'center', py: 7,
              background: 'linear-gradient(135deg, rgba(61,142,248,0.05) 0%, transparent 100%)',
              border: '1px dashed rgba(61,142,248,0.25)',
            }}
          >
            <Box sx={{
              width: 64, height: 64, borderRadius: 3, mx: 'auto', mb: 2,
              background: 'rgba(61,142,248,0.1)', border: '1px solid rgba(61,142,248,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Groups sx={{ fontSize: 30, color: 'rgba(61,142,248,0.7)' }} />
            </Box>
            <Typography variant="h6" gutterBottom fontWeight={700} letterSpacing="-0.01em">No groups linked yet</Typography>
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
              const isCustomBot = !!(g.linked_bot_id || g.linked_via_bot_type === 'custom');

              // Legacy custom bot groups must route to /bot/:botId/group/:groupId so
              // GroupSettings receives the correct bot context and calls the right API.
              // Official groups use /groups/:telegramGroupId (no botId needed).
              const manageRoute = (g.source === 'legacy' && g.legacy_bot_id && g.id)
                ? `/bot/${g.legacy_bot_id}/group/${g.id}`
                : `/groups/${gid}`;
              const analyticsRoute = (g.source === 'legacy' && g.legacy_bot_id && g.id)
                ? `/bot/${g.legacy_bot_id}/group/${g.id}/analytics`
                : `/groups/${gid}/analytics`;

              return (
                <Grid item xs={12} sm={6} lg={groups.length > 2 ? 4 : 6} key={gid}>
                  <Card
                    sx={{
                      height: '100%',
                      transition: 'transform 0.2s cubic-bezier(0.22,1,0.36,1), box-shadow 0.2s, border-color 0.2s',
                      '&:hover': {
                        transform: 'translateY(-2px)',
                        boxShadow: '0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(61,142,248,0.22)',
                        borderColor: 'rgba(61,142,248,0.28)',
                      },
                    }}
                  >
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
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
                        <Box>
                          <Typography variant="caption" color="text.secondary">Bot Type</Typography>
                          <Typography variant="body2" fontWeight={500}>
                            {g.linked_via_bot_type === 'official'
                              ? '🟢 Official Telegizer'
                              : `🔵 ${g.linked_bot_name || (g.linked_bot_username ? `@${g.linked_bot_username}` : 'Custom Bot')}`}
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
                                isCustomBot={isCustomBot}
                                botStatus={g.bot_status}
                              />
                            )}
                            {!isCustomBot && (
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
                            )}
                            {!isCustomBot && (
                              <Tooltip title="View detailed permissions">
                                <IconButton size="small" onClick={() => openPermissionsModal(g)} sx={{ p: 0.25 }}>
                                  <Security fontSize="small" />
                                </IconButton>
                              </Tooltip>
                            )}
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

                      {/* Actions — three equal-width buttons in a single row */}
                      <Box sx={{ display: 'flex', gap: 1, mt: 0.5 }}>
                        <Button
                          size="small"
                          variant="contained"
                          startIcon={<Settings sx={{ fontSize: '0.95rem !important' }} />}
                          onClick={() => navigate(manageRoute)}
                          sx={{
                            flex: 1,
                            fontSize: '0.72rem',
                            fontWeight: 600,
                            letterSpacing: 0.2,
                            textTransform: 'none',
                            py: 0.75,
                            borderRadius: 1.5,
                            boxShadow: 'none',
                            '&:hover': { boxShadow: '0 2px 8px rgba(33,150,243,0.25)', transform: 'translateY(-1px)' },
                            transition: 'transform 0.15s, box-shadow 0.15s',
                          }}
                        >
                          Settings
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          startIcon={<BarChart sx={{ fontSize: '0.95rem !important' }} />}
                          onClick={() => navigate(analyticsRoute)}
                          sx={{
                            flex: 1,
                            fontSize: '0.72rem',
                            fontWeight: 600,
                            letterSpacing: 0.2,
                            textTransform: 'none',
                            py: 0.75,
                            borderRadius: 1.5,
                            '&:hover': { bgcolor: 'primary.main', color: '#fff', borderColor: 'primary.main', transform: 'translateY(-1px)' },
                            transition: 'transform 0.15s, background-color 0.15s, color 0.15s',
                          }}
                        >
                          Analytics
                        </Button>
                        <Tooltip title={g.source === 'legacy' && !g.legacy_bot_id ? 'Use the bot page to manage legacy groups' : isCustomBot ? 'Unlink from custom bot' : 'Unlink group'}>
                          <span style={{ flex: 1, display: 'flex' }}>
                            <Button
                              size="small"
                              variant="outlined"
                              color="error"
                              startIcon={<LinkOff sx={{ fontSize: '0.95rem !important' }} />}
                              onClick={() => setUnlinkTarget(g)}
                              disabled={g.source === 'legacy' && !g.legacy_bot_id}
                              sx={{
                                flex: 1,
                                fontSize: '0.72rem',
                                fontWeight: 600,
                                letterSpacing: 0.2,
                                textTransform: 'none',
                                py: 0.75,
                                borderRadius: 1.5,
                                ...(g.source !== 'legacy' && {
                                  borderColor: 'error.main',
                                  color: 'error.main',
                                }),
                                '&:hover': { bgcolor: 'error.main', color: '#fff', borderColor: 'error.main', transform: 'translateY(-1px)' },
                                transition: 'transform 0.15s, background-color 0.15s, color 0.15s',
                              }}
                            >
                              Unlink
                            </Button>
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
      <Dialog open={!!unlinkTarget} onClose={() => setUnlinkTarget(null)} fullWidth maxWidth="xs">
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

      {/* Hub conflict dialog */}
      <Dialog open={hubConflictOpen} onClose={() => setHubConflictOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Group Already in Echo</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1 }}>
            This group is already connected to <strong>Echo</strong>.
          </Typography>
          <Typography variant="body2" sx={{ mb: 1 }}>
            Echo groups and Group Management groups are separate. Mixing them
            would apply moderation features (XP, welcome messages, analytics, warnings)
            to a private assistant group.
          </Typography>
          <Typography variant="body2">
            To use this group for Group Management, first disconnect it from Echo.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHubConflictOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => { setHubConflictOpen(false); navigate('/ark'); }}
          >
            Open Echo
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}


