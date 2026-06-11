/**
 * Automation area subtabs (Telegizer-parity IA):
 * Scheduler · Auto Reply · Polls · Forwarding · Workflows · Webhooks.
 * Each wraps an existing card with its own data loading so subtabs stay
 * independent and deep-linkable.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Box, CircularProgress, Alert } from '@mui/material';
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

export function SchedulerSubtab({ guildId, channels = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const [messages, reload, error] = useList(guildId, 'scheduled-messages', 'messages');
  if (messages === null) return <Loading />;
  return (
    <>
      {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
      <SchedulerCard guildId={guildId} messages={messages} channels={textChannels} onChanged={reload} />
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
