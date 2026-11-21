import React, { useState } from 'react';
import useAssistantName from '../hooks/useAssistantName';
import {
  Box, AppBar, Toolbar, IconButton, Typography, Drawer,
  useMediaQuery, useTheme, Paper, BottomNavigation, BottomNavigationAction, Alert,
} from '@mui/material';
import { PALETTE } from '../theme';
import { Menu as MenuIcon, Home, Groups, Psychology, AccountCircle, SmartToy } from '@mui/icons-material';
import { getPublicPlatformConfig } from '../services/api';
import Sidebar, { SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH } from '../components/Sidebar';
// Telegizer Assistant panel hidden per user request — keep import handy for re-enable.
// import { DesktopAssistantSidebar, MobileAssistantFab } from '../components/AssistantSidebar';
import TelegizerLogo from '../components/TelegizerLogo';
import NotificationBell from '../components/NotificationBell';
import AnnouncementBanner from '../components/AnnouncementBanner';
import ChatWidget from '../components/ChatWidget';
import { notifications as notificationsApi } from '../services/api';
import { useNavigate, useLocation } from 'react-router-dom';
import { clickableProps } from '../utils/a11y';

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

  // Maintenance banner — surfaced from public platform config (refreshed on mount).
  const [maintenance, setMaintenance] = useState(null);
  React.useEffect(() => {
    let alive = true;
    getPublicPlatformConfig()
      .then(r => {
        const s = r.data?.settings || {};
        if (alive && s.maintenance_mode) setMaintenance(s.maintenance_message || 'Maintenance in progress.');
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  // Echo's co-pilot is hidden inside the Groups context (group management),
  // where an AI assistant panel reads as unrelated clutter. It remains global
  // everywhere else. Covers: the official groups list + per-group settings/
  // analytics (/groups, /groups/*) and custom-bot group management
  // (/bot/:id/group/*) — but NOT the bot settings page itself (/bot/:id).
  // Assistant panel hidden globally per user request, so this guard is unused
  // for now — kept commented alongside the renders below for easy re-enable.
  // const isGroupsContext =
  //   pathname === '/groups' ||
  //   pathname.startsWith('/groups/') ||
  //   /^\/bot\/[^/]+\/group\//.test(pathname);

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
    {/* Keyboard users jump past the sidebar straight to the page content. */}
    <Box
      component="a"
      href="#main-content"
      onClick={(e) => {
        e.preventDefault();
        const el = document.getElementById('main-content');
        if (el) { el.focus(); el.scrollIntoView(); }
      }}
      sx={{
        position: 'fixed', top: 8, left: 8, zIndex: 2000, px: 2, py: 1,
        borderRadius: 1, bgcolor: 'primary.main', color: '#fff', fontWeight: 600, fontSize: '0.85rem',
        textDecoration: 'none', transform: 'translateY(-200%)',
        '&:focus': { transform: 'translateY(0)' },
      }}
    >
      Skip to main content
    </Box>
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
              <IconButton aria-label="Open menu"
                edge="start" size="small"
                onClick={() => setDrawerOpen(true)}
                sx={{ color: 'text.secondary', '&:hover': { color: 'text.primary' } }}
              >
                <MenuIcon fontSize="small" />
              </IconButton>
              <Box
                sx={{ display: 'flex', alignItems: 'center', gap: 0.75, cursor: 'pointer', borderRadius: 1 }}
                {...clickableProps(() => navigate('/dashboard'), { 'aria-label': 'Telegizer dashboard' })}
              >
                <TelegizerLogo size="sm" variant="icon" />
                <Typography fontWeight={800} fontSize="0.9rem" letterSpacing="-0.02em">Telegizer</Typography>
              </Box>
              <Box sx={{ flexGrow: 1 }} />
              <NotificationBell size="small" sx={{ color: 'text.secondary' }} />
            </Toolbar>
          </AppBar>
        )}

        {/* Page content */}
        <Box
          component="main"
          id="main-content"
          tabIndex={-1}
          sx={{
            flex: 1, overflow: 'auto', outline: 'none',
            pb: isMobile ? 'var(--bottom-nav-clearance)' : 0,
          }}
          className="page-enter"
        >
          {maintenance && (
            <Alert severity="warning" sx={{ borderRadius: 0 }}>{maintenance}</Alert>
          )}
          <AnnouncementBanner api={notificationsApi} />
          {children}
        </Box>

        {/* Mobile: floating assistant button — hidden per user request */}
        {/* {isMobile && !isGroupsContext && <MobileAssistantFab />} */}

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
              component="nav"
              aria-label="Primary"
              value={bottomNavValue === -1 ? false : bottomNavValue}
              onChange={(_, newValue) => navigate(BOTTOM_NAV_ITEMS[newValue].path)}
              showLabels
              sx={{ height: 56 }}
            >
              {BOTTOM_NAV_ITEMS.map((item, idx) => (
                <BottomNavigationAction
                  key={item.path}
                  aria-current={bottomNavValue === idx ? 'page' : undefined}
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

      {/* ── Desktop: persistent right assistant sidebar — hidden per user request ── */}
      {/* {!isMobile && !isGroupsContext && <DesktopAssistantSidebar />} */}

    </Box>

    {/* Global floating live-chat launcher (self-hides on /admin + for guests) */}
    <ChatWidget />
    </>
  );
}

