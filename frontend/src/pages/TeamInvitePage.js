import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Typography, Button, Card, CardContent, CircularProgress, Alert, Chip,
} from '@mui/material';
import { Group, CheckCircle, Login } from '@mui/icons-material';
import { team as teamApi } from '../services/api';
import TelegizerLogo from '../components/TelegizerLogo';

const ROLE_LABELS = { owner: 'Owner', admin: 'Admin', member: 'Member' };

export default function TeamInvitePage() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState(false);

  const isLoggedIn = !!localStorage.getItem('token');

  useEffect(() => {
    teamApi.getInvite(token)
      .then(res => setInvite(res.data.invite))
      .catch(e => setError(e?.response?.data?.error || 'Invalid or expired invite link'))
      .finally(() => setLoading(false));
  }, [token]);

  const handleAccept = async () => {
    if (!isLoggedIn) {
      navigate(`/register?team_invite=${token}`);
      return;
    }
    setAccepting(true);
    try {
      await teamApi.acceptInvite(token);
      setAccepted(true);
    } catch (e) {
      setError(e?.response?.data?.error || 'Failed to accept invite');
    } finally {
      setAccepting(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        bgcolor: 'background.default',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        p: 3,
      }}
    >
      {/* Logo */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 4 }}>
        <TelegizerLogo size="sm" variant="icon" />
        <Typography fontWeight={800} fontSize="1.1rem" letterSpacing="-0.02em">
          Telegizer
        </Typography>
      </Box>

      <Card sx={{ maxWidth: 420, width: '100%' }}>
        <CardContent sx={{ p: 4, textAlign: 'center' }}>
          {loading ? (
            <CircularProgress />
          ) : error ? (
            <>
              <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>
              <Button variant="outlined" onClick={() => navigate('/')}>Go Home</Button>
            </>
          ) : accepted ? (
            <>
              <CheckCircle sx={{ fontSize: 52, color: 'success.main', mb: 2 }} />
              <Typography variant="h6" fontWeight={700} gutterBottom>
                You've joined {invite.team_name}!
              </Typography>
              <Typography variant="body2" color="text.secondary" mb={3}>
                You now have {ROLE_LABELS[invite.role] || invite.role} access to the team workspace.
              </Typography>
              <Button variant="contained" onClick={() => navigate('/dashboard')}>
                Open Dashboard
              </Button>
            </>
          ) : (
            <>
              <Box sx={{
                width: 56, height: 56, borderRadius: 3, mx: 'auto', mb: 2,
                bgcolor: 'rgba(61,142,248,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Group sx={{ fontSize: 26, color: 'primary.main' }} />
              </Box>

              <Typography variant="h6" fontWeight={700} gutterBottom>
                You're invited to join
              </Typography>
              <Typography variant="h5" fontWeight={800} color="primary.main" gutterBottom>
                {invite.team_name}
              </Typography>

              <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1, mb: 3 }}>
                <Chip label={`Role: ${ROLE_LABELS[invite.role] || invite.role}`} color="primary" size="small" />
              </Box>

              <Typography variant="body2" color="text.secondary" mb={3}>
                {isLoggedIn
                  ? 'Click below to accept the invite and join the team.'
                  : 'Create a free account (or log in) to accept this invite.'}
              </Typography>

              <Box sx={{ display: 'flex', gap: 1.5, justifyContent: 'center', flexWrap: 'wrap' }}>
                <Button
                  variant="contained"
                  startIcon={accepting ? <CircularProgress size={16} color="inherit" /> : (isLoggedIn ? <CheckCircle /> : <Login />)}
                  onClick={handleAccept}
                  disabled={accepting}
                >
                  {isLoggedIn ? 'Accept Invite' : 'Sign up to Accept'}
                </Button>
                {!isLoggedIn && (
                  <Button variant="outlined" onClick={() => navigate(`/login?team_invite=${token}`)}>
                    Log In
                  </Button>
                )}
              </Box>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
