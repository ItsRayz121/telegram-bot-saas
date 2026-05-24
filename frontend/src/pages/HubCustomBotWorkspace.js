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
  MenuItem, Select, FormControl, InputLabel, Snackbar,
  Switch, List, ListItem, ListItemText, ListItemSecondaryAction,
} from '@mui/material';
import { ArrowBack, SmartToy, Groups, Delete, Save, AutoAwesome } from '@mui/icons-material';
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

  // Reply settings
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [saveLoading, setSaveLoading] = useState(false);
  const [snack, setSnack] = useState(null);
  const [form, setForm] = useState({
    ai_personality_note: '',
    response_language: 'en',
    reply_sensitivity: 'medium',
    escalation_contact: '',
    tone: 'friendly',
  });

  // Knowledge source groups
  const [kcGroups, setKcGroups] = useState([]);
  const [kcLoading, setKcLoading] = useState(true);
  const [kcTogglingId, setKcTogglingId] = useState(null);

  useEffect(() => {
    hub.getBotSettings(bot.id)
      .then(r => {
        const s = r.data?.settings || {};
        setForm({
          ai_personality_note: s.ai_personality_note || '',
          response_language: s.response_language || 'en',
          reply_sensitivity: s.reply_sensitivity || 'medium',
          escalation_contact: s.escalation_contact ? String(s.escalation_contact) : '',
          tone: s.tone || 'friendly',
        });
      })
      .catch(() => {})
      .finally(() => setSettingsLoading(false));
  }, [bot.id]);

  useEffect(() => {
    hub.listBotGroups(bot.id)
      .then(r => setKcGroups(r.data?.groups || []))
      .catch(() => {})
      .finally(() => setKcLoading(false));
  }, [bot.id]);

  const handleKcToggle = async (group) => {
    setKcTogglingId(group.id);
    try {
      const r = await hub.updateBotGroup(bot.id, group.id, {
        is_knowledge_channel: !group.is_knowledge_channel,
      });
      const updated = r.data?.group;
      setKcGroups(prev => prev.map(g => g.id === group.id ? { ...g, ...(updated || { is_knowledge_channel: !group.is_knowledge_channel }) } : g));
    } catch {
      setSnack('Failed to update group setting.');
    }
    setKcTogglingId(null);
  };

  const handleSave = async () => {
    setSaveLoading(true);
    try {
      const payload = {
        ...form,
        escalation_contact: form.escalation_contact ? Number(form.escalation_contact) : null,
      };
      await hub.updateBotSettings(bot.id, payload);
      setSnack('Settings saved.');
    } catch (e) {
      setSnack(e?.response?.data?.error || 'Failed to save settings.');
    }
    setSaveLoading(false);
  };

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

      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Groups sx={{ fontSize: 18, mt: 0.25 }} />
          <span>
            This bot can be added to Telegram groups. Go to <strong>Groups</strong> tab to manage group-level settings and analytics.
          </span>
        </Box>
      </Typography>

      <Divider sx={{ my: 2 }} />

      {/* Community Reply Settings */}
      <Typography variant="subtitle2" fontWeight={600} gutterBottom sx={{ mt: 2 }}>
        Community Reply Settings
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={2}>
        Controls how this bot replies when @mentioned in groups.
      </Typography>

      {settingsLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
          <CircularProgress size={24} />
        </Box>
      ) : (
        <Card variant="outlined" sx={{ mb: 3 }}>
          <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              label="Personality note"
              placeholder="e.g. Always be concise and reply in bullet points."
              size="small"
              fullWidth
              multiline
              rows={2}
              inputProps={{ maxLength: 200 }}
              value={form.ai_personality_note}
              onChange={e => setForm(f => ({ ...f, ai_personality_note: e.target.value }))}
              helperText={`${form.ai_personality_note.length}/200 — Appended to the AI system prompt.`}
            />

            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <FormControl size="small" sx={{ minWidth: 160 }}>
                <InputLabel>Tone</InputLabel>
                <Select
                  label="Tone"
                  value={form.tone}
                  onChange={e => setForm(f => ({ ...f, tone: e.target.value }))}
                >
                  <MenuItem value="friendly">Friendly</MenuItem>
                  <MenuItem value="professional">Professional</MenuItem>
                  <MenuItem value="neutral">Neutral</MenuItem>
                </Select>
              </FormControl>

              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel>Reply sensitivity</InputLabel>
                <Select
                  label="Reply sensitivity"
                  value={form.reply_sensitivity}
                  onChange={e => setForm(f => ({ ...f, reply_sensitivity: e.target.value }))}
                >
                  <MenuItem value="low">Low — reply to everything</MenuItem>
                  <MenuItem value="medium">Medium — default</MenuItem>
                  <MenuItem value="high">High — ask for detail often</MenuItem>
                </Select>
              </FormControl>
            </Box>

            <TextField
              label="Escalation contact (Telegram user ID)"
              placeholder="e.g. 123456789"
              size="small"
              sx={{ maxWidth: 280 }}
              value={form.escalation_contact}
              onChange={e => setForm(f => ({ ...f, escalation_contact: e.target.value.replace(/\D/g, '') }))}
              helperText="When the bot can't answer, it DMs this admin."
            />

            <Box>
              <Button
                variant="contained"
                size="small"
                startIcon={saveLoading ? <CircularProgress size={13} /> : <Save />}
                onClick={handleSave}
                disabled={saveLoading}
              >
                Save settings
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}

      <Divider sx={{ my: 2 }} />

      {/* Knowledge Source */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 2, mb: 0.5 }}>
        <AutoAwesome sx={{ fontSize: 16, color: 'primary.main' }} />
        <Typography variant="subtitle2" fontWeight={600}>Knowledge Source</Typography>
      </Box>
      <Typography variant="caption" color="text.secondary" display="block" mb={2}>
        Mark a group as a knowledge channel. Every message posted there is automatically
        parsed by AI and saved as a knowledge card — no manual entry needed.
      </Typography>

      <Card variant="outlined" sx={{ mb: 3 }}>
        {kcLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
            <CircularProgress size={20} />
          </Box>
        ) : kcGroups.length === 0 ? (
          <CardContent>
            <Typography variant="body2" color="text.secondary">
              No groups connected yet. Add this bot to a Telegram group first.
            </Typography>
          </CardContent>
        ) : (
          <List dense disablePadding>
            {kcGroups.map((group, idx) => (
              <ListItem
                key={group.id}
                divider={idx < kcGroups.length - 1}
                sx={{ py: 1 }}
              >
                <ListItemText
                  primary={group.group_name || `Group ${group.telegram_group_id}`}
                  secondary={group.is_knowledge_channel ? 'Auto-capturing messages → knowledge cards' : 'Not capturing'}
                  primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                  secondaryTypographyProps={{ variant: 'caption' }}
                />
                <ListItemSecondaryAction>
                  {kcTogglingId === group.id
                    ? <CircularProgress size={18} />
                    : (
                      <Switch
                        size="small"
                        checked={!!group.is_knowledge_channel}
                        onChange={() => handleKcToggle(group)}
                        color="primary"
                      />
                    )
                  }
                </ListItemSecondaryAction>
              </ListItem>
            ))}
          </List>
        )}
      </Card>

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

      <Snackbar
        open={!!snack}
        autoHideDuration={3000}
        onClose={() => setSnack(null)}
        message={snack}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </Box>
  );
}
