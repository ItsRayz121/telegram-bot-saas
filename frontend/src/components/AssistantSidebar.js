/**
 * AssistantSidebar — persistent right-side co-pilot panel.
 *
 * Rendered at the AppLayout level so it persists across all pages.
 * On desktop: collapsible 340px right panel.
 * On mobile: triggered by a FloatingActionButton, opens as a full-screen drawer.
 */

import React, {
  useState, useEffect, useRef, useCallback, useContext,
} from 'react';
import {
  Box, Typography, TextField, IconButton, Chip, Paper, Drawer,
  Fab, CircularProgress, Alert, Divider, Tooltip, useMediaQuery,
  useTheme, Badge, Collapse,
} from '@mui/material';
import {
  Send, SmartToy, ChevronRight, ChevronLeft, Close,
  Refresh, LightbulbOutlined,
} from '@mui/icons-material';
import { assistant } from '../services/api';

export const ASSISTANT_SIDEBAR_WIDTH = 340;

const WELCOME_MSG = {
  id: 'welcome',
  direction: 'out',
  content: "Hi! I'm your Telegizer Assistant — your AI operations co-pilot.\n\nAsk me anything: schedule meetings, check your groups, set reminders, or get a briefing on what's happening today.",
  suggestions: [
    { label: "What's on my schedule?", value: "What's on my schedule today?" },
    { label: "Any group issues?", value: "Any issues in my groups?" },
    { label: "Book a meeting", value: "Book a meeting" },
    { label: "Remind me about something", value: "Remind me" },
  ],
};

// ── Message bubble ─────────────────────────────────────────────────────────────

function MessageBubble({ msg, onSuggestion, isLast }) {
  const isUser = msg.direction === 'in';
  return (
    <Box sx={{ mb: 1 }}>
      <Box sx={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
        <Box
          sx={{
            maxWidth: '88%',
            bgcolor: isUser ? 'primary.main' : 'action.selected',
            color: isUser ? 'primary.contrastText' : 'text.primary',
            borderRadius: isUser ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
            px: 1.5,
            py: 0.9,
          }}
        >
          <Typography fontSize="0.82rem" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5 }}>
            {msg.content}
          </Typography>
          {msg.created_at && (
            <Typography fontSize="0.6rem" sx={{ opacity: 0.55, mt: 0.25, textAlign: isUser ? 'right' : 'left' }}>
              {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </Typography>
          )}
        </Box>
      </Box>

      {/* Suggestion chips — only on last bot message */}
      {!isUser && isLast && msg.suggestions?.length > 0 && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.75, pl: 0.25 }}>
          {msg.suggestions.map((s, i) => (
            <Chip
              key={i}
              label={s.label}
              size="small"
              variant="outlined"
              color="primary"
              onClick={() => onSuggestion(s)}
              sx={{ fontSize: '0.7rem', cursor: 'pointer', height: 24 }}
            />
          ))}
        </Box>
      )}
    </Box>
  );
}

// ── Thinking indicator ────────────────────────────────────────────────────────

function ThinkingBubble() {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'flex-start', mb: 1 }}>
      <Box sx={{ bgcolor: 'action.selected', borderRadius: '14px 14px 14px 4px', px: 1.5, py: 0.9 }}>
        <Typography fontSize="0.82rem" color="text.secondary" sx={{ fontStyle: 'italic' }}>
          Thinking…
        </Typography>
      </Box>
    </Box>
  );
}

// ── Main sidebar content ──────────────────────────────────────────────────────

