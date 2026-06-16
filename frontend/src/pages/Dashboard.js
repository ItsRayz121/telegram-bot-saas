import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { SUPPORT_LINKS as SUPPORT_HREFS, openSupportEmail } from '../config/support';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  CardActions, Grid, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, IconButton, Chip, CircularProgress, Tooltip, Menu, MenuItem,
  Avatar, LinearProgress, Alert, Stepper, Step, StepLabel, StepContent,
  InputAdornment, Skeleton, Table, TableBody, TableCell, TableContainer, TableRow, Collapse,
  useTheme,
} from '@mui/material';
import useMediaQuery from '@mui/material/useMediaQuery';
import {
  Add, Delete, Settings, BarChart, SmartToy, AccountCircle,
  PowerSettingsNew, Upgrade, CheckCircle, Close, ContentCopy,
  ArrowForward, CreditCard, People, Home, AttachMoney,
  Search, ManageAccounts,
  EmojiEvents, ExpandMore, Groups, Telegram, OpenInNew,
  HelpOutline, Campaign, Email, Refresh,
} from '@mui/icons-material';
import { track } from '../services/analytics';
import Divider from '@mui/material/Divider';
import ListItemIcon from '@mui/material/ListItemIcon';
import TelegizerLogo from '../components/TelegizerLogo';
import NotificationBell from '../components/NotificationBell';
import PushNudge from '../components/PushNudge';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { bots, auth, billing, referrals as referralsApi, telegramAccount, telegramGroups as telegramGroupsApi } from '../services/api';

const MAX_BOTS = { free: 1, pro: 3, enterprise: 50 };

const HEALTH_COLORS = {
  active:      'success',
  idle:        'default',
  offline:     'default',
  unreachable: 'error',
  // legacy values — map gracefully so old API responses never break UI
  stopped:    'default',
  unknown:    'default',
  recovering: 'success',
  starting:   'success',
  warning:    'success',
  error:      'error',
};

const HEALTH_LABELS = {
  active:      'Active',
  idle:        'Idle',
  offline:     'Offline',
  unreachable: 'Unreachable',
  // legacy
  stopped:    'Offline',
  unknown:    'Active',
  recovering: 'Active',
  starting:   'Active',
  warning:    'Active',
  error:      'Unreachable',
};

function _relativeTime(iso) {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function safeParseUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

// ── Bot card skeleton ──────────────────────────────────────────────────────────
function BotCardSkeleton() {
  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Skeleton variant="circular" width={40} height={40} sx={{ mr: 1.5 }} />
          <Box sx={{ flexGrow: 1 }}>
            <Skeleton width="60%" height={20} />
            <Skeleton width="40%" height={16} />
          </Box>
          <Skeleton width={56} height={24} sx={{ borderRadius: 4 }} />
        </Box>
        <Skeleton width="30%" height={16} />
      </CardContent>
      <Box sx={{ px: 2, pb: 2, display: 'flex', gap: 1 }}>
        <Skeleton width={80} height={32} sx={{ borderRadius: 1 }} />
        <Skeleton width={80} height={32} sx={{ borderRadius: 1 }} />
      </Box>
    </Card>
  );
}

