import React, { useState, useEffect, useRef } from 'react';
import {
  Box, Card, CardContent, TextField, Button, Typography,
  Alert, CircularProgress, Link, FormControlLabel, Checkbox,
} from '@mui/material';
import { CardGiftcard } from '@mui/icons-material';
import TelegizerLogo from '../components/TelegizerLogo';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { auth } from '../services/api';
import { generateFingerprint } from '../utils/fingerprint';
import { track, identify } from '../services/analytics';
import usePageMeta from '../hooks/usePageMeta';

export default function Register() {
  usePageMeta(
    'Create Your Free Account',
    'Create a free Telegizer account — includes a 14-day Pro trial. Connect your Telegram bot and automate moderation in minutes.'
  );
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const refCode = searchParams.get('ref') || '';
  const [form, setForm] = useState({ email: '', password: '', full_name: '' });
  // One checkbox covers ToS + Privacy + AUP (less signup friction); the backend
  // still receives both explicit acceptance flags.
  const [legalAccepted, setLegalAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  // Device fingerprint — generated once on mount, sent with registration payload
  const fingerprintRef = useRef('');

  useEffect(() => {
    fingerprintRef.current = generateFingerprint();
  }, []);

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (form.password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (!legalAccepted) {
      setError('You must accept the Terms of Service, Privacy Policy, and Acceptable Use Policy to continue.');
      return;
    }
    setLoading(true);
    try {
      const res = await auth.register({
        ...form,
        ref: refCode,
        device_fingerprint: fingerprintRef.current,
        tos_accepted: true,   // 1-D-05
        aup_accepted: true,
      });
      // Cookies set by server; only persist non-sensitive user data
      if (res.data.user) {
        localStorage.setItem('user', JSON.stringify(res.data.user));
        identify(res.data.user.id, { plan: res.data.user.subscription_tier });
      }
      track('signup_completed', { ref_code: refCode || null });
      toast.success('Account created — your 14-day Pro trial is active! Verify your email to continue.');
      navigate('/verify-email');
    } catch (err) {
      const code = err.response?.data?.code;
      const msg = err.response?.data?.error;
      if (code === 'IP_SIGNUP_LIMIT') {
        setError(
          'Too many accounts were created from this network. ' +
          'Please try again later or contact support.'
        );
      } else {
        setError(msg || 'Registration failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

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
      <Card sx={{ width: '100%', maxWidth: { xs: '95vw', sm: 420 } }}>
        <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
          <Box sx={{ display: 'flex', justifyContent: 'center', mb: 1.5 }}>
            <TelegizerLogo size="lg" />
          </Box>
          <Typography variant="body2" color="text.secondary" textAlign="center" mb={refCode ? 2 : 3}>
            Create your account to get started
          </Typography>

          {refCode && (
            <Alert
              severity="success"
              icon={<CardGiftcard />}
              sx={{ mb: 2, alignItems: 'center' }}
            >
              <Typography variant="body2" fontWeight={600}>You were invited!</Typography>
              <Typography variant="caption" color="text.secondary">
                Sign up now — your friend referred you to Telegizer.
                They get a Pro trial reward when you join. Start free, no card needed.
              </Typography>
            </Alert>
          )}

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <form onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="Full Name"
              name="full_name"
              value={form.full_name}
              onChange={handleChange}
              required
              sx={{ mb: 2 }}
              autoComplete="name"
            />
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
              type="password"
              value={form.password}
              onChange={handleChange}
              required
              helperText="Minimum 8 characters"
              sx={{ mb: 3 }}
              autoComplete="new-password"
            />
            <FormControlLabel
              sx={{ mb: 2, alignItems: 'flex-start' }}
              control={
                <Checkbox
                  checked={legalAccepted}
                  onChange={(e) => setLegalAccepted(e.target.checked)}
                  size="small"
                  sx={{ pt: 0.5 }}
                  required
                />
              }
              label={
                <Typography variant="caption" color="text.secondary">
                  {/* target=_blank so reading a policy never destroys the half-filled form */}
                  I agree to the{' '}
                  <Link href="/terms" target="_blank" rel="noopener" sx={{ color: 'primary.main', fontSize: 'inherit' }}>
                    Terms of Service
                  </Link>
                  {', '}
                  <Link href="/privacy" target="_blank" rel="noopener" sx={{ color: 'primary.main', fontSize: 'inherit' }}>
                    Privacy Policy
                  </Link>
                  {' '}and{' '}
                  <Link href="/acceptable-use" target="_blank" rel="noopener" sx={{ color: 'primary.main', fontSize: 'inherit' }}>
                    Acceptable Use Policy
                  </Link>
                  {' '}*
                </Typography>
              }
            />
            <Button
              type="submit"
              fullWidth
              variant="contained"
              size="large"
              disabled={loading || !legalAccepted}
              sx={{ mb: 2 }}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : 'Create Account'}
            </Button>
          </form>

          <Typography variant="body2" textAlign="center" color="text.secondary" mb={2}>
            Already have an account?{' '}
            <Link
              component="button"
              onClick={() => navigate('/login')}
              sx={{ color: 'primary.main', cursor: 'pointer' }}
            >
              Sign in
            </Link>
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
