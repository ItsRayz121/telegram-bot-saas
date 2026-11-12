import React, { useState } from 'react';
import {
  CircularProgress, Divider, IconButton, ListItemIcon, ListItemText, Menu, MenuItem, Tooltip,
} from '@mui/material';
import {
  Block, Gavel, LockOpen, PersonRemove, VolumeOff, VolumeUp, Warning as WarningIcon,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { settings } from '../../services/api';

const LABELS = {
  warn: 'Warn', mute: 'Mute (1h)', kick: 'Kick', tempban: 'Temp-ban (24h)',
  ban: 'Ban permanently', unmute: 'Unmute', unban: 'Unban',
};

// The ONE Telegram moderation hammer (official + custom bots). Used by the
// Warnings, Audit Log and Leaderboard rows so an admin can act on a member
// (warn / mute / kick / temp-ban / ban / lift) without leaving the page.
// Single, owner-chosen target only — never bulk (anti-ban rule).
export default function ModerationActions({ botId, groupId, userId, username, onDone }) {
  const [anchor, setAnchor] = useState(null);
  const [busy, setBusy] = useState(false);
  const close = () => setAnchor(null);

  const run = async (action, opts = {}) => {
    close();
    if (!userId) { toast.error('No target user id on this row'); return; }
    const who = username ? `@${username}` : `user ${userId}`;
    if (action !== 'warn' && !window.confirm(`${LABELS[action]} ${who}?`)) return;
    setBusy(true);
    try {
      await settings.moderateMember(botId, groupId, userId, { action, ...opts });
      toast.success(`${LABELS[action]} applied to ${who}`);
      onDone?.();
    } catch (e) {
      toast.error(e.response?.data?.error || `Failed to ${action}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Tooltip title="Moderation actions">
        <span>
          <IconButton size="small" disabled={busy || !userId} aria-label="Moderation actions"
            onClick={(e) => { e.stopPropagation(); setAnchor(e.currentTarget); }}>
            {busy ? <CircularProgress size={16} /> : <Gavel fontSize="small" />}
          </IconButton>
        </span>
      </Tooltip>
      <Menu anchorEl={anchor} open={!!anchor} onClose={close} onClick={(e) => e.stopPropagation()}>
        <MenuItem onClick={() => run('warn')}>
          <ListItemIcon><WarningIcon fontSize="small" color="warning" /></ListItemIcon>
          <ListItemText>Warn</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => run('mute', { duration_minutes: 60 })}>
          <ListItemIcon><VolumeOff fontSize="small" /></ListItemIcon>
          <ListItemText>Mute 1 hour</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => run('kick')}>
          <ListItemIcon><PersonRemove fontSize="small" /></ListItemIcon>
          <ListItemText>Kick (remove)</ListItemText>
        </MenuItem>
        <Divider />
        <MenuItem onClick={() => run('tempban', { duration_minutes: 1440 })}>
          <ListItemIcon><Gavel fontSize="small" color="error" /></ListItemIcon>
          <ListItemText>Temp-ban 24h</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => run('ban')}>
          <ListItemIcon><Block fontSize="small" color="error" /></ListItemIcon>
          <ListItemText>Ban permanently</ListItemText>
        </MenuItem>
        <Divider />
        {/* Reverse actions — lift a mute/ban applied by the bot or an admin. */}
        <MenuItem onClick={() => run('unmute')}>
          <ListItemIcon><VolumeUp fontSize="small" color="success" /></ListItemIcon>
          <ListItemText>Unmute (lift restriction)</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => run('unban')}>
          <ListItemIcon><LockOpen fontSize="small" color="success" /></ListItemIcon>
          <ListItemText>Unban</ListItemText>
        </MenuItem>
      </Menu>
    </>
  );
}
