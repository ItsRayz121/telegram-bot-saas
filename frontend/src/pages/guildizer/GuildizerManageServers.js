import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Container, Typography, CircularProgress, Alert, Button,
} from '@mui/material';
import { Groups, ArrowBack } from '@mui/icons-material';
import guildizerApi from '../../services/guildizerApi';
import { ManageServersView, PermissionsDialog, UnlinkDialog } from './GuildizerServers';

// Dedicated "Manage Servers" page — the linked-server cards on their own route
// (/guildizer/servers), reached from the hero card's "Manage Servers" button.
// Mirrors the Telegram dashboard's "Manage Groups" → /groups behaviour, instead
// of swapping the content inside the main Discord page.
export default function GuildizerManageServers() {
  const navigate = useNavigate();
  const [state, setState] = useState({ loading: true, guilds: [], inviteUrl: null, error: null });
  const [refreshing, setRefreshing] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [permsModalGuild, setPermsModalGuild] = useState(null);
  const [unlinkTarget, setUnlinkTarget] = useState(null);

  const load = async ({ silent = false } = {}) => {
    if (silent) setRefreshing(true);
    try {
      await guildizerApi.get('/auth/me'); // 401 → not connected
      const { data } = await guildizerApi.get('/api/guilds');
      setState({ loading: false, guilds: data.guilds || [], inviteUrl: data.invite_url, error: null });
    } catch (e) {
      // Not connected → there's nothing to manage; send the user back to connect.
      if (e?.response?.status === 401) { navigate('/guildizer', { replace: true }); return; }
      setState((s) => ({ ...s, loading: false, error: 'Failed to load your Discord servers.' }));
    } finally {
      setRefreshing(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const visibleGuilds = useMemo(
    () => (state.guilds || []).filter((g) => g.bot_present),
    [state.guilds],
  );

  if (state.loading) {
    return <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 320 }}><CircularProgress /></Box>;
  }

  return (
    <Container maxWidth="xl" sx={{ py: 2.5 }}>
      {/* Breadcrumb */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
        <Button size="small" variant="text" onClick={() => navigate('/dashboard')}
          sx={{ fontSize: '0.75rem', px: 1, py: 0.25, minWidth: 0, color: 'text.secondary' }}>
          Dashboard
        </Button>
        <Box component="span" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>/</Box>
        <Button size="small" variant="text" onClick={() => navigate('/guildizer')}
          sx={{ fontSize: '0.75rem', px: 1, py: 0.25, minWidth: 0, color: 'text.secondary' }}>
          Discord
        </Button>
        <Box component="span" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>/</Box>
        <Box component="span" sx={{ color: 'text.secondary', fontSize: '0.75rem', px: 1 }}>Manage Servers</Box>
      </Box>

      {/* Page header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <Groups color="primary" />
        <Typography variant="h5" fontWeight={800}>Manage Servers</Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Servers where Guildizer is installed — open <b>Settings</b> to configure each one.
      </Typography>

      {state.error && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={<Button size="small" startIcon={<ArrowBack />} onClick={() => navigate('/guildizer')}>Back</Button>}
        >
          {state.error}
        </Alert>
      )}

      {!state.error && (
        <ManageServersView
          visibleGuilds={visibleGuilds}
          inviteUrl={state.inviteUrl}
          refreshing={refreshing}
          guideOpen={guideOpen}
          onToggleGuide={() => setGuideOpen((o) => !o)}
          onRefresh={() => load({ silent: true })}
          onBack={() => navigate('/guildizer')}
          navigate={navigate}
          onViewPerms={setPermsModalGuild}
          onUnlink={setUnlinkTarget}
        />
      )}

      <PermissionsDialog guild={permsModalGuild} onClose={() => setPermsModalGuild(null)} />
      <UnlinkDialog guild={unlinkTarget} onClose={() => setUnlinkTarget(null)} />
    </Container>
  );
}
