import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, CircularProgress,
  Alert, Grid, LinearProgress, Divider, List, ListItem, ListItemText,
  IconButton, Tooltip, Checkbox,
} from '@mui/material';
import {
  Psychology, AccessTime, EditNote, Summarize, AutoMode, Reply,
  OpenInNew, ContentCopy, CheckCircle, RadioButtonUnchecked, Close,
  ArrowForward,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { assistant } from '../services/api';

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
              <Typography fontSize="0.84rem" noWrap>{r.reminder_text}</Typography>
              <Typography fontSize="0.72rem" color={r.is_delivered ? 'success.main' : 'text.disabled'}>
                {upcomingTime(r.remind_at)}{r.is_delivered ? ' · Done' : ''}
              </Typography>
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

// ── Main Hub ──────────────────────────────────────────────────────────────────

export default function AssistantHub() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [bannerDismissed, setBannerDismissed] = useState(
    () => localStorage.getItem(DISMISS_KEY) === '1'
  );

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
      <Box sx={{ p: 3, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
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
      <Typography color="text.secondary" fontSize="0.88rem" mb={3}>{today}</Typography>

      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      {/* Connect Bot Banner */}
      {showBanner && (
        <ConnectBotBanner
          botUsername={data.bot_username}
          connectedGroups={data.connected_groups}
          onDismiss={dismissBanner}
        />
      )}

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
    </Box>
  );
}
