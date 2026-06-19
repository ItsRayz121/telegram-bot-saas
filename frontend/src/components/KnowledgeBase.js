import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Switch, FormControlLabel, IconButton, Chip, Alert, LinearProgress,
  List, ListItem, ListItemText, ListItemSecondaryAction, Divider,
  MenuItem, Select, FormControl, InputLabel, Slider, CircularProgress,
  Collapse, Paper, Tooltip, Checkbox, InputAdornment,
} from '@mui/material';
import { Upload, Delete, Description, Psychology, Key, ExpandMore, ExpandLess, CheckCircle, SmartToy, Tune, EmojiPeople, ImageSearch, Search, Person } from '@mui/icons-material';
import { toast } from 'react-toastify';
import CollapsibleCard from './CollapsibleCard';
import { knowledge, apiKeys, settings as settingsApi } from '../services/api';
import { AI_PERSONALITIES, REPLY_LENGTHS, EMOJI_LEVELS, FORMALITY_LEVELS } from '../config/aiPersonalities';

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'openrouter', label: 'OpenRouter' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'custom', label: 'Custom (OpenAI-compatible)' },
];

const DEFAULT_MODELS = {
  openai: 'gpt-4o-mini',
  openrouter: 'openai/gpt-4o-mini',
  anthropic: 'claude-haiku-4-5-20251001',
  gemini: 'gemini-1.5-flash',
  custom: '',
};

export default function KnowledgeBase({ botId, groupId, settings, updateSetting }) {
  const [docs, setDocs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStage, setUploadStage] = useState('');
  const fileRef = useRef();
  const kb = settings?.knowledge_base || {};

  // Determine whether the platform AI key is available (Pro/Enterprise plan).
  // The server uses PLATFORM_OPENROUTER_API_KEY as a fallback for all groups
  // whose owner hasn't set a per-group key — Pro/Enterprise plans include this.
  const userTier = (() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}').subscription_tier || 'free'; } catch { return 'free'; }
  })();
  const platformAiIncluded = userTier === 'pro' || userTier === 'enterprise';

  // API Key state
  const [apiKeyOpen, setApiKeyOpen] = useState(false);
  const [savedApiKey, setSavedApiKey] = useState(null);
  const [keyForm, setKeyForm] = useState({
    provider: 'openai',
    api_key: '',
    base_url: '',
    model_name: '',
  });
  const [savingKey, setSavingKey] = useState(false);
  const [testingKey, setTestingKey] = useState(false);

  // Escalation admin dropdown state
  const [escalationDropdownOpen, setEscalationDropdownOpen] = useState(false);
  const [escalationAdmins, setEscalationAdmins] = useState([]);
  const [escalationAdminsLoading, setEscalationAdminsLoading] = useState(false);
  const [escalationAdminSearch, setEscalationAdminSearch] = useState('');
  const escalationDropdownRef = useRef(null);

  const loadEscalationAdmins = useCallback(async () => {
    if (escalationAdmins.length > 0) return; // already loaded
    setEscalationAdminsLoading(true);
    try {
      const res = await settingsApi.getGroupAdmins(botId, groupId);
      setEscalationAdmins(res.data.admins || []);
    } catch {
      setEscalationAdmins([]);
    } finally {
      setEscalationAdminsLoading(false);
    }
  }, [botId, groupId, escalationAdmins.length]);

  useEffect(() => {
    if (!escalationDropdownOpen) return;
    loadEscalationAdmins();
  }, [escalationDropdownOpen, loadEscalationAdmins]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (escalationDropdownRef.current && !escalationDropdownRef.current.contains(e.target)) {
        setEscalationDropdownOpen(false);
      }
    };
    if (escalationDropdownOpen) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [escalationDropdownOpen]);

  const loadDocs = useCallback(async () => {
    try {
      const res = await knowledge.list(botId, groupId);
      setDocs(res.data.documents || []);
    } catch { toast.error('Failed to load knowledge base documents'); }
  }, [botId, groupId]);

  const loadApiKey = useCallback(async () => {
    try {
      const res = await apiKeys.get(botId, groupId);
      const record = res.data.api_key;
      if (record) {
        setSavedApiKey(record);
        setKeyForm(prev => ({
          ...prev,
          provider: record.provider || 'openai',
          base_url: record.base_url || '',
          model_name: record.model_name || '',
          api_key: '', // never pre-fill the key field
        }));
      }
    } catch { }
  }, [botId, groupId]);

  useEffect(() => {
    loadDocs();
    loadApiKey();
  }, [loadDocs, loadApiKey]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const allowed = ['pdf', 'txt', 'md', 'docx'];
    const ext = file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) {
      toast.error(`Unsupported file type. Use: ${allowed.join(', ')}`);
      if (fileRef.current) fileRef.current.value = '';
      return;
    }
    setUploading(true);
    setUploadProgress(0);
    setUploadStage('Uploading…');
    try {
      const fd = new FormData();
      fd.append('file', file);
      await knowledge.uploadWithProgress(botId, groupId, fd, (pct, stage) => {
        setUploadProgress(pct);
        setUploadStage(stage);
      });
      toast.success(`"${file.name}" uploaded and indexed`);
      loadDocs();
    } catch (err) {
      const reason = err.response?.data?.error || err.message || 'Upload failed';
      toast.error(reason);
    } finally {
      setUploading(false);
      setUploadProgress(0);
      setUploadStage('');
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleDelete = async (docId, filename) => {
    try {
      await knowledge.delete(botId, groupId, docId);
      toast.success(`"${filename}" removed`);
      setDocs(prev => prev.filter(d => d.id !== docId));
    } catch { toast.error('Failed to delete'); }
  };

  const handleSaveApiKey = async () => {
    if (!keyForm.api_key.trim() && !savedApiKey) {
      toast.error('API key is required');
      return;
    }
    setSavingKey(true);
    try {
      const payload = {
        provider: keyForm.provider,
        base_url: keyForm.base_url || null,
        model_name: keyForm.model_name || DEFAULT_MODELS[keyForm.provider] || null,
      };
      // Only include api_key if user typed something new (not masked or empty)
      if (keyForm.api_key.trim() && !keyForm.api_key.includes('****')) {
        payload.api_key = keyForm.api_key.trim();
      } else if (!savedApiKey) {
        toast.error('Please enter your API key');
        return;
      }
      // If savedApiKey exists and no new key entered, omit api_key from payload.
      // Backend will keep the existing encrypted key and only update metadata.
      const res = await apiKeys.save(botId, groupId, payload);
      setSavedApiKey(res.data.api_key);
      setKeyForm(prev => ({ ...prev, api_key: '' }));
      toast.success(res.data.message || 'API key saved');
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to save API key');
    } finally {
      setSavingKey(false);
    }
  };

  const handleDeleteApiKey = async () => {
    try {
      await apiKeys.delete(botId, groupId);
      setSavedApiKey(null);
      setKeyForm({ provider: 'openai', api_key: '', base_url: '', model_name: '' });
      toast.success('API key removed');
    } catch {
      toast.error('Failed to remove API key');
    }
  };

  const handleTestConnection = async () => {
    setTestingKey(true);
    try {
      const payload = {
        provider: keyForm.provider,
        api_key: keyForm.api_key.trim() || (savedApiKey?.api_key_masked || ''),
        base_url: keyForm.base_url || null,
        model_name: keyForm.model_name || null,
      };
      const res = await apiKeys.test(botId, groupId, payload);
      if (res.data.success) {
        toast.success(`✅ ${res.data.message}`);
      } else {
        toast.error(`❌ ${res.data.error}`);
      }
    } catch (e) {
      toast.error(e.response?.data?.error || 'Test failed');
    } finally {
      setTestingKey(false);
    }
  };

  const showBaseUrl = ['openrouter', 'custom'].includes(keyForm.provider) || !!keyForm.base_url;

  return (
    <Box>
      {/* Basic enable toggle */}
      <CollapsibleCard
        id="tg.ai.knowledge_base"
        title={(
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Psychology color="primary" />
            <Typography variant="h6" fontWeight={600}>AI Knowledge Base</Typography>
          </Box>
        )}
      >
          <Typography variant="body2" color="text.secondary" mb={2}>
            Upload documents and let the bot answer questions from your files. Use <strong>/ask your question</strong> in the group, or enable automatic replies below.
          </Typography>
          <FormControlLabel
            control={<Switch checked={!!kb.enabled} onChange={e => updateSetting('knowledge_base.enabled', e.target.checked)} />}
            label="Enable AI Q&A from knowledge base"
          />
      </CollapsibleCard>

      {/* API Key Settings */}
      <Card sx={{ mt: 2, mb: 2 }}>
        <CardContent>
          <Box
            sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
            onClick={() => setApiKeyOpen(o => !o)}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Key color="secondary" />
              <Typography variant="subtitle1" fontWeight={600}>
                AI Provider & API Key{platformAiIncluded ? ' (Optional Override)' : ''}
              </Typography>
              {platformAiIncluded && !savedApiKey && (
                <Chip
                  icon={<CheckCircle />}
                  label="Platform AI Active"
                  color="success"
                  size="small"
                />
              )}
              {savedApiKey && (
                <Chip
                  icon={<CheckCircle />}
                  label={`${savedApiKey.provider?.toUpperCase()} configured`}
                  color="success"
                  size="small"
                />
              )}
            </Box>
            {apiKeyOpen ? <ExpandLess /> : <ExpandMore />}
          </Box>

          <Collapse in={apiKeyOpen}>
            <Box sx={{ mt: 2 }}>
              {platformAiIncluded ? (
                <Alert severity="success" sx={{ mb: 2 }}>
                  <strong>Platform AI (OpenRouter) is active</strong> for this group via your {userTier.charAt(0).toUpperCase() + userTier.slice(1)} plan — no API key needed.
                  Add a custom key below only if you want to use a specific provider or model instead.
                </Alert>
              ) : (
                <Alert severity="info" sx={{ mb: 2 }}>
                  Add your own AI provider key to enable AI Q&A for this group.
                  Keys are encrypted before storage and never returned in full.
                </Alert>
              )}

              {savedApiKey && (
                <Alert severity="success" sx={{ mb: 2 }}>
                  Saved key: <strong>{savedApiKey.provider?.toUpperCase()}</strong> — {savedApiKey.api_key_masked}
                  {savedApiKey.model_name && <> — Model: {savedApiKey.model_name}</>}
                </Alert>
              )}

              <Grid container spacing={2}>
                <Grid item xs={12} sm={4}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Provider</InputLabel>
                    <Select
                      value={keyForm.provider}
                      label="Provider"
                      onChange={e => setKeyForm(p => ({
                        ...p,
                        provider: e.target.value,
                        model_name: p.model_name || DEFAULT_MODELS[e.target.value] || '',
                      }))}
                    >
                      {PROVIDERS.map(p => (
                        <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={8}>
                  <TextField
                    fullWidth size="small"
                    label="API Key"
                    type="password"
                    placeholder={savedApiKey ? `Current: ${savedApiKey.api_key_masked} (leave blank to keep)` : 'Enter your API key'}
                    value={keyForm.api_key}
                    onChange={e => setKeyForm(p => ({ ...p, api_key: e.target.value }))}
                    autoComplete="new-password"
                  />
                </Grid>
                {showBaseUrl && (
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth size="small"
                      label="Base URL (optional)"
                      placeholder="https://openrouter.ai/api/v1"
                      value={keyForm.base_url}
                      onChange={e => setKeyForm(p => ({ ...p, base_url: e.target.value }))}
                    />
                  </Grid>
                )}
                <Grid item xs={12} sm={showBaseUrl ? 6 : 12}>
                  <TextField
                    fullWidth size="small"
                    label="Model (optional)"
                    placeholder={DEFAULT_MODELS[keyForm.provider] || 'e.g. gpt-4o-mini'}
                    value={keyForm.model_name}
                    onChange={e => setKeyForm(p => ({ ...p, model_name: e.target.value }))}
                  />
                </Grid>
                <Grid item xs={12}>
                  <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                    <Button
                      variant="contained"
                      onClick={handleSaveApiKey}
                      disabled={savingKey}
                      startIcon={savingKey ? <CircularProgress size={16} /> : null}
                    >
                      {savingKey ? 'Saving…' : savedApiKey ? 'Update Key' : 'Save Key'}
                    </Button>
                    <Button
                      variant="outlined"
                      onClick={handleTestConnection}
                      disabled={testingKey || (!keyForm.api_key && !savedApiKey)}
                      startIcon={testingKey ? <CircularProgress size={16} /> : null}
                    >
                      {testingKey ? 'Testing…' : 'Test Connection'}
                    </Button>
                    {savedApiKey && (
                      <Button variant="outlined" color="error" onClick={handleDeleteApiKey}>
                        Remove Key
                      </Button>
                    )}
                  </Box>
                </Grid>
              </Grid>
            </Box>
          </Collapse>
        </CardContent>
      </Card>

      {/* Automatic Reply Settings */}
      <CollapsibleCard id="tg.ai.auto_replies" title="Automatic Knowledge Replies"
        badge={<Chip label="AI" size="small" color="primary" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />}>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Let the bot automatically answer knowledge-base questions without needing the /ask command.
          </Typography>

          <Grid container spacing={2}>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={!!kb.auto_reply_enabled}
                    onChange={e => updateSetting('knowledge_base.auto_reply_enabled', e.target.checked)}
                  />
                }
                label="Enable automatic knowledge replies"
              />
            </Grid>

            {kb.auto_reply_enabled && (
              <>
                <Grid item xs={12} sm={6}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={!!kb.auto_reply_mention_only}
                        onChange={e => updateSetting('knowledge_base.auto_reply_mention_only', e.target.checked)}
                      />
                    }
                    label="Only reply when bot is @mentioned or replied to"
                  />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={kb.auto_reply_in_groups !== false}
                        onChange={e => updateSetting('knowledge_base.auto_reply_in_groups', e.target.checked)}
                      />
                    }
                    label="Allow automatic replies in group chats"
                  />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={!!kb.fallback_enabled}
                        onChange={e => updateSetting('knowledge_base.fallback_enabled', e.target.checked)}
                      />
                    }
                    label="Reply with fallback if KB confidence is low"
                  />
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="body2" gutterBottom>
                    Minimum confidence threshold: <strong>{Math.round((kb.confidence_threshold || 0.35) * 100)}%</strong>
                  </Typography>
                  <Slider
                    value={Math.round((kb.confidence_threshold || 0.35) * 100)}
                    min={10}
                    max={90}
                    step={5}
                    marks
                    valueLabelDisplay="auto"
                    valueLabelFormat={v => `${v}%`}
                    onChange={(_, v) => updateSetting('knowledge_base.confidence_threshold', v / 100)}
                    sx={{ maxWidth: 400 }}
                  />
                  <Typography variant="caption" color="text.secondary">
                    Lower = bot replies more often but may be less accurate. Higher = more selective replies.
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth size="small"
                    type="number"
                    label="Min message length (words)"
                    value={kb.min_message_words ?? 5}
                    inputProps={{ min: 2, max: 20 }}
                    onChange={e => updateSetting('knowledge_base.min_message_words', parseInt(e.target.value) || 5)}
                  />
                </Grid>
              </>
            )}
          </Grid>
      </CollapsibleCard>

      {/* AI Personality & Reply Behavior */}
      <CollapsibleCard
        id="tg.ai.reply_personality"
        title={(
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SmartToy color="primary" fontSize="small" />
            <Typography variant="subtitle1" fontWeight={600}>AI Reply Personality</Typography>
          </Box>
        )}
      >
          <Typography variant="body2" color="text.secondary" mb={2}>
            Choose how the AI communicates with your community. Each personality uses professionally
            engineered prompts designed to feel natural and human — not robotic.
          </Typography>

          <Grid container spacing={1.5} mb={2}>
            {AI_PERSONALITIES.map((p) => {
              const selected = (kb.personality || 'professional_support') === p.id;
              return (
                <Grid item xs={12} sm={6} key={p.id}>
                  <Box
                    onClick={() => updateSetting('knowledge_base.personality', p.id)}
                    sx={{
                      p: 1.5,
                      border: '1px solid',
                      borderRadius: 1.5,
                      borderColor: selected ? 'primary.main' : 'divider',
                      bgcolor: selected ? 'rgba(33,150,243,0.06)' : 'transparent',
                      cursor: 'pointer',
                      transition: 'border-color 0.15s, background-color 0.15s',
                      '&:hover': { borderColor: 'primary.light' },
                    }}
                  >
                    <Typography variant="body2" fontWeight={600}>
                      {p.emoji} {p.label}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" mt={0.25}>
                      {p.description}
                    </Typography>
                  </Box>
                </Grid>
              );
            })}
          </Grid>

          <Divider sx={{ my: 2 }} />

          {/* Custom Instructions */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Tune fontSize="small" color="action" />
            <Typography variant="subtitle2" fontWeight={600}>Custom Instructions</Typography>
          </Box>
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Add specific rules for your community. Examples: "Always reply in Urdu and English", "Never mention competitor products", "Summarize answers in bullet points", "Always link to our docs site".
          </Typography>
          <TextField
            fullWidth
            multiline
            minRows={3}
            maxRows={7}
            size="small"
            placeholder={'Examples:\n• Reply in both English and Spanish\n• Always end with "Check our docs at docs.example.com"\n• Never use emojis\n• Keep answers under 3 sentences'}
            value={kb.custom_instructions || ''}
            onChange={(e) => updateSetting('knowledge_base.custom_instructions', e.target.value)}
            inputProps={{ maxLength: 1200 }}
            helperText={`${(kb.custom_instructions || '').length}/1200 characters`}
          />

          <Divider sx={{ my: 2 }} />

          {/* Format Controls */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <Tune fontSize="small" color="action" />
            <Typography variant="subtitle2" fontWeight={600}>Reply Format</Typography>
          </Box>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={4}>
              <FormControl fullWidth size="small">
                <InputLabel>Reply Length</InputLabel>
                <Select
                  label="Reply Length"
                  value={kb.reply_length || 'balanced'}
                  onChange={(e) => updateSetting('knowledge_base.reply_length', e.target.value)}
                >
                  {REPLY_LENGTHS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      <Box>
                        <Typography variant="body2">{opt.label}</Typography>
                        <Typography variant="caption" color="text.secondary">{opt.description}</Typography>
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={4}>
              <FormControl fullWidth size="small">
                <InputLabel>Emoji Usage</InputLabel>
                <Select
                  label="Emoji Usage"
                  value={kb.emoji_level || 'minimal'}
                  onChange={(e) => updateSetting('knowledge_base.emoji_level', e.target.value)}
                >
                  {EMOJI_LEVELS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      <Box>
                        <Typography variant="body2">{opt.label}</Typography>
                        <Typography variant="caption" color="text.secondary">{opt.description}</Typography>
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={4}>
              <FormControl fullWidth size="small">
                <InputLabel>Formality Level</InputLabel>
                <Select
                  label="Formality Level"
                  value={kb.formality_level || 'neutral'}
                  onChange={(e) => updateSetting('knowledge_base.formality_level', e.target.value)}
                >
                  {FORMALITY_LEVELS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      <Box>
                        <Typography variant="body2">{opt.label}</Typography>
                        <Typography variant="caption" color="text.secondary">{opt.description}</Typography>
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>

          <Alert severity="info" sx={{ mt: 2, fontSize: '0.8rem' }} icon={false}>
            <strong>How it works:</strong> Telegizer builds a layered system prompt: knowledge-base
            context → personality rules → anti-robotic guidelines → your custom instructions.
            Replies adapt to your community's tone automatically without any AI jailbreak risk.
          </Alert>
      </CollapsibleCard>

      {/* Auto Replies as AI Knowledge */}
      <CollapsibleCard
        id="tg.ai.auto_replies_knowledge"
        title={(
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SmartToy color="primary" fontSize="small" />
            <Typography variant="subtitle1" fontWeight={600}>Auto Replies as AI Knowledge</Typography>
          </Box>
        )}
      >
          <Typography variant="body2" color="text.secondary" mb={1.5}>
            When enabled, the AI can use your saved auto-reply triggers as extra knowledge for smarter,
            context-aware answers — even when users phrase questions differently than the trigger keyword.
          </Typography>
          <FormControlLabel
            control={
              <Switch
                checked={!!kb.use_auto_replies_as_knowledge}
                onChange={e => updateSetting('knowledge_base.use_auto_replies_as_knowledge', e.target.checked)}
              />
            }
            label="Use Auto Replies as AI Knowledge"
          />
          {!!kb.use_auto_replies_as_knowledge && (
            <Alert severity="info" sx={{ mt: 1.5, fontSize: '0.8rem' }} icon={false}>
              Go to <strong>Automation → Auto Reply</strong> and enable the <strong>"AI Knowledge"</strong> toggle
              on each trigger you want the AI to learn from. Only enabled triggers marked for AI use are included.
            </Alert>
          )}
      </CollapsibleCard>

      {/* Human-Like Community Interaction */}
      {(() => {
        const sr = settings?.social_replies || {};
        return (
          <CollapsibleCard
            id="tg.ai.social_replies"
            badge={<Chip label="AI" size="small" color="primary" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />}
            title={(
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <EmojiPeople color="primary" fontSize="small" />
                <Typography variant="subtitle1" fontWeight={600}>Human-Like Community Interaction</Typography>
              </Box>
            )}
          >
              <Typography variant="body2" color="text.secondary" mb={1.5}>
                Bot reacts and responds naturally to appreciation messages ("thanks", "helpful", "solved", etc.)
                — no AI cost, personality-aware, with spam protection.
              </Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={!!sr.enabled}
                    onChange={e => updateSetting('social_replies.enabled', e.target.checked)}
                  />
                }
                label="Enable Human-Like Interaction"
              />
              {!!sr.enabled && (
                <Box mt={2}>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={sr.react_to_appreciation !== false}
                            onChange={e => updateSetting('social_replies.react_to_appreciation', e.target.checked)}
                          />
                        }
                        label="React with emoji to appreciation"
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={sr.reply_to_appreciation !== false}
                            onChange={e => updateSetting('social_replies.reply_to_appreciation', e.target.checked)}
                          />
                        }
                        label="Reply with text acknowledgment"
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <FormControl fullWidth size="small">
                        <InputLabel>Interaction Style</InputLabel>
                        <Select
                          label="Interaction Style"
                          value={sr.mode || 'friendly'}
                          onChange={e => updateSetting('social_replies.mode', e.target.value)}
                        >
                          <MenuItem value="minimal">
                            <Box>
                              <Typography variant="body2">Minimal</Typography>
                              <Typography variant="caption" color="text.secondary">Emoji reaction only, no text reply</Typography>
                            </Box>
                          </MenuItem>
                          <MenuItem value="professional">
                            <Box>
                              <Typography variant="body2">Professional</Typography>
                              <Typography variant="caption" color="text.secondary">Formal text reply, no decorative emojis</Typography>
                            </Box>
                          </MenuItem>
                          <MenuItem value="friendly">
                            <Box>
                              <Typography variant="body2">Friendly</Typography>
                              <Typography variant="caption" color="text.secondary">Warm reply with occasional emojis</Typography>
                            </Box>
                          </MenuItem>
                          <MenuItem value="community_manager">
                            <Box>
                              <Typography variant="body2">Community Manager</Typography>
                              <Typography variant="caption" color="text.secondary">Energetic, engaging, personality-matched</Typography>
                            </Box>
                          </MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth size="small"
                        type="number"
                        label="Cooldown per user (minutes)"
                        value={sr.cooldown_minutes ?? 5}
                        inputProps={{ min: 1, max: 60 }}
                        onChange={e => updateSetting('social_replies.cooldown_minutes', parseInt(e.target.value) || 5)}
                        helperText="Min gap between replies to the same user"
                      />
                    </Grid>
                  </Grid>
                  <Alert severity="info" sx={{ mt: 2, fontSize: '0.8rem' }} icon={false}>
                    <strong>Reply style is determined by your AI Personality setting above.</strong> The interaction
                    style controls formality and emoji intensity. Cooldown prevents the bot from responding to the
                    same user more than once per interval.
                  </Alert>
                </Box>
              )}
          </CollapsibleCard>
        );
      })()}

      {/* Image AI / Multimodal */}
      {(() => {
        const img = settings?.image_ai || {};
        return (
          <CollapsibleCard
            id="tg.ai.image_ai"
            badge={<Chip label="AI" size="small" color="primary" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />}
            title={(
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <ImageSearch color="primary" fontSize="small" />
                <Typography variant="subtitle1" fontWeight={600}>Image Understanding (Multimodal AI)</Typography>
              </Box>
            )}
          >
              <Typography variant="body2" color="text.secondary" mb={1.5}>
                AI analyzes screenshots, error messages, and images sent with captions. Uses GPT-4o mini
                (~$0.0003/image). Smart gating ensures most images are never sent to the API.
              </Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={!!img.enabled}
                    onChange={e => updateSetting('image_ai.enabled', e.target.checked)}
                  />
                }
                label="Enable Image Understanding"
              />
              {!!img.enabled && (
                <Box mt={2}>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={img.mention_only !== false}
                            onChange={e => updateSetting('image_ai.mention_only', e.target.checked)}
                          />
                        }
                        label="Only when bot is @mentioned"
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={img.require_caption !== false}
                            onChange={e => updateSetting('image_ai.require_caption', e.target.checked)}
                          />
                        }
                        label="Require caption/text with image"
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={img.escalation_enabled !== false}
                            onChange={e => updateSetting('image_ai.escalation_enabled', e.target.checked)}
                          />
                        }
                        label="Escalate to admins when confidence low"
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <FormControl fullWidth size="small">
                        <InputLabel>Cost Mode</InputLabel>
                        <Select
                          label="Cost Mode"
                          value={img.cost_mode || 'balanced'}
                          onChange={e => updateSetting('image_ai.cost_mode', e.target.value)}
                        >
                          <MenuItem value="aggressive_savings">
                            <Box>
                              <Typography variant="body2">Aggressive Savings</Typography>
                              <Typography variant="caption" color="text.secondary">Only analyze if @mentioned + error keywords in caption</Typography>
                            </Box>
                          </MenuItem>
                          <MenuItem value="balanced">
                            <Box>
                              <Typography variant="body2">Balanced (Recommended)</Typography>
                              <Typography variant="caption" color="text.secondary">Analyze if caption has question/error keywords</Typography>
                            </Box>
                          </MenuItem>
                          <MenuItem value="quality">
                            <Box>
                              <Typography variant="body2">Quality</Typography>
                              <Typography variant="caption" color="text.secondary">Analyze any image when bot is @mentioned</Typography>
                            </Box>
                          </MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="body2" gutterBottom>
                        Confidence threshold: <strong>{Math.round((img.confidence_threshold || 0.65) * 100)}%</strong>
                      </Typography>
                      <Slider
                        value={Math.round((img.confidence_threshold || 0.65) * 100)}
                        min={30}
                        max={90}
                        step={5}
                        marks
                        valueLabelDisplay="auto"
                        valueLabelFormat={v => `${v}%`}
                        onChange={(_, v) => updateSetting('image_ai.confidence_threshold', v / 100)}
                        sx={{ maxWidth: 300 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        Below this → escalate to admins
                      </Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth size="small"
                        type="number"
                        label="Max image size (MB)"
                        value={img.max_image_size_mb ?? 5}
                        inputProps={{ min: 1, max: 10 }}
                        onChange={e => updateSetting('image_ai.max_image_size_mb', parseInt(e.target.value) || 5)}
                      />
                    </Grid>
                    {img.escalation_enabled !== false && (
                      <Grid item xs={12}>
                        <Box ref={escalationDropdownRef} sx={{ position: 'relative' }}>
                          <Box
                            onClick={() => setEscalationDropdownOpen(o => !o)}
                            sx={{
                              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                              px: 1.5, py: 1, border: '1px solid', borderRadius: 1,
                              borderColor: escalationDropdownOpen ? 'primary.main' : 'divider',
                              cursor: 'pointer', bgcolor: 'background.paper',
                              '&:hover': { borderColor: 'text.primary' },
                            }}
                          >
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <Person sx={{ fontSize: 16, color: 'text.secondary' }} />
                              <Typography variant="body2" color={(img.escalation_admin_ids || []).length ? 'text.primary' : 'text.secondary'}>
                                {(img.escalation_admin_ids || []).length > 0
                                  ? `${(img.escalation_admin_ids || []).length} admin${(img.escalation_admin_ids || []).length !== 1 ? 's' : ''} selected`
                                  : 'Select escalation admins'}
                              </Typography>
                            </Box>
                            {escalationDropdownOpen ? <ExpandLess sx={{ fontSize: 18, color: 'text.secondary' }} /> : <ExpandMore sx={{ fontSize: 18, color: 'text.secondary' }} />}
                          </Box>

                          {escalationDropdownOpen && (
                            <Paper elevation={4} sx={{
                              position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 1300,
                              mt: 0.5, border: '1px solid', borderColor: 'divider',
                              maxHeight: 260, display: 'flex', flexDirection: 'column',
                            }}>
                              <Box sx={{ p: 1, borderBottom: '1px solid', borderColor: 'divider' }}>
                                <TextField
                                  size="small" fullWidth
                                  placeholder="Search admins…"
                                  value={escalationAdminSearch}
                                  onChange={e => setEscalationAdminSearch(e.target.value)}
                                  onClick={e => e.stopPropagation()}
                                  InputProps={{
                                    startAdornment: (
                                      <InputAdornment position="start">
                                        <Search sx={{ fontSize: 16 }} />
                                      </InputAdornment>
                                    ),
                                  }}
                                />
                              </Box>
                              <Box sx={{ overflowY: 'auto', flex: 1 }}>
                                {escalationAdminsLoading ? (
                                  <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                                    <CircularProgress size={20} />
                                  </Box>
                                ) : escalationAdmins.length === 0 ? (
                                  <Typography variant="caption" color="text.secondary" sx={{ p: 1.5, display: 'block' }}>
                                    No admins found. Ensure the bot is an admin in this group.
                                  </Typography>
                                ) : (
                                  escalationAdmins
                                    .filter(a => {
                                      const q = escalationAdminSearch.toLowerCase();
                                      return !q ||
                                        (a.first_name || '').toLowerCase().includes(q) ||
                                        (a.username || '').toLowerCase().includes(q);
                                    })
                                    .map(admin => {
                                      const selectedIds = img.escalation_admin_ids || [];
                                      const isSelected = selectedIds.includes(String(admin.user_id));
                                      return (
                                        <Box
                                          key={admin.user_id}
                                          onClick={() => {
                                            const cur = (img.escalation_admin_ids || []).map(String);
                                            const uid = String(admin.user_id);
                                            updateSetting('image_ai.escalation_admin_ids',
                                              isSelected ? cur.filter(id => id !== uid) : [...cur, uid]);
                                          }}
                                          sx={{
                                            display: 'flex', alignItems: 'center', gap: 1,
                                            px: 1.5, py: 0.75, cursor: 'pointer',
                                            '&:hover': { bgcolor: 'action.hover' },
                                            borderBottom: '1px solid', borderColor: 'divider',
                                          }}
                                        >
                                          <Checkbox size="small" checked={isSelected} disableRipple sx={{ p: 0 }} onChange={() => {}} />
                                          <Box sx={{ flex: 1, minWidth: 0 }}>
                                            <Typography variant="body2" noWrap>
                                              {admin.first_name}{admin.username ? ` @${admin.username}` : ''}
                                            </Typography>
                                          </Box>
                                          {admin.can_dm
                                            ? <Chip label="✅ Can receive DM" color="success" size="small" sx={{ fontSize: '0.65rem', height: 20 }} />
                                            : <Tooltip title="Ask this admin to start a DM with the bot first.">
                                                <Chip label="⚠️ Must start bot" color="warning" size="small" sx={{ fontSize: '0.65rem', height: 20 }} />
                                              </Tooltip>
                                          }
                                        </Box>
                                      );
                                    })
                                )}
                              </Box>
                            </Paper>
                          )}
                        </Box>
                        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                          Selected admins receive DMs when AI confidence is low.
                        </Typography>
                      </Grid>
                    )}
                  </Grid>
                  <Alert severity="info" sx={{ mt: 2, fontSize: '0.8rem' }} icon={false}>
                    <strong>How it works:</strong> Smart gating checks caption keywords before calling the API —
                    most images never cost anything. Requires an OpenAI-compatible API key configured above.
                    For escalation to work, admins must have started a DM with the bot.
                  </Alert>
                </Box>
              )}
          </CollapsibleCard>
        );
      })()}

      {/* Upload */}
      <CollapsibleCard id="tg.ai.kb_upload" title="Upload Documents">
          <Alert severity="info" sx={{ mb: 2 }}>
            Supported: PDF, DOCX, TXT, MD — Max 5MB per file. Text is extracted and indexed for semantic search.
            {savedApiKey
              ? ` Using ${savedApiKey.provider?.toUpperCase()} for embeddings.`
              : ' Requires OPENAI_API_KEY in server environment or a custom key above.'}
          </Alert>
          {uploading && (
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                <Typography variant="caption" color="text.secondary">{uploadStage}</Typography>
                <Typography variant="caption" color="text.secondary">{uploadProgress}%</Typography>
              </Box>
              <LinearProgress variant="determinate" value={uploadProgress} sx={{ borderRadius: 1 }} />
            </Box>
          )}
          <input type="file" ref={fileRef} style={{ display: 'none' }} accept=".pdf,.txt,.md,.docx" onChange={handleUpload} />
          <Button variant="outlined" startIcon={<Upload />} onClick={() => fileRef.current.click()} disabled={uploading}>
            {uploading ? uploadStage || 'Processing…' : 'Upload Document'}
          </Button>
      </CollapsibleCard>

      {/* Document list */}
      <CollapsibleCard id="tg.ai.kb_documents" title={`Indexed Documents (${docs.length})`}>
          {docs.length === 0 ? (
            <Typography variant="body2" color="text.secondary">No documents uploaded yet.</Typography>
          ) : (
            <List disablePadding>
              {docs.map((doc, i) => (
                <React.Fragment key={doc.id}>
                  {i > 0 && <Divider />}
                  <ListItem disableGutters>
                    <Description sx={{ mr: 1.5, color: 'text.secondary' }} />
                    <ListItemText
                      primary={doc.filename}
                      secondary={`${doc.chunk_count} chunks indexed · ${new Date(doc.created_at).toLocaleDateString()}`}
                    />
                    <ListItemSecondaryAction>
                      <Chip label={doc.file_type.toUpperCase()} size="small" sx={{ mr: 1 }} />
                      <IconButton size="small" color="error" onClick={() => handleDelete(doc.id, doc.filename)}>
                        <Delete fontSize="small" />
                      </IconButton>
                    </ListItemSecondaryAction>
                  </ListItem>
                </React.Fragment>
              ))}
            </List>
          )}
      </CollapsibleCard>
    </Box>
  );
}
