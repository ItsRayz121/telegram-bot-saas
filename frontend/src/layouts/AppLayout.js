import React, { useState } from 'react';
import { Box, AppBar, Toolbar, IconButton, Typography, Drawer, useMediaQuery, useTheme } from '@mui/material';
import { Menu as MenuIcon } from '@mui/icons-material';
import Sidebar, { SIDEBAR_WIDTH } from '../components/Sidebar';
import TelegizerLogo from '../components/TelegizerLogo';
import { useNavigate } from 'react-router-dom';

export default function AppLayout({ children }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>

      {/* ── Desktop: persistent sidebar ── */}
      {!isMobile && (
        <Box sx={{ width: SIDEBAR_WIDTH, flexShrink: 0, position: 'sticky', top: 0, height: '100vh' }}>
          <Sidebar />
        </Box>
      )}

      {/* ── Mobile: drawer sidebar ── */}
      {isMobile && (
        <Drawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          ModalProps={{ keepMounted: true }}
          PaperProps={{ sx: { width: SIDEBAR_WIDTH, bgcolor: 'background.paper' } }}
        >
          <Sidebar onClose={() => setDrawerOpen(false)} />
        </Drawer>
      )}

      {/* ── Main area ── */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>

        {/* Mobile top bar */}
        {isMobile && (
          <AppBar
            position="sticky"
            elevation={0}
            sx={{ bgcolor: 'background.paper', borderBottom: '1px solid', borderColor: 'divider' }}
          >
            <Toolbar sx={{ gap: 1, minHeight: 52 }}>
              <IconButton edge="start" size="small" onClick={() => setDrawerOpen(true)}>
                <MenuIcon fontSize="small" />
              </IconButton>
              <Box
                sx={{ display: 'flex', alignItems: 'center', gap: 0.75, cursor: 'pointer' }}
                onClick={() => navigate('/dashboard')}
              >
                <TelegizerLogo size="sm" variant="icon" />
                <Typography fontWeight={700} fontSize="0.9rem">Telegizer</Typography>
              </Box>
            </Toolbar>
          </AppBar>
        )}

        {/* Page content */}
        <Box sx={{ flex: 1, overflow: 'auto' }}>
          {children}
        </Box>
      </Box>
    </Box>
  );
}
