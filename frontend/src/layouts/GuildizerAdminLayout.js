import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, AppBar, Toolbar, IconButton, Typography, Drawer, Chip,
  CircularProgress, Button, useMediaQuery, useTheme,
} from '@mui/material';
import { Menu as MenuIcon, Shield } from '@mui/icons-material';
import { useLocation, useNavigate } from 'react-router-dom';
import { PALETTE } from '../theme';
import guildizerApi from '../services/guildizerApi';
import GuildizerAdminSidebar, { SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH } from '../components/guildizer/GuildizerAdminSidebar';
import { GuildizerAdminContext } from '../contexts/GuildizerAdminContext';

const ROLE_LABELS = { super: 'Super Admin', support: 'Support' };
const ROLE_COLORS = { super: 'error', support: 'info' };

// Full-screen Guildizer admin shell. Replaces the normal app layout for every
// /guildizer/admin route, so the Guildizer admin console has its own dedicated
// navigation (mirrors the Telegizer AdminLayout, independent implementation).
// Gates on the Guildizer session: GET /auth/me -> is_admin.
export default function GuildizerAdminLayout({ children }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const isSmallDesktop = useMediaQuery(theme.breakpoints.down('lg'));
  const { pathname } = useLocation();
  const navigate = useNavigate();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('gz_admin_sidebar_collapsed') === 'true'; } catch { return false; }
  });
  const [status, setStatus] = useState('loading'); // loading | allowed | denied
  const [me, setMe] = useState(null);

  useEffect(() => {
    guildizerApi.get('/auth/me')
      .then(({ data }) => {
        if (data?.is_admin) { setMe(data); setStatus('allowed'); }
        else setStatus('denied');
      })
      .catch(() => setStatus('denied'));
  }, []);

  useEffect(() => { if (!isMobile && isSmallDesktop) setCollapsed(true); }, [isMobile, isSmallDesktop]);
  useEffect(() => { setDrawerOpen(false); }, [pathname]);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem('gz_admin_sidebar_collapsed', String(next)); } catch {}
  };

  const role = me?.admin_role || null;
  const can = useCallback((superOnly) => !superOnly || role === 'super', [role]);
  const ctx = useMemo(() => ({ me, role, can }), [me, role, can]);

  if (status === 'loading') {
    return (
      <Box sx={{ display: 'grid', placeItems: 'center', minHeight: '100vh', bgcolor: PALETTE.bg0 }}>
        <CircularProgress />
      </Box>
    );
  }
  if (status === 'denied') {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', gap: 2, px: 2, textAlign: 'center', bgcolor: PALETTE.bg0 }}>
        <Typography variant="h6" fontWeight={700}>Guildizer Admin Access Required</Typography>
        <Typography variant="body2" color="text.secondary">
          Your account does not have Guildizer admin privileges. Contact a platform administrator if you believe this is an error.
        </Typography>
        <Button variant="outlined" onClick={() => navigate('/guildizer')}>Back to Servers</Button>
      </Box>
    );
  }

  return (
    <GuildizerAdminContext.Provider value={ctx}>
      <Box sx={{
        display: 'flex', height: '100vh', overflow: 'hidden', bgcolor: PALETTE.bg0,
        backgroundImage: `
          radial-gradient(ellipse 80% 50% at 50% -10%, rgba(157,108,247,0.07) 0%, transparent 60%),
          radial-gradient(ellipse 40% 30% at 90% 50%, rgba(61,142,248,0.04) 0%, transparent 55%)
        `,
      }}>
        {!isMobile && (
          <Box sx={{
            width: collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH,
            flexShrink: 0, position: 'sticky', top: 0, height: '100vh', transition: 'width 0.2s ease',
          }}>
            <GuildizerAdminSidebar collapsed={collapsed} onToggle={toggle} />
          </Box>
        )}

        {isMobile && (
          <Drawer
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            ModalProps={{ keepMounted: true }}
            PaperProps={{ sx: { width: `min(${SIDEBAR_WIDTH}px, 86vw)`, maxWidth: '86vw', bgcolor: 'background.paper' } }}
          >
            <GuildizerAdminSidebar onClose={() => setDrawerOpen(false)} />
          </Drawer>
        )}

        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
          <AppBar position="sticky" elevation={0} sx={{ borderBottom: `1px solid ${PALETTE.border1}` }}>
            <Toolbar sx={{ gap: 1, minHeight: 52 }}>
              {isMobile && (
                <IconButton edge="start" size="small" onClick={() => setDrawerOpen(true)}
                  sx={{ color: 'text.secondary', '&:hover': { color: 'text.primary' } }}>
                  <MenuIcon fontSize="small" />
                </IconButton>
              )}
              <Box
                onClick={() => navigate('/guildizer/admin/overview/dashboard')}
                sx={{
                  display: 'flex', alignItems: 'center', gap: 1, flex: 1,
                  cursor: 'pointer', borderRadius: 1, px: 0.5, py: 0.25, ml: -0.5,
                  transition: 'background 0.15s ease',
                  '&:hover': { bgcolor: 'rgba(255,255,255,0.06)' },
                }}
                title="Back to Dashboard"
              >
                <Shield sx={{ fontSize: 18, color: PALETTE.purpleLt }} />
                <Typography fontWeight={700} fontSize="0.95rem">Guildizer Admin</Typography>
              </Box>
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
    </GuildizerAdminContext.Provider>
  );
}
