import React, { useCallback, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box, List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  Typography, Avatar, Chip, Divider, Tooltip, IconButton,
} from '@mui/material';
import {
  ChevronLeft, ChevronRight, ArrowBack, SwapHoriz, Shield, SmartToy,
} from '@mui/icons-material';
import { PALETTE } from '../../theme';
import { GUILDIZER_ADMIN_CATEGORIES } from '../../config/guildizerAdminNav';
import { useGuildizerAdmin } from '../../contexts/GuildizerAdminContext';

export const SIDEBAR_WIDTH = 248;
export const SIDEBAR_COLLAPSED_WIDTH = 56;

const ROLE_LABELS = { super: 'Super Admin', support: 'Support' };
const ROLE_COLORS = { super: 'error', support: 'info' };

// Which section key is active, derived from the URL. Detail drill-downs map back
// to their parent section so the sidebar stays highlighted.
function activeKeyFromPath(pathname) {
  if (pathname.startsWith('/guildizer/admin/users/')) return 'users';
  if (pathname.startsWith('/guildizer/admin/servers/')) return 'servers';
  if (pathname.startsWith('/guildizer/admin/custom-bots/')) return 'bots';
  const m = pathname.match(/^\/guildizer\/admin\/[^/]+\/([^/]+)/);
  if (m) return m[1];
  return 'dashboard';
}

function NavItem({ label, icon: Icon, active, collapsed, onClick }) {
  const content = (
    <ListItemButton
      onClick={onClick}
      sx={{
        pl: collapsed ? 0 : 3.25, pr: 1.5, py: 0.6, mx: collapsed ? 0.5 : 0.75, mb: 0.2,
        borderRadius: 1.5, minHeight: 34,
        justifyContent: collapsed ? 'center' : 'flex-start',
        bgcolor: active ? 'rgba(61,142,248,0.14)' : 'transparent',
        color: active ? PALETTE.blueLt : 'text.secondary',
        boxShadow: active ? `inset 3px 0 0 ${PALETTE.blue}` : 'none',
        transition: 'all 0.18s ease',
        '&:hover': {
          bgcolor: active ? 'rgba(61,142,248,0.2)' : 'rgba(255,255,255,0.05)',
          color: active ? undefined : 'text.primary',
        },
      }}
    >
      {Icon && (
        <ListItemIcon sx={{ minWidth: collapsed ? 0 : 30, color: 'inherit', justifyContent: 'center' }}>
          <Icon sx={{ fontSize: 17 }} />
        </ListItemIcon>
      )}
      {!collapsed && (
        <ListItemText primary={label}
          primaryTypographyProps={{ fontSize: '0.82rem', fontWeight: active ? 600 : 400, noWrap: true }} />
      )}
    </ListItemButton>
  );
  return (
    <ListItem disablePadding sx={{ display: 'block' }}>
      {collapsed ? <Tooltip title={label} placement="right">{content}</Tooltip> : content}
    </ListItem>
  );
}

function CategoryLabel({ label }) {
  return (
    <Typography variant="caption" sx={{
      px: 2, pt: 1.5, pb: 0.25, display: 'block',
      textTransform: 'uppercase', letterSpacing: '0.08em',
      fontSize: '0.6rem', fontWeight: 700, color: PALETTE.text3,
    }}>
      {label}
    </Typography>
  );
}

