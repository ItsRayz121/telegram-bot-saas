import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, CircularProgress,
  Alert, Grid, IconButton, Tooltip, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, Select, MenuItem, FormControl, InputLabel,
  ToggleButtonGroup, ToggleButton, Menu,
} from '@mui/material';
import {
  CheckBox, Add, Edit, Delete, MoreVert,
  FlagOutlined, RadioButtonUnchecked, CheckCircle, RemoveCircleOutline,
} from '@mui/icons-material';
import { hub } from '../services/api';

const STATUS_CONFIG = {
  pending:   { label: 'Pending',     color: 'default', icon: RadioButtonUnchecked },
  confirmed: { label: 'In Progress', color: 'warning',  icon: FlagOutlined },
  done:      { label: 'Done',        color: 'success',  icon: CheckCircle },
  dismissed: { label: 'Dismissed',   color: 'default',  icon: RemoveCircleOutline },
};
const PRIORITY_COLOR = { low: 'default', normal: 'primary', high: 'error' };
const CYCLE = { pending: 'confirmed', confirmed: 'done', done: 'pending', dismissed: 'pending' };

function isOverdue(task) {
  if (!task.due_date || task.status === 'done' || task.status === 'dismissed') return false;
  return new Date(task.due_date) < new Date(new Date().toDateString());
}

function TaskCard({ task, onEdit, onDelete, onStatusChange }) {
  const [anchorEl, setAnchorEl] = useState(null);
  const cfg = STATUS_CONFIG[task.status] || STATUS_CONFIG.pending;
  const StatusIcon = cfg.icon;
  const overdue = isOverdue(task);

  return (
    <Card
      variant="outlined"
      sx={{
        mb: 1,
        borderLeft: 3,
        borderLeftColor: overdue ? 'error.main' : task.priority === 'high' ? 'error.main' : task.priority === 'normal' ? 'primary.main' : 'divider',
        opacity: task.status === 'done' || task.status === 'dismissed' ? 0.6 : 1,
      }}
    >
      <CardContent sx={{ py: '10px !important', px: 1.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Tooltip title="Cycle status">
            <IconButton
              size="small"
              onClick={() => onStatusChange(task)}
              sx={{
                mt: -0.25,
                color: cfg.color === 'success' ? 'success.main' : cfg.color === 'warning' ? 'warning.main' : 'text.disabled',
              }}
            >
              <StatusIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </Tooltip>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              fontSize="0.87rem"
              fontWeight={500}
              sx={{ textDecoration: task.status === 'done' || task.status === 'dismissed' ? 'line-through' : 'none' }}
            >
              {task.title}
            </Typography>
            <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
              <Chip label={task.priority} size="small" color={PRIORITY_COLOR[task.priority] || 'default'} sx={{ fontSize: '0.62rem', height: 16 }} />
              {task.source === 'extracted' && (
                <Chip label="AI" size="small" variant="outlined" color="secondary" sx={{ fontSize: '0.62rem', height: 16 }} />
              )}
              {task.assignee_name && (
                <Typography fontSize="0.68rem" color="text.secondary">@{task.assignee_name}</Typography>
              )}
              {task.due_date && (
                <Typography fontSize="0.68rem" color={overdue ? 'error.main' : 'text.disabled'}>
                  {overdue ? 'Overdue · ' : 'Due '}
                  {new Date(task.due_date).toLocaleDateString()}
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
  const [form, setForm] = useState({
    title: '', description: '', assignee_name: '',
    status: 'pending', priority: 'normal', source_group_id: '', due_date: '',
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({
        title: initial?.title || '',
        description: '',
        assignee_name: initial?.assignee_name || '',
        status: initial?.status || 'pending',
        priority: initial?.priority || 'normal',
        source_group_id: initial?.source_group_id || '',
        due_date: initial?.due_date ? initial.due_date.slice(0, 10) : '',
      });
    }
  }, [open, initial]);

  const save = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const payload = {
        ...form,
        due_date: form.due_date || null,
        source_group_id: form.source_group_id || null,
        description: form.description || null,
        assignee_name: form.assignee_name || null,
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
        <TextField label="Assignee" value={form.assignee_name} onChange={e => setForm(f => ({ ...f, assignee_name: e.target.value }))}
          fullWidth size="small" placeholder="e.g. John" />
        <Box sx={{ display: 'flex', gap: 1.5 }}>
          <FormControl size="small" sx={{ flex: 1 }}>
            <InputLabel>Priority</InputLabel>
            <Select value={form.priority} label="Priority" onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}>
              <MenuItem value="low">Low</MenuItem>
              <MenuItem value="normal">Normal</MenuItem>
              <MenuItem value="high">High</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ flex: 1 }}>
            <InputLabel>Status</InputLabel>
            <Select value={form.status} label="Status" onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
              <MenuItem value="pending">Pending</MenuItem>
              <MenuItem value="confirmed">In Progress</MenuItem>
              <MenuItem value="done">Done</MenuItem>
              <MenuItem value="dismissed">Dismissed</MenuItem>
            </Select>
          </FormControl>
        </Box>
        <Box sx={{ display: 'flex', gap: 1.5 }}>
          <TextField label="Due Date" type="date" value={form.due_date}
            onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))}
            size="small" sx={{ flex: 1 }} InputLabelProps={{ shrink: true }} />
          <FormControl size="small" sx={{ flex: 1 }}>
            <InputLabel>Group (optional)</InputLabel>
            <Select value={form.source_group_id} label="Group (optional)" onChange={e => setForm(f => ({ ...f, source_group_id: e.target.value }))}>
              <MenuItem value="">None</MenuItem>
              {groups.map(g => (
                <MenuItem key={g.id} value={g.id}>{g.group_name || g.telegram_group_id}</MenuItem>
              ))}
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

