/**
 * AI & Integrations area subtabs (Telegizer-parity IA): Knowledge Base.
 * (The Escalation subtab reuses ProtectionTab section="escalation".)
 *
 * Knowledge Base = the existing KB document manager plus the AI reply-behaviour
 * settings (kb_replies section on the moderation config).
 */
import React, { useEffect, useState } from 'react';
import {
  Grid, Box, Typography, TextField, MenuItem, Button, Switch, Chip,
  FormControlLabel, Alert, Snackbar, Card, CardActionArea, Slider,
} from '@mui/material';
import { CheckCircle } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';
import KnowledgeTab from './KnowledgeTab';

export function KnowledgeBaseSubtab({ guildId }) {
  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <PlatformAiCard guildId={guildId} />
      </Grid>
      <Grid item xs={12}>
        <KnowledgeTab guildId={guildId} />
      </Grid>
      <Grid item xs={12}>
        <AutoKnowledgeRepliesCard guildId={guildId} />
      </Grid>
      <Grid item xs={12}>
        <ReplyPersonalityCard guildId={guildId} />
      </Grid>
      <Grid item xs={12}>
        <AutoRepliesAsKnowledgeCard guildId={guildId} />
      </Grid>
      <Grid item xs={12}>
        <HumanLikeCard guildId={guildId} />
      </Grid>
      <Grid item xs={12}>
        <ImageUnderstandingCard guildId={guildId} />
      </Grid>
    </Grid>
  );
}

// Image Understanding (Multimodal AI) — vision Q&A on screenshots/errors/charts.
// Distinct from Moderation's NSFW image removal. Writes the image_understanding
// section on the moderation config.
function ImageUnderstandingCard({ guildId }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/moderation`)
      .then(({ data }) => setCfg(data.image_understanding || {})).catch(() => {});
  }, [guildId]);
  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));

  async function save() {
    setSaving(true);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/moderation`, { image_understanding: cfg });
      setCfg(data.image_understanding || cfg); setSaved(true);
    } catch { /* keep */ }
    setSaving(false);
  }
  if (!cfg) return null;
  const conf = Math.round((cfg.confidence_threshold ?? 0.65) * 100);
  return (
    <GuildizerCollapsibleCard id="ai.image_understanding" title="🖼️ Image Understanding (Multimodal AI)">
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        The bot analyzes screenshots, error messages and charts shared with a question, and replies.
        Smart gating keeps most images off the API. Low-confidence results escalate to admins (via the Escalation settings).
      </Typography>
      <FormControlLabel control={<Switch checked={!!cfg.enabled} onChange={(e) => set({ enabled: e.target.checked })} />}
        label="Enable Image Understanding" />
      {cfg.enabled && (
        <Grid container spacing={1.5} sx={{ mt: 0.5 }}>
          <Grid item xs={12} sm={6}>
            <FormControlLabel control={<Switch size="small" checked={cfg.mention_only !== false} onChange={(e) => set({ mention_only: e.target.checked })} />}
              label="Only when the bot is @mentioned" />
          </Grid>
          <Grid item xs={12} sm={6}>
            <FormControlLabel control={<Switch size="small" checked={cfg.require_caption !== false} onChange={(e) => set({ require_caption: e.target.checked })} />}
              label="Require a caption/text with the image" />
          </Grid>
          <Grid item xs={12} sm={6}>
            <FormControlLabel control={<Switch size="small" checked={cfg.escalate_low_confidence !== false} onChange={(e) => set({ escalate_low_confidence: e.target.checked })} />}
              label="Escalate to admins when confidence is low" />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField select size="small" fullWidth label="Cost mode"
              value={cfg.cost_mode || 'balanced'} onChange={(e) => set({ cost_mode: e.target.value })}>
              <MenuItem value="aggressive_savings">Aggressive savings — @mention + error keywords</MenuItem>
              <MenuItem value="balanced">Balanced (recommended) — caption looks like a question</MenuItem>
              <MenuItem value="quality">Quality — any image when addressed</MenuItem>
            </TextField>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography variant="body2" gutterBottom>Confidence threshold: <strong>{conf}%</strong></Typography>
            <Slider value={conf} min={30} max={90} step={5} marks valueLabelDisplay="auto"
              valueLabelFormat={(v) => `${v}%`} onChange={(_, v) => set({ confidence_threshold: v / 100 })} sx={{ maxWidth: 300 }} />
            <Typography variant="caption" color="text.secondary" display="block">Below this → escalate instead of replying.</Typography>
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField type="number" size="small" fullWidth label="Max image size (MB)"
              value={cfg.max_image_size_mb ?? 5} inputProps={{ min: 1, max: 10 }}
              onChange={(e) => set({ max_image_size_mb: Number(e.target.value) || 5 })} />
          </Grid>
        </Grid>
      )}
      <Button variant="contained" size="small" sx={{ mt: 1.5, display: 'block' }} onClick={save} disabled={saving}>
        {saving ? 'Saving…' : 'Save changes'}
      </Button>
      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </GuildizerCollapsibleCard>
  );
}

