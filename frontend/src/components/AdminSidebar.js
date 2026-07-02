import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box, List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  Typography, Avatar, Chip, Divider, Tooltip, IconButton, Badge,
} from '@mui/material';
import {
  ChevronLeft, ChevronRight, ArrowBack, Logout, Shield,
} from '@mui/icons-material';
import TelegizerLogo from './TelegizerLogo';
import { auth as authApi, admin as adminApi } from '../services/api';
import { PALETTE } from '../theme';
import { ADMIN_CATEGORIES } from '../config/adminNav';

const SIDEBAR_WIDTH = 248;
const SIDEBAR_COLLAPSED_WIDTH = 56;

const ROLE_LABELS = {
  super_admin: 'Super Admin', admin: 'Admin', support: 'Support',
  finance: 'Finance', moderator: 'Moderator', analyst: 'Analyst',
};
const ROLE_COLORS = {
  super_admin: 'error', admin: 'warning', support: 'info',
  finance: 'success', moderator: 'secondary', analyst: 'default',
};

// Which section key is active, derived from the URL. Detail drill-downs map back
// to their parent section so the sidebar stays highlighted.
function activeKeyFromPath(pathname) {
  if (pathname.startsWith('/admin/users/')) return 'users';
  if (pathname.startsWith('/admin/groups/')) return 'groups';
  if (pathname.startsWith('/admin/custom-bots/')) return 'bots';
  const m = pathname.match(/^\/admin\/[^/]+\/([^/]+)/);
  if (m) return m[1];
  return 'dashboard';
}

