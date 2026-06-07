import React, { useState } from 'react';
import useAssistantName from '../hooks/useAssistantName';
import {
  Box, AppBar, Toolbar, IconButton, Typography, Drawer,
  useMediaQuery, useTheme, Paper, BottomNavigation, BottomNavigationAction,
} from '@mui/material';
import { PALETTE } from '../theme';
import { Menu as MenuIcon, Home, Groups, Psychology, AccountCircle, SmartToy } from '@mui/icons-material';
import Sidebar, { SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH } from '../components/Sidebar';
import { DesktopAssistantSidebar, MobileAssistantFab } from '../components/AssistantSidebar';
import TelegizerLogo from '../components/TelegizerLogo';
import { useNavigate, useLocation } from 'react-router-dom';

export default function AppLayout({ children }) {
  const assistantName = useAssistantName();
  const BOTTOM_NAV_ITEMS = [
    { label: 'Home',         icon: <Home />,         path: '/dashboard' },
    { label: 'Groups',       icon: <Groups />,        path: '/groups' },
    { label: 'My Bots',      icon: <SmartToy />,      path: '/custom-bots' },
    { label: assistantName,  icon: <Psychology />,    path: '/ark' },
    { label: 'Account',      icon: <AccountCircle />, path: '/settings' },
  ];
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const isSmallDesktop = useMediaQuery(theme.breakpoints.down('lg'));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return localStorage.getItem('sidebar_collapsed') === 'true'; } catch { return false; }
  });
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // Auto-collapse on small desktop screens (md-lg range)
  React.useEffect(() => {
    if (!isMobile && isSmallDesktop) setSidebarCollapsed(true);
  }, [isMobile, isSmallDesktop]);

  const toggleSidebar = () => {
    const next = !sidebarCollapsed;
    setSidebarCollapsed(next);
    try { localStorage.setItem('sidebar_collapsed', String(next)); } catch {}
  };

  // Map current path to the matching bottom nav index (or -1 for none)
  const bottomNavValue = BOTTOM_NAV_ITEMS.findIndex(
    (item) => pathname === item.path || pathname.startsWith(item.path + '/')
  );

  return (
    <>
    <Box
      sx={{
        display: 'flex', height: '100vh', overflow: 'hidden',
        bgcolor: PALETTE.bg0,
        /* Subtle ambient radial — gives depth without being distracting */
        backgroundImage: `
          radial-gradient(ellipse 80% 50% at 50% -10%, rgba(61,142,248,0.07) 0%, transparent 60%),
          radial-gradient(ellipse 40% 30% at 90% 50%, rgba(157,108,247,0.04) 0%, transparent 55%)
        `,
      }}
    >

      {/* ── Desktop: persistent sidebar ── */}
      {!isMobile && (
        <Box
          sx={{
            width: sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH,
            flexShrink: 0,
            position: 'sticky',
            top: 0,
            height: '100vh',
            transition: 'width 0.2s ease',
          }}
        >
          <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />
        </Box>
      )}

      {/* ── Mobile: drawer sidebar ── */}
      {isMobile && (
        <Drawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          ModalProps={{ keepMounted: true }}
          PaperProps={{ sx: { width: `min(${SIDEBAR_WIDTH}px, 86vw)`, maxWidth: '86vw', bgcolor: 'background.paper' } }}
        >
          <Sidebar onClose={() => setDrawerOpen(false)} />
        </Drawer>
      )}

      {/* ── Main area ── */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

        {/* Mobile top bar */}
        {isMobile && (
          <AppBar position="sticky" elevation={0}>
            <Toolbar sx={{ gap: 1, minHeight: 52 }}>
              <IconButton
                edge="start" size="small"
                onClick={() => setDrawerOpen(true)}
                sx={{ color: 'text.secondary', '&:hover': { color: 'text.primary' } }}
              >
                <MenuIcon fontSize="small" />
              </IconButton>
              <Box
                sx={{ display: 'flex', alignItems: 'center', gap: 0.75, cursor: 'pointer' }}
                onClick={() => navigate('/dashboard')}
              >
                <TelegizerLogo size="sm" variant="icon" />
                <Typography fontWeight={800} fontSize="0.9rem" letterSpacing="-0.02em">Telegizer</Typography>
              </Box>
            </Toolbar>
          </AppBar>
        )}

        {/* Page content */}
        <Box
          sx={{
            flex: 1, overflow: 'auto',
            pb: isMobile ? 'var(--bottom-nav-clearance)' : 0,
          }}
          className="page-enter"
        >
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
              sx={{ height: 56 }}
            >
              {BOTTOM_NAV_ITEMS.map((item) => (
                <BottomNavigationAction
                  key={item.path}
                  label={item.label}
                  icon={item.icon}
                  sx={{
                    minWidth: 0,
                    px: 0.5,
                    '& .MuiBottomNavigationAction-label': {
                      fontSize: '0.68rem',
                      lineHeight: 1.1,
                      maxWidth: '100%',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      // Keep the label visible even when not selected (5 items on
                      // a narrow screen) instead of MUI hiding unselected labels.
                      '&.Mui-selected': { fontSize: '0.7rem' },
                    },
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
    </>
  );
}

