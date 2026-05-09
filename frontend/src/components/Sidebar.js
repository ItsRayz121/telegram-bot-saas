import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box, List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  Typography, Avatar, Chip, Divider, Skeleton, Tooltip,
  Menu, MenuItem, IconButton, Collapse,
} from '@mui/material';
import {
  Home, Groups, Campaign, AccessTime, Send, AutoMode,
  Explore, BarChart, SmartToy, CreditCard, Settings, Add, Handshake,
  AccountCircle, Logout, AdminPanelSettings, ExpandMore, ExpandLess,
  Psychology, Reply, EditNote, Summarize, Tune, CheckBox, LibraryBooks,
  CardGiftcard, ChevronLeft, ChevronRight,
} from '@mui/icons-material';
import TelegizerLogo from './TelegizerLogo';
import { telegramGroups as tgApi, auth as authApi, channels as chApi } from '../services/api';
import { APP_VERSION, BUILD_TIME } from '../version';

const SIDEBAR_WIDTH = 240;
const SIDEBAR_COLLAPSED_WIDTH = 56;

// ── Status dot ────────────────────────────────────────────────────────────────

function StatusDot({ status, permissions }) {
  const hasPerm = permissions && Object.values(permissions).some(Boolean);
  const color =
    status === 'active' && hasPerm ? '#22c55e'
    : status === 'active' && !hasPerm ? '#f59e0b'
    : '#ef4444';
  return (
    <Box sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: color, flexShrink: 0, ml: 0.5 }} />
  );
}

// ── Section label ─────────────────────────────────────────────────────────────

function SectionLabel({ label }) {
  return (
    <Typography
      variant="caption"
      fontWeight={700}
      color="text.disabled"
      sx={{ px: 2, pt: 1.5, pb: 0.25, display: 'block', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: '0.65rem' }}
    >
      {label}
    </Typography>
  );
}

// ── Single nav item ───────────────────────────────────────────────────────────

function NavItem({ label, path, icon: Icon, badge, badgeCount, active, onClick, indent, dimmed, collapsed }) {
  const navigate = useNavigate();
  const handleClick = onClick || (() => navigate(path));

  if (collapsed) {
    return (
      <Tooltip title={label} placement="right">
        <ListItem disablePadding sx={{ display: 'block' }}>
          <ListItemButton
            onClick={handleClick}
            sx={{
              justifyContent: 'center', px: 0, py: 0.6, mx: 0.5, mb: 0.15,
              borderRadius: 1.5, minHeight: 34,
              bgcolor: active ? 'primary.main' : 'transparent',
              color: active ? '#fff' : 'text.secondary',
              '&:hover': { bgcolor: active ? 'primary.dark' : 'rgba(255,255,255,0.05)', color: active ? '#fff' : 'text.primary' },
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
          py: 0.6,
          borderRadius: 1.5,
          mx: 0.75,
          mb: 0.15,
          minHeight: 34,
          bgcolor: active ? 'primary.main' : 'transparent',
          color: active ? '#fff' : dimmed ? 'text.disabled' : 'text.secondary',
          '&:hover': {
            bgcolor: active ? 'primary.dark' : 'rgba(255,255,255,0.05)',
            color: active ? '#fff' : 'text.primary',
          },
          transition: 'background 0.12s, color 0.12s',
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
            sx={{ height: 17, fontSize: '0.62rem', bgcolor: active ? 'rgba(255,255,255,0.25)' : 'error.main', color: '#fff', ml: 0.5 }}
          />
        )}
        {badge && !badgeCount && (
          <Chip
            label={badge}
            size="small"
            sx={{ height: 17, fontSize: '0.62rem', bgcolor: active ? 'rgba(255,255,255,0.25)' : 'primary.main', color: '#fff', ml: 0.5 }}
          />
        )}
      </ListItemButton>
    </ListItem>
  );
}

// ── Expandable section header (text navigates, chevron toggles) ───────────────

function ExpandableHeader({ label, icon: Icon, path, active, open, onToggle, onNavigate }) {
  return (
    <ListItem disablePadding sx={{ display: 'block' }}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          mx: 0.75,
          mb: 0.15,
          borderRadius: 1.5,
          bgcolor: active ? 'rgba(37,99,235,0.12)' : 'transparent',
          '&:hover': { bgcolor: active ? 'rgba(37,99,235,0.18)' : 'rgba(255,255,255,0.04)' },
          transition: 'background 0.12s',
        }}
      >
        {/* Main clickable area — navigates to section page */}
        <ListItemButton
          onClick={onNavigate}
          sx={{
            flex: 1,
            pl: 1.5,
            pr: 0.5,
            py: 0.6,
            minHeight: 34,
            borderRadius: 1.5,
            '&:hover': { bgcolor: 'transparent' },
          }}
        >
          {Icon && (
            <ListItemIcon sx={{ minWidth: 30, color: active ? 'primary.light' : 'text.secondary' }}>
              <Icon sx={{ fontSize: 17 }} />
            </ListItemIcon>
          )}
          <ListItemText
            primary={label}
            primaryTypographyProps={{
              fontSize: '0.82rem',
              fontWeight: active ? 600 : 400,
              noWrap: true,
              color: active ? 'primary.light' : 'text.secondary',
            }}
          />
        </ListItemButton>

        {/* Chevron — only toggles, does not navigate */}
        <IconButton
          size="small"
          onClick={(e) => { e.stopPropagation(); onToggle(); }}
          sx={{
            mr: 0.5,
            width: 22,
            height: 22,
            color: 'text.disabled',
            '&:hover': { color: 'text.secondary', bgcolor: 'rgba(255,255,255,0.06)' },
          }}
        >
          {open ? <ExpandLess sx={{ fontSize: 15 }} /> : <ExpandMore sx={{ fontSize: 15 }} />}
        </IconButton>
      </Box>
    </ListItem>
  );
}

