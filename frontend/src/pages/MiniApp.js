import React, { useState } from 'react';
import {
  Box, Typography, Card, CardContent, CircularProgress, Button,
  Avatar, Chip, List, ListItemButton, ListItemText, ListItemAvatar,
  Alert, Divider, Stack,
} from '@mui/material';
import {
  Groups, OpenInNew, Link, CheckCircle, ErrorOutline, Bolt,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useTelegram } from '../contexts/TelegramContext';
import TelegizerLogo from '../components/TelegizerLogo';

// ── Status screens ────────────────────────────────────────────────────────────

function LoadingScreen() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: 2 }}>
      <CircularProgress size={36} />
      <Typography color="text.secondary" variant="body2">Authenticating…</Typography>
    </Box>
  );
}

function NotLinkedScreen() {
  return (
    <Box sx={{ p: 3, textAlign: 'center' }}>
      <Link sx={{ fontSize: 56, color: 'warning.main', mb: 2 }} />
      <Typography variant="h6" fontWeight={700} gutterBottom>
        Connect your Telegram account
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Your Telegram account isn't linked to a Telegizer account yet.
        Open the website, go to Settings, and link your Telegram.
      </Typography>
      <Button
        variant="contained"
        startIcon={<OpenInNew />}
        href="https://telegizer.xyz/settings"
        target="_blank"
        rel="noopener noreferrer"
      >
        Open Telegizer Settings
      </Button>
    </Box>
  );
}

function ErrorScreen() {
  return (
    <Box sx={{ p: 3, textAlign: 'center' }}>
      <ErrorOutline sx={{ fontSize: 56, color: 'error.main', mb: 2 }} />
      <Typography variant="h6" fontWeight={700} gutterBottom>Something went wrong</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Could not authenticate with Telegizer. Please close and reopen the app.
      </Typography>
    </Box>
  );
}

function NoWebAppScreen() {
  return (
    <Box sx={{ p: 3, textAlign: 'center' }}>
      <Alert severity="info" sx={{ textAlign: 'left', mb: 3 }}>
        Open this page inside Telegram — it's designed to run as a Telegram Mini App.
      </Alert>
      <Button variant="contained" href="https://telegizer.xyz" startIcon={<OpenInNew />}>
        Open Telegizer website
      </Button>
    </Box>
  );
}

// ── Group item ────────────────────────────────────────────────────────────────

function GroupItem({ group, onClick }) {
  const statusColor = group.bot_status === 'active' ? 'success' : 'warning';
  return (
    <ListItemButton onClick={onClick} sx={{ borderRadius: 2, mb: 0.5 }}>
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
              color={statusColor}
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

// ── Main ─────────────────────────────────────────────────────────────────────

export default function MiniApp() {
  const navigate = useNavigate();
  const { tgUser, appUser, groups, status } = useTelegram();

  if (status === 'loading') return <LoadingScreen />;
  if (status === 'not_linked') return <NotLinkedScreen />;
  if (status === 'no_webapp' || status === 'no_init_data') return <NoWebAppScreen />;
  if (status === 'error') return <ErrorScreen />;

  const plan = appUser?.subscription_tier || 'free';
  const planColor = plan === 'enterprise' ? 'secondary' : plan === 'pro' ? 'primary' : 'default';

  return (
    <Box sx={{ maxWidth: 480, mx: 'auto', p: 2 }}>

      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2.5, pt: 1 }}>
        <TelegizerLogo size="sm" variant="icon" />
        <Box sx={{ flex: 1 }}>
          <Typography fontWeight={700} fontSize="0.95rem">
            Hey, {tgUser?.first_name || appUser?.full_name?.split(' ')[0] || 'there'} 👋
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {appUser?.email}
          </Typography>
        </Box>
        <Chip label={plan.charAt(0).toUpperCase() + plan.slice(1)} color={planColor} size="small" sx={{ fontSize: '0.65rem' }} />
      </Box>

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
        <Card sx={{ flex: 1, cursor: 'pointer' }} onClick={() => navigate('/workspace')}>
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
              <Typography variant="body2" color="text.secondary" mb={1.5}>
                No groups connected yet.
              </Typography>
              <Button
                size="small"
                variant="outlined"
                startIcon={<OpenInNew fontSize="small" />}
                href="https://telegizer.xyz/groups"
                target="_blank"
              >
                Add a group on the website
              </Button>
            </Box>
          ) : (
            <List dense disablePadding>
              {groups.map(g => (
                <GroupItem
                  key={g.telegram_group_id}
                  group={g}
                  onClick={() => navigate(`/groups/${g.telegram_group_id}`)}
                />
              ))}
            </List>
          )}
        </CardContent>
      </Card>

      {/* Footer */}
      <Divider sx={{ my: 2.5 }} />
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="caption" color="text.disabled">Telegizer Mini App</Typography>
        <Button
          size="small"
          variant="text"
          endIcon={<OpenInNew fontSize="small" />}
          href="https://telegizer.xyz/dashboard"
          target="_blank"
          sx={{ fontSize: '0.72rem' }}
        >
          Full Dashboard
        </Button>
      </Box>
    </Box>
  );
}
