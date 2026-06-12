import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Container, Typography, Button, Card, CardContent, CardActions, Grid, Avatar,
  CircularProgress, Alert, Chip, Stack, IconButton, Badge, Menu, MenuItem,
  ListItemText, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Divider, Tooltip, Collapse, Paper, List, ListItem, ListItemIcon,
} from '@mui/material';
import {
  Forum, Add, OpenInNew, AdminPanelSettings, SmartToy, Notifications, Redeem,
  CheckCircle, Settings, Refresh, BarChart, LinkOff, Security, HelpOutline,
  ExpandMore, ExpandLess, Groups, ArrowBack, Shield, Lock,
} from '@mui/icons-material';
import guildizerApi, { guildizerLoginUrl } from '../../services/guildizerApi';

const OAUTH_ERRORS = {
  invalid_state: 'Login session expired — please try connecting again.',
  oauth_failed: 'Could not reach Discord. Please try again.',
  access_denied: 'You cancelled the Discord authorization.',
};

// The permission set Guildizer's bot is invited with (mirrors backend _INVITE_BITS),
// surfaced in the per-server permissions modal — the Discord analogue of Telegizer's
// "bot permissions" feature.
const DISCORD_PERMISSIONS = [
  { label: 'Kick Members',        feature: 'Remove disruptive members' },
  { label: 'Ban Members',         feature: 'Bans & raid defense' },
  { label: 'Manage Channels',     feature: 'Lockdown & channel automation' },
  { label: 'Manage Server',       feature: 'Server settings & invites' },
  { label: 'Add Reactions',       feature: 'Emoji reactions & starboard' },
  { label: 'View Channels',       feature: 'Read server channels' },
  { label: 'Send Messages',       feature: 'Replies & announcements' },
  { label: 'Manage Messages',     feature: 'AutoMod deletion & pins' },
  { label: 'Embed Links',         feature: 'Rich embeds' },
  { label: 'Attach Files',        feature: 'Transcripts & exports' },
  { label: 'Read Message History',feature: 'Context for moderation' },
  { label: 'Manage Nicknames',    feature: 'Nickname enforcement' },
  { label: 'Manage Roles',        feature: 'Self-roles & level roles' },
  { label: 'Manage Webhooks',     feature: 'Forwarding & integrations' },
  { label: 'Moderate Members',    feature: 'Timeout / mute' },
];

