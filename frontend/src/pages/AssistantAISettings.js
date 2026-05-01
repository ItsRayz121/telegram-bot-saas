import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Divider, Button, TextField,
  Tabs, Tab, LinearProgress, Chip, CircularProgress, Alert, IconButton,
  InputAdornment, Tooltip,
} from '@mui/material';
import {
  CheckCircle, Cancel, Warning, Visibility, VisibilityOff,
  Delete, Send, Link as LinkIcon,
} from '@mui/icons-material';
import { workspaceAI, telegramAccount } from '../services/api';
import PlanGate from '../components/PlanGate';

function _getUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

const PROVIDERS = [
  { id: 'gemini',     label: 'Gemini',     defaultModel: 'gemini-2.0-flash',          needsBase: false },
  { id: 'openai',     label: 'OpenAI',     defaultModel: 'gpt-4o-mini',               needsBase: false },
  { id: 'anthropic',  label: 'Anthropic',  defaultModel: 'claude-haiku-4-5-20251001', needsBase: false },
  { id: 'openrouter', label: 'OpenRouter', defaultModel: 'google/gemini-flash-1.5',   needsBase: false },
  { id: 'custom',     label: 'Custom',     defaultModel: '',                           needsBase: true  },
];

function StatusDot({ active }) {
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
        bgcolor: active ? 'success.main' : 'text.disabled', mr: 0.75,
      }}
    />
  );
}