function AssistantContent({ onClose }) {
  const [messages, setMessages] = useState([{ ...WELCOME_MSG, created_at: new Date().toISOString() }]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingBriefing, setLoadingBriefing] = useState(false);
  const [error, setError] = useState('');
  const [briefingLoaded, setBriefingLoaded] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll on new messages
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  // Listen for prefill events from other pages (empty state buttons)
  useEffect(() => {
    const handler = (e) => {
      setDraft(e.detail || '');
      setTimeout(() => inputRef.current?.focus(), 100);
    };
    window.addEventListener('assistant:prefill', handler);
    return () => window.removeEventListener('assistant:prefill', handler);
  }, []);

  // Load daily briefing on first mount
  useEffect(() => {
    if (briefingLoaded) return;
    setBriefingLoaded(true);
    loadBriefing();
  }, []); // eslint-disable-line

  const loadBriefing = useCallback(async () => {
    setLoadingBriefing(true);
    try {
      const { data } = await assistant.briefing();
      if (data?.briefing) {
        const briefingMsg = {
          id: `briefing-${Date.now()}`,
          direction: 'out',
          content: data.briefing,
          created_at: new Date().toISOString(),
          suggestions: data.suggestions || [],
        };
        setMessages(prev => [...prev, briefingMsg]);
      }
    } catch {
      // Briefing failed silently — not critical
    } finally {
      setLoadingBriefing(false);
    }
  }, []);

  const send = useCallback(async (text) => {
    const msg = (text || draft).trim();
    if (!msg || sending) return;

    const userMsg = {
      id: Date.now(),
      direction: 'in',
      content: msg,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setDraft('');
    setSending(true);
    setError('');

    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      const { data } = await assistant.chat(msg, tz);
      const botMsg = {
        id: data.message_id || Date.now() + 1,
        direction: 'out',
        content: data.reply,
        created_at: new Date().toISOString(),
        intent: data.intent,
        suggestions: data.suggestions || [],
      };
      setMessages(prev => [...prev, botMsg]);

      // Notify parent if a meeting was created (for dashboard refresh)
      if (data.intent === 'schedule_meeting' && data.data?.id) {
        window.dispatchEvent(new CustomEvent('assistant:meeting_created', { detail: data.data }));
      }
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to get a response. Please try again.');
    } finally {
      setSending(false);
    }
  }, [draft, sending]);

  const handleSuggestion = useCallback((s) => {
    if (s.value === null) {
      inputRef.current?.focus();
    } else {
      send(s.value);
    }
  }, [send]);

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* Header */}
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 1,
        px: 2, py: 1.25,
        borderBottom: '1px solid', borderColor: 'divider',
        bgcolor: 'background.paper',
        flexShrink: 0,
      }}>
        <SmartToy fontSize="small" color="primary" />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography fontWeight={700} fontSize="0.88rem" noWrap>Telegizer Assistant</Typography>
          <Typography fontSize="0.68rem" color="text.secondary" noWrap>AI Operations Co-Pilot</Typography>
        </Box>
        <Tooltip title="Refresh briefing">
          <IconButton size="small" onClick={loadBriefing} disabled={loadingBriefing}>
            {loadingBriefing ? <CircularProgress size={14} /> : <Refresh fontSize="small" />}
          </IconButton>
        </Tooltip>
        {onClose && (
          <Tooltip title="Collapse assistant">
            <IconButton size="small" onClick={onClose}>
              <ChevronRight fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* Conversation area */}
      <Box sx={{ flex: 1, overflowY: 'auto', px: 1.5, py: 1.5, bgcolor: 'background.default' }}>
        {messages.map((m, idx) => (
          <MessageBubble
            key={m.id}
            msg={m}
            isLast={idx === messages.length - 1}
            onSuggestion={handleSuggestion}
          />
        ))}
        {sending && <ThinkingBubble />}
        {error && (
          <Alert severity="error" sx={{ mt: 0.5, py: 0.25, fontSize: '0.78rem' }} onClose={() => setError('')}>
            {error}
          </Alert>
        )}
        <div ref={endRef} />
      </Box>

      {/* Quick actions */}
      <Box sx={{
        px: 1.5, py: 0.75,
        borderTop: '1px solid', borderColor: 'divider',
        bgcolor: 'background.paper',
        flexShrink: 0,
        display: 'flex', gap: 0.75, flexWrap: 'wrap',
      }}>
        {[
          { label: '🧠 Analyze Day', value: 'Analyze my day' },
          { label: '+ Task', value: 'Create task' },
          { label: '⏰ Reminder', value: 'Remind me' },
          { label: '📅 Schedule', value: "What's on my schedule?" },
        ].map(q => (
          <Chip
            key={q.value}
            label={q.label}
            size="small"
            variant="outlined"
            onClick={() => send(q.value)}
            disabled={sending}
            sx={{ fontSize: '0.68rem', cursor: 'pointer' }}
          />
        ))}
      </Box>

      {/* Input area */}
      <Box sx={{
        px: 1.5, py: 1,
        borderTop: '1px solid', borderColor: 'divider',
        bgcolor: 'background.paper',
        flexShrink: 0,
      }}>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
          <TextField
            inputRef={inputRef}
            size="small"
            fullWidth
            multiline
            maxRows={4}
            placeholder="Ask anything…"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={handleKey}
            disabled={sending}
            sx={{ '& .MuiInputBase-root': { fontSize: '0.83rem' } }}
          />
          <IconButton
            color="primary"
            size="small"
            onClick={() => send()}
            disabled={sending || !draft.trim()}
            sx={{ mb: 0.25, flexShrink: 0 }}
          >
            {sending ? <CircularProgress size={16} /> : <Send fontSize="small" />}
          </IconButton>
        </Box>
        <Typography fontSize="0.62rem" color="text.disabled" sx={{ mt: 0.5, textAlign: 'center' }}>
          Press Enter to send · Shift+Enter for new line
        </Typography>
      </Box>
    </Box>
  );
}

