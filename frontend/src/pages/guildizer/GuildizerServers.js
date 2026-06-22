import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Container, Typography, Button, Card, CardContent, CardActions, Grid, Avatar,
  CircularProgress, Alert, Chip, Stack, IconButton,
  ListItemText, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Divider, Tooltip, Collapse, Paper, List, ListItem, ListItemIcon, LinearProgress,
  InputAdornment,
} from '@mui/material';
import {
  Forum, Add, OpenInNew, AdminPanelSettings, SmartToy, Redeem, CardGiftcard,
  CheckCircle, Settings, Refresh, BarChart, LinkOff, Security, HelpOutline,
  ExpandMore, ExpandLess, Groups, ArrowBack, Shield, Lock, Search, Close,
  Delete, Code,
} from '@mui/icons-material';
import guildizerApi, { guildizerLoginUrl, guildizerNotifications } from '../../services/guildizerApi';
import { ConnectWizard } from './GuildizerBots';
import NotificationBell from '../../components/NotificationBell';
import PushNudge from '../../components/PushNudge';

// Mirrors the backend MAX_BOTS_PER_USER (custom_bots_api.py).
const MAX_CUSTOM_BOTS = 5;

// Per request, the Servers view hides the "Invite Friends" button, the
// notification bell, and the web-push nudge banner — these already live
// elsewhere (Referrals page, global TopNav bell, Notifications). Hidden, not
// removed: flip to true to restore them here.
const SHOW_SERVER_EXTRAS = false;

const BOT_STATUS_CHIP = {
  active: { color: 'success', label: 'Active' },
  error: { color: 'error', label: 'Needs attention' },
  disabled: { color: 'default', label: 'Disabled' },
};

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
  const [params] = useSearchParams();
  const [state, setState] = useState({ loading: true, connected: false, guilds: [], inviteUrl: null });
  const [bots, setBots] = useState([]);
  const [error, setError] = useState(OAUTH_ERRORS[params.get('error')] || null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [redeemOpen, setRedeemOpen] = useState(false);
  const [addBotOpen, setAddBotOpen] = useState(false);
  const [botSearch, setBotSearch] = useState('');

  // Custom (white-label) bots are best-effort: a failure here must never block the
  // servers page, so it has its own try/catch and never sets the page error.
  const loadBots = async () => {
    try {
      const { data } = await guildizerApi.get('/api/custom-bots');
      setBots(data.bots || []);
    } catch { /* leave bots as-is; the official bot card still renders */ }
  };

  // Old in-page "Manage Servers" used ?filter=installed; that now lives on its own
  // route (/guildizer/servers). Redirect saved links/bookmarks so they keep working.
  useEffect(() => {
    if (params.get('filter') === 'installed') navigate('/guildizer/servers', { replace: true });
  }, [params, navigate]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data: me } = await guildizerApi.get('/auth/me');
        const { data } = await guildizerApi.get('/api/guilds');
        if (alive) {
          setState({ loading: false, connected: true, guilds: data.guilds, inviteUrl: data.invite_url });
          setIsAdmin(!!me.is_admin);
          await loadBots();
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

  // Custom bots are a Pro feature (custom_bots_api.py): gate "Add Bot" on owning
  // at least one Pro server, mirroring the backend's pro_required guard.
  const hasPro = useMemo(() => state.guilds.some((g) => g.is_pro), [state.guilds]);

  const filteredBots = useMemo(() => {
    const q = botSearch.trim().toLowerCase();
    if (!q) return bots;
    return bots.filter((b) => (b.bot_username || '').toLowerCase().includes(q));
  }, [bots, botSearch]);

  // Full-page redirect into Discord OAuth. Pre-auth, every action on the preview
  // cards routes here — nothing in the dashboard works until the account is linked.
  const connect = () => { window.location.href = guildizerLoginUrl(); };

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

      {/* One-time "Connect your Discord" banner — pinned at the top while signed
          out, auto-hides the moment the account is linked. The full layout
          (official bot + community bots) renders below it either way. */}
      {!state.connected && <ConnectBanner onConnect={connect} />}

      {/* ── Official Guildizer Bot hero card (always visible) ── */}
      <OfficialBotCard
        connected={state.connected}
        installedCount={installedCount}
        inviteUrl={state.inviteUrl}
        onManage={() => navigate('/guildizer/servers')}
        onConnect={connect}
      />

      {/* Secondary controls row — only meaningful once connected (all auth-gated). */}
      {state.connected && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 1, mb: 2, flexWrap: 'wrap' }}>
          {isAdmin && (
            <Button size="small" variant="outlined" startIcon={<AdminPanelSettings />} onClick={() => navigate('/guildizer/admin')}>
              Admin
            </Button>
          )}
          {SHOW_SERVER_EXTRAS && (
            <Button size="small" variant="outlined" startIcon={<CardGiftcard />} onClick={() => navigate('/guildizer/referrals')}>
              Invite Friends
            </Button>
          )}
          <Button size="small" variant="outlined" startIcon={<Redeem />} onClick={() => setRedeemOpen(true)}>
            Redeem code
          </Button>
          {SHOW_SERVER_EXTRAS && <NotificationsBell />}
        </Box>
      )}

      {/* Soft, frequency-capped prompt to enable web push for Guildizer. */}
      {SHOW_SERVER_EXTRAS && state.connected && (
        <PushNudge
          api={guildizerNotifications}
          ns="gz"
          label="Turn on notifications so you never miss raids, anti-nuke alerts and reports on your servers."
        />
      )}

      {/* ── Community (custom) bots, mirroring the Telegizer dashboard's
            Community Bots section. The linked servers live on their own page
            (/guildizer/servers) via the hero card's button. ── */}
      <CommunityBotsSection
        connected={state.connected}
        bots={bots}
        filteredBots={filteredBots}
        hasPro={hasPro}
        search={botSearch}
        onSearch={setBotSearch}
        onAdd={() => setAddBotOpen(true)}
        onConnect={connect}
        onChanged={loadBots}
        navigate={navigate}
      />

      <ConnectWizard
        open={addBotOpen}
        onClose={() => setAddBotOpen(false)}
        onConnected={() => { setAddBotOpen(false); loadBots(); }}
      />
      <RedeemDialog open={redeemOpen} onClose={() => setRedeemOpen(false)} />
    </Container>
  );
}

