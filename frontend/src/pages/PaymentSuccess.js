import React, { useEffect, useState, useRef } from 'react';
import {
  Box, Card, CardContent, Typography, Button, CircularProgress,
  Chip, Stack, LinearProgress,
} from '@mui/material';
import { CheckCircle, HourglassTop, ErrorOutline, SmartToy } from '@mui/icons-material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { billing, auth } from '../services/api';

const MAX_ATTEMPTS = 15;   // 15 × 4s = 60s total poll window
const POLL_INTERVAL = 4000;

export default function PaymentSuccess() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState('checking'); // checking | success | pending | failed
  const [tier, setTier] = useState('');
  const [attempts, setAttempts] = useState(0);
  const intervalRef = useRef(null);

  // URL param ?status=failed (e.g. if coming from a cancel/error redirect)
  const urlStatus = searchParams.get('status');

  useEffect(() => {
    if (urlStatus === 'failed' || urlStatus === 'cancelled') {
      setStatus('failed');
      return;
    }

    const token = localStorage.getItem('token');
    if (!token) { navigate('/login'); return; }

    const check = async () => {
      try {
        const res = await billing.getSubscription();
        const sub = res.data.subscription;
        if (sub.tier && sub.tier !== 'free') {
          // Refresh user cache
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

    // First check immediately
    check().then((done) => {
      if (done) return;
      let count = 0;
      intervalRef.current = setInterval(async () => {
        count++;
        setAttempts(count);
        const confirmed = await check();
        if (confirmed || count >= MAX_ATTEMPTS) {
          clearInterval(intervalRef.current);
          if (!confirmed) setStatus('pending');
        }
      }, POLL_INTERVAL);
    });

    return () => clearInterval(intervalRef.current);
  }, [navigate, urlStatus]);

  // Auto-redirect to dashboard 4 seconds after success
  useEffect(() => {
    if (status !== 'success') return;
    const t = setTimeout(() => navigate('/dashboard'), 4000);
    return () => clearTimeout(t);
  }, [status, navigate]);

  const progressPct = Math.min(100, (attempts / MAX_ATTEMPTS) * 100);

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
        <CardContent sx={{ p: { xs: 3, sm: 5 }, textAlign: 'center' }}>
          {/* Brand */}
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, mb: 3 }}>
            <SmartToy sx={{ color: 'primary.main' }} />
            <Typography variant="h6" fontWeight={700}>BotForge</Typography>
          </Box>

          {/* ── Checking ── */}
          {status === 'checking' && (
            <>
              <CircularProgress size={56} sx={{ mb: 3 }} />
              <Typography variant="h6" fontWeight={700} mb={1}>
                Confirming your payment
              </Typography>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Waiting for blockchain confirmation. This usually takes 1–3 minutes.
              </Typography>
              {attempts > 0 && (
                <>
                  <LinearProgress
                    variant="determinate"
                    value={progressPct}
                    sx={{ borderRadius: 2, mb: 1 }}
                  />
                  <Typography variant="caption" color="text.disabled">
                    Check {attempts} of {MAX_ATTEMPTS} · refreshing automatically
                  </Typography>
                </>
              )}
            </>
          )}

          {/* ── Success ── */}
          {status === 'success' && (
            <>
              <CheckCircle sx={{ fontSize: 72, color: 'success.main', mb: 2 }} />
              <Typography variant="h5" fontWeight={800} mb={1}>
                Payment Confirmed!
              </Typography>
              <Chip
                label={`${tier.charAt(0).toUpperCase() + tier.slice(1)} Plan Active`}
                color="success"
                sx={{ mb: 2, fontWeight: 700 }}
              />
              <Typography color="text.secondary" mb={4}>
                Your subscription is now active. All {tier} features are unlocked.
                Taking you to your dashboard…
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

          {/* ── Pending ── */}
          {status === 'pending' && (
            <>
              <HourglassTop sx={{ fontSize: 72, color: 'warning.main', mb: 2 }} />
              <Typography variant="h5" fontWeight={800} mb={1}>
                Waiting for Confirmation
              </Typography>
              <Typography color="text.secondary" mb={1}>
                Your payment is being processed on-chain. Depending on network congestion,
                crypto confirmations can take up to 10–30 minutes.
              </Typography>
              <Typography variant="body2" color="text.secondary" mb={4}>
                Your plan will upgrade automatically once confirmed — you don't need to do
                anything. Check your dashboard in a few minutes.
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

          {/* ── Failed / Cancelled ── */}
          {status === 'failed' && (
            <>
              <ErrorOutline sx={{ fontSize: 72, color: 'error.main', mb: 2 }} />
              <Typography variant="h5" fontWeight={800} mb={1}>
                Payment Not Completed
              </Typography>
              <Typography color="text.secondary" mb={4}>
                The payment was cancelled or could not be processed. No charge was made.
                You can try again from the pricing page.
              </Typography>
              <Stack spacing={2}>
                <Button variant="contained" fullWidth onClick={() => navigate('/pricing')}>
                  Try Again
                </Button>
                <Button variant="outlined" fullWidth onClick={() => navigate('/dashboard')}>
                  Back to Dashboard
                </Button>
              </Stack>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
