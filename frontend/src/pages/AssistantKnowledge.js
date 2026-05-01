import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, CircularProgress,
  Alert, Grid, IconButton, TextField, Dialog, DialogTitle, DialogContent,
  DialogActions, InputAdornment, LinearProgress, Tooltip, Divider,
} from '@mui/material';
import {
  LibraryBooks, Upload, Delete, Search, QuestionAnswer,
  InsertDriveFile, PictureAsPdf, Close, Send,
} from '@mui/icons-material';
import { workspaceKnowledge as knowledgeApi } from '../services/api';
import PlanGate from '../components/PlanGate';

function _getUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

const TYPE_ICON = { pdf: PictureAsPdf, txt: InsertDriveFile, md: InsertDriveFile, docx: InsertDriveFile };
const TYPE_COLOR = { pdf: '#f44336', txt: '#2196f3', md: '#4caf50', docx: '#2196f3' };

function DocCard({ doc, onDelete, onAsk }) {
  const Icon = TYPE_ICON[doc.file_type] || InsertDriveFile;
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5, mb: 1 }}>
          <Icon sx={{ fontSize: 28, color: TYPE_COLOR[doc.file_type] || 'primary.main', flexShrink: 0, mt: 0.25 }} />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography fontWeight={600} fontSize="0.88rem" noWrap title={doc.filename}>
              {doc.filename}
            </Typography>
            <Typography fontSize="0.72rem" color="text.disabled">
              {doc.chunk_count} chunk{doc.chunk_count !== 1 ? 's' : ''} · {new Date(doc.created_at).toLocaleDateString()}
            </Typography>
          </Box>
        </Box>
        {doc.description && (
          <Typography fontSize="0.78rem" color="text.secondary" mb={1} noWrap>{doc.description}</Typography>
        )}
        {(doc.tags || []).length > 0 && (
          <Box sx={{ display: 'flex', gap: 0.5, mb: 1, flexWrap: 'wrap' }}>
            {doc.tags.map(t => <Chip key={t} label={t} size="small" sx={{ fontSize: '0.62rem', height: 16 }} />)}
          </Box>
        )}
        <Typography fontSize="0.75rem" color="text.secondary" sx={{
          overflow: 'hidden', display: '-webkit-box',
          WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', mb: 1.5,
        }}>
          {doc.content_preview}
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button size="small" variant="outlined" startIcon={<QuestionAnswer sx={{ fontSize: 13 }} />}
            onClick={() => onAsk(doc)} sx={{ fontSize: '0.72rem' }}>
            Ask
          </Button>
          <Tooltip title="Delete document">
            <IconButton size="small" color="error" onClick={() => onDelete(doc.id)}>
              <Delete sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        </Box>
      </CardContent>
    </Card>
  );
}

