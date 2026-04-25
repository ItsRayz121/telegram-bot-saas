import React, { useState, useEffect } from 'react';
import { Box, Card, CardContent, Typography, Button, CircularProgress, Alert } from '@mui/material';
import { CheckCircle, ErrorOutline, Email, MarkEmailRead } from '@mui/icons-material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { auth } from '../services/api';

const SpamTip = () => (
  <Alert severity="info" sx={{ mt: 2, textAlign: 'left', fontSize: '0.8rem' }}>
    Don't see the email? Check your <strong>spam or junk folder</strong> and mark it as "Not Spam".
  </Alert>
);

export default function VerifyEmail() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [status, setStatus] = useState('verifying'); // verifying | success | error | no_token
  const [message, setMessage] = useState('');
  const [resending, setResending] = useState(false);
  const [resendDone, setResendDone] = useState(false);
  const [resendError, setResendError] = useState('');

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
    setResendError('');
    try {
      await auth.resendVerification();
      setResendDone(true);
    } catch (err) {
      const msg = err.response?.data?.error || 'Could not send the email. Please try again later.';
      setResendError(msg);
    } finally {
      setResending(false);
    }
  };

  const ResendButton = () => (
    <Button
      variant="outlined"
      startIcon={resending ? <CircularProgress size={16} /> : <MarkEmailRead />}
      disabled={resending}
      onClick={handleResend}
      sx={{ mr: 1 }}
    >
      {resending ? 'Sending…' : 'Resend Verification Email'}
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
      <Card sx={{ maxWidth: 460, width: '100%' }}>
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

              {resendDone ? (
                <>
                  <Alert severity="success" sx={{ mb: 1, textAlign: 'left' }}>
                    Verification email sent! Check your inbox.
                  </Alert>
                  <SpamTip />
                </>
              ) : (
                <>
                  {resendError && (
                    <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }}>{resendError}</Alert>
                  )}
                  <ResendButton />
                </>
              )}
              <Box mt={2}>
                <Button variant="text" onClick={() => navigate('/dashboard')}>Back to Dashboard</Button>
              </Box>
            </>
          )}

          {status === 'no_token' && (
            <>
              <Email sx={{ fontSize: 56, color: 'primary.main', mb: 2 }} />
              <Typography variant="h5" fontWeight={700} mb={1}>Check Your Email</Typography>
              <Typography variant="body2" color="text.secondary" mb={2}>
                We sent a verification link to your email address. Click the link to verify your account.
              </Typography>

              {resendDone ? (
                <>
                  <Alert severity="success" sx={{ mb: 1, textAlign: 'left' }}>
                    Verification email sent! Check your inbox.
                  </Alert>
                  <SpamTip />
                </>
              ) : (
                <>
                  {resendError && (
                    <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }}>{resendError}</Alert>
                  )}
                  <Button
                    variant="contained"
                    startIcon={resending ? <CircularProgress size={16} color="inherit" /> : <MarkEmailRead />}
                    disabled={resending}
                    onClick={handleResend}
                  >
                    {resending ? 'Sending…' : 'Resend Verification Email'}
                  </Button>
                  <SpamTip />
                </>
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
