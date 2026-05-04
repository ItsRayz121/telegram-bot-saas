import React, { useState } from 'react';
import {
  Box, AppBar, Toolbar, IconButton, Typography, Drawer,
  useMediaQuery, useTheme, Paper, BottomNavigation, BottomNavigationAction,
} from '@mui/material';
import { Menu as MenuIcon, Home, Groups, AutoMode, Psychology, AccountCircle } from '@mui/icons-material';
import Sidebar, { SIDEBAR_WIDTH } from '../components/Sidebar';
import { DesktopAssistantSidebar, MobileAssistantFab } from '../components/AssistantSidebar';
import TelegizerLogo from '../components/TelegizerLogo';
import { useNavigate, useLocation } from 'react-router-dom';

const BOTTOM_NAV_ITEMS = [
  { label: 'Home', icon: <Home />, path: '/dashboard' },
  { label: 'Groups', icon: <Groups />, path: '/groups' },
  { label: 'Automations', icon: <AutoMode />, path: '/workspace/automations' },
  { label: 'AI Hub', icon: <Psychology />, path: '/workspace' },
  { label: 'Account', icon: <AccountCircle />, path: '/settings' },
];

export default function AppLayout({ children }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // Map current path to the matching bottom nav index (or -1 for none)
  const bottomNavValue = BOTTOM_NAV_ITEMS.findIndex(
    (item) => pathname === item.path || pathname.startsWith(item.path + '/')
  );

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
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

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

        {/* Page content — add bottom padding on mobile so content isn't hidden behind nav bar */}
        <Box sx={{ flex: 1, overflow: 'auto', pb: isMobile ? '56px' : 0 }}>
          {children}
        </Box>

        {/* Mobile: floating assistant button */}
        {isMobile && <MobileAssistantFab />}

        {/* ── Mobile bottom navigation bar ── */}
        {isMobile && (
          <Paper
            elevation={3}
            sx={{
              position: 'fixed',
              bottom: 0,
              left: 0,
              right: 0,
              zIndex: theme.zIndex.appBar,
              borderTop: '1px solid',
              borderColor: 'divider',
              // Safe area support for notched phones
              pb: 'env(safe-area-inset-bottom)',
            }}
          >
            <BottomNavigation
              value={bottomNavValue === -1 ? false : bottomNavValue}
              onChange={(_, newValue) => navigate(BOTTOM_NAV_ITEMS[newValue].path)}
              showLabels
              sx={{ bgcolor: 'background.paper', height: 56 }}
            >
              {BOTTOM_NAV_ITEMS.map((item) => (
                <BottomNavigationAction
                  key={item.path}
                  label={item.label}
                  icon={item.icon}
                  sx={{
                    minWidth: 0,
                    fontSize: '0.65rem',
                    '& .MuiBottomNavigationAction-label': { fontSize: '0.65rem' },
                  }}
                />
              ))}
            </BottomNavigation>
          </Paper>
        )}
      </Box>

      {/* ── Desktop: persistent right assistant sidebar ── */}
      {!isMobile && <DesktopAssistantSidebar />}

    </Box>
  );
}
