import React, { useState } from 'react';
import {
  Box, Card, CardContent, TextField, Button, Typography,
  Alert, CircularProgress, Link,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { auth } from '../services/api';

export default function Login() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await auth.login(form);
      localStorage.setItem('token', res.data.token);
      localStorage.setItem('user', JSON.stringify(res.data.user));
      toast.success('Welcome back!');
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.error || 'Login failed. Please try again.');
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
        <CardContent sx={{ p: 4 }}>
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
              type="password"
              value={form.password}
              onChange={handleChange}
              required
              sx={{ mb: 3 }}
              autoComplete="current-password"
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
          <Typography variant="body2" textAlign="center" color="text.secondary">
            Don't have an account?{' '}
            <Link
              component="button"
              onClick={() => navigate('/register')}
              sx={{ color: 'primary.main', cursor: 'pointer' }}
            >
              Sign up
            </Link>
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