// ── Onboarding Card ────────────────────────────────────────────────────────────
function OnboardingCard({ botList, onAddBot, navigate, user, officialGroupCount, onGroupsRefresh }) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem('onboarding_dismissed') === '1'
  );
  const [expanded, setExpanded] = useState(
    () => localStorage.getItem('onboarding_expanded') !== '0'
  );
  const [waitingForGroup, setWaitingForGroup] = useState(false);
  const pollRef = React.useRef(null);

  const syncedRef = React.useRef(new Set(user?.onboarding_completed_steps || []));
  const trackedRef = React.useRef(new Set());

  const hasBots = botList.length > 0;
  const hasGroups = (officialGroupCount ?? 0) > 0 || botList.some((b) => (b.group_count ?? 0) > 0);
  // Telegram-first users are always connected — auth_provider=telegram means TG is their identity
  const isTgConnected = user?.telegram_connected || user?.auth_provider === 'telegram';

  // Sync completed steps to backend + fire PostHog events
  useEffect(() => {
    const stepMap = {
      email_verified: user?.email_verified || isTgConnected,
      bot_connected: hasBots,
      group_linked: hasGroups,
    };
    Object.entries(stepMap).forEach(([step, done]) => {
      if (done && !syncedRef.current.has(step)) {
        syncedRef.current.add(step);
        auth.markOnboardingStep(step).catch(() => { syncedRef.current.delete(step); });
      }
      if (done && !trackedRef.current.has(step)) {
        trackedRef.current.add(step);
        track('onboarding_step_completed', { step, step_number: Object.keys(stepMap).indexOf(step) + 1, total_steps: 5 });
      }
    });
  }, [user?.email_verified, isTgConnected, hasBots, hasGroups]);

  // Stop group-wait polling when group appears
  useEffect(() => {
    if (hasGroups && waitingForGroup) {
      setWaitingForGroup(false);
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    }
  }, [hasGroups, waitingForGroup]);

  // Cleanup poll on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const botUsername = process.env.REACT_APP_TELEGRAM_BOT_USERNAME || 'telegizer_bot';
  const addGroupUrl = `https://t.me/${botUsername}?startgroup=setup`;

  const handleOpenTelegram = () => {
    track('onboarding_open_telegram_clicked');
    setWaitingForGroup(true);
    // Poll for group connection every 5s for up to 3 min
    if (pollRef.current) clearInterval(pollRef.current);
    let attempts = 0;
    pollRef.current = setInterval(() => {
      attempts++;
      if (onGroupsRefresh) onGroupsRefresh();
      if (attempts >= 36) { clearInterval(pollRef.current); pollRef.current = null; setWaitingForGroup(false); }
    }, 5000);
  };

  const steps = [
    { label: 'Create your account', done: true },
    {
      // For Telegram-first users this is already done — show the right message
      label: isTgConnected ? 'Telegram account connected' : 'Connect your Telegram account',
      done: isTgConnected,
      action: !isTgConnected ? (
        <Button size="small" variant="contained" startIcon={<Telegram />} onClick={() => navigate('/settings')} sx={{ mt: 1 }}>
          Connect Telegram
        </Button>
      ) : null,
      hint: isTgConnected
        ? null  // Already done — no hint needed, label says it all
        : 'Go to Settings → Connect Telegram. Once connected, groups link automatically — no codes needed.',
    },
    {
      label: 'Add @telegizer_bot to a Telegram group as admin',
      done: hasGroups,
      action: !hasGroups ? (
        <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Button
            size="small" variant="contained" startIcon={<Telegram />}
            href={addGroupUrl} target="_blank" rel="noopener noreferrer"
            onClick={handleOpenTelegram}
          >
            Open Telegram to Add Bot
          </Button>
          {waitingForGroup && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <CircularProgress size={14} />
              <Typography variant="caption" color="text.secondary">Waiting for group…</Typography>
              <Button size="small" variant="text" sx={{ p: 0, minWidth: 0 }} onClick={() => { if (onGroupsRefresh) onGroupsRefresh(); }}>
                <Refresh sx={{ fontSize: 15 }} />
              </Button>
            </Box>
          )}
        </Box>
      ) : null,
      hint: (
        <Box>
          {isTgConnected ? (
            <Alert severity="success" icon={<CheckCircle fontSize="small" />} sx={{ mb: 1, py: 0.5, fontSize: '0.78rem' }}>
              Your Telegram is connected — after adding the bot as admin, just type <strong>/linkgroup</strong> in the group. It links automatically, no code needed.
            </Alert>
          ) : (
            <>
              <Typography variant="caption" color="text.secondary" display="block">1. Click "Open Telegram to Add Bot" → pick your group → tap Add.</Typography>
              <Typography variant="caption" color="text.secondary" display="block">2. Make @{botUsername} an <strong>admin</strong> (Group Settings → Administrators).</Typography>
              <Typography variant="caption" color="text.secondary" display="block">3. Type <code>/linkgroup</code> in the group → copy the code → paste it at Groups → Link Group.</Typography>
            </>
          )}
        </Box>
      ),
    },
    {
      label: 'Enable AutoMod to protect your group',
      done: !!(user?.onboarding_completed_steps?.includes('automod_enabled')),
      action: hasGroups ? (
        <Button size="small" variant="outlined" onClick={() => navigate('/groups')} sx={{ mt: 1 }}>
          Open Group Settings
        </Button>
      ) : null,
      hint: 'My Groups → select your group → Moderation → AutoMod → turn on spam and link filtering.',
    },
    {
      label: 'Schedule your first automated post',
      done: !!(user?.onboarding_completed_steps?.includes('schedule_created')),
      action: hasGroups ? (
        <Button size="small" variant="outlined" onClick={() => navigate('/groups')} sx={{ mt: 1 }}>
          Open Scheduler
        </Button>
      ) : null,
      hint: 'My Groups → select your group → Automation → Scheduler → create a recurring post.',
    },
  ];

  const completedCount = steps.filter((s) => s.done).length;
  const activeStep = steps.findIndex((s) => !s.done);
  const allDone = completedCount === steps.length;
  const progressPct = (completedCount / steps.length) * 100;

  const toggleExpand = () => {
    const next = !expanded;
    setExpanded(next);
    localStorage.setItem('onboarding_expanded', next ? '1' : '0');
  };

  const handleDismiss = (e) => {
    e.stopPropagation();
    setDismissed(true);
    localStorage.setItem('onboarding_dismissed', '1');
    track('onboarding_dismissed', { completed_steps: completedCount, total_steps: steps.length });
  };

  if (dismissed) return null;

  if (allDone) {
    return null;
  }

  return (
    <Card
      sx={{
        mb: 3,
        border: '1px solid',
        borderColor: expanded ? 'primary.main' : 'divider',
        bgcolor: expanded ? 'rgba(33,150,243,0.04)' : 'background.paper',
        transition: 'border-color 0.2s, background-color 0.2s',
        overflow: 'hidden',
      }}
    >
      <Box
        onClick={toggleExpand}
        sx={{
          display: 'flex', alignItems: 'center', px: 2, py: 1.25,
          gap: { xs: 1, sm: 1.5 }, cursor: 'pointer', userSelect: 'none',
          '&:hover': { bgcolor: 'action.hover' }, transition: 'background-color 0.15s',
        }}
      >
        <CheckCircle sx={{ color: 'primary.main', fontSize: 17, flexShrink: 0 }} />
        <Typography variant="body2" fontWeight={600} sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
          Getting Started
        </Typography>
        <Box sx={{ flexGrow: 1, mx: { xs: 0.5, sm: 1 }, minWidth: 40 }}>
          <LinearProgress variant="determinate" value={progressPct} sx={{ height: 5, borderRadius: 3 }} />
        </Box>
        <Typography variant="caption" color="text.secondary"
          sx={{ flexShrink: 0, whiteSpace: 'nowrap', display: { xs: 'none', sm: 'block' } }}>
          {completedCount}/{steps.length} completed
        </Typography>
        <ExpandMore sx={{
          flexShrink: 0, fontSize: 20, color: 'text.secondary',
          transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.25s ease',
        }} />
        <Tooltip title="Dismiss">
          <IconButton size="small" onClick={handleDismiss} sx={{ flexShrink: 0, p: 0.25 }}>
            <Close sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      </Box>

      <Collapse in={expanded} timeout={250}>
        <Box sx={{ px: 2, pb: 2, pt: 0.5, borderTop: '1px solid', borderColor: 'divider' }}>
          <Stepper activeStep={activeStep} orientation="vertical"
            sx={{ '& .MuiStepLabel-label': { fontSize: '0.875rem' } }}>
            {steps.map((step, idx) => (
              <Step key={step.label} completed={step.done} expanded={idx === activeStep}>
                <StepLabel StepIconProps={{ icon: step.done ? <CheckCircle color="success" /> : undefined }}>
                  <Typography variant="body2" fontWeight={step.done ? 400 : 600}
                    color={step.done ? 'text.disabled' : 'text.primary'}>
                    {step.label}
                  </Typography>
                </StepLabel>
                {!step.done && (
                  <StepContent>
                    {step.hint && (
                      <Box mb={step.action ? 0 : 1}>{step.hint}</Box>
                    )}
                    {step.action}
                  </StepContent>
                )}
              </Step>
            ))}
          </Stepper>
        </Box>
      </Collapse>
    </Card>
  );
}

