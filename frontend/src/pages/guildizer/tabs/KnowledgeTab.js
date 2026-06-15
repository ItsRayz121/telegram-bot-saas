import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Box, Card, CardContent, Typography, TextField, CircularProgress, Alert,
  List, ListItem, ListItemText, Stack, Switch, IconButton, Button, Collapse,
  Chip, LinearProgress, Divider,
} from '@mui/material';
import {
  Delete, Add, ExpandMore, ExpandLess, UploadFile, Description,
} from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const ALLOWED = ['pdf', 'docx', 'txt', 'md'];

export default function KnowledgeTab({ guildId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [docs, setDocs] = useState([]);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);

  // Upload state
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState('');

  const load = useCallback(async () => {
    try {
      const { data } = await guildizerApi.get(`/api/guilds/${guildId}/knowledge`);
      setDocs(data.documents); setError(null);
    } catch { setError('Failed to load the knowledge base.'); }
    setLoading(false);
  }, [guildId]);

  useEffect(() => { load(); }, [load]);

  async function add() {
    setBusy(true);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/knowledge`, { title, content });
      setTitle(''); setContent('');
      await load();
    } catch { setError('Could not save the document.'); }
    setBusy(false);
  }

  async function upload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!ALLOWED.includes(ext)) {
      setError(`Unsupported file type. Use: ${ALLOWED.join(', ')}`);
      if (fileRef.current) fileRef.current.value = '';
      return;
    }
    setUploading(true); setProgress(0); setStage('Uploading…'); setError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await guildizerApi.post(`/api/guilds/${guildId}/knowledge/upload`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (ev) => {
          if (!ev.total) return;
          const pct = Math.round((ev.loaded / ev.total) * 100);
          setProgress(pct);
          setStage(pct >= 100 ? 'Indexing…' : 'Uploading…');
        },
      });
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.response?.data?.error || 'Upload failed.');
    } finally {
      setUploading(false); setProgress(0); setStage('');
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={0.5}>Knowledge base</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={2}>
        Documents here ground the /ask command — the AI answers from your server's own
        FAQ, rules and guides instead of guessing. Upload files (PDF, DOCX, TXT, MD) for
        semantic search, or paste short FAQ entries below.
      </Typography>
      {error && <Alert severity="warning" sx={{ mb: 1 }} onClose={() => setError(null)}>{error}</Alert>}

      {/* ── Upload documents ─────────────────────────────────────────────── */}
      <Alert severity="info" icon={false} sx={{ mb: 1.5, fontSize: '0.8rem' }}>
        Supported: <strong>PDF, DOCX, TXT, MD</strong> — max 5 MB per file. Text is
        extracted and indexed. Semantic search uses the platform <strong>OPENAI_API_KEY</strong>;
        without it, uploaded text still answers via keyword search.
      </Alert>
      {uploading && (
        <Box sx={{ mb: 1.5 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">{stage}</Typography>
            <Typography variant="caption" color="text.secondary">{progress}%</Typography>
          </Box>
          <LinearProgress variant={stage === 'Indexing…' ? 'indeterminate' : 'determinate'}
            value={progress} sx={{ borderRadius: 1 }} />
        </Box>
      )}
      <input type="file" ref={fileRef} style={{ display: 'none' }}
        accept=".pdf,.txt,.md,.docx" onChange={upload} />
      <Button variant="outlined" startIcon={<UploadFile />} disabled={uploading}
        onClick={() => fileRef.current?.click()}>
        {uploading ? (stage || 'Processing…') : 'Upload document'}
      </Button>

      <Divider sx={{ my: 2 }} />

      {/* ── Manual FAQ entry ─────────────────────────────────────────────── */}
      <Typography variant="subtitle2" fontWeight={600} mb={0.5}>Add a text entry</Typography>
      <TextField fullWidth size="small" margin="dense" label="Title" value={title}
        inputProps={{ maxLength: 200 }} onChange={(e) => setTitle(e.target.value)} />
      <TextField fullWidth multiline minRows={3} size="small" margin="dense" label="Content"
        value={content} inputProps={{ maxLength: 8000 }} onChange={(e) => setContent(e.target.value)} />
      <Button startIcon={<Add />} variant="contained" size="small" sx={{ mt: 1 }}
        disabled={busy || !title.trim() || !content.trim()} onClick={add}>
        Add document
      </Button>

      {/* ── Indexed documents ────────────────────────────────────────────── */}
      <Typography variant="subtitle2" fontWeight={600} sx={{ mt: 2.5, mb: 0.5 }}>
        Indexed documents ({docs.length})
      </Typography>
      <List dense>
        {docs.map((d) => <DocRow key={d.id} guildId={guildId} doc={d} onChanged={load} />)}
        {docs.length === 0 && <Typography variant="body2" color="text.secondary">No documents yet.</Typography>}
      </List>
    </CardContent></Card>
  );
}

function DocRow({ guildId, doc, onChanged }) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState(doc.content);
  const [busy, setBusy] = useState(false);
  const isFile = (doc.file_type || 'text') !== 'text';

  async function save() {
    setBusy(true);
    try {
      await guildizerApi.put(`/api/guilds/${guildId}/knowledge/${doc.id}`, { content });
      await onChanged();
    } catch { /* parent reload surfaces issues */ }
    setBusy(false);
  }

  const meta = isFile
    ? `${doc.chunk_count} chunk${doc.chunk_count === 1 ? '' : 's'} indexed · ${doc.created_at ? new Date(doc.created_at).toLocaleDateString() : ''}`
    : `${(doc.content || '').length} chars · updated ${doc.updated_at ? new Date(doc.updated_at).toLocaleString() : ''}`;

  return (
    <>
      <ListItem disableGutters divider
        secondaryAction={(
          <Stack direction="row" spacing={0.5} alignItems="center">
            {isFile && <Chip size="small" label={(doc.file_type || '').toUpperCase()} sx={{ mr: 0.5, height: 20, fontSize: '0.65rem' }} />}
            <Switch size="small" checked={doc.enabled}
              onChange={(e) => guildizerApi.put(`/api/guilds/${guildId}/knowledge/${doc.id}`, { enabled: e.target.checked }).then(onChanged)} />
            {!isFile && (
              <IconButton size="small" onClick={() => setOpen((v) => !v)}>
                {open ? <ExpandLess /> : <ExpandMore />}
              </IconButton>
            )}
            <IconButton size="small" color="error"
              onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/knowledge/${doc.id}`).then(onChanged)}>
              <Delete fontSize="small" />
            </IconButton>
          </Stack>
        )}>
        {isFile && <Description sx={{ mr: 1, color: 'text.secondary', fontSize: 18 }} />}
        <ListItemText primary={doc.filename || doc.title} secondary={meta}
          primaryTypographyProps={{ variant: 'body2', fontWeight: 700, noWrap: true }} />
      </ListItem>
      {!isFile && (
        <Collapse in={open}>
          <Box sx={{ pb: 1.5 }}>
            <TextField fullWidth multiline minRows={3} size="small" value={content}
              inputProps={{ maxLength: 8000 }} onChange={(e) => setContent(e.target.value)} />
            <Button size="small" variant="outlined" sx={{ mt: 0.5 }} disabled={busy} onClick={save}>
              Save changes
            </Button>
          </Box>
        </Collapse>
      )}
    </>
  );
}