function NavItem({ label, icon: Icon, active, collapsed, onClick, badge = 0 }) {
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
          <Badge color="error" variant="dot" invisible={!collapsed || badge <= 0}>
            <Icon sx={{ fontSize: 17 }} />
          </Badge>
        </ListItemIcon>
      )}
      {!collapsed && (
        <ListItemText
          primary={label}
          primaryTypographyProps={{ fontSize: '0.82rem', fontWeight: active ? 600 : 400, noWrap: true }}
        />
      )}
      {!collapsed && badge > 0 && (
        <Box sx={{
          ml: 'auto', minWidth: 18, height: 18, px: 0.5, borderRadius: 9,
          bgcolor: '#ef4444', color: '#fff', fontSize: '0.62rem', fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          {badge > 99 ? '99+' : badge}
        </Box>
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
    <Typography
      variant="caption"
      sx={{
        px: 2, pt: 1.5, pb: 0.25, display: 'block',
        textTransform: 'uppercase', letterSpacing: '0.08em',
        fontSize: '0.6rem', fontWeight: 700, color: PALETTE.text3,
      }}
    >
      {label}
    </Typography>
  );
}

export default function AdminSidebar({ collapsed, onToggle, onClose, user: userProp }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [user, setUser] = useState(userProp || null);

  useEffect(() => {
    if (userProp) { setUser(userProp); return; }
    const stored = localStorage.getItem('user');
    if (stored) { try { setUser(JSON.parse(stored)); } catch {} }
    authApi.getMe().then(r => {
      setUser(r.data.user);
      localStorage.setItem('user', JSON.stringify(r.data.user));
    }).catch(() => {});
  }, [userProp]);

  const perms = useMemo(() => user?.admin_permissions || [], [user]);
  const can = useCallback((p) => !p || perms.includes(p), [perms]);
  const activeKey = activeKeyFromPath(pathname);

  // Live-chat unread count → badge on the "Live Chat" nav item.
  const [supportUnread, setSupportUnread] = useState(0);
  const canSupport = can('support.manage');
  useEffect(() => {
    if (!canSupport) return undefined;
    let alive = true;
    const load = () => adminApi.supportUnreadCount()
      .then((r) => { if (alive) setSupportUnread(r.data?.unread || 0); })
      .catch(() => {});
    load();
    const id = setInterval(load, 20000);
    return () => { alive = false; clearInterval(id); };
  }, [canSupport]);

  const go = useCallback((category, key) => {
    if (onClose) onClose();
    navigate(`/admin/${category}/${key}`);
  }, [navigate, onClose]);

  const handleLogout = () => {
    authApi.logout?.().catch(() => {});
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const plan = user?.subscription_tier || 'free';
  const planLabel = plan === 'enterprise' ? 'Enterprise' : plan === 'pro' ? 'Pro' : 'Free';
  const role = user?.admin_role;

  // Categories with at least one permitted item.
  const visibleCategories = useMemo(() =>
    ADMIN_CATEGORIES
      .map(c => ({ ...c, items: c.items.filter(i => can(i.permission)) }))
      .filter(c => c.items.length > 0),
  [can]);

  const shellSx = {
    width: '100%', height: '100vh', display: 'flex', flexDirection: 'column',
    bgcolor: PALETTE.bg1, borderRight: `1px solid ${PALETTE.border1}`,
    overflowY: 'auto', overflowX: 'hidden', flexShrink: 0,
    '&::-webkit-scrollbar': { width: 3 },
    '&::-webkit-scrollbar-thumb': { bgcolor: 'rgba(61,142,248,0.15)', borderRadius: 2 },
  };

  // ── Collapsed: icons only, flat list ──
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
          {visibleCategories.flatMap(c => c.items).map(item => (
            <NavItem
              key={item.key} label={item.label} icon={item.icon}
              active={activeKey === item.key} collapsed
              badge={item.key === 'support' ? supportUnread : 0}
              onClick={() => go(item.category, item.key)}
            />
          ))}
        </List>
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Back to app" placement="right">
          <IconButton size="small" onClick={() => navigate('/dashboard')} sx={{ mb: 1, color: 'text.disabled' }}>
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
          onClick={() => navigate('/dashboard')}>
          <TelegizerLogo size="sm" variant="icon" />
          <Box>
            <Typography fontWeight={800} fontSize="0.9rem" letterSpacing="-0.02em" color="text.primary" lineHeight={1.1}>
              Telegizer
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
          <Avatar sx={{ width: 30, height: 30, bgcolor: PALETTE.purpleDk, fontSize: '0.8rem' }}>
            {(user?.full_name || user?.email || 'A').charAt(0).toUpperCase()}
          </Avatar>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography fontSize="0.78rem" fontWeight={600} noWrap color="text.primary">
              {user?.full_name || 'Admin'}
            </Typography>
            <Typography fontSize="0.62rem" noWrap color="text.disabled">{user?.email}</Typography>
          </Box>
        </Box>
        <Box sx={{ display: 'flex', gap: 0.5, mt: 0.75 }}>
          {role && (
            <Chip size="small" icon={<Shield sx={{ fontSize: 12 }} />}
              label={(ROLE_LABELS[role] || 'Admin').toUpperCase()}
              color={ROLE_COLORS[role] || 'default'}
              sx={{ height: 18, fontSize: '0.58rem', fontWeight: 700 }} />
          )}
          <Chip size="small" label={planLabel} sx={{ height: 18, fontSize: '0.58rem', fontWeight: 600 }} />
        </Box>
      </Box>

      <Divider sx={{ borderColor: PALETTE.border1 }} />

      {/* Categories */}
      <Box sx={{ flex: 1, py: 0.5 }}>
        {visibleCategories.map(cat => (
          <Box key={cat.slug}>
            <CategoryLabel label={cat.label} />
            <List dense disablePadding>
              {cat.items.map(item => (
                <NavItem
                  key={item.key} label={item.label} icon={item.icon}
                  active={activeKey === item.key}
                  badge={item.key === 'support' ? supportUnread : 0}
                  onClick={() => go(item.category, item.key)}
                />
              ))}
            </List>
          </Box>
        ))}
      </Box>

      <Divider sx={{ borderColor: PALETTE.border1 }} />

      {/* Footer */}
      <List dense disablePadding sx={{ py: 0.5 }}>
        <NavItem label="Back to App" icon={ArrowBack} onClick={() => navigate('/dashboard')} />
        <NavItem label="Logout" icon={Logout} onClick={handleLogout} />
      </List>
    </Box>
  );
}

export { SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH };
