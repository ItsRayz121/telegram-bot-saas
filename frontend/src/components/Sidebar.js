import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box, List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  Typography, Avatar, Chip, Divider, Tooltip,
  Menu, MenuItem, IconButton, Collapse, LinearProgress,
} from '@mui/material';
import {
  Home, Groups, AutoMode,
  CreditCard, Settings, AccountCircle, Logout,
  AdminPanelSettings, ExpandMore, ExpandLess,
  Psychology, ChevronLeft, ChevronRight,
  EmojiEvents, CheckCircle, RadioButtonUnchecked,
  CheckBox, LibraryBooks, ManageAccounts, VideoCall,
} from '@mui/icons-material';
import TelegizerLogo from './TelegizerLogo';
import { auth as authApi } from '../services/api';
import { APP_VERSION, BUILD_TIME } from '../version';
import { PALETTE } from '../theme';
import useAssistantName from '../hooks/useAssistantName';

const SIDEBAR_WIDTH = 240;
const SIDEBAR_COLLAPSED_WIDTH = 56;

// ── Section label ──────────────────────────────────────────────────────────────
function SectionLabel({ label }) {
  return (
    <Typography
      variant="caption"
      sx={{
        px: 2, pt: 1.5, pb: 0.25, display: 'block',
        textTransform: 'uppercase', letterSpacing: '0.1em',
        fontSize: '0.6rem', fontWeight: 700,
        color: PALETTE.text3,
      }}
    >
      {label}
    </Typography>
  );
}

// ── Single nav item ────────────────────────────────────────────────────────────
function NavItem({ label, path, icon: Icon, badge, badgeCount, active, onClick, indent, dimmed, collapsed, aiAccent }) {
  const navigate = useNavigate();
  const handleClick = onClick || (() => navigate(path));

  const activeStyles = active ? {
    bgcolor: aiAccent
      ? 'rgba(157,108,247,0.16)'
      : 'rgba(61,142,248,0.14)',
    color: aiAccent ? PALETTE.purpleLt : PALETTE.blueLt,
    boxShadow: aiAccent
      ? `inset 3px 0 0 ${PALETTE.purple}, 0 0 12px rgba(157,108,247,0.12)`
      : `inset 3px 0 0 ${PALETTE.blue}, 0 0 12px rgba(61,142,248,0.12)`,
  } : {};

  if (collapsed) {
    return (
      <Tooltip title={label} placement="right">
        <ListItem disablePadding sx={{ display: 'block' }}>
          <ListItemButton
            onClick={handleClick}
            sx={{
              justifyContent: 'center', px: 0, py: 0.65, mx: 0.5, mb: 0.2,
              borderRadius: 1.5, minHeight: 36,
              ...activeStyles,
              bgcolor: active
                ? (aiAccent ? 'rgba(157,108,247,0.16)' : 'rgba(61,142,248,0.14)')
                : 'transparent',
              color: active ? (aiAccent ? PALETTE.purpleLt : PALETTE.blueLt) : 'text.secondary',
              transition: 'all 0.18s ease',
              '&:hover': {
                bgcolor: active
                  ? (aiAccent ? 'rgba(157,108,247,0.22)' : 'rgba(61,142,248,0.2)')
                  : 'rgba(255,255,255,0.05)',
                color: active ? undefined : 'text.primary',
              },
            }}
          >
            {Icon && <Icon sx={{ fontSize: 18 }} />}
          </ListItemButton>
        </ListItem>
      </Tooltip>
    );
  }

  return (
    <ListItem disablePadding sx={{ display: 'block' }}>
      <ListItemButton
        onClick={handleClick}
        sx={{
          pl: indent ? 3.5 : 1.5,
          pr: 1.5,
          py: 0.65,
          borderRadius: 1.5,
          mx: 0.75,
          mb: 0.2,
          minHeight: 36,
          position: 'relative',
          ...activeStyles,
          bgcolor: active
            ? (aiAccent ? 'rgba(157,108,247,0.14)' : 'rgba(61,142,248,0.12)')
            : 'transparent',
          color: active
            ? (aiAccent ? PALETTE.purpleLt : PALETTE.blueLt)
            : dimmed ? 'text.disabled' : 'text.secondary',
          transition: 'all 0.18s ease',
          '&:hover': {
            bgcolor: active
              ? (aiAccent ? 'rgba(157,108,247,0.2)' : 'rgba(61,142,248,0.18)')
              : 'rgba(255,255,255,0.05)',
            color: active ? undefined : 'text.primary',
            transform: 'translateX(1px)',
          },
        }}
      >
        {Icon && (
          <ListItemIcon sx={{ minWidth: 30, color: 'inherit' }}>
            <Icon sx={{ fontSize: 17 }} />
          </ListItemIcon>
        )}
        <ListItemText
          primary={label}
          primaryTypographyProps={{
            fontSize: '0.82rem',
            fontWeight: active ? 600 : 400,
            noWrap: true,
            lineHeight: 1.3,
          }}
        />
        {badgeCount > 0 && (
          <Chip
            label={badgeCount}
            size="small"
            sx={{
              height: 17, fontSize: '0.62rem', ml: 0.5,
              bgcolor: active ? 'rgba(255,255,255,0.18)' : 'error.main',
              color: '#fff',
            }}
          />
        )}
        {badge && !badgeCount && (
          <Chip
            label={badge}
            size="small"
            sx={{
              height: 17, fontSize: '0.62rem', ml: 0.5,
              bgcolor: active
                ? 'rgba(255,255,255,0.18)'
                : aiAccent ? PALETTE.purple : PALETTE.blue,
              color: '#fff',
            }}
          />
        )}
      </ListItemButton>
    </ListItem>
  );
}

