import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Card, CardContent, CircularProgress, Button,
  Avatar, Chip, List, ListItemButton, ListItemText, ListItemAvatar,
  Alert, Divider, Stack, BottomNavigation, BottomNavigationAction, Paper,
} from '@mui/material';
import {
  Groups, OpenInNew, CheckCircle, ErrorOutline,
  Bolt, CardGiftcard, Settings, Shield,
} from '@mui/icons-material';
import { useTelegram } from '../contexts/TelegramContext';
import TelegizerLogo from '../components/TelegizerLogo';
import MiniAppReferrals from './MiniAppReferrals';
import MiniAppSetup from './MiniAppSetup';
import EmailLinkFlow from '../components/EmailLinkFlow';

// ── Status screens ────────────────────────────────────────────────────────────

function LoadingScreen() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: 2 }}>
      <CircularProgress size={36} />
      <Typography color="text.secondary" variant="body2">Opening Telegizer…</Typography>
    </Box>
  );
}

function ErrorScreen({ message }) {
  return (
    <Box sx={{ p: { xs: 2, md: 3 }, textAlign: 'center' }}>
      <ErrorOutline sx={{ fontSize: 56, color: 'error.main', mb: 2 }} />
      <Typography variant="h6" fontWeight={700} gutterBottom>Something went wrong</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        {message || 'Could not open Telegizer. Please close and reopen the app.'}
      </Typography>
    </Box>
  );
}

function NoWebAppScreen() {
  return (
    <Box sx={{ p: { xs: 2, md: 3 }, textAlign: 'center' }}>
      <Alert severity="info" sx={{ textAlign: 'left', mb: 3 }}>
        Open this page inside Telegram — it's a Telegram Mini App.
      </Alert>
      <Button variant="contained" href="https://telegizer.com" startIcon={<OpenInNew />}>
        Open Telegizer website
      </Button>
    </Box>
  );
}

// ── Group item ────────────────────────────────────────────────────────────────

function GroupItem({ group, onClick }) {
  const { haptic, tg } = useTelegram();
  const handle = () => {
    haptic.impact('light');
    const url = `https://telegizer.com/groups/${group.telegram_group_id}`;
    if (tg?.openLink) {
      try { tg.openLink(url); return; } catch {}
    }
    if (onClick) onClick();
  };
  return (
    <ListItemButton onClick={handle} sx={{ borderRadius: 2, mb: 0.5 }}>
      <ListItemAvatar>
        <Avatar sx={{ bgcolor: 'primary.main', width: 38, height: 38, fontSize: '0.85rem' }}>
          {group.name?.[0]?.toUpperCase() || 'G'}
        </Avatar>
      </ListItemAvatar>
      <ListItemText
        primary={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" fontWeight={600} noWrap>{group.name}</Typography>
            <Chip
              label={group.bot_status || 'unknown'}
              color={group.bot_status === 'active' ? 'success' : 'warning'}
              size="small"
              sx={{ height: 16, fontSize: '0.6rem' }}
            />
          </Box>
        }
        secondary={group.member_count ? `${group.member_count.toLocaleString()} members` : null}
        secondaryTypographyProps={{ fontSize: '0.72rem' }}
      />
    </ListItemButton>
  );
}

// ── Onboarding checklist ──────────────────────────────────────────────────────