// ── One-time "Connect your Discord" banner (signed-out only) ──────────────────
function ConnectBanner({ onConnect }) {
  return (
    <Card
      sx={{
        mb: 2,
        border: '1px solid',
        borderColor: 'rgba(88,101,242,0.35)',
        background: 'linear-gradient(135deg, rgba(88,101,242,0.12) 0%, rgba(11,22,38,0.9) 100%)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.4), 0 0 0 1px rgba(88,101,242,0.18)',
      }}
    >
      <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap', py: 2 }}>
        <Avatar
          sx={{
            width: 42, height: 42, flexShrink: 0,
            background: 'linear-gradient(135deg, #5865f2, #22d3ee)',
            boxShadow: '0 0 14px rgba(88,101,242,0.4)',
          }}
        >
          <Forum fontSize="small" />
        </Avatar>
        <Box sx={{ flexGrow: 1, minWidth: 200 }}>
          <Typography variant="subtitle1" fontWeight={700} letterSpacing="-0.01em">Connect your Discord</Typography>
          <Typography variant="body2" color="text.secondary">
            Authorize Discord to see and manage the servers you run. We request <b>identify</b> and <b>guilds</b> only.
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<Forum />} onClick={onConnect} sx={{ flexShrink: 0 }}>
          Continue with Discord
        </Button>
      </CardContent>
    </Card>
  );
}