function UploadDialog({ open, onClose, onUploaded }) {
  const [mode, setMode] = useState('file'); // 'file' | 'text'
  const [file, setFile] = useState(null);
  const [text, setText] = useState('');
  const [filename, setFilename] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef();

  const reset = () => { setFile(null); setText(''); setFilename(''); setDescription(''); setTags(''); setError(''); };

  const upload = async () => {
    setUploading(true); setError('');
    try {
      if (mode === 'file') {
        if (!file) { setError('Choose a file'); return; }
        const fd = new FormData();
        fd.append('file', file);
        fd.append('description', description);
        fd.append('tags', tags);
        const { data } = await knowledgeApi.upload(fd);
        onUploaded(data.document);
      } else {
        if (!text.trim()) { setError('Enter some text'); return; }
        const { data } = await knowledgeApi.uploadText({
          content: text, filename: filename || 'note.txt',
          description, tags: tags.split(',').map(t => t.trim()).filter(Boolean),
        });
        onUploaded(data.document);
      }
      reset(); onClose();
    } catch (e) {
      setError(e.response?.data?.error || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open={open} onClose={() => { reset(); onClose(); }} maxWidth="sm" fullWidth>
      <DialogTitle>Add to Knowledge Base</DialogTitle>
      <DialogContent sx={{ pt: '16px !important', display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Box sx={{ display: 'flex', gap: 1, mb: 0.5 }}>
          <Button size="small" variant={mode === 'file' ? 'contained' : 'outlined'} onClick={() => setMode('file')}>
            Upload File
          </Button>
          <Button size="small" variant={mode === 'text' ? 'contained' : 'outlined'} onClick={() => setMode('text')}>
            Paste Text
          </Button>
        </Box>
        {mode === 'file' ? (
          <>
            <Box
              sx={{
                border: '2px dashed', borderColor: file ? 'success.main' : 'divider',
                borderRadius: 2, p: 3, textAlign: 'center', cursor: 'pointer',
                '&:hover': { borderColor: 'primary.main' },
              }}
              onClick={() => fileRef.current?.click()}
            >
              <Upload sx={{ fontSize: 32, color: 'text.disabled', mb: 0.5 }} />
              <Typography fontSize="0.85rem" color={file ? 'success.main' : 'text.secondary'}>
                {file ? file.name : 'Click to choose PDF, TXT, MD, or DOCX (max 5 MB)'}
              </Typography>
              <input ref={fileRef} type="file" accept=".pdf,.txt,.md,.docx" hidden
                onChange={e => setFile(e.target.files[0] || null)} />
            </Box>
          </>
        ) : (
          <>
            <TextField label="Filename" value={filename} onChange={e => setFilename(e.target.value)}
              placeholder="my-notes.txt" size="small" fullWidth />
            <TextField label="Content" value={text} onChange={e => setText(e.target.value)}
              multiline rows={5} size="small" fullWidth placeholder="Paste or type your content here..." />
          </>
        )}
        <TextField label="Description (optional)" value={description} onChange={e => setDescription(e.target.value)}
          size="small" fullWidth />
        <TextField label="Tags (comma-separated)" value={tags} onChange={e => setTags(e.target.value)}
          size="small" fullWidth placeholder="policy, onboarding, faq" />
        {error && <Alert severity="error">{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={() => { reset(); onClose(); }}>Cancel</Button>
        <Button variant="contained" onClick={upload} disabled={uploading} startIcon={uploading ? <CircularProgress size={16} /> : <Upload />}>
          Upload
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function AskDialog({ open, doc, onClose }) {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const ask = async () => {
    if (!question.trim()) return;
    setLoading(true); setError(''); setAnswer('');
    try {
      const { data } = await knowledgeApi.ask(doc.id, question);
      setAnswer(data.answer);
    } catch (e) {
      setError(e.response?.data?.error || 'AI request failed');
    } finally {
      setLoading(false);
    }
  };

  const handleKey = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        Ask about: {doc?.filename}
        <IconButton size="small" onClick={onClose}><Close fontSize="small" /></IconButton>
      </DialogTitle>
      <DialogContent sx={{ pt: '12px !important' }}>
        <Typography fontSize="0.82rem" color="text.secondary" mb={2}>
          AI will answer your question using only the content of this document.
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
          <TextField
            size="small" fullWidth placeholder="Ask a question about this document…"
            value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={handleKey}
            disabled={loading}
          />
          <IconButton color="primary" onClick={ask} disabled={loading || !question.trim()}>
            {loading ? <CircularProgress size={18} /> : <Send fontSize="small" />}
          </IconButton>
        </Box>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        {answer && (
          <Card variant="outlined" sx={{ bgcolor: 'action.hover' }}>
            <CardContent sx={{ py: '12px !important' }}>
              <Typography fontSize="0.85rem" sx={{ whiteSpace: 'pre-wrap' }}>{answer}</Typography>
            </CardContent>
          </Card>
        )}
      </DialogContent>
    </Dialog>
  );
}

function SearchResultsPanel({ query, results, onClear }) {
  if (!query) return null;
  return (
    <Box sx={{ mb: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Typography fontSize="0.85rem" fontWeight={600}>
          {results.length} result{results.length !== 1 ? 's' : ''} for "{query}"
        </Typography>
        <Button size="small" onClick={onClear}>Clear</Button>
      </Box>
      {results.length === 0 ? (
        <Typography fontSize="0.84rem" color="text.secondary">No matches found.</Typography>
      ) : (
        results.map(r => (
          <Card key={r.id} variant="outlined" sx={{ mb: 1 }}>
            <CardContent sx={{ py: '10px !important' }}>
              <Typography fontSize="0.83rem" fontWeight={600}>{r.filename}</Typography>
              <Typography fontSize="0.78rem" color="text.secondary" sx={{ fontStyle: 'italic', mt: 0.25 }}>
                …{r.snippet}…
              </Typography>
            </CardContent>
          </Card>
        ))
      )}
      <Divider sx={{ mt: 2, mb: 2 }} />
    </Box>
  );
}

export default function AssistantKnowledge() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [askDoc, setAskDoc] = useState(null);
  const [searchQ, setSearchQ] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await knowledgeApi.list();
      setDocs(data.documents || []);
    } catch { setError('Failed to load documents.'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const deleteDoc = async (id) => {
    setDocs(prev => prev.filter(d => d.id !== id));
    try { await knowledgeApi.delete(id); } catch { load(); }
  };

  const search = async () => {
    if (searchQ.trim().length < 2) return;
    setSearching(true);
    try {
      const { data } = await knowledgeApi.search(searchQ.trim());
      setSearchResults(data.results || []);
    } catch { setSearchResults([]); }
    finally { setSearching(false); }
  };

  const user = _getUser();

  return (
    <PlanGate plan="pro" userTier={user.subscription_tier} feature="Knowledge Base">
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 860, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <LibraryBooks sx={{ fontSize: 26, color: 'primary.main' }} />
          <Typography variant="h5" fontWeight={700}>Knowledge Base</Typography>
        </Box>
        <Button variant="contained" size="small" startIcon={<Upload />} onClick={() => setUploadOpen(true)}>
          Add Document
        </Button>
      </Box>
      <Typography color="text.secondary" fontSize="0.88rem" mb={3}>
        Upload docs, PDFs, and text — then ask the AI questions about them
      </Typography>

      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      {/* Search bar */}
      <Box sx={{ display: 'flex', gap: 1, mb: 3 }}>
        <TextField
          size="small" fullWidth placeholder="Search across all documents…"
          value={searchQ} onChange={e => setSearchQ(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
          InputProps={{
            startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment>,
            endAdornment: searching ? <InputAdornment position="end"><CircularProgress size={16} /></InputAdornment> : null,
          }}
        />
        <Button variant="outlined" onClick={search} disabled={searching}>Search</Button>
      </Box>

      {searchResults !== null && (
        <SearchResultsPanel query={searchQ} results={searchResults} onClear={() => { setSearchResults(null); setSearchQ(''); }} />
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={32} /></Box>
      ) : docs.length === 0 ? (
        <Card variant="outlined" sx={{ textAlign: 'center', py: 8 }}>
          <LibraryBooks sx={{ fontSize: 48, color: 'text.disabled', mb: 1.5 }} />
          <Typography fontWeight={600} mb={0.5}>No documents yet</Typography>
          <Typography color="text.secondary" fontSize="0.85rem" mb={2}>
            Upload PDFs, text files, or paste content to build your knowledge base.
          </Typography>
          <Button variant="contained" startIcon={<Upload />} onClick={() => setUploadOpen(true)}>
            Add First Document
          </Button>
        </Card>
      ) : (
        <Grid container spacing={2}>
          {docs.map(d => (
            <Grid item xs={12} sm={6} md={4} key={d.id}>
              <DocCard doc={d} onDelete={deleteDoc} onAsk={setAskDoc} />
            </Grid>
          ))}
        </Grid>
      )}

      <UploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)}
        onUploaded={doc => { setDocs(prev => [doc, ...prev]); }} />
      {askDoc && (
        <AskDialog open={Boolean(askDoc)} doc={askDoc} onClose={() => setAskDoc(null)} />
      )}
    </Box>
    </PlanGate>
  );
}
