import React, { useState } from 'react';
import {
  Box, Card, CardContent, TextField, Button, Typography,
  Alert, CircularProgress, Link, InputAdornment, IconButton,
} from '@mui/material';
import { Visibility, VisibilityOff, Lock } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { auth } from '../services/api';

export default function Login() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: '', password: '' });
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 2FA flow state
  const [requires2FA, setRequires2FA] = useState(false);
  const [pendingToken, setPendingToken] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [totpLoading, setTotpLoading] = useState(false);

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await auth.login(form);
      if (res.data.requires_2fa) {
        // Step 2: need TOTP code
        setPendingToken(res.data.totp_pending_token);
        setRequires2FA(true);
      } else {
        localStorage.setItem('token', res.data.token);
        localStorage.setItem('user', JSON.stringify(res.data.user));
        toast.success('Welcome back!');
        navigate('/dashboard');
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleTotpSubmit = async (e) => {
    e.preventDefault();
    if (!totpCode.trim()) return;
    setError('');
    setTotpLoading(true);
    try {
      const res = await auth.verifyTotpLogin({
        totp_pending_token: pendingToken,
        totp_code: totpCode.trim(),
      });
      localStorage.setItem('token', res.data.token);
      localStorage.setItem('user', JSON.stringify(res.data.user));
      toast.success('Welcome back!');
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.error || 'Invalid 2FA code. Try again.');
    } finally {
      setTotpLoading(false);
    }
  };

  // ── 2FA code entry screen ────────────────────────────────────────────────────
  if (requires2FA) {
    return (
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #0d1117 0%, #161b22 100%)',
          p: 2,
        }}
      >
        <Card sx={{ width: '100%', maxWidth: 420 }}>
          <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, mb: 1 }}>
              <Lock color="primary" />
              <Typography variant="h5" fontWeight={700}>Two-Factor Auth</Typography>
            </Box>
            <Typography variant="body2" color="text.secondary" textAlign="center" mb={3}>
              Enter the 6-digit code from your authenticator app, or one of your backup codes.
            </Typography>

            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

            <form onSubmit={handleTotpSubmit}>
              <TextField
                fullWidth
                label="2FA Code"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                placeholder="000000"
                inputProps={{ maxLength: 12, inputMode: 'numeric' }}
                autoFocus
                sx={{ mb: 3 }}
              />
              <Button
                type="submit"
                fullWidth
                variant="contained"
                size="large"
                disabled={totpLoading || !totpCode.trim()}
                sx={{ mb: 2 }}
              >
                {totpLoading ? <CircularProgress size={24} color="inherit" /> : 'Verify'}
              </Button>
            </form>

            <Typography variant="body2" textAlign="center" color="text.secondary">
              <Link
                component="button"
                onClick={() => { setRequires2FA(false); setPendingToken(''); setError(''); }}
                sx={{ color: 'text.secondary', cursor: 'pointer' }}
              >
                Back to login
              </Link>
            </Typography>
          </CardContent>
        </Card>
      </Box>
    );
  }

  // ── Normal login screen ──────────────────────────────────────────────────────
  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #0d1117 0%, #161b22 100%)',
        p: 2,
      }}
    >
      <Card sx={{ width: '100%', maxWidth: 420 }}>
        <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
          <Typography variant="h4" fontWeight={700} mb={0.5} textAlign="center">
            BotForge
          </Typography>
          <Typography variant="body2" color="text.secondary" textAlign="center" mb={3}>
            Sign in to manage your Telegram bots
          </Typography>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <form onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="Email"
              name="email"
              type="email"
              value={form.email}
              onChange={handleChange}
              required
              sx={{ mb: 2 }}
              autoComplete="email"
            />
            <TextField
              fullWidth
              label="Password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              value={form.password}
              onChange={handleChange}
              required
              sx={{ mb: 3 }}
              autoComplete="current-password"
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowPassword((p) => !p)} edge="end" size="small">
                      {showPassword ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
            <Button
              type="submit"
              fullWidth
              variant="contained"
              size="large"
              disabled={loading}
              sx={{ mb: 2 }}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : 'Sign In'}
            </Button>
          </form>

          <Typography variant="body2" textAlign="center" color="text.secondary" mb={1}>
            <Link
              component="button"
              onClick={() => navigate('/forgot-password')}
              sx={{ color: 'text.secondary', cursor: 'pointer' }}
            >
              Forgot password?
            </Link>
          </Typography>
          <Typography variant="body2" textAlign="center" color="text.secondary" mb={2}>
            Don't have an account?{' '}
            <Link
              component="button"
              onClick={() => navigate('/register')}
              sx={{ color: 'primary.main', cursor: 'pointer' }}
            >
              Sign up free
            </Link>
          </Typography>

          <Typography variant="caption" textAlign="center" color="text.disabled" display="block">
            <Link component="button" onClick={() => navigate('/terms')} sx={{ color: 'text.disabled', cursor: 'pointer', fontSize: 'inherit' }}>
              Terms of Service
            </Link>
            {' · '}
            <Link component="button" onClick={() => navigate('/privacy')} sx={{ color: 'text.disabled', cursor: 'pointer', fontSize: 'inherit' }}>
              Privacy Policy
            </Link>
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
