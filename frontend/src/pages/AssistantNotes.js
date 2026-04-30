import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, CircularProgress,
  Alert, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  ToggleButton, ToggleButtonGroup, Menu, MenuItem, IconButton, Tooltip,
  Select, FormControl, InputLabel,
} from '@mui/material';
import {
  Add, AutoAwesome, Edit, Delete, EditNote, FilterList, Close,
} from '@mui/icons-material';
import { notes, telegramGroups } from '../services/api';
import { useNavigate } from 'react-router-dom';

const TAG_COLORS = {
  decision: 'primary',
  task: 'warning',
  link: 'info',
  question: 'secondary',
};

const SOURCE_LABELS = { manual: 'Manual', ai: 'AI', bot: 'Bot' };
const ALL_TAGS = ['decision', 'task', 'link', 'question'];

function NoteDialog({ open, onClose, note, onSaved, groups }) {
  const [content, setContent] = useState('');
  const [tags, setTags] = useState([]);
  const [groupId, setGroupId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) {
      setContent(note?.content || '');
      setTags(note?.tags || []);
      setGroupId(note?.group_id || '');
      setError('');
    }
  }, [open, note]);

  const toggleTag = (tag) =>
    setTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]);

  const handleSave = async () => {
    if (!content.trim()) { setError('Content is required.'); return; }
    setSaving(true);
    setError('');
    try {
      const group = groups.find(g => g.telegram_group_id === groupId);
      const payload = { content: content.trim(), tags, group_id: groupId || null, group_title: group?.title || null };
      if (note) {
        await notes.update(note.id, payload);
      } else {
        await notes.create(payload);
      }
      onSaved();
      onClose();
    } catch (e) {
      setError(e?.response?.data?.error || 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{note ? 'Edit Note' : 'New Note'}</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        {error && <Alert severity="error" sx={{ mb: 1.5, fontSize: '0.82rem' }}>{error}</Alert>}

        <TextField
          label="Content"
          multiline
          minRows={4}
          fullWidth
          value={content}
          onChange={e => setContent(e.target.value)}
          sx={{ mb: 2 }}
        />

        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel>Group (optional)</InputLabel>
          <Select value={groupId} label="Group (optional)" onChange={e => setGroupId(e.target.value)}>
            <MenuItem value="">Personal (no group)</MenuItem>
            {groups.map(g => (
              <MenuItem key={g.telegram_group_id} value={g.telegram_group_id}>{g.title}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Typography fontSize="0.8rem" color="text.secondary" mb={0.75}>Tags</Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {ALL_TAGS.map(tag => (
            <Chip
              key={tag}
              label={tag}
              color={tags.includes(tag) ? TAG_COLORS[tag] : 'default'}
              onClick={() => toggleTag(tag)}
              size="small"
              sx={{ cursor: 'pointer' }}
            />
          ))}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} size="small">Cancel</Button>
        <Button variant="contained" size="small" onClick={handleSave} disabled={saving}
          startIcon={saving ? <CircularProgress size={14} /> : null}>
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function GenerateDialog({ open, onClose, groups, onGenerated }) {
  const [groupId, setGroupId] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => { if (open) { setResult(null); setError(''); setGroupId(''); } }, [open]);

  const handleGenerate = async () => {
    if (!groupId) return;
    setLoading(true); setError(''); setResult(null);
    try {
      const { data } = await notes.generate(groupId);
      setResult(data);
      onGenerated();
    } catch (e) {
      setError(e?.response?.data?.error || 'Generation failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Generate AI Notes</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <Typography fontSize="0.84rem" color="text.secondary" mb={2}>
          Extracts decisions, tasks, links, and questions from the last 48 hours of group messages.
        </Typography>
        {error && <Alert severity="error" sx={{ mb: 1.5, fontSize: '0.82rem' }}>{error}</Alert>}
        {result ? (
          <Alert severity="success" sx={{ fontSize: '0.82rem' }}>
            Created {result.notes?.length || 0} notes —{' '}
            {Object.entries(result.counts || {}).filter(([, v]) => v > 0).map(([k, v]) => `${v} ${k}`).join(', ')}
          </Alert>
        ) : (
          <FormControl fullWidth size="small">
            <InputLabel>Select Group</InputLabel>
            <Select value={groupId} label="Select Group" onChange={e => setGroupId(e.target.value)}>
              {groups.map(g => (
                <MenuItem key={g.telegram_group_id} value={g.telegram_group_id}>{g.title}</MenuItem>
              ))}
            </Select>
          </FormControl>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} size="small">{result ? 'Close' : 'Cancel'}</Button>
        {!result && (
          <Button variant="contained" size="small" onClick={handleGenerate}
            disabled={!groupId || loading}
            startIcon={loading ? <CircularProgress size={14} /> : <AutoAwesome />}>
            Generate
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

function NoteCard({ note, onEdit, onDelete }) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try { await notes.delete(note.id); onDelete(note.id); }
    catch { setDeleting(false); }
  };

  return (
    <Card variant="outlined" sx={{ mb: 1.5 }}>
      <CardContent sx={{ pb: '12px !important' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
            {note.group_title && (
              <Chip label={note.group_title} size="small" variant="outlined"
                sx={{ fontSize: '0.7rem', height: 20 }} />
            )}
            <Chip label={SOURCE_LABELS[note.source] || note.source} size="small"
              color={note.source === 'ai' ? 'success' : note.source === 'bot' ? 'info' : 'default'}
              sx={{ fontSize: '0.7rem', height: 20 }} />
            {(note.tags || []).map(tag => (
              <Chip key={tag} label={tag} size="small" color={TAG_COLORS[tag] || 'default'}
                sx={{ fontSize: '0.7rem', height: 20 }} />
            ))}
          </Box>
          <Box sx={{ display: 'flex', gap: 0.25, ml: 1, flexShrink: 0 }}>
            <Tooltip title="Edit">
              <IconButton size="small" onClick={() => onEdit(note)}>
                <Edit sx={{ fontSize: 15 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Delete">
              <IconButton size="small" onClick={handleDelete} disabled={deleting}>
                {deleting ? <CircularProgress size={14} /> : <Delete sx={{ fontSize: 15 }} />}
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        <Typography fontSize="0.88rem" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {note.content}
        </Typography>

        <Typography fontSize="0.72rem" color="text.disabled" mt={0.75}>
          {new Date(note.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
        </Typography>
      </CardContent>
    </Card>
  );
}

export default function AssistantNotes() {
  const [noteList, setNoteList] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editNote, setEditNote] = useState(null);    // null = closed, {} = new, note = edit
  const [generateOpen, setGenerateOpen] = useState(false);

  // Filters
  const [filterGroup, setFilterGroup] = useState('');
  const [filterSource, setFilterSource] = useState('');
  const [filterTag, setFilterTag] = useState('');

  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = {};
      if (filterGroup) params.group_id = filterGroup;
      if (filterSource) params.source = filterSource;
      if (filterTag) params.tag = filterTag;
      const [notesRes, groupsRes] = await Promise.all([
        notes.list(params),
        telegramGroups.list(),
      ]);
      setNoteList(notesRes.data.notes || []);
      setGroups((groupsRes.data.groups || groupsRes.data.telegram_groups || []).filter(g => g.bot_status === 'active' || g.bot_status === 'pending'));
    } catch {
      setError('Failed to load notes.');
    } finally {
      setLoading(false);
    }
  }, [filterGroup, filterSource, filterTag]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = (id) => setNoteList(prev => prev.filter(n => n.id !== id));

  const clearFilters = filterGroup || filterSource || filterTag;

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 760, mx: 'auto' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Typography variant="h5" fontWeight={700}>Notes</Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button variant="outlined" size="small" startIcon={<AutoAwesome />}
            onClick={() => setGenerateOpen(true)}>
            Generate AI Notes
          </Button>
          <Button variant="contained" size="small" startIcon={<Add />}
            onClick={() => setEditNote({})}>
            New Note
          </Button>
        </Box>
      </Box>
      <Typography color="text.secondary" fontSize="0.9rem" mb={2.5}>
        Capture decisions, tasks, links, and questions — manually or via AI extraction.
      </Typography>

      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      {/* Filters */}
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', mb: 2, alignItems: 'center' }}>
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>Group</InputLabel>
          <Select value={filterGroup} label="Group" onChange={e => setFilterGroup(e.target.value)}>
            <MenuItem value="">All Groups</MenuItem>
            {groups.map(g => <MenuItem key={g.telegram_group_id} value={g.telegram_group_id}>{g.title}</MenuItem>)}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Source</InputLabel>
          <Select value={filterSource} label="Source" onChange={e => setFilterSource(e.target.value)}>
            <MenuItem value="">All Sources</MenuItem>
            <MenuItem value="manual">Manual</MenuItem>
            <MenuItem value="ai">AI</MenuItem>
            <MenuItem value="bot">Bot</MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Tag</InputLabel>
          <Select value={filterTag} label="Tag" onChange={e => setFilterTag(e.target.value)}>
            <MenuItem value="">All Tags</MenuItem>
            {ALL_TAGS.map(t => <MenuItem key={t} value={t}>{t}</MenuItem>)}
          </Select>
        </FormControl>

        {clearFilters && (
          <Button size="small" startIcon={<Close />}
            onClick={() => { setFilterGroup(''); setFilterSource(''); setFilterTag(''); }}>
            Clear
          </Button>
        )}
      </Box>

      {/* List */}
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress size={32} />
        </Box>
      ) : noteList.length === 0 ? (
        <Card variant="outlined">
          <CardContent sx={{ textAlign: 'center', py: 5 }}>
            <EditNote sx={{ fontSize: 48, color: 'text.disabled', mb: 1.5 }} />
            <Typography fontWeight={600} mb={0.5}>No notes yet</Typography>
            <Typography color="text.secondary" fontSize="0.88rem" mb={2.5}>
              Add the bot to a group and say "note this", or click Generate AI Notes to extract from recent messages.
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center', flexWrap: 'wrap' }}>
              <Button variant="outlined" size="small" onClick={() => navigate('/groups')}>
                Connect a Group
              </Button>
              <Button variant="contained" size="small" startIcon={<Add />} onClick={() => setEditNote({})}>
                Create Manual Note
              </Button>
            </Box>
          </CardContent>
        </Card>
      ) : (
        noteList.map(note => (
          <NoteCard key={note.id} note={note} onEdit={n => setEditNote(n)} onDelete={handleDelete} />
        ))
      )}

      {/* Dialogs */}
      <NoteDialog
        open={editNote !== null}
        onClose={() => setEditNote(null)}
        note={editNote && editNote.id ? editNote : null}
        onSaved={load}
        groups={groups}
      />
      <GenerateDialog
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
        groups={groups}
        onGenerated={load}
      />
    </Box>
  );
}
