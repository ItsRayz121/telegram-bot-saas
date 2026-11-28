import React, { useEffect, useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { Box, Card, CardActionArea, Typography, Chip, Stack, CircularProgress } from '@mui/material';
import { Telegram, Forum, CheckCircle, Cancel } from '@mui/icons-material';
import { PALETTE } from '../theme';
import guildizerApi from '../services/guildizerApi';

// Console chooser: clicking "Admin Panel" lands here and offers the Telegizer
// admin (existing, untouched) or the Guildizer admin (separate product). Each
// destination enforces its own access gate; this page just shows which you can
// reach and routes there.
function ConsoleCard({ icon: Icon, title, subtitle, gradient, access, onClick }) {
  return (
    <Card variant="outlined" sx={{ flex: 1, minWidth: 260, overflow: 'hidden' }}>
      <CardActionArea onClick={onClick} sx={{ p: 3, height: '100%' }}>
        <Box sx={{
          width: 56, height: 56, borderRadius: 2, mb: 2, display: 'grid', placeItems: 'center',
          background: gradient, color: '#fff',
        }}>
          <Icon sx={{ fontSize: 30 }} />
        </Box>
        <Typography variant="h6" fontWeight={600}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" mb={1.5}>{subtitle}</Typography>
        {access === null ? (
          <Chip size="small" label="Checking…" variant="outlined" />
        ) : access ? (
          <Chip size="small" icon={<CheckCircle sx={{ fontSize: 14 }} />} label="You have access" color="success" variant="outlined" />
        ) : (
          <Chip size="small" icon={<Cancel sx={{ fontSize: 14 }} />} label="No admin access" color="default" variant="outlined" />
        )}
      </CardActionArea>
    </Card>
  );
}

export default function AdminHub() {
  const navigate = useNavigate();
  const token = localStorage.getItem('token');
  const [tgAdmin, setTgAdmin] = useState(null);
  const [gzAdmin, setGzAdmin] = useState(null);

  useEffect(() => {
    // Telegizer admin status — also drives the Guildizer card: a Telegizer
    // super_admin reaches the Guildizer admin via the email bridge (no Discord
    // login), so super-admins see access on both.
    const base = process.env.REACT_APP_API_URL || '';
    let isSuper = false;
    fetch(`${base}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json())
      .then((d) => {
        setTgAdmin(!!d.user?.is_admin);
        isSuper = d.user?.admin_role === 'super_admin';
        if (isSuper) setGzAdmin(true); // bridged in — short-circuit the Discord check
      })
      .catch(() => setTgAdmin(false));
    // Guildizer admin via its own Discord session (covers Discord-only admins who
    // aren't Telegizer super-admins). Don't downgrade a super-admin who's already
    // been granted above.
    guildizerApi.get('/auth/me')
      .then(({ data }) => setGzAdmin((prev) => prev || !!data?.is_admin))
      .catch(() => setGzAdmin((prev) => (isSuper ? true : (prev ?? false))));
  }, [token]);

  if (!token) return <Navigate to="/login" replace />;

  return (
    <Box sx={{
      minHeight: '100vh', display: 'grid', placeItems: 'center', px: 2, bgcolor: PALETTE.bg0,
    }}>
      <Box sx={{ width: '100%', maxWidth: 760 }}>
        <Typography variant="h4" fontWeight={600} textAlign="center">Admin console</Typography>
        <Typography variant="body2" color="text.secondary" textAlign="center" mb={4}>
          Choose which product's admin panel you want to open.
        </Typography>
        {(tgAdmin === null && gzAdmin === null) && (
          <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>
        )}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <ConsoleCard
            icon={Telegram}
            title="Telegizer admin"
            subtitle="Telegram groups, bots, users & platform"
            gradient="#27282d"
            access={tgAdmin}
            onClick={() => navigate('/admin')}
          />
          <ConsoleCard
            icon={Forum}
            title="Guildizer admin"
            subtitle="Discord servers, custom bots & analytics"
            gradient="#5865f2"
            access={gzAdmin}
            onClick={() => navigate('/guildizer/admin')}
          />
        </Stack>
      </Box>
    </Box>
  );
}
