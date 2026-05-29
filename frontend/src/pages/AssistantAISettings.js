import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Divider, Button, TextField,
  Tabs, Tab, LinearProgress, Chip, CircularProgress, Alert, IconButton,
  InputAdornment, Tooltip, Radio, RadioGroup, FormControlLabel,
  Stack, Paper,
} from '@mui/material';
import {
  CheckCircle, Cancel, Warning, Visibility, VisibilityOff,
  Delete, Send, Link as LinkIcon, AutoAwesome, VpnKey,
  BoltOutlined,
} from '@mui/icons-material';
import { workspaceAI, telegramAccount, auth as authApi, assistant } from '../services/api';
import PlanGate from '../components/PlanGate';

const PROVIDERS = [
  { id: 'gemini',     label: 'Gemini',     defaultModel: 'gemini-2.0-flash',          needsBase: false },
  { id: 'openai',     label: 'OpenAI',     defaultModel: 'gpt-4o-mini',               needsBase: false },
  { id: 'anthropic',  label: 'Anthropic',  defaultModel: 'claude-haiku-4-5-20251001', needsBase: false },
  { id: 'openrouter', label: 'OpenRouter', defaultModel: 'openai/gpt-4o-mini',        needsBase: false },
  { id: 'custom',     label: 'Custom',     defaultModel: '',                           needsBase: true  },
];

const TIER_COLORS = { enterprise: 'secondary', pro: 'primary', free: 'default' };

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

function PlatformAIPanel({ settings, userTier }) {
  const plan = settings?.plan || {};
  const usage = settings?.token_usage || { used: 0, limit: 10000 };
  const usagePct = Math.min(100, (usage.used / (usage.limit || 1)) * 100);
  const atLimit = usagePct >= 100;
  const platformActive = settings?.platform_key_active;
  const planActive = plan.subscription_active !== false;

  return (
    <Box>
      {/* Plan badge + status */}
      <Stack direction="row" alignItems="center" spacing={1} mb={2} flexWrap="wrap">
        <Chip
          label={plan.label || userTier.charAt(0).toUpperCase() + userTier.slice(1)}
          color={TIER_COLORS[userTier] || 'default'}
          size="small"
          sx={{ fontWeight: 700 }}
        />
        {platformActive && planActive ? (
          atLimit ? (
            <Chip icon={<Warning sx={{ fontSize: 14 }} />} label="Limit reached today" color="warning" size="small" />
          ) : (
            <Chip icon={<CheckCircle sx={{ fontSize: 14 }} />} label="Active" color="success" size="small" />
          )
        ) : (
          <Chip
            icon={<Cancel sx={{ fontSize: 14 }} />}
            label={
              !platformActive
                ? (plan.platform_ai_included ? 'Pending activation' : 'Not included in plan')
                : 'Subscription inactive'
            }
            color={plan.platform_ai_included && !platformActive ? 'warning' : 'default'}
            size="small"
          />
        )}
      </Stack>

      {!platformActive && (
        <Alert
          severity={plan.platform_ai_included ? 'warning' : 'info'}
          sx={{ mb: 2, fontSize: '0.82rem' }}
        >
          {plan.platform_ai_included
            ? 'Telegizer AI is included in your plan but is not yet activated on this server. No action needed on your end — contact support@telegizer.com to enable it, or use your own API key below in the meantime.'
            : 'Platform AI is not available on the free plan. Upgrade to Pro or Enterprise, or add your own API key below.'}
        </Alert>
      )}

      {platformActive && (
        <>
          {/* Included models */}
          {plan.models?.length > 0 && (
            <Box mb={2}>
              <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
                Models included
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={0.75}>
                {plan.models.map((m) => (
                  <Chip key={m} label={m} size="small" variant="outlined" sx={{ fontSize: '0.72rem' }} />
                ))}
              </Stack>
            </Box>
          )}

          {/* Usage bar */}
          <Box mb={1.5}>
            <Stack direction="row" justifyContent="space-between" mb={0.5}>
              <Typography variant="caption" color="text.secondary">Daily tokens used</Typography>
              <Typography variant="caption" color={atLimit ? 'error.main' : 'text.secondary'} fontWeight={600}>
                {(usage.used || 0).toLocaleString()} / {(usage.limit || 0).toLocaleString()}
              </Typography>
            </Stack>
            <LinearProgress
              variant="determinate"
              value={usagePct}
              color={atLimit ? 'error' : usagePct > 80 ? 'warning' : 'primary'}
              sx={{ borderRadius: 1, height: 6 }}
            />
            {atLimit && (
              <Typography variant="caption" color="error.main" mt={0.5} display="block">
                Limit reached. Resets in 24 hours, or switch to your own API key.
              </Typography>
            )}
          </Box>

          {plan.priority && (
            <Stack direction="row" alignItems="center" spacing={0.5}>
              <BoltOutlined sx={{ fontSize: 14, color: 'text.secondary' }} />
              <Typography variant="caption" color="text.secondary">{plan.priority}</Typography>
            </Stack>
          )}
        </>
      )}
    </Box>
  );
}

