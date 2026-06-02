import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, CircularProgress, Typography, Button } from '@mui/material';
import { ErrorOutline } from '@mui/icons-material';
import { useTelegram } from '../contexts/TelegramContext';

function LoadingScreen() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 2 }}>
      <CircularProgress size={36} />
      <Typography color="text.secondary" variant="body2">Opening Telegizer…</Typography>
    </Box>
  );
}

function ErrorScreen({ message }) {
  return (
    <Box sx={{ p: 3, textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 2 }}>
      <ErrorOutline sx={{ fontSize: 56, color: 'error.main' }} />
      <Typography variant="h6" fontWeight={700}>Authentication failed</Typography>
      <Typography variant="body2" color="text.secondary">
        {message || 'Could not open Telegizer. Please close and reopen the app.'}
      </Typography>
      <Button variant="outlined" onClick={() => window.location.reload()}>Retry</Button>
    </Box>
  );
}

export default function MiniApp() {
  const { status, authError } = useTelegram();
  const navigate = useNavigate();

  useEffect(() => {
    if (status === 'ok') {
      navigate('/dashboard', { replace: true });
    }
    if (status === 'no_webapp') {
      // Opened outside Telegram — go to the normal website.
      window.location.replace('/');
    }
    if (status === 'no_init_data') {
      // initData missing but WebApp object exists (e.g. Telegram Desktop edge case).
      // If there's already a valid session from a prior TMA auth, use it.
      const token = localStorage.getItem('token');
      if (token) {
        navigate('/dashboard', { replace: true });
      }
    }
  }, [status, navigate]);

  if (status === 'error') return <ErrorScreen message={authError} />;
  if (status === 'no_init_data') {
    // No existing session to fall back to — show actionable error.
    const hasToken = !!localStorage.getItem('token');
    if (!hasToken) return <ErrorScreen message="Could not read Telegram session data. Please close and reopen the app." />;
    return <LoadingScreen />;
  }

  return <LoadingScreen />;
}