// ── Official Guildizer Bot hero card (mirrors Telegizer's OfficialBotSection) ──
// Always rendered. Pre-auth it shows a generic "preview" (no live counts) and its
// action buttons funnel into the Discord connect flow.
function OfficialBotCard({ connected, installedCount, inviteUrl, onManage, onConnect }) {
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
          {connected
            ? `${installedCount} server${installedCount !== 1 ? 's' : ''} linked · Free for all verified users`
            : 'Free for all verified users · Connect Discord to link your servers'}
        </Typography>
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2, pt: 1, gap: 1 }}>
        {connected && inviteUrl ? (
          <Button size="small" variant="contained" component="a" href={inviteUrl} target="_blank" rel="noopener noreferrer"
            startIcon={<Add />}>
            Add to Server
          </Button>
        ) : (
          <Button size="small" variant="contained" startIcon={<Add />} onClick={onConnect}>
            Add to Server
          </Button>
        )}
        <Button size="small" startIcon={<Groups />} onClick={connected ? onManage : onConnect}>
          Manage Servers{connected ? ` (${installedCount})` : ''}
        </Button>
      </CardActions>
    </Card>
  );
}

// ── "Manage Servers" view — the linked-server cards, shown only after the user
//    clicks "Manage Servers" on the hero card (mirrors Telegizer's Manage Groups) ──
export function ManageServersView({
  visibleGuilds, inviteUrl, refreshing, guideOpen,
  onToggleGuide, onRefresh, onBack, navigate, onViewPerms, onUnlink,
}) {
  return (
    <>
      {/* Scope banner */}
      <Alert
        severity="info"
        icon={<Groups fontSize="small" />}
        sx={{ mb: 2, borderRadius: 2, alignItems: 'center' }}
        action={
          <Button size="small" startIcon={<ArrowBack />} onClick={onBack}>
            Back
          </Button>
        }
      >
        Showing the servers where <strong>Guildizer is installed</strong>.
      </Alert>

      {/* Compact toolbar row: refresh + collapsible guide + Add to a server */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
        <IconButton size="small" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? <CircularProgress size={16} /> : <Refresh fontSize="small" />}
        </IconButton>
        <Button
          size="small"
          variant="text"
          startIcon={<HelpOutline fontSize="small" />}
          endIcon={guideOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
          onClick={onToggleGuide}
          sx={{ color: 'text.secondary', textTransform: 'none', fontSize: '0.8rem' }}
        >
          How to link a server?
        </Button>
        {inviteUrl && (
          <Button
            size="small"
            variant="outlined"
            startIcon={<Add fontSize="small" />}
            href={inviteUrl}
            target="_blank"
            rel="noreferrer"
            sx={{ ml: 'auto' }}
          >
            Add to a server
          </Button>
        )}
      </Box>

      {/* Collapsible guide */}
      <Collapse in={guideOpen || visibleGuilds.length === 0}>
        <Paper sx={{ px: 2, py: 1.5, mb: 2, background: 'linear-gradient(135deg, rgba(88,101,242,0.07) 0%, rgba(11,22,38,0.9) 100%)', border: '1px solid rgba(88,101,242,0.2)', borderRadius: 2 }}>
          <Typography variant="body2" color="text.secondary">
            1. Click <strong>Add to a server</strong> &nbsp;·&nbsp;
            2. Pick the server &amp; approve Guildizer's permissions &nbsp;·&nbsp;
            3. It appears here — open <strong>Settings</strong> to configure it
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
            Guildizer is not installed on any server yet.
          </Typography>
          <Typography variant="caption" color="text.disabled" display="block">
            You need the <b>Manage Server</b> permission, or to own the server.
          </Typography>
          {inviteUrl && (
            <Button sx={{ mt: 2 }} variant="contained" startIcon={<Add />} href={inviteUrl} target="_blank" rel="noreferrer">
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
              onViewPerms={() => onViewPerms(g)}
              onUnlink={() => onUnlink(g)}
            />
          ))}
        </Grid>
      )}
    </>
  );
}

