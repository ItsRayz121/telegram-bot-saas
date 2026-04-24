import React, { useState, useEffect, useRef } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Switch, FormControlLabel, IconButton, Chip, Alert, LinearProgress,
  List, ListItem, ListItemText, ListItemSecondaryAction, Divider,
  MenuItem, Select, FormControl, InputLabel, Slider, CircularProgress,
  Collapse,
} from '@mui/material';
import { Upload, Delete, Description, Psychology, Key, ExpandMore, ExpandLess, CheckCircle } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { knowledge, apiKeys } from '../services/api';

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
  const fileRef = useRef();
  const kb = settings?.knowledge_base || {};

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

  const loadDocs = async () => {
    try {
      const res = await knowledge.list(botId, groupId);
      setDocs(res.data.documents || []);
    } catch { toast.error('Failed to load knowledge base documents'); }
  };

  const loadApiKey = async () => {
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
  };

  useEffect(() => {
    loadDocs();
    loadApiKey();
  }, [botId, groupId]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const allowed = ['pdf', 'txt', 'md', 'docx'];
    const ext = file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) {
      toast.error(`Unsupported file type. Use: ${allowed.join(', ')}`);
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await knowledge.upload(botId, groupId, fd);
      toast.success(`"${file.name}" uploaded and indexed`);
      loadDocs();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Upload failed');
    } finally {
      setUploading(false);
      fileRef.current.value = '';
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
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Psychology color="primary" />
            <Typography variant="h6" fontWeight={600}>AI Knowledge Base</Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Upload documents and let the bot answer questions from your files. Use <strong>/ask your question</strong> in the group, or enable automatic replies below.
          </Typography>
          <FormControlLabel
            control={<Switch checked={!!kb.enabled} onChange={e => updateSetting('knowledge_base.enabled', e.target.checked)} />}
            label="Enable AI Q&A from knowledge base"
          />
        </CardContent>
      </Card>

      {/* API Key Settings */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Box
            sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
            onClick={() => setApiKeyOpen(o => !o)}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Key color="secondary" />
              <Typography variant="subtitle1" fontWeight={600}>AI Provider & API Key</Typography>
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
              <Alert severity="info" sx={{ mb: 2 }}>
                Add your own AI provider key. This overrides the server's default OpenAI key for this group.
                Keys are encrypted before storage and never returned in full.
              </Alert>

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
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="subtitle1" fontWeight={600} mb={1}>Automatic Knowledge Replies</Typography>
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
        </CardContent>
      </Card>

      {/* Upload */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="subtitle1" fontWeight={600} mb={2}>Upload Documents</Typography>
          <Alert severity="info" sx={{ mb: 2 }}>
            Supported: PDF, DOCX, TXT, MD — Max 5MB per file. Text is extracted and indexed for semantic search.
            {savedApiKey
              ? ` Using ${savedApiKey.provider?.toUpperCase()} for embeddings.`
              : ' Requires OPENAI_API_KEY in server environment or a custom key above.'}
          </Alert>
          {uploading && <LinearProgress sx={{ mb: 2 }} />}
          <input type="file" ref={fileRef} style={{ display: 'none' }} accept=".pdf,.txt,.md,.docx" onChange={handleUpload} />
          <Button variant="outlined" startIcon={<Upload />} onClick={() => fileRef.current.click()} disabled={uploading}>
            {uploading ? 'Processing...' : 'Upload Document'}
          </Button>
        </CardContent>
      </Card>

      {/* Document list */}
      <Card>
        <CardContent>
          <Typography variant="subtitle1" fontWeight={600} mb={1}>Indexed Documents ({docs.length})</Typography>
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
        </CardContent>
      </Card>
    </Box>
  );
}
