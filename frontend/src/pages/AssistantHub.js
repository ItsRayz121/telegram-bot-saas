import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, CircularProgress,
  Alert, LinearProgress,
  IconButton, Tooltip, Collapse, Tabs, Tab,
} from '@mui/material';
import {
  Psychology, OpenInNew, ContentCopy, CheckCircle, RadioButtonUnchecked, Close,
  ArrowForward, ExpandMore, ExpandLess,
  CalendarMonth, SmartToy, Lock, Groups, Person, TrendingUp,
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
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(4, 1fr)' }, gap: 1 }}>
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

// ── Calendar Helpers ──────────────────────────────────────────────────────────

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


// ── Meetings Panel ────────────────────────────────────────────────────────────

const PRIORITY_COLOR = { low: 'success', medium: 'warning', high: 'error' };

function MeetingsCard() {
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

          {/* Upcoming Meetings */}
          <MeetingsCard />

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
