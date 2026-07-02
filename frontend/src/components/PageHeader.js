import React from 'react';
import { AppBar, Toolbar, Box, Typography, Button } from '@mui/material';
import { ArrowBack, SpaceDashboard } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import TelegizerLogo from './TelegizerLogo';

/**
 * Permanent header for public info / legal pages.
 * Always offers three ways out: Back, the Telegizer logo (-> home), and
 * Dashboard (-> /dashboard when signed in, otherwise /login).
 */
export default function PageHeader() {
  const navigate = useNavigate();
  const loggedIn = typeof window !== 'undefined' && !!localStorage.getItem('token');

  const goBack = () => {
    if (typeof window !== 'undefined' && window.history.length > 1) navigate(-1);
    else navigate('/');
  };

  return (
    <AppBar
      position="sticky"
      elevation={0}
      sx={{ borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.default' }}
    >
      <Toolbar sx={{ gap: 1 }}>
        <Button
          size="small"
          startIcon={<ArrowBack />}
          onClick={goBack}
          sx={{ color: 'text.secondary', minWidth: 0 }}
        >
          <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>Back</Box>
        </Button>

        <Box
          onClick={() => navigate('/')}
          sx={{ display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer', flexGrow: 1, justifyContent: 'center' }}
        >
          <TelegizerLogo size="sm" variant="icon" />
          <Typography variant="h6" fontWeight={700} sx={{ display: { xs: 'none', sm: 'block' } }}>
            Telegizer
          </Typography>
        </Box>

        <Button
          size="small"
          variant="contained"
          startIcon={<SpaceDashboard sx={{ fontSize: 18 }} />}
          onClick={() => navigate(loggedIn ? '/dashboard' : '/login')}
          sx={{ minWidth: 0 }}
        >
          <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>Dashboard</Box>
        </Button>
      </Toolbar>
    </AppBar>
  );
}