// ── Invite Card ────────────────────────────────────────────────────────────────
const REFERRAL_MILESTONES = [
  { count: 3,  days: 7,  label: '7 days Pro' },
  { count: 10, days: 30, label: '1 month Pro' },
];

function InviteCard() {
  const [copied, setCopied] = useState(false);
  const [stats, setStats] = useState(null);

  const botUsername = (process.env.REACT_APP_TELEGRAM_BOT_USERNAME || 'telegizer_bot').replace(/^@/, '');
  // Primary: Telegram deep link — opens the bot which redirects to the Mini App.
  // Falls back to web invite page once stats load.
  const refCode = stats?.referral_code;
  const tgLink  = refCode ? `https://t.me/${botUsername}?start=ref_${refCode}` : '';
  const webLink = refCode ? `${window.location.origin}/invite/${refCode}` : '';
  const inviteLink = tgLink || webLink;

  useEffect(() => {
    referralsApi.getStats().then((r) => setStats(r.data)).catch(() => {});
  }, []);

  const handleCopy = () => {
    if (!inviteLink) return;
    navigator.clipboard.writeText(inviteLink).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleTelegramShare = () => {
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(webLink || inviteLink)}&text=${encodeURIComponent('Manage your Telegram groups with Telegizer — free!')}`;
    window.open(shareUrl, '_blank', 'noopener,noreferrer');
    track('referral_shared', { method: 'telegram' });
  };

  const total = stats?.total_referrals ?? 0;
  const nextMilestone = REFERRAL_MILESTONES.find((m) => total < m.count);
  const lastMilestone = [...REFERRAL_MILESTONES].reverse().find((m) => total >= m.count);

  return (
    <Card sx={{ mt: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <People color="primary" />
          <Typography variant="subtitle1" fontWeight={700}>Invite Friends — Earn Free Pro</Typography>
        </Box>

        {nextMilestone && (
          <Box sx={{ mb: 2, p: 1.5, bgcolor: 'rgba(33,150,243,0.07)', borderRadius: 2, border: '1px solid rgba(33,150,243,0.2)' }}>
            <Typography variant="body2" fontWeight={600} color="primary.main">
              {total}/{nextMilestone.count} referrals → {nextMilestone.label} free
            </Typography>
            <LinearProgress variant="determinate" value={(total / nextMilestone.count) * 100}
              sx={{ mt: 1, borderRadius: 2, height: 6 }} />
          </Box>
        )}
        {lastMilestone && !nextMilestone && (
          <Box sx={{ mb: 2, p: 1.5, bgcolor: 'rgba(46,125,50,0.07)', borderRadius: 2, border: '1px solid rgba(46,125,50,0.2)' }}>
            <Typography variant="body2" fontWeight={600} color="success.main">
              All milestones reached! {total} referrals total.
            </Typography>
          </Box>
        )}

        <Typography variant="body2" color="text.secondary" mb={2}>
          Invite 3 → get 7 days Pro · Invite 10 → get 1 month Pro. Rewards apply automatically.
        </Typography>

        {/* Telegram-first referral link */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1.5, bgcolor: 'background.default', borderRadius: 2, border: '1px solid', borderColor: 'divider', mb: 1.5 }}>
          <Telegram sx={{ fontSize: 16, color: '#0088cc', flexShrink: 0 }} />
          <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1, fontFamily: 'monospace', wordBreak: 'break-all' }}>
            {inviteLink || 'Loading…'}
          </Typography>
          <IconButton size="small" onClick={handleCopy} color={copied ? 'success' : 'default'} disabled={!inviteLink}>
            {copied ? <CheckCircle fontSize="small" /> : <ContentCopy fontSize="small" />}
          </IconButton>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button size="small" variant="outlined" startIcon={<ContentCopy fontSize="small" />}
            onClick={handleCopy} disabled={!inviteLink}>
            {copied ? 'Copied!' : 'Copy Link'}
          </Button>
          <Button size="small" variant="contained" startIcon={<Telegram fontSize="small" />}
            onClick={handleTelegramShare} disabled={!inviteLink}
            sx={{ bgcolor: '#0088cc', '&:hover': { bgcolor: '#006699' } }}>
            Share on Telegram
          </Button>
        </Box>

        {copied && (
          <Typography variant="caption" color="success.main" mt={0.75} display="block">Link copied!</Typography>
        )}
        {total > 0 && (
          <Typography variant="caption" color="text.disabled" display="block" mt={1}>
            {total} successful referral{total !== 1 ? 's' : ''} so far
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

// eslint-disable-next-line no-unused-vars
function LeaderboardCard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    referralsApi.getLeaderboard()
      .then((r) => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (!loading && (!data || data.leaderboard.length === 0)) return null;

  return (
    <Card sx={{ mt: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <EmojiEvents color="warning" />
          <Typography variant="subtitle1" fontWeight={700}>
            Top Referrers — {data?.month || ''}
          </Typography>
        </Box>

        {loading ? (
          <Box sx={{ display: 'flex', gap: 1, flexDirection: 'column' }}>
            {[1, 2, 3].map((i) => (
              <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Skeleton width={24} height={20} />
                <Skeleton width={120} height={20} sx={{ flexGrow: 1 }} />
                <Skeleton width={40} height={20} />
              </Box>
            ))}
          </Box>
        ) : (
          <>
            <TableContainer sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableBody>
                {data.leaderboard.map((entry) => (
                  <TableRow
                    key={entry.rank}
                    sx={{
                      bgcolor: entry.is_current_user ? 'rgba(33,150,243,0.07)' : 'transparent',
                    }}
                  >
                    <TableCell sx={{ width: 32, pr: 0, fontWeight: 700, color: entry.rank <= 3 ? 'warning.main' : 'text.secondary' }}>
                      #{entry.rank}
                    </TableCell>
                    <TableCell sx={{ fontWeight: entry.is_current_user ? 700 : 400 }}>
                      {entry.name} {entry.is_current_user && <Chip label="You" size="small" color="primary" sx={{ ml: 0.5, height: 18, fontSize: 10 }} />}
                    </TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600 }}>
                      {entry.referrals}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </TableContainer>

            {data.current_user_rank === null && data.current_user_count > 0 && (
              <Box sx={{ mt: 1.5, pt: 1.5, borderTop: '1px dashed', borderColor: 'divider' }}>
                <Typography variant="caption" color="text.secondary">
                  Your rank this month: unranked · {data.current_user_count} referral{data.current_user_count !== 1 ? 's' : ''}
                </Typography>
              </Box>
            )}
            {data.current_user_rank === null && data.current_user_count === 0 && (
              <Typography variant="caption" color="text.disabled" display="block" mt={1}>
                Refer friends to appear on the leaderboard
              </Typography>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── Official Bot Section ───────────────────────────────────────────────────────
function OfficialBotSection({ user, navigate, officialGroupCount }) {
  const botUsername = process.env.REACT_APP_TELEGRAM_BOT_USERNAME || 'telegizer_bot';
  const addGroupUrl = `https://t.me/${botUsername}?startgroup=setup`;
  return (
    <Card
      sx={{
        mb: 2,
        border: '1px solid',
        borderColor: 'rgba(61,142,248,0.3)',
        background: 'linear-gradient(135deg, rgba(61,142,248,0.06) 0%, rgba(11,22,38,0.9) 100%)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.4), 0 0 0 1px rgba(61,142,248,0.15)',
        transition: 'box-shadow 0.2s ease',
        '&:hover': { boxShadow: '0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(61,142,248,0.3)' },
      }}
    >
      <CardContent sx={{ pb: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Avatar
            sx={{
              mr: 1.5, width: 40, height: 40,
              background: 'linear-gradient(135deg, #3d8ef8, #22d3ee)',
              boxShadow: '0 0 14px rgba(61,142,248,0.4)',
            }}
          >
            <SmartToy fontSize="small" />
          </Avatar>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" fontWeight={700} letterSpacing="-0.01em">Official Telegizer Bot</Typography>
            <Typography variant="body2" color="text.secondary" noWrap>@{botUsername} · Shared · Always Active</Typography>
          </Box>
          <Chip label="Active" color="success" size="small" sx={{ boxShadow: '0 0 8px rgba(34,197,94,0.4)' }} />
        </Box>
        {!user?.telegram_connected && (
          <Alert severity="info" sx={{ mb: 1, py: 0.5 }} icon={<Telegram fontSize="small" />}>
            <Typography variant="caption">
              <Button size="small" sx={{ p: 0, minWidth: 0, verticalAlign: 'baseline', textTransform: 'none', fontWeight: 700 }}
                onClick={() => navigate('/settings')}>Connect Telegram</Button>
              {' '}to link groups automatically without codes.
            </Typography>
          </Alert>
        )}
        <Typography variant="caption" color="text.disabled">
          {officialGroupCount} group{officialGroupCount !== 1 ? 's' : ''} linked · Free for all verified users
        </Typography>
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2, pt: 1, gap: 1 }}>
        <Button size="small" variant="contained" component="a" href={addGroupUrl} target="_blank" rel="noopener noreferrer"
          startIcon={<Add />}>
          Add to Group
        </Button>
        <Button size="small" startIcon={<Groups />} onClick={() => navigate('/groups?bot_type=official')}>
          Manage Groups ({officialGroupCount})
        </Button>
      </CardActions>
    </Card>
  );
}

// ── Main Dashboard ─────────────────────────────────────────────────────────────
export default function Dashboard() {
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [searchParams] = useSearchParams();
  const [botList, setBotList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedBot, setSelectedBot] = useState(null);
  const [newToken, setNewToken] = useState('');
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [anchorEl, setAnchorEl] = useState(null);
  const [user, setUser] = useState(safeParseUser);
  const [subscription, setSubscription] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [tgConnecting, setTgConnecting] = useState(false);
  const [tgConnectLoading, setTgConnectLoading] = useState(false);
  const [tgConnectTimedOut, setTgConnectTimedOut] = useState(false);
  const [officialGroupCount, setOfficialGroupCount] = useState(0);
  const tgPollRef = React.useRef(null);

  const fetchBots = useCallback(async () => {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const res = await bots.getAll();
        setBotList(res.data.bots);
        setLoading(false);
        return;
      } catch (err) {
        if (attempt === 0) {
          await new Promise((r) => setTimeout(r, 1500));
        } else {
          const msg = !err.response
            ? 'Server is starting up — bots will appear shortly. Refresh in 30s.'
            : `Failed to load bots (${err.response.status})`;
          toast.error(msg);
          setLoading(false);
        }
      }
    }
  }, []);

  const fetchOfficialGroups = useCallback(async () => {
    try {
      const res = await telegramGroupsApi.list();
      const officialOnly = (res.data.groups ?? []).filter(
        (g) => (g.linked_via_bot_type === 'official' || !g.linked_via_bot_type) && !g.linked_bot_id
      );
      setOfficialGroupCount(officialOnly.length);
    } catch { /* non-fatal */ }
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const res = await auth.getMe();
      const fresh = res.data.user;
      localStorage.setItem('user', JSON.stringify(fresh));
      setUser(fresh);
    } catch { /* 401 handled by interceptor */ }
  }, []);

  const fetchSubscription = useCallback(async () => {
    try {
      const res = await billing.getSubscription();
      setSubscription(res.data.subscription);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    Promise.all([refreshUser(), fetchBots(), fetchSubscription(), fetchOfficialGroups()]);
    track('dashboard_viewed');
    return () => {
      if (tgPollRef.current) { clearInterval(tgPollRef.current); tgPollRef.current = null; }
    };
  }, [refreshUser, fetchBots, fetchSubscription, fetchOfficialGroups]);

  useEffect(() => {
    if (searchParams.get('payment') === 'success') {
      toast.success('Payment received! Your plan will upgrade within a few minutes.');
    }
  }, [searchParams]);

  const tier = user.subscription_tier || 'free';
  const maxBots = MAX_BOTS[tier] ?? 1;
  const botCount = botList.length;
  const atLimit = botCount >= maxBots;
  const nearLimit = !atLimit && botCount / maxBots >= 0.8;

  // Search / filter bots
  const filteredBots = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return botList;
    return botList.filter(
      (b) =>
        (b.bot_name || '').toLowerCase().includes(q) ||
        (b.bot_username || '').toLowerCase().includes(q)
    );
  }, [botList, searchQuery]);

  const handleAddBot = async () => {
    if (!newToken.trim()) return;
    if (atLimit) {
      toast.error(`Bot limit reached on ${tier} plan. Upgrade to add more.`);
      return;
    }
    setAdding(true);
    try {
      await bots.create({ bot_token: newToken.trim() });
      toast.success('Bot added successfully!');
      setAddOpen(false);
      setNewToken('');
      fetchBots();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to add bot');
    } finally {
      setAdding(false);
    }
  };

  const handleDeleteBot = async () => {
    if (!selectedBot) return;
    setDeleting(true);
    try {
      await bots.delete(selectedBot.id);
      toast.success('Bot deleted');
      setDeleteOpen(false);
      setSelectedBot(null);
      fetchBots();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to delete bot');
    } finally {
      setDeleting(false);
    }
  };

  const handleToggle = async (bot) => {
    try {
      await bots.toggle(bot.id);
      toast.success(`Bot ${bot.is_active ? 'stopped' : 'started'}`);
      fetchBots();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to toggle bot');
    }
  };

  const [supportAnchor, setSupportAnchor] = useState(null);

  const stopTgPoll = () => {
    if (tgPollRef.current) { clearInterval(tgPollRef.current); tgPollRef.current = null; }
  };

  const checkTgStatus = async () => {
    try {
      const s = await telegramAccount.connectionStatus();
      if (s.data.connected) {
        stopTgPoll();
        setTgConnecting(false);
        setTgConnectTimedOut(false);
        toast.success('Telegram connected!');
        await refreshUser();
        fetchOfficialGroups();
        return true;
      }
    } catch { /* ignore */ }
    return false;
  };

  const handleConnectTelegram = async () => {
    setTgConnectLoading(true);
    setTgConnectTimedOut(false);
    try {
      const r = await telegramAccount.generateConnectCode();
      window.open(r.data.url, '_blank', 'noopener,noreferrer');
      setTgConnecting(true);
      let attempts = 0;
      tgPollRef.current = setInterval(async () => {
        attempts++;
        const connected = await checkTgStatus();
        if (!connected && attempts >= 40) {
          stopTgPoll();
          setTgConnecting(false);
          setTgConnectTimedOut(true);
        }
      }, 3000);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to generate connect link');
    } finally {
      setTgConnectLoading(false);
    }
  };

  const handleLogout = async () => {
    try { await auth.logout(); } catch {}
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const tierColor = tier === 'enterprise' ? 'secondary' : tier === 'pro' ? 'primary' : 'default';

  return (
    <Box sx={{ minHeight: '100vh' }}>
      {/* ── AppBar (desktop only — AppLayout renders its own mobile top bar) ── */}
      {!isMobile && <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar sx={{ gap: 0.5, minHeight: { xs: 52, sm: 64 }, flexWrap: { xs: 'wrap', sm: 'nowrap' } }}>
          <Box
            onClick={() => navigate('/dashboard')}
            sx={{ display: 'flex', alignItems: 'center', gap: 0.75, cursor: 'pointer', mr: { xs: 0.5, md: 2 }, userSelect: 'none', flexShrink: 0 }}
          >
            <TelegizerLogo size="sm" />
          </Box>

          <Box sx={{ display: { xs: 'none', md: 'flex' }, gap: 0.5, flexGrow: 1, overflow: 'hidden' }}>
            <Button size="small" startIcon={<Home fontSize="small" />} onClick={() => navigate('/')} sx={{ color: 'text.secondary' }}>
              Home
            </Button>
            <Button size="small" startIcon={<CreditCard fontSize="small" />} onClick={() => navigate('/billing')} sx={{ color: 'text.secondary' }}>
              Billing
            </Button>
            <Button size="small" startIcon={<People fontSize="small" />} onClick={() => navigate('/referrals')} sx={{ color: 'text.secondary' }}>
              Referrals
            </Button>
            <Button size="small" startIcon={<HelpOutline fontSize="small" />} endIcon={<ExpandMore fontSize="small" />}
              onClick={e => setSupportAnchor(e.currentTarget)} sx={{ color: 'text.secondary' }}>
              Support
            </Button>
            <Menu
              anchorEl={supportAnchor}
              open={Boolean(supportAnchor)}
              onClose={() => setSupportAnchor(null)}
              anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
              transformOrigin={{ vertical: 'top', horizontal: 'left' }}
              PaperProps={{ sx: { mt: 0.5, minWidth: 220, border: '1px solid', borderColor: 'divider' } }}
            >
              <Box sx={{ px: 2, py: 1 }}>
                <Typography variant="caption" fontWeight={700} color="text.disabled" sx={{ textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: '0.65rem' }}>
                  Help &amp; Support
                </Typography>
              </Box>
              <Divider />
              <MenuItem component="a" href={SUPPORT_HREFS.channel} target="_blank" rel="noopener noreferrer" onClick={() => setSupportAnchor(null)} dense>
                <ListItemIcon><Campaign fontSize="small" sx={{ color: 'text.secondary' }} /></ListItemIcon>
                <Box>
                  <Typography variant="body2" fontWeight={600}>Official Channel</Typography>
                  <Typography variant="caption" color="text.secondary">Updates &amp; announcements</Typography>
                </Box>
                <OpenInNew sx={{ fontSize: 12, ml: 'auto', color: 'text.disabled' }} />
              </MenuItem>
              <MenuItem component="a" href={SUPPORT_HREFS.community} target="_blank" rel="noopener noreferrer" onClick={() => setSupportAnchor(null)} dense>
                <ListItemIcon><People fontSize="small" sx={{ color: 'text.secondary' }} /></ListItemIcon>
                <Box>
                  <Typography variant="body2" fontWeight={600}>Community Group</Typography>
                  <Typography variant="caption" color="text.secondary">Help from other users</Typography>
                </Box>
                <OpenInNew sx={{ fontSize: 12, ml: 'auto', color: 'text.disabled' }} />
              </MenuItem>
              <MenuItem
                onClick={() => { setSupportAnchor(null); openSupportEmail(); }}
                dense
                sx={{ cursor: 'pointer' }}
              >
                <ListItemIcon><Email fontSize="small" sx={{ color: 'primary.main' }} /></ListItemIcon>
                <Box>
                  <Typography variant="body2" fontWeight={600}>Email Support</Typography>
                  <Typography variant="caption" color="text.secondary">Click to contact us</Typography>
                </Box>
                <OpenInNew sx={{ fontSize: 12, ml: 'auto', color: 'text.disabled' }} />
              </MenuItem>
            </Menu>
          </Box>

          <Box sx={{ flexGrow: { xs: 1, md: 0 } }} />

          <Chip label={tier.toUpperCase()} color={tierColor} size="small" sx={{ mr: 1 }} />
          {tier === 'free' && (
            <Button size="small" startIcon={<Upgrade />} onClick={() => navigate('/pricing')} sx={{ mr: 1, display: { xs: 'none', sm: 'inline-flex' } }}>
              Upgrade
            </Button>
          )}
          <NotificationBell sx={{ mr: 0.5 }} />
          <IconButton onClick={(e) => setAnchorEl(e.currentTarget)}>
            <AccountCircle />
          </IconButton>
          <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
            <MenuItem disabled>
              <Typography variant="body2">
                {user.telegram_first_name ? `${user.telegram_first_name} · ` : ''}{user.email}
              </Typography>
            </MenuItem>
            <MenuItem disabled>
              <Typography variant="caption" color="text.secondary">
                {tier.charAt(0).toUpperCase() + tier.slice(1)} Plan
                {subscription?.expires && ` · expires ${new Date(subscription.expires).toLocaleDateString()}`}
              </Typography>
            </MenuItem>
            {/* Mobile-only nav items */}
            <MenuItem onClick={() => { setAnchorEl(null); navigate('/'); }} sx={{ display: { md: 'none' } }}>
              <Home fontSize="small" sx={{ mr: 1 }} /> Home / Website
            </MenuItem>
            <MenuItem onClick={() => { setAnchorEl(null); navigate('/pricing'); }} sx={{ display: { md: 'none' } }}>
              <AttachMoney fontSize="small" sx={{ mr: 1 }} /> Pricing
            </MenuItem>
            <MenuItem onClick={() => { setAnchorEl(null); navigate('/billing'); }}>
              <CreditCard fontSize="small" sx={{ mr: 1 }} /> Billing
            </MenuItem>
            <MenuItem onClick={() => { setAnchorEl(null); navigate('/settings'); }}>
              <ManageAccounts fontSize="small" sx={{ mr: 1 }} /> Account Settings
            </MenuItem>
            {tier !== 'enterprise' && (
              <MenuItem onClick={() => { setAnchorEl(null); navigate('/pricing'); }}>
                <Upgrade fontSize="small" sx={{ mr: 1 }} /> Upgrade Plan
              </MenuItem>
            )}
            {user.is_admin && (
              <MenuItem onClick={() => { setAnchorEl(null); navigate('/admin'); }}>
                Admin Panel
              </MenuItem>
            )}
            <MenuItem onClick={handleLogout}>Logout</MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>}

      <Box sx={{ maxWidth: 1200, mx: 'auto', p: { xs: 2, md: 3 } }}>

        {/* Soft, frequency-capped prompt to enable web push (only while the OS
            permission is still untouched — see PushNudge policy). */}
        <PushNudge ns="tg" />

        {/* Email verification is now enforced by VerifiedRoute in App.js —
            unverified users never reach this page. No banner needed. */}

        {/* ── Trial countdown banner (2-D-01) ── */}
        {user.trial_ends_at && user.subscription_tier === 'pro' && !subscription?.is_expired && (() => {
          const days = Math.max(0, Math.ceil((new Date(user.trial_ends_at) - Date.now()) / 86400000));
          return days <= 14 ? (
            <Alert severity={days <= 3 ? 'warning' : 'info'} sx={{ mb: 2 }}
              action={<Button size="small" color={days <= 3 ? 'warning' : 'info'} onClick={() => navigate('/billing')}>Upgrade</Button>}
              icon={<Upgrade fontSize="small" />}
            >
              {days === 0
                ? 'Your Pro trial ends today — upgrade now to keep all features.'
                : `⏰ Your Pro trial ends in ${days} day${days !== 1 ? 's' : ''} — upgrade to keep all features.`}
            </Alert>
          ) : null;
        })()}

        {/* ── Expired warning ── */}
        {subscription?.is_expired && (
          <Alert severity="error" sx={{ mb: 2 }} action={
            <Button size="small" color="error" onClick={() => navigate('/pricing')}>Renew Now</Button>
          }>
            Your {tier} plan has expired. Paid features are paused. Renew to restore full access.
          </Alert>
        )}

        {/* ── Expiry soon warning ── */}
        {!subscription?.is_expired && subscription?.expires && (() => {
          const days = Math.ceil((new Date(subscription.expires) - Date.now()) / 86400000);
          return days <= 5 ? (
            <Alert severity="warning" sx={{ mb: 2 }} action={
              <Button size="small" color="warning" onClick={() => navigate('/billing')}>Renew</Button>
            }>
              Your {tier} plan expires in {days} day{days !== 1 ? 's' : ''}. Renew to avoid interruption.
            </Alert>
          ) : null;
        })()}

        {/* ── Bot limit upgrade trigger ── */}
        {atLimit && tier !== 'enterprise' && (
          <Alert severity="info" sx={{ mb: 2 }} action={
            <Button size="small" onClick={() => navigate('/pricing')} endIcon={<ArrowForward />}>
              Upgrade
            </Button>
          }>
            You've reached the <strong>{maxBots}-bot limit</strong> on the {tier} plan. Upgrade to add more bots.
          </Alert>
        )}

        {/* ── Onboarding ── */}
        {!loading && (
          <OnboardingCard botList={botList} onAddBot={() => setAddOpen(true)} navigate={navigate}
            user={user} officialGroupCount={officialGroupCount}
            onGroupsRefresh={() => fetchOfficialGroups()} />
        )}

        {/* ── Connect Telegram banner (only for non-TG users who haven't connected yet) ── */}
        {!user.telegram_connected && user.auth_provider !== 'telegram' && !tgConnecting && !tgConnectTimedOut && (
          <Alert severity="info" icon={<Telegram />} sx={{ mb: 2 }}
            action={
              <Button size="small" color="info" variant="outlined" endIcon={<OpenInNew fontSize="small" />}
                onClick={handleConnectTelegram} disabled={tgConnectLoading}>
                {tgConnectLoading ? 'Opening…' : 'Connect'}
              </Button>
            }
          >
            <strong>Connect your Telegram account</strong> — link groups automatically without codes.
          </Alert>
        )}
        {/* ── Timed-out banner ── */}
        {tgConnectTimedOut && !user.telegram_connected && (
          <Alert severity="warning" icon={<Telegram />} sx={{ mb: 2 }}
            action={
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button size="small" variant="outlined" color="warning" onClick={checkTgStatus}>
                  Check Now
                </Button>
                <Button size="small" onClick={handleConnectTelegram} disabled={tgConnectLoading}>
                  Retry
                </Button>
              </Box>
            }
          >
            <strong>Connection timed out.</strong> Open <strong>@telegizer_bot</strong> on Telegram and
            send /start, then tap <em>Check Now</em> — or click <em>Retry</em> to generate a new link.
          </Alert>
        )}
        {/* ── Waiting banner ── */}
        {tgConnecting && (
          <Alert severity="info" icon={<CircularProgress size={18} />} sx={{ mb: 2 }}
            action={
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button size="small" variant="outlined" onClick={checkTgStatus}>Check Now</Button>
                <Button size="small" onClick={() => { stopTgPoll(); setTgConnecting(false); }}>Cancel</Button>
              </Box>
            }
          >
            Waiting for you to confirm in @telegizer_bot… Open the link that just opened in Telegram.
          </Alert>
        )}

        {/* ── Official Telegizer Bot ── */}
        {!loading && (
          <OfficialBotSection user={user} navigate={navigate} officialGroupCount={officialGroupCount} />
        )}

        {/* ── Custom Bots section ── */}
        {/* Header bar */}
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
          <Avatar
            sx={{
              width: 36, height: 36, flexShrink: 0,
              background: 'linear-gradient(135deg, #9d6cf7, #5b21b6)',
              boxShadow: '0 0 12px rgba(157,108,247,0.35)',
            }}
          >
            <SmartToy sx={{ fontSize: 18 }} />
          </Avatar>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" fontWeight={700} lineHeight={1.2} letterSpacing="-0.01em">Community Bots</Typography>
            <Typography variant="caption" color="text.secondary">
              {botCount} / {maxBots} used · {tier} plan
            </Typography>
          </Box>
          <Chip
            label={atLimit ? 'Limit Reached' : `${maxBots - botCount} slot${maxBots - botCount !== 1 ? 's' : ''} free`}
            color={atLimit ? 'error' : nearLimit ? 'warning' : 'success'}
            size="small"
          />
          <LinearProgress
            variant="determinate"
            value={(botCount / maxBots) * 100}
            color={atLimit ? 'error' : nearLimit ? 'warning' : 'primary'}
            sx={{ width: '100%', height: 3, borderRadius: 3, mt: 0.25 }}
          />
        </Box>

        {/* CTA row */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2, flexWrap: 'wrap' }}>
          <Button variant="contained" size="small" startIcon={<Add />} onClick={() => setAddOpen(true)} disabled={atLimit}>
            Add Bot
          </Button>
          <Button variant="text" size="small" component="a" href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer" startIcon={<Telegram />} sx={{ color: 'text.secondary' }}>
            BotFather
          </Button>
          {/* Compact how-to — only shown when no bots yet */}
          {botList.length === 0 && (
            <Typography variant="caption" color="text.disabled" sx={{ ml: 0.5 }}>
              Create bot on BotFather → copy token → click Add Bot
            </Typography>
          )}
          {/* How-to link — shown after first bot is added */}
          {botList.length > 0 && (
            <Tooltip title="Create bot → /newbot on @BotFather → copy token → Add Bot">
              <Typography variant="caption" color="text.disabled" sx={{ cursor: 'default', ml: 0.5, '&:hover': { color: 'text.secondary' } }}>
                How to add a bot?
              </Typography>
            </Tooltip>
          )}
          {botList.length > 1 && (
            <TextField
              size="small"
              placeholder="Search bots…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              InputProps={{
                startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment>,
                endAdornment: searchQuery ? (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => setSearchQuery('')}><Close fontSize="small" /></IconButton>
                  </InputAdornment>
                ) : null,
              }}
              sx={{ width: { xs: '100%', sm: 180 }, ml: { sm: 'auto' } }}
            />
          )}
        </Box>

        {/* Bot grid — responsive: 1→full, 2→2col, 3+→3col max */}
        {loading ? (
          <Grid container spacing={2} sx={{ mb: 3 }}>
            {[1, 2, 3].map((i) => (
              <Grid item xs={12} sm={6} md={4} key={i}>
                <BotCardSkeleton />
              </Grid>
            ))}
          </Grid>
        ) : botList.length === 0 ? null
        : filteredBots.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4, mb: 3 }}>
            <Typography color="text.secondary">No bots match "{searchQuery}"</Typography>
          </Box>
        ) : (
          <Grid container spacing={2} sx={{ mb: 3 }}>
            {filteredBots.map((bot) => {
              const health = bot.health_status || 'unknown';
              // 1 bot → full width; 2 bots → half; 3+ → thirds (max 3/row)
              const colMd = filteredBots.length === 1 ? 12 : filteredBots.length === 2 ? 6 : 4;
              const colSm = filteredBots.length === 1 ? 12 : 6;
              return (
                <Grid item xs={12} sm={colSm} md={colMd} key={bot.id} sx={{ display: 'flex' }}>
                  <Card
                    sx={{
                      flex: 1, display: 'flex', flexDirection: 'column',
                      cursor: 'pointer',
                      transition: 'transform 0.2s cubic-bezier(0.22,1,0.36,1), box-shadow 0.2s ease, border-color 0.2s',
                      '&:hover': {
                        transform: 'translateY(-3px)',
                        boxShadow: '0 12px 40px rgba(0,0,0,0.55), 0 0 0 1px rgba(61,142,248,0.25)',
                        borderColor: 'rgba(61,142,248,0.3)',
                      },
                    }}
                  >
                    <CardContent sx={{ flex: 1, pb: 1 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                        <Avatar
                          sx={{
                            mr: 1.5, width: 38, height: 38, flexShrink: 0,
                            background: 'linear-gradient(135deg, #3d8ef8, #9d6cf7)',
                            boxShadow: '0 0 10px rgba(61,142,248,0.3)',
                          }}
                        >
                          <SmartToy sx={{ fontSize: 18 }} />
                        </Avatar>
                        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                          <Typography variant="subtitle2" fontWeight={700} noWrap>{bot.bot_name}</Typography>
                          <Typography variant="caption" color="text.secondary" noWrap>@{bot.bot_username}</Typography>
                        </Box>
                        <Tooltip title={`Health: ${HEALTH_LABELS[health]}`}>
                          <Chip label={HEALTH_LABELS[health]} color={HEALTH_COLORS[health]} size="small" />
                        </Tooltip>
                      </Box>
                      <Typography variant="caption" color="text.disabled">
                        {bot.group_count ?? 0} group{bot.group_count !== 1 ? 's' : ''}
                        {bot.last_active && <> · last active {_relativeTime(bot.last_active)}</>}
                      </Typography>
                    </CardContent>
                    <CardActions sx={{ px: 1.5, pb: 1.5, pt: 0, gap: 0.5, flexWrap: 'wrap' }}>
                      <Button size="small" startIcon={<Settings />} onClick={() => navigate(`/bot/${bot.id}`)}>Groups</Button>
                      <Button size="small" startIcon={<BarChart />} onClick={() => navigate(`/analytics/${bot.id}`)}>Analytics</Button>
                      <Box sx={{ flexGrow: 1 }} />
                      <Tooltip title={bot.is_active ? 'Stop bot' : 'Start bot'}>
                        <IconButton size="small" onClick={() => handleToggle(bot)}>
                          <PowerSettingsNew fontSize="small" color={bot.is_active ? 'success' : 'disabled'} />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Delete bot">
                        <IconButton size="small" onClick={() => { setSelectedBot(bot); setDeleteOpen(true); }}>
                          <Delete fontSize="small" color="error" />
                        </IconButton>
                      </Tooltip>
                    </CardActions>
                  </Card>
                </Grid>
              );
            })}
          </Grid>
        )}


        {/* ── Upgrade CTA for free users with bots ── */}
        {!loading && tier === 'free' && botList.length > 0 && (
          <Card
            sx={{
              mt: 3, border: 'none', overflow: 'hidden', position: 'relative',
              background: 'linear-gradient(135deg, #1a3a6e 0%, #3d1d82 50%, #0d2a5a 100%)',
              backgroundSize: '200% 200%',
              animation: 'gradientShift 8s ease infinite',
              boxShadow: '0 8px 32px rgba(61,142,248,0.25), 0 0 60px rgba(157,108,247,0.15)',
            }}
          >
            {/* Ambient orb */}
            <Box sx={{
              position: 'absolute', top: -30, right: -30,
              width: 180, height: 180, borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(157,108,247,0.25) 0%, transparent 70%)',
              pointerEvents: 'none',
            }} />
            <CardContent sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2, p: { xs: 2.5, md: 3 }, position: 'relative' }}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="subtitle1" fontWeight={700} color="white" letterSpacing="-0.01em">
                  Unlock 5 bots, unlimited groups & scheduling
                </Typography>
                <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.7)' }}>
                  Pro plan — just $9/month. Pay with crypto.
                </Typography>
              </Box>
              <Button
                variant="contained"
                onClick={() => navigate('/pricing')}
                endIcon={<ArrowForward />}
                sx={{
                  bgcolor: 'white', color: '#1a3a6e', fontWeight: 700,
                  boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
                  '&:hover': { bgcolor: '#e8f0ff', transform: 'translateY(-1px)' },
                  width: { xs: '100%', sm: 'auto' },
                }}
              >
                Upgrade to Pro
              </Button>
            </CardContent>
          </Card>
        )}


      </Box>

      {/* ── Add Bot Dialog ── */}
      <Dialog open={addOpen} onClose={() => { setAddOpen(false); setNewToken(''); }} maxWidth="sm" fullWidth>
        <DialogTitle>Add Telegram Bot</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            1. Open Telegram and message <strong>@BotFather</strong><br />
            2. Send <code>/newbot</code> and follow the steps<br />
            3. Copy the token it gives you and paste it below
          </Typography>
          <TextField
            fullWidth
            label="Bot Token"
            value={newToken}
            onChange={(e) => setNewToken(e.target.value)}
            placeholder="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
            helperText="Token from @BotFather — starts with your bot's ID"
            autoFocus
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setAddOpen(false); setNewToken(''); }}>Cancel</Button>
          <Button variant="contained" onClick={handleAddBot} disabled={adding || !newToken.trim()}>
            {adding ? <CircularProgress size={20} color="inherit" /> : 'Add Bot'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Delete Bot Dialog ── */}
      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Delete Bot</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>{selectedBot?.bot_name}</strong>? This removes all
            groups, members, settings, and scheduled content. This cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOpen(false)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDeleteBot} disabled={deleting}>
            {deleting ? <CircularProgress size={20} color="inherit" /> : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
