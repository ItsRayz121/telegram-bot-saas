import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Button, Card, CardContent, Chip, CircularProgress,
  Alert, TextField, IconButton, Tooltip, Dialog, DialogTitle,
  DialogContent, DialogActions, Select, MenuItem, FormControl,
  InputLabel, Checkbox, ListItemText, OutlinedInput, Tabs, Tab,
  Divider, Collapse,
} from '@mui/material';
import {
  Add, Delete, CheckCircle, Warning, ContentCopy, PlayArrow,
  OpenInNew, ExpandMore, ExpandLess, Bolt, Code,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { integrationWebhooks as whApi } from '../services/api';
import TopNav from '../components/TopNav';

const STATUS_COLOR = { ok: 'success', error: 'error' };

// ── Event selector ─────────────────────────────────────────────────────────────
function EventPicker({ selected, onChange, eventTypes }) {
  return (
    <FormControl fullWidth size="small">
      <InputLabel>Events to subscribe</InputLabel>
      <Select
        multiple
        value={selected}
        onChange={e => onChange(e.target.value)}
        input={<OutlinedInput label="Events to subscribe" />}
        renderValue={vals => (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {vals.map(v => <Chip key={v} label={v} size="small" />)}
          </Box>
        )}
      >
        {eventTypes.map(et => (
          <MenuItem key={et.event} value={et.event}>
            <Checkbox checked={selected.includes(et.event)} size="small" />
            <ListItemText
              primary={et.label}
              secondary={et.description}
              primaryTypographyProps={{ variant: 'body2', fontWeight: 600 }}
              secondaryTypographyProps={{ variant: 'caption' }}
            />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

// ── Create webhook dialog ──────────────────────────────────────────────────────
function CreateDialog({ open, onClose, onCreated, eventTypes }) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [secret, setSecret] = useState('');
  const [events, setEvents] = useState([]);
  const [saving, setSaving] = useState(false);

  const reset = () => { setName(''); setUrl(''); setSecret(''); setEvents([]); };

  const handleCreate = async () => {
    if (!name.trim() || !url.trim() || events.length === 0) {
      toast.error('Name, URL and at least one event are required');
      return;
    }
    setSaving(true);
    try {
      const { data } = await whApi.create({ name: name.trim(), url: url.trim(), secret: secret.trim() || undefined, events });
      onCreated(data.webhook);
      reset();
      onClose();
      toast.success('Webhook created');
    } catch (e) {
      toast.error(e?.response?.data?.error || 'Failed to create webhook');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>New Outbound Webhook</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
        <TextField size="small" label="Name" value={name} onChange={e => setName(e.target.value)} fullWidth placeholder="e.g. Notify Slack" />
        <TextField size="small" label="Destination URL" value={url} onChange={e => setUrl(e.target.value)} fullWidth placeholder="https://hooks.zapier.com/..." />
        <TextField size="small" label="Secret (optional)" value={secret} onChange={e => setSecret(e.target.value)} fullWidth placeholder="Random string for HMAC signing" helperText="We'll send X-Telegizer-Signature with each request" />
        <EventPicker selected={events} onChange={setEvents} eventTypes={eventTypes} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleCreate} disabled={saving}>
          {saving ? <CircularProgress size={18} /> : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Webhook row ────────────────────────────────────────────────────────────────
function WebhookRow({ hook, onDelete, onTestResult }) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [expanded, setExpanded] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    try {
      const { data } = await whApi.test(hook.id);
      setTestResult(data);
      onTestResult && onTestResult(hook.id, data.ok);
      toast[data.ok ? 'success' : 'error'](data.ok ? 'Test delivered!' : `Test failed: ${data.error || data.status_code}`);
    } catch {
      toast.error('Test request failed');
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card variant="outlined" sx={{ mb: 1.5 }}>
      <CardContent sx={{ pb: '12px !important' }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, mb: 0.5 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <Typography variant="body2" fontWeight={700}>{hook.name}</Typography>
              {hook.last_status && (
                <Chip
                  label={hook.last_status === 'ok' ? 'Active' : `Error: ${hook.last_error?.slice(0, 40)}`}
                  color={STATUS_COLOR[hook.last_status] || 'default'}
                  size="small"
                  icon={hook.last_status === 'ok' ? <CheckCircle sx={{ fontSize: '12px !important' }} /> : <Warning sx={{ fontSize: '12px !important' }} />}
                />
              )}
              {!hook.is_active && <Chip label="Disabled" color="error" size="small" />}
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
              {hook.url}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 0.5, flexShrink: 0 }}>
            <Tooltip title="Send test event">
              <IconButton size="small" onClick={handleTest} disabled={testing}>
                {testing ? <CircularProgress size={16} /> : <PlayArrow sx={{ fontSize: 16 }} />}
              </IconButton>
            </Tooltip>
            <Tooltip title="Delete">
              <IconButton size="small" onClick={() => onDelete(hook.id)} color="error">
                <Delete sx={{ fontSize: 16 }} />
              </IconButton>
            </Tooltip>
            <IconButton size="small" onClick={() => setExpanded(v => !v)}>
              {expanded ? <ExpandLess sx={{ fontSize: 16 }} /> : <ExpandMore sx={{ fontSize: 16 }} />}
            </IconButton>
          </Box>
        </Box>

        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
          {(hook.events || []).map(e => (
            <Chip key={e} label={e} size="small" variant="outlined" sx={{ fontSize: '0.68rem', height: 20 }} />
          ))}
        </Box>

        <Collapse in={expanded}>
          <Box sx={{ mt: 1.5, pt: 1.5, borderTop: '1px solid', borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary">
              Failures: {hook.failure_count || 0} &nbsp;·&nbsp;
              Last triggered: {hook.last_triggered_at ? new Date(hook.last_triggered_at).toLocaleString() : 'never'}
            </Typography>
            {testResult && (
              <Alert severity={testResult.ok ? 'success' : 'error'} sx={{ mt: 1, fontSize: '0.78rem' }}>
                {testResult.ok ? `HTTP ${testResult.status_code} — delivery confirmed` : testResult.error || `HTTP ${testResult.status_code}`}
                {testResult.response_preview && (
                  <Box component="pre" sx={{ mt: 0.5, fontSize: '0.72rem', overflow: 'auto', maxHeight: 80 }}>
                    {testResult.response_preview}
                  </Box>
                )}
              </Alert>
            )}
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ── Event catalog ──────────────────────────────────────────────────────────────
function EventCatalog({ eventTypes }) {
  const [open, setOpen] = useState(null);
  return (
    <Box>
      {eventTypes.map(et => (
        <Card key={et.event} variant="outlined" sx={{ mb: 1 }}>
          <CardContent sx={{ pb: '8px !important' }}>
            <Box
              sx={{ display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer' }}
              onClick={() => setOpen(open === et.event ? null : et.event)}
            >
              <Bolt sx={{ fontSize: 16, color: 'primary.main' }} />
              <Box sx={{ flex: 1 }}>
                <Typography variant="body2" fontWeight={700}>{et.label}</Typography>
                <Typography variant="caption" color="text.secondary">{et.description}</Typography>
              </Box>
              <Chip label={et.event} size="small" sx={{ fontFamily: 'monospace', fontSize: '0.68rem' }} />
              {open === et.event ? <ExpandLess sx={{ fontSize: 16 }} /> : <ExpandMore sx={{ fontSize: 16 }} />}
            </Box>
            <Collapse in={open === et.event}>
              <Box sx={{ mt: 1.5, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
                <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
                  Sample payload (data field):
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    fontSize: '0.75rem', bgcolor: 'action.hover',
                    p: 1.5, borderRadius: 1.5, overflow: 'auto',
                    border: '1px solid', borderColor: 'divider',
                    m: 0,
                  }}
                >
                  {JSON.stringify(et.sample, null, 2)}
                </Box>
              </Box>
            </Collapse>
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}

// ── Zapier / Make guides ───────────────────────────────────────────────────────
function ZapierGuide() {
  const [copied, setCopied] = useState('');
  const copy = (text, key) => {
    navigator.clipboard.writeText(text).then(() => { setCopied(key); setTimeout(() => setCopied(''), 2000); });
  };

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 3 }}>
        Telegizer works with <strong>Webhooks by Zapier</strong> — no separate Zapier app needed.
      </Alert>
      {[
        {
          num: '1',
          title: 'Create a Zap',
          body: 'In Zapier, create a new Zap and choose "Webhooks by Zapier" as the trigger. Select "Catch Hook" as the trigger event.',
        },
        {
          num: '2',
          title: 'Copy your Zapier webhook URL',
          body: 'Zapier gives you a unique URL like https://hooks.zapier.com/hooks/catch/... Copy it.',
        },
        {
          num: '3',
          title: 'Add it to Telegizer',
          body: 'In the Webhooks tab above, click "+ Add Webhook". Paste the Zapier URL and select the events you want to receive.',
        },
        {
          num: '4',
          title: 'Test the connection',
          body: 'Click the ▶ test button on your webhook. Then go back to Zapier and click "Test trigger" — you\'ll see the sample payload.',
        },
        {
          num: '5',
          title: 'Build your Zap action',
          body: 'Map the payload fields (event.data.title, event.data.scheduled_at, etc.) to your Zap action — Slack, Gmail, Notion, Airtable, whatever you need.',
        },
      ].map(({ num, title, body }) => (
        <Box key={num} sx={{ display: 'flex', gap: 2, mb: 2.5 }}>
          <Box sx={{
            width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
            bgcolor: '#FF4A00', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Typography variant="caption" fontWeight={700} color="white">{num}</Typography>
          </Box>
          <Box>
            <Typography variant="body2" fontWeight={700} gutterBottom>{title}</Typography>
            <Typography variant="body2" color="text.secondary">{body}</Typography>
          </Box>
        </Box>
      ))}

      <Divider sx={{ my: 3 }} />
      <Typography variant="body2" fontWeight={600} mb={1}>Payload structure</Typography>
      <Box
        component="pre"
        sx={{ fontSize: '0.76rem', bgcolor: 'action.hover', p: 2, borderRadius: 2, overflow: 'auto', border: '1px solid', borderColor: 'divider', m: 0 }}
      >
{`{
  "event": "meeting.created",
  "delivery_id": "uuid",
  "timestamp": "2026-06-01T14:00:00Z",
  "user_id": 42,
  "data": {
    // event-specific fields — see Event Catalog tab
  }
}`}
      </Box>
      <Box sx={{ display: 'flex', gap: 1, mt: 1.5 }}>
        <Button size="small" variant="outlined" startIcon={<ContentCopy />}
          onClick={() => copy('X-Telegizer-Signature', 'sig')}>
          {copied === 'sig' ? 'Copied!' : 'Copy signature header name'}
        </Button>
        <Button size="small" variant="outlined" startIcon={<OpenInNew />}
          href="https://zapier.com/apps/webhook" target="_blank" rel="noopener noreferrer">
          Open Zapier
        </Button>
      </Box>
    </Box>
  );
}

function MakeGuide() {
  return (
    <Box>
      <Alert severity="info" sx={{ mb: 3 }}>
        Use Make's built-in <strong>Webhooks → Custom Webhook</strong> module as your trigger.
      </Alert>
      {[
        { num: '1', title: 'Add a Custom Webhook trigger', body: 'In Make, create a new scenario. Add the "Webhooks" module and choose "Custom Webhook" as the trigger.' },
        { num: '2', title: 'Copy the webhook address', body: 'Make generates a unique URL. Copy it — it looks like https://hook.eu1.make.com/...' },
        { num: '3', title: 'Register it in Telegizer', body: 'In the Webhooks tab, click "+ Add Webhook", paste the Make URL, and choose your events.' },
        { num: '4', title: 'Test and map fields', body: 'Click ▶ test on your webhook, then in Make click "Run once" — it\'ll capture the payload. Map event.data fields to your Make modules (Slack, Notion, Google Sheets, etc.).' },
      ].map(({ num, title, body }) => (
        <Box key={num} sx={{ display: 'flex', gap: 2, mb: 2.5 }}>
          <Box sx={{
            width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
            bgcolor: '#6D00CC', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Typography variant="caption" fontWeight={700} color="white">{num}</Typography>
          </Box>
          <Box>
            <Typography variant="body2" fontWeight={700} gutterBottom>{title}</Typography>
            <Typography variant="body2" color="text.secondary">{body}</Typography>
          </Box>
        </Box>
      ))}
      <Divider sx={{ my: 2 }} />
      <Button size="small" variant="outlined" startIcon={<OpenInNew />}
        href="https://make.com" target="_blank" rel="noopener noreferrer">
        Open Make
      </Button>
    </Box>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function Integrations() {
  const [tab, setTab] = useState(0);
  const [hooks, setHooks] = useState([]);
  const [eventTypes, setEventTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const [listRes, typesRes] = await Promise.all([
        whApi.list(),
        whApi.eventTypes(),
      ]);
      setHooks(listRes.data.webhooks || []);
      setEventTypes(typesRes.data.events || []);
    } catch {
      toast.error('Failed to load integrations');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (id) => {
    try {
      await whApi.delete(id);
      setHooks(prev => prev.filter(h => h.id !== id));
      toast.success('Webhook deleted');
    } catch {
      toast.error('Failed to delete webhook');
    }
  };

  return (
    <Box>
      <TopNav
        hasSidebar
        breadcrumb={[{ label: 'Workspace', path: '/workspace' }, { label: 'Integrations' }]}
        actions={
          <Button variant="contained" size="small" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
            Add Webhook
          </Button>
        }
      />

      <Box sx={{ maxWidth: 800, mx: 'auto', px: { xs: 2, md: 3 }, py: 2.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
          <Code sx={{ fontSize: 24, color: 'primary.main' }} />
          <Typography variant="h5" fontWeight={700}>Integrations</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" mb={3}>
          Send real-time events to Zapier, Make, n8n, or any HTTP endpoint. Deliveries retry automatically on failure.
        </Typography>

        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Tab label={`Webhooks${hooks.length ? ` (${hooks.length})` : ''}`} />
          <Tab label="Event Catalog" />
          <Tab label="Zapier Setup" />
          <Tab label="Make Setup" />
        </Tabs>

        {/* ── Webhooks tab ── */}
        {tab === 0 && (
          loading ? <CircularProgress /> : hooks.length === 0 ? (
            <Card variant="outlined" sx={{ textAlign: 'center', py: 6, borderStyle: 'dashed' }}>
              <Bolt sx={{ fontSize: 40, color: 'text.disabled', mb: 1 }} />
              <Typography variant="h6" fontWeight={700} gutterBottom>No webhooks yet</Typography>
              <Typography variant="body2" color="text.secondary" mb={3} maxWidth={360} mx="auto">
                Add a webhook URL to start receiving real-time events in Zapier, Make, or your own service.
              </Typography>
              <Button variant="contained" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
                Add Your First Webhook
              </Button>
            </Card>
          ) : (
            hooks.map(h => (
              <WebhookRow key={h.id} hook={h} onDelete={handleDelete} />
            ))
          )
        )}

        {/* ── Event catalog tab ── */}
        {tab === 1 && <EventCatalog eventTypes={eventTypes} />}

        {/* ── Zapier tab ── */}
        {tab === 2 && <ZapierGuide />}

        {/* ── Make tab ── */}
        {tab === 3 && <MakeGuide />}
      </Box>

      <CreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={wh => setHooks(prev => [wh, ...prev])}
        eventTypes={eventTypes}
      />
    </Box>
  );
}
