import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Box, Typography, Paper, List, ListItemButton, TextField, IconButton, Chip,
  ToggleButton, ToggleButtonGroup, CircularProgress, Avatar, Divider, Button,
  InputAdornment, Tooltip,
} from '@mui/material';
import {
  Search, Send, SupportAgent, Person, Refresh, CheckCircle, ReplayCircleFilled,
  MarkChatUnread,
} from '@mui/icons-material';
import { admin } from '../../services/api';
import { PALETTE } from '../../theme';
import { buildThreadItems, closeReasonLabel, fmtDivider } from '../../utils/supportThread';

const LIST_POLL_MS = 15000;
const THREAD_POLL_MS = 5000;

const maxMsgId = (msgs) => (msgs || []).reduce((m, x) => (x.id > m ? x.id : m), 0);

function fmtRelative(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(diff)) return '';
  const s = Math.floor(diff / 1000);
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export default function SupportInboxTab({ onAdminError }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState('open');
  const [search, setSearch] = useState('');
  const [conversations, setConversations] = useState([]);
  const [loadingList, setLoadingList] = useState(true);

  const [activeId, setActiveId] = useState(null);
  const [thread, setThread] = useState({ conversation: null, messages: [], sessions: [] });
  const [loadingThread, setLoadingThread] = useState(false);
  const [reply, setReply] = useState('');
  const [sending, setSending] = useState(false);

  const listRef = useRef(null);
  const activeIdRef = useRef(null);
  const threadMaxRef = useRef(0);   // highest message id we're displaying
  useEffect(() => { activeIdRef.current = activeId; }, [activeId]);

  const scrollToBottom = useCallback(() => {
    const el = listRef.current;
    if (el) requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
  }, []);

  const fetchList = useCallback(async () => {
    try {
      const { data } = await admin.supportConversations({ status, search: search.trim() });
      setConversations(data.conversations || []);
    } catch (err) {
      onAdminError?.(err);
    } finally {
      setLoadingList(false);
    }
  }, [status, search, onAdminError]);

  const openThread = useCallback(async (cid, { silent } = {}) => {
    if (!silent) { setLoadingThread(true); setActiveId(cid); threadMaxRef.current = 0; }
    try {
      const { data } = await admin.supportThread(cid);
      const serverMax = maxMsgId(data.messages);
      // Drop a stale silent poll whose response is behind what we already show
      // (e.g. a poll in flight from before an optimistic reply landed) so it can't
      // wipe the just-sent message.
      if (silent && serverMax < threadMaxRef.current) return;
      const grew = serverMax > threadMaxRef.current;
      threadMaxRef.current = serverMax;
      setThread(data);
      // Only jump to the bottom on open or when a new message actually arrived —
      // never on a routine silent poll, so scrolling up to read history sticks.
      if (!silent || grew) scrollToBottom();
      // Mark it read locally in the list so the badge clears immediately.
      setConversations((prev) => prev.map((c) => (c.id === cid ? { ...c, unread_admin: false } : c)));
    } catch (err) {
      onAdminError?.(err);
    } finally {
      setLoadingThread(false);
    }
  }, [onAdminError, scrollToBottom]);

  // Initial + polling for the list.
  useEffect(() => {
    setLoadingList(true);
    fetchList();
    const id = setInterval(fetchList, LIST_POLL_MS);
    return () => clearInterval(id);
  }, [fetchList]);

  // Deep-link: /admin/compliance/support?c=<id> opens that conversation.
  useEffect(() => {
    const c = searchParams.get('c');
    if (c && String(activeId) !== c) openThread(parseInt(c, 10));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Poll the open thread for new user messages.
  useEffect(() => {
    if (!activeId) return undefined;
    const id = setInterval(() => {
      if (activeIdRef.current) openThread(activeIdRef.current, { silent: true });
    }, THREAD_POLL_MS);
    return () => clearInterval(id);
  }, [activeId, openThread]);

  const selectConversation = (cid) => {
    setActiveId(cid);
    setSearchParams((p) => { p.set('c', String(cid)); return p; }, { replace: true });
    openThread(cid);
  };

  const sendReply = async () => {
    const body = reply.trim();
    if (!body || !activeId || sending) return;
    setSending(true);
    setReply('');
    try {
      const { data } = await admin.supportReply(activeId, body);
      if (data.message?.id) threadMaxRef.current = Math.max(threadMaxRef.current, data.message.id);
      setThread((prev) => {
        const sessions = data.session
          ? [...prev.sessions.filter((s) => s.id !== data.session.id), data.session]
          : prev.sessions;
        return { conversation: data.conversation, messages: [...prev.messages, data.message], sessions };
      });
      scrollToBottom();
      fetchList();
    } catch (err) {
      setReply(body);
      onAdminError?.(err);
    } finally {
      setSending(false);
    }
  };

  const setConvStatus = async (newStatus) => {
    if (!activeId) return;
    try {
      const { data } = await admin.supportSetStatus(activeId, newStatus);
      setThread((prev) => ({ ...prev, conversation: data.conversation, sessions: data.sessions || prev.sessions }));
      fetchList();
    } catch (err) {
      onAdminError?.(err);
    }
  };

  const conv = thread.conversation;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2, flexWrap: 'wrap' }}>
        <SupportAgent sx={{ color: PALETTE.blue }} />
        <Typography variant="h6" fontWeight={700}>Live Chat</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
          Messages from the website chat widget. Reply and users are notified instantly.
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Refresh"><IconButton size="small" onClick={fetchList}><Refresh fontSize="small" /></IconButton></Tooltip>
      </Box>

      <Box sx={{ display: 'flex', gap: 2, height: 'calc(100vh - 220px)', minHeight: 420, flexDirection: { xs: 'column', md: 'row' } }}>
        {/* ── Conversation list ── */}
        <Paper sx={{ width: { xs: '100%', md: 340 }, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <Box sx={{ p: 1.25, display: 'flex', flexDirection: 'column', gap: 1 }}>
            <ToggleButtonGroup
              size="small" exclusive value={status}
              onChange={(_, v) => v && setStatus(v)} fullWidth
            >
              <ToggleButton value="open">Open</ToggleButton>
              <ToggleButton value="closed">Closed</ToggleButton>
              <ToggleButton value="all">All</ToggleButton>
            </ToggleButtonGroup>
            <TextField
              size="small" placeholder="Search name or email…" value={search}
              onChange={(e) => setSearch(e.target.value)}
              InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
            />
          </Box>
          <Divider />
          <List sx={{ flex: 1, overflowY: 'auto', p: 0 }}>
            {loadingList ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress size={22} /></Box>
            ) : conversations.length === 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 4, px: 2 }}>
                No conversations yet.
              </Typography>
            ) : conversations.map((c) => (
              <ListItemButton
                key={c.id} selected={c.id === activeId}
                onClick={() => selectConversation(c.id)}
                sx={{ alignItems: 'flex-start', gap: 1, py: 1.25, borderBottom: `1px solid ${PALETTE.border1}` }}
              >
                <Avatar sx={{ width: 32, height: 32, bgcolor: c.unread_admin ? PALETTE.blue : 'rgba(255,255,255,0.1)' }}>
                  <Person fontSize="small" />
                </Avatar>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Typography fontSize="0.83rem" fontWeight={c.unread_admin ? 800 : 600} noWrap sx={{ flex: 1 }}>
                      {c.user?.name || 'User'}
                    </Typography>
                    {c.unread_admin && <MarkChatUnread sx={{ fontSize: 15, color: PALETTE.blue }} />}
                    <Typography fontSize="0.65rem" color="text.disabled">{fmtRelative(c.last_message_at)}</Typography>
                  </Box>
                  <Typography fontSize="0.72rem" color="text.secondary" noWrap>
                    {c.last_message_preview || '—'}
                  </Typography>
                </Box>
              </ListItemButton>
            ))}
          </List>
        </Paper>

        {/* ── Thread ── */}
        <Paper sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
          {!conv ? (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'text.secondary' }}>
              <SupportAgent sx={{ fontSize: 48, opacity: 0.3, mb: 1 }} />
              <Typography variant="body2">Select a conversation to view and reply.</Typography>
            </Box>
          ) : (
            <>
              <Box sx={{ px: 2, py: 1.25, display: 'flex', alignItems: 'center', gap: 1, borderBottom: `1px solid ${PALETTE.border1}` }}>
                <Avatar sx={{ width: 34, height: 34, bgcolor: 'rgba(255,255,255,0.1)' }}><Person fontSize="small" /></Avatar>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography fontSize="0.9rem" fontWeight={700} noWrap>{conv.user?.name || 'User'}</Typography>
                  <Typography fontSize="0.7rem" color="text.secondary" noWrap>
                    {conv.user?.email || '—'}{conv.user?.tier ? ` · ${conv.user.tier}` : ''}
                  </Typography>
                </Box>
                <Chip size="small" label={conv.status} color={conv.status === 'open' ? 'success' : 'default'} sx={{ height: 20, fontSize: '0.65rem' }} />
                {conv.status === 'open' ? (
                  <Button size="small" startIcon={<CheckCircle />} onClick={() => setConvStatus('closed')}>Close</Button>
                ) : (
                  <Button size="small" startIcon={<ReplayCircleFilled />} onClick={() => setConvStatus('open')}>Reopen</Button>
                )}
              </Box>

              <Box ref={listRef} sx={{ flex: 1, overflowY: 'auto', p: 2, bgcolor: PALETTE.bg0 }}>
                {loadingThread && thread.messages.length === 0 ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress size={22} /></Box>
                ) : buildThreadItems(thread.messages, thread.sessions).map((it) => {
                  if (it.kind === 'start') {
                    return (
                      <Box key={it.key} sx={{ display: 'flex', alignItems: 'center', gap: 1, my: 1.5 }}>
                        <Box sx={{ flex: 1, height: '1px', bgcolor: PALETTE.border1 }} />
                        <Typography fontSize="0.65rem" sx={{ color: 'text.disabled', whiteSpace: 'nowrap' }}>
                          Conversation started · {fmtDivider(it.at)}
                        </Typography>
                        <Box sx={{ flex: 1, height: '1px', bgcolor: PALETTE.border1 }} />
                      </Box>
                    );
                  }
                  if (it.kind === 'end') {
                    return (
                      <Typography key={it.key} fontSize="0.65rem" sx={{ color: 'text.disabled', textAlign: 'center', my: 1, fontStyle: 'italic' }}>
                        {closeReasonLabel(it.session?.close_reason)} · {fmtDivider(it.session?.ended_at)}
                      </Typography>
                    );
                  }
                  const m = it.message;
                  const isAdmin = m.author === 'admin';
                  return (
                    <Box key={it.key} sx={{ display: 'flex', justifyContent: isAdmin ? 'flex-end' : 'flex-start', mb: 1 }}>
                      <Box sx={{
                        maxWidth: '72%', px: 1.5, py: 1, borderRadius: 2,
                        bgcolor: isAdmin ? PALETTE.blue : 'rgba(255,255,255,0.06)',
                        color: isAdmin ? '#fff' : 'text.primary',
                      }}>
                        {isAdmin && m.admin_name && (
                          <Typography fontSize="0.62rem" fontWeight={700} sx={{ opacity: 0.85, mb: 0.25 }}>{m.admin_name}</Typography>
                        )}
                        <Typography fontSize="0.83rem" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{m.body}</Typography>
                        <Typography fontSize="0.6rem" sx={{ opacity: 0.6, mt: 0.4, textAlign: 'right' }}>{fmtRelative(m.created_at)}</Typography>
                      </Box>
                    </Box>
                  );
                })}
              </Box>

              <Box sx={{ p: 1.25, borderTop: `1px solid ${PALETTE.border1}`, display: 'flex', gap: 1, alignItems: 'flex-end' }}>
                <TextField
                  value={reply} onChange={(e) => setReply(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendReply(); } }}
                  placeholder="Type your reply…" size="small" fullWidth multiline maxRows={5}
                />
                <IconButton color="primary" onClick={sendReply} disabled={!reply.trim() || sending}
                  sx={{ bgcolor: `${PALETTE.blue}22`, '&:hover': { bgcolor: `${PALETTE.blue}33` } }}>
                  {sending ? <CircularProgress size={18} /> : <Send fontSize="small" />}
                </IconButton>
              </Box>
            </>
          )}
        </Paper>
      </Box>
    </Box>
  );
}
