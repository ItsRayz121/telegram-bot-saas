import React, { useState, useEffect, useRef } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Switch, FormControlLabel, IconButton, Chip, Alert, LinearProgress,
  List, ListItem, ListItemText, ListItemSecondaryAction, Divider,
} from '@mui/material';
import { Upload, Delete, Description, Psychology } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { knowledge } from '../services/api';

export default function KnowledgeBase({ botId, groupId, settings, updateSetting }) {
  const [docs, setDocs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef();
  const kb = settings?.knowledge_base || {};

  const load = async () => {
    try {
      const res = await knowledge.list(botId, groupId);
      setDocs(res.data.documents || []);
    } catch { }
  };

  useEffect(() => { load(); }, [botId, groupId]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const allowed = ['pdf', 'txt', 'md', 'docx'];
    const ext = file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) {
      toast.error(`Unsupported file type. Use: ${allowed.join(', ')}`);
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await knowledge.upload(botId, groupId, fd);
      toast.success(`"${file.name}" uploaded and indexed`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Upload failed');
    } finally {
      setUploading(false);
      fileRef.current.value = '';
    }
  };

  const handleDelete = async (docId, filename) => {
    try {
      await knowledge.delete(botId, groupId, docId);
      toast.success(`"${filename}" removed`);
      setDocs(prev => prev.filter(d => d.id !== docId));
    } catch { toast.error('Failed to delete'); }
  };

  return (
    <Box>
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Psychology color="primary" />
            <Typography variant="h6" fontWeight={600}>AI Knowledge Base</Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Upload documents (PDF, DOCX, TXT, MD) and members can ask the bot questions answered directly from your files using AI.
            Use <strong>/ask your question</strong> in the group.
          </Typography>
          <FormControlLabel
            control={<Switch checked={!!kb.enabled} onChange={e => updateSetting('knowledge_base.enabled', e.target.checked)} />}
            label="Enable AI Q&A from knowledge base"
          />
        </CardContent>
      </Card>

      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="subtitle1" fontWeight={600} mb={2}>Upload Documents</Typography>
          <Alert severity="info" sx={{ mb: 2 }}>
            Supported: PDF, DOCX, TXT, MD — Max 5MB per file. Text is extracted and indexed using OpenAI embeddings.
            Requires <strong>OPENAI_API_KEY</strong> in your environment.
          </Alert>
          {uploading && <LinearProgress sx={{ mb: 2 }} />}
          <input type="file" ref={fileRef} style={{ display: 'none' }} accept=".pdf,.txt,.md,.docx" onChange={handleUpload} />
          <Button variant="outlined" startIcon={<Upload />} onClick={() => fileRef.current.click()} disabled={uploading}>
            {uploading ? 'Processing...' : 'Upload Document'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="subtitle1" fontWeight={600} mb={1}>Indexed Documents ({docs.length})</Typography>
          {docs.length === 0 ? (
            <Typography variant="body2" color="text.secondary">No documents uploaded yet.</Typography>
          ) : (
            <List disablePadding>
              {docs.map((doc, i) => (
                <React.Fragment key={doc.id}>
                  {i > 0 && <Divider />}
                  <ListItem disableGutters>
                    <Description sx={{ mr: 1.5, color: 'text.secondary' }} />
                    <ListItemText
                      primary={doc.filename}
                      secondary={`${doc.chunk_count} chunks indexed · ${new Date(doc.created_at).toLocaleDateString()}`}
                    />
                    <ListItemSecondaryAction>
                      <Chip label={doc.file_type.toUpperCase()} size="small" sx={{ mr: 1 }} />
                      <IconButton size="small" color="error" onClick={() => handleDelete(doc.id, doc.filename)}>
                        <Delete fontSize="small" />
                      </IconButton>
                    </ListItemSecondaryAction>
                  </ListItem>
                </React.Fragment>
              ))}
            </List>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
