import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Typography, TextField, CircularProgress, Alert,
  List, ListItem, ListItemText, Stack, Switch, IconButton, Button, Collapse,
} from '@mui/material';
import { Delete, Add, ExpandMore, ExpandLess } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

export default function KnowledgeTab({ guildId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [docs, setDocs] = useState([]);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);

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

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={0.5}>Knowledge base</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={2}>
        Documents here ground the /ask command — the AI answers from your server's own
        FAQ, rules and guides instead of guessing.
      </Typography>
      {error && <Alert severity="warning" sx={{ mb: 1 }} onClose={() => setError(null)}>{error}</Alert>}

      <TextField fullWidth size="small" margin="dense" label="Title" value={title}
        inputProps={{ maxLength: 200 }} onChange={(e) => setTitle(e.target.value)} />
      <TextField fullWidth multiline minRows={3} size="small" margin="dense" label="Content"
        value={content} inputProps={{ maxLength: 8000 }} onChange={(e) => setContent(e.target.value)} />
      <Button startIcon={<Add />} variant="contained" size="small" sx={{ mt: 1 }}
        disabled={busy || !title.trim() || !content.trim()} onClick={add}>
        Add document
      </Button>

      <List dense sx={{ mt: 2 }}>
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

  async function save() {
    setBusy(true);
    try {
      await guildizerApi.put(`/api/guilds/${guildId}/knowledge/${doc.id}`, { content });
      await onChanged();
    } catch { /* parent reload surfaces issues */ }
    setBusy(false);
  }

  return (
    <>
      <ListItem disableGutters divider
        secondaryAction={(
          <Stack direction="row" spacing={0.5} alignItems="center">
            <Switch size="small" checked={doc.enabled}
              onChange={(e) => guildizerApi.put(`/api/guilds/${guildId}/knowledge/${doc.id}`, { enabled: e.target.checked }).then(onChanged)} />
            <IconButton size="small" onClick={() => setOpen((v) => !v)}>
              {open ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
            <IconButton size="small" color="error"
              onClick={() => guildizerApi.delete(`/api/guilds/${guildId}/knowledge/${doc.id}`).then(onChanged)}>
              <Delete fontSize="small" />
            </IconButton>
          </Stack>
        )}>
        <ListItemText primary={doc.title}
          secondary={`${doc.content.length} chars · updated ${doc.updated_at ? new Date(doc.updated_at).toLocaleString() : ''}`}
          primaryTypographyProps={{ variant: 'body2', fontWeight: 700, noWrap: true }} />
      </ListItem>
      <Collapse in={open}>
        <Box sx={{ pb: 1.5 }}>
          <TextField fullWidth multiline minRows={3} size="small" value={content}
            inputProps={{ maxLength: 8000 }} onChange={(e) => setContent(e.target.value)} />
          <Button size="small" variant="outlined" sx={{ mt: 0.5 }} disabled={busy} onClick={save}>
            Save changes
          </Button>
        </Box>
      </Collapse>
    </>
  );
}