export default function AssistantAISettings() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [providerTab, setProviderTab] = useState(0);
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [connectLoading, setConnectLoading] = useState(false);
  const [connectCode, setConnectCode] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await workspaceAI.getSettings();
      setSettings(data);
      if (data.user_key) {
        const idx = PROVIDERS.findIndex(p => p.id === data.user_key.provider);
        setProviderTab(idx >= 0 ? idx : 0);
        setModel(data.user_key.model_name || '');
        setBaseUrl(data.user_key.base_url || '');
      }
    } catch {
      setError('Failed to load AI settings.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const currentProvider = PROVIDERS[providerTab];

  const handleTest = async () => {
    if (!apiKey) return;
    setTesting(true);
    setTestResult(null);
    try {
      const { data } = await workspaceAI.testKey(
        currentProvider.id, apiKey,
        model || currentProvider.defaultModel,
        currentProvider.needsBase ? baseUrl : undefined,
      );
      setTestResult(data);
    } catch (e) {
      setTestResult({ success: false, message: e?.response?.data?.error || 'Request failed' });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    if (!apiKey) return;
    setSaving(true);
    setTestResult(null);
    try {
      await workspaceAI.saveKey(
        currentProvider.id, apiKey,
        model || currentProvider.defaultModel,
        currentProvider.needsBase ? baseUrl : undefined,
      );
      setApiKey('');
      await load();
    } catch (e) {
      setError(e?.response?.data?.error || 'Failed to save key.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await workspaceAI.deleteKey();
      setApiKey('');
      setModel('');
      setBaseUrl('');
      setTestResult(null);
      await load();
    } catch {
      setError('Failed to remove key.');
    } finally {
      setDeleting(false);
    }
  };

  const handleConnect = async () => {
    setConnectLoading(true);
    try {
      const { data } = await telegramAccount.generateConnectCode();
      setConnectCode(data.code || data.connect_code);
    } catch {
      setError('Failed to generate connect code.');
    } finally {
      setConnectLoading(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ p: { xs: 2, md: 3 }, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
        <CircularProgress size={32} />
      </Box>
    );
  }

  const usage = settings?.token_usage || { used: 0, limit: 50000 };
  const usagePct = Math.min(100, (usage.used / usage.limit) * 100);
  const atLimit = usagePct >= 100;

  const user = _getUser();

  return (
    <PlanGate plan="pro" userTier={user.subscription_tier} feature="AI Settings">
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 720, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>AI Settings</Typography>
      <Typography color="text.secondary" fontSize="0.9rem" mb={3}>
        Configure the AI provider for all Assistant features — Notes, Digests, and Hub.
      </Typography>

      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── Platform AI ── */}
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Typography fontWeight={600} mb={0.5}>Platform AI — Powered by Telegizer</Typography>
          <Typography fontSize="0.82rem" color="text.secondary" mb={1.5}>
            Provider: Google Gemini Flash 2.0
          </Typography>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            {settings?.platform_key_active ? (
              atLimit ? (
                <Chip icon={<Warning />} label="Limit reached" color="warning" size="small" />
              ) : (
                <Chip icon={<CheckCircle />} label="Active" color="success" size="small" />
              )
            ) : (
              <Chip icon={<Cancel />} label="Not configured" color="default" size="small" />
            )}
          </Box>

          {!settings?.platform_key_active && (
            <Typography fontSize="0.8rem" color="text.secondary" mb={1}>
              The platform AI key is not set up yet. Set your own API key below to enable all AI features.
            </Typography>
          )}

          {settings?.platform_key_active && (
            <>
              <Typography fontSize="0.78rem" color="text.secondary" mb={0.5}>
                Usage today: {(usage.used || 0).toLocaleString()} / {(usage.limit || 50000).toLocaleString()} tokens
              </Typography>
              <LinearProgress
                variant="determinate"
                value={usagePct}
                color={atLimit ? 'error' : usagePct > 80 ? 'warning' : 'primary'}
                sx={{ borderRadius: 1, height: 6, mb: 0.75 }}
              />
              {usage.limit === 50000 && (
                <Typography fontSize="0.75rem" color="text.disabled">
                  Upgrade to Pro for 200,000 tokens/day
                </Typography>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* ── Your API Key ── */}
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Typography fontWeight={600} mb={0.25}>Your API Key — Optional Override</Typography>
          <Typography fontSize="0.82rem" color="text.secondary" mb={2}>
            When set, bypasses the platform key for all Assistant features.
          </Typography>

          {settings?.user_key && (
            <Alert
              severity="success"
              sx={{ mb: 2, fontSize: '0.82rem' }}
              action={
                <Button
                  size="small"
                  color="inherit"
                  startIcon={deleting ? <CircularProgress size={14} /> : <Delete />}
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  Remove
                </Button>
              }
            >
              Active key: <strong>{settings.user_key.provider}</strong>
              {settings.user_key.model_name && ` · ${settings.user_key.model_name}`}
              {settings.user_key.api_key_masked && ` · ${settings.user_key.api_key_masked}`}
            </Alert>
          )}

          <Tabs
            value={providerTab}
            onChange={(_, v) => { setProviderTab(v); setTestResult(null); setModel(''); setBaseUrl(''); }}
            sx={{ mb: 2, minHeight: 36 }}
            TabIndicatorProps={{ style: { height: 2 } }}
          >
            {PROVIDERS.map((p, i) => (
              <Tab key={p.id} label={p.label} value={i} sx={{ fontSize: '0.8rem', minHeight: 36, py: 0 }} />
            ))}
          </Tabs>

          <TextField
            label="API Key"
            fullWidth
            size="small"
            type={showKey ? 'text' : 'password'}
            value={apiKey}
            onChange={e => { setApiKey(e.target.value); setTestResult(null); }}
            placeholder={`Paste your ${currentProvider.label} API key`}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <Tooltip title={showKey ? 'Hide' : 'Show'}>
                    <IconButton size="small" onClick={() => setShowKey(v => !v)} edge="end">
                      {showKey ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                    </IconButton>
                  </Tooltip>
                </InputAdornment>
              ),
            }}
            sx={{ mb: 1.5 }}
          />

          <TextField
            label={`Model (default: ${currentProvider.defaultModel || 'provider default'})`}
            fullWidth
            size="small"
            value={model}
            onChange={e => setModel(e.target.value)}
            sx={{ mb: currentProvider.needsBase ? 1.5 : 0 }}
          />

          {currentProvider.needsBase && (
            <TextField
              label="Base URL"
              fullWidth
              size="small"
              value={baseUrl}
              onChange={e => setBaseUrl(e.target.value)}
              placeholder="https://your-openai-compatible-endpoint.com"
            />
          )}

          {testResult && (
            <Alert severity={testResult.success ? 'success' : 'error'} sx={{ mt: 1.5, fontSize: '0.82rem' }}>
              {testResult.message}
            </Alert>
          )}

          <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
            <Button
              variant="outlined"
              size="small"
              onClick={handleTest}
              disabled={!apiKey || testing}
              startIcon={testing ? <CircularProgress size={14} /> : <Send />}
            >
              Test
            </Button>
            <Button
              variant="contained"
              size="small"
              onClick={handleSave}
              disabled={!apiKey || saving}
              startIcon={saving ? <CircularProgress size={14} /> : null}
            >
              Save Key
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* ── Telegram connection ── */}
      <Card variant="outlined">
        <CardContent>
          <Typography fontWeight={600} mb={0.25}>Connect Telegram Account</Typography>
          <Typography fontSize="0.82rem" color="text.secondary" mb={2}>
            Link your Telegram account to enable bot DM features — Smart Reminders and Live Chat.
          </Typography>
          <Divider sx={{ mb: 2 }} />

          {settings?.telegram_connected ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <StatusDot active />
              <Typography fontSize="0.88rem">
                Connected
                {settings.telegram_username && (
                  <Typography component="span" fontWeight={600}> as @{settings.telegram_username}</Typography>
                )}
              </Typography>
            </Box>
          ) : (
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <StatusDot active={false} />
                <Typography fontSize="0.88rem" color="text.secondary">Not connected</Typography>
              </Box>
              {connectCode ? (
                <Alert severity="info" sx={{ fontSize: '0.82rem' }}>
                  Open Telegram and send this code to <strong>@telegizer_bot</strong>:{' '}
                  <strong>{connectCode}</strong>
                </Alert>
              ) : (
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={connectLoading ? <CircularProgress size={14} /> : <LinkIcon />}
                  onClick={handleConnect}
                  disabled={connectLoading}
                >
                  Connect via Telegram
                </Button>
              )}
            </Box>
          )}
        </CardContent>
      </Card>
    </Box>
    </PlanGate>
  );
}
