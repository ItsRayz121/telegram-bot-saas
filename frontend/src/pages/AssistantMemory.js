import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, CircularProgress,
  Alert, Grid, IconButton, TextField, Dialog, DialogTitle, DialogContent,
  DialogActions, Tabs, Tab, Tooltip, MenuItem, Select,
  FormControl, InputLabel,
} from '@mui/material';
import {
  ManageAccounts, Person, FolderSpecial, Add, Delete, Edit,
  Check, Close, AutoAwesome,
} from '@mui/icons-material';
import { hub as hubApi } from '../services/api';

const PROJECT_STATUSES = ['active', 'paused', 'completed', 'archived'];

// ── Small helpers ─────────────────────────────────────────────────────────────

function SectionHeader({ icon: Icon, title, subtitle, action }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 2 }}>
      <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
        <Icon sx={{ color: 'primary.main', fontSize: 22 }} />
        <Box>
          <Typography fontWeight={700} fontSize="1rem">{title}</Typography>
          {subtitle && <Typography fontSize="0.75rem" color="text.secondary">{subtitle}</Typography>}
        </Box>
      </Box>
      {action}
    </Box>
  );
}

// ── Global profile tab ────────────────────────────────────────────────────────

function GlobalTab() {
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await hubApi.getMemoryGlobal();
      setData(res.data.memory || {});
      setForm(res.data.memory || {});
    } catch {
      setData({});
      setForm({});
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      await hubApi.updateMemoryGlobal(form);
      setData(form);
      setEditing(false);
    } catch {
      setError('Failed to save. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  if (data === null) return <CircularProgress size={24} sx={{ mt: 3 }} />;

  const fields = [
    { key: 'preferred_name', label: 'Preferred Name', hint: 'What should the assistant call you?' },
    { key: 'company_name',   label: 'Company / Organisation', hint: '' },
    { key: 'role',           label: 'Your Role', hint: 'e.g. CEO, Community Manager' },
    { key: 'current_priorities', label: 'Current Priorities', hint: 'Key goals this month', multiline: true, rows: 3 },
    { key: 'free_notes',     label: 'Notes for the Assistant', hint: 'Anything you want it to always know', multiline: true, rows: 4 },
  ];

  return (
    <Box>
      <SectionHeader
        icon={ManageAccounts}
        title="Your Profile"
        subtitle="Context the assistant uses in every conversation"
        action={
          editing
            ? <Box sx={{ display: 'flex', gap: 1 }}>
                <Button size="small" onClick={() => { setEditing(false); setForm(data); }}>Cancel</Button>
                <Button size="small" variant="contained" onClick={save} disabled={saving}>
                  {saving ? 'Saving…' : 'Save'}
                </Button>
              </Box>
            : <Button size="small" startIcon={<Edit />} onClick={() => setEditing(true)}>Edit</Button>
        }
      />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Grid container spacing={2}>
        {fields.map(f => (
          <Grid item xs={12} sm={f.multiline ? 12 : 6} key={f.key}>
            {editing ? (
              <TextField
                fullWidth
                size="small"
                label={f.label}
                helperText={f.hint}
                multiline={!!f.multiline}
                rows={f.rows || 1}
                value={form[f.key] || ''}
                onChange={e => setForm(prev => ({ ...prev, [f.key]: e.target.value }))}
              />
            ) : (
              <Box>
                <Typography fontSize="0.72rem" color="text.disabled" mb={0.25}>{f.label}</Typography>
                <Typography fontSize="0.87rem" color={data[f.key] ? 'text.primary' : 'text.disabled'}>
                  {data[f.key] || '—'}
                </Typography>
              </Box>
            )}
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}

// ── People tab ────────────────────────────────────────────────────────────────

function PeopleTab() {
  const [people, setPeople] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [form, setForm] = useState({ name: '', role: '', notes: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await hubApi.listMemoryPeople();
      setPeople(res.data.people || []);
    } catch { setPeople([]); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openNew = () => { setEditTarget(null); setForm({ name: '', role: '', notes: '' }); setError(''); setDialogOpen(true); };
  const openEdit = p => { setEditTarget(p); setForm({ name: p.name, role: p.role || '', notes: p.notes || '' }); setError(''); setDialogOpen(true); };

  const save = async () => {
    if (!form.name.trim()) { setError('Name is required'); return; }
    setSaving(true);
    setError('');
    try {
      if (editTarget) {
        await hubApi.updateMemoryPerson(editTarget.id, form);
      } else {
        await hubApi.createMemoryPerson(form);
      }
      setDialogOpen(false);
      load();
    } catch (e) {
      const msg = e?.response?.data?.message || e?.response?.data?.error;
      if (msg === 'plan_limit') setError('Plan limit reached. Upgrade to add more people.');
      else setError('Failed to save.');
    } finally {
      setSaving(false);
    }
  };

  const deletePerson = async (id) => {
    if (!window.confirm('Delete this person from memory?')) return;
    try {
      await hubApi.deleteMemoryPerson(id);
      setPeople(prev => prev.filter(p => p.id !== id));
    } catch { /* ignore */ }
  };

  return (
    <Box>
      <SectionHeader
        icon={Person}
        title="People"
        subtitle="Team members, contacts, and collaborators the assistant knows about"
        action={<Button size="small" startIcon={<Add />} variant="outlined" onClick={openNew}>Add Person</Button>}
      />
      {people === null ? (
        <CircularProgress size={24} sx={{ mt: 2 }} />
      ) : people.length === 0 ? (
        <Alert severity="info" sx={{ mt: 1 }}>
          No people saved yet. Add people the assistant should know about — team members, clients, collaborators.
        </Alert>
      ) : (
        <Grid container spacing={1.5}>
          {people.map(p => (
            <Grid item xs={12} sm={6} md={4} key={p.id}>
              <Card variant="outlined" sx={{ height: '100%' }}>
                <CardContent sx={{ pb: '12px !important' }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <Box>
                      <Typography fontWeight={600} fontSize="0.88rem">{p.name}</Typography>
                      {p.role && <Typography fontSize="0.75rem" color="text.secondary">{p.role}</Typography>}
                    </Box>
                    <Box>
                      <Tooltip title="Edit"><IconButton size="small" onClick={() => openEdit(p)}><Edit fontSize="small" /></IconButton></Tooltip>
                      <Tooltip title="Delete"><IconButton size="small" color="error" onClick={() => deletePerson(p.id)}><Delete fontSize="small" /></IconButton></Tooltip>
                    </Box>
                  </Box>
                  {p.notes && (
                    <Typography fontSize="0.75rem" color="text.secondary" mt={0.75} sx={{
                      overflow: 'hidden', display: '-webkit-box',
                      WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                    }}>
                      {p.notes}
                    </Typography>
                  )}
                  {p.source === 'suggestion' && (
                    <Chip label="auto-detected" size="small" icon={<AutoAwesome sx={{ fontSize: '11px !important' }} />}
                      sx={{ mt: 1, fontSize: '0.65rem', height: 18 }} color="primary" variant="outlined" />
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{editTarget ? 'Edit Person' : 'Add Person'}</DialogTitle>
        <DialogContent sx={{ pt: '8px !important', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField autoFocus size="small" label="Name *" fullWidth value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
          <TextField size="small" label="Role / Title" fullWidth value={form.role} onChange={e => setForm(p => ({ ...p, role: e.target.value }))} />
          <TextField size="small" label="Notes" fullWidth multiline rows={3} value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} helperText="What should the assistant know about this person?" />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Projects tab ──────────────────────────────────────────────────────────────

function ProjectsTab() {
  const [projects, setProjects] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [form, setForm] = useState({ name: '', status: 'active', context_notes: '', deadline: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await hubApi.listMemoryProjects();
      setProjects(res.data.projects || []);
    } catch { setProjects([]); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openNew = () => {
    setEditTarget(null);
    setForm({ name: '', status: 'active', context_notes: '', deadline: '' });
    setError('');
    setDialogOpen(true);
  };
  const openEdit = pj => {
    setEditTarget(pj);
    setForm({ name: pj.name, status: pj.status || 'active', context_notes: pj.context_notes || '', deadline: pj.deadline ? pj.deadline.slice(0, 10) : '' });
    setError('');
    setDialogOpen(true);
  };

  const save = async () => {
    if (!form.name.trim()) { setError('Project name is required'); return; }
    setSaving(true);
    setError('');
    try {
      if (editTarget) {
        await hubApi.updateMemoryProject(editTarget.id, form);
      } else {
        await hubApi.createMemoryProject(form);
      }
      setDialogOpen(false);
      load();
    } catch (e) {
      const d = e?.response?.data;
      if (d?.error === 'plan_limit') setError('Plan limit reached. Upgrade to add more projects.');
      else setError('Failed to save.');
    } finally {
      setSaving(false);
    }
  };

  const deleteProject = async (id) => {
    if (!window.confirm('Delete this project from memory?')) return;
    try {
      await hubApi.deleteMemoryProject(id);
      setProjects(prev => prev.filter(p => p.id !== id));
    } catch { /* ignore */ }
  };

  const STATUS_COLOR = { active: 'success', paused: 'warning', completed: 'default', archived: 'default' };

  return (
    <Box>
      <SectionHeader
        icon={FolderSpecial}
        title="Projects"
        subtitle="Ongoing projects and initiatives the assistant tracks for you"
        action={<Button size="small" startIcon={<Add />} variant="outlined" onClick={openNew}>Add Project</Button>}
      />
      {projects === null ? (
        <CircularProgress size={24} sx={{ mt: 2 }} />
      ) : projects.length === 0 ? (
        <Alert severity="info" sx={{ mt: 1 }}>
          No projects saved yet. Add projects so the assistant can reference them in conversation.
        </Alert>
      ) : (
        <Grid container spacing={1.5}>
          {projects.map(pj => (
            <Grid item xs={12} sm={6} md={4} key={pj.id}>
              <Card variant="outlined" sx={{ height: '100%' }}>
                <CardContent sx={{ pb: '12px !important' }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <Box sx={{ flex: 1, minWidth: 0, mr: 1 }}>
                      <Typography fontWeight={600} fontSize="0.88rem" noWrap>{pj.name}</Typography>
                      <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap' }}>
                        {pj.status && <Chip label={pj.status} size="small" color={STATUS_COLOR[pj.status]} sx={{ fontSize: '0.65rem', height: 18 }} />}
                        {pj.deadline && <Chip label={`Due ${new Date(pj.deadline).toLocaleDateString()}`} size="small" sx={{ fontSize: '0.65rem', height: 18 }} />}
                      </Box>
                    </Box>
                    <Box>
                      <Tooltip title="Edit"><IconButton size="small" onClick={() => openEdit(pj)}><Edit fontSize="small" /></IconButton></Tooltip>
                      <Tooltip title="Delete"><IconButton size="small" color="error" onClick={() => deleteProject(pj.id)}><Delete fontSize="small" /></IconButton></Tooltip>
                    </Box>
                  </Box>
                  {pj.context_notes && (
                    <Typography fontSize="0.75rem" color="text.secondary" mt={0.75} sx={{
                      overflow: 'hidden', display: '-webkit-box',
                      WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                    }}>
                      {pj.context_notes}
                    </Typography>
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{editTarget ? 'Edit Project' : 'Add Project'}</DialogTitle>
        <DialogContent sx={{ pt: '8px !important', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField autoFocus size="small" label="Project Name *" fullWidth value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
          <FormControl size="small" fullWidth>
            <InputLabel>Status</InputLabel>
            <Select label="Status" value={form.status} onChange={e => setForm(p => ({ ...p, status: e.target.value }))}>
              {PROJECT_STATUSES.map(s => <MenuItem key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</MenuItem>)}
            </Select>
          </FormControl>
          <TextField size="small" label="Context / Notes" fullWidth multiline rows={3} value={form.context_notes} onChange={e => setForm(p => ({ ...p, context_notes: e.target.value }))} helperText="What is this project about? Key decisions, blockers, etc." />
          <TextField size="small" label="Deadline" type="date" fullWidth InputLabelProps={{ shrink: true }} value={form.deadline} onChange={e => setForm(p => ({ ...p, deadline: e.target.value }))} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Suggestions tab ───────────────────────────────────────────────────────────

function SuggestionsTab() {
  const [suggestions, setSuggestions] = useState(null);
  const [resolving, setResolving] = useState({});

  const load = useCallback(async () => {
    try {
      const res = await hubApi.listMemorySuggestions('pending');
      setSuggestions(res.data.suggestions || []);
    } catch { setSuggestions([]); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const resolve = async (id, status) => {
    setResolving(prev => ({ ...prev, [id]: true }));
    try {
      await hubApi.resolveMemorySuggestion(id, status);
      setSuggestions(prev => prev.filter(s => s.id !== id));
    } catch { /* ignore */ } finally {
      setResolving(prev => ({ ...prev, [id]: false }));
    }
  };

  return (
    <Box>
      <SectionHeader
        icon={AutoAwesome}
        title="Auto-detected Suggestions"
        subtitle="People and projects the assistant spotted in your group conversations"
      />
      {suggestions === null ? (
        <CircularProgress size={24} sx={{ mt: 2 }} />
      ) : suggestions.length === 0 ? (
        <Alert severity="info" sx={{ mt: 1 }}>
          No pending suggestions. The assistant will surface people and projects it detects in group messages.
        </Alert>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {suggestions.map(s => {
            const d = s.suggested_data || {};
            const busy = resolving[s.id];
            return (
              <Card variant="outlined" key={s.id}>
                <CardContent sx={{ pb: '12px !important', display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Chip
                    label={s.suggestion_type}
                    size="small"
                    color={s.suggestion_type === 'person' ? 'primary' : 'secondary'}
                    sx={{ fontSize: '0.7rem', flexShrink: 0 }}
                  />
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography fontWeight={600} fontSize="0.88rem" noWrap>{d.name || 'Unknown'}</Typography>
                    {(d.role || d.status) && (
                      <Typography fontSize="0.75rem" color="text.secondary">
                        {d.role || d.status}
                      </Typography>
                    )}
                    {(d.notes || d.context_notes) && (
                      <Typography fontSize="0.75rem" color="text.secondary" noWrap>
                        {d.notes || d.context_notes}
                      </Typography>
                    )}
                  </Box>
                  <Box sx={{ display: 'flex', gap: 0.5, flexShrink: 0 }}>
                    <Tooltip title="Approve — add to memory">
                      <span>
                        <IconButton size="small" color="success" disabled={busy} onClick={() => resolve(s.id, 'approved')}>
                          {busy ? <CircularProgress size={16} /> : <Check fontSize="small" />}
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title="Skip">
                      <span>
                        <IconButton size="small" disabled={busy} onClick={() => resolve(s.id, 'skipped')}>
                          <Close fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Box>
                </CardContent>
              </Card>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AssistantMemory() {
  const [tab, setTab] = useState(0);

  return (
    <Box sx={{ maxWidth: 900, mx: 'auto', p: { xs: 2, md: 3 } }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <ManageAccounts sx={{ fontSize: 28, color: 'primary.main' }} />
        <Box>
          <Typography variant="h5" fontWeight={700}>Assistant Memory</Typography>
          <Typography variant="body2" color="text.secondary">
            Facts the assistant remembers across every conversation
          </Typography>
        </Box>
      </Box>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}>
        <Tab label="Your Profile" />
        <Tab label="People" />
        <Tab label="Projects" />
        <Tab label="Suggestions" />
      </Tabs>

      {tab === 0 && <GlobalTab />}
      {tab === 1 && <PeopleTab />}
      {tab === 2 && <ProjectsTab />}
      {tab === 3 && <SuggestionsTab />}
    </Box>
  );
}
