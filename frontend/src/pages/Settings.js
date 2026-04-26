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
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { auth, totp as totpApi, billing, userSettings, telegramAccount } from '../services/api';
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
      setStatus({ connected: false, telegram_username: null, connected_at: null });
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
          {status.telegram_username && <strong> @{status.telegram_username}</strong>}.
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
  const [deleting, setDeleting] = useState(false);

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

  const handleDeleteAccount = async () => {
    if (!deletePw) {
      toast.error('Enter your password to confirm deletion');
      return;
    }
    setDeleting(true);
    try {
      await userSettings.deleteAccount({ password: deletePw });
      toast.success('Account deleted');
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
  const expires = subscription?.expires ? new Date(subscription.expires) : null;
  const tierColor = tier === 'enterprise' ? 'secondary' : tier === 'pro' ? 'primary' : 'default';

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
              <Typography variant="caption" color="text.secondary">Email</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Typography variant="body1">{user.email || '—'}</Typography>
                {user.email_verified === false && (
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

        {/* Current Plan */}
        <Section title="Current Plan" icon={<Schedule color="primary" />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
            <Chip label={tier.toUpperCase()} color={tierColor} size="medium" />
            {expires && (
              <Typography variant="body2" color="text.secondary">
                Expires {expires.toLocaleDateString()}
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

        {/* Change Password */}
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
              <Button
                variant="contained"
                onClick={handleChangePassword}
                disabled={pwLoading || !currentPw || !newPw || !confirmPw}
              >
                {pwLoading ? <CircularProgress size={20} color="inherit" /> : 'Update Password'}
              </Button>
            </Box>
          </Stack>
        </Section>

        {/* Connect Telegram */}
        <Section title="Connect Telegram Account" icon={<Telegram color="primary" />}>
          <TelegramConnectSection user={user} onUserRefresh={fetchUser} />
        </Section>

        {/* Two-Factor Authentication */}
        <Section title="Two-Factor Authentication" icon={<Security color="primary" />}>
          <TwoFactorSection user={user} onUserRefresh={fetchUser} />
        </Section>

        {/* Default Timezone */}
        <Section title="Default Timezone" icon={<Schedule color="primary" />}>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Used as a default when creating scheduled messages.
          </Typography>
          <Stack direction="row" spacing={2} alignItems="flex-start" flexWrap="wrap">
            <Box sx={{ flexGrow: 1, minWidth: 200 }}>
              <TimezoneSelect value={timezone} onChange={setTimezone} />
            </Box>
            <Button variant="outlined" onClick={handleSaveTimezone} disabled={tzSaving} sx={{ mt: { xs: 1, sm: 0 } }}>
              Save
            </Button>
          </Stack>
        </Section>

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

      <Dialog open={deleteOpen} onClose={() => { setDeleteOpen(false); setDeletePw(''); }} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ color: 'error.main', fontWeight: 700 }}>Delete Account</DialogTitle>
        <DialogContent>
          <Typography variant="body2" mb={2}>
            This will permanently delete your account and all associated data. Enter your password to confirm.
          </Typography>
          <TextField
            fullWidth type="password" label="Your Password"
            value={deletePw} onChange={(e) => setDeletePw(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleDeleteAccount()}
            autoFocus
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setDeleteOpen(false); setDeletePw(''); }} disabled={deleting}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDeleteAccount} disabled={deleting || !deletePw}>
            {deleting ? <CircularProgress size={20} color="inherit" /> : 'Delete Forever'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
