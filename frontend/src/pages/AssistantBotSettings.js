import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Chip,
  Alert, CircularProgress, Divider, InputAdornment, IconButton, Tooltip,
} from '@mui/material';
import {
  SmartToy, CheckCircle, ErrorOutline, Visibility, VisibilityOff,
  Delete, Add, Refresh,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { assistantBot as assistantBotApi } from '../services/api';
import PlanGate from '../components/PlanGate';

function _getUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

function StatusBadge({ bot }) {
  if (!bot) return <Chip label="Not connected" size="small" sx={{ bgcolor: 'action.hover' }} />;
  return bot.is_active
    ? <Chip label="Active" size="small" color="success" />
    : <Chip label="Inactive" size="small" color="default" />;
}

export default function AssistantBotSettings() {
  const navigate = useNavigate();
  const user = _getUser();
  const plan = user.subscription_tier || 'free';

  const [bot, setBot] = useState(undefined); // undefined=loading, null=none, obj=exists
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Form state
  const [tokenInput, setTokenInput] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toggling, setToggling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await assistantBotApi.get();
      setBot(data.bot || null);
    } catch {
      setError('Failed to load assistant bot settings.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const clearMessages = () => { setError(''); setSuccess(''); };

  const handleConnect = async () => {
    const token = tokenInput.trim();
    if (!token) { setError('Paste your bot token first.'); return; }
    clearMessages();
    setSaving(true);
    try {
      const { data } = await assistantBotApi.create({ bot_token: token });
      setBot(data.bot);
      setTokenInput('');
      setSuccess('Bot connected and webhook registered! Send /start to your bot in Telegram to test it.');
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to connect bot.');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateToken = async () => {
    const token = tokenInput.trim();
    if (!token) { setError('Paste your new bot token first.'); return; }
    clearMessages();
    setSaving(true);
    try {
      const { data } = await assistantBotApi.update({ bot_token: token });
      setBot(data.bot);
      setTokenInput('');
      setSuccess('Bot token updated and webhook re-registered.');
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to update bot token.');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async () => {
    clearMessages();
    setToggling(true);
    try {
      const { data } = await assistantBotApi.update({ is_active: !bot.is_active });
      setBot(data.bot);
      setSuccess(data.bot.is_active ? 'Bot activated.' : 'Bot deactivated.');
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to toggle bot status.');
    } finally {
      setToggling(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Remove your assistant bot? This will delete the Telegram webhook. You can reconnect any time.')) return;
    clearMessages();
    setDeleting(true);
    try {
      await assistantBotApi.remove();
      setBot(null);
      setSuccess('Assistant bot removed.');
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to remove bot.');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ p: 3, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
        <CircularProgress size={32} />
      </Box>
    );
  }

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 680, mx: 'auto' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <SmartToy sx={{ fontSize: 26, color: 'primary.main' }} />
        <Typography variant="h5" fontWeight={700}>Assistant Bot</Typography>
        <StatusBadge bot={bot} />
      </Box>
      <Typography color="text.secondary" fontSize="0.88rem" mb={3}>
        Connect your own Telegram bot to use as a personal assistant — set reminders, capture notes and tasks, and get AI summaries right from Telegram.
      </Typography>

      <PlanGate plan="pro" userTier={plan} feature="Assistant Bot">

        {error && <Alert severity="error" onClose={clearMessages} sx={{ mb: 2 }}>{error}</Alert>}
        {success && <Alert severity="success" onClose={clearMessages} sx={{ mb: 2 }}>{success}</Alert>}

        {/* ── No bot connected ── */}
        {!bot && (
          <Card variant="outlined">
            <CardContent>
              <Typography fontWeight={600} mb={0.5}>Connect a Telegram Bot</Typography>
              <Typography fontSize="0.84rem" color="text.secondary" mb={2}>
                Create a bot via <strong>@BotFather</strong> on Telegram, copy the token, and paste it below. We'll register a webhook automatically.
              </Typography>

              <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                <TextField
                  fullWidth
                  size="small"
                  label="Bot Token"
                  placeholder="123456789:ABCdef..."
                  value={tokenInput}
                  onChange={e => setTokenInput(e.target.value)}
                  type={showToken ? 'text' : 'password'}
                  disabled={saving}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton size="small" onClick={() => setShowToken(v => !v)}>
                          {showToken ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                />
                <Button
                  variant="contained"
                  startIcon={saving ? <CircularProgress size={14} color="inherit" /> : <Add />}
                  onClick={handleConnect}
                  disabled={saving || !tokenInput.trim()}
                  sx={{ minWidth: 120, flexShrink: 0 }}
                >
                  Connect
                </Button>
              </Box>

              <Typography fontSize="0.75rem" color="text.disabled" mt={1.5}>
                Your token is stored encrypted and never exposed via the API.
              </Typography>
            </CardContent>
          </Card>
        )}

        {/* ── Bot connected ── */}
        {bot && (
          <>
            <Card variant="outlined" sx={{ mb: 2 }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {bot.is_active
                      ? <CheckCircle color="success" fontSize="small" />
                      : <ErrorOutline color="disabled" fontSize="small" />
                    }
                    <Typography fontWeight={600}>
                      {bot.bot_name || bot.bot_username || 'Your Bot'}
                    </Typography>
                    {bot.bot_username && (
                      <Typography fontSize="0.8rem" color="text.secondary">@{bot.bot_username}</Typography>
                    )}
                  </Box>
                  <Tooltip title="Refresh status">
                    <IconButton size="small" onClick={load}><Refresh fontSize="small" /></IconButton>
                  </Tooltip>
                </Box>

                <Typography fontSize="0.78rem" color="text.secondary" mb={0.5}>
                  Connected {new Date(bot.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                </Typography>
                <Typography fontSize="0.78rem" color="text.secondary">
                  Webhook: active · Commands: /remind · /note · /task · /summary
                </Typography>
              </CardContent>
            </Card>

            {/* Update token */}
            <Card variant="outlined" sx={{ mb: 2 }}>
              <CardContent>
                <Typography fontWeight={600} mb={0.5} fontSize="0.9rem">Replace Bot Token</Typography>
                <Typography fontSize="0.82rem" color="text.secondary" mb={1.5}>
                  If you revoked and regenerated the token via @BotFather, update it here. The old webhook will be removed and a new one registered.
                </Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <TextField
                    fullWidth
                    size="small"
                    label="New Bot Token"
                    placeholder="123456789:ABCdef..."
                    value={tokenInput}
                    onChange={e => setTokenInput(e.target.value)}
                    type={showToken ? 'text' : 'password'}
                    disabled={saving}
                    InputProps={{
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton size="small" onClick={() => setShowToken(v => !v)}>
                            {showToken ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />
                  <Button
                    variant="outlined"
                    startIcon={saving ? <CircularProgress size={14} color="inherit" /> : null}
                    onClick={handleUpdateToken}
                    disabled={saving || !tokenInput.trim()}
                    sx={{ minWidth: 110, flexShrink: 0 }}
                  >
                    Update
                  </Button>
                </Box>
              </CardContent>
            </Card>

            {/* Danger zone */}
            <Card variant="outlined" sx={{ borderColor: 'error.main', opacity: 0.85 }}>
              <CardContent>
                <Typography fontWeight={600} fontSize="0.9rem" mb={1.5}>Danger Zone</Typography>
                <Divider sx={{ mb: 1.5 }} />
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
                  <Box>
                    <Typography fontSize="0.84rem" fontWeight={500}>
                      {bot.is_active ? 'Deactivate bot' : 'Reactivate bot'}
                    </Typography>
                    <Typography fontSize="0.75rem" color="text.secondary">
                      {bot.is_active ? 'Removes the Telegram webhook — bot stops responding.' : 'Re-registers the webhook — bot resumes responding.'}
                    </Typography>
                  </Box>
                  <Button
                    size="small"
                    variant="outlined"
                    color={bot.is_active ? 'warning' : 'success'}
                    onClick={handleToggleActive}
                    disabled={toggling}
                    sx={{ minWidth: 100, flexShrink: 0 }}
                  >
                    {toggling ? <CircularProgress size={14} /> : bot.is_active ? 'Deactivate' : 'Reactivate'}
                  </Button>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography fontSize="0.84rem" fontWeight={500}>Remove assistant bot</Typography>
                    <Typography fontSize="0.75rem" color="text.secondary">
                      Deletes the connection and removes the Telegram webhook. Your notes and tasks are kept.
                    </Typography>
                  </Box>
                  <Button
                    size="small"
                    variant="outlined"
                    color="error"
                    startIcon={deleting ? <CircularProgress size={14} /> : <Delete fontSize="small" />}
                    onClick={handleDelete}
                    disabled={deleting}
                    sx={{ minWidth: 100, flexShrink: 0 }}
                  >
                    Remove
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </>
        )}

      </PlanGate>
    </Box>
  );
}