// ── Desktop: collapsible right sidebar ────────────────────────────────────────

export function DesktopAssistantSidebar() {
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem('assistant_sidebar_open') !== 'false'; }
    catch { return true; }
  });

  const toggle = () => {
    const next = !open;
    setOpen(next);
    try { localStorage.setItem('assistant_sidebar_open', String(next)); } catch { }
  };

  return (
    <>
      {/* Collapsed: show slim toggle strip */}
      {!open && (
        <Box
          sx={{
            width: 40, flexShrink: 0, display: 'flex', flexDirection: 'column',
            alignItems: 'center', pt: 2, gap: 1,
            borderLeft: '1px solid', borderColor: 'divider',
            bgcolor: 'background.paper', cursor: 'pointer',
          }}
          onClick={toggle}
        >
          <Tooltip title="Open Assistant" placement="left">
            <SmartToy fontSize="small" color="primary" />
          </Tooltip>
          <Tooltip title="Open Assistant" placement="left">
            <ChevronLeft fontSize="small" sx={{ color: 'text.secondary' }} />
          </Tooltip>
        </Box>
      )}

      {/* Open: full sidebar */}
      {open && (
        <Box
          sx={{
            width: ASSISTANT_SIDEBAR_WIDTH,
            flexShrink: 0,
            height: '100vh',
            position: 'sticky',
            top: 0,
            borderLeft: '1px solid',
            borderColor: 'divider',
            display: 'flex',
            flexDirection: 'column',
            bgcolor: 'background.paper',
            overflow: 'hidden',
          }}
        >
          <AssistantContent onClose={toggle} />
        </Box>
      )}
    </>
  );
}

// ── Mobile: FAB + full-screen drawer ─────────────────────────────────────────

export function MobileAssistantFab() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Floating action button */}
      <Fab
        color="primary"
        size="medium"
        onClick={() => setOpen(true)}
        sx={{
          position: 'fixed',
          bottom: 72,   // above the bottom nav bar (56px) + 16px gap
          right: 16,
          zIndex: 1300,
          boxShadow: 4,
        }}
      >
        <SmartToy />
      </Fab>

      {/* Full-screen assistant drawer */}
      <Drawer
        anchor="bottom"
        open={open}
        onClose={() => setOpen(false)}
        PaperProps={{
          sx: {
            height: '92vh',
            borderTopLeftRadius: 16,
            borderTopRightRadius: 16,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          },
        }}
      >
        {/* Drag handle */}
        <Box sx={{ display: 'flex', justifyContent: 'center', pt: 1, pb: 0.5, flexShrink: 0 }}>
          <Box sx={{ width: 36, height: 4, borderRadius: 2, bgcolor: 'action.disabled' }} />
        </Box>
        <Box sx={{ flex: 1, minHeight: 0 }}>
          <AssistantContent onClose={() => setOpen(false)} />
        </Box>
      </Drawer>
    </>
  );
}
