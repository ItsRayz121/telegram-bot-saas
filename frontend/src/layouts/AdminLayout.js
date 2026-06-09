import React, { useState, useEffect } from 'react';
import {
  Box, AppBar, Toolbar, IconButton, Typography, Drawer, Chip,
  useMediaQuery, useTheme,
} from '@mui/material';
import { Menu as MenuIcon, Shield } from '@mui/icons-material';
import { useLocation } from 'react-router-dom';
import { PALETTE } from '../theme';
import { auth as authApi } from '../services/api';
import AdminSidebar, { SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH } from '../components/AdminSidebar';

const ROLE_LABELS = {
  super_admin: 'Super Admin', admin: 'Admin', support: 'Support',
  finance: 'Finance', moderator: 'Moderator', analyst: 'Analyst',
};
const ROLE_COLORS = {
  super_admin: 'error', admin: 'warning', support: 'info',
  finance: 'success', moderator: 'secondary', analyst: 'default',
};

// Full-screen admin shell. Replaces the normal user AppLayout (with its
// Dashboard/Groups/Echo/Referrals/Settings sidebar) for every /admin route, so
// the admin console has its own dedicated navigation. Authorized restructure —
// scoped to /admin/* only.
export default function AdminLayout({ children }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const isSmallDesktop = useMediaQuery(theme.breakpoints.down('lg'));
  const { pathname } = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('admin_sidebar_collapsed') === 'true'; } catch { return false; }
  });
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('user') || 'null'); } catch { return null; }
  });

  useEffect(() => {
    authApi.getMe().then(r => {
      setUser(r.data.user);
      localStorage.setItem('user', JSON.stringify(r.data.user));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!isMobile && isSmallDesktop) setCollapsed(true);
  }, [isMobile, isSmallDesktop]);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => { setDrawerOpen(false); }, [pathname]);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem('admin_sidebar_collapsed', String(next)); } catch {}
  };

  const role = user?.admin_role;

  return (
    <Box
      sx={{
        display: 'flex', height: '100vh', overflow: 'hidden', bgcolor: PALETTE.bg0,
        backgroundImage: `
          radial-gradient(ellipse 80% 50% at 50% -10%, rgba(157,108,247,0.07) 0%, transparent 60%),
          radial-gradient(ellipse 40% 30% at 90% 50%, rgba(61,142,248,0.04) 0%, transparent 55%)
        `,
      }}
    >
      {/* Desktop: persistent admin sidebar */}
      {!isMobile && (
        <Box sx={{
          width: collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH,
          flexShrink: 0, position: 'sticky', top: 0, height: '100vh', transition: 'width 0.2s ease',
        }}>
          <AdminSidebar collapsed={collapsed} onToggle={toggle} user={user} />
        </Box>
      )}

      {/* Mobile: drawer */}
      {isMobile && (
        <Drawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          ModalProps={{ keepMounted: true }}
          PaperProps={{ sx: { width: `min(${SIDEBAR_WIDTH}px, 86vw)`, maxWidth: '86vw', bgcolor: 'background.paper' } }}
        >
          <AdminSidebar onClose={() => setDrawerOpen(false)} user={user} />
        </Drawer>
      )}

      {/* Main area */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        <AppBar position="sticky" elevation={0} sx={{ borderBottom: `1px solid ${PALETTE.border1}` }}>
          <Toolbar sx={{ gap: 1, minHeight: 52 }}>
            {isMobile && (
              <IconButton edge="start" size="small" onClick={() => setDrawerOpen(true)}
                sx={{ color: 'text.secondary', '&:hover': { color: 'text.primary' } }}>
                <MenuIcon fontSize="small" />
              </IconButton>
            )}
            <Shield sx={{ fontSize: 18, color: PALETTE.purpleLt }} />
            <Typography fontWeight={700} fontSize="0.95rem" flex={1}>Admin Console</Typography>
            {role && (
              <Chip label={(ROLE_LABELS[role] || 'Admin').toUpperCase()} size="small"
                color={ROLE_COLORS[role] || 'default'} sx={{ fontWeight: 700, fontSize: '0.62rem' }} />
            )}
          </Toolbar>
        </AppBar>

        <Box sx={{ flex: 1, overflow: 'auto' }} className="page-enter">
          {children}
        </Box>
      </Box>
    </Box>
  );
}
