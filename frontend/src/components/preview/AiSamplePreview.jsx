import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, CircularProgress, Stack, TextField, Typography } from '@mui/material';
import { AutoAwesome } from '@mui/icons-material';
import { MessagePreview } from './MessagePreview';

/**
 * "Generate sample" for AI / personality replies.
 *
 * Nothing here runs on its own: opening the panel, typing, or changing a setting never calls the AI.
 * Only the button does. When the settings that feed the prompt change, the existing sample is marked
 * outdated (and stays visible) until the person asks for a new one. Each click is one real provider
 * call, so the cost line below is always shown.
 *
 * generate(payload, { signal }) -> Promise<{ data: { answer, no_answer, billed_to, ... } }>
 */
// A generated sample survives closing and reopening the panel (and tab switches) for as long as the page is open,
// so reopening never costs another call. It is memory only: a refresh starts clean.
const SESSION = new Map();

export default function AiSamplePreview({
  generate, inputs, defaultQuestion, defaultContext, contextLabel, showContext = true,
  platform = 'telegram', format = 'markdown', botName, destination, costNote, fallbackToPlain = false,
  summary, cacheKey, footnote,
}) {
  const saved = cacheKey ? SESSION.get(cacheKey) : null;
  const [question, setQuestion] = useState(saved?.question ?? defaultQuestion);
  const [context, setContext] = useState(saved?.context ?? (defaultContext || ''));
  const [state, setState] = useState(saved?.state ?? { status: 'idle', result: null, stamp: null, error: null });
  const ctrl = useRef(null);

  // Cancel an in-flight request when the preview is closed / the form is left.
  useEffect(() => () => { if (ctrl.current) ctrl.current.abort(); }, []);

  useEffect(() => {
    if (cacheKey && state.status !== 'loading') SESSION.set(cacheKey, { question, context, state });
  }, [cacheKey, question, context, state]);

  const stampNow = JSON.stringify({ inputs, question, context });
  const outdated = !!state.result && state.stamp !== stampNow;
  const loading = state.status === 'loading';

  const run = async () => {
    if (loading) return;
    if (ctrl.current) ctrl.current.abort();
    ctrl.current = new AbortController();
    const stamp = stampNow;
    setState((s) => ({ ...s, status: 'loading', error: null }));
    try {
      const res = await generate({ ...inputs, question, sample_context: context }, { signal: ctrl.current.signal });
      setState({ status: 'done', result: res.data, stamp, error: null });
    } catch (e) {
      if (e?.code === 'ERR_CANCELED') return;
      const status = e?.response?.status;
      const msg = e?.response?.data?.error
        || (status === 429 ? 'Too many samples in a row. Wait a moment and try again.' : 'Could not generate a sample.');
      // The previous sample (if any) stays on screen; the editor behind this panel is unaffected.
      setState((s) => ({ ...s, status: 'error', error: msg }));
    }
  };

  const r = state.result;
  return (
    <Box>
      {summary && (
        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mb: 1.25 }}>
          {summary.map((c) => <Chip key={c} size="small" variant="outlined" label={c} />)}
        </Stack>
      )}
      <TextField fullWidth size="small" label="Sample question from a member" value={question}
        onChange={(e) => setQuestion(e.target.value)} inputProps={{ maxLength: 300 }} sx={{ mb: 1.25 }} />
      {showContext && (
        <TextField fullWidth size="small" multiline maxRows={4} label={contextLabel || 'Sample fact the bot may use'} value={context}
          onChange={(e) => setContext(e.target.value)} inputProps={{ maxLength: 800 }} sx={{ mb: 1.25 }}
          helperText="Typed by you for this preview only. Nothing is read from your group or knowledge base." />
      )}
      <Stack direction="row" spacing={1.25} alignItems="center" useFlexGap flexWrap="wrap" sx={{ mb: 1.25 }}>
        <Button variant={outdated ? 'contained' : 'outlined'} size="small" onClick={run}
          disabled={loading || !question.trim() || (showContext && !context.trim())}
          startIcon={loading ? <CircularProgress size={14} /> : <AutoAwesome fontSize="small" />}>
          {loading ? 'Generating…' : r ? 'Regenerate sample' : 'Generate sample'}
        </Button>
        {outdated && <Chip size="small" color="warning" label="Outdated: settings changed since this sample" />}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.25 }}>
        {costNote || 'Each sample is one real AI call and counts toward your AI usage.'}
        {' '}Nothing is posted, saved to memory or added to your knowledge base.
      </Typography>

      {footnote && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.25 }}>{footnote}</Typography>}
      {state.status === 'error' && <Alert severity="warning" sx={{ mb: 1 }} role="alert">{state.error}</Alert>}
      {r && (r.no_answer
        ? <Alert severity="info" sx={{ mb: 1 }}>With this sample fact the bot decided it could not answer, so in a live chat it would stay silent or escalate. Try a question the fact covers.</Alert>
        : (
          <Box sx={{ opacity: outdated ? 0.6 : 1 }}>
            <MessagePreview platform={platform} syntax="none" sample kind="reply" text={r.answer}
              plain={format === 'plain'} html={format === 'html'} fallbackToPlain={fallbackToPlain} botName={botName}
              replyTo={{ author: 'A member', text: state.stamp ? (JSON.parse(state.stamp).question || question) : question }}
              destination={destination}
              notes={format === 'html' ? ['Echo sends replies as Telegram HTML; the AI\'s wording is shown as it would be sent.'] : []} />
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
              Example only: live wording will vary. Generated with {r.provider || 'the configured provider'}{r.model ? ` (${r.model})` : ''}, billed to {r.billed_to}.
            </Typography>
          </Box>
        ))}
    </Box>
  );
}
