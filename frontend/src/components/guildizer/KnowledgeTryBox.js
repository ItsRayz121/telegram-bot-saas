import React, { useState } from 'react';
import { Alert, Box, Button, CircularProgress, Stack, TextField, Typography } from '@mui/material';
import guildizerApi from '../../services/guildizerApi';

const STATUS_TEXT = {
  no_answer: 'The assistant would not answer this one. Members asking it would be passed to your moderators.',
  conflict: 'Your sources disagree about this, so the assistant would not guess. Members asking it would be passed to your moderators.',
  no_knowledge: 'Nothing in the knowledge base to answer from yet.',
};

/** "Try a question": ONE real AI answer built from the knowledge base exactly as the
 *  bot would, so an admin can test it. Nothing is posted, stored or counted. */
export default function KnowledgeTryBox({ guildId }) {
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [error, setError] = useState('');

  async function ask() {
    setBusy(true); setError(''); setRes(null);
    try {
      const { data } = await guildizerApi.post(`/api/guilds/${guildId}/knowledge/ask-sample`, { question: q });
      setRes(data);
    } catch (e) {
      setError(e.response?.data?.message || 'Could not get a sample answer.');
    }
    setBusy(false);
  }

  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={600} mb={0.5}>Try a question</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        See how the assistant would answer a member, using your documents and sources. This makes one real AI request;
        nothing is posted to Discord or saved.
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField size="small" fullWidth label="A question a member might ask" value={q}
          inputProps={{ maxLength: 300 }} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && q.trim().length >= 3 && !busy && ask()} />
        <Button variant="outlined" onClick={ask} disabled={busy || q.trim().length < 3}
          startIcon={busy ? <CircularProgress size={14} /> : null}>
          Ask
        </Button>
      </Stack>
      {error && <Alert severity="warning" sx={{ mt: 1 }}>{error}</Alert>}
      {res && (
        <Alert severity={res.status === 'answered' ? 'success' : 'info'} sx={{ mt: 1, whiteSpace: 'pre-wrap' }}>
          {res.status === 'answered' ? res.answer : STATUS_TEXT[res.status]}
          <Typography variant="caption" display="block" sx={{ mt: 0.5, opacity: 0.8 }}>{res.note}</Typography>
        </Alert>
      )}
    </Box>
  );
}
