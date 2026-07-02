import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  IconButton, Badge, Menu, Box, Typography, Button, MenuItem, Divider, Tooltip,
} from '@mui/material';
import {
  Notifications, NotificationsNone, VolumeUp, VolumeOff, ChatBubbleOutline,
} from '@mui/icons-material';
import { notifications as notificationsApi } from '../services/api';
import { playBellSound } from '../utils/push';

const SOUND_KEY = 'telegizer_notif_sound';
const POLL_MS = 45000;

function soundEnabled() {
  try { return localStorage.getItem(SOUND_KEY) !== 'off'; } catch { return true; }
}

/**
 * Reusable notification bell: unread badge, live polling, bell sound on new
 * arrivals, a dropdown of recent items, mark-all-read, a quick mute toggle and
 * a "View all" link to the full notifications page. Used in the Telegizer
 * desktop AppBar (Dashboard), the mobile top bar (AppLayout), and — with a
 * Guildizer api/viewAllPath — the Guildizer dashboard.
 */
export default function NotificationBell({
  size = 'medium',
  sx,
  api = notificationsApi,
  viewAllPath = '/notifications',
}) {
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [list, setList] = useState([]);
  const [anchor, setAnchor] = useState(null);
  const [muted, setMuted] = useState(!soundEnabled());
  const prevUnread = useRef(null);
  const pollRef = useRef(null);

  const poll = useCallback(async () => {
    try {
      const r = await api.unreadCount();
      const n = r.data.unread || 0;
      // Play the bell only when the count increases (not on first load).
      if (prevUnread.current !== null && n > prevUnread.current && !muted) {
        playBellSound();
      }
      prevUnread.current = n;
      setUnread(n);
    } catch { /* ignore transient errors */ }
  }, [muted, api]);

  useEffect(() => {
    poll();
    pollRef.current = setInterval(poll, POLL_MS);
    const onVisible = () => { if (document.visibilityState === 'visible') poll(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [poll]);

  const openMenu = async (e) => {
    setAnchor(e.currentTarget);
    try {
      const r = await api.list({ per_page: 8 });
      setList(r.data.notifications || []);
      const n = r.data.unread || 0;
      prevUnread.current = n;
      setUnread(n);
    } catch { /* ignore */ }
  };

  const markAllRead = async () => {
    try {
      await api.markAllRead();
      prevUnread.current = 0;
      setUnread(0);
      setList(prev => prev.map(n => ({ ...n, read: true })));
    } catch { /* ignore */ }
  };

  const toggleMute = () => {
    const next = !muted;
    setMuted(next);
    try { localStorage.setItem(SOUND_KEY, next ? 'off' : 'on'); } catch { /* ignore */ }
    if (!next) playBellSound(); // preview on un-mute
  };

  const openOne = async (n) => {
    setAnchor(null);
    if (!n.read) {
      try { await api.markRead(n.id); } catch { /* ignore */ }
      setUnread(u => Math.max(0, u - 1));
    }
    const url = n.metadata && n.metadata.url;
    navigate(url || viewAllPath);
    // Support replies deep-link to the dashboard AND pop the live-chat widget.
    if (n.metadata && n.metadata.open_support) {
      window.dispatchEvent(new Event('open-support-chat'));
    }
  };

  return (
    <>
      <IconButton onClick={openMenu} size={size} sx={sx} aria-label="Notifications">
        <Badge badgeContent={unread} color="error" max={99}>
          {unread > 0 ? <Notifications /> : <NotificationsNone />}
        </Badge>
      </IconButton>
      <Menu
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={() => setAnchor(null)}
        PaperProps={{ sx: { width: { xs: '92vw', sm: 360 }, maxHeight: 480 } }}
      >
        <Box sx={{ px: 2, py: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="subtitle2" fontWeight={700}>Notifications</Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Tooltip title={muted ? 'Unmute sound' : 'Mute sound'}>
              <IconButton size="small" onClick={toggleMute}>
                {muted ? <VolumeOff fontSize="small" /> : <VolumeUp fontSize="small" />}
              </IconButton>
            </Tooltip>
            {unread > 0 && <Button size="small" onClick={markAllRead}>Mark all read</Button>}
          </Box>
        </Box>
        <Divider />
        {list.length === 0 ? (
          <MenuItem disabled>
            <Typography variant="body2" color="text.secondary">No notifications yet</Typography>
          </MenuItem>
        ) : list.map(n => (
          <MenuItem
            key={n.id}
            onClick={() => openOne(n)}
            sx={{ whiteSpace: 'normal', alignItems: 'flex-start', py: 1,
              bgcolor: n.read ? 'transparent' : 'action.hover' }}
          >
            <Box>
              <Typography variant="body2" fontWeight={n.read ? 400 : 600}>{n.title}</Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{n.message || n.body}</Typography>
              <Typography variant="caption" display="block" color="text.disabled">
                {new Date(n.created_at).toLocaleString()}
              </Typography>
            </Box>
          </MenuItem>
        ))}
        <Divider />
        <Box sx={{ p: 1, display: 'flex', gap: 1 }}>
          {/* Live chat lives in the Telegizer app (ChatWidget). Offer it alongside
              notifications; skip in Guildizer where no chat widget is mounted. */}
          {typeof window !== 'undefined' && !window.location.pathname.startsWith('/guildizer') && (
            <Button
              size="small" variant="outlined" startIcon={<ChatBubbleOutline fontSize="small" />}
              onClick={() => { setAnchor(null); window.dispatchEvent(new Event('open-support-chat')); }}
              sx={{ flexShrink: 0 }}
            >
              Live Chat
            </Button>
          )}
          <Button fullWidth size="small" onClick={() => { setAnchor(null); navigate(viewAllPath); }}>
            View all
          </Button>
        </Box>
      </Menu>
    </>
  );
}
