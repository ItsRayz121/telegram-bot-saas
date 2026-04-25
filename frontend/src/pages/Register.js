import React, { useState, useEffect, useRef } from 'react';
import {
  Box, Card, CardContent, TextField, Button, Typography,
  Alert, CircularProgress, Link,
} from '@mui/material';
import { CardGiftcard } from '@mui/icons-material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { auth } from '../services/api';
import { generateFingerprint } from '../utils/fingerprint';

export default function Register() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const refCode = searchParams.get('ref') || '';
  const [form, setForm] = useState({ email: '', password: '', full_name: '' });
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
    setLoading(true);
    try {
      const res = await auth.register({
        ...form,
        ref: refCode,
        device_fingerprint: fingerprintRef.current,
      });
      localStorage.setItem('token', res.data.token);
      localStorage.setItem('user', JSON.stringify(res.data.user));
      toast.success('Account created! Please verify your email to continue.');
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
      <Card sx={{ width: '100%', maxWidth: 420 }}>
        <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
          <Typography variant="h4" fontWeight={700} mb={0.5} textAlign="center">
            Telegizer
          </Typography>
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
            <Button
              type="submit"
              fullWidth
              variant="contained"
              size="large"
              disabled={loading}
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

          <Typography variant="caption" textAlign="center" color="text.disabled" display="block">
            By creating an account you agree to our{' '}
            <Link component="button" onClick={() => navigate('/terms')} sx={{ color: 'text.secondary', cursor: 'pointer', fontSize: 'inherit' }}>
              Terms of Service
            </Link>
            {' '}and{' '}
            <Link component="button" onClick={() => navigate('/privacy')} sx={{ color: 'text.secondary', cursor: 'pointer', fontSize: 'inherit' }}>
              Privacy Policy
            </Link>
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
