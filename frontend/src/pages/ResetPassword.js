import React, { useState } from 'react';
import {
  Box, Card, CardContent, TextField, Button, Typography,
  Alert, CircularProgress, Link,
} from '@mui/material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { auth } from '../services/api';

export default function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [form, setForm] = useState({ new_password: '', confirm_password: '' });
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (form.new_password !== form.confirm_password) {
      setError('Passwords do not match.');
      return;
    }
    if (form.new_password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    setLoading(true);
    try {
      await auth.resetPassword({ token, new_password: form.new_password });
      setDone(true);
    } catch (err) {
      setError(err.response?.data?.error || 'Reset failed. The link may have expired.');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2 }}>
        <Alert severity="error">Invalid reset link. Please request a new one.</Alert>
      </Box>
    );
  }

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
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h5" fontWeight={700} mb={0.5} textAlign="center">
            New Password
          </Typography>
          <Typography variant="body2" color="text.secondary" textAlign="center" mb={3}>
            Choose a new password for your account
          </Typography>

          {done ? (
            <>
              <Alert severity="success" sx={{ mb: 2 }}>
                Password reset successfully!
              </Alert>
              <Button fullWidth variant="contained" onClick={() => navigate('/login')}>
                Sign In
              </Button>
            </>
          ) : (
            <>
              {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
              <form onSubmit={handleSubmit}>
                <TextField
                  fullWidth
                  label="New Password"
                  type="password"
                  value={form.new_password}
                  onChange={(e) => setForm({ ...form, new_password: e.target.value })}
                  required
                  sx={{ mb: 2 }}
                  autoComplete="new-password"
                />
                <TextField
                  fullWidth
                  label="Confirm Password"
                  type="password"
                  value={form.confirm_password}
                  onChange={(e) => setForm({ ...form, confirm_password: e.target.value })}
                  required
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
                  {loading ? <CircularProgress size={24} color="inherit" /> : 'Reset Password'}
                </Button>
              </form>
            </>
          )}

          <Typography variant="body2" textAlign="center" color="text.secondary">
            <Link
              component="button"
              onClick={() => navigate('/login')}
              sx={{ color: 'primary.main', cursor: 'pointer' }}
            >
              Back to Sign In
            </Link>
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