// AI Provider status — Guildizer uses one platform AI key for the whole fleet
// (no per-guild keys by design), so this surfaces the live provider state.
function PlatformAiCard({ guildId }) {
  const [s, setS] = useState(null);
  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/ai-status`).then(({ data }) => setS(data)).catch(() => setS(false));
  }, [guildId]);
  return (
    <GuildizerCollapsibleCard id="ai.platform_ai" title="🔑 AI Provider"
      badge={s && s !== false ? <Chip size="small" color={s.provider_connected ? 'success' : 'default'}
        label={s.provider_connected ? 'Platform AI Active' : 'Not connected'} /> : null}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Guildizer includes managed <strong>Platform AI</strong> for this whole server — there is
        no API key to add, no billing to set up and nothing to configure. It powers AI moderation,
        knowledge-base auto-replies, AI welcome messages and the reply personalities out of the box,
        included in your plan.
        {s && s !== false && <> Current provider: <strong>{s.provider}</strong>{s.provider_connected ? ' — connected and active.' : ' — not configured on this instance.'}</>}
      </Typography>
      <Typography variant="caption" color="text.disabled" display="block">
        The platform key is managed fleet-wide and applies to every server automatically. Per-server
        provider overrides aren't needed on Guildizer — if your plan changes, AI access updates here.
      </Typography>
    </GuildizerCollapsibleCard>
  );
}

const PERSONALITIES = [
  ['professional_support', '🎧 Professional Customer Support', 'Calm, concise, trusted support-agent feel. Best for SaaS, services and product communities.'],
  ['friendly', '🤝 Friendly Community Moderator', 'Warm, conversational, community-first. Best for hobby groups, fan communities and welcoming servers.'],
  ['expert', '📚 Serious Expert', 'Knowledgeable, precise, structured. Best for technical, financial and B2B communities.'],
  ['community_manager', '🪙 Web3 Community Manager', 'Crypto-native tone, ecosystem-focused, educational but casual. Best for crypto and Web3 projects.'],
  ['concise', '⚡ Concise', 'Short, direct answers with minimal fluff.'],
];

// Human-Like Community Interaction (social_replies) — surfaced on the AI tab for
// Telegizer parity; writes the same moderation config as the Moderation tab.
function HumanLikeCard({ guildId }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/moderation`)
      .then(({ data }) => setCfg(data.social_replies || {})).catch(() => {});
  }, [guildId]);
  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));

  async function save() {
    setSaving(true);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/moderation`, { social_replies: cfg });
      setCfg(data.social_replies || cfg); setSaved(true);
    } catch { /* keep */ }
    setSaving(false);
  }
  if (!cfg) return null;
  return (
    <GuildizerCollapsibleCard id="ai.human_like" title="🙋 Human-Like Community Interaction">
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Bot reacts and replies naturally to appreciation ("thanks", "helpful", "solved") — no AI
        cost, personality-aware, with spam protection.
      </Typography>
      <FormControlLabel control={<Switch checked={!!cfg.enabled} onChange={(e) => set({ enabled: e.target.checked })} />}
        label="Enable human-like interaction" />
      {cfg.enabled && (
        <>
          <FormControlLabel control={<Switch checked={cfg.react_to_appreciation !== false} onChange={(e) => set({ react_to_appreciation: e.target.checked })} />}
            label="React with emoji to appreciation" />
          <FormControlLabel control={<Switch checked={cfg.reply_to_appreciation !== false} onChange={(e) => set({ reply_to_appreciation: e.target.checked })} />}
            label="Reply with a text acknowledgment" />
          <TextField select size="small" margin="dense" fullWidth label="Interaction style"
            value={cfg.mode || 'friendly'} onChange={(e) => set({ mode: e.target.value })}>
            {[['minimal', 'Minimal'], ['professional', 'Professional'], ['friendly', 'Friendly'], ['community_manager', 'Community Manager']]
              .map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
          </TextField>
          <TextField type="number" size="small" margin="dense" fullWidth label="Cooldown per user (minutes)"
            value={cfg.cooldown_minutes ?? 5} inputProps={{ min: 1, max: 1440 }}
            onChange={(e) => set({ cooldown_minutes: Number(e.target.value) })} />
        </>
      )}
      <Button variant="contained" size="small" sx={{ mt: 1 }} onClick={save} disabled={saving}>
        {saving ? 'Saving…' : 'Save changes'}
      </Button>
      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </GuildizerCollapsibleCard>
  );
}

// Automatic Knowledge Replies — the behaviour toggles (the "AI Reply
// Personality" half now lives in its own card below, for Telegizer parity).
// Both cards write the kb_replies section; the backend merges field-by-field
// so they never clobber each other.
function AutoKnowledgeRepliesCard({ guildId }) {
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
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/moderation`, {
        kb_replies: {
          enabled: cfg.enabled, mention_only: cfg.mention_only,
          low_confidence_fallback: cfg.low_confidence_fallback,
          min_words: cfg.min_words, reply_length: cfg.reply_length,
          emoji_usage: cfg.emoji_usage, formality: cfg.formality,
        },
      });
      setCfg(data.kb_replies || cfg);
      setSaved(true);
    } catch { setError('Save failed.'); }
    setSaving(false);
  }

  if (!cfg) return null;

  return (
    <GuildizerCollapsibleCard id="ai.auto_knowledge_replies" title="Automatic Knowledge Replies"
      badge={<Chip label="AI" size="small" color="primary" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />}>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Controls how the bot answers from the knowledge base. /ask always works; automatic
        replies follow these rules (one auto-reply per member per 30 seconds).
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
    </GuildizerCollapsibleCard>
  );
}

// AI Reply Personality — its own card (Telegizer parity). Writes only the
// personality + custom_instructions keys of kb_replies (merged server-side).
function ReplyPersonalityCard({ guildId }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/moderation`)
      .then(({ data }) => setCfg(data.kb_replies || {}))
      .catch(() => setError('Failed to load personality settings.'));
  }, [guildId]);

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));

  async function save() {
    setSaving(true); setError(null);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/moderation`, {
        kb_replies: { personality: cfg.personality, custom_instructions: cfg.custom_instructions || '' },
      });
      setCfg(data.kb_replies || cfg);
      setSaved(true);
    } catch { setError('Save failed.'); }
    setSaving(false);
  }

  if (!cfg) return null;

  return (
    <GuildizerCollapsibleCard id="ai.reply_personality" title="🎭 AI Reply Personality"
      badge={<Chip label="AI" size="small" color="primary" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />}>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Shapes how the AI talks when answering from the knowledge base. Each uses a
        professionally engineered prompt designed to feel natural — not robotic.
      </Typography>
      <Grid container spacing={1}>
        {PERSONALITIES.map(([value, title, desc]) => {
          const active = (cfg.personality || 'professional_support') === value;
          return (
            <Grid item xs={12} sm={6} key={value}>
              <Card variant="outlined" sx={{ borderColor: active ? 'primary.main' : 'divider', borderWidth: active ? 2 : 1, height: '100%' }}>
                <CardActionArea onClick={() => set({ personality: value })} sx={{ p: 1.25, height: '100%', alignItems: 'flex-start' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Typography variant="body2" fontWeight={700}>{title}</Typography>
                    {active && <CheckCircle color="primary" sx={{ fontSize: 16 }} />}
                  </Box>
                  <Typography variant="caption" color="text.secondary">{desc}</Typography>
                </CardActionArea>
              </Card>
            </Grid>
          );
        })}
      </Grid>
      <TextField multiline minRows={2} size="small" margin="dense" fullWidth
        label="Custom instructions"
        placeholder={'e.g. Always reply in English and Spanish\nNever recommend competitor tools\nLink to docs.example.com when relevant'}
        value={cfg.custom_instructions || ''} inputProps={{ maxLength: 1200 }}
        onChange={(e) => set({ custom_instructions: e.target.value })}
        helperText={`${(cfg.custom_instructions || '').length}/1200 — extra rules appended to every KB answer.`} />
      {error && <Alert severity="error" sx={{ mt: 1, py: 0 }}>{error}</Alert>}
      <Button variant="contained" size="small" sx={{ mt: 1 }} onClick={save} disabled={saving}>
        {saving ? 'Saving…' : 'Save changes'}
      </Button>
      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </GuildizerCollapsibleCard>
  );
}

// Auto Replies as AI Knowledge — surfaces auto-reply rules flagged "use as AI
// knowledge" so the /ask AI can answer from them too (Telegizer parity). The
// per-rule toggle itself lives on Automation → Auto Reply.
function AutoRepliesAsKnowledgeCard({ guildId }) {
  const [rules, setRules] = useState(null);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/auto-responses`)
      .then(({ data }) => setRules(data.responses || [])).catch(() => setRules([]));
  }, [guildId]);

  const knowledgeRules = (rules || []).filter((r) => r.use_as_ai_knowledge);

  return (
    <GuildizerCollapsibleCard id="ai.auto_replies_as_knowledge" title="🔁 Auto Replies as AI Knowledge"
      badge={<Chip label="AI" size="small" color="primary" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />}>
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Auto-reply rules you flag as “AI knowledge” are also used by the /ask AI to answer
        related questions — not just exact trigger matches. Toggle a rule’s “AI knowledge”
        switch on <strong>Automation → Auto Reply</strong>.
      </Typography>
      {rules === null ? (
        <Typography variant="body2" color="text.secondary">Loading…</Typography>
      ) : knowledgeRules.length === 0 ? (
        <Alert severity="info" icon={false} sx={{ fontSize: '0.8rem' }}>
          No auto-reply rules are used as AI knowledge yet. Add rules on Automation → Auto Reply
          and turn on their “AI knowledge” switch.
        </Alert>
      ) : (
        <Box>
          <Typography variant="body2" fontWeight={600} mb={0.5}>
            {knowledgeRules.length} rule{knowledgeRules.length === 1 ? '' : 's'} feeding the AI:
          </Typography>
          {knowledgeRules.map((r) => (
            <Chip key={r.id} size="small" variant="outlined" sx={{ mr: 0.5, mb: 0.5 }}
              label={r.trigger?.length > 30 ? `${r.trigger.slice(0, 30)}…` : r.trigger} />
          ))}
        </Box>
      )}
    </GuildizerCollapsibleCard>
  );
}