function OnboardingChecklist({ groups, emailLinked }) {
  const hasGroup = groups.length > 0;
  const hasActive = groups.some(g => g.bot_status === 'active');

  const steps = [
    { label: 'Connected to Telegizer', done: true },
    { label: 'Add a group', done: hasGroup },
    { label: 'Bot is active in a group', done: hasActive },
    { label: 'Protect your account', done: emailLinked },
  ];

  const allDone = steps.every(s => s.done);
  if (allDone) return null;

  return (
    <Card sx={{ mb: 2, border: '1px solid', borderColor: 'primary.main', bgcolor: 'rgba(37,99,235,0.06)' }}>
      <CardContent sx={{ p: 2 }}>
        <Typography variant="subtitle2" fontWeight={700} mb={1.5}>
          Getting started
        </Typography>
        {steps.map((step, i) => (
          <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
            <CheckCircle
              fontSize="small"
              sx={{ color: step.done ? 'success.main' : 'text.disabled', flexShrink: 0 }}
            />
            <Typography
              variant="body2"
              sx={{ textDecoration: step.done ? 'line-through' : 'none', color: step.done ? 'text.disabled' : 'text.primary' }}
            >
              {step.label}
            </Typography>
          </Box>
        ))}
        {!hasGroup && (
          <Button size="small" variant="outlined" href="https://telegizer.com/groups"
            target="_blank" startIcon={<OpenInNew fontSize="small" />} sx={{ mt: 1 }}>
            Add a group
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// ── Protect account banner ────────────────────────────────────────────────────

function ProtectAccountBanner({ onOpen }) {
  return (
    <Card sx={{
      mb: 2,
      border: '1px solid',
      borderColor: 'warning.main',
      bgcolor: 'rgba(245,158,11,0.06)',
    }}>
      <CardContent sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
          <Shield sx={{ color: 'warning.main', mt: 0.25, flexShrink: 0 }} />
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2" fontWeight={700} mb={0.5}>
              Protect your account
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={1.5}>
              Add an email and password so you can recover your account if you ever lose access to Telegram.
            </Typography>
            <Button
              size="small"
              variant="outlined"
              color="warning"
              onClick={onOpen}
              startIcon={<Shield fontSize="small" />}
            >
              Add email &amp; password
            </Button>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Home tab ──────────────────────────────────────────────────────────────────

function HomeTab({ onOpenEmailFlow }) {
  const { tgUser, appUser, groups, emailLinked, haptic, tg } = useTelegram();
  const openOnWeb = (path) => {
    const url = `https://telegizer.com${path}`;
    if (tg?.openLink) { try { tg.openLink(url); return; } catch {} }
    window.open(url, '_blank', 'noopener');
  };

  const plan = appUser?.subscription_tier || 'free';
  const planColor = plan === 'enterprise' ? 'secondary' : plan === 'pro' ? 'primary' : 'default';

  // Display name: prefer Telegram first name, fall back to full_name, then username
  const displayFirst =
    tgUser?.first_name ||
    appUser?.full_name?.split(' ')[0] ||
    (appUser?.telegram_username ? `@${appUser.telegram_username}` : 'there');

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2.5, pt: 1 }}>
        <TelegizerLogo size="sm" variant="icon" />
        <Box sx={{ flex: 1 }}>
          <Typography fontWeight={700} fontSize="0.95rem">
            Hey, {displayFirst} 👋
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {appUser?.email
              ? appUser.email
              : appUser?.telegram_username
              ? `@${appUser.telegram_username}`
              : 'Telegram user'}
          </Typography>
        </Box>
        <Chip label={plan.charAt(0).toUpperCase() + plan.slice(1)} color={planColor}
          size="small" sx={{ fontSize: '0.65rem' }} />
      </Box>

      {/* Protect account banner — shown until email is linked */}
      {!emailLinked && <ProtectAccountBanner onOpen={onOpenEmailFlow} />}

      {/* Onboarding checklist — hides when all steps complete */}
      <OnboardingChecklist groups={groups} emailLinked={emailLinked} />

      {/* Quick stats */}
      <Stack direction="row" spacing={1.5} mb={2.5}>
        {[
          { label: 'Groups', value: groups.length },
          { label: 'Active', value: groups.filter(g => g.bot_status === 'active').length },
        ].map(s => (
          <Card key={s.label} sx={{ flex: 1 }}>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="h5" fontWeight={800} color="primary.main">{s.value}</Typography>
              <Typography variant="caption" color="text.secondary">{s.label}</Typography>
            </CardContent>
          </Card>
        ))}
        <Card sx={{ flex: 1, cursor: 'pointer' }}
          onClick={() => { haptic.impact('light'); openOnWeb('/workspace'); }}>
          <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
            <Bolt sx={{ fontSize: 22, color: 'primary.main' }} />
            <Typography variant="caption" color="text.secondary" display="block">Workspace</Typography>
          </CardContent>
        </Card>
      </Stack>

      {/* Groups list */}
      <Card>
        <CardContent sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <Groups fontSize="small" color="primary" />
            <Typography variant="subtitle2" fontWeight={700}>Your Groups</Typography>
          </Box>
          {groups.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 3 }}>
              <Typography variant="body2" color="text.secondary" mb={1.5}>No groups connected yet.</Typography>
              <Button size="small" variant="outlined" startIcon={<OpenInNew fontSize="small" />}
                href="https://telegizer.com/groups" target="_blank">
                Add a group on the website
              </Button>
            </Box>
          ) : (
            <List dense disablePadding>
              {groups.map(g => (
                <GroupItem key={g.telegram_group_id} group={g} />
              ))}
            </List>
          )}
        </CardContent>
      </Card>

      <Divider sx={{ my: 2.5 }} />
      <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button size="small" variant="text" endIcon={<OpenInNew fontSize="small" />}
          href="https://telegizer.com/dashboard" target="_blank" sx={{ fontSize: '0.72rem' }}>
          Full Dashboard
        </Button>
      </Box>
    </Box>
  );
}

