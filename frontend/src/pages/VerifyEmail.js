import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Card, CardContent, Typography, Button, CircularProgress,
  Alert, Divider,
} from '@mui/material';
import { CheckCircle, ErrorOutline, Email, MarkEmailRead, Logout } from '@mui/icons-material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { auth } from '../services/api';

const SpamTip = () => (
  <Alert severity="info" sx={{ mt: 2, textAlign: 'left', fontSize: '0.8rem' }}>
    Don't see the email? Check your <strong>spam or junk folder</strong> and mark it
    as "Not Spam" so future emails reach you.
  </Alert>
);

function LogoutButton() {
  const navigate = useNavigate();
  const handleLogout = () => {
    auth.logout().catch(() => {});
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };
  return (
    <Button
      variant="text"
      color="inherit"
      size="small"
      startIcon={<Logout fontSize="small" />}
      onClick={handleLogout}
      sx={{ color: 'text.disabled', mt: 1 }}
    >
      Sign out
    </Button>
  );
}

export default function VerifyEmail() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const isLoggedIn = Boolean(localStorage.getItem('token'));

  const [status, setStatus] = useState('verifying'); // verifying | success | error | no_token
  const [message, setMessage] = useState('');
  const [resending, setResending] = useState(false);
  const [resendDone, setResendDone] = useState(false);
  const [resendError, setResendError] = useState('');
  // Cooldown countdown (seconds remaining)
  const [cooldownSecs, setCooldownSecs] = useState(0);

  useEffect(() => {
    if (!token) {
      setStatus('no_token');
      return;
    }
    auth.verifyEmail({ token })
      .then(() => {
        // Stamp email_verified in localStorage so VerifiedRoute unblocks immediately
        try {
          const u = JSON.parse(localStorage.getItem('user') || '{}');
          u.email_verified = true;
          localStorage.setItem('user', JSON.stringify(u));
        } catch {}
        setStatus('success');
      })
      .catch((err) => {
        setMessage(err.response?.data?.error || 'Verification failed. The link may have expired.');
        setStatus('error');
      });
  }, [token]);

  // Countdown timer for resend cooldown
  useEffect(() => {
    if (cooldownSecs <= 0) return;
    const t = setTimeout(() => setCooldownSecs((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldownSecs]);

  const handleResend = useCallback(async () => {
    setResending(true);
    setResendError('');
    try {
      await auth.resendVerification();
      setResendDone(true);
    } catch (err) {
      const code = err.response?.data?.code;
      const msg = err.response?.data?.error || 'Could not send the email. Please try again later.';
      if (code === 'RESEND_COOLDOWN') {
        setCooldownSecs(60); // conservative — show 60s countdown
      }
      setResendError(msg);
    } finally {
      setResending(false);
    }
  }, []);

  const ResendButton = ({ variant = 'outlined', fullWidth = false }) => (
    <Button
      variant={variant}
      fullWidth={fullWidth}
      startIcon={resending ? <CircularProgress size={16} /> : <MarkEmailRead />}
      disabled={resending || cooldownSecs > 0}
      onClick={handleResend}
    >
      {resending
        ? 'Sending…'
        : cooldownSecs > 0
          ? `Resend in ${cooldownSecs}s`
          : 'Resend Verification Email'}
    </Button>
  );

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
        <CardContent sx={{ p: { xs: 3, sm: 4 }, textAlign: 'center' }}>

          {/* ── Verifying ───────────────────────────────────────────────────── */}
          {status === 'verifying' && (
            <>
              <CircularProgress sx={{ mb: 2 }} />
              <Typography variant="h6" fontWeight={600}>Verifying your email…</Typography>
            </>
          )}

          {/* ── Success ─────────────────────────────────────────────────────── */}
          {status === 'success' && (
            <>
              <CheckCircle sx={{ fontSize: 56, color: 'success.main', mb: 2 }} />
              <Typography variant="h5" fontWeight={700} mb={1}>Email Verified!</Typography>
              <Typography variant="body2" color="text.secondary" mb={3}>
                Your email address is confirmed. You now have full access to Telegizer.
              </Typography>
              <Button variant="contained" size="large" fullWidth onClick={() => navigate('/dashboard')}>
                Go to Dashboard
              </Button>
            </>
          )}

          {/* ── Token error ─────────────────────────────────────────────────── */}
          {status === 'error' && (
            <>
              <ErrorOutline sx={{ fontSize: 56, color: 'error.main', mb: 2 }} />
              <Typography variant="h5" fontWeight={700} mb={1}>Verification Failed</Typography>
              <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }}>{message}</Alert>

              {resendDone ? (
                <>
                  <Alert severity="success" sx={{ mb: 1, textAlign: 'left' }}>
                    New verification email sent!
                  </Alert>
                  <SpamTip />
                </>
              ) : (
                <>
                  {resendError && (
                    <Alert severity="warning" sx={{ mb: 2, textAlign: 'left' }}>{resendError}</Alert>
                  )}
                  {isLoggedIn && <ResendButton />}
                </>
              )}

              <Box mt={2} sx={{ display: 'flex', justifyContent: 'center', gap: 1, flexWrap: 'wrap' }}>
                {isLoggedIn && <LogoutButton />}
              </Box>
            </>
          )}

          {/* ── No token (just arrived, or blocked route) ────────────────────── */}
          {status === 'no_token' && (
            <>
              <Email sx={{ fontSize: 56, color: 'primary.main', mb: 2 }} />
              <Typography variant="h5" fontWeight={700} mb={1}>Verify Your Email</Typography>
              <Typography variant="body2" color="text.secondary" mb={1}>
                A verification link was sent to your email address when you signed up.
                Click it to unlock full access to Telegizer.
              </Typography>

              {resendDone ? (
                <>
                  <Alert severity="success" sx={{ mb: 1, textAlign: 'left' }}>
                    Verification email sent!
                  </Alert>
                  <SpamTip />
                </>
              ) : (
                <>
                  <SpamTip />
                  {resendError && (
                    <Alert severity="warning" sx={{ mt: 2, mb: 1, textAlign: 'left' }}>{resendError}</Alert>
                  )}
                  {isLoggedIn && (
                    <Box mt={2}>
                      <ResendButton variant="contained" fullWidth />
                    </Box>
                  )}
                </>
              )}

              {isLoggedIn && (
                <>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="caption" color="text.disabled">
                    Wrong account?
                  </Typography>
                  <Box>
                    <LogoutButton />
                  </Box>
                </>
              )}
            </>
          )}

        </CardContent>
      </Card>
    </Box>
  );
}