// ── Sidebar content ───────────────────────────────────────────────────────────

export default function Sidebar({ onClose, collapsed, onToggle }) {
  const navigate = useNavigate();
  const { pathname, search } = useLocation();

  const [groups, setGroups] = useState([]);
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [channels, setChannels] = useState([]);
  const [channelsLoading, setChannelsLoading] = useState(true);
  const [user, setUser] = useState(null);
  const [anchorEl, setAnchorEl] = useState(null);
  const [showAllGroups, setShowAllGroups] = useState(false);

  const isActive = useCallback(
    (path, exact = false) =>
      exact ? pathname === path : pathname === path || pathname.startsWith(path + '/'),
    [pathname]
  );

  // Derive initial open states from current URL so deep-linking opens the right section
  const groupActive = isActive('/groups');
  const channelActive = isActive('/channels');

  const [groupsOpen, setGroupsOpen] = useState(groupActive);
  const [channelsOpen, setChannelsOpen] = useState(channelActive);

  const assistantActive = isActive('/workspace');
  const [assistantOpen, setAssistantOpen] = useState(() => {
    const stored = localStorage.getItem('sidebar_assistant_open');
    return stored === null ? true : stored === '1';
  });

  const toggleAssistant = () => setAssistantOpen(o => {
    localStorage.setItem('sidebar_assistant_open', !o ? '1' : '0');
    return !o;
  });

  const automationActive = isActive('/workspace/forwarding') || isActive('/workspace/automations') || isActive('/workflow-builder');
  const [automationOpen, setAutomationOpen] = useState(() => {
    const stored = localStorage.getItem('sidebar_automation_open');
    return stored === null ? true : stored === '1';
  });

  const toggleAutomation = () => setAutomationOpen(o => {
    localStorage.setItem('sidebar_automation_open', !o ? '1' : '0');
    return !o;
  });

  const analyticsActive = isActive('/analytics');
  const [analyticsOpen, setAnalyticsOpen] = useState(() => {
    const stored = localStorage.getItem('sidebar_analytics_open');
    return stored === null ? isActive('/analytics') : stored === '1';
  });

  const toggleAnalytics = () => setAnalyticsOpen(o => {
    localStorage.setItem('sidebar_analytics_open', !o ? '1' : '0');
    return !o;
  });

  // Keep sections open when navigating within them
  useEffect(() => {
    if (isActive('/groups')) setGroupsOpen(true);
  }, [pathname, isActive]);

  useEffect(() => {
    if (isActive('/channels')) setChannelsOpen(true);
  }, [pathname, isActive]);

  // ── Load user and groups ───────────────────────────────────────────────────

  useEffect(() => {
    const stored = localStorage.getItem('user');
    if (stored) {
      try { setUser(JSON.parse(stored)); } catch {}
    }
    authApi.getMe().then(r => {
      setUser(r.data.user);
      localStorage.setItem('user', JSON.stringify(r.data.user));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    tgApi.list().then(r => {
      setGroups(r.data.groups || []);
    }).catch(() => {}).finally(() => setGroupsLoading(false));
  }, []);

  useEffect(() => {
    chApi.list().then(r => {
      setChannels(r.data.channels || []);
    }).catch(() => {}).finally(() => setChannelsLoading(false));
  }, []);

  // ── Derived state ─────────────────────────────────────────────────────────

  const plan = user?.subscription_tier || 'free';
  const planLabel = plan === 'enterprise' ? 'Enterprise' : plan === 'pro' ? 'Pro' : 'Free';
  const planColor = plan === 'enterprise' ? 'secondary' : plan === 'pro' ? 'primary' : 'default';

  const isAdmin = user?.is_admin;
  const visibleGroups = showAllGroups ? groups : groups.slice(0, 8);
  const hasMoreGroups = groups.length > 8;
  const hasChannels = channels.length > 0;

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

  // ── Render ─────────────────────────────────────────────────────────────────

  // ── Collapsed (icon-only) view ────────────────────────────────────────────
  if (collapsed) {
    const COLLAPSED_ITEMS = [
      { label: 'Dashboard', icon: Home, path: '/dashboard', exact: true },
      { label: 'Groups',    icon: Groups, path: '/groups' },
      { label: 'Channels',  icon: Campaign, path: '/channels' },
      { label: 'Hub',       icon: Psychology, path: '/workspace' },
      { label: 'Automation',icon: AutoMode, path: '/workspace/automations' },
      { label: 'Billing',   icon: CreditCard, path: '/billing' },
      { label: 'Settings',  icon: Settings, path: '/settings' },
    ];
    return (
      <Box sx={{
        width: '100%', height: '100vh', display: 'flex', flexDirection: 'column',
        bgcolor: 'background.paper', borderRight: '1px solid', borderColor: 'divider',
        overflowY: 'auto', overflowX: 'hidden', alignItems: 'center', pt: 1,
        '&::-webkit-scrollbar': { width: 0 },
      }}>
        <Tooltip title="Expand sidebar" placement="right">
          <IconButton size="small" onClick={onToggle} sx={{ mb: 1 }}>
            <ChevronRight fontSize="small" />
          </IconButton>
        </Tooltip>
        <Divider sx={{ width: '100%', mb: 0.5 }} />
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
    );
  }

  return (
    <Box
      sx={{
        width: '100%',
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'background.paper',
        borderRight: '1px solid',
        borderColor: 'divider',
        overflowY: 'auto',
        overflowX: 'hidden',
        flexShrink: 0,
        '&::-webkit-scrollbar': { width: 4 },
        '&::-webkit-scrollbar-thumb': { bgcolor: 'divider', borderRadius: 2 },
      }}
    >
      {/* ── Logo + collapse toggle ── */}
      <Box sx={{ px: 2, py: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1, cursor: 'pointer' }} onClick={() => nav('/dashboard')}>
          <TelegizerLogo size="sm" variant="icon" />
          <Typography fontWeight={700} fontSize="0.95rem" color="text.primary">Telegizer</Typography>
        </Box>
        {onToggle && (
          <Tooltip title="Collapse sidebar" placement="right">
            <IconButton size="small" onClick={onToggle} sx={{ color: 'text.disabled' }}>
              <ChevronLeft sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      <Divider />

      {/* ── User card ── */}
      <Box
        sx={{ px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer' }}
        onClick={e => setAnchorEl(e.currentTarget)}
      >
        <Avatar sx={{ width: 28, height: 28, bgcolor: 'primary.main', fontSize: '0.75rem' }}>
          {user?.full_name?.[0]?.toUpperCase() || 'U'}
        </Avatar>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography fontSize="0.78rem" fontWeight={600} noWrap>{user?.full_name || 'Loading...'}</Typography>
          <Typography fontSize="0.65rem" color="text.disabled" noWrap>{user?.email || ''}</Typography>
        </Box>
        <Chip
          label={planLabel}
          size="small"
          color={planColor}
          sx={{ height: 16, fontSize: '0.6rem', flexShrink: 0 }}
        />
        <ExpandMore sx={{ fontSize: 14, color: 'text.disabled', flexShrink: 0 }} />
      </Box>

      {/* ── User menu ── */}
      <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}
        PaperProps={{ sx: { minWidth: 160 } }}>
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

      <Divider />

      {/* ── Nav list ── */}
      <List dense disablePadding sx={{ flex: 1, py: 0.5 }}>

        {/* Dashboard */}
        <NavItem label="Dashboard" path="/dashboard" icon={Home} active={isActive('/dashboard', true)} onClick={() => nav('/dashboard')} />

        {/* ── COMMUNITIES ── */}
        <SectionLabel label="Communities" />

        {/* Groups — flat link, opens My Groups page */}
        <NavItem label="Groups" path="/groups" icon={Groups} active={groupActive} />

        {/* Channels — expandable if channels exist, flat with add-icon if not */}
        {hasChannels ? (
          <>
            <ExpandableHeader
              label="Channels"
              icon={Campaign}
              path="/channels"
              active={channelActive}
              open={channelsOpen}
              onToggle={() => setChannelsOpen(o => !o)}
              onNavigate={() => nav('/channels')}
            />

            <Collapse in={channelsOpen} timeout={160} unmountOnExit>
              {channelsLoading ? (
                [1].map(i => (
                  <ListItem key={i} sx={{ pl: 4, py: 0.3 }}>
                    <Skeleton width={140} height={14} />
                  </ListItem>
                ))
              ) : (
                channels.map(channel => {
                  const cPath = `/channels/${channel.id}`;
                  const cActive = isActive(cPath);
                  return (
                    <ListItem key={channel.id} disablePadding>
                      <ListItemButton
                        onClick={() => nav(cPath)}
                        sx={{
                          pl: 3.5, pr: 1.5, py: 0.4, mx: 0.75, mb: 0.1, borderRadius: 1.5,
                          bgcolor: cActive ? 'rgba(37,99,235,0.15)' : 'transparent',
                          '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' },
                        }}
                      >
                        <ListItemText
                          primary={channel.title || channel.name}
                          primaryTypographyProps={{
                            fontSize: '0.78rem',
                            fontWeight: cActive ? 600 : 400,
                            noWrap: true,
                            color: cActive ? 'primary.light' : 'text.secondary',
                          }}
                        />
                      </ListItemButton>
                    </ListItem>
                  );
                })
              )}

              {/* + Add Channel */}
              <ListItem disablePadding>
                <ListItemButton
                  onClick={() => nav('/channels')}
                  sx={{ pl: 3.5, py: 0.4, mx: 0.75, mb: 0.25, borderRadius: 1.5, '&:hover': { bgcolor: 'rgba(255,255,255,0.04)' } }}
                >
                  <ListItemIcon sx={{ minWidth: 22 }}>
                    <Add sx={{ fontSize: 14, color: 'text.disabled' }} />
                  </ListItemIcon>
                  <ListItemText
                    primary="Add Channel"
                    primaryTypographyProps={{ fontSize: '0.75rem', color: 'text.disabled' }}
                  />
                </ListItemButton>
              </ListItem>
            </Collapse>
          </>
        ) : (
          // No channels yet — flat item with add icon on the right
          <ListItem disablePadding sx={{ display: 'block' }}>
            <ListItemButton
              onClick={() => nav('/channels')}
              sx={{
                pl: 1.5, pr: 0.5, py: 0.6, mx: 0.75, mb: 0.15, borderRadius: 1.5, minHeight: 34,
                bgcolor: channelActive ? 'rgba(37,99,235,0.12)' : 'transparent',
                color: channelActive ? 'primary.light' : 'text.secondary',
                '&:hover': { bgcolor: 'rgba(255,255,255,0.05)', color: 'text.primary' },
                transition: 'background 0.12s, color 0.12s',
              }}
            >
              <ListItemIcon sx={{ minWidth: 30, color: 'inherit' }}>
                <Campaign sx={{ fontSize: 17 }} />
              </ListItemIcon>
              <ListItemText
                primary="Channels"
                primaryTypographyProps={{ fontSize: '0.82rem', fontWeight: channelActive ? 600 : 400, noWrap: true }}
              />
              <IconButton
                size="small"
                onClick={(e) => { e.stopPropagation(); nav('/channels'); }}
                sx={{ width: 20, height: 20, mr: 0.25, color: 'text.disabled', '&:hover': { color: 'text.secondary' } }}
              >
                <Add sx={{ fontSize: 14 }} />
              </IconButton>
            </ListItemButton>
          </ListItem>
        )}

        {/* ── ASSISTANT HUB ── */}
        <SectionLabel label="Assistant Hub" />
        <ExpandableHeader
          label="Hub"
          icon={Psychology}
          path="/workspace"
          active={assistantActive}
          open={assistantOpen}
          onToggle={toggleAssistant}
          onNavigate={() => nav('/workspace')}
        />
        {/* "Powered by" subtitle — always visible, outside the Collapse */}
        <Typography variant="caption" sx={{ px: 2, pb: 0.5, display: 'block', fontSize: '0.62rem', color: 'text.disabled', lineHeight: 1.3 }}>
          Powered by Telegizer Assistant
        </Typography>
        <Collapse in={assistantOpen} timeout={160} unmountOnExit>
          <NavItem label="Assistant Bot" path="/workspace/assistant-bot"  icon={SmartToy}    active={isActive('/workspace/assistant-bot')} onClick={() => nav('/workspace/assistant-bot')} indent badge={plan === 'free' ? 'Pro' : null} />
          <NavItem label="Auto-Replies"  path="/workspace/smart-links"    icon={Reply}       active={isActive('/workspace/smart-links')}    onClick={() => nav('/workspace/smart-links')} indent />
          <NavItem label="Reminders"     path="/workspace/reminders"      icon={AccessTime}  active={isActive('/workspace/reminders')}      onClick={() => nav('/workspace/reminders')} indent />
          <NavItem label="Tasks"         path="/workspace/tasks"          icon={CheckBox}    active={isActive('/workspace/tasks')}          onClick={() => nav('/workspace/tasks')} indent />
          <NavItem label="Notes"         path="/workspace/notes"          icon={EditNote}    active={isActive('/workspace/notes')}          onClick={() => nav('/workspace/notes')} indent />
          <NavItem label="Digests"       path="/workspace/digests"        icon={Summarize}   active={isActive('/workspace/digests')}       onClick={() => nav('/workspace/digests')} indent />
          <NavItem label="Knowledge"     path="/workspace/knowledge"      icon={LibraryBooks} active={isActive('/workspace/knowledge')}    onClick={() => nav('/workspace/knowledge')} indent />
          <NavItem label="AI Settings"   path="/workspace/ai-settings"    icon={Tune}        active={isActive('/workspace/ai-settings')}   onClick={() => nav('/workspace/ai-settings')} indent />
        </Collapse>

        {/* ── AUTOMATION ── */}
        <SectionLabel label="Automation" />
        <ExpandableHeader
          label="Automation"
          icon={AutoMode}
          path="/workspace/automations"
          active={automationActive}
          open={automationOpen}
          onToggle={toggleAutomation}
          onNavigate={() => nav('/workspace/automations')}
        />
        <Collapse in={automationOpen} timeout={160} unmountOnExit>
          <NavItem label="Forwarding"   path="/workspace/forwarding"   icon={Send}     active={isActive('/workspace/forwarding')}   onClick={() => nav('/workspace/forwarding')} indent />
          <NavItem label="Workflows"    path="/workspace/automations"  icon={AutoMode} active={isActive('/workspace/automations')}  onClick={() => nav('/workspace/automations')} indent />
          {/* Flow Builder hidden — duplicate of Workflows; route and page intact for future reactivation */}
        </Collapse>

        {/* Analytics hidden from sidebar — accessible via group/channel pages */}

        {/* ── ACCOUNT ── */}
        <SectionLabel label="Account" />
        <NavItem label="Billing"  path="/billing"  icon={CreditCard} active={isActive('/billing')}  onClick={() => nav('/billing')} />
        <NavItem label="Settings" path="/settings" icon={Settings}   active={isActive('/settings')} onClick={() => nav('/settings')} />

      </List>

      {/* ── Plan upgrade banner ── */}
      {plan === 'free' && (
        <Box
          sx={{
            m: 1, p: 1.5, borderRadius: 2, bgcolor: 'rgba(37,99,235,0.1)',
            border: '1px solid rgba(37,99,235,0.3)', cursor: 'pointer',
          }}
          onClick={() => nav('/billing')}
        >
          <Typography fontSize="0.75rem" fontWeight={600} color="primary.light">Upgrade to Pro</Typography>
          <Typography fontSize="0.68rem" color="text.disabled" mt={0.25}>
            5 groups · 3 channels · AI digest
          </Typography>
        </Box>
      )}

      {/* Version footer */}
      <Box sx={{ px: 1.5, pb: 1, pt: 0.5 }}>
        <Typography
          variant="caption"
          color="text.disabled"
          fontSize="0.65rem"
          display="block"
          title={`Build: ${BUILD_TIME}`}
          sx={{ userSelect: 'none' }}
        >
          v{APP_VERSION}
        </Typography>
      </Box>
    </Box>
  );
}

export { SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH };
