import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, CircularProgress,
  Alert, IconButton, Select, MenuItem, FormControl, InputLabel,
  TextField, Dialog, DialogTitle, DialogContent, DialogActions,
  Divider, Tooltip, Switch,
} from '@mui/material';
import {
  AutoMode, Add, Delete, ArrowDownward, Edit, PlayArrow,
  Close, CheckCircle, Error as ErrorIcon, Bolt,
} from '@mui/icons-material';
import { automations as autoApi, telegramGroups as groupsApi } from '../services/api';
import PlanGate from '../components/PlanGate';

function _getUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

// ── Config definitions ────────────────────────────────────────────────────────

const TRIGGER_TYPES = [
  { value: 'message_received',  label: 'Message received in group' },
  { value: 'member_joined',     label: 'Member joins group' },
  { value: 'member_banned',     label: 'Member is banned' },
  { value: 'scheduled',         label: 'Scheduled (cron)' },
];

const CONDITION_TYPES = [
  { value: 'message_contains',  label: 'Message contains keyword' },
  { value: 'sender_is_admin',   label: 'Sender is admin' },
  { value: 'group_matches',     label: 'Specific group' },
];

const ACTION_TYPES = [
  { value: 'send_dm',           label: 'Send DM to admin' },
  { value: 'notify_admin_dm',   label: 'Notify all admins' },
  { value: 'forward_message',   label: 'Forward message to group' },
  { value: 'send_group_message',label: 'Send message to group' },
  { value: 'ban_user',          label: 'Ban the triggering user' },
];

// ── Small building blocks ─────────────────────────────────────────────────────

function NodeBox({ color = 'primary.main', icon, title, subtitle, children, onDelete, corner }) {
  return (
    <Card variant="outlined" sx={{ borderColor: color, position: 'relative' }}>
      <CardContent sx={{ pb: '12px !important' }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, mb: children ? 1.5 : 0 }}>
          <Box sx={{ p: 0.75, borderRadius: 1.5, bgcolor: `${color}22`, flexShrink: 0 }}>
            {React.cloneElement(icon, { sx: { fontSize: 16, color } })}
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography fontSize="0.75rem" fontWeight={700} color={color} textTransform="uppercase" letterSpacing={0.5}>
              {title}
            </Typography>
            {subtitle && <Typography fontSize="0.83rem" fontWeight={500} noWrap>{subtitle}</Typography>}
          </Box>
          {corner}
          {onDelete && (
            <IconButton size="small" onClick={onDelete} sx={{ ml: 0.5 }}>
              <Close sx={{ fontSize: 14 }} />
            </IconButton>
          )}
        </Box>
        {children}
      </CardContent>
    </Card>
  );
}

function ConnectorArrow() {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', py: 0.5 }}>
      <ArrowDownward sx={{ fontSize: 20, color: 'text.disabled' }} />
    </Box>
  );
}

function ParamField({ label, value, onChange, type = 'text', placeholder }) {
  return (
    <TextField
      label={label} value={value || ''} onChange={e => onChange(e.target.value)}
      size="small" fullWidth type={type} placeholder={placeholder}
      sx={{ mt: 1 }}
    />
  );
}

// ── Trigger node ─────────────────────────────────────────────────────────────

function TriggerNode({ trigger, groups, onChange }) {
  return (
    <NodeBox color="#2196f3" icon={<Bolt />} title="Trigger" subtitle={TRIGGER_TYPES.find(t => t.value === trigger.type)?.label || 'Select trigger'}>
      <FormControl size="small" fullWidth>
        <InputLabel>Event</InputLabel>
        <Select value={trigger.type || ''} label="Event" onChange={e => onChange({ type: e.target.value, params: {} })}>
          {TRIGGER_TYPES.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
        </Select>
      </FormControl>
      {trigger.type === 'scheduled' && (
        <ParamField label="Cron expression (e.g. 0 9 * * 1)" value={trigger.params?.cron}
          onChange={v => onChange({ ...trigger, params: { ...trigger.params, cron: v } })}
          placeholder="0 9 * * 1" />
      )}
      {trigger.type === 'message_received' && (
        <FormControl size="small" fullWidth sx={{ mt: 1 }}>
          <InputLabel>Group (optional)</InputLabel>
          <Select value={trigger.params?.group_id || ''} label="Group (optional)"
            onChange={e => onChange({ ...trigger, params: { ...trigger.params, group_id: e.target.value } })}>
            <MenuItem value="">Any group</MenuItem>
            {groups.map(g => <MenuItem key={g.id} value={g.telegram_group_id}>{g.title || g.telegram_group_id}</MenuItem>)}
          </Select>
        </FormControl>
      )}
    </NodeBox>
  );
}

// ── Condition node ────────────────────────────────────────────────────────────

function ConditionNode({ condition, groups, onChange, onDelete }) {
  const def = CONDITION_TYPES.find(c => c.value === condition.type);
  return (
    <NodeBox color="#ff9800" icon={<CheckCircle />} title="Condition" subtitle={def?.label || 'Select condition'} onDelete={onDelete}>
      <FormControl size="small" fullWidth>
        <InputLabel>Condition</InputLabel>
        <Select value={condition.type || ''} label="Condition"
          onChange={e => onChange({ type: e.target.value, params: {} })}>
          {CONDITION_TYPES.map(c => <MenuItem key={c.value} value={c.value}>{c.label}</MenuItem>)}
        </Select>
      </FormControl>
      {condition.type === 'message_contains' && (
        <ParamField label="Keyword" value={condition.params?.keyword}
          onChange={v => onChange({ ...condition, params: { ...condition.params, keyword: v } })}
          placeholder="spam, crypto, nsfw" />
      )}
      {condition.type === 'group_matches' && (
        <FormControl size="small" fullWidth sx={{ mt: 1 }}>
          <InputLabel>Group</InputLabel>
          <Select value={condition.params?.group_id || ''} label="Group"
            onChange={e => onChange({ ...condition, params: { ...condition.params, group_id: e.target.value } })}>
            {groups.map(g => <MenuItem key={g.id} value={g.telegram_group_id}>{g.title || g.telegram_group_id}</MenuItem>)}
          </Select>
        </FormControl>
      )}
    </NodeBox>
  );
}

// ── Action node ───────────────────────────────────────────────────────────────

function ActionNode({ action, groups, onChange, onDelete }) {
  const def = ACTION_TYPES.find(a => a.value === action.type);
  return (
    <NodeBox color="#4caf50" icon={<PlayArrow />} title="Action" subtitle={def?.label || 'Select action'} onDelete={onDelete}>
      <FormControl size="small" fullWidth>
        <InputLabel>Action</InputLabel>
        <Select value={action.type || ''} label="Action"
          onChange={e => onChange({ type: e.target.value, params: {} })}>
          {ACTION_TYPES.map(a => <MenuItem key={a.value} value={a.value}>{a.label}</MenuItem>)}
        </Select>
      </FormControl>
      {(action.type === 'send_dm' || action.type === 'send_group_message') && (
        <ParamField label="Message text" value={action.params?.message}
          onChange={v => onChange({ ...action, params: { ...action.params, message: v } })}
          placeholder="Your message here…" />
      )}
      {action.type === 'forward_message' && (
        <FormControl size="small" fullWidth sx={{ mt: 1 }}>
          <InputLabel>Target group</InputLabel>
          <Select value={action.params?.target_group_id || ''} label="Target group"
            onChange={e => onChange({ ...action, params: { ...action.params, target_group_id: e.target.value } })}>
            {groups.map(g => <MenuItem key={g.id} value={g.telegram_group_id}>{g.title || g.telegram_group_id}</MenuItem>)}
          </Select>
        </FormControl>
      )}
    </NodeBox>
  );
}

// ── Execution log ─────────────────────────────────────────────────────────────

function ExecLog({ wfId }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!wfId) return;
    autoApi.getExecutions(wfId)
      .then(({ data }) => setLogs(data.executions || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [wfId]);
  if (loading) return <CircularProgress size={20} />;
  if (logs.length === 0) return <Typography fontSize="0.82rem" color="text.secondary">No runs yet.</Typography>;
  return (
    <Box sx={{ maxHeight: 200, overflowY: 'auto' }}>
      {logs.slice(0, 20).map(l => (
        <Box key={l.id} sx={{ display: 'flex', gap: 1, alignItems: 'center', py: 0.4, borderBottom: '1px solid', borderColor: 'divider' }}>
          {l.status === 'success'
            ? <CheckCircle sx={{ fontSize: 14, color: 'success.main' }} />
            : <ErrorIcon sx={{ fontSize: 14, color: 'error.main' }} />}
          <Typography fontSize="0.75rem" color="text.secondary" flex={1} noWrap>
            {l.trigger_type}
          </Typography>
          <Typography fontSize="0.72rem" color="text.disabled">
            {new Date(l.executed_at).toLocaleString()}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

// ── Builder canvas ────────────────────────────────────────────────────────────

function BuilderCanvas({ workflow, groups, onChange }) {
  const { trigger, conditions, actions } = workflow;

  const updateCondition = (i, c) => onChange({ ...workflow, conditions: conditions.map((x, idx) => idx === i ? c : x) });
  const removeCondition = i => onChange({ ...workflow, conditions: conditions.filter((_, idx) => idx !== i) });
  const addCondition = () => onChange({ ...workflow, conditions: [...conditions, { type: '', params: {} }] });

  const updateAction = (i, a) => onChange({ ...workflow, actions: actions.map((x, idx) => idx === i ? a : x) });
  const removeAction = i => onChange({ ...workflow, actions: actions.filter((_, idx) => idx !== i) });
  const addAction = () => onChange({ ...workflow, actions: [...actions, { type: '', params: {} }] });

  return (
    <Box sx={{ maxWidth: 480, mx: 'auto' }}>
      <TriggerNode trigger={trigger} groups={groups} onChange={t => onChange({ ...workflow, trigger: t })} />

      <ConnectorArrow />

      {conditions.map((c, i) => (
        <React.Fragment key={i}>
          <ConditionNode condition={c} groups={groups}
            onChange={updated => updateCondition(i, updated)}
            onDelete={() => removeCondition(i)} />
          <ConnectorArrow />
        </React.Fragment>
      ))}

      <Box sx={{ textAlign: 'center', mb: 0.5 }}>
        <Button size="small" startIcon={<Add />} onClick={addCondition} sx={{ fontSize: '0.75rem' }}>
          Add Condition
        </Button>
      </Box>

      <ConnectorArrow />

      {actions.map((a, i) => (
        <React.Fragment key={i}>
          <ActionNode action={a} groups={groups}
            onChange={updated => updateAction(i, updated)}
            onDelete={actions.length > 1 ? () => removeAction(i) : undefined} />
          {i < actions.length - 1 && <ConnectorArrow />}
        </React.Fragment>
      ))}

      <Box sx={{ textAlign: 'center', mt: 0.5 }}>
        <Button size="small" startIcon={<Add />} onClick={addAction} sx={{ fontSize: '0.75rem' }}>
          Add Action
        </Button>
      </Box>
    </Box>
  );
}

// ── Workflow list card ────────────────────────────────────────────────────────

function WorkflowCard({ wf, onEdit, onToggle, onDelete }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <Card variant="outlined">
      <CardContent sx={{ pb: '12px !important' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <AutoMode fontSize="small" color={wf.is_active ? 'success' : 'disabled'} />
          <Typography fontWeight={600} fontSize="0.9rem" flex={1} noWrap>{wf.name}</Typography>
          <Chip label={wf.is_active ? 'Active' : 'Paused'} size="small"
            color={wf.is_active ? 'success' : 'default'} sx={{ fontSize: '0.62rem', height: 18 }} />
          <Tooltip title="Toggle active"><Switch size="small" checked={wf.is_active} onChange={() => onToggle(wf)} /></Tooltip>
          <IconButton size="small" onClick={() => onEdit(wf)}><Edit sx={{ fontSize: 16 }} /></IconButton>
          <IconButton size="small" onClick={() => onDelete(wf.id)} color="error"><Delete sx={{ fontSize: 16 }} /></IconButton>
        </Box>
        <Typography fontSize="0.75rem" color="text.secondary" mt={0.5}>
          Trigger: {TRIGGER_TYPES.find(t => t.value === wf.trigger?.type)?.label || wf.trigger?.type} ·
          {wf.conditions?.length || 0} condition{wf.conditions?.length !== 1 ? 's' : ''} ·
          {wf.actions?.length || 0} action{wf.actions?.length !== 1 ? 's' : ''} ·
          Run {wf.run_count} time{wf.run_count !== 1 ? 's' : ''}
        </Typography>
        <Button size="small" sx={{ mt: 0.5, fontSize: '0.72rem', px: 0 }}
          onClick={() => setExpanded(v => !v)}>
          {expanded ? 'Hide' : 'Show'} run history
        </Button>
        {expanded && <Box sx={{ mt: 1 }}><ExecLog wfId={wf.id} /></Box>}
      </CardContent>
    </Card>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const BLANK_WF = () => ({ name: '', trigger: { type: '', params: {} }, conditions: [], actions: [{ type: '', params: {} }] });

export default function WorkflowBuilder() {
  const [workflows, setWorkflows] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editWf, setEditWf] = useState(null);
  const [draftWf, setDraftWf] = useState(BLANK_WF());
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [wr, gr] = await Promise.all([autoApi.listWorkflows(), groupsApi.list()]);
      setWorkflows(wr.data.workflows || []);
      setGroups(gr.data.groups || []);
    } catch { setError('Failed to load.'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openNew = () => { setEditWf(null); setDraftWf(BLANK_WF()); setDialogOpen(true); };
  const openEdit = wf => {
    setEditWf(wf);
    setDraftWf({ name: wf.name, trigger: wf.trigger, conditions: wf.conditions || [], actions: wf.actions || [] });
    setDialogOpen(true);
  };

  const save = async () => {
    if (!draftWf.name.trim() || !draftWf.trigger.type || !draftWf.actions.some(a => a.type)) return;
    setSaving(true);
    try {
      if (editWf) {
        const { data } = await autoApi.updateWorkflow(editWf.id, draftWf);
        setWorkflows(prev => prev.map(w => w.id === editWf.id ? data.workflow : w));
      } else {
        const { data } = await autoApi.createWorkflow(draftWf);
        setWorkflows(prev => [data.workflow, ...prev]);
      }
      setDialogOpen(false);
    } catch (e) {
      setError(e.response?.data?.error || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const toggle = async wf => {
    try {
      const { data } = await autoApi.toggleWorkflow(wf.id);
      setWorkflows(prev => prev.map(w => w.id === wf.id ? { ...w, is_active: data.workflow?.is_active ?? !w.is_active } : w));
    } catch { load(); }
  };

  const deleteWf = async id => {
    setWorkflows(prev => prev.filter(w => w.id !== id));
    try { await autoApi.deleteWorkflow(id); } catch { load(); }
  };

  const user = _getUser();

  return (
    <PlanGate plan="pro" userTier={user.subscription_tier} feature="Workflow Builder">
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 900, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <AutoMode sx={{ fontSize: 26, color: 'primary.main' }} />
          <Typography variant="h5" fontWeight={700}>Workflow Builder</Typography>
        </Box>
        <Button variant="contained" size="small" startIcon={<Add />} onClick={openNew}>
          New Workflow
        </Button>
      </Box>
      <Typography color="text.secondary" fontSize="0.88rem" mb={3}>
        Build trigger → condition → action automations visually
      </Typography>

      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={32} /></Box>
      ) : workflows.length === 0 ? (
        <Card variant="outlined" sx={{ textAlign: 'center', py: 8 }}>
          <AutoMode sx={{ fontSize: 48, color: 'text.disabled', mb: 1.5 }} />
          <Typography fontWeight={600} mb={0.5}>No workflows yet</Typography>
          <Typography color="text.secondary" fontSize="0.85rem" mb={2}>
            Automate actions in your groups with trigger → condition → action flows.
          </Typography>
          <Button variant="contained" startIcon={<Add />} onClick={openNew}>Create First Workflow</Button>
        </Card>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {workflows.map(wf => (
            <WorkflowCard key={wf.id} wf={wf} onEdit={openEdit} onToggle={toggle} onDelete={deleteWf} />
          ))}
        </Box>
      )}

      {/* Builder dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          {editWf ? 'Edit Workflow' : 'New Workflow'}
          <IconButton size="small" onClick={() => setDialogOpen(false)}><Close fontSize="small" /></IconButton>
        </DialogTitle>
        <DialogContent sx={{ pt: '16px !important' }}>
          <TextField
            label="Workflow name" value={draftWf.name}
            onChange={e => setDraftWf(w => ({ ...w, name: e.target.value }))}
            size="small" fullWidth sx={{ mb: 3 }} placeholder="e.g. Spam keyword alert"
          />
          <Divider sx={{ mb: 3 }}>
            <Chip label="Visual Builder" size="small" />
          </Divider>
          <BuilderCanvas workflow={draftWf} groups={groups} onChange={setDraftWf} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={save}
            disabled={saving || !draftWf.name.trim() || !draftWf.trigger.type}
          >
            {saving ? <CircularProgress size={18} /> : (editWf ? 'Save Changes' : 'Create Workflow')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
    </PlanGate>
  );
}
