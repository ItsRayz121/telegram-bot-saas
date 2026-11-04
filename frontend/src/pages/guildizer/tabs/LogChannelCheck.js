import React, { useEffect, useState } from 'react';
import { Alert, Button, Stack, CircularProgress } from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';

const ERR = {
  not_in_server: 'That channel is not in this server any more.',
  not_a_text_channel: 'Pick a text channel.',
  discord_unavailable: "Couldn't reach Discord to check it.",
};

// Under a staff log / alert channel picker: warns when @everyone can see the channel
// (moderation records would be public) and can send one test message so a missing
// permission shows up now, not when a real event fires. Nothing is saved here.
export default function LogChannelCheck({ guildId, channelId }) {
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(test) {
    setBusy(true); setErr(null);
    try {
      const { data } = await guildizerApi.post(`/api/guilds/${guildId}/log-channel/check`, { channel_id: channelId, test });
      setRes(data);
    } catch (e) {
      setRes(null); setErr(ERR[e?.response?.data?.error] || "Couldn't check the channel.");
    } finally { setBusy(false); }
  }
  useEffect(() => {
    setRes(null); setErr(null);
    if (channelId) run(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelId, guildId]);

  if (!channelId) return null;
  return (
    <Stack spacing={1} sx={{ mt: 1 }}>
      {err && <Alert severity="warning">{err}</Alert>}
      {res?.public && (
        <Alert severity="warning">
          <b>#{res.channel.name}</b> is visible to everyone in the server. Moderation logs can name members and
          reasons — make the channel staff-only in Discord (deny View Channel for @everyone).
        </Alert>
      )}
      {res && !res.public && !res.test && <Alert severity="success" icon={false} sx={{ py: 0 }}>#{res.channel.name} is not visible to @everyone.</Alert>}
      {res?.test?.ok && <Alert severity="success">Test message sent to #{res.channel.name}.</Alert>}
      {res?.test && !res.test.ok && (
        <Alert severity="error">
          {res.test.error === 'missing_permission'
            ? `Guildizer can't post in #${res.channel.name}. Give it View Channel + Send Messages there.`
            : "Discord rejected the test message."}
        </Alert>
      )}
      <div>
        <Button size="small" variant="outlined" disabled={busy} onClick={() => run(true)}
          startIcon={busy ? <CircularProgress size={14} /> : null}>Send test message</Button>
      </div>
    </Stack>
  );
}
