import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Chip,
  Alert, CircularProgress, Divider, InputAdornment, IconButton, Tooltip,
} from '@mui/material';
import {
  SmartToy, CheckCircle, ErrorOutline, Visibility, VisibilityOff,
  Delete, Add, Refresh, OpenInNew, ContentCopy,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { assistantBot as assistantBotApi, assistant } from '../services/api';
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

// ── Telegizer Official Bot card (available to all plans) ──────────────────────

function TelegizerBotCard({ botUsername }) {
  const [copied, setCopied] = useState(false);
  const dmLink = botUsername ? `https://t.me/${botUsername}` : null;
  const groupLink = botUsername ? `https://t.me/${botUsername}?startgroup=true` : null;

  const copyDmLink = () => {
    if (!dmLink) return;
    navigator.clipboard.writeText(dmLink).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Card
      variant="outlined"
      sx={{ mb: 3, borderColor: 'primary.main', bgcolor: 'rgba(37,99,235,0.04)', position: 'relative' }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SmartToy color="primary" fontSize="small" />
            <Typography fontWeight={700} fontSize="0.95rem">Telegizer Assistant</Typography>
            <Chip label="Ready to use" size="small" color="success" sx={{ height: 18, fontSize: '0.62rem' }} />
          </Box>
          <Chip label="Free & Pro" size="small" sx={{ height: 18, fontSize: '0.62rem', bgcolor: 'action.hover' }} />
        </Box>

        <Typography fontSize="0.83rem" color="text.secondary" mb={0.5}>
          {botUsername ? `@${botUsername}` : 'Official Telegizer bot'}
        </Typography>
        <Typography fontSize="0.82rem" color="text.secondary" mb={2}>
          The official Telegizer bot is pre-configured and ready to use — no setup required.
          DM it or add it to any group to use <strong>/remind</strong>, <strong>/note</strong>, <strong>/task</strong>, and <strong>/summary</strong> instantly.
        </Typography>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {dmLink && (
            <Button
              size="small"
              variant="contained"
              startIcon={<OpenInNew sx={{ fontSize: 14 }} />}
              href={dmLink}
              target="_blank"
              rel="noopener noreferrer"
            >
              Message Bot
            </Button>
          )}
          {groupLink && (
            <Button
              size="small"
              variant="outlined"
              startIcon={<OpenInNew sx={{ fontSize: 14 }} />}
              href={groupLink}
              target="_blank"
              rel="noopener noreferrer"
            >
              Add to Group
            </Button>
          )}
          {dmLink && (
            <Tooltip title={copied ? 'Copied!' : 'Copy bot link'}>
              <Button
                size="small"
                variant="text"
                startIcon={<ContentCopy sx={{ fontSize: 14 }} />}
                onClick={copyDmLink}
                sx={{ color: 'text.secondary' }}
              >
                {copied ? 'Copied!' : 'Copy Link'}
              </Button>
            </Tooltip>
          )}
        </Box>

        <Divider sx={{ my: 2 }} />

        <Typography fontSize="0.75rem" color="text.disabled">
          Commands: &nbsp;
          {['/remind 30m Buy coffee', '/note Decision: launch Friday', '/task Write the spec', '/summary'].map(c => (
            <Box key={c} component="span"
              sx={{ fontFamily: 'monospace', bgcolor: 'action.hover', px: 0.6, py: 0.1, borderRadius: 0.5, mr: 0.5 }}>
              {c}
            </Box>
          ))}
        </Typography>
      </CardContent>
    </Card>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AssistantBotSettings() {
  useNavigate();
  const user = _getUser();
  const plan = user.subscription_tier || 'free';

  const [bot, setBot] = useState(undefined);
  const [platformBotUsername, setPlatformBotUsername] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const [tokenInput, setTokenInput] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toggling, setToggling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [botRes, hubRes] = await Promise.all([
        assistantBotApi.get(),
        assistant.hubSummary().catch(() => ({ data: {} })),
      ]);
      setBot(botRes.data.bot || null);
      setPlatformBotUsername(hubRes.data.bot_username || '');
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
    if (!window.confirm('Remove your custom bot? The Telegram webhook will be deleted. You can reconnect any time.')) return;
    clearMessages();
    setDeleting(true);
    try {
      await assistantBotApi.remove();
      setBot(null);
      setSuccess('Custom bot removed.');
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to remove bot.');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ p: { xs: 2, md: 3 }, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
        <CircularProgress size={32} />
      </Box>
    );
  }

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 700, mx: 'auto' }}>

      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <SmartToy sx={{ fontSize: 26, color: 'primary.main' }} />
        <Typography variant="h5" fontWeight={700}>Assistant Bot</Typography>
        {bot && <StatusBadge bot={bot} />}
      </Box>
      <Typography color="text.secondary" fontSize="0.88rem" mb={3}>
        Use the official Telegizer bot instantly, or connect your own for full custom branding.
      </Typography>

      {error && <Alert severity="error" onClose={clearMessages} sx={{ mb: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" onClose={clearMessages} sx={{ mb: 2 }}>{success}</Alert>}

      {/* ── Option 1: Telegizer official bot (all plans) ── */}
      <Typography variant="overline" color="text.disabled" fontSize="0.65rem" letterSpacing="0.1em">
        Option 1 — Use the official bot
      </Typography>
      <Box sx={{ mt: 0.5 }}>
        <TelegizerBotCard botUsername={platformBotUsername} />
      </Box>

      {/* ── Option 2: Custom bot (Pro) ── */}
      <Typography variant="overline" color="text.disabled" fontSize="0.65rem" letterSpacing="0.1em">
        Option 2 — Connect your own bot
      </Typography>

      <Box sx={{ mt: 0.5 }}>
        <PlanGate plan="pro" userTier={plan} feature="Custom Assistant Bot">

          {/* No custom bot connected */}
          {!bot && (
            <Card variant="outlined">
              <CardContent>
                <Typography fontWeight={600} mb={0.5}>Connect a Custom Telegram Bot</Typography>
                <Typography fontSize="0.84rem" color="text.secondary" mb={2}>
                  Create a bot via <strong>@BotFather</strong> on Telegram, copy the token, and paste it below.
                  We'll register a webhook automatically — your bot will respond to the same commands under your own brand.
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
                  Token is stored encrypted and never exposed via the API.
                </Typography>
              </CardContent>
            </Card>
          )}

          {/* Custom bot connected */}
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
                    <Tooltip title="Refresh">
                      <IconButton size="small" onClick={load}><Refresh fontSize="small" /></IconButton>
                    </Tooltip>
                  </Box>
                  <Typography fontSize="0.78rem" color="text.secondary" mb={0.5}>
                    Connected {new Date(bot.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                  </Typography>
                  <Typography fontSize="0.78rem" color="text.secondary">
                    Webhook active · Commands: /remind · /note · /task · /summary
                  </Typography>
                </CardContent>
              </Card>

              {/* Update token */}
              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                  <Typography fontWeight={600} mb={0.5} fontSize="0.9rem">Replace Bot Token</Typography>
                  <Typography fontSize="0.82rem" color="text.secondary" mb={1.5}>
                    Use this if you revoked and regenerated the token via @BotFather. The old webhook will be removed and a new one registered.
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
              <Card variant="outlined" sx={{ borderColor: 'divider', opacity: 0.9 }}>
                <CardContent>
                  <Typography fontWeight={600} fontSize="0.9rem" mb={1.5} color="error.main">Danger Zone</Typography>
                  <Divider sx={{ mb: 1.5 }} />
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
                    <Box>
                      <Typography fontSize="0.84rem" fontWeight={500}>
                        {bot.is_active ? 'Deactivate bot' : 'Reactivate bot'}
                      </Typography>
                      <Typography fontSize="0.75rem" color="text.secondary">
                        {bot.is_active
                          ? 'Removes the Telegram webhook — bot stops responding.'
                          : 'Re-registers the webhook — bot resumes responding.'}
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
                      <Typography fontSize="0.84rem" fontWeight={500}>Remove custom bot</Typography>
                      <Typography fontSize="0.75rem" color="text.secondary">
                        Deletes the connection and webhook. Notes and tasks are kept.
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
    </Box>
  );
}