function OwnKeyPanel({
  settings, providerTab, setProviderTab, apiKey, setApiKey,
  model, setModel, baseUrl, setBaseUrl, showKey, setShowKey,
  saving, testing, testResult, deleting, onTest, onSave, onDelete,
}) {
  const currentProvider = PROVIDERS[providerTab];

  return (
    <Box>
      {settings?.user_key && (
        <Alert
          severity="success"
          sx={{ mb: 2, fontSize: '0.82rem' }}
          action={
            <Button
              size="small"
              color="inherit"
              startIcon={deleting ? <CircularProgress size={14} /> : <Delete />}
              onClick={onDelete}
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

      <Alert severity="info" icon={false} sx={{ mb: 2, fontSize: '0.8rem', py: 0.75 }}>
        Your key overrides platform AI for all Assistant features. Keys are encrypted before storage and never returned in full.
      </Alert>

      <Tabs
        value={providerTab}
        onChange={(_, v) => { setProviderTab(v); setApiKey(''); setModel(''); setBaseUrl(''); }}
        sx={{ mb: 2, minHeight: 36 }}
        TabIndicatorProps={{ style: { height: 2 } }}
        variant="scrollable"
        scrollButtons="auto"
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
        onChange={e => setApiKey(e.target.value)}
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

      <Stack direction="row" spacing={1} mt={2}>
        <Button
          variant="outlined"
          size="small"
          onClick={onTest}
          disabled={!apiKey || testing}
          startIcon={testing ? <CircularProgress size={14} /> : <Send />}
        >
          Test
        </Button>
        <Button
          variant="contained"
          size="small"
          onClick={onSave}
          disabled={!apiKey || saving}
          startIcon={saving ? <CircularProgress size={14} /> : null}
        >
          Save Key
        </Button>
      </Stack>
    </Box>
  );
}

export default function AssistantAISettings() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [userTier, setUserTier] = useState(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}').subscription_tier || 'free'; } catch { return 'free'; }
  });

  // "platform" | "custom"
  const [aiMode, setAiMode] = useState('platform');

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
  const [botUsername, setBotUsername] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [{ data }, meRes, hubRes] = await Promise.all([
        workspaceAI.getSettings(),
        authApi.getMe().catch(() => null),
        assistant.hubSummary().catch(() => ({ data: {} })),
      ]);
      setBotUsername(hubRes.data.bot_username || '');
      setSettings(data);
      if (meRes?.data?.user) {
        const freshTier = meRes.data.user.subscription_tier || 'free';
        setUserTier(freshTier);
        localStorage.setItem('user', JSON.stringify({ ...meRes.data.user }));
      }
      // Infer mode from whether user has an active custom key
      if (data.user_key) {
        setAiMode('custom');
        const idx = PROVIDERS.findIndex(p => p.id === data.user_key.provider);
        setProviderTab(idx >= 0 ? idx : 0);
        setModel(data.user_key.model_name || '');
        setBaseUrl(data.user_key.base_url || '');
      } else {
        setAiMode('platform');
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

  const handleModeChange = (e) => {
    setAiMode(e.target.value);
    setTestResult(null);
  };

  if (loading) {
    return (
      <Box sx={{ p: { xs: 2, md: 3 }, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
        <CircularProgress size={32} />
      </Box>
    );
  }

  const plan = settings?.plan || {};

  return (
    <PlanGate plan="pro" userTier={userTier} feature="AI Settings">
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 680, mx: 'auto' }}>

      <Stack direction="row" alignItems="center" spacing={1.5} mb={0.5}>
        <Typography variant="h5" fontWeight={700}>AI Settings</Typography>
        <Chip
          label={plan.label || userTier}
          color={TIER_COLORS[userTier] || 'default'}
          size="small"
          sx={{ fontWeight: 700, textTransform: 'capitalize' }}
        />
      </Stack>
      <Typography color="text.secondary" fontSize="0.9rem" mb={3}>
        Configure the AI provider for all Assistant features — Notes, Digests, and Hub.
      </Typography>

      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── Mode selector ── */}
      <RadioGroup value={aiMode} onChange={handleModeChange} sx={{ mb: 2, gap: 1.5 }}>

        {/* Platform AI card */}
        <Paper
          variant="outlined"
          onClick={() => setAiMode('platform')}
          sx={{
            p: 2, cursor: 'pointer', borderRadius: 2,
            borderColor: aiMode === 'platform' ? 'primary.main' : 'divider',
            borderWidth: aiMode === 'platform' ? 2 : 1,
            transition: 'border-color 0.15s',
            '&:hover': { borderColor: 'primary.light' },
          }}
        >
          <Stack direction="row" alignItems="flex-start" spacing={1}>
            <FormControlLabel
              value="platform"
              control={<Radio size="small" sx={{ mt: -0.25 }} />}
              label=""
              sx={{ m: 0, mr: 0.5 }}
            />
            <Box sx={{ flex: 1 }}>
              <Stack direction="row" alignItems="center" spacing={1} mb={0.25}>
                <AutoAwesome sx={{ fontSize: 18, color: 'primary.main' }} />
                <Typography fontWeight={700} fontSize="0.95rem">Use Telegizer AI</Typography>
                <Chip label="Recommended" size="small" color="primary" variant="outlined" sx={{ height: 18, fontSize: '0.65rem' }} />
              </Stack>
              <Typography fontSize="0.82rem" color="text.secondary" mb={aiMode === 'platform' ? 2 : 0}>
                {plan.description || 'Managed by Telegizer — no setup required.'}
              </Typography>

              {aiMode === 'platform' && (
                <PlatformAIPanel settings={settings} userTier={userTier} />
              )}
            </Box>
          </Stack>
        </Paper>

        {/* Own key card */}
        <Paper
          variant="outlined"
          onClick={() => setAiMode('custom')}
          sx={{
            p: 2, cursor: 'pointer', borderRadius: 2,
            borderColor: aiMode === 'custom' ? 'primary.main' : 'divider',
            borderWidth: aiMode === 'custom' ? 2 : 1,
            transition: 'border-color 0.15s',
            '&:hover': { borderColor: 'primary.light' },
          }}
        >
          <Stack direction="row" alignItems="flex-start" spacing={1}>
            <FormControlLabel
              value="custom"
              control={<Radio size="small" sx={{ mt: -0.25 }} />}
              label=""
              sx={{ m: 0, mr: 0.5 }}
            />
            <Box sx={{ flex: 1 }}>
              <Stack direction="row" alignItems="center" spacing={1} mb={0.25}>
                <VpnKey sx={{ fontSize: 18, color: 'text.secondary' }} />
                <Typography fontWeight={700} fontSize="0.95rem">Use My Own API Key</Typography>
              </Stack>
              <Typography fontSize="0.82rem" color="text.secondary" mb={aiMode === 'custom' ? 2 : 0}>
                OpenAI, Claude, Gemini, OpenRouter, or any custom endpoint. Overrides platform AI.
              </Typography>

              {aiMode === 'custom' && (
                <OwnKeyPanel
                  settings={settings}
                  providerTab={providerTab}
                  setProviderTab={setProviderTab}
                  apiKey={apiKey}
                  setApiKey={setApiKey}
                  model={model}
                  setModel={setModel}
                  baseUrl={baseUrl}
                  setBaseUrl={setBaseUrl}
                  showKey={showKey}
                  setShowKey={setShowKey}
                  saving={saving}
                  testing={testing}
                  testResult={testResult}
                  deleting={deleting}
                  onTest={handleTest}
                  onSave={handleSave}
                  onDelete={handleDelete}
                />
              )}
            </Box>
          </Stack>
        </Paper>
      </RadioGroup>

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
                  Open Telegram and send this code to <strong>@{botUsername || 'telegizer_bot'}</strong>:{' '}
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