export default function GuildizerServers() {
  const navigate = useNavigate();
  const [params, setSearchParams] = useSearchParams();
  const [state, setState] = useState({ loading: true, connected: false, guilds: [], inviteUrl: null });
  const [error, setError] = useState(OAUTH_ERRORS[params.get('error')] || null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [redeemOpen, setRedeemOpen] = useState(false);
  const [permsModalGuild, setPermsModalGuild] = useState(null);
  const [unlinkTarget, setUnlinkTarget] = useState(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Scoped view — the hero card's "Manage Servers" button filters to installed servers.
  const filter = params.get('filter'); // 'installed' | null

  const load = async ({ silent = false } = {}) => {
    if (silent) setRefreshing(true);
    try {
      const { data: me } = await guildizerApi.get('/auth/me'); // 401 → not connected
      const { data } = await guildizerApi.get('/api/guilds');
      setState({ loading: false, connected: true, guilds: data.guilds, inviteUrl: data.invite_url });
      setIsAdmin(!!me.is_admin);
    } catch (e) {
      if (e?.response?.status === 401) setState({ loading: false, connected: false, guilds: [], inviteUrl: null });
      else { setError('Failed to load your Discord servers.'); setState((s) => ({ ...s, loading: false })); }
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data: me } = await guildizerApi.get('/auth/me');
        const { data } = await guildizerApi.get('/api/guilds');
        if (alive) {
          setState({ loading: false, connected: true, guilds: data.guilds, inviteUrl: data.invite_url });
          setIsAdmin(!!me.is_admin);
        }
      } catch (e) {
        if (!alive) return;
        if (e?.response?.status === 401) setState({ loading: false, connected: false, guilds: [], inviteUrl: null });
        else { setError('Failed to load your Discord servers.'); setState((s) => ({ ...s, loading: false })); }
      }
    })();
    return () => { alive = false; };
  }, []);

  const installedCount = useMemo(
    () => state.guilds.filter((g) => g.bot_present).length,
    [state.guilds],
  );

  const visibleGuilds = useMemo(
    () => (filter === 'installed' ? state.guilds.filter((g) => g.bot_present) : state.guilds),
    [state.guilds, filter],
  );

  if (state.loading) {
    return <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 320 }}><CircularProgress /></Box>;
  }

  return (
    <Container maxWidth="xl" sx={{ py: 2.5 }}>
      {/* Page header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <Forum color="primary" />
        <Typography variant="h5" fontWeight={800}>Discord</Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Manage your Discord servers with Guildizer — moderation, leveling, campaigns and more.
      </Typography>

      {error && <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}

      {!state.connected ? (
        <Card variant="outlined" sx={{ maxWidth: 460, mx: 'auto', textAlign: 'center' }}>
          <CardContent sx={{ p: 4 }}>
            <Forum sx={{ fontSize: 44, color: 'primary.main', mb: 1 }} />
            <Typography variant="h6" fontWeight={700} mb={0.5}>Connect your Discord</Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              Authorize Discord to see and manage the servers you run. We request <b>identify</b> and <b>guilds</b> only.
            </Typography>
            <Button
              variant="contained" size="large" startIcon={<Forum />}
              onClick={() => { window.location.href = guildizerLoginUrl(); }}
            >
              Continue with Discord
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* ── Official Guildizer Bot hero card ── */}
          <OfficialBotCard
            installedCount={installedCount}
            inviteUrl={state.inviteUrl}
            onManage={() => setSearchParams({ filter: 'installed' }, { replace: true })}
          />

          {/* Secondary controls row (Guildizer-specific) */}
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 1, mb: 2, flexWrap: 'wrap' }}>
            {isAdmin && (
              <Button size="small" variant="outlined" startIcon={<AdminPanelSettings />} onClick={() => navigate('/guildizer/admin')}>
                Admin
              </Button>
            )}
            <Button size="small" variant="outlined" startIcon={<SmartToy />} onClick={() => navigate('/guildizer/bots')}>
              My Bots
            </Button>
            <Button size="small" variant="outlined" startIcon={<Redeem />} onClick={() => setRedeemOpen(true)}>
              Redeem code
            </Button>
            <NotificationsBell />
          </Box>

          {/* Filter context banner — shown only when scoped to installed servers */}
          {filter === 'installed' && (
            <Alert
              severity="info"
              icon={<Groups fontSize="small" />}
              sx={{ mb: 2, borderRadius: 2, alignItems: 'center' }}
              action={
                <Button size="small" startIcon={<ArrowBack />} onClick={() => setSearchParams({}, { replace: true })}>
                  Back
                </Button>
              }
            >
              Showing servers where <strong>Guildizer is installed</strong> only.{' '}
              <Button size="small" sx={{ p: 0, minWidth: 0, textTransform: 'none', fontWeight: 600 }} onClick={() => setSearchParams({}, { replace: true })}>
                View all servers
              </Button>
            </Alert>
          )}

          {/* Compact toolbar row: refresh + collapsible guide + Add to a server */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <IconButton size="small" onClick={() => load({ silent: true })} disabled={refreshing}>
              {refreshing ? <CircularProgress size={16} /> : <Refresh fontSize="small" />}
            </IconButton>
            <Button
              size="small"
              variant="text"
              startIcon={<HelpOutline fontSize="small" />}
              endIcon={guideOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
              onClick={() => setGuideOpen((o) => !o)}
              sx={{ color: 'text.secondary', textTransform: 'none', fontSize: '0.8rem' }}
            >
              How to link a server?
            </Button>
            {state.inviteUrl && (
              <Button
                size="small"
                variant="outlined"
                startIcon={<Add fontSize="small" />}
                href={state.inviteUrl}
                target="_blank"
                rel="noreferrer"
                sx={{ ml: 'auto' }}
              >
                Add to a server
              </Button>
            )}
          </Box>

          {/* Collapsible guide */}
          <Collapse in={guideOpen || (visibleGuilds.length === 0)}>
            <Paper sx={{ px: 2, py: 1.5, mb: 2, background: 'linear-gradient(135deg, rgba(88,101,242,0.07) 0%, rgba(11,22,38,0.9) 100%)', border: '1px solid rgba(88,101,242,0.2)', borderRadius: 2 }}>
              <Typography variant="body2" color="text.secondary">
                1. Click <strong>Add to a server</strong> &nbsp;·&nbsp;
                2. Pick the server &amp; approve Guildizer's permissions &nbsp;·&nbsp;
                3. It appears below — open <strong>Settings</strong> to configure it
              </Typography>
              <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>
                You need the <b>Manage Server</b> permission, or to own the server.
              </Typography>
            </Paper>
          </Collapse>

          {visibleGuilds.length === 0 ? (
            <Card variant="outlined"><CardContent sx={{ textAlign: 'center', py: 5 }}>
              <Groups sx={{ fontSize: 40, color: 'text.disabled', mb: 1 }} />
              <Typography color="text.secondary" gutterBottom>
                {filter === 'installed' ? 'Guildizer is not installed on any server yet.' : 'No manageable servers found.'}
              </Typography>
              <Typography variant="caption" color="text.disabled" display="block">
                You need the <b>Manage Server</b> permission, or to own the server.
              </Typography>
              {state.inviteUrl && (
                <Button sx={{ mt: 2 }} variant="contained" startIcon={<Add />} href={state.inviteUrl} target="_blank" rel="noreferrer">
                  Add Guildizer to a server
                </Button>
              )}
            </CardContent></Card>
          ) : (
            <Grid container spacing={2}>
              {visibleGuilds.map((g) => (
                <ServerCard
                  key={g.id}
                  guild={g}
                  count={visibleGuilds.length}
                  navigate={navigate}
                  onViewPerms={() => setPermsModalGuild(g)}
                  onUnlink={() => setUnlinkTarget(g)}
                />
              ))}
            </Grid>
          )}
        </>
      )}

      <RedeemDialog open={redeemOpen} onClose={() => setRedeemOpen(false)} />
      <PermissionsDialog guild={permsModalGuild} onClose={() => setPermsModalGuild(null)} />
      <UnlinkDialog guild={unlinkTarget} onClose={() => setUnlinkTarget(null)} />
    </Container>
  );
}

