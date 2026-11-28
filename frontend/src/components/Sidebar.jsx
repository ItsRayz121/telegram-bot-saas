import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box, List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  Typography, Avatar, Divider, Tooltip,
  Menu, MenuItem, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions, Button,
} from '@mui/material';
import {
  Home, Groups,
  CreditCard, Settings, AccountCircle, Logout,
  AdminPanelSettings, ExpandMore,
  Psychology, SmartToy, ChevronLeft, ChevronRight,
  EmojiEvents,
  CheckBox, LibraryBooks, ManageAccounts, VideoCall,
  NewReleases, Forum, SupportAgent, ChatBubbleOutline, Campaign, People, Email,
} from '@mui/icons-material';
import TelegizerLogo from './TelegizerLogo';
import { auth as authApi } from '../services/api';
import { APP_VERSION, BUILD_TIME } from '../version';
import { PALETTE } from '../theme';
import useAssistantName from '../hooks/useAssistantName';
import { SUPPORT_LINKS, openSupportEmail } from '../config/support';
import { clickableProps } from '../utils/a11y';

// Opens the in-app live-chat panel from anywhere (ChatWidget listens for this).
const openLiveChat = () => window.dispatchEvent(new Event('open-support-chat'));

const SIDEBAR_WIDTH = 240;
const SIDEBAR_COLLAPSED_WIDTH = 56;

// ── What's New changelog ───────────────────────────────────────────────────────
const CHANGELOG_VERSION = '2026-05-31';
const CHANGELOG_KEY = 'telegizer_whats_new_seen';

const CHANGELOG_ENTRIES = [
  { date: 'May 2026', title: 'Celery scheduled tasks now live', body: 'Reminders, digests, onboarding emails, and subscription downgrades now fire reliably via the Celery worker.' },
  { date: 'May 2026', title: '14-day Pro trial', body: 'All free users can now start a 14-day Pro trial with one click — no credit card required.' },
  { date: 'May 2026', title: 'CSP security hardening', body: 'Removed unsafe-inline from Content Security Policy. XSS protection is now fully active.' },
  { date: 'May 2026', title: 'Echo positioning clarified', body: 'Echo is now properly described as the AI assistant layer that works alongside Telegizer\'s moderation and automation — not a separate product.' },
  { date: 'May 2026', title: 'Lifecycle email sequence expanded', body: 'Added day 5 (AI feature spotlight), day 21 (growth playbook), and day 30 (upgrade nudge) emails to the onboarding sequence.' },
];