export default function GuildizerAdminSidebar({ collapsed, onToggle, onClose }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { me, role, can } = useGuildizerAdmin();

  const activeKey = activeKeyFromPath(pathname);

  const go = useCallback((category, key) => {
    if (onClose) onClose();
    navigate(`/guildizer/admin/${category}/${key}`);
  }, [navigate, onClose]);

  // Categories with at least one permitted item.
  const visibleCategories = useMemo(() =>
    GUILDIZER_ADMIN_CATEGORIES
      .map((c) => ({ ...c, items: c.items.filter((i) => can(i.superOnly)) }))
      .filter((c) => c.items.length > 0),
  [can]);

  const shellSx = {
    width: '100%', height: '100vh', display: 'flex', flexDirection: 'column',
    bgcolor: PALETTE.bg1, borderRight: `1px solid ${PALETTE.border1}`,
    overflowY: 'auto', overflowX: 'hidden', flexShrink: 0,
    '&::-webkit-scrollbar': { width: 3 },
    '&::-webkit-scrollbar-thumb': { bgcolor: 'rgba(61,142,248,0.15)', borderRadius: 2 },
  };

  const name = me?.global_name || me?.username || 'Admin';

  // ── Collapsed: icons only ──
  if (collapsed) {
    return (
      <Box sx={{ ...shellSx, alignItems: 'center', pt: 1 }}>
        <Tooltip title="Expand" placement="right">
          <IconButton size="small" onClick={onToggle} sx={{ mb: 1, color: 'text.disabled' }}>
            <ChevronRight fontSize="small" />
          </IconButton>
        </Tooltip>
        <Divider sx={{ width: '100%', mb: 0.5, borderColor: PALETTE.border1 }} />
        <List dense disablePadding sx={{ width: '100%' }}>
          {visibleCategories.flatMap((c) => c.items).map((item) => (
            <NavItem key={item.key} label={item.label} icon={item.icon}
              active={activeKey === item.key} collapsed onClick={() => go(item.category, item.key)} />
          ))}
        </List>
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Back to servers" placement="right">
          <IconButton size="small" onClick={() => navigate('/guildizer')} sx={{ mb: 1, color: 'text.disabled' }}>
            <ArrowBack fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
    );
  }

  // ── Full view ──
  return (
    <Box sx={shellSx}>
      {/* Header */}
      <Box sx={{ px: 2, py: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1, cursor: 'pointer' }}
          onClick={() => navigate('/guildizer')}>
          <Box sx={{
            width: 30, height: 30, borderRadius: 1.5, display: 'grid', placeItems: 'center',
            background: 'linear-gradient(135deg, #5865f2 0%, #9d6cf7 100%)', color: '#fff',
          }}>
            <SmartToy sx={{ fontSize: 18 }} />
          </Box>
          <Box>
            <Typography fontWeight={800} fontSize="0.9rem" letterSpacing="-0.02em" color="text.primary" lineHeight={1.1}>
              Guildizer
            </Typography>
            <Typography fontSize="0.6rem" fontWeight={700} letterSpacing="0.1em" color={PALETTE.purpleLt} sx={{ textTransform: 'uppercase' }}>
              Admin Console
            </Typography>
          </Box>
        </Box>
        {onToggle && (
          <Tooltip title="Collapse" placement="right">
            <IconButton size="small" onClick={onToggle}
              sx={{ color: 'text.disabled', borderRadius: 1.5, '&:hover': { color: 'text.secondary', bgcolor: 'rgba(255,255,255,0.06)' } }}>
              <ChevronLeft sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* Profile / role */}
      <Box sx={{ px: 2, pb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1, borderRadius: 1.5, bgcolor: PALETTE.bg2, border: `1px solid ${PALETTE.border1}` }}>
          <Avatar src={me?.avatar_url || undefined} sx={{ width: 30, height: 30, bgcolor: PALETTE.purpleDk, fontSize: '0.8rem' }}>
            {name.charAt(0).toUpperCase()}
          </Avatar>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography fontSize="0.78rem" fontWeight={600} noWrap color="text.primary">{name}</Typography>
            <Typography fontSize="0.62rem" noWrap color="text.disabled">{me?.username ? '@' + me.username : me?.id}</Typography>
          </Box>
        </Box>
        {role && (
          <Box sx={{ display: 'flex', gap: 0.5, mt: 0.75 }}>
            <Chip size="small" icon={<Shield sx={{ fontSize: 12 }} />}
              label={(ROLE_LABELS[role] || 'Admin').toUpperCase()}
              color={ROLE_COLORS[role] || 'default'}
              sx={{ height: 18, fontSize: '0.58rem', fontWeight: 700 }} />
          </Box>
        )}
      </Box>

      <Divider sx={{ borderColor: PALETTE.border1 }} />

      {/* Categories */}
      <Box sx={{ flex: 1, py: 0.5 }}>
        {visibleCategories.map((cat) => (
          <Box key={cat.slug}>
            <CategoryLabel label={cat.label} />
            <List dense disablePadding>
              {cat.items.map((item) => (
                <NavItem key={item.key} label={item.label} icon={item.icon}
                  active={activeKey === item.key} onClick={() => go(item.category, item.key)} />
              ))}
            </List>
          </Box>
        ))}
      </Box>

      <Divider sx={{ borderColor: PALETTE.border1 }} />

      {/* Footer */}
      <List dense disablePadding sx={{ py: 0.5 }}>
        <NavItem label="Back to Servers" icon={ArrowBack} onClick={() => navigate('/guildizer')} />
        <NavItem label="Switch Console" icon={SwapHoriz} onClick={() => navigate('/admin-hub')} />
      </List>
    </Box>
  );
}
