import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  TextField, IconButton, Divider, Alert, CircularProgress,
  Dialog, DialogTitle, DialogContent, DialogActions, Stack,
  Chip,
} from '@mui/material';
import { ArrowBack, SmartToy, Person, Lock, DeleteForever, Schedule } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { auth, billing, userSettings } from '../services/api';
import TimezoneSelect from '../components/TimezoneSelect';

function safeParseUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

// ── Section wrapper ───────────────────────────────────────────────────────────
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

export default function Settings() {
  const navigate = useNavigate();
  const [user, setUser] = useState(safeParseUser);
  const [subscription, setSubscription] = useState(null);

  // Change password
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwLoading, setPwLoading] = useState(false);

  // Timezone
  const [timezone, setTimezone] = useState('');
  const [tzSaving, setTzSaving] = useState(false);

  // Delete account
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePw, setDeletePw] = useState('');
  const [deleting, setDeleting] = useState(false);

  const fetchUser = useCallback(async () => {
    try {
      const res = await auth.getMe();
      const fresh = res.data.user;
      localStorage.setItem('user', JSON.stringify(fresh));
      setUser(fresh);
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
    // Load saved timezone preference
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
              <Typography variant="body1">{user.email || '—'}</Typography>
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
            <Button
              variant="outlined"
              size="small"
              sx={{ mt: 2 }}
              onClick={() => navigate('/pricing')}
            >
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
              fullWidth
              type="password"
              label="Current Password"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              size="small"
            />
            <TextField
              fullWidth
              type="password"
              label="New Password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              size="small"
              helperText="At least 8 characters"
            />
            <TextField
              fullWidth
              type="password"
              label="Confirm New Password"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              size="small"
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

        {/* Timezone */}
        <Section title="Default Timezone" icon={<Schedule color="primary" />}>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Used as a default when creating scheduled messages.
          </Typography>
          <Stack direction="row" spacing={2} alignItems="flex-start" flexWrap="wrap">
            <Box sx={{ flexGrow: 1, minWidth: 200 }}>
              <TimezoneSelect value={timezone} onChange={setTimezone} />
            </Box>
            <Button
              variant="outlined"
              onClick={handleSaveTimezone}
              disabled={tzSaving}
              sx={{ mt: { xs: 1, sm: 0 } }}
            >
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
              variant="outlined"
              color="error"
              startIcon={<DeleteForever />}
              onClick={() => setDeleteOpen(true)}
            >
              Delete My Account
            </Button>
          </CardContent>
        </Card>

      </Box>

      {/* Delete Account Dialog */}
      <Dialog open={deleteOpen} onClose={() => { setDeleteOpen(false); setDeletePw(''); }} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ color: 'error.main', fontWeight: 700 }}>Delete Account</DialogTitle>
        <DialogContent>
          <Typography variant="body2" mb={2}>
            This will permanently delete your account and all associated data.
            Enter your password to confirm.
          </Typography>
          <TextField
            fullWidth
            type="password"
            label="Your Password"
            value={deletePw}
            onChange={(e) => setDeletePw(e.target.value)}
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
