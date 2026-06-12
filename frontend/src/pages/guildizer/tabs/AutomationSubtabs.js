/**
 * Automation area subtabs (Telegizer-parity IA):
 * Scheduler · Auto Reply · Polls · Forwarding · Workflows · Webhooks.
 * Each wraps an existing card with its own data loading so subtabs stay
 * independent and deep-linkable.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Box, CircularProgress, Alert, Card, CardContent, Typography, Switch,
  FormControlLabel, TextField, MenuItem, Button, Snackbar,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';
import { SchedulerCard, PollsCard, AutoResponsesCard } from './ContentTab';
import { WorkflowsCard, MirrorsCard, WebhooksCard } from './AutomationTab';

const TEXT_TYPES = new Set([0, 5]);

function useList(guildId, path, field) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const reload = useCallback(async () => {
    try {
      const { data } = await guildizerApi.get(`/api/guilds/${guildId}/${path}`);
      setItems(data[field]); setError(null);
    } catch { setError('Failed to load.'); setItems([]); }
  }, [guildId, path, field]);
  useEffect(() => { reload(); }, [reload]);
  return [items, reload, error];
}

function Loading() {
  return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
}

// Announcement (news) channels can crosspost to follower servers.
const ANNOUNCEMENT_TYPE = 5;

function AutoPublishCard({ guildId, channels = [] }) {
  const announcementChannels = channels.filter((c) => c.type === ANNOUNCEMENT_TYPE);
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/auto-publish`)
      .then(({ data }) => setCfg(data))
      .catch(() => setError('Failed to load auto-publish settings.'));
  }, [guildId]);

  async function save() {
    setSaving(true); setError(null);
    try {
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/auto-publish`, cfg);
      setCfg(data); setSaved(true);
    } catch { setError('Save failed.'); } finally { setSaving(false); }
  }

  if (!cfg) return error ? <Alert severity="warning" sx={{ mt: 2 }}>{error}</Alert> : null;
  return (
    <Card variant="outlined" sx={{ mt: 2 }}><CardContent>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>📣 Auto-publish announcements</Typography>
      <FormControlLabel control={<Switch checked={!!cfg.enabled} onChange={(e) => setCfg((c) => ({ ...c, enabled: e.target.checked }))} />}
        label="Publish posts in announcement channels to follower servers automatically" />
      <Typography variant="caption" color="text.secondary" display="block" mb={1}>
        Applies to Announcement-type channels only (Discord caps publishing at 10 posts per
        channel per hour). Scheduled messages the bot posts there are published too.
      </Typography>
      {announcementChannels.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          This server has no announcement channels yet — convert one in Discord via
          Edit Channel → Announcement Channel.
        </Typography>
      ) : (
        <TextField select fullWidth size="small" margin="dense" label="Channels (empty = all announcement channels)"
          SelectProps={{ multiple: true }} value={cfg.channel_ids || []}
          onChange={(e) => setCfg((c) => ({ ...c, channel_ids: e.target.value }))}>
          {announcementChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
        </TextField>
      )}
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1 }}>
        {error && <Alert severity="error" sx={{ py: 0, mr: 2 }}>{error}</Alert>}
        <Button variant="contained" size="small" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </Box>
      <Snackbar open={saved} autoHideDuration={2000} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </CardContent></Card>
  );
}

export function SchedulerSubtab({ guildId, channels = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const [messages, reload, error] = useList(guildId, 'scheduled-messages', 'messages');
  if (messages === null) return <Loading />;
  return (
    <>
      {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
      <SchedulerCard guildId={guildId} messages={messages} channels={textChannels} onChanged={reload} />
      <AutoPublishCard guildId={guildId} channels={channels} />
    </>
  );
}

export function AutoReplySubtab({ guildId }) {
  const [responses, reload, error] = useList(guildId, 'auto-responses', 'responses');
  if (responses === null) return <Loading />;
  return (
    <>
      {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
      <AutoResponsesCard guildId={guildId} responses={responses} onChanged={reload} />
    </>
  );
}

export function PollsSubtab({ guildId, channels = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const [polls, reload, error] = useList(guildId, 'polls', 'polls');
  if (polls === null) return <Loading />;
  return (
    <>
      {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
      <PollsCard guildId={guildId} polls={polls} channels={textChannels} onChanged={reload} />
    </>
  );
}

export function ForwardingSubtab({ guildId, channels = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const [mirrors, reload, error] = useList(guildId, 'mirrors', 'mirrors');
  if (mirrors === null) return <Loading />;
  return (
    <>
      {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
      <MirrorsCard guildId={guildId} mirrors={mirrors} channels={textChannels} onChanged={reload} />
    </>
  );
}

export function WorkflowsSubtab({ guildId, channels = [], roles = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const assignableRoles = roles.filter((r) => !r.managed && r.name !== '@everyone');
  const [workflows, reload, error] = useList(guildId, 'workflows', 'workflows');
  if (workflows === null) return <Loading />;
  return (
    <>
      {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
      <WorkflowsCard guildId={guildId} workflows={workflows} channels={textChannels}
        roles={assignableRoles} onChanged={reload} />
    </>
  );
}

export function WebhooksSubtab({ guildId, channels = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const [inbound, reloadIn, errIn] = useList(guildId, 'inbound-webhooks', 'webhooks');
  const [outbound, reloadOut, errOut] = useList(guildId, 'outbound-webhooks', 'webhooks');
  if (inbound === null || outbound === null) return <Loading />;
  const reload = () => Promise.all([reloadIn(), reloadOut()]);
  return (
    <>
      {(errIn || errOut) && <Alert severity="warning" sx={{ mb: 2 }}>{errIn || errOut}</Alert>}
      <WebhooksCard guildId={guildId} inbound={inbound} outbound={outbound}
        channels={textChannels} onChanged={reload} />
    </>
  );
}
