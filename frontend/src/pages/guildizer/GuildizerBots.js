import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Button, Card, CardContent, Grid, Avatar, Chip, Stack,
  CircularProgress, Alert, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Stepper, Step, StepLabel, Link, Divider, MenuItem, Select,
  FormControl, InputLabel, IconButton,
} from '@mui/material';
import {
  SmartToy, Add, OpenInNew, Refresh, Delete, ArrowBack, Key,
  CheckCircle, Cancel,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import guildizerApi from '../../services/guildizerApi';
import { ServerCard, PermissionsDialog } from './GuildizerServers';

// Mirrors the backend MAX_BOTS_PER_USER (custom_bots_api.py).
const MAX_CUSTOM_BOTS = 5;

const STATUS_CHIP = {
  active: { color: 'success', label: 'Active' },
  error: { color: 'error', label: 'Needs attention' },
  disabled: { color: 'default', label: 'Disabled' },
  paused: { color: 'warning', label: 'Paused: Pro ended' },
};

export default function GuildizerBots() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [bots, setBots] = useState([]);
  const [guilds, setGuilds] = useState([]);
  const [error, setError] = useState(null);
  const [wizardOpen, setWizardOpen] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [{ data: botData }, { data: guildData }] = await Promise.all([
        guildizerApi.get('/api/custom-bots'),
        guildizerApi.get('/api/guilds'),
      ]);
      setBots(botData.bots);
      setGuilds(guildData.guilds);
      setError(null);
    } catch (e) {
      if (e?.response?.status === 401) navigate('/guildizer');
      else setError('Failed to load your bots.');
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => { reload(); }, [reload]);

  if (loading) {
    return <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 320 }}><CircularProgress /></Box>;
  }

  // With exactly one bot the page is that bot's page, titled with its name.
  const single = bots.length === 1 ? bots[0] : null;

  return (
    <Box sx={{ maxWidth: 1100, mx: 'auto', px: { xs: 2, md: 3 }, py: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <IconButton aria-label="Back" size="small" onClick={() => navigate('/guildizer')}><ArrowBack /></IconButton>
        {single
          ? <Avatar src={single.avatar_url || undefined} variant="rounded" sx={{ width: 36, height: 36 }}><SmartToy /></Avatar>
          : <SmartToy color="primary" />}
        <Typography variant="h5" fontWeight={800} noWrap sx={{ flex: 1, minWidth: 0 }}>
          {single ? single.bot_username : 'My Bots'}
        </Typography>
        {bots.length > 0 && bots.length < MAX_CUSTOM_BOTS && (
          <Button size="small" startIcon={<Add />} onClick={() => setWizardOpen(true)} sx={{ flexShrink: 0 }}>
            Add bot
          </Button>
        )}
      </Box>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Run Guildizer under your own brand. Connect a Discord bot you created and it gets
        every Guildizer feature — your name, your avatar, our engine. Updates apply automatically.
      </Typography>

      {error && <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}

      {bots.length === 0 && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
          <Button variant="contained" startIcon={<Add />} onClick={() => setWizardOpen(true)}>Connect a bot</Button>
        </Box>
      )}

      {bots.length === 0 ? (
        <Card variant="outlined"><CardContent sx={{ textAlign: 'center', py: 5 }}>
          <SmartToy sx={{ fontSize: 44, color: 'text.disabled', mb: 1 }} />
          <Typography color="text.secondary">No custom bots yet.</Typography>
          <Typography variant="caption" color="text.disabled">
            Create a bot in the Discord Developer Portal, then connect it here with its token.
          </Typography>
        </CardContent></Card>
      ) : (
        <Grid container spacing={2}>
          {bots.map((bot) => (
            <BotCard key={bot.id} bot={bot} guilds={guilds} onChanged={reload} />
          ))}
        </Grid>
      )}

      <ConnectWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onConnected={() => { setWizardOpen(false); reload(); }}
      />
    </Box>
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

function BotCard({ bot, guilds, onChanged }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [tokenDialog, setTokenDialog] = useState(false);
  const [linkGuildId, setLinkGuildId] = useState('');
  const [permsGuild, setPermsGuild] = useState(null);
  const status = STATUS_CHIP[bot.status] || STATUS_CHIP.disabled;
  const linkedIds = new Set(bot.linked_guilds.map((g) => g.id));
  // Full guild records (members, owner, …) for the shared server card; fall back
  // to the slim linked_guilds entry if the guild list hasn't returned it.
  const serverCards = bot.linked_guilds.map((lg) => ({
    bot_present: true,
    ...lg,
    ...(guilds.find((g) => g.id === lg.id) || {}),
    custom_bot_id: bot.id,
  }));
  const linkable = guilds.filter((g) => g.bot_present && !linkedIds.has(g.id));

  const act = async (fn) => {
    setBusy(true);
    try { await fn(); await onChanged(); } catch { /* surfaced by parent reload */ }
    setBusy(false);
  };

  const openInvite = async () => {
    const { data } = await guildizerApi.get(`/api/custom-bots/${bot.id}/invite`);
    window.open(data.invite_url, '_blank', 'noreferrer');
  };

  return (
    <Grid item xs={12}>
      <Card variant="outlined" sx={{ height: '100%' }}>
        <CardContent>
          <Stack direction="row" spacing={1.5} alignItems="center" mb={1}>
            <Avatar src={bot.avatar_url || undefined} variant="rounded" sx={{ width: 44, height: 44 }}>
              <SmartToy />
            </Avatar>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography fontWeight={700} noWrap>@{bot.bot_username}</Typography>
              <Typography variant="caption" color="text.secondary">
                {bot.last_online_at ? `Last online ${new Date(bot.last_online_at).toLocaleString()}` : 'Not seen online yet'}
              </Typography>
            </Box>
            <Chip size="small" variant="outlined" color={status.color} label={status.label} />
          </Stack>

          {bot.status === 'paused' && (
            <Alert severity="warning" sx={{ mb: 1.5 }}
              action={(
                <Button color="inherit" size="small" disabled={busy}
                  onClick={() => act(async () => {
                    try { await guildizerApi.post(`/api/custom-bots/${bot.id}/reactivate`); toast.success('Reactivated'); }
                    catch (e) { toast.error(e.response?.data?.message || 'Could not reactivate'); throw e; }
                  })}>
                  Reactivate
                </Button>
              )}>
              This bot was switched off because Pro ended. Nothing was deleted. Renew Pro on one of your servers, then
              press Reactivate. Without Pro it is removed 22 days after Pro ended and your servers move back to the
              official Guildizer bot.
            </Alert>
          )}
          {bot.status !== 'paused' && bot.lapse_started_at && (
            <Alert severity="warning" sx={{ mb: 1.5 }}>
              Pro ended on your servers. This bot will be paused 7 days after it ended
              ({new Date(new Date(bot.lapse_started_at).getTime() + 7 * 86400000).toLocaleDateString()}) unless you renew Pro.
            </Alert>
          )}
          {bot.error_detail && <Alert severity="error" sx={{ mb: 1.5 }}>{bot.error_detail}</Alert>}

          <Stack direction="row" spacing={2} mb={1.5}>
            <IntentRow ok={bot.intents_members} label="Server Members intent" />
            <IntentRow ok={bot.intents_message_content} label="Message Content intent" />
          </Stack>
          {!bot.intents_ok && (
            <Alert severity="warning" sx={{ mb: 1.5 }}>
              Enable both privileged intents for this app in the{' '}
              <Link href={`https://discord.com/developers/applications/${bot.application_id}/bot`} target="_blank" rel="noreferrer">
                Developer Portal
              </Link>, then press Re-check.
            </Alert>
          )}

          <Divider sx={{ my: 1.5 }} />
          <Typography variant="caption" color="text.secondary">Serving servers</Typography>
          {serverCards.length === 0 ? (
            <Typography variant="caption" color="text.disabled" display="block" mt={0.75} mb={1.5}>
              None yet. Press Add a server below, invite this bot, and it links automatically.
            </Typography>
          ) : (
            <Grid container spacing={2} sx={{ mt: 0, mb: 2 }}>
              {serverCards.map((g) => (
                <ServerCard
                  key={g.id}
                  guild={g}
                  count={serverCards.length}
                  navigate={navigate}
                  onViewPerms={() => setPermsGuild(g)}
                  unlinkTitle="Unlink (the bot leaves this server)"
                  onUnlink={() => {
                    if (window.confirm(`Unlink ${g.name} from @${bot.bot_username}? The bot will leave this server. (It only stays on the dashboard if the official Guildizer bot is also in it.)`)) {
                      act(() => guildizerApi.delete(`/api/custom-bots/${bot.id}/guilds/${g.id}`, { params: { leave: 1 } }));
                    }
                  }}
                />
              ))}
            </Grid>
          )}
          <PermissionsDialog guild={permsGuild} onClose={() => setPermsGuild(null)} />

          {linkable.length > 0 && (
            <Stack direction="row" spacing={1} alignItems="center" mb={0.5}>
              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel>Link an existing server</InputLabel>
                <Select label="Link an existing server" value={linkGuildId} onChange={(e) => setLinkGuildId(e.target.value)}>
                  {linkable.map((g) => <MenuItem key={g.id} value={g.id}>{g.name}</MenuItem>)}
                </Select>
              </FormControl>
              <Button
                size="small" disabled={!linkGuildId || busy}
                onClick={() => act(async () => {
                  await guildizerApi.post(`/api/custom-bots/${bot.id}/guilds/${linkGuildId}`);
                  setLinkGuildId('');
                })}
              >
                Link
              </Button>
            </Stack>
          )}
        </CardContent>

        <Box sx={{ p: 1.5, pt: 0, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button size="small" variant="contained" endIcon={<OpenInNew />} onClick={openInvite} disabled={busy}>
            Add a server
          </Button>
          <Button
            size="small" startIcon={<Refresh />} disabled={busy}
            onClick={() => act(() => guildizerApi.post(`/api/custom-bots/${bot.id}/recheck`))}
          >
            Re-check
          </Button>
          <Button size="small" startIcon={<Key />} onClick={() => setTokenDialog(true)} disabled={busy}>
            Replace token
          </Button>
          <Button
            size="small" color="error" startIcon={<Delete />} disabled={busy}
            onClick={() => {
              if (window.confirm(`Disconnect @${bot.bot_username}? It will leave the servers linked to it. Re-adding it later means re-inviting it.`)) {
                act(() => guildizerApi.delete(`/api/custom-bots/${bot.id}`, { params: { leave: 1 } }));
              }
            }}
          >
            Disconnect
          </Button>
        </Box>
      </Card>

      <TokenDialog
        open={tokenDialog}
        title={`Replace token for @${bot.bot_username}`}
        submit={async (token) => guildizerApi.post(`/api/custom-bots/${bot.id}/token`, { token })}
        onClose={() => setTokenDialog(false)}
        onDone={() => { setTokenDialog(false); onChanged(); }}
      />
    </Grid>
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
