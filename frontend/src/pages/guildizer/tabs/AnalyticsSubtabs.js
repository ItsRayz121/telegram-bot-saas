/**
 * Analytics area subtabs (Telegizer-parity IA):
 * Leaderboard · Audit Log · Warnings · Digest · AI Activity.
 * (Overview reuses AnalyticsTab, Members reuses MembersTab.)
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Typography, Chip, CircularProgress, Alert,
  List, ListItem, ListItemText, IconButton,
} from '@mui/material';
import { Delete } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import { DigestCard } from './ContentTab';

const TEXT_TYPES = new Set([0, 5]);
const CAT_LABEL = {
  nsfw: 'NSFW', csam: 'CSAM', invite: 'Invite', link: 'Link', custom: 'Blocked word',
  spam: 'Spam', raid: 'Raid', lockdown_join: 'Lockdown join', join_gate: 'Join gate', manual_lockdown: 'Lockdown',
  external_link: 'External link', emoji_flood: 'Emoji flood', caps_lock: 'Caps lock', language: 'Language',
  attachment: 'Attachment', sticker: 'Sticker', voice_message: 'Voice message',
  warning: 'Warning', moderation: 'Moderation', report: 'Report',
  smart_mod: 'Smart mod', smart_promo: 'Smart mod', image_ai: 'Image AI', image_nsfw: 'Image AI',
  verification: 'Verification', bot_policy: 'Bot policy', escalation: 'Escalation',
};
const CAT_COLOR = { nsfw: 'error', csam: 'error', raid: 'warning', manual_lockdown: 'warning', lockdown_join: 'warning', invite: 'info', link: 'info' };
// Event categories produced by the AI layers — used to filter AI Activity.
const AI_CATEGORIES = new Set(['smart_mod', 'smart_promo', 'image_ai', 'image_nsfw', 'ask', 'ai', 'escalation']);

function Loading() {
  return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
}

// ── Leaderboard ────────────────────────────────────────────────────────────────
export function LeaderboardSubtab({ guildId }) {
  const [board, setBoard] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/leaderboard?limit=50`)
      .then(({ data }) => setBoard(data.leaderboard || []))
      .catch(() => { setError('Failed to load the leaderboard.'); setBoard([]); });
  }, [guildId]);

  if (board === null) return <Loading />;

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>XP leaderboard (top 50)</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Your most active members ranked by XP earned from chatting and voice activity.
      </Typography>
      {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}</Alert>}
      {board.length === 0 && <Typography variant="body2" color="text.secondary">No XP earned yet.</Typography>}
      <List dense>
        {board.map((m) => (
          <ListItem key={m.user_id} disableGutters
            secondaryAction={<Typography variant="caption" color="text.secondary">{m.xp} XP</Typography>}>
            <Typography variant="body2" fontWeight={700} color="primary.main" sx={{ width: 38 }}>#{m.rank}</Typography>
            <ListItemText primary={m.username || m.user_id} primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
            <Chip size="small" label={`Lvl ${m.level}`} sx={{ mr: 1 }} />
          </ListItem>
        ))}
      </List>
    </CardContent></Card>
  );
}

// ── Audit Log: every protection / moderation event ─────────────────────────────
export function AuditLogSubtab({ guildId }) {
  return <EventFeed guildId={guildId} title="Audit log" limit={150} />;
}

// ── AI Activity: AI-driven events only ─────────────────────────────────────────
export function AIActivitySubtab({ guildId }) {
  return (
    <EventFeed guildId={guildId} title="AI activity" limit={200}
      filter={(e) => AI_CATEGORIES.has(e.category)}
      emptyText="No AI actions yet. Enable Smart mod, Image AI or the knowledge base to see activity here." />
  );
}

function EventFeed({ guildId, title, limit, filter, emptyText = 'No events yet.' }) {
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/protection/events?limit=${limit}`)
      .then(({ data }) => setEvents(filter ? data.events.filter(filter) : data.events))
      .catch(() => { setError('Failed to load events.'); setEvents([]); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId, limit]);

  if (events === null) return <Loading />;

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>{title}</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        A read-only feed of recent moderation and protection events on this server.
      </Typography>
      {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}</Alert>}
      {events.length === 0 && <Typography variant="body2" color="text.secondary">{emptyText}</Typography>}
      <List dense>
        {events.map((e) => (
          <ListItem key={e.id} disableGutters
            secondaryAction={<Typography variant="caption" color="text.disabled">{new Date(e.created_at).toLocaleString()}</Typography>}>
            <Chip size="small" label={CAT_LABEL[e.category] || e.category} color={CAT_COLOR[e.category] || 'default'} variant="outlined" sx={{ mr: 1 }} />
            <ListItemText primary={`${e.action} — ${e.username ? e.username + ' · ' : ''}${e.detail || ''}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
      </List>
    </CardContent></Card>
  );
}

// ── Warnings: active warnings with removal ─────────────────────────────────────
export function WarningsSubtab({ guildId }) {
  const [warnings, setWarnings] = useState(null);
  const [error, setError] = useState(null);

  const reload = useCallback(() => guildizerApi.get(`/api/guilds/${guildId}/warnings?limit=100`)
    .then(({ data }) => setWarnings(data.warnings))
    .catch(() => { setError('Failed to load warnings.'); setWarnings([]); }), [guildId]);

  useEffect(() => { reload(); }, [reload]);

  async function remove(id) {
    try {
      await guildizerApi.delete(`/api/guilds/${guildId}/warnings/${id}`);
      await reload();
    } catch { setError('Could not remove the warning.'); }
  }

  if (warnings === null) return <Loading />;

  return (
    <Card variant="outlined"><CardContent>
      <Typography variant="h6" fontWeight={600} mb={1}>Warnings</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Active warnings issued to members. Remove any that no longer apply.
      </Typography>
      {error && <Alert severity="warning" sx={{ mb: 1 }} onClose={() => setError(null)}>{error}</Alert>}
      {warnings.length === 0 && <Typography variant="body2" color="text.secondary">No warnings on record. 🎉</Typography>}
      <List dense>
        {warnings.map((w) => (
          <ListItem key={w.id} disableGutters
            secondaryAction={(
              <IconButton size="small" color="error" onClick={() => remove(w.id)} title="Remove warning">
                <Delete fontSize="small" />
              </IconButton>
            )}>
            <ListItemText
              primary={`${w.username || w.user_id} — ${w.reason || 'no reason'}`}
              secondary={`by ${w.moderator_name || 'automod'} · ${new Date(w.created_at).toLocaleString()}`}
              primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
          </ListItem>
        ))}
      </List>
    </CardContent></Card>
  );
}

// ── Digest: reuses the digest settings card ────────────────────────────────────
export function DigestSubtab({ guildId, channels = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  return <DigestCard guildId={guildId} channels={textChannels} />;
}
