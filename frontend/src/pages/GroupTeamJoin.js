import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Typography, Button, Card, CardContent, CircularProgress, Alert, Chip } from '@mui/material';
import { Group, CheckCircle, Login } from '@mui/icons-material';
import { groupTeam } from '../services/api';
import TelegizerLogo from '../components/TelegizerLogo';

const ROLE_TEXT = {
  manager: 'manage this group (settings, moderation and tools)',
  viewer: 'view this group (read-only)',
};

export default function GroupTeamJoin() {
  const { code } = useParams();
  const navigate = useNavigate();
  const isLoggedIn = !!localStorage.getItem('token');
  const [invite, setInvite] = useState(null);
  const [loading, setLoading] = useState(isLoggedIn);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!isLoggedIn) return;
    groupTeam.preview(code)
      .then((r) => setInvite(r.data.invite))
      .catch((e) => setError(e?.response?.data?.error || 'Invalid or expired invite link'))
      .finally(() => setLoading(false));
  }, [code, isLoggedIn]);

  const accept = async () => {
    setBusy(true);
    try { await groupTeam.redeem(code); setDone(true); }
    catch (e) { setError(e?.response?.data?.error || 'Could not accept this invite'); }
    setBusy(false);
  };

  const goLogin = () => {
    try { sessionStorage.setItem('post_login_redirect', `/group-team/join/${code}`); } catch { /* ignore */ }
    navigate(`/login?next=${encodeURIComponent(`/group-team/join/${code}`)}`);
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', p: 3 }}>
      <Box sx={{ mb: 4 }}><TelegizerLogo size="sm" variant="icon" /></Box>
      <Card sx={{ maxWidth: 440, width: '100%' }}>
        <CardContent sx={{ textAlign: 'center', p: 4 }}>
          {loading ? <CircularProgress /> : done ? (
            <>
              <CheckCircle color="success" sx={{ fontSize: 48, mb: 1 }} />
              <Typography variant="h6" gutterBottom>You're in</Typography>
              <Button variant="contained" onClick={() => navigate('/groups')}>Go to My Groups</Button>
            </>
          ) : !isLoggedIn ? (
            <>
              <Group sx={{ fontSize: 48, mb: 1 }} color="primary" />
              <Typography variant="h6" gutterBottom>You've been invited to a Telegram group</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Log in or create an account to accept.
              </Typography>
              <Button variant="contained" startIcon={<Login />} onClick={goLogin}>Log in to accept</Button>
            </>
          ) : error && !invite ? (
            <Alert severity="error">{error}</Alert>
          ) : (
            <>
              <Group sx={{ fontSize: 48, mb: 1 }} color="primary" />
              <Typography variant="h6" gutterBottom>{invite.group_title}</Typography>
              <Chip label={invite.role} size="small" sx={{ mb: 1 }} />
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                You'll be able to {ROLE_TEXT[invite.role] || 'access this group'}. Your other
                groups and account stay separate.
              </Typography>
              {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
              <Button variant="contained" disabled={busy} onClick={accept}>Accept invite</Button>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