// ── Main (tab shell) ──────────────────────────────────────────────────────────

export default function MiniApp() {
  const { status, authError, haptic, tg } = useTelegram();
  const [tab, setTab] = useState(0);
  const [emailFlowOpen, setEmailFlowOpen] = useState(false);

  // Wire Telegram system BackButton: visible on any non-Home tab, returns to Home.
  useEffect(() => {
    const btn = tg?.BackButton;
    if (!btn) return;
    if (tab === 0) { try { btn.hide(); } catch {} return; }
    const handler = () => setTab(0);
    try { btn.show(); btn.onClick(handler); } catch {}
    return () => {
      try { btn.offClick(handler); btn.hide(); } catch {}
    };
  }, [tg, tab]);

  if (status === 'loading') return <LoadingScreen />;
  if (status === 'no_webapp' || status === 'no_init_data') return <NoWebAppScreen />;
  if (status === 'error') return <ErrorScreen message={authError} />;

  const tabs = [
    { label: 'Home', icon: <Groups /> },
    { label: 'Referrals', icon: <CardGiftcard /> },
    { label: 'Setup', icon: <Settings /> },
  ];

  return (
    <Box sx={{ maxWidth: 480, mx: 'auto', px: 2, pt: 1, pb: 'calc(64px + env(safe-area-inset-bottom, 0px))' }}>
      {tab === 0 && <HomeTab onOpenEmailFlow={() => setEmailFlowOpen(true)} />}
      {tab === 1 && <MiniAppReferrals />}
      {tab === 2 && <MiniAppSetup />}

      {/* Email linking modal */}
      <EmailLinkFlow
        open={emailFlowOpen}
        onClose={() => setEmailFlowOpen(false)}
      />

      {/* Bottom navigation */}
      <Paper
        elevation={3}
        sx={{
          position: 'fixed', bottom: 0, left: 0, right: 0,
          pb: 'env(safe-area-inset-bottom, 0px)',
          zIndex: 100,
        }}
      >
        <BottomNavigation
          value={tab}
          onChange={(_, v) => { haptic.selection(); setTab(v); }}
          showLabels
          sx={{ bgcolor: 'background.paper' }}
        >
          {tabs.map((t) => (
            <BottomNavigationAction key={t.label} label={t.label} icon={t.icon}
              sx={{ '&.Mui-selected': { color: 'primary.main' }, color: 'text.secondary', fontSize: '0.7rem' }}
            />
          ))}
        </BottomNavigation>
      </Paper>
    </Box>
  );
}
