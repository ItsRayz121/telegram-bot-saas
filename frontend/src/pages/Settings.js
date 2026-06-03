import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  TextField, IconButton, Divider, Alert, CircularProgress,
  Dialog, DialogTitle, DialogContent, DialogActions, Stack,
  Chip,
} from '@mui/material';
import {
  ArrowBack, SmartToy, Person, Lock, DeleteForever, Schedule,
  Security, CheckCircle, ContentCopy, Telegram, LinkOff, OpenInNew,
  Add, Star, StarBorder, Delete, CalendarMonth, MailOutline,
  CardGiftcard, People, Tour, Group, PersonAdd, Cancel,
} from '@mui/icons-material';
import { List, ListItem, ListItemText, ListItemSecondaryAction, Tooltip, Select, MenuItem, FormControl, InputLabel, LinearProgress } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { auth, totp as totpApi, billing, userSettings, telegramAccount, googleCalendar as calApi, referrals as referralsApi, team as teamApi } from '../services/api';
import { track } from '../services/analytics';
import { resetTour } from '../components/OnboardingTour';
import TimezoneSelect from '../components/TimezoneSelect';

function safeParseUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

function Section({ title, icon, children }) {
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          {icon}
          <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
        </Box>
        {children}
      </CardContent>
    </Card>
  );
}

// ── 2FA Section ────────────────────────────────────────────────────────────────
function TwoFactorSection({ user, onUserRefresh }) {
  const [step, setStep] = useState('idle'); // idle | setup | enable | backup_codes
  const [loading, setLoading] = useState(false);
  const [provUri, setProvUri] = useState('');
  const [secret, setSecret] = useState('');
  const [enableCode, setEnableCode] = useState('');
  const [backupCodes, setBackupCodes] = useState([]);
  const [backupCount, setBackupCount] = useState(null);
  const [disableOpen, setDisableOpen] = useState(false);
  const [disablePw, setDisablePw] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [disabling, setDisabling] = useState(false);
  const [copied, setCopied] = useState(false);

  const isPaidOrAdmin = user.subscription_tier === 'pro' || user.subscription_tier === 'enterprise' || user.is_admin;

  useEffect(() => {
    if (user.totp_enabled) {
      totpApi.getBackupCodeCount().then(r => setBackupCount(r.data.backup_codes_remaining)).catch(() => {});
    }
  }, [user.totp_enabled]);

  const handleSetup = async () => {
    setLoading(true);
    try {
      const r = await totpApi.setup();
      setSecret(r.data.secret);
      setProvUri(r.data.provisioning_uri);
      setStep('setup');
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to start 2FA setup');
    } finally {
      setLoading(false);
    }
  };

  const handleEnable = async () => {
    if (!enableCode.trim()) return;
    setLoading(true);
    try {
      const r = await totpApi.enable({ totp_code: enableCode.trim() });
      setBackupCodes(r.data.backup_codes || []);
      setStep('backup_codes');
      await onUserRefresh();
      toast.success('2FA enabled successfully!');
    } catch (e) {
      toast.error(e.response?.data?.error || 'Invalid code. Check your authenticator app.');
    } finally {
      setLoading(false);
    }
  };

  const handleDisable = async () => {
    if (!disablePw || !disableCode) return;
    setDisabling(true);
    try {
      await totpApi.disable({ password: disablePw, totp_code: disableCode });
      setDisableOpen(false);
      setDisablePw('');
      setDisableCode('');
      await onUserRefresh();
      toast.success('2FA disabled');
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to disable 2FA');
    } finally {
      setDisabling(false);
    }
  };

  const copySecret = () => {
    navigator.clipboard.writeText(secret).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!isPaidOrAdmin) {
    return (
      <Alert severity="info">
        Two-factor authentication is available on <strong>Pro and Enterprise</strong> plans.{' '}
        <Button size="small" href="/pricing">Upgrade</Button>
      </Alert>
    );
  }

  if (step === 'backup_codes') {
    return (
      <Box>
        <Alert severity="success" sx={{ mb: 2 }}>2FA enabled! Save these backup codes somewhere safe — they won't be shown again.</Alert>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 1, mb: 2 }}>
          {backupCodes.map((c, i) => (
            <Typography key={i} variant="body2" sx={{ fontFamily: 'monospace', bgcolor: 'background.default', p: 1, borderRadius: 1 }}>
              {c}
            </Typography>
          ))}
        </Box>
        <Button variant="contained" onClick={() => setStep('idle')}>Done</Button>
      </Box>
    );
  }

  if (step === 'setup') {
    return (
      <Box>
        <Alert severity="info" sx={{ mb: 2 }}>
          Scan the QR code below in your authenticator app (Google Authenticator, Authy, etc.)
        </Alert>

        {/* QR Code via Google Charts API */}
        <Box sx={{ textAlign: 'center', mb: 2 }}>
          <img
            src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(provUri)}`}
            alt="TOTP QR Code"
            style={{ borderRadius: 8, border: '4px solid #fff' }}
          />
        </Box>

        <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
          Can't scan? Enter this code manually:
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2, bgcolor: 'background.default', p: 1.5, borderRadius: 1 }}>
          <Typography variant="body2" sx={{ fontFamily: 'monospace', flexGrow: 1, letterSpacing: 2 }}>{secret}</Typography>
          <IconButton size="small" onClick={copySecret}>
            {copied ? <CheckCircle fontSize="small" color="success" /> : <ContentCopy fontSize="small" />}
          </IconButton>
        </Box>

        <TextField
          fullWidth
          label="Enter the 6-digit code from your app"
          value={enableCode}
          onChange={(e) => setEnableCode(e.target.value)}
          size="small"
          inputProps={{ maxLength: 8, inputMode: 'numeric' }}
          sx={{ mb: 2 }}
        />
        <Stack direction="row" spacing={1}>
          <Button variant="contained" onClick={handleEnable} disabled={loading || !enableCode.trim()}>
            {loading ? <CircularProgress size={20} color="inherit" /> : 'Activate 2FA'}
          </Button>
          <Button variant="outlined" onClick={() => setStep('idle')}>Cancel</Button>
        </Stack>
      </Box>
    );
  }

  // Idle state
  return (
    <Box>
      {user.totp_enabled ? (
        <>
          <Alert severity="success" icon={<CheckCircle />} sx={{ mb: 2 }}>
            Two-factor authentication is <strong>enabled</strong>.
            {backupCount !== null && ` ${backupCount} backup code${backupCount !== 1 ? 's' : ''} remaining.`}
          </Alert>
          <Button variant="outlined" color="error" onClick={() => setDisableOpen(true)} sx={{ mr: 1 }}>
            Disable 2FA
          </Button>
        </>
      ) : (
        <>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Add an extra layer of security. You'll need your authenticator app when signing in.
          </Typography>
          <Button variant="contained" onClick={handleSetup} disabled={loading} startIcon={<Security />}>
            {loading ? <CircularProgress size={20} color="inherit" /> : 'Set Up 2FA'}
          </Button>
        </>
      )}

      {/* Disable 2FA dialog */}
      <Dialog open={disableOpen} onClose={() => setDisableOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle fontWeight={700}>Disable Two-Factor Auth</DialogTitle>
        <DialogContent>
          <Typography variant="body2" mb={2}>
            Enter your password and current 2FA code to confirm.
          </Typography>
          <Stack spacing={2}>
            <TextField
              fullWidth type="password" label="Password" size="small"
              value={disablePw} onChange={(e) => setDisablePw(e.target.value)}
            />
            <TextField
              fullWidth label="2FA Code" size="small"
              value={disableCode} onChange={(e) => setDisableCode(e.target.value)}
              inputProps={{ maxLength: 8, inputMode: 'numeric' }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDisableOpen(false)} disabled={disabling}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDisable} disabled={disabling || !disablePw || !disableCode}>
            {disabling ? <CircularProgress size={20} color="inherit" /> : 'Disable 2FA'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Telegram Connect Section ───────────────────────────────────────────────────
function TelegramConnectSection({ user, onUserRefresh }) {
  const [status, setStatus] = React.useState({
    connected: user.telegram_connected || false,
    telegram_username: user.telegram_username || null,
    telegram_first_name: user.telegram_first_name || null,
    connected_at: user.telegram_connected_at || null,
  });
  const [loading, setLoading] = React.useState(false);
  const [connecting, setConnecting] = React.useState(false);
  const [disconnectOpen, setDisconnectOpen] = React.useState(false);
  const pollRef = React.useRef(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  React.useEffect(() => stopPolling, []);

  const startPolling = () => {
    let attempts = 0;
    pollRef.current = setInterval(async () => {
      attempts++;
      try {
        const r = await telegramAccount.connectionStatus();
        if (r.data.connected) {
          setStatus(r.data);
          setConnecting(false);
          stopPolling();
          toast.success('Telegram account connected!');
          track('telegram_connected');
          await onUserRefresh();
        }
      } catch { /* ignore */ }
      if (attempts >= 40) { // 2 minutes
        stopPolling();
        setConnecting(false);
      }
    }, 3000);
  };

  const handleConnect = async () => {
    setLoading(true);
    try {
      const r = await telegramAccount.generateConnectCode();
      const { url } = r.data;
      window.open(url, '_blank', 'noopener,noreferrer');
      setConnecting(true);
      startPolling();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to generate connect code');
    } finally {
      setLoading(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await telegramAccount.disconnect();
      setStatus({ connected: false, telegram_username: null, telegram_first_name: null, connected_at: null });
      setDisconnectOpen(false);
      toast.success('Telegram disconnected');
      await onUserRefresh();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to disconnect');
    }
  };

  if (status.connected) {
    return (
      <Box>
        <Alert severity="success" icon={<CheckCircle />} sx={{ mb: 2 }}>
          Telegram account connected
          {status.telegram_first_name && <strong> {status.telegram_first_name}</strong>}
          {status.telegram_username && <span style={{ color: 'inherit', opacity: 0.75 }}> (@{status.telegram_username})</span>}.
          {status.connected_at && (
            <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
              Since {new Date(status.connected_at).toLocaleDateString()}
            </Typography>
          )}
        </Alert>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Groups you add via @telegizer_bot are automatically linked to your account.
          Custom bots can be connected directly in the Telegram app.
        </Typography>
        <Button
          variant="outlined"
          color="error"
          startIcon={<LinkOff />}
          onClick={() => setDisconnectOpen(true)}
          size="small"
        >
          Disconnect Telegram
        </Button>

        <Dialog open={disconnectOpen} onClose={() => setDisconnectOpen(false)} maxWidth="xs" fullWidth>
          <DialogTitle fontWeight={700}>Disconnect Telegram?</DialogTitle>
          <DialogContent>
            <Typography variant="body2">
              This will unlink your Telegram identity. Groups won't auto-link anymore and
              you won't be able to submit bot tokens via the Telegram app until you reconnect.
            </Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDisconnectOpen(false)}>Cancel</Button>
            <Button variant="contained" color="error" onClick={handleDisconnect}>Disconnect</Button>
          </DialogActions>
        </Dialog>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Link your Telegram account to Telegizer so groups and bots you manage via
        @telegizer_bot appear in your dashboard automatically — no code entry needed.
      </Typography>
      {connecting ? (
        <Alert severity="info" icon={<CircularProgress size={18} />} sx={{ mb: 2 }}>
          Waiting for you to open the bot and confirm…{' '}
          <Button size="small" onClick={() => { setConnecting(false); stopPolling(); }}>Cancel</Button>
        </Alert>
      ) : (
        <Button
          variant="contained"
          startIcon={<Telegram />}
          onClick={handleConnect}
          disabled={loading}
          endIcon={<OpenInNew fontSize="small" />}
        >
          {loading ? <CircularProgress size={20} color="inherit" /> : 'Connect Telegram'}
        </Button>
      )}
    </Box>
  );
}

// ── Linked Telegram Accounts ───────────────────────────────────────────────────
function LinkedTelegramAccountsSection() {
  const [accounts, setAccounts] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [addingCode, setAddingCode] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const r = await telegramAccount.listLinkedAccounts();
      setAccounts(r.data.accounts || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const handleAddAccount = async () => {
    setAddingCode(true);
    try {
      const r = await telegramAccount.generateConnectCode();
      window.open(r.data.url, '_blank', 'noopener,noreferrer');
      // Poll briefly for the new account to appear
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const r2 = await telegramAccount.listLinkedAccounts();
          const newAccounts = r2.data.accounts || [];
          if (newAccounts.length > accounts.length) {
            setAccounts(newAccounts);
            clearInterval(poll);
            setAddingCode(false);
            toast.success('New Telegram account linked!');
          }
        } catch { /* ignore */ }
        if (attempts >= 40) { clearInterval(poll); setAddingCode(false); }
      }, 3000);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to generate connect code');
      setAddingCode(false);
    }
  };

  const handleRemove = async (id) => {
    try {
      await telegramAccount.removeLinkedAccount(id);
      setAccounts(prev => prev.filter(a => a.id !== id));
      toast.success('Account unlinked');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to unlink');
    }
  };

  const handleSetPrimary = async (id) => {
    try {
      await telegramAccount.setPrimaryAccount(id);
      setAccounts(prev => prev.map(a => ({ ...a, is_primary: a.id === id })));
      toast.success('Primary account updated');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to update primary');
    }
  };

  if (loading) return <CircularProgress size={20} />;

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" mb={1.5}>
        Link multiple Telegram accounts to the same email — manage all your groups and bots
        from one dashboard regardless of which Telegram account you're using.
      </Typography>

      {accounts.length > 0 && (
        <List dense disablePadding sx={{ mb: 2 }}>
          {accounts.map((acct) => (
            <ListItem
              key={acct.id ?? acct.telegram_user_id}
              sx={{ px: 0, py: 0.5, borderBottom: '1px solid', borderColor: 'divider' }}
            >
              <Telegram sx={{ fontSize: 18, color: 'primary.main', mr: 1.5 }} />
              <ListItemText
                primary={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Typography fontSize="0.88rem" fontWeight={500}>
                      {acct.telegram_first_name || 'Unknown'}
                      {acct.telegram_username && (
                        <Typography component="span" fontSize="0.82rem" color="text.secondary"> @{acct.telegram_username}</Typography>
                      )}
                    </Typography>
                    {acct.is_primary && <Chip label="Primary" size="small" color="primary" sx={{ height: 18, fontSize: '0.65rem' }} />}
                  </Box>
                }
                secondary={acct.linked_at ? `Linked ${new Date(acct.linked_at).toLocaleDateString()}` : ''}
              />
              <ListItemSecondaryAction sx={{ display: 'flex', gap: 0.5 }}>
                {!acct.is_primary && acct.id && (
                  <Tooltip title="Set as primary">
                    <IconButton size="small" onClick={() => handleSetPrimary(acct.id)}>
                      <StarBorder fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
                {acct.is_primary && <Star fontSize="small" sx={{ color: 'warning.main', mt: 0.5 }} />}
                {acct.id && (
                  <Tooltip title="Unlink">
                    <IconButton size="small" color="error" onClick={() => handleRemove(acct.id)}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
              </ListItemSecondaryAction>
            </ListItem>
          ))}
        </List>
      )}

      <Button
        variant="outlined"
        size="small"
        startIcon={addingCode ? <CircularProgress size={16} /> : <Add />}
        onClick={handleAddAccount}
        disabled={addingCode}
      >
        {addingCode ? 'Waiting for confirmation…' : 'Add Telegram Account'}
      </Button>
    </Box>
  );
}

// ── Google Calendar Section ────────────────────────────────────────────────────
function GoogleCalendarSection() {
  const [status, setStatus] = useState(null);
  const [events, setEvents] = useState(null);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState('');

  const loadStatus = useCallback(async () => {
    try {
      const { data } = await calApi.status();
      setStatus(data);
    } catch { setStatus({ connected: false }); }
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  // Handle redirect-back from Google OAuth
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const cal = params.get('calendar');
    if (cal === 'connected') {
      loadStatus();
      window.history.replaceState({}, '', window.location.pathname);
    } else if (cal === 'error') {
      setError('Google Calendar connection failed. Please try again.');
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [loadStatus]);

  const connect = async () => {
    setConnecting(true);
    setError('');
    try {
      const { data } = await calApi.getAuthUrl();
      window.location.href = data.auth_url;
    } catch (e) {
      const msg = e?.response?.data?.error;
      if (msg?.includes('not configured')) setError('Google Calendar is not configured on this server yet.');
      else setError('Failed to start Google OAuth. Please try again.');
      setConnecting(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm('Disconnect Google Calendar?')) return;
    setDisconnecting(true);
    try {
      await calApi.disconnect();
      setStatus({ connected: false });
      setEvents(null);
    } catch { setError('Failed to disconnect.'); }
    finally { setDisconnecting(false); }
  };

  const loadEvents = async () => {
    setLoadingEvents(true);
    try {
      const { data } = await calApi.listEvents();
      setEvents(data.events || []);
    } catch { setEvents([]); }
    finally { setLoadingEvents(false); }
  };

  if (!status) return <CircularProgress size={20} />;

  return (
    <Box>
      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}
      {status.connected ? (
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
            <CheckCircle color="success" />
            <Box>
              <Typography fontWeight={600} fontSize="0.9rem">Connected</Typography>
              {status.email && <Typography fontSize="0.8rem" color="text.secondary">{status.email}</Typography>}
            </Box>
            <Button size="small" color="error" startIcon={<LinkOff />} sx={{ ml: 'auto' }} onClick={disconnect} disabled={disconnecting}>
              {disconnecting ? 'Disconnecting…' : 'Disconnect'}
            </Button>
          </Box>
          {events === null ? (
            <Button size="small" variant="outlined" onClick={loadEvents} disabled={loadingEvents}>
              {loadingEvents ? 'Loading…' : 'Show upcoming events'}
            </Button>
          ) : events.length === 0 ? (
            <Alert severity="info">No upcoming events found.</Alert>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              {events.slice(0, 8).map(e => (
                <Box key={e.id} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
                  <CalendarMonth sx={{ fontSize: 16, color: 'text.disabled', flexShrink: 0 }} />
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography fontSize="0.85rem" fontWeight={500} noWrap>{e.summary}</Typography>
                    <Typography fontSize="0.72rem" color="text.secondary">
                      {e.start ? new Date(e.start).toLocaleString() : 'All day'}
                    </Typography>
                  </Box>
                  {e.html_link && (
                    <IconButton size="small" href={e.html_link} target="_blank" rel="noopener noreferrer">
                      <OpenInNew fontSize="small" />
                    </IconButton>
                  )}
                </Box>
              ))}
            </Box>
          )}
        </Box>
      ) : (
        <Box>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Connect your Google Calendar to sync reminders and meetings. Upcoming events will appear alongside your workspace schedule.
          </Typography>
          <Button variant="contained" startIcon={<CalendarMonth />} onClick={connect} disabled={connecting}>
            {connecting ? 'Connecting…' : 'Connect Google Calendar'}
          </Button>
        </Box>
      )}
    </Box>
  );
}

// ── Team Section ──────────────────────────────────────────────────────────────
const ROLE_LABELS = { owner: 'Owner', admin: 'Admin', member: 'Member' };
const ROLE_COLORS = { owner: 'primary', admin: 'secondary', member: 'default' };

function TeamSection() {
  const [team, setTeam] = useState(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [teamName, setTeamName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviting, setInviting] = useState(false);
  const [inviteLink, setInviteLink] = useState('');
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await teamApi.get();
      setTeam(data.team || null);
    } catch {
      setTeam(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createTeam = async () => {
    if (!teamName.trim()) return;
    setCreating(true);
    try {
      await teamApi.create({ name: teamName.trim() });
      await load();
      toast.success('Team created!');
    } catch (e) {
      toast.error(e?.response?.data?.error || 'Failed to create team');
    } finally {
      setCreating(false);
    }
  };

  const invite = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      const { data } = await teamApi.invite({ email: inviteEmail.trim(), role: inviteRole });
      setInviteLink(data.invite_url);
      setInviteEmail('');
      toast.success('Invite created!');
    } catch (e) {
      toast.error(e?.response?.data?.error || 'Failed to create invite');
    } finally {
      setInviting(false);
    }
  };

  const removeMember = async (userId) => {
    try {
      await teamApi.removeMember(userId);
      await load();
      toast.success('Member removed');
    } catch {
      toast.error('Failed to remove member');
    }
  };

  const copyLink = () => {
    navigator.clipboard.writeText(inviteLink).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (loading) {
    return (
      <Section title="Team Members" icon={<Group color="primary" />}>
        <LinearProgress />
      </Section>
    );
  }

  const me = safeParseUser();
  const myRole = team?.members?.find(m => m.user_id === me.id)?.role;
  const canManage = myRole === 'owner' || myRole === 'admin';

  if (!team) {
    return (
      <Section title="Team Members" icon={<Group color="primary" />}>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Create a team to invite collaborators to your workspace. Team members share access to your groups and settings.
        </Typography>
        <Alert severity="info" sx={{ mb: 2 }}>
          Team collaboration requires a <strong>Pro</strong> plan. Free users can create a team and invite up to 1 member.
        </Alert>
        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <TextField
            size="small"
            label="Team name"
            value={teamName}
            onChange={e => setTeamName(e.target.value)}
            placeholder="e.g. Acme Community"
            sx={{ minWidth: 220 }}
            onKeyDown={e => e.key === 'Enter' && createTeam()}
          />
          <Button
            variant="contained"
            startIcon={creating ? <CircularProgress size={16} color="inherit" /> : <Group />}
            onClick={createTeam}
            disabled={creating || !teamName.trim()}
          >
            Create Team
          </Button>
        </Box>
      </Section>
    );
  }

  return (
    <Section title={`Team — ${team.name}`} icon={<Group color="primary" />}>
      {/* Members list */}
      <List dense disablePadding sx={{ mb: 2 }}>
        {(team.members || []).map(m => (
          <ListItem
            key={m.user_id}
            disablePadding
            sx={{ py: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}
          >
            <ListItemText
              primary={m.full_name || m.email || `User #${m.user_id}`}
              secondary={m.email}
              primaryTypographyProps={{ variant: 'body2', fontWeight: 600 }}
              secondaryTypographyProps={{ variant: 'caption' }}
            />
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexShrink: 0 }}>
              <Chip label={ROLE_LABELS[m.role] || m.role} color={ROLE_COLORS[m.role]} size="small" />
              {canManage && m.role !== 'owner' && m.user_id !== me.id && (
                <Tooltip title="Remove member">
                  <IconButton size="small" onClick={() => removeMember(m.user_id)} color="error">
                    <Cancel sx={{ fontSize: 16 }} />
                  </IconButton>
                </Tooltip>
              )}
            </Box>
          </ListItem>
        ))}
      </List>

      {/* Invite form — owners and admins only */}
      {canManage && (
        <Box>
          <Typography variant="body2" fontWeight={600} mb={1.5}>Invite a new member</Typography>
          <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'flex-start', mb: 1.5 }}>
            <TextField
              size="small"
              label="Email address"
              type="email"
              value={inviteEmail}
              onChange={e => setInviteEmail(e.target.value)}
              placeholder="colleague@example.com"
              sx={{ minWidth: 220, flex: 1 }}
            />
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Role</InputLabel>
              <Select label="Role" value={inviteRole} onChange={e => setInviteRole(e.target.value)}>
                <MenuItem value="admin">Admin</MenuItem>
                <MenuItem value="member">Member</MenuItem>
              </Select>
            </FormControl>
            <Button
              variant="contained"
              startIcon={inviting ? <CircularProgress size={16} color="inherit" /> : <PersonAdd />}
              onClick={invite}
              disabled={inviting || !inviteEmail.trim()}
            >
              Invite
            </Button>
          </Box>

          {/* Invite link copy */}
          {inviteLink && (
            <Alert
              severity="success"
              sx={{ mb: 1 }}
              action={
                <Button size="small" startIcon={<ContentCopy />} onClick={copyLink}>
                  {copied ? 'Copied!' : 'Copy Link'}
                </Button>
              }
            >
              Invite link generated. Share it with your teammate.
            </Alert>
          )}

          {/* Pending invites */}
          {(team.pending_invites || []).length > 0 && (
            <Box mt={2}>
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                Pending invites
              </Typography>
              {team.pending_invites.map(inv => (
                <Box key={inv.id} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                  <Typography variant="caption" sx={{ flex: 1 }}>{inv.invited_email}</Typography>
                  <Chip label={ROLE_LABELS[inv.role] || inv.role} size="small" variant="outlined" />
                  <Tooltip title="Cancel invite">
                    <IconButton size="small" onClick={() => teamApi.cancelInvite(inv.id).then(load)} color="error">
                      <Cancel sx={{ fontSize: 14 }} />
                    </IconButton>
                  </Tooltip>
                </Box>
              ))}
            </Box>
          )}
        </Box>
      )}
    </Section>
  );
}

// ── Main Settings Page ─────────────────────────────────────────────────────────
export default function Settings() {
  const navigate = useNavigate();
  const [user, setUser] = useState(safeParseUser);
  const [subscription, setSubscription] = useState(null);

  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwLoading, setPwLoading] = useState(false);

  const [timezone, setTimezone] = useState('');
  const [tzSaving, setTzSaving] = useState(false);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePw, setDeletePw] = useState('');
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleting, setDeleting] = useState(false);

  const [exportingData, setExportingData] = useState(false);

  const [refStats, setRefStats] = useState(null);
  const [refCopied, setRefCopied] = useState(false);

  const fetchUser = useCallback(async () => {
    try {
      const res = await auth.getMe();
      const fresh = res.data.user;
      localStorage.setItem('user', JSON.stringify(fresh));
      setUser(fresh);
      return fresh;
    } catch { /* 401 handled by interceptor */ }
  }, []);

  const fetchSub = useCallback(async () => {
    try {
      const res = await billing.getSubscription();
      setSubscription(res.data.subscription);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchUser();
    fetchSub();
    const saved = localStorage.getItem('user_timezone') || '';
    setTimezone(saved);
    referralsApi.getStats().then(r => setRefStats(r.data)).catch(() => {});
  }, [fetchUser, fetchSub]);

  const handleChangePassword = async () => {
    if (!currentPw || !newPw) {
      toast.error('Fill in all password fields');
      return;
    }
    if (newPw.length < 8) {
      toast.error('New password must be at least 8 characters');
      return;
    }
    if (newPw !== confirmPw) {
      toast.error('New passwords do not match');
      return;
    }
    setPwLoading(true);
    try {
      await auth.changePassword({ current_password: currentPw, new_password: newPw });
      toast.success('Password changed successfully');
      setCurrentPw('');
      setNewPw('');
      setConfirmPw('');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to change password');
    } finally {
      setPwLoading(false);
    }
  };

  const handleSaveTimezone = () => {
    setTzSaving(true);
    try {
      localStorage.setItem('user_timezone', timezone);
      toast.success('Timezone preference saved');
    } finally {
      setTzSaving(false);
    }
  };

  const handleExportData = async () => {
    setExportingData(true);
    try {
      await userSettings.exportData();
      toast.success('Export requested — check your email within 24 hours.');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to request export. Please try again later.');
    } finally {
      setExportingData(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!deletePw) {
      toast.error('Enter your password to confirm deletion');
      return;
    }
    if (deleteConfirmText !== 'DELETE') {
      toast.error('Type DELETE in the confirmation field to proceed');
      return;
    }
    setDeleting(true);
    try {
      await userSettings.deleteAccount({ password: deletePw });
      toast.success('Account deletion scheduled. Your data will be removed within 30 days.');
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      navigate('/');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to delete account');
    } finally {
      setDeleting(false);
    }
  };

  const tier = subscription?.tier || user.subscription_tier || 'free';
  const isTrial = !subscription?.expires && !!user.trial_ends_at;
  const expires = subscription?.expires
    ? new Date(subscription.expires)
    : (user.trial_ends_at ? new Date(user.trial_ends_at) : null);
  const tierColor = tier === 'enterprise' ? 'secondary' : tier === 'pro' ? 'primary' : 'default';

  const botUsername = (process.env.REACT_APP_TELEGRAM_BOT_USERNAME || 'telegizer_bot').replace(/^@/, '');
  const refCode = refStats?.referral_code;
  const refLink = refCode
    ? `https://t.me/${botUsername}?start=ref_${refCode}`
    : '';

  const handleRefCopy = () => {
    if (!refLink) return;
    navigator.clipboard.writeText(refLink).then(() => {
      setRefCopied(true);
      setTimeout(() => setRefCopied(false), 2000);
    });
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate('/dashboard')} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          <SmartToy sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="h6" fontWeight={700} sx={{ flexGrow: 1 }}>
            Account Settings
          </Typography>
        </Toolbar>
      </AppBar>

      <Box sx={{ maxWidth: 700, mx: 'auto', p: { xs: 2, md: 3 } }}>

        {/* Profile */}
        <Section title="Profile" icon={<Person color="primary" />}>
          <Stack spacing={1.5}>
            <Box>
              <Typography variant="caption" color="text.secondary">Full Name</Typography>
              <Typography variant="body1" fontWeight={500}>{user.full_name || '—'}</Typography>
            </Box>
            <Divider />
            <Box>
              {/* Telegram-only: no email linked yet */}
              {!user.email && user.auth_provider === 'telegram' ? (
                <>
                  <Typography variant="caption" color="text.secondary">Recovery Email</Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mt: 0.25 }}>
                    <MailOutline sx={{ fontSize: 18, color: 'text.disabled' }} />
                    <Typography variant="body1" color="text.secondary" fontStyle="italic">Not added</Typography>
                    <Chip
                      label="Optional"
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: '0.65rem', height: 18 }}
                    />
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                    Add an email and password to log in from the website and recover your account.
                  </Typography>
                </>
              ) : (
                <>
                  <Typography variant="caption" color="text.secondary">Email</Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                    <Typography variant="body1">{user.email || '—'}</Typography>
                    {user.email && user.email_verified === false && (
                      <Chip
                        label="Unverified"
                        size="small"
                        color="warning"
                        onClick={() => navigate('/verify-email')}
                        sx={{ cursor: 'pointer' }}
                      />
                    )}
                    {user.email_verified === true && (
                      <Chip label="Verified" size="small" color="success" icon={<CheckCircle />} />
                    )}
                  </Box>
                </>
              )}
            </Box>
            <Divider />
            <Box>
              <Typography variant="caption" color="text.secondary">Member since</Typography>
              <Typography variant="body1">
                {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
              </Typography>
            </Box>
          </Stack>
        </Section>

        {/* Invite Friends */}
        <Section title="Invite Friends — Earn Free Pro" icon={<CardGiftcard color="primary" />}>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Share your link. When friends sign up and activate, you earn free Pro time automatically.
          </Typography>
          {refLink ? (
            <Box
              sx={{
                display: 'flex', alignItems: 'center', gap: 1,
                bgcolor: 'action.hover', borderRadius: 1.5, px: 1.5, py: 1, mb: 2,
                border: '1px solid', borderColor: 'divider',
                overflow: 'hidden',
              }}
            >
              <Typography
                variant="body2"
                sx={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'monospace', fontSize: '0.78rem' }}
              >
                {refLink}
              </Typography>
              <Tooltip title={refCopied ? 'Copied!' : 'Copy link'}>
                <IconButton size="small" onClick={handleRefCopy}>
                  {refCopied ? <CheckCircle fontSize="small" color="success" /> : <ContentCopy fontSize="small" />}
                </IconButton>
              </Tooltip>
            </Box>
          ) : (
            <Box sx={{ bgcolor: 'action.hover', borderRadius: 1.5, px: 1.5, py: 1, mb: 2, border: '1px solid', borderColor: 'divider' }}>
              <Typography variant="body2" color="text.disabled" sx={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>Loading your referral link…</Typography>
            </Box>
          )}
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<ContentCopy fontSize="small" />}
              onClick={handleRefCopy}
              disabled={!refLink}
            >
              {refCopied ? 'Copied!' : 'Copy Link'}
            </Button>
            <Button
              variant="text"
              size="small"
              startIcon={<People fontSize="small" />}
              onClick={() => navigate('/referrals')}
            >
              View Referral Rewards
            </Button>
          </Box>
        </Section>

        {/* Current Plan */}
        <Section title="Current Plan" icon={<Schedule color="primary" />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
            <Chip label={tier.toUpperCase()} color={tierColor} size="medium" />
            {expires && (
              <Typography variant="body2" color="text.secondary">
                {isTrial ? 'Trial ends' : 'Expires'} {expires.toLocaleDateString()}
              </Typography>
            )}
            {!expires && tier !== 'free' && (
              <Typography variant="body2" color="text.secondary">No expiry</Typography>
            )}
          </Box>
          {tier !== 'enterprise' && (
            <Button variant="outlined" size="small" sx={{ mt: 2 }} onClick={() => navigate('/pricing')}>
              Upgrade Plan
            </Button>
          )}
          <Button
            variant="text"
            size="small"
            sx={{ mt: 1, ml: tier !== 'enterprise' ? 1 : 0 }}
            onClick={() => navigate('/billing')}
          >
            View Billing History
          </Button>
        </Section>

        {/* Change Password — hidden for Telegram-only users who have no password yet */}
        {user.email ? (
          <Section title="Change Password" icon={<Lock color="primary" />}>
            <Stack spacing={2}>
              <TextField
                fullWidth type="password" label="Current Password"
                value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} size="small"
              />
              <TextField
                fullWidth type="password" label="New Password"
                value={newPw} onChange={(e) => setNewPw(e.target.value)}
                size="small" helperText="At least 8 characters"
              />
              <TextField
                fullWidth type="password" label="Confirm New Password"
                value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} size="small"
                error={confirmPw.length > 0 && newPw !== confirmPw}
                helperText={confirmPw.length > 0 && newPw !== confirmPw ? 'Passwords do not match' : ''}
              />
              <Box>
                <Button variant="contained" onClick={handleChangePassword}
                  disabled={pwLoading || !currentPw || !newPw || !confirmPw}>
                  {pwLoading ? <CircularProgress size={20} color="inherit" /> : 'Update Password'}
                </Button>
              </Box>
            </Stack>
          </Section>
        ) : user.auth_provider === 'telegram' && (
          <Section title="Account Security" icon={<Lock color="primary" />}>
            <Alert severity="info" icon={<MailOutline />} sx={{ mb: 0 }}>
              <Typography variant="body2" fontWeight={600} gutterBottom>Add a recovery email to enable password login</Typography>
              <Typography variant="body2" color="text.secondary">
                You signed in with Telegram. Adding an email lets you log in from any browser and recover your account if you ever lose Telegram access.
              </Typography>
              <Button size="small" variant="outlined" sx={{ mt: 1.5 }} onClick={() => navigate('/settings#telegram')}>
                Add Email &amp; Password
              </Button>
            </Alert>
          </Section>
        )}

        {/* Connect Telegram */}
        <Section title="Connect Telegram Account" icon={<Telegram color="primary" />}>
          <TelegramConnectSection user={user} onUserRefresh={fetchUser} />
        </Section>

        {/* Linked Telegram Accounts */}
        <Section title="Linked Telegram Accounts" icon={<Telegram color="primary" />}>
          <LinkedTelegramAccountsSection />
        </Section>

        {/* Two-Factor Authentication — requires email/password */}
        {user.email && (
          <Section title="Two-Factor Authentication" icon={<Security color="primary" />}>
            <TwoFactorSection user={user} onUserRefresh={fetchUser} />
          </Section>
        )}

        {/* Default Timezone */}
        <Section title="Default Timezone" icon={<Schedule color="primary" />}>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Used as a default when creating scheduled messages.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ xs: 'stretch', sm: 'flex-start' }}>
            <Box sx={{ flexGrow: 1, minWidth: { xs: 0, sm: 200 } }}>
              <TimezoneSelect value={timezone} onChange={setTimezone} />
            </Box>
            <Button variant="outlined" onClick={handleSaveTimezone} disabled={tzSaving} sx={{ mt: { xs: 1, sm: 0 } }}>
              Save
            </Button>
          </Stack>
        </Section>

        {/* Google Calendar */}
        <Section title="Google Calendar" icon={<CalendarMonth color="primary" />}>
          <GoogleCalendarSection />
        </Section>

        {/* Onboarding Tour */}
        <Section title="Product Tour" icon={<Tour color="primary" />}>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Replay the guided walkthrough to revisit the key features of Telegizer.
          </Typography>
          <Button
            variant="outlined"
            startIcon={<Tour />}
            onClick={async () => { await resetTour(); window.location.reload(); }}
          >
            Retake Onboarding Tour
          </Button>
        </Section>

        {/* Team Members */}
        <TeamSection />

        {/* Data Privacy */}
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>Data & Privacy</Typography>
            <Typography variant="body2" color="text.secondary" mb={2}>
              Download a copy of all your data stored on Telegizer (GDPR Art. 20).
              You will receive an email with your data within 24 hours.
            </Typography>
            <Button
              variant="outlined"
              startIcon={exportingData ? <CircularProgress size={16} /> : null}
              onClick={handleExportData}
              disabled={exportingData}
            >
              {exportingData ? 'Requesting…' : 'Download My Data'}
            </Button>
          </CardContent>
        </Card>

        {/* Danger Zone */}
        <Card sx={{ mb: 3, border: '1px solid', borderColor: 'error.dark' }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <DeleteForever color="error" />
              <Typography variant="subtitle1" fontWeight={700} color="error.main">Danger Zone</Typography>
            </Box>
            <Alert severity="error" sx={{ mb: 2 }}>
              Deleting your account permanently removes all bots, groups, members, and settings.
              This action cannot be undone.
            </Alert>
            <Button
              variant="outlined" color="error" startIcon={<DeleteForever />}
              onClick={() => setDeleteOpen(true)}
            >
              Delete My Account
            </Button>
          </CardContent>
        </Card>

      </Box>

      <Dialog open={deleteOpen} onClose={() => { setDeleteOpen(false); setDeletePw(''); setDeleteConfirmText(''); }} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ color: 'error.main', fontWeight: 700 }}>Delete Account</DialogTitle>
        <DialogContent>
          <Alert severity="error" sx={{ mb: 2 }}>
            This will permanently schedule deletion of your account and all data (bots, groups, settings).
            You will have 30 days before the data is fully erased.
          </Alert>
          <TextField
            fullWidth type="password" label="Your Password"
            value={deletePw} onChange={(e) => setDeletePw(e.target.value)}
            sx={{ mb: 2 }}
            autoFocus
          />
          <TextField
            fullWidth label='Type "DELETE" to confirm'
            value={deleteConfirmText} onChange={(e) => setDeleteConfirmText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleDeleteAccount()}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setDeleteOpen(false); setDeletePw(''); setDeleteConfirmText(''); }} disabled={deleting}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDeleteAccount}
            disabled={deleting || !deletePw || deleteConfirmText !== 'DELETE'}>
            {deleting ? <CircularProgress size={20} color="inherit" /> : 'Delete Forever'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