// ── Official Guildizer Bot hero card (mirrors Telegizer's OfficialBotSection) ──
function OfficialBotCard({ installedCount, inviteUrl, onManage }) {
  return (
    <Card
      sx={{
        mb: 2,
        border: '1px solid',
        borderColor: 'rgba(88,101,242,0.3)',
        background: 'linear-gradient(135deg, rgba(88,101,242,0.06) 0%, rgba(11,22,38,0.9) 100%)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.4), 0 0 0 1px rgba(88,101,242,0.15)',
        transition: 'box-shadow 0.2s ease',
        '&:hover': { boxShadow: '0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(88,101,242,0.3)' },
      }}
    >
      <CardContent sx={{ pb: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Avatar
            sx={{
              mr: 1.5, width: 40, height: 40,
              background: 'linear-gradient(135deg, #5865f2, #22d3ee)',
              boxShadow: '0 0 14px rgba(88,101,242,0.4)',
            }}
          >
            <SmartToy fontSize="small" />
          </Avatar>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" fontWeight={700} letterSpacing="-0.01em">Official Guildizer Bot</Typography>
            <Typography variant="body2" color="text.secondary" noWrap>@Guildizer · Shared · Always Active</Typography>
          </Box>
          <Chip label="Active" color="success" size="small" sx={{ boxShadow: '0 0 8px rgba(34,197,94,0.4)' }} />
        </Box>
        <Typography variant="caption" color="text.disabled">
          {installedCount} server{installedCount !== 1 ? 's' : ''} linked · Free for all verified users
        </Typography>
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2, pt: 1, gap: 1 }}>
        {inviteUrl && (
          <Button size="small" variant="contained" component="a" href={inviteUrl} target="_blank" rel="noopener noreferrer"
            startIcon={<Add />}>
            Add to Server
          </Button>
        )}
        <Button size="small" startIcon={<Groups />} onClick={onManage}>
          Manage Servers ({installedCount})
        </Button>
      </CardActions>
    </Card>
  );
}

