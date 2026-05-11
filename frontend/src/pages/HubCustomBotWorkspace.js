/**
 * /hub/bots/:botId/:tab — Custom bot workspace.
 * Uses the same 8 tabs as the official bot workspace, with all data scoped
 * to this bot's ID. The Settings tab shows bot-specific danger zone instead
 * of the global official-bot settings.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Box, Tabs, Tab, Typography, Chip, Button, CircularProgress,
  Card, CardContent, Alert, Divider, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, Avatar,
} from '@mui/material';
import { ArrowBack, SmartToy, Groups, Delete } from '@mui/icons-material';
import { hub } from '../services/api';
import { PALETTE } from '../theme';
import { TabContent } from './HubWorkspace';
import { getTabsForBot } from '../config/assistantHubRegistry';

// Custom bots show all non-officialOnly tabs — derived from the shared registry.
const TABS = getTabsForBot(false).map(t => ({ label: t.label, value: t.key }));

export default function HubCustomBotWorkspace() {
  const navigate = useNavigate();
  const { botId, tab = 'overview' } = useParams();
  const [bot, setBot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [groups, setGroups] = useState([]);

  const loadBot = useCallback(() => {
    setLoading(true);
    hub.listBots()
      .then(r => {
        const found = (r.data?.bots || []).find(b => String(b.id) === String(botId) && b.bot_type === 'custom');
        if (found) setBot(found);
        else setNotFound(true);
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [botId]);

  const loadGroups = useCallback(() => {
    hub.listBotGroups(botId)
      .then(r => setGroups(r.data?.groups || []))
      .catch(() => {});
  }, [botId]);

  useEffect(() => { loadBot(); }, [loadBot]);
  useEffect(() => { loadGroups(); }, [loadGroups]);

  const handleTabChange = (_, newTab) => navigate(`/hub/bots/${botId}/${newTab}`);
  const handleDeleted = () => navigate('/hub');

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (notFound) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" action={
          <Button size="small" onClick={() => navigate('/hub')}>Back to Hub</Button>
        }>
          Bot not found or you don't have access to it.
        </Alert>
      </Box>
    );
  }

  const activeTab = TABS.find(t => t.value === tab) ? tab : 'overview';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <Box sx={{ px: { xs: 2, sm: 3 }, pt: 2, pb: 0, borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Button size="small" startIcon={<ArrowBack sx={{ fontSize: 15 }} />} onClick={() => navigate('/hub')}
            sx={{ minWidth: 0, color: 'text.secondary', fontWeight: 400, px: 0.5 }}>Hub</Button>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1, minWidth: 0 }}>
            <Avatar sx={{ width: 24, height: 24, bgcolor: PALETTE.blue + '33', flexShrink: 0 }}>
              <SmartToy sx={{ fontSize: 14, color: PALETTE.blue }} />
            </Avatar>
            <Typography variant="subtitle1" fontWeight={700} noWrap>
              {bot.display_name || bot.telegram_bot_username || `Bot #${bot.id}`}
            </Typography>
            <Chip label="Active" size="small" sx={{ bgcolor: 'success.main', color: '#fff', height: 18, fontSize: '0.65rem', flexShrink: 0 }} />
            <Chip label="Custom Bot" size="small" variant="outlined" sx={{ height: 18, fontSize: '0.65rem', flexShrink: 0 }} />
            {bot.telegram_bot_username && (
              <Typography variant="caption" color="text.secondary" noWrap sx={{ flexShrink: 0 }}>
                @{bot.telegram_bot_username} · {groups.length} groups
              </Typography>
            )}
          </Box>
        </Box>
        <Tabs value={activeTab} onChange={handleTabChange}
          variant="scrollable" scrollButtons="auto"
          sx={{ minHeight: 38, '& .MuiTab-root': { minHeight: 38, fontSize: '0.8rem', py: 0, px: 1.5, textTransform: 'none' } }}>
          {TABS.map(t => <Tab key={t.value} label={t.label} value={t.value} />)}
        </Tabs>
      </Box>

      {/* Tab content */}
      <Box sx={{ flex: 1, overflow: 'auto', p: { xs: 2, sm: 3 } }}>
        {activeTab === 'settings'
          ? <CustomBotSettings bot={bot} onDeleted={handleDeleted} />
          : <TabContent tab={activeTab} botData={bot} groups={groups} setGroups={setGroups} botId={botId} />
        }
      </Box>
    </Box>
  );
}


function CustomBotSettings({ bot, onDeleted }) {
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const handleDelete = async () => {
    if (deleteConfirm !== bot.display_name) return;
    setDeleteLoading(true); setDeleteError(null);
    try {
      await hub.deleteBot(bot.id);
      setDeleteOpen(false);
      onDeleted();
    } catch (e) {
      setDeleteError(e?.response?.data?.error || 'Failed to delete bot.');
    }
    setDeleteLoading(false);
  };

  return (
    <Box sx={{ maxWidth: 600 }}>
      <Typography variant="subtitle2" fontWeight={600} gutterBottom>Bot Details</Typography>
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="body2" color="text.secondary" mb={1}>
            <strong>Name:</strong> {bot.display_name || '—'}
          </Typography>
          <Typography variant="body2" color="text.secondary" mb={1}>
            <strong>Username:</strong> @{bot.telegram_bot_username || '—'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            <strong>Groups:</strong> {bot.group_count ?? 0} connected
          </Typography>
        </CardContent>
      </Card>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Groups sx={{ fontSize: 18, mt: 0.25 }} />
          <span>
            This bot can be added to Telegram groups. Go to <strong>Groups</strong> in the sidebar to manage group-level settings and analytics.
          </span>
        </Box>
      </Typography>

      <Divider sx={{ my: 3 }} />

      <Typography variant="subtitle2" color="error.main" fontWeight={600} gutterBottom>Danger Zone</Typography>
      <Card variant="outlined" sx={{ borderColor: 'error.main', borderWidth: 1 }}>
        <CardContent>
          <Typography variant="body2" fontWeight={500} gutterBottom>Delete This Bot</Typography>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Permanently removes the bot integration, stops the webhook, and disconnects all groups.
            This cannot be undone.
          </Typography>
          <Button
            variant="outlined"
            color="error"
            size="small"
            startIcon={<Delete />}
            onClick={() => { setDeleteOpen(true); setDeleteConfirm(''); setDeleteError(null); }}
          >
            Delete Bot
          </Button>
        </CardContent>
      </Card>

      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete {bot.display_name}?</DialogTitle>
        <DialogContent>
          {deleteError && <Alert severity="error" sx={{ mb: 2 }}>{deleteError}</Alert>}
          <Typography variant="body2" color="text.secondary" mb={2}>
            This permanently removes the bot integration, stops the webhook, and cannot be undone.
            The bot will stop responding in all linked groups.
          </Typography>
          <TextField
            label={`Type "${bot.display_name}" to confirm`}
            size="small" fullWidth
            value={deleteConfirm}
            onChange={e => setDeleteConfirm(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleteOpen(false)} size="small" color="inherit">Cancel</Button>
          <Button onClick={handleDelete} variant="contained" color="error" size="small"
            disabled={deleteConfirm !== bot.display_name || deleteLoading}>
            {deleteLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}Delete Bot
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
