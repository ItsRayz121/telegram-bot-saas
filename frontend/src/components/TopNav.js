import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppBar, Toolbar, Box, Button, IconButton, Tooltip,
  Popover, List, ListItemButton, ListItemIcon, ListItemText, Typography, Divider,
} from '@mui/material';
import {
  Home, Dashboard, Groups, SmartToy, CreditCard, Settings,
  HelpOutline, Campaign, People, Email, OpenInNew, CardGiftcard,
  AdminPanelSettings, ChatBubbleOutline,
} from '@mui/icons-material';
import TelegizerLogo from './TelegizerLogo';
import UniversalSearchBar from './UniversalSearchBar';
import { PALETTE } from '../theme';
import { SUPPORT_LINKS as SUPPORT_HREFS, openSupportEmail } from '../config/support';

const SUPPORT_LINKS = [
  { label: 'Live Chat',        sub: 'Chat with our team now',  href: null,                    icon: ChatBubbleOutline, isChat: true  },
  { label: 'Official Channel', sub: 'Updates & announcements', href: SUPPORT_HREFS.channel,   icon: Campaign, isEmail: false },
  { label: 'Community Group',  sub: 'Help from other users',   href: SUPPORT_HREFS.community, icon: People,   isEmail: false },
  { label: 'Email Support',    sub: 'Click to contact us',     href: null,                    icon: Email,    isEmail: true  },
];

