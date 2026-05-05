import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, CircularProgress,
  Alert, Grid, LinearProgress,
  IconButton, Tooltip, Collapse, TextField, Paper, Tabs, Tab,
} from '@mui/material';
import {
  Psychology, AccessTime, EditNote, Summarize, AutoMode, Reply,
  OpenInNew, ContentCopy, CheckCircle, RadioButtonUnchecked, Close,
  ArrowForward, Chat, Send, ExpandMore, ExpandLess, QuestionAnswer,
  CalendarMonth, SmartToy, Lock, Groups, Person,
  NotificationsActive, MenuBook, BarChart, TrendingUp,
} from '@mui/icons-material';
import GroupTrendsDashboard from '../components/GroupTrendsDashboard';
import { useMediaQuery, useTheme } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { assistant, assistantBot as assistantBotApi, meetings as meetingsApi } from '../services/api';

const DISMISS_KEY = 'hub_connect_banner_dismissed';

function relTime(isoStr) {
  if (!isoStr) return null;
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 2) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  if (Math.floor(hrs / 24) === 1) return 'Yesterday';
  return `${Math.floor(hrs / 24)}d ago`;
}

function upcomingTime(isoStr) {
  if (!isoStr) return '';
  return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ── Connect Bot Banner ────────────────────────────────────────────────────────

function ConnectBotBanner({ botUsername, connectedGroups, onDismiss }) {
  const [copied, setCopied] = useState(false);
  const link = `https://t.me/${botUsername}?startgroup=true`;

  const copyLink = () => {
    navigator.clipboard.writeText(link).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Card
      variant="outlined"
      sx={{ mb: 3, borderColor: 'primary.main', bgcolor: 'rgba(37,99,235,0.05)' }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Box>
            <Typography fontWeight={700} mb={0.5}>
              Add @{botUsername} to your Telegram groups
            </Typography>
            <Typography fontSize="0.84rem" color="text.secondary" mb={1.5}>
              The bot enables AI digests, note capture, smart reminders, and auto-replies
              for every group you connect.
              {connectedGroups > 0 && (
                <Typography component="span" color="success.main" fontWeight={600}>
                  {' '}{connectedGroups} group{connectedGroups > 1 ? 's' : ''} connected.
                </Typography>
              )}
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <Button
                variant="contained"
                size="small"
                startIcon={<OpenInNew />}
                href={link}
                target="_blank"
                rel="noopener noreferrer"
              >
                Add to Group
              </Button>
              <Tooltip title={copied ? 'Copied!' : 'Copy bot link'}>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<ContentCopy />}
                  onClick={copyLink}
                >
                  {copied ? 'Copied!' : 'Copy Link'}
                </Button>
              </Tooltip>
            </Box>
          </Box>
          <IconButton size="small" onClick={onDismiss} sx={{ ml: 1 }}>
            <Close fontSize="small" />
          </IconButton>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Mobile Feature Navigation Grid ───────────────────────────────────────────

const FEATURE_TILES = [
  { label: 'Notes', icon: EditNote, path: '/workspace/notes', color: '#3b82f6' },
  { label: 'Tasks', icon: CheckCircle, path: '/workspace/tasks', color: '#10b981' },
  { label: 'Reminders', icon: NotificationsActive, path: '/workspace/reminders', color: '#f59e0b' },
  { label: 'Digests', icon: Summarize, path: '/workspace/digests', color: '#8b5cf6' },
  { label: 'Auto-Reply', icon: Reply, path: '/workspace/smart-links', color: '#ec4899' },
  { label: 'Knowledge', icon: MenuBook, path: '/workspace/knowledge-base', color: '#06b6d4' },
  { label: 'Automations', icon: AutoMode, path: '/workspace/automations', color: '#f97316' },
  { label: 'Analytics', icon: BarChart, path: '/analytics', color: '#64748b' },
];

function MobileFeatureGrid() {
  const navigate = useNavigate();
  return (
    <Box sx={{ mb: 3 }}>
      <Typography fontWeight={600} fontSize="0.82rem" color="text.secondary" mb={1.5} sx={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Features
      </Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 1 }}>
        {FEATURE_TILES.map(({ label, icon: Icon, path, color }) => (
          <Box
            key={path}
            onClick={() => navigate(path)}
            sx={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              gap: 0.75, p: 1.25, borderRadius: 2,
              bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider',
              cursor: 'pointer',
              transition: 'transform 0.15s, box-shadow 0.15s',
              '&:active': { transform: 'scale(0.95)' },
            }}
          >
            <Box sx={{ width: 36, height: 36, borderRadius: '50%', bgcolor: color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Icon sx={{ fontSize: 18, color }} />
            </Box>
            <Typography fontSize="0.68rem" fontWeight={500} textAlign="center" lineHeight={1.2}>
              {label}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ── Onboarding Checklist ──────────────────────────────────────────────────────

function OnboardingCard({ onboarding }) {
  const navigate = useNavigate();
  const steps = [
    { label: 'Add bot to a group', done: onboarding.has_active_group, action: () => navigate('/groups') },
    { label: 'Configure first Auto-Reply', done: onboarding.has_auto_reply, action: () => navigate('/workspace/smart-links') },
    { label: 'Set up Daily Digest', done: onboarding.has_digest, action: () => navigate('/workspace/digests') },
    { label: 'Create your first Note', done: onboarding.has_note, action: () => navigate('/workspace/notes') },
  ];
  const doneCount = steps.filter(s => s.done).length;
  const pct = (doneCount / steps.length) * 100;

  if (doneCount === steps.length) return null;

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography fontWeight={600} mb={0.5}>Getting started</Typography>
        <LinearProgress variant="determinate" value={pct} sx={{ borderRadius: 1, height: 5, mb: 1.5 }} />
        <Typography fontSize="0.75rem" color="text.secondary" mb={1.5}>
          {doneCount} / {steps.length} complete
        </Typography>
        {steps.map(({ label, done, action }) => (
          <Box
            key={label}
            sx={{
              display: 'flex', alignItems: 'center', gap: 1, py: 0.5,
              cursor: done ? 'default' : 'pointer',
              '&:hover': done ? {} : { '& .step-label': { color: 'primary.main' } },
            }}
            onClick={done ? undefined : action}
          >
            {done
              ? <CheckCircle sx={{ fontSize: 18, color: 'success.main' }} />
              : <RadioButtonUnchecked sx={{ fontSize: 18, color: 'text.disabled' }} />
            }
            <Typography
              className="step-label"
              fontSize="0.86rem"
              color={done ? 'text.disabled' : 'text.primary'}
              sx={{ textDecoration: done ? 'line-through' : 'none' }}
            >
              {label}
            </Typography>
          </Box>
        ))}
      </CardContent>
    </Card>
  );
}

// ── Data Cards ────────────────────────────────────────────────────────────────

function _gcalUrl({ title, startIso, durationMins = 30, description = '' }) {
  const dt = new Date(startIso);
  const pad = n => String(n).padStart(2, '0');
  const fmt = d =>
    `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}00Z`;
  const end = new Date(dt.getTime() + durationMins * 60000);
  const params = new URLSearchParams({ action: 'TEMPLATE', text: title, dates: `${fmt(dt)}/${fmt(end)}`, details: description });
  return `https://calendar.google.com/calendar/render?${params}`;
}

function GCalButton({ title, startIso, durationMins, description, compact = false }) {
  const url = _gcalUrl({ title, startIso, durationMins, description });
  if (compact) {
    return (
      <Tooltip title="Add to Google Calendar">
        <IconButton size="small" component="a" href={url} target="_blank" rel="noopener noreferrer">
          <CalendarMonth sx={{ fontSize: 15, color: '#4285f4' }} />
        </IconButton>
      </Tooltip>
    );
  }
  return (
    <Button
      size="small"
      variant="outlined"
      component="a"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      startIcon={<CalendarMonth sx={{ fontSize: 14, color: '#4285f4' }} />}
      sx={{ fontSize: '0.72rem', borderColor: '#4285f4', color: '#4285f4', '&:hover': { bgcolor: 'rgba(66,133,244,0.06)', borderColor: '#4285f4' }, py: 0.25, px: 1 }}
    >
      Add to Calendar
    </Button>
  );
}

function RemindersCard({ reminders }) {
  const navigate = useNavigate();
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AccessTime fontSize="small" color="primary" />
            <Typography fontWeight={600} fontSize="0.95rem">Reminders Today</Typography>
          </Box>
          <Button size="small" endIcon={<ArrowForward sx={{ fontSize: 13 }} />}
            onClick={() => navigate('/workspace/reminders')} sx={{ fontSize: '0.75rem' }}>
            View All
          </Button>
        </Box>
        {reminders.length === 0 ? (
          <Typography fontSize="0.84rem" color="text.secondary">No reminders for today.</Typography>
        ) : (
          reminders.map(r => (
            <Box key={r.id} sx={{ mb: 1, pb: 1, borderBottom: '1px solid', borderColor: 'divider', '&:last-child': { mb: 0, pb: 0, border: 'none' } }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <Typography fontSize="0.84rem" noWrap sx={{ flex: 1 }}>{r.reminder_text}</Typography>
                <GCalButton title={r.reminder_text} startIso={r.remind_at} compact />
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography fontSize="0.72rem" color={r.is_delivered ? 'success.main' : 'text.disabled'}>
                  {upcomingTime(r.remind_at)}{r.is_delivered ? ' · Done' : ''}
                </Typography>
              </Box>
            </Box>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function NotesCard({ recentNotes }) {
  const navigate = useNavigate();
  const TAG_COLORS = { decision: 'primary', task: 'warning', link: 'info', question: 'secondary' };
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <EditNote fontSize="small" color="primary" />
            <Typography fontWeight={600} fontSize="0.95rem">Recent Notes</Typography>
          </Box>
          <Button size="small" endIcon={<ArrowForward sx={{ fontSize: 13 }} />}
            onClick={() => navigate('/workspace/notes')} sx={{ fontSize: '0.75rem' }}>
            View All
          </Button>
        </Box>
        {recentNotes.length === 0 ? (
          <Typography fontSize="0.84rem" color="text.secondary">No notes yet.</Typography>
        ) : (
          recentNotes.map(n => (
            <Box key={n.id} sx={{ mb: 1.25, pb: 1.25, borderBottom: '1px solid', borderColor: 'divider', '&:last-child': { mb: 0, pb: 0, border: 'none' } }}>
              <Box sx={{ display: 'flex', gap: 0.5, mb: 0.4, flexWrap: 'wrap' }}>
                {(n.tags || []).map(t => (
                  <Chip key={t} label={t} size="small" color={TAG_COLORS[t] || 'default'} sx={{ height: 16, fontSize: '0.65rem' }} />
                ))}
              </Box>
              <Typography fontSize="0.83rem" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                {n.content}
              </Typography>
              <Typography fontSize="0.72rem" color="text.disabled">{relTime(n.created_at)}</Typography>
            </Box>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function DigestCard({ digestStatus }) {
  const navigate = useNavigate();
  const statusIcon = { sent: '✓', pending: '⏳', disabled: '—' };
  const statusColor = { sent: 'success.main', pending: 'warning.main', disabled: 'text.disabled' };
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Summarize fontSize="small" color="primary" />
            <Typography fontWeight={600} fontSize="0.95rem">Digest Status</Typography>
          </Box>
          <Button size="small" endIcon={<ArrowForward sx={{ fontSize: 13 }} />}
            onClick={() => navigate('/workspace/digests')} sx={{ fontSize: '0.75rem' }}>
            Configure
          </Button>
        </Box>
        {digestStatus.length === 0 ? (
          <Typography fontSize="0.84rem" color="text.secondary">No groups connected yet.</Typography>
        ) : (
          digestStatus.map(d => (
            <Box key={d.group_id} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}>
              <Typography fontSize="0.83rem" noWrap sx={{ flex: 1, mr: 1 }}>{d.group_title}</Typography>
              <Typography fontSize="0.78rem" color={statusColor[d.status]} fontWeight={600}>
                {statusIcon[d.status]} {d.last_sent ? relTime(d.last_sent) : d.status}
              </Typography>
            </Box>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function ActivityCard({ activity }) {
  const navigate = useNavigate();
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AutoMode fontSize="small" color="primary" />
            <Typography fontWeight={600} fontSize="0.95rem">Automation Today</Typography>
          </Box>
          <Button size="small" endIcon={<ArrowForward sx={{ fontSize: 13 }} />}
            onClick={() => navigate('/workspace/automations')} sx={{ fontSize: '0.75rem' }}>
            Workflows
          </Button>
        </Box>
        <Box sx={{ display: 'flex', gap: 3 }}>
          <Box>
            <Typography fontSize="1.6rem" fontWeight={700} lineHeight={1}>{activity.auto_replies_today}</Typography>
            <Typography fontSize="0.75rem" color="text.secondary">Auto-replies</Typography>
          </Box>
          <Box>
            <Typography fontSize="1.6rem" fontWeight={700} lineHeight={1}>{activity.workflows_today}</Typography>
            <Typography fontSize="0.75rem" color="text.secondary">Workflows fired</Typography>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Ask Your Community (cross-group intelligence) ─────────────────────────────

function AskCard({ hasGroups }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const ask = async () => {
    if (!question.trim()) return;
    setLoading(true); setError(''); setAnswer(null);
    try {
      const { data } = await assistant.ask(question.trim());
      setAnswer(data);
    } catch (e) {
      setError(e.response?.data?.error || 'AI request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card variant="outlined" sx={{ mt: 2 }}>
      <CardContent sx={{ pb: open ? 1 : undefined }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
          onClick={() => setOpen(v => !v)}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <QuestionAnswer fontSize="small" color="primary" />
            <Typography fontWeight={600} fontSize="0.95rem">Ask Your Community</Typography>
            {!hasGroups && <Chip label="Connect groups first" size="small" color="warning" sx={{ fontSize: '0.65rem', height: 18 }} />}
          </Box>
          {open ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
        </Box>
        <Collapse in={open}>
          <Typography fontSize="0.82rem" color="text.secondary" mt={1.5} mb={1.5}>
            Ask a question — AI searches the last 72h of messages across all your groups and answers.
          </Typography>
          {!hasGroups ? (
            <Typography fontSize="0.84rem" color="text.secondary">Connect at least one group to use this feature.</Typography>
          ) : (
            <>
              <Box sx={{ display: 'flex', gap: 1, mb: 1.5 }}>
                <TextField
                  size="small" fullWidth
                  placeholder="What was decided about the product launch?"
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), ask())}
                  disabled={loading}
                />
                <Button variant="contained" size="small" onClick={ask} disabled={loading || !question.trim()} sx={{ minWidth: 72 }}>
                  {loading ? <CircularProgress size={18} /> : 'Ask'}
                </Button>
              </Box>
              {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
              {answer && (
                <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'action.hover' }}>
                  <Typography fontSize="0.85rem" sx={{ whiteSpace: 'pre-wrap' }}>{answer.answer}</Typography>
                  <Typography fontSize="0.7rem" color="text.disabled" mt={0.75}>
                    Searched {answer.groups_searched} group{answer.groups_searched !== 1 ? 's' : ''} · {answer.messages_scanned} messages
                  </Typography>
                </Paper>
              )}
            </>
          )}
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ── Personal Assistant Chat ───────────────────────────────────────────────────

const QUICK_SUGGESTIONS = [
  "Book a meeting",
  "What's on my schedule?",
  "Remind me about something",
  "Any issues in my groups?",
];

function PersonalAssistantChat({ onMeetingCreated, botConnected }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(true);
  const [messages, setMessages] = useState([
    { id: 'welcome', direction: 'out', content: "Hi! I'm your personal assistant. I can schedule meetings, set reminders, show upcoming events, and summarise group issues. What can I help you with?", created_at: new Date().toISOString() },
  ]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const endRef = useRef(null);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  const send = useCallback(async (text) => {
    const msg = (text || draft).trim();
    if (!msg) return;
    const userMsg = { id: Date.now(), direction: 'in', content: msg, created_at: new Date().toISOString() };
    setMessages(prev => [...prev, userMsg]);
    setDraft('');
    setSending(true);
    setError('');
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      const { data } = await assistant.chat(msg, tz);
      const botMsg = { id: data.message_id || Date.now() + 1, direction: 'out', content: data.reply, created_at: new Date().toISOString(), intent: data.intent, suggestions: data.suggestions || [] };
      setMessages(prev => [...prev, botMsg]);
      if (data.intent === 'schedule_meeting' && data.data && data.data.id && onMeetingCreated) {
        onMeetingCreated(data.data);
      }
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to get a response. Please try again.');
    } finally {
      setSending(false);
    }
  }, [draft, onMeetingCreated]);

  const handleKey = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };

  return (
    <Card variant="outlined" sx={{ mt: 3 }}>
      <CardContent sx={{ pb: open ? 1 : undefined }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', mb: open ? 1.5 : 0 }}
          onClick={() => setOpen(v => !v)}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Chat fontSize="small" color="primary" />
            <Typography fontWeight={600} fontSize="0.95rem">Live Chat with Bot</Typography>
            <Chip label="AI" size="small" color="primary" sx={{ height: 17, fontSize: '0.62rem' }} />
          </Box>
          {open ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
        </Box>

        <Collapse in={open}>
          {/* Quick suggestion chips */}
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 1.5 }}>
            {QUICK_SUGGESTIONS.map(s => (
              <Chip
                key={s}
                label={s}
                size="small"
                variant="outlined"
                onClick={() => !sending && send(s)}
                sx={{ fontSize: '0.72rem', cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}
              />
            ))}
          </Box>

          {/* Chat window */}
          <Paper variant="outlined" sx={{ height: 320, overflowY: 'auto', p: 1.5, bgcolor: 'background.default' }}>
            {messages.map((m, idx) => (
              <Box key={m.id}>
                <Box sx={{ display: 'flex', justifyContent: m.direction === 'out' ? 'flex-start' : 'flex-end', mb: m.suggestions?.length ? 0.5 : 1 }}>
                  <Box sx={{
                    maxWidth: '82%',
                    bgcolor: m.direction === 'in' ? 'primary.main' : 'action.selected',
                    color: m.direction === 'in' ? 'primary.contrastText' : 'text.primary',
                    borderRadius: m.direction === 'in' ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                    px: 1.5, py: 1,
                  }}>
                    <Typography fontSize="0.83rem" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {m.content}
                    </Typography>
                    <Typography fontSize="0.62rem" sx={{ opacity: 0.6, mt: 0.25 }}>
                      {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </Typography>
                  </Box>
                </Box>
                {/* Inline suggestion buttons for bot messages */}
                {m.direction === 'out' && m.suggestions?.length > 0 && idx === messages.length - 1 && (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1, pl: 0.5 }}>
                    {m.suggestions.map((s, si) => (
                      <Chip
                        key={si}
                        label={s.label}
                        size="small"
                        color="primary"
                        variant="outlined"
                        onClick={() => {
                          if (!sending) {
                            if (s.value === null) {
                              // Focus input for custom entry
                              document.querySelector('[placeholder*="Schedule"]')?.focus();
                            } else {
                              send(s.value);
                            }
                          }
                        }}
                        sx={{ fontSize: '0.72rem', cursor: 'pointer' }}
                      />
                    ))}
                  </Box>
                )}
              </Box>
            ))}
            {sending && (
              <Box sx={{ display: 'flex', justifyContent: 'flex-start', mb: 1 }}>
                <Box sx={{ bgcolor: 'action.selected', borderRadius: '12px 12px 12px 4px', px: 1.5, py: 1 }}>
                  <Typography fontSize="0.83rem" color="text.secondary">Thinking…</Typography>
                </Box>
              </Box>
            )}
            <div ref={endRef} />
          </Paper>

          {error && <Alert severity="error" sx={{ mt: 0.75, py: 0, fontSize: '0.8rem' }}>{error}</Alert>}

          {!botConnected && (
            <Alert
              severity="info"
              sx={{ mt: 1, py: 0.5, fontSize: '0.8rem' }}
              action={
                <Button size="small" onClick={() => navigate('/workspace/ai-settings')}>Connect</Button>
              }
            >
              Connect your Telegram account to receive reminders and DMs from the bot.
            </Alert>
          )}

          <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
            <TextField
              size="small" fullWidth multiline maxRows={3}
              placeholder="Schedule meeting, show reminders, group issues…"
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={handleKey}
              disabled={sending}
            />
            <IconButton color="primary" onClick={() => send()} disabled={sending || !draft.trim()}>
              {sending ? <CircularProgress size={18} /> : <Send fontSize="small" />}
            </IconButton>
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ── Meetings Panel ────────────────────────────────────────────────────────────

const PRIORITY_COLOR = { low: 'success', medium: 'warning', high: 'error' };

function MeetingsCard({ newMeeting }) {
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(true);

  const load = useCallback(async () => {
    try {
      const { data } = await meetingsApi.list();
      setMeetings(data.meetings || []);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // When assistant creates a new meeting, prepend it without re-fetching
  useEffect(() => {
    if (!newMeeting) return;
    setMeetings(prev => {
      if (prev.find(m => m.id === newMeeting.id)) return prev;
      return [newMeeting, ...prev];
    });
    setOpen(true);
  }, [newMeeting]);

  const markComplete = async (id) => {
    try {
      await meetingsApi.complete(id);
      setMeetings(prev => prev.filter(m => m.id !== id));
    } catch { /* noop */ }
  };

  const deleteMeeting = async (id) => {
    try {
      await meetingsApi.remove(id);
      setMeetings(prev => prev.filter(m => m.id !== id));
    } catch { /* noop */ }
  };

  return (
    <Card variant="outlined" sx={{ mt: 3 }}>
      <CardContent sx={{ pb: open ? 1 : undefined }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', mb: open ? 1 : 0 }}
          onClick={() => setOpen(v => !v)}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CalendarMonth fontSize="small" color="primary" />
            <Typography fontWeight={600} fontSize="0.95rem">Upcoming Meetings</Typography>
            {meetings.length > 0 && <Chip label={meetings.length} size="small" sx={{ height: 17, fontSize: '0.65rem' }} />}
          </Box>
          {open ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
        </Box>

        <Collapse in={open}>
          {loading ? (
            <CircularProgress size={20} sx={{ mt: 1 }} />
          ) : meetings.length === 0 ? (
            <Typography fontSize="0.84rem" color="text.secondary" mt={0.5}>
              No upcoming meetings. Ask the assistant to schedule one!
            </Typography>
          ) : (
            meetings.map(m => (
              <Box key={m.id} sx={{ mb: 1.5, pb: 1.5, borderBottom: '1px solid', borderColor: 'divider', '&:last-child': { mb: 0, pb: 0, border: 'none' } }}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                  <Box sx={{ flex: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap', mb: 0.25 }}>
                      <Typography fontSize="0.88rem" fontWeight={600}>{m.title}</Typography>
                      <Chip label={m.priority} size="small" color={PRIORITY_COLOR[m.priority] || 'default'} sx={{ height: 16, fontSize: '0.6rem' }} />
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mt: 0.25 }}>
                      <Typography fontSize="0.78rem" color="text.secondary">
                        {new Date(m.scheduled_at).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        {m.timezone && m.timezone !== 'UTC' ? ` (${m.timezone})` : ' UTC'}
                      </Typography>
                      <GCalButton
                        title={m.title}
                        startIso={m.scheduled_at}
                        durationMins={60}
                        description={m.participants ? `With: ${m.participants.join(', ')}` : ''}
                        compact={false}
                      />
                    </Box>
                    {m.participants && m.participants.length > 0 && (
                      <Typography fontSize="0.75rem" color="text.secondary">
                        With: {m.participants.join(', ')}
                      </Typography>
                    )}
                    {m.resources && m.resources.length > 0 && (
                      <Box sx={{ mt: 0.5, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {m.resources.map((r, i) => (
                          <Chip
                            key={i}
                            label={r.type === 'link' ? (r.label || 'Link') : (r.value.slice(0, 30))}
                            size="small"
                            variant="outlined"
                            component={r.type === 'link' ? 'a' : 'div'}
                            href={r.type === 'link' ? r.value : undefined}
                            target="_blank"
                            rel="noopener noreferrer"
                            clickable={r.type === 'link'}
                            sx={{ height: 18, fontSize: '0.65rem' }}
                          />
                        ))}
                      </Box>
                    )}
                  </Box>
                  <Box sx={{ display: 'flex', gap: 0.25, flexShrink: 0 }}>
                    <Tooltip title="Mark complete">
                      <IconButton size="small" onClick={() => markComplete(m.id)} sx={{ color: 'success.main' }}>
                        <CheckCircle sx={{ fontSize: 16 }} />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton size="small" onClick={() => deleteMeeting(m.id)} sx={{ color: 'text.disabled' }}>
                        <Close sx={{ fontSize: 16 }} />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Box>
              </Box>
            ))
          )}
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ── Assistant Bot Status Card ─────────────────────────────────────────────────

function AssistantBotCard({ plan }) {
  const navigate = useNavigate();
  const isPro = plan === 'pro' || plan === 'enterprise';
  const [bot, setBot] = useState(undefined); // undefined = loading, null = none

  useEffect(() => {
    if (!isPro) { setBot(null); return; }
    assistantBotApi.get().then(r => setBot(r.data.bot)).catch(() => setBot(null));
  }, [isPro]);

  const subtitle = bot
    ? `@${bot.bot_username || bot.bot_name} · ${bot.is_active ? 'Active' : 'Inactive'}`
    : isPro
    ? 'No bot connected yet'
    : 'Official Telegizer Assistant';

  return (
    <Card variant="outlined" sx={{ mb: 3, borderColor: isPro ? 'divider' : 'rgba(37,99,235,0.3)', bgcolor: isPro ? 'transparent' : 'rgba(37,99,235,0.03)' }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <SmartToy fontSize="small" color={bot ? 'primary' : 'disabled'} />
            <Box>
              <Typography fontWeight={600} fontSize="0.9rem">Your Assistant Bot</Typography>
              <Typography fontSize="0.78rem" color="text.secondary">{subtitle}</Typography>
            </Box>
          </Box>
          {isPro ? (
            <Button size="small" variant="outlined" onClick={() => navigate('/workspace/assistant-bot')}>
              {bot ? 'Manage' : 'Connect Bot'}
            </Button>
          ) : (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Lock sx={{ fontSize: 14, color: 'text.disabled' }} />
              <Button size="small" variant="contained" onClick={() => navigate('/billing')}>
                Upgrade to Connect Your Own Bot
              </Button>
            </Box>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Active Spaces ─────────────────────────────────────────────────────────────

function ActiveSpacesCard({ plan }) {
  const navigate = useNavigate();
  const isPro = plan === 'pro' || plan === 'enterprise';
  const [spaces, setSpaces] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!isPro) return;
    assistantBotApi.listSpaces().then(r => setSpaces(r.data.spaces || [])).catch(() => {});
  }, [isPro]);

  if (!isPro || spaces.length === 0) return null;

  const typeIcon = (type) => type === 'private' ? <Person sx={{ fontSize: 14 }} /> : <Groups sx={{ fontSize: 14 }} />;

  function relTime(iso) {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 2) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  }

  return (
    <Card variant="outlined" sx={{ mt: 2 }}>
      <CardContent sx={{ pb: open ? 1 : undefined }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
          onClick={() => setOpen(v => !v)}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SmartToy fontSize="small" color="primary" />
            <Typography fontWeight={600} fontSize="0.95rem">Active Spaces</Typography>
            <Chip label={spaces.length} size="small" sx={{ height: 17, fontSize: '0.65rem' }} />
          </Box>
          {open ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
        </Box>
        <Collapse in={open}>
          <Typography fontSize="0.8rem" color="text.secondary" mt={1} mb={1.5}>
            Chats where your assistant bot has been active. Commands work in all of these.
          </Typography>
          {spaces.map(s => (
            <Box key={s.id} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75 }}>
              <Box sx={{ color: 'text.disabled' }}>{typeIcon(s.chat_type)}</Box>
              <Typography fontSize="0.84rem" sx={{ flex: 1 }} noWrap>
                {s.chat_title || s.telegram_chat_id}
              </Typography>
              <Typography fontSize="0.72rem" color="text.disabled" flexShrink={0}>
                {relTime(s.last_seen_at)}
              </Typography>
            </Box>
          ))}
          <Button size="small" sx={{ mt: 0.5, fontSize: '0.75rem' }}
            endIcon={<ArrowForward sx={{ fontSize: 13 }} />}
            onClick={() => navigate('/workspace/assistant-bot')}>
            Manage Bot
          </Button>
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ── Main Hub ──────────────────────────────────────────────────────────────────

export default function AssistantHub() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [newMeeting, setNewMeeting] = useState(null);
  const [hubTab, setHubTab] = useState(0);
  const [bannerDismissed, setBannerDismissed] = useState(
    () => localStorage.getItem(DISMISS_KEY) === '1'
  );
  const plan = (() => { try { return JSON.parse(localStorage.getItem('user') || '{}').subscription_tier || 'free'; } catch { return 'free'; } })();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data: d } = await assistant.hubSummary();
      setData(d);
    } catch {
      setError('Failed to load hub data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const dismissBanner = () => {
    localStorage.setItem(DISMISS_KEY, '1');
    setBannerDismissed(true);
  };

  const showBanner = !bannerDismissed && data && data.active_groups === 0;

  if (loading) {
    return (
      <Box sx={{ p: { xs: 2, md: 3 }, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
        <CircularProgress size={32} />
      </Box>
    );
  }

  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 860, mx: 'auto' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <Psychology sx={{ fontSize: 26, color: 'primary.main' }} />
        <Typography variant="h5" fontWeight={700}>Assistant Hub</Typography>
      </Box>
      <Typography color="text.secondary" fontSize="0.88rem" mb={2}>{today}</Typography>

      {/* Tab navigation */}
      <Tabs
        value={hubTab}
        onChange={(_, v) => setHubTab(v)}
        sx={{ mb: 3, borderBottom: '1px solid', borderColor: 'divider' }}
        variant="scrollable"
        scrollButtons="auto"
      >
        <Tab label="Overview" icon={<Psychology fontSize="small" />} iconPosition="start" />
        <Tab label="Group Trends" icon={<TrendingUp fontSize="small" />} iconPosition="start" />
      </Tabs>

      {hubTab === 0 && (
        <>
          {/* Assistant Bot status card */}
          <AssistantBotCard plan={plan} />

          {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

          {/* Connect Bot Banner */}
          {showBanner && (
            <ConnectBotBanner
              botUsername={data.bot_username}
              connectedGroups={data.connected_groups}
              onDismiss={dismissBanner}
            />
          )}

          {/* Mobile feature navigation grid */}
          {isMobile && <MobileFeatureGrid />}

          {/* Onboarding checklist */}
          {data?.onboarding && <OnboardingCard onboarding={data.onboarding} />}

          {/* Row 1 — Reminders + Notes */}
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={12} sm={6}>
              <RemindersCard reminders={data?.reminders_today || []} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <NotesCard recentNotes={data?.recent_notes || []} />
            </Grid>
          </Grid>

          {/* Row 2 — Digest + Automation */}
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <DigestCard digestStatus={data?.digest_status || []} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <ActivityCard activity={data?.automation_activity || { auto_replies_today: 0, workflows_today: 0 }} />
            </Grid>
          </Grid>

          {/* Ask Your Community */}
          <AskCard hasGroups={(data?.active_groups || 0) > 0} />

          {/* Personal Assistant Chat */}
          <PersonalAssistantChat onMeetingCreated={setNewMeeting} botConnected={data?.bot_connected} />

          {/* Upcoming Meetings */}
          <MeetingsCard newMeeting={newMeeting} />

          {/* Active Spaces — assistant bot chats */}
          <ActiveSpacesCard plan={plan} />
        </>
      )}

      {hubTab === 1 && (
        <Box>
          <Typography variant="body2" color="text.secondary" mb={3}>
            Daily health signals computed every 2 hours from your connected group activity.
          </Typography>
          <GroupTrendsDashboard />
        </Box>
      )}
    </Box>
  );
}