export default function AssistantTasks() {
  const [tasks, setTasks] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTask, setEditTask] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [tr, gr] = await Promise.all([hub.listTasks(), hub.listOfficialGroups()]);
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
    const next = CYCLE[task.status] || 'pending';
    const updated = { ...task, status: next };
    setTasks(prev => prev.map(t => t.id === task.id ? updated : t));
    try { await hub.updateTask(task.id, { status: next }); } catch { load(); }
  };

  const saveTask = async (payload) => {
    if (editTask) {
      const { data } = await hub.updateTask(editTask.id, payload);
      setTasks(prev => prev.map(t => t.id === editTask.id ? data.task : t));
    } else {
      const { data } = await hub.createTask(payload);
      setTasks(prev => [data.task, ...prev]);
    }
    setDialogOpen(false);
    setEditTask(null);
  };

  const deleteTask = async (id) => {
    setTasks(prev => prev.filter(t => t.id !== id));
    try { await hub.deleteTask(id); } catch { load(); }
  };

  const STATUSES = ['pending', 'confirmed', 'done', 'dismissed'];
  const filtered = filterStatus ? tasks.filter(t => t.status === filterStatus) : tasks;
  const activeStatuses = ['pending', 'confirmed', 'done'];
  const byStatus = activeStatuses.reduce((acc, s) => ({ ...acc, [s]: filtered.filter(t => t.status === s) }), {});

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 860, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <CheckBox sx={{ fontSize: 26, color: 'primary.main' }} />
          <Typography variant="h5" fontWeight={700}>Tasks</Typography>
        </Box>
        <Button size="small" variant="contained" startIcon={<Add />} onClick={() => { setEditTask(null); setDialogOpen(true); }}>
          New Task
        </Button>
      </Box>
      <Typography color="text.secondary" fontSize="0.88rem" mb={3}>
        Action items created manually or auto-extracted from group messages by Echo
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
        <Card variant="outlined" sx={{ textAlign: 'center', py: 6, px: 3 }}>
          <CheckBox sx={{ fontSize: 48, color: 'text.disabled', mb: 2 }} />
          <Typography variant="h6" gutterBottom>No tasks yet</Typography>
          <Typography color="text.secondary" mb={3}>
            Create a task manually or let Echo extract action items from your group messages automatically.
          </Typography>
          <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)}>
            Create Task
          </Button>
        </Card>
      ) : filterStatus ? (
        <Box>
          {filtered.length === 0 ? (
            <Typography color="text.secondary" fontSize="0.85rem">
              No tasks with status "{STATUS_CONFIG[filterStatus]?.label}".
            </Typography>
          ) : (
            filtered.map(t => (
              <TaskCard key={t.id} task={t}
                onEdit={task => { setEditTask(task); setDialogOpen(true); }}
                onDelete={deleteTask} onStatusChange={cycleStatus} />
            ))
          )}
        </Box>
      ) : (
        <Grid container spacing={2}>
          {activeStatuses.map(s => (
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
                    <TaskCard key={t.id} task={t}
                      onEdit={task => { setEditTask(task); setDialogOpen(true); }}
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
    </Box>
  );
}
