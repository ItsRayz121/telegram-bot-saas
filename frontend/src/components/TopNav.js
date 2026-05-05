import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppBar, Toolbar, Box, Button, IconButton, Tooltip, Chip,
  Popover, List, ListItemButton, ListItemIcon, ListItemText, Typography, Divider,
} from '@mui/material';
import {
  Home, Dashboard, Groups, SmartToy, CreditCard, Settings,
  HelpOutline, Campaign, People, Email, OpenInNew, CardGiftcard,
} from '@mui/icons-material';
import TelegizerLogo from './TelegizerLogo';
import UniversalSearchBar from './UniversalSearchBar';

const SUPPORT_LINKS = [
  { label: 'Official Channel',  sub: 'Updates & announcements', href: 'https://t.me/telegizer',           icon: Campaign, external: true },
  { label: 'Community Group',   sub: 'Help from other users',   href: 'https://t.me/telegizer_community', icon: People,   external: true },
  { label: 'Email Support',     sub: 'Contact the team',        href: 'mailto:fazalelahi5577@gmail.com',  icon: Email,    external: false },
];

function SupportPopover() {
  const [anchor, setAnchor] = useState(null);
  return (
    <>
      <Tooltip title="Help & Support">
        <IconButton size="small" onClick={e => setAnchor(e.currentTarget)} sx={{ ml: 0.5 }}>
          <HelpOutline fontSize="small" />
        </IconButton>
      </Tooltip>
      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        PaperProps={{ sx: { width: 260, mt: 0.5, border: '1px solid', borderColor: 'divider' } }}
      >
        <Box sx={{ px: 2, pt: 1.5, pb: 1 }}>
          <Typography variant="caption" fontWeight={700} color="text.disabled" sx={{ textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: '0.65rem' }}>
            Help & Support
          </Typography>
        </Box>
        <Divider />
        <List dense disablePadding>
          {SUPPORT_LINKS.map(({ label, sub, href, icon: Icon, external }) => (
            <ListItemButton
              key={label}
              component="a"
              href={href}
              target={external ? '_blank' : '_self'}
              rel="noopener noreferrer"
              onClick={() => setAnchor(null)}
              sx={{ px: 2, py: 1 }}
            >
              <ListItemIcon sx={{ minWidth: 34 }}>
                <Icon fontSize="small" sx={{ color: 'text.secondary' }} />
              </ListItemIcon>
              <ListItemText
                primary={label}
                secondary={sub}
                primaryTypographyProps={{ fontSize: '0.82rem', fontWeight: 600 }}
                secondaryTypographyProps={{ fontSize: '0.72rem' }}
              />
              {external && <OpenInNew sx={{ fontSize: 13, color: 'text.disabled', ml: 0.5 }} />}
            </ListItemButton>
          ))}
        </List>
      </Popover>
    </>
  );
}

const NAV_ITEMS = [
  { label: 'Home',       path: '/',          icon: Home,      exact: true },
  { label: 'Dashboard',  path: '/dashboard', icon: Dashboard  },
  { label: 'My Groups',  path: '/my-groups', icon: Groups     },
  { label: 'My Bots',    path: '/my-bots',   icon: SmartToy   },
  { label: 'Billing',    path: '/billing',   icon: CreditCard },
];

// hasSidebar: pass true when this TopNav renders inside AppLayout so the
// global nav links are hidden (the sidebar already provides navigation).
export default function TopNav({ title, subtitle, actions, breadcrumb, hasSidebar = false }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const isActive = (path, exact) =>
    exact ? pathname === path : pathname === path || pathname.startsWith(path + '/');

  return (
    <AppBar
      position="sticky"
      elevation={0}
      sx={{ borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}
    >
      <Toolbar sx={{ gap: 1, flexWrap: 'wrap', minHeight: { xs: 56, sm: 64 } }}>
        {/* Logo */}
        <Box
          sx={{ display: 'flex', alignItems: 'center', cursor: 'pointer', mr: 1 }}
          onClick={() => navigate('/dashboard')}
        >
          <TelegizerLogo size="sm" variant="icon" />
        </Box>

        {/* Nav links — hidden when sidebar is present (sidebar handles navigation) */}
        {!hasSidebar && (
          <Box sx={{ display: 'flex', gap: 0.5, flex: 1, flexWrap: 'wrap' }}>
            {NAV_ITEMS.map(({ label, path, icon: Icon, exact }) => (
              <Button
                key={path}
                size="small"
                startIcon={<Icon sx={{ fontSize: '16px !important' }} />}
                onClick={() => navigate(path)}
                color={isActive(path, exact) ? 'primary' : 'inherit'}
                variant={isActive(path, exact) ? 'contained' : 'text'}
                sx={{
                  px: 1.5,
                  py: 0.5,
                  fontSize: '0.8rem',
                  minWidth: 0,
                  opacity: isActive(path, exact) ? 1 : 0.75,
                  '&:hover': { opacity: 1 },
                }}
              >
                {label}
              </Button>
            ))}
          </Box>
        )}
        {hasSidebar && <Box sx={{ flex: 1 }} />}

        {/* Universal search — visible in sidebar layouts */}
        {hasSidebar && (
          <UniversalSearchBar
            placeholder="Search meetings, notes, reminders…"
            sx={{ width: { xs: 160, sm: 260 }, mr: 1 }}
          />
        )}

        {/* Right side: optional actions */}
        {actions && (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            {actions}
          </Box>
        )}

        {/* Referrals button */}
        <Tooltip title="Invite Friends — Earn Free Pro">
          <Button
            size="small"
            startIcon={<CardGiftcard sx={{ fontSize: '15px !important' }} />}
            onClick={() => navigate('/referrals')}
            variant={pathname === '/referrals' ? 'contained' : 'outlined'}
            color="primary"
            sx={{ px: 1.5, py: 0.4, fontSize: '0.78rem', borderRadius: 1.5, minWidth: 0, display: { xs: 'none', sm: 'flex' } }}
          >
            Referrals
          </Button>
        </Tooltip>

        {/* Support popover */}
        <SupportPopover />

        {/* Settings icon shortcut */}
        <Tooltip title="Settings">
          <IconButton
            size="small"
            onClick={() => navigate('/settings')}
            color={pathname === '/settings' ? 'primary' : 'default'}
            sx={{ ml: 0.5 }}
          >
            <Settings fontSize="small" />
          </IconButton>
        </Tooltip>
      </Toolbar>

      {/* Breadcrumb / subtitle row */}
      {(title || breadcrumb) && (
        <Box
          sx={{
            px: 2, pb: 1,
            display: 'flex', alignItems: 'center', gap: 1,
            borderTop: '1px solid', borderColor: 'divider',
          }}
        >
          {breadcrumb && breadcrumb.map((crumb, idx) => (
            <React.Fragment key={idx}>
              {idx > 0 && (
                <Box component="span" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>/</Box>
              )}
              {crumb.path ? (
                <Button
                  size="small"
                  variant="text"
                  onClick={() => navigate(crumb.path)}
                  sx={{ p: 0, minWidth: 0, fontSize: '0.75rem', color: 'text.secondary' }}
                >
                  {crumb.label}
                </Button>
              ) : (
                <Box component="span" sx={{ fontSize: '0.75rem', color: 'text.primary', fontWeight: 600 }}>
                  {crumb.label}
                </Box>
              )}
            </React.Fragment>
          ))}
          {subtitle && (
            <Chip label={subtitle} size="small" sx={{ height: 18, fontSize: '0.65rem', ml: 'auto' }} />
          )}
        </Box>
      )}
    </AppBar>
  );
}
