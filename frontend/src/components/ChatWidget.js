import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Box, Paper, IconButton, Fab, Typography, TextField, Badge, Avatar,
  CircularProgress, Tooltip, Zoom, Chip, useMediaQuery, useTheme,
} from '@mui/material';
import {
  ChatBubbleOutline, Close, Send, SupportAgent,
} from '@mui/icons-material';
import { support } from '../services/api';
import { PALETTE } from '../theme';
import { buildThreadItems, closeReasonLabel, fmtDivider, productMeta, defaultProductForPath, PRODUCTS } from '../utils/supportThread';

// Persisted "last message id the user has seen", so the unread dot survives page
// reloads without depending on a server flag.
const LS_KEY = 'support_last_seen_id';
const readLastSeen = () => {
  try { return parseInt(localStorage.getItem(LS_KEY) || '0', 10) || 0; } catch { return 0; }
};
const writeLastSeen = (id) => { try { localStorage.setItem(LS_KEY, String(id)); } catch {} };

const POLL_OPEN_MS = 4000;    // active conversation
const POLL_IDLE_MS = 25000;   // background check for new replies

function maxId(msgs) {
  return msgs.reduce((m, x) => (x.id > m ? x.id : m), 0);
}

export default function ChatWidget() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const { pathname } = useLocation();

  const [enabled, setEnabled] = useState(true);   // false if the user isn't authenticated
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [convStatus, setConvStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [draft, setDraft] = useState('');
  const [hasUnread, setHasUnread] = useState(false);
  const [product, setProduct] = useState(() => defaultProductForPath(pathname));
  // Once the user manually picks a product for the current episode, stop
  // re-seeding it from the route (otherwise navigating mid-compose would silently
  // overwrite their choice). Reset when a fresh episode begins.
  const productTouchedRef = useRef(false);

  // The next message starts a NEW episode whenever there's no open session, so
  // that's when we ask "what's this about?".
  const needsProduct = !sessions.some((s) => s.status === 'open');
  useEffect(() => {
    // While the user hasn't chosen, keep the picker on the route-smart default.
    if (needsProduct && !productTouchedRef.current) setProduct(defaultProductForPath(pathname));
    // Episode is active again → arm the next episode to re-seed from the route.
    if (!needsProduct) productTouchedRef.current = false;
  }, [needsProduct, pathname]);

  const chooseProduct = (value) => { productTouchedRef.current = true; setProduct(value); };

  const lastIdRef = useRef(0);            // newest message id we hold
  const listRef = useRef(null);
  const openRef = useRef(false);
  useEffect(() => { openRef.current = open; }, [open]);

  const scrollToBottom = useCallback(() => {
    const el = listRef.current;
    if (el) requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
  }, []);

  // ── Load full history when the panel opens ──────────────────────────────────
  const loadChat = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await support.getChat();
      const msgs = data.messages || [];
      setMessages(msgs);
      setSessions(data.sessions || []);
      setConvStatus(data.conversation?.status || null);
      const top = maxId(msgs);
      lastIdRef.current = top;
      writeLastSeen(top);
      setHasUnread(false);
      scrollToBottom();
    } catch (err) {
      if (err?.response?.status === 401 || err?.response?.status === 422) setEnabled(false);
    } finally {
      setLoading(false);
    }
  }, [scrollToBottom]);

  // ── Poll for new messages ───────────────────────────────────────────────────
  const poll = useCallback(async () => {
    try {
      const since = openRef.current ? lastIdRef.current : readLastSeen();
      const { data } = await support.poll(since);
      const fresh = data.messages || [];
      if (openRef.current) {
        // Panel is open → keep session dividers + status fresh, append new msgs.
        setSessions(data.sessions || []);
        setConvStatus(data.conversation?.status || null);
        if (fresh.length) {
          setMessages((prev) => {
            const seen = new Set(prev.map((m) => m.id));
            return [...prev, ...fresh.filter((m) => !seen.has(m.id))];
          });
          const top = maxId(fresh);
          if (top > lastIdRef.current) lastIdRef.current = top;
          writeLastSeen(lastIdRef.current);
          scrollToBottom();
        }
      } else if (fresh.some((m) => m.author === 'admin')) {
        // Closed → an admin replied: raise the unread dot (sticky until opened).
        setHasUnread(true);
      }
    } catch (err) {
      if (err?.response?.status === 401 || err?.response?.status === 422) setEnabled(false);
    }
  }, [scrollToBottom]);

  // Interval driver — cadence depends on whether the panel is open.
  useEffect(() => {
    if (!enabled) return undefined;
    poll(); // immediate check
    const id = setInterval(poll, open ? POLL_OPEN_MS : POLL_IDLE_MS);
    return () => clearInterval(id);
  }, [enabled, open, poll]);

  // Open the widget from anywhere (Support dropdown, deep links).
  useEffect(() => {
    const handler = () => setOpen(true);
    window.addEventListener('open-support-chat', handler);
    return () => window.removeEventListener('open-support-chat', handler);
  }, []);

  useEffect(() => {
    if (open && messages.length === 0) loadChat();
    if (open) setHasUnread(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSend = async () => {
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setDraft('');
    // Optimistic bubble so the UI feels instant. Tag it with the currently-open
    // session (if any) so it groups correctly; otherwise a sentinel so it starts
    // its own "new conversation" divider until the server assigns a real session.
    const openSess = sessions.find((s) => s.status === 'open');
    const optimisticSid = openSess ? openSess.id : '__pending__';
    const tempId = -Date.now();
    setMessages((prev) => [...prev, { id: tempId, session_id: optimisticSid, author: 'user', body, created_at: new Date().toISOString(), _pending: true }]);
    scrollToBottom();
    try {
      const { data } = await support.send(body, product);
      const real = data.message;
      setMessages((prev) => prev.map((m) => (m.id === tempId ? real : m)));
      setConvStatus(data.conversation?.status || 'open');
      if (data.session) {
        setSessions((prev) => {
          const rest = prev.filter((s) => s.id !== data.session.id);
          return [...rest, data.session];
        });
      }
      if (real?.id > lastIdRef.current) { lastIdRef.current = real.id; writeLastSeen(real.id); }
    } catch (err) {
      // Roll the optimistic message back and restore the draft.
      setMessages((prev) => prev.filter((m) => m.id !== tempId));
      setDraft(body);
      if (err?.response?.status === 401 || err?.response?.status === 422) setEnabled(false);
    } finally {
      setSending(false);
    }
  };

  // Hidden for unauthenticated users and inside the admin panel (admins have the
  // Support inbox tab there; a floating widget would overlap it).
  if (!enabled || pathname.startsWith('/admin')) return null;

  const bubbleBottom = isMobile ? 'calc(var(--bottom-nav-clearance, 56px) + 14px)' : 24;

  return (
    <>
      {/* Panel */}
      <Zoom in={open} unmountOnExit>
        <Paper
          elevation={12}
          sx={{
            position: 'fixed', zIndex: (t) => t.zIndex.modal,
            display: 'flex', flexDirection: 'column',
            overflow: 'hidden',
            ...(isMobile
              ? { inset: 0, borderRadius: 0 }
              : { bottom: 96, right: 24, width: 372, height: 'min(560px, 78vh)', borderRadius: 3,
                  border: '1px solid rgba(255,255,255,0.08)' }),
          }}
        >
          {/* Header */}
          <Box sx={{
            px: 2, py: 1.5, display: 'flex', alignItems: 'center', gap: 1.25,
            background: `linear-gradient(135deg, ${PALETTE.blue}, ${PALETTE.blue}cc)`,
            color: '#fff', flexShrink: 0,
          }}>
            <Avatar sx={{ bgcolor: 'rgba(255,255,255,0.2)', width: 34, height: 34 }}>
              <SupportAgent fontSize="small" />
            </Avatar>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography fontWeight={700} fontSize="0.92rem" lineHeight={1.2}>Live Support</Typography>
              <Typography fontSize="0.68rem" sx={{ opacity: 0.85 }}>We typically reply within a few minutes</Typography>
            </Box>
            <IconButton size="small" onClick={() => setOpen(false)} sx={{ color: '#fff' }}>
              <Close fontSize="small" />
            </IconButton>
          </Box>

          {/* Messages */}
          <Box ref={listRef} sx={{ flex: 1, overflowY: 'auto', px: 1.5, py: 1.5, bgcolor: PALETTE.bg0 }}>
            {loading && messages.length === 0 ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress size={22} /></Box>
            ) : messages.length === 0 ? (
              <Box sx={{ textAlign: 'center', mt: 5, px: 2, color: 'text.secondary' }}>
                <SupportAgent sx={{ fontSize: 40, opacity: 0.4, mb: 1 }} />
                <Typography fontSize="0.85rem" fontWeight={600} color="text.primary">How can we help?</Typography>
                <Typography fontSize="0.75rem" sx={{ mt: 0.5 }}>
                  Send us a message and our team will reply here — you’ll be notified when we do.
                </Typography>
              </Box>
            ) : (
              buildThreadItems(messages, sessions).map((it) => {
                if (it.kind === 'start') {
                  const pm = productMeta(it.session?.product);
                  return (
                    <Box key={it.key} sx={{ display: 'flex', alignItems: 'center', gap: 1, my: 1.25 }}>
                      <Box sx={{ flex: 1, height: '1px', bgcolor: 'rgba(255,255,255,0.08)' }} />
                      <Typography fontSize="0.6rem" sx={{ color: 'text.disabled', whiteSpace: 'nowrap' }}>
                        Started · {fmtDivider(it.at)}
                      </Typography>
                      {pm && (
                        <Chip label={pm.label} size="small"
                          sx={{ height: 16, fontSize: '0.55rem', bgcolor: `${pm.color}22`, color: pm.color, '& .MuiChip-label': { px: 0.75 } }} />
                      )}
                      <Box sx={{ flex: 1, height: '1px', bgcolor: 'rgba(255,255,255,0.08)' }} />
                    </Box>
                  );
                }
                if (it.kind === 'end') {
                  return (
                    <Typography key={it.key} fontSize="0.6rem" sx={{ color: 'text.disabled', textAlign: 'center', my: 0.75, fontStyle: 'italic' }}>
                      {closeReasonLabel(it.session?.close_reason)} · {fmtDivider(it.session?.ended_at)}
                    </Typography>
                  );
                }
                const m = it.message;
                const mine = m.author === 'user';
                return (
                  <Box key={it.key} sx={{ display: 'flex', justifyContent: mine ? 'flex-end' : 'flex-start', mb: 1 }}>
                    <Box sx={{
                      maxWidth: '82%', px: 1.5, py: 1, borderRadius: 2,
                      bgcolor: mine ? PALETTE.blue : 'rgba(255,255,255,0.06)',
                      color: mine ? '#fff' : 'text.primary',
                      opacity: m._pending ? 0.6 : 1,
                      borderTopRightRadius: mine ? 4 : 16,
                      borderTopLeftRadius: mine ? 16 : 4,
                    }}>
                      {!mine && m.admin_name && (
                        <Typography fontSize="0.62rem" fontWeight={700} sx={{ color: PALETTE.blue, mb: 0.25 }}>
                          {m.admin_name}
                        </Typography>
                      )}
                      <Typography fontSize="0.82rem" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                        {m.body}
                      </Typography>
                    </Box>
                  </Box>
                );
              })
            )}
            {/* Closed-episode hint — sending starts a fresh conversation */}
            {convStatus === 'closed' && messages.length > 0 && (
              <Typography fontSize="0.65rem" sx={{ color: 'text.disabled', textAlign: 'center', mt: 1.5 }}>
                This chat was closed. Send a message to start a new conversation.
              </Typography>
            )}
          </Box>

          {/* Product picker — asked once when a new episode is about to start */}
          {needsProduct && (
            <Box sx={{ px: 1.25, pt: 1, pb: 0.5, flexShrink: 0, bgcolor: PALETTE.bg0, borderTop: '1px solid rgba(255,255,255,0.07)' }}>
              <Typography fontSize="0.62rem" sx={{ color: 'text.disabled', mb: 0.6 }}>What's this about?</Typography>
              <Box sx={{ display: 'flex', gap: 0.6, flexWrap: 'wrap' }}>
                {PRODUCTS.map((p) => {
                  const sel = p.value === product;
                  return (
                    <Chip
                      key={p.value} label={p.label} size="small"
                      onClick={() => chooseProduct(p.value)}
                      variant={sel ? 'filled' : 'outlined'}
                      sx={{
                        height: 24, fontSize: '0.68rem', cursor: 'pointer',
                        borderColor: `${p.color}66`,
                        color: sel ? '#fff' : p.color,
                        bgcolor: sel ? p.color : 'transparent',
                        '&:hover': { bgcolor: sel ? p.color : `${p.color}1f` },
                      }}
                    />
                  );
                })}
              </Box>
            </Box>
          )}

          {/* Composer */}
          <Box sx={{ p: 1, borderTop: needsProduct ? 'none' : '1px solid rgba(255,255,255,0.07)', display: 'flex', gap: 0.75, alignItems: 'flex-end', flexShrink: 0, bgcolor: PALETTE.bg0 }}>
            <TextField
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="Type your message…"
              size="small" fullWidth multiline maxRows={4}
              InputProps={{ sx: { fontSize: '0.85rem', borderRadius: 2 } }}
            />
            <IconButton
              color="primary" onClick={handleSend} disabled={!draft.trim() || sending}
              sx={{ bgcolor: `${PALETTE.blue}22`, '&:hover': { bgcolor: `${PALETTE.blue}33` } }}
            >
              {sending ? <CircularProgress size={18} /> : <Send fontSize="small" />}
            </IconButton>
          </Box>
        </Paper>
      </Zoom>

      {/* Launcher bubble — desktop only. On mobile it covered content, so the
          entry points are the sidebar Support dropdown and the notification bell
          (both dispatch 'open-support-chat'); the panel opens full-screen. */}
      {!isMobile && !open && (
        <Tooltip title="Live Support" placement="left" arrow>
          <Badge
            color="error" variant="dot" overlap="circular" invisible={!hasUnread}
            sx={{ position: 'fixed', bottom: bubbleBottom, right: isMobile ? 16 : 24, zIndex: (t) => t.zIndex.modal - 1 }}
          >
            <Fab color="primary" onClick={() => setOpen((v) => !v)} aria-label="Live support chat">
              {open ? <Close /> : <ChatBubbleOutline />}
            </Fab>
          </Badge>
        </Tooltip>
      )}
    </>
  );
}
