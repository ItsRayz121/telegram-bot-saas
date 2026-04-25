import React, { useState, useEffect } from 'react';
import { Box, Card, CardContent, Typography, Button, CircularProgress, Alert } from '@mui/material';
import { CheckCircle, ErrorOutline, Email } from '@mui/icons-material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { auth } from '../services/api';

export default function VerifyEmail() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [status, setStatus] = useState('verifying'); // verifying | success | error | no_token
  const [message, setMessage] = useState('');
  const [resending, setResending] = useState(false);
  const [resendDone, setResendDone] = useState(false);

  useEffect(() => {
    if (!token) {
      setStatus('no_token');
      return;
    }
    auth.verifyEmail({ token })
      .then(() => setStatus('success'))
      .catch((err) => {
        setMessage(err.response?.data?.error || 'Verification failed. The link may have expired.');
        setStatus('error');
      });
  }, [token]);

  const handleResend = async () => {
    setResending(true);
    try {
      await auth.resendVerification();
      setResendDone(true);
    } catch (err) {
      setMessage(err.response?.data?.error || 'Could not resend. Please try again later.');
    } finally {
      setResending(false);
    }
  };

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
      <Card sx={{ maxWidth: 440, width: '100%' }}>
        <CardContent sx={{ p: { xs: 3, sm: 4 }, textAlign: 'center' }}>

          {status === 'verifying' && (
            <>
              <CircularProgress sx={{ mb: 2 }} />
              <Typography variant="h6" fontWeight={600}>Verifying your email…</Typography>
            </>
          )}

          {status === 'success' && (
            <>
              <CheckCircle sx={{ fontSize: 56, color: 'success.main', mb: 2 }} />
              <Typography variant="h5" fontWeight={700} mb={1}>Email Verified!</Typography>
              <Typography variant="body2" color="text.secondary" mb={3}>
                Your email address has been confirmed. You now have full access to BotForge.
              </Typography>
              <Button variant="contained" size="large" onClick={() => navigate('/dashboard')}>
                Go to Dashboard
              </Button>
            </>
          )}

          {status === 'error' && (
            <>
              <ErrorOutline sx={{ fontSize: 56, color: 'error.main', mb: 2 }} />
              <Typography variant="h5" fontWeight={700} mb={1}>Verification Failed</Typography>
              <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }}>{message}</Alert>
              {!resendDone ? (
                <Button
                  variant="outlined"
                  startIcon={resending ? <CircularProgress size={16} /> : <Email />}
                  disabled={resending}
                  onClick={handleResend}
                  sx={{ mr: 1 }}
                >
                  Resend Verification Email
                </Button>
              ) : (
                <Alert severity="success" sx={{ mb: 2 }}>Verification email sent! Check your inbox.</Alert>
              )}
              <Button variant="text" onClick={() => navigate('/dashboard')}>Back to Dashboard</Button>
            </>
          )}

          {status === 'no_token' && (
            <>
              <Email sx={{ fontSize: 56, color: 'primary.main', mb: 2 }} />
              <Typography variant="h5" fontWeight={700} mb={1}>Check Your Email</Typography>
              <Typography variant="body2" color="text.secondary" mb={3}>
                We sent a verification link to your email address. Click the link in the email to verify your account.
              </Typography>
              {!resendDone ? (
                <Button
                  variant="contained"
                  startIcon={resending ? <CircularProgress size={16} color="inherit" /> : <Email />}
                  disabled={resending}
                  onClick={handleResend}
                >
                  Resend Verification Email
                </Button>
              ) : (
                <Alert severity="success">Verification email sent! Check your inbox.</Alert>
              )}
              <Box mt={2}>
                <Button variant="text" onClick={() => navigate('/dashboard')}>Back to Dashboard</Button>
              </Box>
            </>
          )}

        </CardContent>
      </Card>
    </Box>
  );
}
