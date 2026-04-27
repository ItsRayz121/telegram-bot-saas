import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppBar, Toolbar, Box, Button, IconButton, Tooltip, Chip,
} from '@mui/material';
import {
  Home, Dashboard, Groups, SmartToy, CreditCard, Settings,
} from '@mui/icons-material';
import TelegizerLogo from './TelegizerLogo';

const NAV_ITEMS = [
  { label: 'Home',       path: '/',          icon: Home,      exact: true },
  { label: 'Dashboard',  path: '/dashboard', icon: Dashboard  },
  { label: 'My Groups',  path: '/my-groups', icon: Groups     },
  { label: 'My Bots',    path: '/my-bots',   icon: SmartToy   },
  { label: 'Billing',    path: '/billing',   icon: CreditCard },
];

export default function TopNav({ title, subtitle, actions, breadcrumb }) {
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

        {/* Nav links */}
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

        {/* Right side: optional actions */}
        {actions && (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            {actions}
          </Box>
        )}

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
