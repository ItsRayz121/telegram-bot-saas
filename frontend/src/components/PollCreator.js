import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Switch, FormControlLabel, Dialog, DialogTitle, DialogContent,
  DialogActions, IconButton, Chip, Select, MenuItem, FormControl,
  InputLabel, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper,
} from '@mui/material';
import { Add, Delete, HowToVote, Quiz, Close } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { polls } from '../services/api';

export default function PollCreator({ botId, groupId }) {
  const [pollList, setPollList] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    question: '', options: ['', ''], is_quiz: false,
    correct_option_index: 0, is_anonymous: true, allows_multiple: false,
    explanation: '', scheduled_at: '',
  });

  const load = async () => {
    try {
      const res = await polls.list(botId, groupId);
      setPollList(res.data.polls || []);
    } catch { }
  };

  useEffect(() => { load(); }, [botId, groupId]);

  const addOption = () => {
    if (form.options.length >= 10) return;
    setForm(p => ({ ...p, options: [...p.options, ''] }));
  };

  const removeOption = (idx) => {
    if (form.options.length <= 2) return;
    setForm(p => ({ ...p, options: p.options.filter((_, i) => i !== idx) }));
  };

  const setOption = (idx, val) => {
    setForm(p => { const opts = [...p.options]; opts[idx] = val; return { ...p, options: opts }; });
  };

  const handleCreate = async () => {
    const filledOptions = form.options.filter(o => o.trim());
    if (!form.question.trim()) { toast.error('Question is required'); return; }
    if (filledOptions.length < 2) { toast.error('At least 2 options required'); return; }
    try {
      await polls.create(botId, groupId, {
        ...form,
        options: filledOptions,
        scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : null,
      });
      toast.success(form.scheduled_at ? 'Poll scheduled' : 'Poll sent to group');
      setOpen(false);
      setForm({ question: '', options: ['', ''], is_quiz: false, correct_option_index: 0, is_anonymous: true, allows_multiple: false, explanation: '', scheduled_at: '' });
      load();
    } catch (e) { toast.error(e.response?.data?.error || 'Failed to create poll'); }
  };

  const handleDelete = async (id) => {
    try {
      await polls.delete(botId, groupId, id);
      setPollList(prev => prev.filter(p => p.id !== id));
      toast.success('Deleted');
    } catch { toast.error('Failed to delete'); }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight={600}>Polls & Quizzes</Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => setOpen(true)}>Create Poll</Button>
      </Box>

      {pollList.length === 0 ? (
        <Card><CardContent><Typography color="text.secondary" align="center">No polls created yet.</Typography></CardContent></Card>
      ) : (
        <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Question</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Options</TableCell>
                <TableCell>Scheduled</TableCell>
                <TableCell>Status</TableCell>
                <TableCell></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pollList.map(p => (
                <TableRow key={p.id} hover>
                  <TableCell><Typography variant="body2" noWrap sx={{ maxWidth: 200 }}>{p.question}</Typography></TableCell>
                  <TableCell>
                    <Chip icon={p.is_quiz ? <Quiz /> : <HowToVote />} label={p.is_quiz ? 'Quiz' : 'Poll'} size="small" color={p.is_quiz ? 'secondary' : 'primary'} variant="outlined" />
                  </TableCell>
                  <TableCell><Typography variant="body2">{(p.options || []).length} options</Typography></TableCell>
                  <TableCell>
                    <Typography variant="body2">{p.scheduled_at ? new Date(p.scheduled_at).toLocaleString() : '—'}</Typography>
                  </TableCell>
                  <TableCell>
                    <Chip label={p.is_sent ? 'Sent' : 'Pending'} size="small" color={p.is_sent ? 'success' : 'warning'} />
                  </TableCell>
                  <TableCell>
                    <IconButton size="small" color="error" onClick={() => handleDelete(p.id)}><Delete fontSize="small" /></IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create Poll / Quiz</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12}>
              <TextField fullWidth label="Question" value={form.question}
                onChange={e => setForm(p => ({ ...p, question: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              <Typography variant="subtitle2" mb={1}>Options</Typography>
              {form.options.map((opt, idx) => (
                <Box key={idx} sx={{ display: 'flex', gap: 1, mb: 1 }}>
                  <TextField size="small" fullWidth label={`Option ${idx + 1}`} value={opt}
                    onChange={e => setOption(idx, e.target.value)} />
                  <IconButton size="small" onClick={() => removeOption(idx)} disabled={form.options.length <= 2}>
                    <Close fontSize="small" />
                  </IconButton>
                </Box>
              ))}
              {form.options.length < 10 && (
                <Button size="small" startIcon={<Add />} onClick={addOption}>Add Option</Button>
              )}
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControlLabel control={<Switch checked={form.is_quiz} onChange={e => setForm(p => ({ ...p, is_quiz: e.target.checked }))} />} label="Quiz mode (correct answer)" />
            </Grid>
            {form.is_quiz && (
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth size="small">
                  <InputLabel>Correct Answer</InputLabel>
                  <Select value={form.correct_option_index} label="Correct Answer"
                    onChange={e => setForm(p => ({ ...p, correct_option_index: e.target.value }))}>
                    {form.options.map((opt, idx) => (
                      <MenuItem key={idx} value={idx}>{opt || `Option ${idx + 1}`}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
            )}
            {form.is_quiz && (
              <Grid item xs={12}>
                <TextField fullWidth label="Explanation (shown after answer)" value={form.explanation}
                  onChange={e => setForm(p => ({ ...p, explanation: e.target.value }))} />
              </Grid>
            )}
            <Grid item xs={6}>
              <FormControlLabel control={<Switch checked={form.is_anonymous} onChange={e => setForm(p => ({ ...p, is_anonymous: e.target.checked }))} />} label="Anonymous" />
            </Grid>
            {!form.is_quiz && (
              <Grid item xs={6}>
                <FormControlLabel control={<Switch checked={form.allows_multiple} onChange={e => setForm(p => ({ ...p, allows_multiple: e.target.checked }))} />} label="Multiple answers" />
              </Grid>
            )}
            <Grid item xs={12}>
              <TextField fullWidth type="datetime-local" label="Schedule (leave blank to send now)"
                InputLabelProps={{ shrink: true }} value={form.scheduled_at}
                onChange={e => setForm(p => ({ ...p, scheduled_at: e.target.value }))} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreate}>
            {form.scheduled_at ? 'Schedule' : 'Send Now'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
