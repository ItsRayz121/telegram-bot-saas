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
        <Typography variant="h6" fontWeight={800}>{title}</Typography>
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
    // Telegizer admin status.
    const base = process.env.REACT_APP_API_URL || '';
    fetch(`${base}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json()).then((d) => setTgAdmin(!!d.user?.is_admin)).catch(() => setTgAdmin(false));
    // Guildizer admin status (separate session cookie).
    guildizerApi.get('/auth/me').then(({ data }) => setGzAdmin(!!data?.is_admin)).catch(() => setGzAdmin(false));
  }, [token]);

  if (!token) return <Navigate to="/login" replace />;

  return (
    <Box sx={{
      minHeight: '100vh', display: 'grid', placeItems: 'center', px: 2, bgcolor: PALETTE.bg0,
      backgroundImage: `
        radial-gradient(ellipse 80% 50% at 50% -10%, rgba(157,108,247,0.08) 0%, transparent 60%),
        radial-gradient(ellipse 40% 30% at 90% 50%, rgba(61,142,248,0.05) 0%, transparent 55%)
      `,
    }}>
      <Box sx={{ width: '100%', maxWidth: 760 }}>
        <Typography variant="h4" fontWeight={800} textAlign="center">Admin Console</Typography>
        <Typography variant="body2" color="text.secondary" textAlign="center" mb={4}>
          Choose which product's admin panel you want to open.
        </Typography>
        {(tgAdmin === null && gzAdmin === null) && (
          <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>
        )}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <ConsoleCard
            icon={Telegram}
            title="Telegizer Admin"
            subtitle="Telegram groups, bots, users & platform"
            gradient="linear-gradient(135deg, #229ed9 0%, #3d8ef8 100%)"
            access={tgAdmin}
            onClick={() => navigate('/admin')}
          />
          <ConsoleCard
            icon={Forum}
            title="Guildizer Admin"
            subtitle="Discord servers, custom bots & analytics"
            gradient="linear-gradient(135deg, #5865f2 0%, #9d6cf7 100%)"
            access={gzAdmin}
            onClick={() => navigate('/guildizer/admin')}
          />
        </Stack>
      </Box>
    </Box>
  );
}
