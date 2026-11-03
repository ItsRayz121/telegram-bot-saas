import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Box, Typography, Button, Card, CardContent, Grid, Avatar, Chip, Stack,
  Alert, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions,
  TextField, Stepper, Step, StepLabel, Link, IconButton, InputAdornment,
  Menu, MenuItem, ListItemIcon, Skeleton, Tooltip,
} from '@mui/material';
import {
  SmartToy, Add, OpenInNew, Refresh, Delete, ArrowBack, Key, Search, Dns,
  BarChart, PowerSettingsNew, PlayArrow, MoreVert, CheckCircle, Cancel,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import guildizerApi from '../../services/guildizerApi';
import { ServerCard, PermissionsDialog } from './GuildizerServers';

// Mirrors the backend MAX_BOTS_PER_USER (custom_bots_api.py).
const MAX_CUSTOM_BOTS = 5;

const STATUS_CHIP = {
  active: { color: 'success', label: 'Active' },
  error: { color: 'error', label: 'Needs attention' },
  disabled: { color: 'default', label: 'Stopped' },
  paused: { color: 'warning', label: 'Paused: Pro ended' },
};

const cardHover = {
  transition: 'transform 0.2s cubic-bezier(0.22,1,0.36,1), box-shadow 0.2s ease, border-color 0.2s',
  '&:hover': {
    transform: 'translateY(-2px)',
    boxShadow: '0 12px 40px rgba(0,0,0,0.5), 0 0 0 1px rgba(88,101,242,0.22)',
    borderColor: 'rgba(88,101,242,0.28)',
  },
};

const errMessage = (e, fallback) => e?.response?.data?.message || fallback;

const relativeTime = (iso) => {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const s = Math.floor((Date.now() - then) / 1000);
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

// Opens the real Discord OAuth invite for this bot's own application. Nothing is
// marked linked here: the bot links the server itself once Discord adds it.
async function openBotInvite(bot) {
  try {
    const { data } = await guildizerApi.get(`/api/custom-bots/${bot.id}/invite`);
    window.open(data.invite_url, '_blank', 'noreferrer');
    toast.info('Invite opened in a new tab. The server appears here once you authorize the bot.');
  } catch (e) {
    toast.error(errMessage(e, 'Could not create the invite link. Try again.'));
  }
}

export default function GuildizerBots() {
  const navigate = useNavigate();
  const { botId } = useParams();
  const [loading, setLoading] = useState(true);
  const [bots, setBots] = useState([]);
  const [guilds, setGuilds] = useState([]);
  const [entitled, setEntitled] = useState(true);
  const [error, setError] = useState(null);
  const [wizardOpen, setWizardOpen] = useState(false);

  const reload = useCallback(async ({ silent = false } = {}) => {
    try {
      const [{ data: botData }, { data: guildData }] = await Promise.all([
        guildizerApi.get('/api/custom-bots'),
        guildizerApi.get('/api/guilds'),
      ]);
      setBots(botData.bots);
      setEntitled(botData.entitled !== false);
      setGuilds(guildData.guilds);
      setError(null);
    } catch (e) {
      if (e?.response?.status === 401) navigate('/guildizer');
      else if (!silent) setError('Failed to load your bots.');
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => { reload(); }, [reload]);

  // Coming back from the Discord invite tab: pick up the newly linked server.
  useEffect(() => {
    const onFocus = () => reload({ silent: true });
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [reload]);

  const bot = botId ? bots.find((b) => String(b.id) === String(botId)) : null;

  return (
    <Box sx={{ maxWidth: 1100, mx: 'auto', px: { xs: 2, md: 3 }, py: 3 }}>
      {loading ? <BotsSkeleton /> : error && bots.length === 0 ? (
        <Alert severity="warning" action={<Button color="inherit" size="small" onClick={() => { setLoading(true); reload(); }}>Retry</Button>}>
          {error}
        </Alert>
      ) : botId ? (
        bot ? (
          <BotServers bot={bot} guilds={guilds} onChanged={reload} navigate={navigate} />
        ) : (
          <Alert severity="info" action={<Button color="inherit" size="small" onClick={() => navigate('/guildizer/bots')}>All bots</Button>}>
            This bot is not connected to your account.
          </Alert>
        )
      ) : (
        <BotsList
          bots={bots} entitled={entitled} onChanged={reload} navigate={navigate}
          onAdd={() => setWizardOpen(true)}
        />
      )}

      <ConnectWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onConnected={() => { setWizardOpen(false); reload(); }}
      />
    </Box>
  );
}

function BotsSkeleton() {
  return (
    <Box aria-busy="true" aria-label="Loading bots">
      <Skeleton variant="text" width={180} height={40} sx={{ mb: 2 }} />
      <Grid container spacing={2}>
        {[0, 1].map((i) => (
          <Grid item xs={12} md={6} key={i}><Skeleton variant="rounded" height={190} /></Grid>
        ))}
      </Grid>
    </Box>
  );
}

// ── Accessible confirmation dialog (used for Delete and Unlink) ──────────────
function ConfirmDialog({ open, title, children, confirmLabel, busy, onConfirm, onClose }) {
  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} fullWidth maxWidth="xs" aria-labelledby="confirm-title">
      <DialogTitle id="confirm-title">{title}</DialogTitle>
      <DialogContent>
        <DialogContentText component="div" variant="body2">{children}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button color="error" variant="contained" onClick={onConfirm} disabled={busy} autoFocus>
          {busy ? 'Working…' : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Bot list ─────────────────────────────────────────────────────────────────
function BotsList({ bots, entitled, onChanged, navigate, onAdd }) {
  const [query, setQuery] = useState('');
  const atLimit = bots.length >= MAX_CUSTOM_BOTS;
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? bots.filter((b) => (b.bot_username || '').toLowerCase().includes(q)) : bots;
  }, [bots, query]);

  return (
    <>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <IconButton aria-label="Back to Discord" size="small" onClick={() => navigate('/guildizer')}><ArrowBack /></IconButton>
        <SmartToy color="primary" />
        <Typography variant="h5" fontWeight={800} noWrap sx={{ flex: 1, minWidth: 0 }}>My Bots</Typography>
        <Tooltip title={atLimit ? `You can connect up to ${MAX_CUSTOM_BOTS} bots` : ''}>
          <span>
            <Button variant="contained" size="small" startIcon={<Add />} onClick={onAdd} disabled={atLimit} sx={{ flexShrink: 0 }}>
              Add bot
            </Button>
          </span>
        </Tooltip>
      </Box>
      <Typography variant="body2" color="text.secondary" mb={2}>
        {bots.length} of {MAX_CUSTOM_BOTS} bots connected
        {!entitled && ' · Custom bots need a Pro server'}
      </Typography>

      {bots.length > 0 && (
        <TextField
          size="small" fullWidth placeholder="Search bots" value={query}
          onChange={(e) => setQuery(e.target.value)}
          inputProps={{ 'aria-label': 'Search bots' }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
          sx={{ mb: 2, maxWidth: 420 }}
        />
      )}

      {bots.length === 0 ? (
        <Card variant="outlined"><CardContent sx={{ textAlign: 'center', py: 5 }}>
          <SmartToy sx={{ fontSize: 44, color: 'text.disabled', mb: 1 }} />
          <Typography color="text.secondary" gutterBottom>No custom bots yet.</Typography>
          <Button variant="contained" startIcon={<Add />} onClick={onAdd} sx={{ mt: 1 }}>Connect a bot</Button>
        </CardContent></Card>
      ) : shown.length === 0 ? (
        <Typography color="text.secondary">No bots match “{query}”.</Typography>
      ) : (
        <Grid container spacing={2}>
          {shown.map((bot) => (
            <BotCard key={bot.id} bot={bot} navigate={navigate} onChanged={onChanged} />
          ))}
        </Grid>
      )}
    </>
  );
}

function IntentRow({ ok, label }) {
  return (
    <Stack direction="row" spacing={0.75} alignItems="center">
      {ok ? <CheckCircle color="success" sx={{ fontSize: 16 }} /> : <Cancel color="error" sx={{ fontSize: 16 }} />}
      <Typography variant="caption" color={ok ? 'text.secondary' : 'error.main'}>{label}</Typography>
    </Stack>
  );
}

function BotCard({ bot, navigate, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState(null);
  const [tokenDialog, setTokenDialog] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const status = STATUS_CHIP[bot.status] || STATUS_CHIP.disabled;
  const servers = bot.linked_guilds || [];

  // One power control whose meaning follows the real status.
  const power = {
    active: { label: 'Stop', icon: <PowerSettingsNew />, path: 'stop', done: 'Bot stopped' },
    disabled: { label: 'Start', icon: <PlayArrow />, path: 'start', done: 'Bot started' },
    paused: { label: 'Reactivate', icon: <PlayArrow />, path: 'reactivate', done: 'Bot reactivated' },
    error: { label: 'Retry', icon: <Refresh />, path: 'recheck', done: 'Re-checked' },
  }[bot.status] || { label: 'Retry', icon: <Refresh />, path: 'recheck', done: 'Re-checked' };

  const run = async (fn, failMsg) => {
    setBusy(true);
    try { await fn(); await onChanged({ silent: true }); return true; }
    catch (e) { toast.error(errMessage(e, failMsg)); return false; }
    finally { setBusy(false); }
  };

  const togglePower = () => run(async () => {
    await guildizerApi.post(`/api/custom-bots/${bot.id}/${power.path}`);
    toast.success(power.done);
  }, `Could not ${power.label.toLowerCase()} the bot`);

  const doDelete = async () => {
    const ok = await run(() => guildizerApi.delete(`/api/custom-bots/${bot.id}`, { params: { leave: 1 } }), 'Could not delete the bot');
    if (ok) { toast.success('Bot deleted'); setConfirmDelete(false); }
  };

  const analyticsTarget = servers.length === 1
    ? `/guildizer/servers/${servers[0].id}?tab=Analytics&sub=Overview`
    : `/guildizer/bots/${bot.id}`;

  return (
    <Grid item xs={12} md={6}>
      <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column', ...cardHover }}>
        <CardContent sx={{ flex: 1, pb: 1 }}>
          <Stack direction="row" spacing={1.5} alignItems="center" mb={1.25}>
            <Avatar
              src={bot.avatar_url || undefined} variant="rounded"
              sx={{ width: 44, height: 44, background: 'linear-gradient(135deg, #5865f2, #9d6cf7)' }}
            >
              <SmartToy />
            </Avatar>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography fontWeight={700} noWrap>@{bot.bot_username}</Typography>
              <Typography variant="caption" color="text.secondary" noWrap display="block" sx={{ fontFamily: 'monospace' }}>
                ID: {bot.bot_user_id}
              </Typography>
            </Box>
            <Chip size="small" variant="outlined" color={status.color} label={status.label} />
          </Stack>

          <Typography variant="body2" color="text.secondary">
            {servers.length} server{servers.length !== 1 ? 's' : ''}
            {bot.last_online_at && ` · last online ${relativeTime(bot.last_online_at)}`}
          </Typography>
          {bot.status === 'paused' && (
            <Typography variant="caption" color="warning.main" display="block" mt={0.5}>
              Switched off because Pro ended. Renew Pro, then Reactivate.
            </Typography>
          )}
          {bot.status === 'error' && bot.error_detail && (
            <Typography variant="caption" color="error.main" display="block" mt={0.5}>{bot.error_detail}</Typography>
          )}
          {bot.status !== 'error' && !bot.intents_ok && (
            <Typography variant="caption" color="warning.main" display="block" mt={0.5}>
              Enable both privileged intents in the{' '}
              <Link href={`https://discord.com/developers/applications/${bot.application_id}/bot`} target="_blank" rel="noreferrer">Developer Portal</Link>.
            </Typography>
          )}
        </CardContent>

        <Box sx={{ px: 1.5, pb: 1.5, display: 'flex', gap: 0.75, flexWrap: 'wrap', alignItems: 'center' }}>
          <Button size="small" variant="contained" startIcon={<Dns />} onClick={() => navigate(`/guildizer/bots/${bot.id}`)} disabled={busy}>
            Servers
          </Button>
          <Button
            size="small" variant="outlined" startIcon={<BarChart />} disabled={busy || servers.length === 0}
            onClick={() => navigate(analyticsTarget)}
          >
            Analytics
          </Button>
          <Button size="small" variant="outlined" startIcon={<OpenInNew />} onClick={() => openBotInvite(bot)} disabled={busy}>
            Add Server
          </Button>
          <Box sx={{ flexGrow: 1 }} />
          <Button
            size="small" color="success" variant="outlined" startIcon={power.icon}
            onClick={togglePower} disabled={busy}
          >
            {power.label}
          </Button>
          <Tooltip title="Delete bot">
            <span>
              <IconButton size="small" color="error" aria-label={`Delete @${bot.bot_username}`} onClick={() => setConfirmDelete(true)} disabled={busy}>
                <Delete fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <IconButton size="small" aria-label="More bot actions" onClick={(e) => setMenuAnchor(e.currentTarget)} disabled={busy}>
            <MoreVert fontSize="small" />
          </IconButton>
        </Box>
      </Card>

      <Menu anchorEl={menuAnchor} open={!!menuAnchor} onClose={() => setMenuAnchor(null)}>
        <MenuItem onClick={() => { setMenuAnchor(null); run(async () => { await guildizerApi.post(`/api/custom-bots/${bot.id}/recheck`); toast.success('Re-checked'); }, 'Re-check failed'); }}>
          <ListItemIcon><Refresh fontSize="small" /></ListItemIcon>Re-check
        </MenuItem>
        <MenuItem onClick={() => { setMenuAnchor(null); setTokenDialog(true); }}>
          <ListItemIcon><Key fontSize="small" /></ListItemIcon>Replace token
        </MenuItem>
      </Menu>

      <ConfirmDialog
        open={confirmDelete} busy={busy} confirmLabel="Delete bot"
        title={`Delete @${bot.bot_username}?`}
        onConfirm={doDelete} onClose={() => setConfirmDelete(false)}
      >
        The bot stops running, leaves the {servers.length} server{servers.length !== 1 ? 's' : ''} linked to it, and its
        stored token is erased. Your Discord servers are not deleted and their Guildizer settings stay saved.
        Connecting it again later means re-adding the token and re-inviting it.
      </ConfirmDialog>

      <TokenDialog
        open={tokenDialog}
        title={`Replace token for @${bot.bot_username}`}
        submit={async (token) => guildizerApi.post(`/api/custom-bots/${bot.id}/token`, { token })}
        onClose={() => setTokenDialog(false)}
        onDone={() => { setTokenDialog(false); onChanged({ silent: true }); }}
      />
    </Grid>
  );
}

// ── Inside one bot: only its linked servers ──────────────────────────────────
function BotServers({ bot, guilds, onChanged, navigate }) {
  const [permsGuild, setPermsGuild] = useState(null);
  const [unlinkTarget, setUnlinkTarget] = useState(null);
  const [busy, setBusy] = useState(false);

  // Full guild records (members, owner, …) for the shared server card; fall back
  // to the slim linked_guilds entry if the guild list hasn't returned it.
  const serverCards = (bot.linked_guilds || []).map((lg) => ({
    bot_present: true,
    ...lg,
    ...(guilds.find((g) => g.id === lg.id) || {}),
    custom_bot_id: bot.id,
  }));

  const unlink = async () => {
    setBusy(true);
    try {
      await guildizerApi.delete(`/api/custom-bots/${bot.id}/guilds/${unlinkTarget.id}`, { params: { leave: 1 } });
      toast.success(`${unlinkTarget.name} unlinked`);
      setUnlinkTarget(null);
      await onChanged({ silent: true });
    } catch (e) {
      toast.error(errMessage(e, 'Could not unlink the server'));
    }
    setBusy(false);
  };

  return (
    <>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <IconButton aria-label="Back to all bots" size="small" onClick={() => navigate('/guildizer/bots')}><ArrowBack /></IconButton>
        <Avatar src={bot.avatar_url || undefined} variant="rounded" sx={{ width: 36, height: 36 }}><SmartToy /></Avatar>
        <Typography variant="h5" fontWeight={800} noWrap sx={{ flex: 1, minWidth: 0 }}>@{bot.bot_username}</Typography>
        <Button size="small" variant="contained" startIcon={<Add />} onClick={() => openBotInvite(bot)} sx={{ flexShrink: 0 }}>
          Add Server
        </Button>
      </Box>

      {serverCards.length === 0 ? (
        <Typography variant="body2" color="text.disabled">No servers linked yet.</Typography>
      ) : (
        <Grid container spacing={2}>
          {serverCards.map((g) => (
            <ServerCard
              key={g.id}
              guild={g}
              botName={bot.bot_username}
              count={serverCards.length}
              navigate={navigate}
              onViewPerms={() => setPermsGuild(g)}
              unlinkTitle="Unlink (the bot leaves this server)"
              onUnlink={() => setUnlinkTarget(g)}
            />
          ))}
        </Grid>
      )}
      <PermissionsDialog guild={permsGuild} onClose={() => setPermsGuild(null)} />

      <ConfirmDialog
        open={!!unlinkTarget} busy={busy} confirmLabel="Unlink"
        title={`Unlink ${unlinkTarget?.name || 'this server'}?`}
        onConfirm={unlink} onClose={() => setUnlinkTarget(null)}
      >
        @{bot.bot_username} leaves this server and stops managing it. The Discord server itself is not touched and its
        settings stay saved. It only remains on your dashboard if the official Guildizer bot is also in it.
      </ConfirmDialog>
    </>
  );
}

const TOKEN_ERRORS = {
  invalid_token: 'Discord rejected that token. Copy it again from the Bot tab (Reset Token if needed).',
  token_belongs_to_different_bot: 'That token belongs to a different bot than this card.',
  bot_already_connected: 'That bot is already connected to another Guildizer account.',
  bot_limit_reached: 'You have reached the custom-bot limit for your account.',
  discord_unreachable: 'Could not reach Discord — try again in a moment.',
  pro_required: 'Custom bots need at least one Pro server.',
};

const tokenErrorMessage = (e) =>
  TOKEN_ERRORS[e?.response?.data?.error] || e?.response?.data?.message || 'Something went wrong — try again.';

function TokenDialog({ open, title, submit, onClose, onDone }) {
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const go = async () => {
    setBusy(true); setErr(null);
    try {
      await submit(token.trim());
      setToken('');
      onDone();
    } catch (e) {
      setErr(tokenErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
        <TextField
          autoFocus fullWidth label="Bot token" type="password" value={token}
          onChange={(e) => setToken(e.target.value)}
          helperText="Stored encrypted. Never shown again after save."
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!token.trim() || busy} onClick={go}>
          {busy ? 'Validating…' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function ConnectWizard({ open, onClose, onConnected }) {
  const [step, setStep] = useState(0);
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [bot, setBot] = useState(null);

  const reset = () => { setStep(0); setToken(''); setErr(null); setBot(null); };

  const connect = async () => {
    setBusy(true); setErr(null);
    try {
      const { data } = await guildizerApi.post('/api/custom-bots', { token: token.trim() });
      setBot(data.bot);
      setToken('');
      setStep(2);
    } catch (e) {
      setErr(tokenErrorMessage(e));
    }
    setBusy(false);
  };

  const openInvite = async () => {
    const { data } = await guildizerApi.get(`/api/custom-bots/${bot.id}/invite`);
    window.open(data.invite_url, '_blank', 'noreferrer');
  };

  return (
    <Dialog open={open} onClose={() => { reset(); onClose(); }} fullWidth maxWidth="sm">
      <DialogTitle>Connect your own bot</DialogTitle>
      <DialogContent>
        <Stepper activeStep={step} sx={{ mb: 3 }}>
          {['Create the bot', 'Paste its token', 'Invite it'].map((label) => (
            <Step key={label}><StepLabel>{label}</StepLabel></Step>
          ))}
        </Stepper>

        {step === 0 && (
          <Box>
            <Typography variant="body2" component="div" color="text.secondary">
              <ol style={{ margin: 0, paddingLeft: 18, lineHeight: 2 }}>
                <li>
                  Open the{' '}
                  <Link href="https://discord.com/developers/applications" target="_blank" rel="noreferrer">
                    Discord Developer Portal
                  </Link>{' '}
                  and click <b>New Application</b>. The name becomes your bot's brand.
                </li>
                <li>Go to the <b>Bot</b> tab. Set the avatar and username you want.</li>
                <li>
                  On the same tab, turn ON both <b>Server Members Intent</b> and{' '}
                  <b>Message Content Intent</b> (under Privileged Gateway Intents).
                </li>
                <li>Press <b>Reset Token</b> and copy the token — you'll paste it in the next step.</li>
              </ol>
            </Typography>
          </Box>
        )}

        {step === 1 && (
          <Box>
            {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
            <TextField
              autoFocus fullWidth label="Bot token" type="password" value={token}
              onChange={(e) => setToken(e.target.value)}
              helperText="We validate it with Discord, then store it encrypted. It is never shown again."
            />
          </Box>
        )}

        {step === 2 && bot && (
          <Box>
            <Alert severity="success" sx={{ mb: 2 }}>
              <b>@{bot.bot_username}</b> is connected and will come online within a minute.
            </Alert>
            <Stack direction="row" spacing={2} mb={1.5}>
              <IntentRow ok={bot.intents_members} label="Server Members intent" />
              <IntentRow ok={bot.intents_message_content} label="Message Content intent" />
            </Stack>
            {!bot.intents_ok && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                Both privileged intents must be ON or the bot cannot connect. Toggle them in the{' '}
                <Link href={`https://discord.com/developers/applications/${bot.application_id}/bot`} target="_blank" rel="noreferrer">
                  Developer Portal
                </Link>{' '}
                and press Re-check on the bot card.
              </Alert>
            )}
            <Typography variant="body2" color="text.secondary">
              Last step: invite your bot to your server. The server then automatically switches
              from the official Guildizer bot to yours.
            </Typography>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        {step === 0 && (
          <>
            <Button onClick={() => { reset(); onClose(); }}>Cancel</Button>
            <Button variant="contained" onClick={() => setStep(1)}>I have my token</Button>
          </>
        )}
        {step === 1 && (
          <>
            <Button onClick={() => setStep(0)}>Back</Button>
            <Button variant="contained" disabled={!token.trim() || busy} onClick={connect}>
              {busy ? 'Validating…' : 'Connect'}
            </Button>
          </>
        )}
        {step === 2 && (
          <>
            <Button onClick={onConnected}>Done</Button>
            <Button variant="contained" endIcon={<OpenInNew />} onClick={openInvite}>
              Invite to a server
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}