function NotificationsBell() {
  const [anchor, setAnchor] = useState(null);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    guildizerApi.get('/api/notifications')
      .then(({ data }) => { setItems(data.notifications); setUnread(data.unread); })
      .catch(() => {});
  }, []);

  const openMenu = (e) => {
    setAnchor(e.currentTarget);
    if (unread > 0) {
      guildizerApi.post('/api/notifications/read').then(() => setUnread(0)).catch(() => {});
    }
  };

  return (
    <>
      <IconButton onClick={openMenu}>
        <Badge badgeContent={unread} color="error"><Notifications /></Badge>
      </IconButton>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        {items.length === 0 && <MenuItem disabled>No notifications</MenuItem>}
        {items.map((n) => (
          <MenuItem key={n.id} sx={{ whiteSpace: 'normal', maxWidth: 360 }} onClick={() => setAnchor(null)}>
            <ListItemText primary={n.title} secondary={n.body}
              primaryTypographyProps={{ fontWeight: n.read ? 400 : 700, variant: 'body2' }} />
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

function RedeemDialog({ open, onClose }) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  async function redeem() {
    setBusy(true); setMsg(null);
    try {
      const { data } = await guildizerApi.post('/api/team/redeem', { code: code.trim() });
      setMsg({ ok: true, text: `You now have dashboard access to ${data.guild.name}. Reload to see it.` });
      setCode('');
    } catch (e) {
      setMsg({ ok: false, text: e?.response?.status === 404 ? 'That code is invalid, used, or expired.' : 'Something went wrong.' });
    }
    setBusy(false);
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Redeem a team invite</DialogTitle>
      <DialogContent>
        {msg && <Alert severity={msg.ok ? 'success' : 'error'} sx={{ mb: 1.5 }}>{msg.text}</Alert>}
        <TextField autoFocus fullWidth size="small" label="Invite code" value={code}
          onChange={(e) => setCode(e.target.value)} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        <Button variant="contained" disabled={busy || !code.trim()} onClick={redeem}>Redeem</Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Telegizer-parity server card ──────────────────────────────────────────────
function ServerCard({ guild, count, navigate, onViewPerms, onUnlink }) {
  const initials = (guild.name || '?').slice(0, 2).toUpperCase();
  const installed = guild.bot_present;
  const isCustomBot = !!guild.custom_bot_id;

  return (
    <Grid item xs={12} sm={6} lg={count > 2 ? 4 : 6}>
      <Card
        sx={{
          height: '100%',
          transition: 'transform 0.2s cubic-bezier(0.22,1,0.36,1), box-shadow 0.2s, border-color 0.2s',
          '&:hover': {
            transform: 'translateY(-2px)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(88,101,242,0.22)',
            borderColor: 'rgba(88,101,242,0.28)',
          },
        }}
      >
        <CardContent>
          {/* Title + status */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ flex: 1, minWidth: 0 }}>
              <Avatar src={guild.icon_url || undefined} variant="rounded" sx={{ width: 40, height: 40, fontWeight: 700 }}>
                {initials}
              </Avatar>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="h6" noWrap fontWeight={600}>{guild.name}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                  ID: {guild.id}
                </Typography>
              </Box>
            </Stack>
            {installed
              ? <Chip label="Active" color="success" size="small" />
              : <Chip label="Not installed" size="small" />}
          </Box>

          <Divider sx={{ my: 1.5 }} />

          {/* Bot type + permissions row */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
            <Box>
              <Typography variant="caption" color="text.secondary">Bot Type</Typography>
              <Typography variant="body2" fontWeight={500}>
                {isCustomBot ? '🔵 Custom Bot' : '🟢 Official Guildizer'}
              </Typography>
            </Box>
            <Box sx={{ textAlign: 'right' }}>
              <Typography variant="caption" color="text.secondary" display="block">
                Permissions
              </Typography>
              <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', justifyContent: 'flex-end', mt: 0.25 }}>
                {installed
                  ? <Chip label="Full Access" color="success" size="small" icon={<CheckCircle sx={{ fontSize: '14px !important' }} />} />
                  : <Chip label="Not installed" size="small" />}
                <Tooltip title="View Guildizer's permissions">
                  <IconButton size="small" onClick={onViewPerms} sx={{ p: 0.25 }}>
                    <Security fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
            </Box>
          </Box>

          <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
            {guild.member_count?.toLocaleString?.() || guild.member_count || 0} members
            {guild.is_owner && ' · Owner'}
            {guild.is_pro && ' · Pro'}
          </Typography>

          {/* Actions — three equal-width buttons in a single row */}
          {installed ? (
            <Box sx={{ display: 'flex', gap: 1, mt: 0.5 }}>
              <Button
                size="small"
                variant="contained"
                startIcon={<Settings sx={{ fontSize: '0.95rem !important' }} />}
                onClick={() => navigate(`/guildizer/servers/${guild.id}`)}
                sx={cardBtn(true)}
              >
                Settings
              </Button>
              <Button
                size="small"
                variant="outlined"
                startIcon={<BarChart sx={{ fontSize: '0.95rem !important' }} />}
                onClick={() => navigate(`/guildizer/servers/${guild.id}?tab=Analytics&sub=Overview`)}
                sx={cardBtn(false)}
              >
                Analytics
              </Button>
              <Tooltip title="How to remove Guildizer">
                <span style={{ flex: 1, display: 'flex' }}>
                  <Button
                    size="small"
                    variant="outlined"
                    color="error"
                    startIcon={<LinkOff sx={{ fontSize: '0.95rem !important' }} />}
                    onClick={onUnlink}
                    sx={{
                      ...cardBtn(false),
                      borderColor: 'error.main',
                      color: 'error.main',
                      '&:hover': { bgcolor: 'error.main', color: '#fff', borderColor: 'error.main', transform: 'translateY(-1px)' },
                    }}
                  >
                    Unlink
                  </Button>
                </span>
              </Tooltip>
            </Box>
          ) : (
            <Button fullWidth variant="contained" endIcon={<OpenInNew />} href={guild.invite_url} target="_blank" rel="noreferrer">
              Add Guildizer
            </Button>
          )}
        </CardContent>
      </Card>
    </Grid>
  );
}

const cardBtn = (primary) => ({
  flex: 1,
  fontSize: '0.72rem',
  fontWeight: 600,
  letterSpacing: 0.2,
  textTransform: 'none',
  py: 0.75,
  borderRadius: 1.5,
  ...(primary && { boxShadow: 'none' }),
  '&:hover': primary
    ? { boxShadow: '0 2px 8px rgba(88,101,242,0.25)', transform: 'translateY(-1px)' }
    : { bgcolor: 'primary.main', color: '#fff', borderColor: 'primary.main', transform: 'translateY(-1px)' },
  transition: 'transform 0.15s, box-shadow 0.15s, background-color 0.15s, color 0.15s',
});

// ── Permissions detail modal (mirrors Telegizer's bot-permissions modal) ──────
function PermissionsDialog({ guild, onClose }) {
  return (
    <Dialog open={!!guild} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Lock fontSize="small" />
        Bot Permissions — {guild?.name}
      </DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
          <Typography variant="body2" color="text.secondary">Status:</Typography>
          {guild?.bot_present
            ? <Chip label="Full Access" color="success" size="small" icon={<CheckCircle sx={{ fontSize: '14px !important' }} />} />
            : <Chip label="Not installed" size="small" />}
        </Box>
        <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
          Guildizer is invited with the permissions below. They unlock the matching features —
          remove any in Discord → Server Settings → Roles → Guildizer to restrict it.
        </Typography>
        <List dense disablePadding>
          {DISCORD_PERMISSIONS.map((p) => (
            <ListItem key={p.label} disablePadding sx={{ py: 0.4 }}>
              <ListItemIcon sx={{ minWidth: 32 }}>
                <CheckCircle color={guild?.bot_present ? 'success' : 'disabled'} fontSize="small" />
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
      </DialogContent>
      <DialogActions>
        <Button variant="contained" onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Unlink helper (Discord has no dashboard unlink — explain the real flow) ────
function UnlinkDialog({ guild, onClose }) {
  return (
    <Dialog open={!!guild} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Shield fontSize="small" /> Remove Guildizer?
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 1.5 }}>
          To stop managing <strong>{guild?.name}</strong>, remove the Guildizer bot from your
          Discord server:
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Open <strong>{guild?.name}</strong> in Discord → <strong>Server Settings</strong> →
          <strong> Members</strong> (or <strong>Integrations</strong>) → find <strong>Guildizer</strong> →
          <strong> Kick</strong>. It will disappear from this dashboard on its next sync.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
