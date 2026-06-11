/**
 * AI & Integrations area subtabs (Telegizer-parity IA): Knowledge Base.
 * (The Escalation subtab reuses ProtectionTab section="escalation".)
 *
 * Knowledge Base = the existing KB document manager plus the AI reply-behaviour
 * settings (kb_replies section on the moderation config).
 */
import React, { useEffect, useState } from 'react';
import {
  Grid, Card, CardContent, Typography, TextField, MenuItem, Button, Switch,
  FormControlLabel, Alert, Snackbar,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';
import KnowledgeTab from './KnowledgeTab';

export function KnowledgeBaseSubtab({ guildId }) {
  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={7}>
        <KnowledgeTab guildId={guildId} />
      </Grid>
      <Grid item xs={12} md={5}>
        <KbRepliesCard guildId={guildId} />
      </Grid>
    </Grid>
  );
}

function KbRepliesCard({ guildId }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/moderation`)
      .then(({ data }) => setCfg(data.kb_replies || {}))
      .catch(() => setError('Failed to load AI reply settings.'));
  }, [guildId]);

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));

  async function save() {
    setSaving(true); setError(null);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/moderation`, { kb_replies: cfg });
      setCfg(data.kb_replies || cfg);
      setSaved(true);
    } catch { setError('Save failed.'); }
    setSaving(false);
  }

  if (!cfg) return null;

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>AI reply behaviour</Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Controls how the bot answers from the knowledge base. /ask always works; automatic
        replies follow these rules. Settings save now; bot rollout is staged.
      </Typography>
      <FormControlLabel control={<Switch checked={!!cfg.enabled} onChange={(e) => set({ enabled: e.target.checked })} />}
        label="Answer member questions automatically from the KB" />
      <FormControlLabel control={<Switch checked={!!cfg.mention_only} onChange={(e) => set({ mention_only: e.target.checked })} />}
        label="Only reply when the bot is @mentioned or replied to" />
      <FormControlLabel control={<Switch checked={!!cfg.low_confidence_fallback} onChange={(e) => set({ low_confidence_fallback: e.target.checked })} />}
        label="Reply with a fallback line when KB confidence is low" />
      <TextField type="number" size="small" margin="dense" fullWidth label="Minimum message length (words)"
        value={cfg.min_words ?? 3} inputProps={{ min: 1, max: 50 }}
        onChange={(e) => set({ min_words: Number(e.target.value) })} />
      <TextField select size="small" margin="dense" fullWidth label="Reply length"
        value={cfg.reply_length || 'medium'} onChange={(e) => set({ reply_length: e.target.value })}>
        {['short', 'medium', 'long'].map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
      </TextField>
      <TextField select size="small" margin="dense" fullWidth label="Emoji usage"
        value={cfg.emoji_usage || 'some'} onChange={(e) => set({ emoji_usage: e.target.value })}>
        {['none', 'some', 'lots'].map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
      </TextField>
      <TextField select size="small" margin="dense" fullWidth label="Formality"
        value={cfg.formality || 'casual'} onChange={(e) => set({ formality: e.target.value })}>
        {['casual', 'neutral', 'formal'].map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
      </TextField>
      {error && <Alert severity="error" sx={{ mt: 1, py: 0 }}>{error}</Alert>}
      <Button variant="contained" size="small" sx={{ mt: 1 }} onClick={save} disabled={saving}>
        {saving ? 'Saving…' : 'Save changes'}
      </Button>
      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </CardContent></Card>
  );
}
