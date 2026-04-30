import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, CircularProgress,
  Alert, Grid, IconButton, Tooltip, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, Select, MenuItem, FormControl, InputLabel,
  ToggleButtonGroup, ToggleButton, Divider, Menu,
} from '@mui/material';
import {
  CheckBox, Add, Edit, Delete, MoreVert, Psychology,
  FlagOutlined, Groups, RadioButtonUnchecked, CheckCircle,
} from '@mui/icons-material';
import { tasks as tasksApi, telegramGroups as groupsApi } from '../services/api';

const STATUS_CONFIG = {
  todo:  { label: 'To Do',       color: 'default',  icon: RadioButtonUnchecked },
  doing: { label: 'In Progress', color: 'warning',  icon: FlagOutlined },
  done:  { label: 'Done',        color: 'success',  icon: CheckCircle },
};
const PRIORITY_COLOR = { low: 'default', medium: 'primary', high: 'error' };

function TaskCard({ task, onEdit, onDelete, onStatusChange }) {
  const [anchorEl, setAnchorEl] = useState(null);
  const StatusIcon = STATUS_CONFIG[task.status]?.icon || RadioButtonUnchecked;

  return (
    <Card
      variant="outlined"
      sx={{
        mb: 1,
        borderLeft: 3,
        borderLeftColor: task.priority === 'high' ? 'error.main' : task.priority === 'medium' ? 'primary.main' : 'divider',
        opacity: task.status === 'done' ? 0.6 : 1,
      }}
    >
      <CardContent sx={{ py: '10px !important', px: 1.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Tooltip title="Cycle status">
            <IconButton
              size="small"
              onClick={() => onStatusChange(task)}
              sx={{ mt: -0.25, color: STATUS_CONFIG[task.status]?.color === 'success' ? 'success.main' : STATUS_CONFIG[task.status]?.color === 'warning' ? 'warning.main' : 'text.disabled' }}
            >
              <StatusIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </Tooltip>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              fontSize="0.87rem"
              fontWeight={500}
              sx={{ textDecoration: task.status === 'done' ? 'line-through' : 'none' }}
            >
              {task.title}
            </Typography>
            {task.description && (
              <Typography fontSize="0.75rem" color="text.secondary" sx={{ mt: 0.25 }} noWrap>
                {task.description}
              </Typography>
            )}
            <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
              <Chip label={task.priority} size="small" color={PRIORITY_COLOR[task.priority]} sx={{ fontSize: '0.62rem', height: 16 }} />
              {task.source !== 'manual' && (
                <Chip label={task.source} size="small" variant="outlined" sx={{ fontSize: '0.62rem', height: 16 }} />
              )}
              {task.due_at && (
                <Typography fontSize="0.68rem" color="text.disabled">
                  Due {new Date(task.due_at).toLocaleDateString()}
                </Typography>
              )}
            </Box>
          </Box>
          <IconButton size="small" onClick={e => setAnchorEl(e.currentTarget)}>
            <MoreVert fontSize="small" />
          </IconButton>
          <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
            <MenuItem onClick={() => { setAnchorEl(null); onEdit(task); }}>
              <Edit fontSize="small" sx={{ mr: 1 }} /> Edit
            </MenuItem>
            <MenuItem onClick={() => { setAnchorEl(null); onDelete(task.id); }} sx={{ color: 'error.main' }}>
              <Delete fontSize="small" sx={{ mr: 1 }} /> Delete
            </MenuItem>
          </Menu>
        </Box>
      </CardContent>
    </Card>
  );
}

function TaskDialog({ open, initial, groups, onClose, onSave }) {
  const [form, setForm] = useState({ title: '', description: '', status: 'todo', priority: 'medium', group_id: '', due_at: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({
        title: initial?.title || '',
        description: initial?.description || '',
        status: initial?.status || 'todo',
        priority: initial?.priority || 'medium',
        group_id: initial?.group_id || '',
        due_at: initial?.due_at ? initial.due_at.slice(0, 10) : '',
      });
    }
  }, [open, initial]);

  const save = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const payload = {
        ...form,
        due_at: form.due_at ? `${form.due_at}T00:00:00Z` : null,
        group_id: form.group_id || null,
      };
      await onSave(payload);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{initial ? 'Edit Task' : 'New Task'}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        <TextField label="Title" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
          fullWidth size="small" required />
        <TextField label="Description" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
          fullWidth size="small" multiline rows={2} />
        <Box sx={{ display: 'flex', gap: 1.5 }}>
          <FormControl size="small" sx={{ flex: 1 }}>
            <InputLabel>Priority</InputLabel>
            <Select value={form.priority} label="Priority" onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}>
              <MenuItem value="low">Low</MenuItem>
              <MenuItem value="medium">Medium</MenuItem>
              <MenuItem value="high">High</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ flex: 1 }}>
            <InputLabel>Status</InputLabel>
            <Select value={form.status} label="Status" onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
              <MenuItem value="todo">To Do</MenuItem>
              <MenuItem value="doing">In Progress</MenuItem>
              <MenuItem value="done">Done</MenuItem>
            </Select>
          </FormControl>
        </Box>
        <Box sx={{ display: 'flex', gap: 1.5 }}>
          <TextField label="Due Date" type="date" value={form.due_at}
            onChange={e => setForm(f => ({ ...f, due_at: e.target.value }))}
            size="small" sx={{ flex: 1 }} InputLabelProps={{ shrink: true }} />
          <FormControl size="small" sx={{ flex: 1 }}>
            <InputLabel>Group (optional)</InputLabel>
            <Select value={form.group_id} label="Group (optional)" onChange={e => setForm(f => ({ ...f, group_id: e.target.value }))}>
              <MenuItem value="">None</MenuItem>
              {groups.map(g => <MenuItem key={g.id} value={g.telegram_group_id}>{g.title || g.telegram_group_id}</MenuItem>)}
            </Select>
          </FormControl>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={saving || !form.title.trim()}>
          {saving ? <CircularProgress size={18} /> : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ExtractDialog({ open, groups, onClose, onDone }) {
  const [groupId, setGroupId] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const extract = async () => {
    setLoading(true); setError(''); setResult(null);
    try {
      const { data } = await tasksApi.extract(groupId);
      setResult(data);
    } catch (e) {
      setError(e.response?.data?.error || 'Extraction failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Extract Tasks with AI</DialogTitle>
      <DialogContent sx={{ pt: '16px !important' }}>
        <Typography fontSize="0.85rem" color="text.secondary" mb={2}>
          AI will scan the last 48h of messages in a group and extract action items as tasks.
        </Typography>
        {result ? (
          <Alert severity="success">Created {result.created} task{result.created !== 1 ? 's' : ''} from group messages!</Alert>
        ) : (
          <>
            <FormControl size="small" fullWidth>
              <InputLabel>Select Group</InputLabel>
              <Select value={groupId} label="Select Group" onChange={e => setGroupId(e.target.value)}>
                {groups.map(g => <MenuItem key={g.id} value={g.telegram_group_id}>{g.title || g.telegram_group_id}</MenuItem>)}
              </Select>
            </FormControl>
            {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={result ? () => { onClose(); onDone(); } : onClose}>
          {result ? 'Done' : 'Cancel'}
        </Button>
        {!result && (
          <Button variant="contained" onClick={extract} disabled={!groupId || loading} startIcon={loading ? <CircularProgress size={16} /> : <Psychology />}>
            Extract
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

export default function AssistantTasks() {
  const [tasks, setTasks] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTask, setEditTask] = useState(null);
  const [extractOpen, setExtractOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [tr, gr] = await Promise.all([tasksApi.list(), groupsApi.list()]);
      setTasks(tr.data.tasks || []);
      setGroups(gr.data.groups || []);
    } catch {
      setError('Failed to load tasks.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const cycleStatus = async (task) => {
    const next = { todo: 'doing', doing: 'done', done: 'todo' };
    const updated = { ...task, status: next[task.status] };
    setTasks(prev => prev.map(t => t.id === task.id ? updated : t));
    try { await tasksApi.update(task.id, { status: updated.status }); } catch { load(); }
  };

  const saveTask = async (payload) => {
    if (editTask) {
      const { data } = await tasksApi.update(editTask.id, payload);
      setTasks(prev => prev.map(t => t.id === editTask.id ? data.task : t));
    } else {
      const { data } = await tasksApi.create(payload);
      setTasks(prev => [data.task, ...prev]);
    }
    setDialogOpen(false);
    setEditTask(null);
  };

  const deleteTask = async (id) => {
    setTasks(prev => prev.filter(t => t.id !== id));
    try { await tasksApi.delete(id); } catch { load(); }
  };

  const STATUSES = ['todo', 'doing', 'done'];
  const filtered = filterStatus ? tasks.filter(t => t.status === filterStatus) : tasks;
  const byStatus = STATUSES.reduce((acc, s) => ({ ...acc, [s]: filtered.filter(t => t.status === s) }), {});

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 860, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <CheckBox sx={{ fontSize: 26, color: 'primary.main' }} />
          <Typography variant="h5" fontWeight={700}>Tasks</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button size="small" variant="outlined" startIcon={<Psychology />} onClick={() => setExtractOpen(true)}>
            Extract with AI
          </Button>
          <Button size="small" variant="contained" startIcon={<Add />} onClick={() => { setEditTask(null); setDialogOpen(true); }}>
            New Task
          </Button>
        </Box>
      </Box>
      <Typography color="text.secondary" fontSize="0.88rem" mb={3}>
        Manage action items — created manually, from AI extraction, or via bot DM
      </Typography>

      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      <ToggleButtonGroup value={filterStatus} exclusive onChange={(_, v) => setFilterStatus(v || '')} size="small" sx={{ mb: 3 }}>
        <ToggleButton value="">All</ToggleButton>
        {STATUSES.map(s => (
          <ToggleButton key={s} value={s}>{STATUS_CONFIG[s].label}</ToggleButton>
        ))}
      </ToggleButtonGroup>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={32} /></Box>
      ) : tasks.length === 0 ? (
        <Card variant="outlined" sx={{ textAlign: 'center', py: 6 }}>
          <CheckBox sx={{ fontSize: 40, color: 'text.disabled', mb: 1 }} />
          <Typography color="text.secondary">No tasks yet. Create one or extract from group messages.</Typography>
        </Card>
      ) : filterStatus ? (
        /* Flat list when filtered */
        <Box>
          {filtered.length === 0 ? (
            <Typography color="text.secondary" fontSize="0.85rem">No tasks with status "{STATUS_CONFIG[filterStatus]?.label}".</Typography>
          ) : (
            filtered.map(t => (
              <TaskCard key={t.id} task={t} onEdit={task => { setEditTask(task); setDialogOpen(true); }}
                onDelete={deleteTask} onStatusChange={cycleStatus} />
            ))
          )}
        </Box>
      ) : (
        /* Kanban columns */
        <Grid container spacing={2}>
          {STATUSES.map(s => (
            <Grid item xs={12} md={4} key={s}>
              <Box sx={{ bgcolor: 'action.hover', borderRadius: 2, p: 1.5 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                  <Typography fontWeight={600} fontSize="0.88rem">{STATUS_CONFIG[s].label}</Typography>
                  <Chip label={byStatus[s].length} size="small" sx={{ height: 18, fontSize: '0.65rem' }} />
                </Box>
                {byStatus[s].length === 0 ? (
                  <Typography fontSize="0.78rem" color="text.disabled" sx={{ textAlign: 'center', py: 2 }}>Empty</Typography>
                ) : (
                  byStatus[s].map(t => (
                    <TaskCard key={t.id} task={t} onEdit={task => { setEditTask(task); setDialogOpen(true); }}
                      onDelete={deleteTask} onStatusChange={cycleStatus} />
                  ))
                )}
              </Box>
            </Grid>
          ))}
        </Grid>
      )}

      <TaskDialog open={dialogOpen} initial={editTask} groups={groups}
        onClose={() => { setDialogOpen(false); setEditTask(null); }}
        onSave={saveTask} />
      <ExtractDialog open={extractOpen} groups={groups}
        onClose={() => setExtractOpen(false)} onDone={load} />
    </Box>
  );
}