function SupportPopover() {
  const [anchor, setAnchor] = useState(null);
  return (
    <>
      <Tooltip title="Help & support" arrow>
        <IconButton
          size="small"
          onClick={e => setAnchor(e.currentTarget)}
          sx={{
            ml: 0.5, color: 'text.secondary',
            '&:hover': { color: 'text.primary', bgcolor: 'action.hover' },
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
        PaperProps={{
          sx: {
            width: 300, mt: 1,
          },
        }}
      >
        <Box sx={{ px: 2, pt: 1.5, pb: 1 }}>
          <Typography variant="caption" sx={{ fontSize: '0.75rem', fontWeight: 500, color: 'text.disabled' }}>
            Help and support
          </Typography>
        </Box>
        <Divider />
        <List dense disablePadding sx={{ py: 0.75 }}>
          {SUPPORT_LINKS.map(({ label, sub, href, icon: Icon, isEmail, isChat }) => {
            const isAction = isEmail || isChat;   // in-app action (not an external link)
            return (
            <ListItemButton
              key={label}
              {...(isChat
                ? {
                    onClick: () => { setAnchor(null); window.dispatchEvent(new Event('open-support-chat')); },
                  }
                : isEmail
                ? {
                    onClick: (e) => { e.preventDefault(); setAnchor(null); openSupportEmail(); },
                  }
                : {
                    component: 'a',
                    href,
                    target: '_blank',
                    rel: 'noopener noreferrer',
                    onClick: () => setAnchor(null),
                  }
              )}
              sx={{
                px: 1.5, py: 1, mx: 0.5, my: '2px', borderRadius: 1,
                cursor: 'pointer',
                '&:hover': { bgcolor: 'action.hover' },
              }}
            >
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Icon sx={{ fontSize: 18, color: 'text.secondary' }} />
              </ListItemIcon>
              <ListItemText
                primary={label}
                secondary={sub}
                primaryTypographyProps={{ fontSize: '0.875rem', fontWeight: 500, lineHeight: 1.3 }}
                secondaryTypographyProps={{ fontSize: '0.75rem', mt: 0.25 }}
              />
              {!isAction && (
                <OpenInNew sx={{ fontSize: 12, color: 'text.disabled', ml: 1, flexShrink: 0 }} />
              )}
            </ListItemButton>
            );
          })}
        </List>
        <Divider />
        <Box sx={{ px: 2, py: 1.25, textAlign: 'center' }}>
          <Typography variant="caption" color="text.disabled">
            Replies usually within 24 hours
          </Typography>
        </Box>
      </Popover>
    </>
  );
}

const NAV_ITEMS = [
  { label: 'Home',      path: '/',          icon: Home,      exact: true },
  { label: 'Dashboard', path: '/dashboard', icon: Dashboard  },
  { label: 'My Groups', path: '/groups',      icon: Groups     },
  { label: 'My Bots',   path: '/custom-bots', icon: SmartToy   },
  { label: 'Billing',   path: '/billing',   icon: CreditCard },
];

function _isAdmin() {
  try { return JSON.parse(localStorage.getItem('user') || '{}').is_admin === true; } catch { return false; }
}

export default function TopNav({ title, subtitle, actions, breadcrumb, hasSidebar = false, hideReferrals = false }) {
  const navigate  = useNavigate();
  const { pathname } = useLocation();
  const isAdmin = _isAdmin();

  const isActive = (path, exact) =>
    exact ? pathname === path : pathname === path || pathname.startsWith(path + '/');

  return (
    <AppBar position="sticky" elevation={0}>
      <Toolbar sx={{ gap: 1, rowGap: 0.5, flexWrap: 'wrap', minHeight: { xs: 56, sm: 56 }, py: { xs: 0.5, sm: 0 } }}>

        {/* Logo — hidden on mobile (AppLayout's mobile bar already shows it),
            so this row reads as a focused page action/context bar, not a
            second redundant header. */}
        <Box
          sx={{ display: { xs: 'none', md: 'flex' }, alignItems: 'center', cursor: 'pointer', mr: 1 }}
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
                    px: 1.5, py: 0.5, fontSize: '0.875rem', minWidth: 0,
                    color: active ? 'text.primary' : 'text.secondary',
                    fontWeight: active ? 500 : 400,
                    bgcolor: active ? PALETTE.bg3 : 'transparent',
                    borderRadius: 1,
                    '&:hover': { color: 'text.primary', bgcolor: 'action.hover' },
                  }}
                >
                  {label}
                </Button>
              );
            })}
          </Box>
        )}
        {/* Spacer only pushes actions right on desktop; on mobile it would grow
            and force the action button + help icon to wrap onto a second line. */}
        {hasSidebar && <Box sx={{ flex: 1, display: { xs: 'none', md: 'block' } }} />}

        {/* Universal search — shrinks (never grows) on mobile so the action button
            and trailing icons keep their space on the SAME row. */}
        {hasSidebar && (
          <UniversalSearchBar
            placeholder="Search…"
            sx={{ flexGrow: { xs: 1, md: 0 }, flexShrink: 1, width: { xs: 'auto', sm: 200, md: 260 }, minWidth: { xs: 72, sm: 160 }, mr: 1 }}
          />
        )}

        {/* Optional actions slot — never shrinks/wraps; search yields space to it */}
        {actions && (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexShrink: 0 }}>
            {actions}
          </Box>
        )}

        {/* Referrals — suppressed in contexts that opt out (e.g. Groups) to reduce header clutter */}
        {!hideReferrals && (
          <Tooltip title="Invite friends and earn free Pro time" arrow>
            <Button
              size="small"
              startIcon={<CardGiftcard sx={{ fontSize: '15px !important' }} />}
              onClick={() => navigate('/referrals')}
              aria-label="Referrals"
              variant="text"
              sx={{
                px: 1.5, fontSize: '0.875rem',
                color: pathname === '/referrals' ? 'text.primary' : 'text.secondary',
                bgcolor: pathname === '/referrals' ? PALETTE.bg3 : 'transparent',
                minWidth: 0, display: { xs: 'none', sm: 'flex' },
              }}
            >
              Referrals
            </Button>
          </Tooltip>
        )}

        <SupportPopover />

        {/* Admin panel shortcut — only visible to admins */}
        {isAdmin && (
          <Tooltip title="Admin panel" arrow>
            <IconButton
              size="small"
              onClick={() => navigate('/admin-hub')}
              sx={{
                ml: 0.5, color: pathname.startsWith('/admin') ? '#eb5257' : 'text.secondary',
                display: { xs: 'none', md: 'inline-flex' },
                '&:hover': { color: 'text.primary', bgcolor: 'action.hover' },
              }}
            >
              <AdminPanelSettings fontSize="small" />
            </IconButton>
          </Tooltip>
        )}

        {/* Settings shortcut */}
        <Tooltip title="Settings" arrow>
          <IconButton
            size="small"
            onClick={() => navigate('/settings')}
            sx={{
              ml: 0.5, color: pathname === '/settings' ? 'text.primary' : 'text.secondary',
              display: { xs: 'none', md: 'inline-flex' },
              '&:hover': { color: 'text.primary', bgcolor: 'action.hover' },
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
                <Box component="span" sx={{ fontSize: '0.8125rem', color: 'text.primary', fontWeight: 500 }}>
                  {crumb.label}
                </Box>
              )}
            </React.Fragment>
          ))}
          {subtitle && (
            <Typography component="span" sx={{ fontSize: '0.75rem', color: 'text.disabled', ml: 'auto' }}>{subtitle}</Typography>
          )}
        </Box>
      )}
    </AppBar>
  );
}