// ── Community Bots section — the default Servers view. White-label custom bots,
//    laid out to match the Telegizer dashboard's Community Bots section 1:1. ──
function CommunityBotsSection({ connected, bots, filteredBots, hasPro, search, onSearch, onAdd, onConnect, onChanged, navigate }) {
  const count = bots.length;
  const atLimit = count >= MAX_CUSTOM_BOTS;
  const slotsFree = MAX_CUSTOM_BOTS - count;
  const nearLimit = slotsFree <= 1 && !atLimit;

  return (
    <>
      {/* Header bar */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
        <Avatar
          sx={{
            width: 36, height: 36, flexShrink: 0,
            background: 'linear-gradient(135deg, #9d6cf7, #5b21b6)',
            boxShadow: '0 0 12px rgba(157,108,247,0.35)',
          }}
        >
          <SmartToy sx={{ fontSize: 18 }} />
        </Avatar>
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography variant="subtitle1" fontWeight={700} lineHeight={1.2} letterSpacing="-0.01em">Community Bots</Typography>
          <Typography variant="caption" color="text.secondary">
            {count} / {MAX_CUSTOM_BOTS} used · {hasPro ? 'Pro' : 'Free'} plan
          </Typography>
        </Box>
        <Chip
          label={atLimit ? 'Limit Reached' : `${slotsFree} slot${slotsFree !== 1 ? 's' : ''} free`}
          color={atLimit ? 'error' : nearLimit ? 'warning' : 'success'}
          size="small"
        />
        <LinearProgress
          variant="determinate"
          value={(count / MAX_CUSTOM_BOTS) * 100}
          color={atLimit ? 'error' : nearLimit ? 'warning' : 'primary'}
          sx={{ width: '100%', height: 3, borderRadius: 3, mt: 0.25 }}
        />
      </Box>

      {/* CTA row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2, flexWrap: 'wrap' }}>
        <Tooltip title={!connected ? 'Connect your Discord first' : atLimit ? 'Custom-bot limit reached' : !hasPro ? 'Custom bots need at least one Pro server' : ''}>
          <span>
            <Button variant="contained" size="small" startIcon={<Add />} onClick={connected ? onAdd : onConnect} disabled={connected && atLimit}>
              Add Bot
            </Button>
          </span>
        </Tooltip>
        <Button
          variant="text" size="small" component="a"
          href="https://discord.com/developers/applications" target="_blank" rel="noopener noreferrer"
          startIcon={<Code />} sx={{ color: 'text.secondary' }}
        >
          Developer Portal
        </Button>
        {count === 0 && (
          <Typography variant="caption" color="text.disabled" sx={{ ml: 0.5 }}>
            Create an app in the Developer Portal → enable intents → copy token → Add Bot
          </Typography>
        )}
        {count > 0 && (
          <Tooltip title="Create app → enable both privileged intents → Reset Token → Add Bot">
            <Typography variant="caption" color="text.disabled" sx={{ cursor: 'default', ml: 0.5, '&:hover': { color: 'text.secondary' } }}>
              How to add a bot?
            </Typography>
          </Tooltip>
        )}
        {count > 1 && (
          <TextField
            size="small"
            placeholder="Search bots…"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            InputProps={{
              startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment>,
              endAdornment: search ? (
                <InputAdornment position="end">
                  <IconButton size="small" onClick={() => onSearch('')}><Close fontSize="small" /></IconButton>
                </InputAdornment>
              ) : null,
            }}
            sx={{ width: { xs: '100%', sm: 180 }, ml: { sm: 'auto' } }}
          />
        )}
      </Box>

      {/* Bot grid */}
      {count === 0 ? (
        <Card variant="outlined"><CardContent sx={{ textAlign: 'center', py: 5 }}>
          <SmartToy sx={{ fontSize: 44, color: 'text.disabled', mb: 1 }} />
          <Typography color="text.secondary" gutterBottom>No custom bots yet.</Typography>
          <Typography variant="caption" color="text.disabled" display="block">
            Run Guildizer under your own brand — connect a Discord bot you created and it
            inherits every Guildizer feature.
          </Typography>
          <Button
            sx={{ mt: 2 }} variant="contained" startIcon={<Add />}
            onClick={connected ? onAdd : onConnect}
          >
            Connect a bot
          </Button>
        </CardContent></Card>
      ) : filteredBots.length === 0 ? (
        <Box sx={{ textAlign: 'center', py: 4 }}>
          <Typography color="text.secondary">No bots match &quot;{search}&quot;</Typography>
        </Box>
      ) : (
        <Grid container spacing={2}>
          {filteredBots.map((bot) => {
            const colMd = filteredBots.length === 1 ? 12 : filteredBots.length === 2 ? 6 : 4;
            const colSm = filteredBots.length === 1 ? 12 : 6;
            return (
              <Grid item xs={12} sm={colSm} md={colMd} key={bot.id} sx={{ display: 'flex' }}>
                <CommunityBotCard bot={bot} navigate={navigate} onChanged={onChanged} />
              </Grid>
            );
          })}
        </Grid>
      )}
    </>
  );
}

// ── Compact custom-bot card (matches the Telegizer dashboard bot card) ──
function CommunityBotCard({ bot, navigate, onChanged }) {
  const [busy, setBusy] = useState(false);
  const status = BOT_STATUS_CHIP[bot.status] || BOT_STATUS_CHIP.disabled;
  const serverCount = bot.linked_guilds?.length ?? 0;

  const disconnect = async () => {
    if (!window.confirm(`Disconnect @${bot.bot_username}? Its servers revert to the official Guildizer bot.`)) return;
    setBusy(true);
    try { await guildizerApi.delete(`/api/custom-bots/${bot.id}`); await onChanged(); }
    catch { /* surfaced on next reload */ }
    setBusy(false);
  };

  return (
    <Card
      sx={{
        flex: 1, display: 'flex', flexDirection: 'column',
        transition: 'transform 0.2s cubic-bezier(0.22,1,0.36,1), box-shadow 0.2s ease, border-color 0.2s',
        '&:hover': {
          transform: 'translateY(-3px)',
          boxShadow: '0 12px 40px rgba(0,0,0,0.55), 0 0 0 1px rgba(157,108,247,0.25)',
          borderColor: 'rgba(157,108,247,0.3)',
        },
      }}
    >
      <CardContent sx={{ flex: 1, pb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Avatar
            src={bot.avatar_url || undefined}
            sx={{
              mr: 1.5, width: 38, height: 38, flexShrink: 0,
              background: 'linear-gradient(135deg, #5865f2, #9d6cf7)',
              boxShadow: '0 0 10px rgba(88,101,242,0.3)',
            }}
          >
            <SmartToy sx={{ fontSize: 18 }} />
          </Avatar>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography variant="subtitle2" fontWeight={700} noWrap>@{bot.bot_username}</Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {bot.last_online_at ? `last online ${_relativeTime(bot.last_online_at)}` : 'not seen online yet'}
            </Typography>
          </Box>
          <Chip label={status.label} color={status.color} size="small" variant="outlined" />
        </Box>
        <Typography variant="caption" color="text.disabled">
          {serverCount} server{serverCount !== 1 ? 's' : ''}
        </Typography>
        {!bot.intents_ok && (
          <Typography variant="caption" color="warning.main" display="block" mt={0.5}>
            Enable both privileged intents — open Manage to fix.
          </Typography>
        )}
      </CardContent>
      <CardActions sx={{ px: 1.5, pb: 1.5, pt: 0, gap: 0.5, flexWrap: 'wrap' }}>
        <Button size="small" startIcon={<Settings />} onClick={() => navigate('/guildizer/bots')}>Manage</Button>
        <Button size="small" startIcon={<BarChart />} onClick={() => navigate('/guildizer/bots')}>Servers</Button>
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Disconnect bot">
          <span>
            <IconButton size="small" onClick={disconnect} disabled={busy}>
              <Delete fontSize="small" color="error" />
            </IconButton>
          </span>
        </Tooltip>
      </CardActions>
    </Card>
  );
}

// Lightweight relative-time helper (mirrors the Telegizer dashboard's _relativeTime).
function _relativeTime(iso) {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const s = Math.floor((Date.now() - then) / 1000);
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

// Guildizer reuses the shared Telegizer bell (live polling, sound, mute, "view
// all") pointed at the Guildizer backend + notifications page.
function NotificationsBell() {
  return <NotificationBell api={guildizerNotifications} viewAllPath="/guildizer/notifications" />;
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
export function PermissionsDialog({ guild, onClose }) {
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
export function UnlinkDialog({ guild, onClose }) {
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