// ── AI Hub label with pulse dot ────────────────────────────────────────────────
function HubSectionLabel() {
  return (
    <Box sx={{ px: 2, pt: 1.5, pb: 0.25, display: 'flex', alignItems: 'center', gap: 0.75 }}>
      <Typography
        variant="caption"
        sx={{
          textTransform: 'uppercase', letterSpacing: '0.1em',
          fontSize: '0.6rem', fontWeight: 700, color: PALETTE.text3,
        }}
      >
        Echo
      </Typography>
      <Box className="ai-pulse-dot" sx={{ width: 5, height: 5 }} />
    </Box>
  );
}

// ── 5-step onboarding checklist ───────────────────────────────────────────────
const ONBOARDING_STEPS = [
  { key: 'telegram_connected',     label: 'Connect Telegram',       path: '/settings' },
  { key: 'first_group_linked',     label: 'Link a Group',           path: '/groups' },
  { key: 'welcome_message_set',    label: 'Enable Welcome Message', path: '/groups' },
  { key: 'moderation_rule_set',    label: 'Set Moderation Rule',    path: '/groups' },
  { key: 'referral_shared',        label: 'Invite a Friend',        path: '/referrals' },
];

function OnboardingChecklist({ user, nav }) {
  const [open, setOpen] = useState(false);
  const completed = user?.onboarding_completed_steps || [];
  const doneCount = ONBOARDING_STEPS.filter(s => completed.includes(s.key)).length;

  if (doneCount >= ONBOARDING_STEPS.length) return null;

  return (
    <Box sx={{ mx: 1, mb: 0.5 }}>
      <Box
        onClick={() => setOpen(o => !o)}
        sx={{
          display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer',
          px: 1.5, py: 1, borderRadius: 1.5,
          border: '1px solid rgba(61,142,248,0.2)',
          background: 'rgba(61,142,248,0.06)',
          '&:hover': { background: 'rgba(61,142,248,0.1)' },
        }}
      >
        <Typography fontSize="0.72rem" fontWeight={600} sx={{ flex: 1, color: PALETTE.blueLt }}>
          Getting Started {doneCount}/{ONBOARDING_STEPS.length}
        </Typography>
        <LinearProgress
          variant="determinate"
          value={(doneCount / ONBOARDING_STEPS.length) * 100}
          sx={{
            width: 48, height: 4, borderRadius: 2,
            bgcolor: 'rgba(61,142,248,0.15)',
            '& .MuiLinearProgress-bar': { bgcolor: PALETTE.blue },
          }}
        />
        {open ? <ExpandLess sx={{ fontSize: 14, color: 'text.disabled' }} /> : <ExpandMore sx={{ fontSize: 14, color: 'text.disabled' }} />}
      </Box>
      <Collapse in={open} timeout={180} unmountOnExit>
        <Box sx={{ pt: 0.5 }}>
          {ONBOARDING_STEPS.map(step => {
            const done = completed.includes(step.key);
            return (
              <Box
                key={step.key}
                onClick={() => nav(step.path)}
                sx={{
                  display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer',
                  px: 1.5, py: 0.6, borderRadius: 1, mx: 0.25,
                  '&:hover': { background: 'rgba(255,255,255,0.04)' },
                }}
              >
                {done
                  ? <CheckCircle sx={{ fontSize: 14, color: 'success.main', flexShrink: 0 }} />
                  : <RadioButtonUnchecked sx={{ fontSize: 14, color: 'text.disabled', flexShrink: 0 }} />
                }
                <Typography
                  fontSize="0.76rem"
                  sx={{ color: done ? 'text.disabled' : 'text.secondary', textDecoration: done ? 'line-through' : 'none' }}
                >
                  {step.label}
                </Typography>
              </Box>
            );
          })}
        </Box>
      </Collapse>
    </Box>
  );
}

