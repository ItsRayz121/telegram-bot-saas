import React, { useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Typography, Button, CircularProgress, Chip, Stack,
} from '@mui/material';
import { CheckCircle, HourglassTop, SmartToy } from '@mui/icons-material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { billing, auth } from '../services/api';

export default function PaymentSuccess() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState('checking'); // checking | success | pending
  const [tier, setTier] = useState('');
  const [attempts, setAttempts] = useState(0);

  // Poll subscription until it upgrades (webhook may take a few seconds)
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { navigate('/login'); return; }

    const check = async () => {
      try {
        const res = await billing.getSubscription();
        const sub = res.data.subscription;
        if (sub.tier && sub.tier !== 'free') {
          // Refresh user in localStorage too
          try {
            const meRes = await auth.getMe();
            localStorage.setItem('user', JSON.stringify(meRes.data.user));
          } catch { /* ignore */ }
          setTier(sub.tier);
          setStatus('success');
          return true;
        }
      } catch { /* ignore */ }
      return false;
    };

    let interval;
    check().then((done) => {
      if (!done) {
        // Poll every 3 seconds up to 10 times (~30s total)
        let count = 0;
        interval = setInterval(async () => {
          count++;
          setAttempts(count);
          const done = await check();
          if (done || count >= 10) {
            clearInterval(interval);
            if (!done) setStatus('pending');
          }
        }, 3000);
      }
    });

    return () => clearInterval(interval);
  }, [navigate]);

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        p: 2,
      }}
    >
      <Card sx={{ maxWidth: 480, width: '100%' }}>
        <CardContent sx={{ p: 5, textAlign: 'center' }}>
          <SmartToy sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
          <Typography variant="h5" fontWeight={700} mb={1}>
            BotForge
          </Typography>

          {status === 'checking' && (
            <>
              <CircularProgress sx={{ my: 3 }} />
              <Typography color="text.secondary">
                Confirming your payment{attempts > 0 ? ` (${attempts}/10)` : ''}…
              </Typography>
              <Typography variant="caption" color="text.disabled" display="block" mt={1}>
                This usually takes a few seconds.
              </Typography>
            </>
          )}

          {status === 'success' && (
            <>
              <CheckCircle sx={{ fontSize: 64, color: 'success.main', my: 2 }} />
              <Typography variant="h5" fontWeight={700} mb={1}>
                Payment Confirmed!
              </Typography>
              <Chip
                label={`${tier.charAt(0).toUpperCase() + tier.slice(1)} Plan Active`}
                color="success"
                sx={{ mb: 2 }}
              />
              <Typography color="text.secondary" mb={4}>
                Your subscription is now active. You can start using all{' '}
                {tier} features right away.
              </Typography>
              <Stack spacing={2}>
                <Button
                  variant="contained"
                  size="large"
                  fullWidth
                  onClick={() => navigate('/dashboard')}
                >
                  Go to Dashboard
                </Button>
              </Stack>
            </>
          )}

          {status === 'pending' && (
            <>
              <HourglassTop sx={{ fontSize: 64, color: 'warning.main', my: 2 }} />
              <Typography variant="h5" fontWeight={700} mb={1}>
                Payment Processing
              </Typography>
              <Typography color="text.secondary" mb={1}>
                Your payment is being processed. Crypto confirmations can take
                a few minutes depending on network congestion.
              </Typography>
              <Typography variant="body2" color="text.secondary" mb={4}>
                Your plan will be upgraded automatically once the payment is
                confirmed. You'll see the updated tier in your dashboard.
              </Typography>
              <Stack spacing={2}>
                <Button variant="contained" fullWidth onClick={() => navigate('/dashboard')}>
                  Go to Dashboard
                </Button>
                <Button variant="outlined" fullWidth onClick={() => window.location.reload()}>
                  Check Again
                </Button>
              </Stack>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
