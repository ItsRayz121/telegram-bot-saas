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
import { PALETTE } from '../theme';

const SUPPORT_EMAIL = 'fazalelahi5577@gmail.com';
const SUPPORT_MAILTO = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('Telegizer Support Request')}&body=${encodeURIComponent('Hi Telegizer team,\n\nI need help with:\n\n[describe your issue]\n\n---\nAccount email: ')}`;

const SUPPORT_LINKS = [
  { label: 'Official Channel', sub: 'Updates & announcements',    href: 'https://t.me/telegizer',           icon: Campaign, external: true },
  { label: 'Community Group',  sub: 'Help from other users',      href: 'https://t.me/telegizer_community', icon: People,   external: true },
  { label: 'Email Support',    sub: 'Contact us by email',        href: SUPPORT_MAILTO,                     icon: Email,    external: true, isEmail: true },
];

function SupportPopover() {
  const [anchor, setAnchor] = useState(null);
  return (
    <>
      <Tooltip title="Help & Support" arrow>
        <IconButton
          size="small"
          onClick={e => setAnchor(e.currentTarget)}
          sx={{
            ml: 0.5, color: 'text.secondary',
            transition: 'color 0.15s, background 0.15s',
            '&:hover': { color: PALETTE.blue, bgcolor: `${PALETTE.blue}14` },
          }}
        >
          <HelpOutline fontSize="small" />
        </IconButton>
      </Tooltip>
      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        PaperProps={{ sx: { width: 270, mt: 1 } }}
      >
        <Box sx={{ px: 2, pt: 1.5, pb: 1 }}>
          <Typography
            variant="caption"
            sx={{
              textTransform: 'uppercase', letterSpacing: '0.1em',
              fontSize: '0.6rem', fontWeight: 700, color: 'text.disabled',
            }}
          >
            Help & Support
          </Typography>
        </Box>
        <Divider />
        <List dense disablePadding sx={{ pb: 0.5 }}>
          {SUPPORT_LINKS.map(({ label, sub, href, icon: Icon, external, isEmail }) => (
            <ListItemButton
              key={label}
              onClick={() => { setAnchor(null); window.open(href, '_blank', 'noopener,noreferrer'); }}
              sx={{
                px: 2, py: 1, mx: 0.5, my: 0.25, borderRadius: 1.5,
                transition: 'background 0.15s ease',
                '&:hover': { bgcolor: isEmail ? `${PALETTE.blue}12` : 'rgba(255,255,255,0.05)' },
              }}
            >
              <ListItemIcon sx={{ minWidth: 34 }}>
                <Icon
                  fontSize="small"
                  sx={{ color: isEmail ? PALETTE.blue : 'text.secondary' }}
                />
              </ListItemIcon>
              <ListItemText
                primary={label}
                secondary={sub}
                primaryTypographyProps={{ fontSize: '0.82rem', fontWeight: 600 }}
                secondaryTypographyProps={{ fontSize: '0.72rem' }}
              />
              {external && <OpenInNew sx={{ fontSize: 13, color: 'text.disabled', ml: 0.5, flexShrink: 0 }} />}
            </ListItemButton>
          ))}
        </List>
      </Popover>
    </>
  );
}

const NAV_ITEMS = [
  { label: 'Home',      path: '/',          icon: Home,      exact: true },
  { label: 'Dashboard', path: '/dashboard', icon: Dashboard  },
  { label: 'My Groups', path: '/my-groups', icon: Groups     },
  { label: 'My Bots',   path: '/my-bots',   icon: SmartToy   },
  { label: 'Billing',   path: '/billing',   icon: CreditCard },
];

export default function TopNav({ title, subtitle, actions, breadcrumb, hasSidebar = false }) {
  const navigate  = useNavigate();
  const { pathname } = useLocation();

  const isActive = (path, exact) =>
    exact ? pathname === path : pathname === path || pathname.startsWith(path + '/');

  return (
    <AppBar position="sticky" elevation={0}>
      <Toolbar sx={{ gap: 1, flexWrap: 'wrap', minHeight: { xs: 52, sm: 60 } }}>

        {/* Logo */}
        <Box
          sx={{ display: 'flex', alignItems: 'center', cursor: 'pointer', mr: 1 }}
          onClick={() => navigate('/dashboard')}
        >
          <TelegizerLogo size="sm" variant="icon" />
        </Box>

        {/* Nav links — hidden when sidebar handles navigation */}
        {!hasSidebar && (
          <Box sx={{ display: 'flex', gap: 0.5, flex: 1, flexWrap: 'wrap' }}>
            {NAV_ITEMS.map(({ label, path, icon: Icon, exact }) => {
              const active = isActive(path, exact);
              return (
                <Button
                  key={path}
                  size="small"
                  startIcon={<Icon sx={{ fontSize: '15px !important' }} />}
                  onClick={() => navigate(path)}
                  sx={{
                    px: 1.5, py: 0.5, fontSize: '0.8rem', minWidth: 0,
                    color: active ? PALETTE.blue : 'text.secondary',
                    fontWeight: active ? 600 : 400,
                    bgcolor: active ? `${PALETTE.blue}14` : 'transparent',
                    borderRadius: 1.5,
                    transition: 'all 0.15s ease',
                    '&:hover': { color: 'text.primary', bgcolor: 'rgba(255,255,255,0.06)' },
                  }}
                >
                  {label}
                </Button>
              );
            })}
          </Box>
        )}
        {hasSidebar && <Box sx={{ flex: 1 }} />}

        {/* Universal search */}
        {hasSidebar && (
          <UniversalSearchBar
            placeholder="Search…"
            sx={{ width: { xs: 120, sm: 200, md: 260 }, mr: 1, flexShrink: 1 }}
          />
        )}

        {/* Optional actions slot */}
        {actions && (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            {actions}
          </Box>
        )}

        {/* Referrals */}
        <Tooltip title="Invite Friends — Earn Free Pro" arrow>
          <Button
            size="small"
            startIcon={<CardGiftcard sx={{ fontSize: '15px !important' }} />}
            onClick={() => navigate('/referrals')}
            variant={pathname === '/referrals' ? 'contained' : 'outlined'}
            color="primary"
            sx={{
              px: 1.5, py: 0.4, fontSize: '0.78rem', borderRadius: 1.5,
              minWidth: 0, display: { xs: 'none', sm: 'flex' },
              transition: 'all 0.18s ease',
            }}
          >
            Referrals
          </Button>
        </Tooltip>

        <SupportPopover />

        {/* Settings shortcut */}
        <Tooltip title="Settings" arrow>
          <IconButton
            size="small"
            onClick={() => navigate('/settings')}
            sx={{
              ml: 0.5, color: pathname === '/settings' ? PALETTE.blue : 'text.secondary',
              transition: 'color 0.15s, background 0.15s',
              '&:hover': { color: PALETTE.blue, bgcolor: `${PALETTE.blue}14` },
            }}
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
            borderTop: `1px solid ${PALETTE.border1}`,
          }}
        >
          {breadcrumb && breadcrumb.map((crumb, idx) => (
            <React.Fragment key={idx}>
              {idx > 0 && (
                <Box component="span" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>/</Box>
              )}
              {crumb.path ? (
                <Button
                  size="small" variant="text"
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
