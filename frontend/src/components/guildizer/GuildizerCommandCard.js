// Command Management card for Guildizer (Discord). Same table as Telegizer, one card per section:
// pass `only` (commands this card owns) or `except` (everything the other cards own).
import React, { useCallback } from 'react';
import { Typography } from '@mui/material';
import { toast } from 'react-toastify';
import guildizerApi from '../../services/guildizerApi';
import GuildizerCollapsibleCard from './GuildizerCollapsibleCard';
import CommandManagementTable, { useCommandTable } from '../CommandManagementTable';

export const GZ_LEVELING_COMMANDS = ['/rank', '/leaderboard'];
export const GZ_MOD_COMMANDS = ['/warn', '/warnings', '/removewarning', '/mute', '/unmute', '/kick', '/ban', '/unban',
  '/tempban', '/purge', '/auditlog', '/report'];

export default function GuildizerCommandCard({ id, guildId, only, except = [], accessLabel, sx,
  description = 'One row per command. Status off turns the command off on this server. The timer starts when the bot\'s reply is sent, and the reply is then deleted by the server (also after a restart). Private replies are never touched.' }) {
  const load = useCallback(() => guildizerApi.get(`/api/guilds/${guildId}/command-table`), [guildId]);
  const save = useCallback((commands) => guildizerApi.put(`/api/guilds/${guildId}/command-table`, { commands }), [guildId]);
  const table = useCommandTable({
    load, save,
    onSaved: () => toast.success('Command settings saved!'),
    onError: (e) => toast.error(e?.response?.data?.error || 'Could not save the command settings'),
  });
  const rows = table.rows.filter((r) => (only ? only.includes(r.command) : !except.includes(r.command)));
  const names = rows.map((r) => r.command);
  return (
    <GuildizerCollapsibleCard id={id} title="Command Management" sx={sx}>
      <Typography variant="body2" color="text.secondary" mb={2}>{description}</Typography>
      <CommandManagementTable
        rows={rows}
        limits={table.limits}
        failures={table.failures}
        loading={table.loading}
        saving={table.saving}
        dirty={table.dirty}
        invalid={rows.some((r) => r._invalid)}
        accessMode="fixed"
        accessLabel={accessLabel}
        onChange={table.change}
        onSave={() => table.save(names)}
      />
    </GuildizerCollapsibleCard>
  );
}
