import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, IconButton, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Select, MenuItem, FormControl, InputLabel, Alert, CircularProgress,
  Divider, Tooltip, Collapse, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Stack,
} from '@mui/material';
import {
  Add, Delete, AutoMode, ExpandMore, ExpandLess, PlayArrow, Pause,
  ArrowBack, BoltOutlined, ContentCopy,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { automations as autoApi, telegramGroups as tgApi } from '../services/api';
import PlanGate from '../components/PlanGate';
import { track } from '../services/analytics';
import { WebhooksSection } from '../components/WebhooksSection';

function _getUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

const TRIGGER_LABELS = {
  message_received: 'Message received',
  member_joined: 'Member joined',
  member_banned: 'Member banned',
  scheduled: 'Scheduled (daily)',
};

const ACTION_LABELS = {
  notify_admin_dm: 'DM the admin',
  send_dm: 'DM the admin',
  send_group_message: 'Send message to group',
  forward_message: 'Forward message to chat',
  create_reminder: 'Create a reminder',
  ban_sender: 'Ban the sender',
  delete_message: 'Delete the message',
};

const CONDITION_LABELS = {
  message_contains: 'Message contains keyword',
  message_starts_with: 'Message starts with keyword',
};

const STATUS_COLOR = { success: 'success', failed: 'error', skipped: 'default' };

// ── Execution log ─────────────────────────────────────────────────────────────

function ExecutionLog({ wfId, open }) {
  const [execs, setExecs] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !wfId) return;
    setLoading(true);
    autoApi.getExecutions(wfId, { per_page: 20 })
      .then(r => setExecs(r.data.executions || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, wfId]);

  if (!open) return null;
  return (
    <Box sx={{ px: 2, pb: 2 }}>
      <Divider sx={{ mb: 2 }} />
      <Typography variant="caption" color="text.secondary" fontWeight={700} display="block" mb={1}>
        Recent Executions
      </Typography>
      {loading ? <CircularProgress size={18} /> : execs.length === 0 ? (
        <Typography variant="caption" color="text.disabled">No executions yet.</Typography>
      ) : (
        <TableContainer sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>Time</TableCell>
                <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>Trigger</TableCell>
                <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>Status</TableCell>
                <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>Detail</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {execs.map(e => (
                <TableRow key={e.id}>
                  <TableCell sx={{ fontSize: '0.7rem', py: 0.5, whiteSpace: 'nowrap' }}>
                    {new Date(e.executed_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </TableCell>
                  <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>{TRIGGER_LABELS[e.trigger_type] || e.trigger_type}</TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <Chip label={e.status} color={STATUS_COLOR[e.status] || 'default'} size="small" sx={{ height: 16, fontSize: '0.62rem' }} />
                  </TableCell>
                  <TableCell sx={{ fontSize: '0.7rem', py: 0.5, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: e.error_msg ? 'error.main' : 'text.disabled' }}>
                    {e.error_msg || (e.trigger_data?.text ? `"${e.trigger_data.text.slice(0, 40)}"` : '—')}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}

// ── Workflow card ─────────────────────────────────────────────────────────────

function WorkflowCard({ wf, groups, onToggle, onDelete }) {
  const [logsOpen, setLogsOpen] = useState(false);
  const sourceGroup = groups.find(g => g.telegram_group_id === wf.source_group_id);
  const triggerLabel = TRIGGER_LABELS[wf.trigger?.type] || wf.trigger?.type || '—';
  const actionLabels = (wf.actions || []).map(a => ACTION_LABELS[a.type] || a.type);

  return (
    <Card sx={{ mb: 2, opacity: wf.is_active ? 1 : 0.65, transition: 'opacity 0.2s' }}>
      <CardContent sx={{ p: 2, '&:last-child': { pb: logsOpen ? 0 : 2 } }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
          <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: 'rgba(16,185,129,0.1)', flexShrink: 0, mt: 0.25 }}>
            <AutoMode sx={{ fontSize: 18, color: '#10b981' }} />
          </Box>

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.5 }}>
              <Typography fontWeight={700} fontSize="0.9rem">{wf.name}</Typography>
              {!wf.is_active && <Chip label="Paused" size="small" sx={{ height: 18, fontSize: '0.62rem' }} />}
            </Box>

            {/* Trigger → Actions flow */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap', mb: 0.75 }}>
              <Chip label={`⚡ ${triggerLabel}`} size="small" color="primary" variant="outlined" sx={{ height: 20, fontSize: '0.65rem' }} />
              {(wf.conditions || []).map((c, i) => (
                <Chip key={i} label={`? ${CONDITION_LABELS[c.type] || c.type}`} size="small" color="warning" variant="outlined" sx={{ height: 20, fontSize: '0.65rem' }} />
              ))}
              {actionLabels.map((a, i) => (
                <Chip key={i} label={`→ ${a}`} size="small" color="success" variant="outlined" sx={{ height: 20, fontSize: '0.65rem' }} />
              ))}
            </Box>

            <Typography variant="caption" color="text.disabled">
              {sourceGroup ? `Group: ${sourceGroup.name}` : wf.source_group_id ? `Group: ${wf.source_group_id}` : 'All groups'}
              {' · '}
              {wf.run_count} runs
              {wf.last_run_at ? ` · Last: ${new Date(wf.last_run_at).toLocaleDateString()}` : ''}
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
            <Tooltip title={wf.is_active ? 'Pause' : 'Activate'}>
              <IconButton size="small" onClick={() => onToggle(wf.id)}>
                {wf.is_active ? <Pause fontSize="small" /> : <PlayArrow fontSize="small" />}
              </IconButton>
            </Tooltip>
            <Tooltip title="Delete">
              <IconButton size="small" color="error" onClick={() => onDelete(wf.id)}>
                <Delete fontSize="small" />
              </IconButton>
            </Tooltip>
            <IconButton size="small" onClick={() => setLogsOpen(o => !o)}>
              {logsOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
            </IconButton>
          </Box>
        </Box>

        <Collapse in={logsOpen}>
          <ExecutionLog wfId={wf.id} open={logsOpen} />
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ── Create dialog ─────────────────────────────────────────────────────────────

const EMPTY_FORM = {
  name: '',
  source_group_id: '',
  trigger_type: 'message_received',
  condition_type: '',
  condition_keyword: '',
  action_type: 'notify_admin_dm',
  action_message: '',
  action_destination: '',
  action_reminder_text: '',
  action_delay_minutes: 60,
};

function CreateDialog({ open, onClose, onCreated, groups, templates }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const set = f => e => setForm(prev => ({ ...prev, [f]: e.target.value }));

  const applyTemplate = (tpl) => {
    const t = tpl.trigger || {};
    const c = (tpl.conditions || [])[0] || {};
    const a = (tpl.actions || [])[0] || {};
    setForm(prev => ({
      ...prev,
      name: tpl.name,
      trigger_type: t.type || 'message_received',
      condition_type: c.type || '',
      condition_keyword: c.params?.keyword || '',
      action_type: a.type || 'notify_admin_dm',
      action_message: a.params?.message || '',
      action_destination: a.params?.destination_id || '',
      action_reminder_text: a.params?.text || '',
      action_delay_minutes: a.params?.delay_minutes || 60,
    }));
  };

  const buildPayload = () => {
    const trigger = { type: form.trigger_type };
    const conditions = [];
    if (form.condition_type) {
      conditions.push({ type: form.condition_type, params: { keyword: form.condition_keyword } });
    }
    const actionParams = {};
    if (['notify_admin_dm', 'send_dm', 'send_group_message'].includes(form.action_type)) {
      actionParams.message = form.action_message;
    }
    if (form.action_type === 'forward_message') {
      actionParams.destination_id = form.action_destination;
    }
    if (form.action_type === 'create_reminder') {
      actionParams.text = form.action_reminder_text;
      actionParams.delay_minutes = Number(form.action_delay_minutes);
    }
    const actions = [{ type: form.action_type, params: actionParams }];
    return {
      name: form.name,
      source_group_id: form.source_group_id || null,
      trigger,
      conditions,
      actions,
    };
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) { toast.error('Workflow name is required'); return; }
    if (!form.source_group_id) { toast.error('Select a source group'); return; }
    setSaving(true);
    try {
      const res = await autoApi.createWorkflow(buildPayload());
      onCreated(res.data.workflow);
      track('feature_used', { feature: 'automation' });
      setForm(EMPTY_FORM);
      onClose();
      toast.success('Workflow created');
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to create workflow');
    } finally {
      setSaving(false);
    }
  };

  const needsKeyword = ['message_contains', 'message_starts_with'].includes(form.condition_type);
  const needsMessage = ['notify_admin_dm', 'send_dm', 'send_group_message'].includes(form.action_type);
  const needsDest = form.action_type === 'forward_message';
  const needsReminder = form.action_type === 'create_reminder';

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle fontWeight={700}>New Automation Workflow</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>

        {/* Templates */}
        {templates.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1}>
              Start from a template
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
              {templates.map(tpl => (
                <Chip
                  key={tpl.id}
                  label={tpl.name}
                  size="small"
                  icon={<ContentCopy sx={{ fontSize: '0.75rem !important' }} />}
                  onClick={() => applyTemplate(tpl)}
                  clickable
                  variant="outlined"
                  sx={{ fontSize: '0.72rem' }}
                />
              ))}
            </Box>
            <Divider sx={{ mt: 2, mb: 2 }} />
          </Box>
        )}

        <TextField fullWidth label="Workflow name" size="small" sx={{ mb: 2 }}
          value={form.name} onChange={set('name')} />

        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel>Source group</InputLabel>
          <Select label="Source group" value={form.source_group_id} onChange={set('source_group_id')}>
            {groups.map(g => (
              <MenuItem key={g.telegram_group_id} value={g.telegram_group_id}>{g.name}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Typography variant="caption" color="text.secondary" fontWeight={700} display="block" mb={1}>
          TRIGGER — When this happens…
        </Typography>
        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel>Trigger</InputLabel>
          <Select label="Trigger" value={form.trigger_type} onChange={set('trigger_type')}>
            {Object.entries(TRIGGER_LABELS).map(([v, l]) => (
              <MenuItem key={v} value={v}>{l}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Typography variant="caption" color="text.secondary" fontWeight={700} display="block" mb={1}>
          CONDITION — Only if… (optional)
        </Typography>
        <FormControl fullWidth size="small" sx={{ mb: needsKeyword ? 1 : 2 }}>
          <InputLabel>Condition</InputLabel>
          <Select label="Condition" value={form.condition_type} onChange={set('condition_type')}>
            <MenuItem value="">No condition (always run)</MenuItem>
            {Object.entries(CONDITION_LABELS).map(([v, l]) => (
              <MenuItem key={v} value={v}>{l}</MenuItem>
            ))}
          </Select>
        </FormControl>
        {needsKeyword && (
          <TextField fullWidth label="Keyword" size="small" sx={{ mb: 2 }}
            value={form.condition_keyword} onChange={set('condition_keyword')} />
        )}

        <Typography variant="caption" color="text.secondary" fontWeight={700} display="block" mb={1}>
          ACTION — Then do this…
        </Typography>
        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel>Action</InputLabel>
          <Select label="Action" value={form.action_type} onChange={set('action_type')}>
            {Object.entries(ACTION_LABELS).filter(([v]) => v !== 'send_dm').map(([v, l]) => (
              <MenuItem key={v} value={v}>{l}</MenuItem>
            ))}
          </Select>
        </FormControl>
        {needsMessage && (
          <TextField fullWidth label="Message text" size="small" sx={{ mb: 2 }} multiline rows={2}
            value={form.action_message} onChange={set('action_message')} />
        )}
        {needsDest && (
          <TextField fullWidth label="Destination chat ID or @username" size="small" sx={{ mb: 2 }}
            value={form.action_destination} onChange={set('action_destination')} />
        )}
        {needsReminder && (
          <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
            <TextField fullWidth label="Reminder text" size="small"
              value={form.action_reminder_text} onChange={set('action_reminder_text')} />
            <TextField label="Delay (min)" size="small" type="number" sx={{ width: 120 }}
              value={form.action_delay_minutes} onChange={set('action_delay_minutes')} />
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={saving}
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <BoltOutlined />}>
          Create Workflow
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function WorkspaceAutomations() {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState([]);
  const [groups, setGroups] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(() => {
    autoApi.listWorkflows()
      .then(r => setWorkflows(r.data.workflows || []))
      .catch(() => toast.error('Failed to load workflows'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    tgApi.list().then(r => setGroups(r.data.groups || [])).catch(() => {});
    autoApi.listTemplates().then(r => setTemplates(r.data.templates || [])).catch(() => {});
  }, [load]);

  const handleToggle = async (id) => {
    try {
      const res = await autoApi.toggleWorkflow(id);
      setWorkflows(prev => prev.map(w => w.id === id ? res.data.workflow : w));
    } catch { toast.error('Failed to toggle workflow'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this workflow and its execution log?')) return;
    try {
      await autoApi.deleteWorkflow(id);
      setWorkflows(prev => prev.filter(w => w.id !== id));
      toast.success('Workflow deleted');
    } catch { toast.error('Failed to delete workflow'); }
  };

  const activeCount = workflows.filter(w => w.is_active).length;
  const user = _getUser();

  return (
    <PlanGate plan="pro" userTier={user.subscription_tier} feature="Workflow Automations">
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 900, mx: 'auto' }}>

      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
        <IconButton size="small" onClick={() => navigate('/workspace')} sx={{ mr: 0.5 }}>
          <ArrowBack fontSize="small" />
        </IconButton>
        <AutoMode sx={{ color: '#10b981' }} />
        <Typography variant="h5" fontWeight={700}>Automations</Typography>
        {activeCount > 0 && (
          <Chip label={`${activeCount} active`} size="small" color="success" sx={{ height: 20, fontSize: '0.65rem' }} />
        )}
      </Box>
      <Typography color="text.secondary" mb={3} pl={6}>
        Build workflows: trigger → condition → action. Runs automatically inside your groups — no code needed.
      </Typography>

      <Alert severity="info" sx={{ mb: 3 }}>
        Workflows fire on messages and member events in your connected groups.
        <strong> Tip:</strong> Start from a template to get going in seconds.
      </Alert>

      {/* Header bar */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="subtitle2" color="text.secondary">
          {workflows.length} workflow{workflows.length !== 1 ? 's' : ''}
        </Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
          New Workflow
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ py: 6, textAlign: 'center' }}><CircularProgress /></Box>
      ) : workflows.length === 0 ? (
        <Box sx={{ textAlign: 'center', py: 8, color: 'text.secondary' }}>
          <AutoMode sx={{ fontSize: 56, mb: 1.5, opacity: 0.4 }} />
          <Typography variant="h6" fontWeight={600} gutterBottom>No automations yet</Typography>
          <Typography variant="body2" mb={3}>
            Create your first automation to auto-respond to triggers in your groups.
          </Typography>
          <Button variant="contained" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
            New Automation
          </Button>
        </Box>
      ) : (
        workflows.map(wf => (
          <WorkflowCard key={wf.id} wf={wf} groups={groups} onToggle={handleToggle} onDelete={handleDelete} />
        ))
      )}

      <CreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={wf => setWorkflows(prev => [wf, ...prev])}
        groups={groups}
        templates={templates}
      />

      {/* ── Outbound Webhooks (n8n / Zapier / custom) ── */}
      <Divider sx={{ my: 4 }} />
      <WebhooksSection />

    </Box>
    </PlanGate>
  );
}