// ── Sidebar content ────────────────────────────────────────────────────────────
export default function Sidebar({ onClose, collapsed, onToggle }) {
  const assistantName = useAssistantName();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const [user, setUser] = useState(null);
  const [anchorEl, setAnchorEl] = useState(null);

  const isActive = useCallback(
    (path, exact = false) =>
      exact ? pathname === path : pathname === path || pathname.startsWith(path + '/'),
    [pathname]
  );

  const groupActive = isActive('/groups');

  const assistantActive = isActive('/ark') || isActive('/hub') || isActive('/workspace');
  const automationActive = isActive('/automation') || isActive('/workspace/forwarding') || isActive('/workspace/automations') || isActive('/workflow-builder');

  useEffect(() => {
    const stored = localStorage.getItem('user');
    if (stored) { try { setUser(JSON.parse(stored)); } catch {} }
    authApi.getMe().then(r => {
      setUser(r.data.user);
      localStorage.setItem('user', JSON.stringify(r.data.user));
    }).catch((err) => {
      if (process.env.NODE_ENV !== 'production') console.warn('[sidebar] getMe failed', err);
    });
  }, []);

  const plan      = user?.subscription_tier || 'free';
  const planLabel = plan === 'enterprise' ? 'Enterprise' : plan === 'pro' ? 'Pro' : 'Free';
  const planColor = plan === 'enterprise' ? '#9d6cf7' : plan === 'pro' ? '#3d8ef8' : PALETTE.text3;
  const isAdmin = user?.is_admin;

  const handleLogout = () => {
    authApi.logout?.().catch(() => {});
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const nav = (path) => {
    if (onClose) onClose();
    navigate(path);
  };

  // ── Sidebar shell styles ───────────────────────────────────────────────────
  const shellSx = {
    width: '100%', height: '100vh', display: 'flex', flexDirection: 'column',
    bgcolor: PALETTE.bg1,
    borderRight: `1px solid ${PALETTE.border1}`,
    overflowY: 'auto', overflowX: 'hidden', flexShrink: 0,
    '&::-webkit-scrollbar': { width: 3 },
    '&::-webkit-scrollbar-thumb': { bgcolor: 'rgba(61,142,248,0.15)', borderRadius: 2 },
  };

  // ── Collapsed view ────────────────────────────────────────────────────────
  if (collapsed) {
    const COLLAPSED_ITEMS = [
      { label: 'Dashboard',      icon: Home,           path: '/dashboard', exact: true },
      { label: 'Groups',         icon: Groups,         path: '/groups' },
      { label: assistantName,    icon: Psychology,     path: '/ark', ai: true },
      { label: 'Tasks',          icon: CheckBox,       path: '/workspace/tasks' },
      { label: 'Knowledge',      icon: LibraryBooks,   path: '/workspace/knowledge' },
      { label: 'Memory',         icon: ManageAccounts, path: '/workspace/memory' },
      { label: 'Meeting Links',  icon: VideoCall,      path: '/workspace/meeting-links' },
      { label: 'Referrals',      icon: EmojiEvents,    path: '/referrals' },
      { label: 'Automation',     icon: AutoMode,       path: '/automation' },
      { label: 'Settings',       icon: Settings,       path: '/settings' },
    ];
    return (
      <Box sx={{ ...shellSx, alignItems: 'center', pt: 1 }}>
        <Tooltip title="Expand sidebar" placement="right">
          <IconButton size="small" onClick={onToggle} sx={{ mb: 1, color: 'text.disabled' }}>
            <ChevronRight fontSize="small" />
          </IconButton>
        </Tooltip>
        <Divider sx={{ width: '100%', mb: 0.5, borderColor: PALETTE.border1 }} />
        <List dense disablePadding sx={{ width: '100%' }}>
          {COLLAPSED_ITEMS.map(item => (
            <NavItem
              key={item.path}
              label={item.label}
              path={item.path}
              icon={item.icon}
              active={isActive(item.path, item.exact)}
              onClick={() => nav(item.path)}
              aiAccent={item.ai}
              collapsed
            />
          ))}
        </List>
      </Box>
    );
  }

  // ── Full view ─────────────────────────────────────────────────────────────
  return (
    <Box sx={shellSx}>

      {/* ── Logo + collapse toggle ── */}
      <Box sx={{ px: 2, py: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box
          sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1, cursor: 'pointer' }}
          onClick={() => nav('/dashboard')}
        >
          <TelegizerLogo size="sm" variant="icon" />
          <Typography fontWeight={800} fontSize="0.95rem" letterSpacing="-0.02em" color="text.primary">
            Telegizer
          </Typography>
        </Box>
        {onToggle && (
          <Tooltip title="Collapse sidebar" placement="right">
            <IconButton
              size="small"
              onClick={onToggle}
              sx={{
                color: 'text.disabled', borderRadius: 1.5,
                '&:hover': { color: 'text.secondary', bgcolor: 'rgba(255,255,255,0.06)' },
              }}
            >
              <ChevronLeft sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      <Divider sx={{ borderColor: PALETTE.border1 }} />

      {/* ── User card ── */}
      <Box
        sx={{
          px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 1,
          cursor: 'pointer', borderRadius: 2, mx: 0.5,
          transition: 'background 0.15s ease',
          '&:hover': { bgcolor: 'rgba(255,255,255,0.04)' },
        }}
        onClick={e => setAnchorEl(e.currentTarget)}
      >
        <Avatar
          sx={{
            width: 30, height: 30, fontSize: '0.78rem', fontWeight: 700,
            background: `linear-gradient(135deg, ${PALETTE.blue}, ${PALETTE.purple})`,
            boxShadow: `0 0 10px ${PALETTE.glowBlue}`,
          }}
        >
          {user?.full_name?.[0]?.toUpperCase() || 'U'}
        </Avatar>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography fontSize="0.78rem" fontWeight={600} noWrap letterSpacing="-0.01em">
            {user?.full_name || 'Loading...'}
          </Typography>
          <Typography fontSize="0.65rem" color="text.disabled" noWrap>
            {user?.email || ''}
          </Typography>
        </Box>
        <Chip
          label={planLabel}
          size="small"
          sx={{
            height: 17, fontSize: '0.6rem', fontWeight: 600, flexShrink: 0,
            bgcolor: `${planColor}22`,
            color: planColor,
            border: `1px solid ${planColor}44`,
          }}
        />
        <ExpandMore sx={{ fontSize: 14, color: 'text.disabled', flexShrink: 0, transition: 'transform 0.15s', ...(Boolean(anchorEl) && { transform: 'rotate(180deg)' }) }} />
      </Box>

      {/* ── User menu ── */}
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
        PaperProps={{ sx: { minWidth: 180 } }}
      >
        <MenuItem onClick={() => { setAnchorEl(null); nav('/settings'); }} dense>
          <ListItemIcon><AccountCircle fontSize="small" /></ListItemIcon>
          Account Settings
        </MenuItem>
        <MenuItem onClick={() => { setAnchorEl(null); nav('/billing'); }} dense>
          <ListItemIcon><CreditCard fontSize="small" /></ListItemIcon>
          Billing & Plan
        </MenuItem>
        {isAdmin && (
          <MenuItem onClick={() => { setAnchorEl(null); nav('/admin'); }} dense>
            <ListItemIcon><AdminPanelSettings fontSize="small" /></ListItemIcon>
            Admin Panel
          </MenuItem>
        )}
        <Divider />
        <MenuItem onClick={handleLogout} dense sx={{ color: 'error.main' }}>
          <ListItemIcon><Logout fontSize="small" sx={{ color: 'error.main' }} /></ListItemIcon>
          Logout
        </MenuItem>
      </Menu>

      <Divider sx={{ borderColor: PALETTE.border1 }} />

      {/* ── Nav list ── */}
      <List dense disablePadding sx={{ flex: 1, py: 0.5 }}>

        <NavItem label="Dashboard" path="/dashboard" icon={Home} active={isActive('/dashboard', true)} onClick={() => nav('/dashboard')} />

        {/* GROUPS */}
        <SectionLabel label="Groups" />
        <NavItem label="Groups" path="/groups" icon={Groups} active={groupActive} onClick={() => nav('/groups')} />

        {/* ECHO */}
        <HubSectionLabel />
        <NavItem label={assistantName} icon={Psychology} path="/ark" active={assistantActive} aiAccent onClick={() => nav('/ark')} />

        {/* AUTOMATION */}
        <SectionLabel label="Automation" />
        <NavItem label="Automation" icon={AutoMode} path="/automation" active={automationActive} onClick={() => nav('/automation')} />

        <NavItem label="Referrals" path="/referrals" icon={EmojiEvents} active={isActive('/referrals')} onClick={() => nav('/referrals')} />

        <NavItem label="Settings" path="/settings" icon={Settings} active={isActive('/settings')} onClick={() => nav('/settings')} />

      </List>

      {/* ── Plan upgrade banner ── */}
      {plan === 'free' && (
        <Box
          onClick={() => nav('/billing')}
          sx={{
            m: 1, p: 1.5, borderRadius: 2, cursor: 'pointer',
            background: `linear-gradient(135deg, rgba(61,142,248,0.12) 0%, rgba(157,108,247,0.1) 100%)`,
            border: `1px solid rgba(61,142,248,0.25)`,
            transition: 'all 0.2s ease',
            '&:hover': {
              background: `linear-gradient(135deg, rgba(61,142,248,0.18) 0%, rgba(157,108,247,0.16) 100%)`,
              borderColor: 'rgba(61,142,248,0.4)',
              transform: 'translateY(-1px)',
            },
          }}
        >
          <Typography fontSize="0.75rem" fontWeight={700} sx={{ color: PALETTE.blueLt, letterSpacing: '-0.01em' }}>
            Upgrade to Pro ↗
          </Typography>
          <Typography fontSize="0.67rem" color="text.disabled" mt={0.25}>
            5 groups · 3 channels · AI digest
          </Typography>
        </Box>
      )}

      {/* Version footer */}
      <Box sx={{ px: 2, pb: 1.5, pt: 0.5 }}>
        <Typography
          variant="caption"
          color="text.disabled"
          fontSize="0.6rem"
          display="block"
          title={`Build: ${BUILD_TIME}`}
          sx={{ userSelect: 'none', letterSpacing: '0.04em' }}
        >
          v{APP_VERSION}
        </Typography>
      </Box>
    </Box>
  );
}

export { SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH };

