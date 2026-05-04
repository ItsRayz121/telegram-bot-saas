import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Chip,
  IconButton, Alert, CircularProgress, Switch, FormControlLabel,
  Dialog, DialogTitle, DialogContent, DialogActions, Tooltip,
  FormGroup, Checkbox, FormControlLabel as FCL, Collapse,
} from '@mui/material';
import {
  Add, Delete, Edit, ContentCopy, CheckCircle, Error as ErrorIcon,
  Webhook, Send, ExpandMore, ExpandLess, Info,
} from '@mui/icons-material';
import { integrationWebhooks } from '../services/api';

const ALL_EVENTS = [
  { key: 'meeting.created',      label: 'Meeting Created',       desc: 'Fires when a meeting is scheduled via assistant or dashboard.' },
  { key: 'reminder.created',     label: 'Reminder Created',      desc: 'Fires when a workspace reminder is saved.' },
  { key: 'resource.attached',    label: 'Resource Attached',     desc: 'Fires when a link or note is added to a meeting.' },
  { key: 'group.issue.detected', label: 'Group Issue Detected',  desc: 'Fires when the assistant summarises group issues.' },
];

function relTime(iso) {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 2) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const EMPTY_FORM = { name: '', url: '', secret: '', events: [] };

// ── Webhook Form Dialog ───────────────────────────────────────────────────────

function WebhookFormDialog({ open, initial, onClose, onSave }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) {
      setForm(initial
        ? { name: initial.name, url: initial.url, secret: '', events: initial.events || [] }
        : EMPTY_FORM
      );
      setError('');
    }
  }, [open, initial]);

  const toggleEvent = (key) => {
    setForm(f => ({
      ...f,
      events: f.events.includes(key) ? f.events.filter(e => e !== key) : [...f.events, key],
    }));
  };

  const handleSave = async () => {
    if (!form.name.trim()) { setError('Name is required'); return; }
    if (!form.url.trim()) { setError('Webhook URL is required'); return; }
    if (form.events.length === 0) { setError('Select at least one event'); return; }
    setSaving(true);
    setError('');
    try {
      await onSave(form);
      onClose();
    } catch (e) {
      setError(e.response?.data?.error || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const isHttps = form.url.startsWith('https://');
  const isHttp = form.url.startsWith('http://') && !isHttps;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ fontWeight: 700 }}>{initial ? 'Edit Webhook' : 'Add Webhook'}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <TextField
          label="Name" fullWidth size="small" sx={{ mb: 2, mt: 0.5 }}
          placeholder="My n8n workflow"
          value={form.name}
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
        />

        <TextField
          label="Webhook URL" fullWidth size="small" sx={{ mb: 0.5 }}
          placeholder="https://your-n8n.example.com/webhook/..."
          value={form.url}
          onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
          error={isHttp}
          helperText={isHttp ? '⚠ HTTP is allowed but HTTPS is strongly recommended' : ''}
        />

        <TextField
          label="Secret (optional)" fullWidth size="small" sx={{ mb: 2, mt: 1.5 }}
          placeholder="Leave blank to skip signing"
          type="password"
          value={form.secret}
          onChange={e => setForm(f => ({ ...f, secret: e.target.value }))}
          helperText={initial?.secret_set ? 'Leave blank to keep existing secret' : 'Used for HMAC-SHA256 signature in X-Telegizer-Signature header'}
        />

        <Typography fontWeight={600} fontSize="0.88rem" mb={1}>Events to subscribe</Typography>
        <FormGroup>
          {ALL_EVENTS.map(ev => (
            <FCL
              key={ev.key}
              control={
                <Checkbox
                  size="small"
                  checked={form.events.includes(ev.key)}
                  onChange={() => toggleEvent(ev.key)}
                />
              }
              label={
                <Box>
                  <Typography fontSize="0.84rem" fontWeight={500}>{ev.label}</Typography>
                  <Typography fontSize="0.74rem" color="text.secondary">{ev.desc}</Typography>
                </Box>
              }
              sx={{ mb: 0.5 }}
            />
          ))}
        </FormGroup>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={handleSave} disabled={saving}>
          {saving ? <CircularProgress size={18} /> : initial ? 'Save Changes' : 'Add Webhook'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Single Webhook Row ────────────────────────────────────────────────────────

function WebhookRow({ hook, onEdit, onDelete, onToggle, onTest }) {
  const [expanded, setExpanded] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const { data } = await onTest(hook.id);
      setTestResult(data);
    } catch (e) {
      setTestResult({ ok: false, error: e.response?.data?.error || 'Request failed' });
    } finally {
      setTesting(false);
    }
  };

  const copyUrl = () => {
    navigator.clipboard.writeText(hook.url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const statusColor = hook.last_status === 'ok' ? 'success.main'
    : hook.last_status === 'error' ? 'error.main'
    : 'text.disabled';

  return (
    <Card variant="outlined" sx={{ mb: 1.5, opacity: hook.is_active ? 1 : 0.65 }}>
      <CardContent sx={{ pb: '12px !important' }}>
        {/* Header row */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Webhook sx={{ fontSize: 18, color: hook.is_active ? 'primary.main' : 'text.disabled' }} />
          <Typography fontWeight={600} fontSize="0.9rem" sx={{ flex: 1 }}>{hook.name}</Typography>
          {!hook.is_active && <Chip label="Disabled" size="small" color="default" sx={{ height: 18, fontSize: '0.65rem' }} />}
          {hook.failure_count >= 5 && <Chip label="Auto-disabled" size="small" color="error" sx={{ height: 18, fontSize: '0.65rem' }} />}

          <FormControlLabel
            control={<Switch size="small" checked={hook.is_active} onChange={() => onToggle(hook)} />}
            label=""
            sx={{ mr: 0 }}
          />
          <Tooltip title="Edit"><IconButton size="small" onClick={() => onEdit(hook)}><Edit sx={{ fontSize: 16 }} /></IconButton></Tooltip>
          <Tooltip title="Delete"><IconButton size="small" onClick={() => onDelete(hook.id)} sx={{ color: 'error.main' }}><Delete sx={{ fontSize: 16 }} /></IconButton></Tooltip>
          <IconButton size="small" onClick={() => setExpanded(v => !v)}>
            {expanded ? <ExpandLess sx={{ fontSize: 16 }} /> : <ExpandMore sx={{ fontSize: 16 }} />}
          </IconButton>
        </Box>

        {/* URL + events summary */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.75, flexWrap: 'wrap' }}>
          <Typography fontSize="0.76rem" color="text.secondary" noWrap sx={{ maxWidth: 300 }}>{hook.url}</Typography>
          <Tooltip title={copied ? 'Copied!' : 'Copy URL'}>
            <IconButton size="small" onClick={copyUrl}><ContentCopy sx={{ fontSize: 13 }} /></IconButton>
          </Tooltip>
        </Box>
        <Box sx={{ display: 'flex', gap: 0.5, mt: 0.75, flexWrap: 'wrap' }}>
          {(hook.events || []).map(e => (
            <Chip key={e} label={e} size="small" variant="outlined" sx={{ height: 18, fontSize: '0.62rem' }} />
          ))}
        </Box>

        {/* Status + last triggered */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.75 }}>
          {hook.last_status === 'ok' && <CheckCircle sx={{ fontSize: 13, color: 'success.main' }} />}
          {hook.last_status === 'error' && <ErrorIcon sx={{ fontSize: 13, color: 'error.main' }} />}
          <Typography fontSize="0.72rem" color={statusColor}>
            {hook.last_status ? `Last: ${hook.last_status} · ${relTime(hook.last_triggered_at)}` : 'Never triggered'}
          </Typography>
          {hook.failure_count > 0 && (
            <Typography fontSize="0.72rem" color="error.main">{hook.failure_count} failure{hook.failure_count > 1 ? 's' : ''}</Typography>
          )}
        </Box>

        {/* Expanded detail + test */}
        <Collapse in={expanded}>
          <Box sx={{ mt: 1.5, pt: 1.5, borderTop: '1px solid', borderColor: 'divider' }}>
            {hook.last_error && (
              <Alert severity="error" sx={{ mb: 1, py: 0, fontSize: '0.78rem' }}>{hook.last_error}</Alert>
            )}

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <Button
                size="small" variant="outlined" startIcon={<Send sx={{ fontSize: 14 }} />}
                onClick={handleTest} disabled={testing}
              >
                {testing ? <CircularProgress size={14} /> : 'Send Test Event'}
              </Button>
              <Typography fontSize="0.74rem" color="text.secondary">
                Sends a test payload to verify your endpoint is reachable.
              </Typography>
            </Box>

            {testResult && (
              <Alert severity={testResult.ok ? 'success' : 'error'} sx={{ mt: 1, py: 0.5, fontSize: '0.78rem' }}>
                {testResult.ok
                  ? `Success — HTTP ${testResult.status_code}`
                  : testResult.error || `HTTP ${testResult.status_code}`
                }
                {testResult.response_preview && (
                  <Typography fontSize="0.72rem" sx={{ mt: 0.5, fontFamily: 'monospace', opacity: 0.8, wordBreak: 'break-all' }}>
                    {testResult.response_preview.slice(0, 200)}
                  </Typography>
                )}
              </Alert>
            )}

            <Box sx={{ mt: 1.5, p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
              <Typography fontSize="0.72rem" color="text.secondary" fontWeight={600} mb={0.5}>Payload structure</Typography>
              <Typography fontSize="0.7rem" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', color: 'text.secondary' }}>
{`{
  "event": "meeting.created",
  "delivery_id": "uuid",
  "timestamp": "2026-05-04T12:00:00Z",
  "user_id": 42,
  "data": { ... }
}`}
              </Typography>
            </Box>
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Integrations() {
  const [hooks, setHooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await integrationWebhooks.list();
      setHooks(data.webhooks || []);
    } catch {
      setError('Failed to load webhooks.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => { setEditTarget(null); setDialogOpen(true); };
  const openEdit = (hook) => { setEditTarget(hook); setDialogOpen(true); };

  const handleSave = async (form) => {
    if (editTarget) {
      const { data } = await integrationWebhooks.update(editTarget.id, form);
      setHooks(prev => prev.map(h => h.id === editTarget.id ? data.webhook : h));
    } else {
      const { data } = await integrationWebhooks.create(form);
      setHooks(prev => [data.webhook, ...prev]);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this webhook?')) return;
    await integrationWebhooks.remove(id);
    setHooks(prev => prev.filter(h => h.id !== id));
  };

  const handleToggle = async (hook) => {
    const { data } = await integrationWebhooks.update(hook.id, { is_active: !hook.is_active });
    setHooks(prev => prev.map(h => h.id === hook.id ? data.webhook : h));
  };

  const handleTest = (id) => integrationWebhooks.test(id);

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 760, mx: 'auto' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Webhook sx={{ fontSize: 24, color: 'primary.main' }} />
          <Typography variant="h5" fontWeight={700}>Integrations</Typography>
        </Box>
        <Button variant="contained" size="small" startIcon={<Add />} onClick={openCreate}>
          Add Webhook
        </Button>
      </Box>
      <Typography color="text.secondary" fontSize="0.88rem" mb={3}>
        Send Telegizer events to n8n, Make, Zapier, or any custom automation tool.
      </Typography>

      {/* How it works */}
      <Card variant="outlined" sx={{ mb: 3, bgcolor: 'rgba(37,99,235,0.04)', borderColor: 'primary.light' }}>
        <CardContent sx={{ py: '12px !important' }}>
          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
            <Info sx={{ fontSize: 18, color: 'primary.main', mt: 0.1 }} />
            <Box>
              <Typography fontWeight={600} fontSize="0.88rem" mb={0.5}>How it works</Typography>
              <Typography fontSize="0.82rem" color="text.secondary">
                When events happen in Telegizer (meeting created, reminder set, etc.), we POST a JSON payload
                to your webhook URL. In <strong>n8n</strong>: add a Webhook node, copy its URL here, choose
                your events, and build your automation. Requests are signed with{' '}
                <code style={{ fontSize: '0.78rem' }}>X-Telegizer-Signature</code> if you set a secret.
              </Typography>
            </Box>
          </Box>
        </CardContent>
      </Card>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={28} /></Box>
      ) : hooks.length === 0 ? (
        <Box sx={{ textAlign: 'center', py: 6 }}>
          <Webhook sx={{ fontSize: 48, color: 'text.disabled', mb: 1.5 }} />
          <Typography fontWeight={600} mb={0.5}>No webhooks yet</Typography>
          <Typography fontSize="0.84rem" color="text.secondary" mb={2}>
            Add your first webhook to start sending Telegizer events to n8n or any automation tool.
          </Typography>
          <Button variant="contained" startIcon={<Add />} onClick={openCreate}>Add Webhook</Button>
        </Box>
      ) : (
        hooks.map(hook => (
          <WebhookRow
            key={hook.id}
            hook={hook}
            onEdit={openEdit}
            onDelete={handleDelete}
            onToggle={handleToggle}
            onTest={handleTest}
          />
        ))
      )}

      <WebhookFormDialog
        open={dialogOpen}
        initial={editTarget}
        onClose={() => setDialogOpen(false)}
        onSave={handleSave}
      />
    </Box>
  );
}