function WhatsNewDialog({ open, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ pb: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <NewReleases sx={{ color: 'text.secondary' }} />
          What's new
        </Box>
      </DialogTitle>
      <DialogContent sx={{ pt: 1.5 }}>
        {CHANGELOG_ENTRIES.map((entry, i) => (
          <Box key={i} sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.disabled" display="block" mb={0.25}>
              {entry.date}
            </Typography>
            <Typography variant="body2" fontWeight={600} mb={0.25}>
              {entry.title}
            </Typography>
            <Typography variant="caption" color="text.secondary" lineHeight={1.5} display="block">
              {entry.body}
            </Typography>
            {i < CHANGELOG_ENTRIES.length - 1 && <Divider sx={{ mt: 1.5 }} />}
          </Box>
        ))}
      </DialogContent>
      <DialogActions sx={{ px: 2, pb: 2 }}>
        <Button variant="contained" size="small" onClick={onClose} fullWidth>
          Got it
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Section label ──────────────────────────────────────────────────────────────
// 20px above, 4px below: a label sits closer to its own items than to the group above.
function SectionLabel({ label, dot }) {
  return (
    <Box component="li" sx={{ px: 2.5, pt: 2.5, pb: 0.5, display: 'flex', alignItems: 'center', gap: 0.75, listStyle: 'none' }}>
      <Typography variant="caption" sx={{ fontSize: '0.75rem', fontWeight: 500, color: PALETTE.text3, lineHeight: 1.33 }}>
        {label}
      </Typography>
      {dot && <Box className="ai-pulse-dot" />}
    </Box>
  );
}

// ── Single nav item ────────────────────────────────────────────────────────────
// Rows are 36px with 2px between them. Active = one surface step + hairline highlight.
const ROW = {
  minHeight: 36, borderRadius: '8px', mb: '2px',
  transition: 'background-color 0.12s cubic-bezier(0.22,1,0.36,1), color 0.12s cubic-bezier(0.22,1,0.36,1)',
};
function rowState(active, dimmed) {
  return {
    bgcolor: active ? PALETTE.bg3 : 'transparent',
    boxShadow: active ? 'inset 0 1px 0 rgba(255,255,255,0.05)' : 'none',
    color: active ? 'text.primary' : dimmed ? 'text.disabled' : 'text.secondary',
    '&:hover': { bgcolor: active ? PALETTE.bg3 : 'rgba(236,236,238,0.04)', color: 'text.primary' },
  };
}

function NavItem({ label, path, icon: Icon, badge, badgeCount, active, onClick, indent, dimmed, collapsed, tourId, ariaHasPopup }) {
  const navigate = useNavigate();
  const handleClick = onClick || (() => navigate(path));

  if (collapsed) {
    return (
      <Tooltip title={label} placement="right">
        <ListItem id={tourId} disablePadding sx={{ display: 'block' }}>
          <ListItemButton
            onClick={handleClick}
            aria-current={active ? 'page' : undefined}
            aria-label={label}
            sx={{ ...ROW, ...rowState(active), justifyContent: 'center', px: 0, mx: 1 }}
          >
            {Icon && <Icon sx={{ fontSize: 18 }} />}
          </ListItemButton>
        </ListItem>
      </Tooltip>
    );
  }

  return (
    <ListItem id={tourId} disablePadding sx={{ display: 'block' }}>
      <ListItemButton
        onClick={handleClick}
        aria-current={active && !ariaHasPopup ? 'page' : undefined}
        aria-haspopup={ariaHasPopup}
        aria-expanded={ariaHasPopup ? Boolean(active) : undefined}
        sx={{ ...ROW, ...rowState(active, dimmed), pl: indent ? 4 : 1.5, pr: 1.5, py: 0, mx: 1 }}
      >
        {Icon && (
          <ListItemIcon sx={{ minWidth: 28, color: 'inherit' }}>
            <Icon sx={{ fontSize: 18 }} />
          </ListItemIcon>
        )}
        <ListItemText
          primary={label}
          primaryTypographyProps={{ fontSize: '0.875rem', fontWeight: active ? 500 : 400, noWrap: true, lineHeight: 1.4 }}
        />
        {badgeCount > 0 && (
          <Typography component="span" className="mono" sx={{ fontSize: '0.75rem', color: 'error.main', ml: 0.5 }}>
            {badgeCount}
          </Typography>
        )}
        {badge && !badgeCount && (
          <Typography component="span" sx={{ fontSize: '0.75rem', color: 'text.disabled', ml: 0.5 }}>
            {badge}
          </Typography>
        )}
      </ListItemButton>
    </ListItem>
  );
}

// ── Sidebar content ────────────────────────────────────────────────────────────
export default function Sidebar({ onClose, collapsed, onToggle }) {
  const assistantName = useAssistantName();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const [user, setUser] = useState(null);
  const [anchorEl, setAnchorEl] = useState(null);
  const [supportAnchor, setSupportAnchor] = useState(null);
  const [whatsNewOpen, setWhatsNewOpen] = useState(false);
  const hasNewChangelog = localStorage.getItem(CHANGELOG_KEY) !== CHANGELOG_VERSION;

  const handleWhatsNewClose = () => {
    localStorage.setItem(CHANGELOG_KEY, CHANGELOG_VERSION);
    setWhatsNewOpen(false);
  };

  const isActive = useCallback(
    (path, exact = false) =>
      exact ? pathname === path : pathname === path || pathname.startsWith(path + '/'),
    [pathname]
  );

  const groupActive = isActive('/groups');
  const botsActive = isActive('/custom-bots') || isActive('/dashboard/bots');
  const discordBotsActive = isActive('/guildizer/bots');

  const assistantActive = isActive('/ark') || isActive('/hub') || isActive('/workspace');

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
    '&::-webkit-scrollbar': { width: 4 },
    '&::-webkit-scrollbar-thumb': { bgcolor: 'rgba(236,236,238,0.1)', borderRadius: 2 },
  };

  // ── Collapsed view ────────────────────────────────────────────────────────
  if (collapsed) {
    const COLLAPSED_ITEMS = [
      { label: 'Dashboard',      icon: Home,           path: '/dashboard', exact: true },
      { label: 'Telegram Bots',  icon: SmartToy,       path: '/custom-bots' },
      { label: 'Groups',         icon: Groups,         path: '/groups' },
      { label: assistantName,    icon: Psychology,     path: '/ark', ai: true },
      { label: 'Discord',        icon: Forum,          path: '/guildizer' },
      { label: 'Tasks',          icon: CheckBox,       path: '/workspace/tasks' },
      { label: 'Knowledge',      icon: LibraryBooks,   path: '/workspace/knowledge' },
      { label: 'Memory',         icon: ManageAccounts, path: '/workspace/memory' },
      { label: 'Meeting Links',  icon: VideoCall,      path: '/workspace/meeting-links' },
      { label: 'Referrals',      icon: EmojiEvents,    path: '/referrals' },
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
        <Box component="nav" aria-label="Main navigation" sx={{ width: '100%' }}>
        <List dense disablePadding sx={{ width: '100%' }}>
          {COLLAPSED_ITEMS.map(item => (
            <NavItem
              key={item.path}
              label={item.label}
              path={item.path}
              icon={item.icon}
              active={isActive(item.path, item.exact)}
              onClick={() => nav(item.path)}
              collapsed
            />
          ))}
        </List>
        </Box>
      </Box>
    );
  }

  // ── Full view ─────────────────────────────────────────────────────────────
  return (
    <Box sx={shellSx}>

      {/* ── Logo + collapse toggle ── */}
      <Box sx={{ px: 2, height: 56, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box
          sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1, cursor: 'pointer', borderRadius: 1 }}
          {...clickableProps(() => nav('/dashboard'), { 'aria-label': 'Telegizer dashboard' })}
        >
          <TelegizerLogo size="sm" />
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
          px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 1.25,
          cursor: 'pointer', borderRadius: '8px', mx: 1, my: 1,
          transition: 'background-color 0.12s cubic-bezier(0.22,1,0.36,1)',
          '&:hover': { bgcolor: 'rgba(236,236,238,0.04)' },
        }}
        {...clickableProps(e => setAnchorEl(e.currentTarget), { 'aria-haspopup': 'menu', 'aria-expanded': Boolean(anchorEl) })}
      >
        <Avatar
          sx={{
            width: 28, height: 28, fontSize: '0.8125rem', fontWeight: 500,
            bgcolor: PALETTE.bg4, color: 'text.primary',
          }}
        >
          {user?.full_name?.[0]?.toUpperCase() || 'U'}
        </Avatar>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography fontSize="0.8125rem" fontWeight={500} noWrap>
            {user?.full_name || 'Loading'}
          </Typography>
          <Typography fontSize="0.75rem" color="text.disabled" noWrap>
            {user?.email || ''}
          </Typography>
        </Box>
        <Typography component="span" sx={{ fontSize: '0.75rem', color: plan === 'free' ? 'text.disabled' : 'text.secondary', flexShrink: 0 }}>
          {planLabel}
        </Typography>
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
          Account settings
        </MenuItem>
        <MenuItem onClick={() => { setAnchorEl(null); nav('/billing'); }} dense>
          <ListItemIcon><CreditCard fontSize="small" /></ListItemIcon>
          Billing and plan
        </MenuItem>
        {isAdmin && (
          <MenuItem onClick={() => { setAnchorEl(null); nav('/admin-hub'); }} dense>
            <ListItemIcon><AdminPanelSettings fontSize="small" /></ListItemIcon>
            Admin panel
          </MenuItem>
        )}
        <Divider />
        <MenuItem onClick={handleLogout} dense sx={{ color: 'error.main' }}>
          <ListItemIcon><Logout fontSize="small" sx={{ color: 'error.main' }} /></ListItemIcon>
          Log out
        </MenuItem>
      </Menu>

      <Divider sx={{ borderColor: PALETTE.border1 }} />

      {/* ── Nav list ── */}
      <Box component="nav" aria-label="Main navigation" sx={{ flex: 1 }}>
      <List dense disablePadding sx={{ py: 0.5 }}>

        <NavItem label="Dashboard" path="/dashboard" icon={Home} active={isActive('/dashboard', true)} onClick={() => nav('/dashboard')} tourId="tour-dashboard" />

        {/* TELEGRAM — bots first, then groups (same order as the Dashboard) */}
        <SectionLabel label="Telegram" />
        <NavItem label="Bots" path="/custom-bots" icon={SmartToy} active={botsActive} onClick={() => nav('/custom-bots')} tourId="tour-bots" />
        <NavItem label="Groups" path="/groups" icon={Groups} active={groupActive} onClick={() => nav('/groups')} tourId="tour-groups" />

        {/* ECHO */}
        <SectionLabel label="Echo" dot />
        <NavItem label={assistantName} icon={Psychology} path="/ark" active={assistantActive} onClick={() => nav('/ark')} tourId="tour-echo" />

        {/* DISCORD — Guildizer, the 3rd pillar (separate backend, embedded UI) */}
        <SectionLabel label="Discord" />
        <NavItem label="Servers" path="/guildizer" icon={Forum} active={isActive('/guildizer') && !discordBotsActive} onClick={() => nav('/guildizer')} tourId="tour-guildizer" />
        <NavItem label="Bots" path="/guildizer/bots" icon={SmartToy} active={discordBotsActive} onClick={() => nav('/guildizer/bots')} />

        {/* Automation hub removed — Forwarding / Workflows / Webhooks now live in
            each group's Automation tab (Groups › <group> › Automation). */}
        <NavItem label="Referrals" path="/referrals" icon={EmojiEvents} active={isActive('/referrals')} onClick={() => nav('/referrals')} />

        <NavItem label="Settings" path="/settings" icon={Settings} active={isActive('/settings')} onClick={() => nav('/settings')} tourId="tour-settings" />

        {/* SUPPORT — dropdown: live chat, channel, community, email. Replaces the
            floating chat bubble as the primary entry point (esp. on mobile). */}
        <NavItem label="Support" icon={SupportAgent} ariaHasPopup="menu" active={Boolean(supportAnchor)} onClick={(e) => setSupportAnchor(e.currentTarget)} />

      </List>
      </Box>

      {/* ── Support menu ── */}
      <Menu
        anchorEl={supportAnchor}
        open={Boolean(supportAnchor)}
        onClose={() => setSupportAnchor(null)}
        PaperProps={{ sx: { minWidth: 210 } }}
      >
        <MenuItem dense onClick={() => { setSupportAnchor(null); openLiveChat(); }}>
          <ListItemIcon><ChatBubbleOutline fontSize="small" /></ListItemIcon>
          Live chat
        </MenuItem>
        <MenuItem dense component="a" href={SUPPORT_LINKS.channel} target="_blank" rel="noopener noreferrer" onClick={() => setSupportAnchor(null)}>
          <ListItemIcon><Campaign fontSize="small" /></ListItemIcon>
          Official channel
        </MenuItem>
        <MenuItem dense component="a" href={SUPPORT_LINKS.community} target="_blank" rel="noopener noreferrer" onClick={() => setSupportAnchor(null)}>
          <ListItemIcon><People fontSize="small" /></ListItemIcon>
          Community group
        </MenuItem>
        <MenuItem dense onClick={() => { setSupportAnchor(null); openSupportEmail(); }}>
          <ListItemIcon><Email fontSize="small" /></ListItemIcon>
          Email support
        </MenuItem>
      </Menu>

      {/* ── Plan upgrade banner ── */}
      {plan === 'free' && (
        <Box
          {...clickableProps(() => nav('/billing'))}
          sx={{
            mx: 1, mb: 1, p: 1.5, borderRadius: '12px', cursor: 'pointer',
            bgcolor: PALETTE.bg2,
            border: `1px solid ${PALETTE.border1}`,
            transition: 'border-color 0.12s cubic-bezier(0.22,1,0.36,1)',
            '&:hover': { borderColor: PALETTE.border2 },
          }}
        >
          <Typography fontSize="0.8125rem" fontWeight={500} color="text.primary">
            Upgrade to Pro
          </Typography>
          <Typography fontSize="0.75rem" color="text.secondary" mt={0.25}>
            3 custom bots, analytics, AI answers
          </Typography>
        </Box>
      )}

      {/* ── What's New ── */}
      <Box sx={{ px: 1, pb: 0.5 }}>
        <ListItemButton
          onClick={() => setWhatsNewOpen(true)}
          sx={{
            ...ROW, py: 0, px: 1.5,
            color: 'text.secondary',
            '&:hover': { bgcolor: 'rgba(236,236,238,0.04)', color: 'text.primary' },
          }}
        >
          <ListItemIcon sx={{ minWidth: 28, color: 'inherit' }}>
            <NewReleases sx={{ fontSize: 18 }} />
          </ListItemIcon>
          <ListItemText
            primary="What's new"
            primaryTypographyProps={{ fontSize: '0.875rem', fontWeight: 400 }}
          />
          {hasNewChangelog && (
            <Box sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: 'primary.main', flexShrink: 0 }} />
          )}
        </ListItemButton>
      </Box>

      {/* Version footer */}
      <Box sx={{ px: 2.5, pb: 2, pt: 0.5 }}>
        <Typography
          variant="caption"
          className="mono"
          color="text.disabled"
          fontSize="0.75rem"
          display="block"
          title={`Build: ${BUILD_TIME}`}
          sx={{ userSelect: 'none' }}
        >
          v{APP_VERSION}
        </Typography>
      </Box>

      <WhatsNewDialog open={whatsNewOpen} onClose={handleWhatsNewClose} />
    </Box>
  );
}

export { SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH };

