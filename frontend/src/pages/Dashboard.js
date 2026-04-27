import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  CardActions, Grid, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, IconButton, Chip, CircularProgress, Tooltip, Menu, MenuItem,
  Avatar, LinearProgress, Alert, Stepper, Step, StepLabel, StepContent,
  InputAdornment, Skeleton, Table, TableBody, TableCell, TableRow, Collapse,
} from '@mui/material';
import {
  Add, Delete, Settings, BarChart, SmartToy, AccountCircle,
  PowerSettingsNew, Upgrade, CheckCircle, Close, ContentCopy,
  ArrowForward, CreditCard, People, Home, AttachMoney,
  Notifications, NotificationsNone, Search, ManageAccounts,
  EmojiEvents, ExpandMore, Groups, Telegram, OpenInNew,
} from '@mui/icons-material';
import TelegizerLogo from '../components/TelegizerLogo';
import Badge from '@mui/material/Badge';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { bots, auth, billing, referrals as referralsApi, notifications as notificationsApi, telegramAccount, telegramGroups as telegramGroupsApi } from '../services/api';

const MAX_BOTS = { free: 1, pro: 5, enterprise: 50 };

const HEALTH_COLORS = {
  active:     'success',
  warning:    'warning',
  error:      'error',
  stopped:    'default',
  unknown:    'default',
  recovering: 'warning',
  starting:   'info',
};

const HEALTH_LABELS = {
  active:     'Active',
  warning:    'Stale',
  error:      'Error',
  stopped:    'Stopped',
  unknown:    'Unknown',
  recovering: 'Restarting',
  starting:   'Starting',
};

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
function OnboardingCard({ botList, onAddBot, navigate, user, officialGroupCount }) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem('onboarding_dismissed') === '1'
  );
  // Collapsed by default; remember user's preference
  const [expanded, setExpanded] = useState(
    () => localStorage.getItem('onboarding_expanded') === '1'
  );

  const hasBots = botList.length > 0;
  const hasGroups = (officialGroupCount ?? 0) > 0 || botList.some((b) => (b.group_count ?? 0) > 0);
  const isTgConnected = user?.telegram_connected;
  const botUsername = 'telegizer_bot';
  const addGroupUrl = `https://t.me/${botUsername}?startgroup=setup`;

  const steps = [
    { label: 'Create your account', done: true },
    {
      label: 'Connect your Telegram account',
      done: isTgConnected,
      action: !isTgConnected ? (
        <Button size="small" variant="contained" startIcon={<Telegram />} onClick={() => navigate('/settings')} sx={{ mt: 1 }}>
          Connect Telegram
        </Button>
      ) : null,
      hint: 'Go to Settings → Connect Telegram. This lets you link groups automatically without entering codes.',
    },
    {
      label: 'Add @telegizer_bot to a Telegram group as admin',
      done: hasGroups,
      action: !hasGroups ? (
        <Button size="small" variant="contained" startIcon={<Add />} href={addGroupUrl} target="_blank" rel="noopener noreferrer" sx={{ mt: 1 }}>
          Add to Group
        </Button>
      ) : null,
      hint: 'Open Telegram, add @telegizer_bot to your group, make it admin, then run /linkgroup in the group.',
    },
    {
      label: 'Enable AutoMod',
      done: false,
      action: hasGroups ? (
        <Button size="small" variant="outlined" onClick={() => navigate('/my-groups')} sx={{ mt: 1 }}>
          Open Group Settings
        </Button>
      ) : null,
      hint: 'Go to My Groups → Group Settings → AutoMod to enable spam detection and link filtering.',
    },
    {
      label: 'Schedule your first message',
      done: false,
      action: hasGroups ? (
        <Button size="small" variant="outlined" onClick={() => navigate('/my-groups')} sx={{ mt: 1 }}>
          Open Scheduler
        </Button>
      ) : null,
      hint: 'Set up a daily or weekly post so your group always has fresh content.',
    },
  ];

  const completedCount = steps.filter((s) => s.done).length;
  const activeStep = steps.findIndex((s) => !s.done);
  const allDone = completedCount === steps.length;
  const progressPct = (completedCount / steps.length) * 100;

  // Auto-hide when dismissed or fully complete
  if (dismissed || allDone) return null;

  const toggleExpand = () => {
    const next = !expanded;
    setExpanded(next);
    localStorage.setItem('onboarding_expanded', next ? '1' : '0');
  };

  const handleDismiss = (e) => {
    e.stopPropagation();
    setDismissed(true);
    localStorage.setItem('onboarding_dismissed', '1');
  };

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
      {/* ── Compact summary bar (always visible) ── */}
      <Box
        onClick={toggleExpand}
        sx={{
          display: 'flex',
          alignItems: 'center',
          px: 2,
          py: 1.25,
          gap: { xs: 1, sm: 1.5 },
          cursor: 'pointer',
          userSelect: 'none',
          '&:hover': { bgcolor: 'action.hover' },
          transition: 'background-color 0.15s',
        }}
      >
        <CheckCircle sx={{ color: 'primary.main', fontSize: 17, flexShrink: 0 }} />

        <Typography variant="body2" fontWeight={600} sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
          Getting Started
        </Typography>

        {/* Inline progress bar — fills available space */}
        <Box sx={{ flexGrow: 1, mx: { xs: 0.5, sm: 1 }, minWidth: 40 }}>
          <LinearProgress
            variant="determinate"
            value={progressPct}
            sx={{ height: 5, borderRadius: 3 }}
          />
        </Box>

        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ flexShrink: 0, whiteSpace: 'nowrap', display: { xs: 'none', sm: 'block' } }}
        >
          {completedCount}/{steps.length} completed
        </Typography>

        {/* Chevron */}
        <ExpandMore
          sx={{
            flexShrink: 0,
            fontSize: 20,
            color: 'text.secondary',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.25s ease',
          }}
        />

        {/* Dismiss */}
        <Tooltip title="Dismiss">
          <IconButton size="small" onClick={handleDismiss} sx={{ flexShrink: 0, p: 0.25 }}>
            <Close sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      </Box>

      {/* ── Expanded checklist ── */}
      <Collapse in={expanded} timeout={250}>
        <Box sx={{ px: 2, pb: 2, pt: 0.5, borderTop: '1px solid', borderColor: 'divider' }}>
          <Stepper
            activeStep={activeStep}
            orientation="vertical"
            sx={{ '& .MuiStepLabel-label': { fontSize: '0.875rem' } }}
          >
            {steps.map((step, idx) => (
              <Step key={step.label} completed={step.done} expanded={idx === activeStep}>
                <StepLabel StepIconProps={{ icon: step.done ? <CheckCircle color="success" /> : undefined }}>
                  <Typography
                    variant="body2"
                    fontWeight={step.done ? 400 : 600}
                    color={step.done ? 'text.disabled' : 'text.primary'}
                  >
                    {step.label}
                  </Typography>
                </StepLabel>
                {!step.done && (
                  <StepContent>
                    {step.hint && (
                      <Typography variant="caption" color="text.secondary" display="block" mb={step.action ? 0 : 1}>
                        {step.hint}
                      </Typography>
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

function InviteCard({ userId }) {
  const [copied, setCopied] = useState(false);
  const [stats, setStats] = useState(null);
  const inviteLink = `${window.location.origin}/register?ref=${userId}`;

  useEffect(() => {
    referralsApi.getStats().then((r) => setStats(r.data)).catch(() => {});
  }, []);

  const handleCopy = () => {
    navigator.clipboard.writeText(inviteLink).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
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
            <LinearProgress
              variant="determinate"
              value={(total / nextMilestone.count) * 100}
              sx={{ mt: 1, borderRadius: 2, height: 6 }}
            />
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

        <Box sx={{
          display: 'flex', alignItems: 'center', gap: 1,
          p: 1.5, bgcolor: 'background.default', borderRadius: 2,
          border: '1px solid', borderColor: 'divider', overflowX: 'auto',
        }}>
          <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
            {inviteLink}
          </Typography>
          <IconButton size="small" onClick={handleCopy} color={copied ? 'success' : 'default'}>
            {copied ? <CheckCircle fontSize="small" /> : <ContentCopy fontSize="small" />}
          </IconButton>
        </Box>
        {copied && (
          <Typography variant="caption" color="success.main" mt={0.5} display="block">Link copied!</Typography>
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

// ── Referral Leaderboard Card ──────────────────────────────────────────────────
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
  const botUsername = 'telegizer_bot';
  const addGroupUrl = `https://t.me/${botUsername}?startgroup=setup`;
  return (
    <Card sx={{ mb: 2, border: '1px solid', borderColor: 'primary.light', bgcolor: 'rgba(33,150,243,0.03)' }}>
      <CardContent sx={{ pb: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Avatar sx={{ bgcolor: 'primary.main', mr: 1.5, width: 40, height: 40 }}>
            <SmartToy fontSize="small" />
          </Avatar>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" fontWeight={700}>Official Telegizer Bot</Typography>
            <Typography variant="body2" color="text.secondary" noWrap>@{botUsername} · Shared · Always Active</Typography>
          </Box>
          <Chip label="Active" color="success" size="small" />
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
        <Button size="small" startIcon={<Groups />} onClick={() => navigate('/my-groups?bot_type=official')}>
          Manage Groups ({officialGroupCount})
        </Button>
      </CardActions>
    </Card>
  );
}

// ── Main Dashboard ─────────────────────────────────────────────────────────────
export default function Dashboard() {
  const navigate = useNavigate();
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
    try {
      const res = await bots.getAll();
      setBotList(res.data.bots);
    } catch {
      toast.error('Failed to load bots');
    } finally {
      setLoading(false);
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
    refreshUser();
    fetchBots();
    fetchSubscription();
    fetchOfficialGroups();
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

  const [unreadNotifs, setUnreadNotifs] = useState(0);
  const [notifAnchor, setNotifAnchor] = useState(null);
  const [notifList, setNotifList] = useState([]);

  useEffect(() => {
    notificationsApi.unreadCount().then(r => setUnreadNotifs(r.data.unread || 0)).catch(() => {});
  }, []);

  const openNotifMenu = async (e) => {
    setNotifAnchor(e.currentTarget);
    try {
      const r = await notificationsApi.list({ per_page: 10 });
      setNotifList(r.data.notifications || []);
      setUnreadNotifs(r.data.unread || 0);
    } catch {}
  };

  const markAllRead = async () => {
    try {
      await notificationsApi.markAllRead();
      setUnreadNotifs(0);
      setNotifList(prev => prev.map(n => ({ ...n, read: true })));
    } catch {}
  };

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
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* ── AppBar ── */}
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar sx={{ gap: 0.5 }}>
          <Box
            onClick={() => navigate('/dashboard')}
            sx={{ display: 'flex', alignItems: 'center', gap: 0.75, cursor: 'pointer', mr: 2, userSelect: 'none' }}
          >
            <TelegizerLogo size="sm" />
          </Box>

          <Box sx={{ display: { xs: 'none', md: 'flex' }, gap: 0.5, flexGrow: 1 }}>
            <Button size="small" startIcon={<Home fontSize="small" />} onClick={() => navigate('/')} sx={{ color: 'text.secondary' }}>
              Home
            </Button>
            <Button size="small" startIcon={<CreditCard fontSize="small" />} onClick={() => navigate('/billing')} sx={{ color: 'text.secondary' }}>
              Billing
            </Button>
          </Box>

          <Box sx={{ flexGrow: { xs: 1, md: 0 } }} />

          <Chip label={tier.toUpperCase()} color={tierColor} size="small" sx={{ mr: 1 }} />
          {tier === 'free' && (
            <Button size="small" startIcon={<Upgrade />} onClick={() => navigate('/pricing')} sx={{ mr: 1, display: { xs: 'none', sm: 'inline-flex' } }}>
              Upgrade
            </Button>
          )}
          <IconButton onClick={openNotifMenu} sx={{ mr: 0.5 }}>
            <Badge badgeContent={unreadNotifs} color="error" max={99}>
              {unreadNotifs > 0 ? <Notifications /> : <NotificationsNone />}
            </Badge>
          </IconButton>
          <Menu anchorEl={notifAnchor} open={Boolean(notifAnchor)} onClose={() => setNotifAnchor(null)}
            PaperProps={{ sx: { width: 340, maxHeight: 460 } }}>
            <Box sx={{ px: 2, py: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="subtitle2" fontWeight={700}>Notifications</Typography>
              {unreadNotifs > 0 && <Button size="small" onClick={markAllRead}>Mark all read</Button>}
            </Box>
            {notifList.length === 0 ? (
              <MenuItem disabled><Typography variant="body2" color="text.secondary">No notifications yet</Typography></MenuItem>
            ) : notifList.map(n => (
              <MenuItem key={n.id} sx={{ whiteSpace: 'normal', alignItems: 'flex-start', py: 1,
                bgcolor: n.read ? 'transparent' : 'action.hover' }}>
                <Box>
                  <Typography variant="body2" fontWeight={n.read ? 400 : 600}>{n.title}</Typography>
                  <Typography variant="caption" color="text.secondary">{n.message}</Typography>
                  <Typography variant="caption" display="block" color="text.disabled">
                    {new Date(n.created_at).toLocaleDateString()}
                  </Typography>
                </Box>
              </MenuItem>
            ))}
          </Menu>
          <IconButton onClick={(e) => setAnchorEl(e.currentTarget)}>
            <AccountCircle />
          </IconButton>
          <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
            <MenuItem disabled>
              <Typography variant="body2">{user.email}</Typography>
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
      </AppBar>

      <Box sx={{ maxWidth: 1200, mx: 'auto', p: { xs: 2, md: 3 } }}>

        {/* Email verification is now enforced by VerifiedRoute in App.js —
            unverified users never reach this page. No banner needed. */}

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
            user={user} officialGroupCount={officialGroupCount} />
        )}

        {/* ── Connect Telegram banner ── */}
        {!user.telegram_connected && !tgConnecting && !tgConnectTimedOut && (
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

        {/* ── Custom Bots header + search ── */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1, gap: 1, flexWrap: 'wrap' }}>
          <Box>
            <Typography variant="h5" fontWeight={700}>Custom Bots</Typography>
            <Typography variant="caption" color="text.secondary">
              {botCount} / {maxBots} custom bots · {tier} plan
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
            {botList.length > 1 && (
              <TextField
                size="small"
                placeholder="Search bots…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search fontSize="small" />
                    </InputAdornment>
                  ),
                  endAdornment: searchQuery ? (
                    <InputAdornment position="end">
                      <IconButton size="small" onClick={() => setSearchQuery('')}>
                        <Close fontSize="small" />
                      </IconButton>
                    </InputAdornment>
                  ) : null,
                }}
                sx={{ width: { xs: '100%', sm: 220 } }}
              />
            )}
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setAddOpen(true)}
              disabled={atLimit}
              sx={{ flexShrink: 0 }}
            >
              Add Bot
            </Button>
          </Box>
        </Box>

        {/* ── Bot limit bar ── */}
        <Box sx={{ mb: 3 }}>
          <LinearProgress
            variant="determinate"
            value={(botCount / maxBots) * 100}
            color={atLimit ? 'error' : nearLimit ? 'warning' : 'primary'}
            sx={{ height: 4, borderRadius: 2 }}
          />
        </Box>

        {/* ── Bot list ── */}
        {loading ? (
          <Grid container spacing={2}>
            {[1, 2, 3].map((i) => (
              <Grid item xs={12} sm={6} md={4} key={i}>
                <BotCardSkeleton />
              </Grid>
            ))}
          </Grid>
        ) : botList.length === 0 ? (
          <Card sx={{ textAlign: 'center', py: 8, px: 3 }}>
            <TelegizerLogo variant="icon" size="xl" sx={{ mb: 2, opacity: 0.35 }} />
            <Typography variant="h6" fontWeight={700} mb={1}>Add your first bot</Typography>
            <Typography variant="body2" color="text.secondary" mb={0.5} sx={{ maxWidth: 400, mx: 'auto' }}>
              Get a token from <strong>@BotFather</strong> on Telegram, paste it here, and you're running in seconds.
            </Typography>
            <Typography variant="caption" color="text.disabled" display="block" mb={3}>
              Your free plan includes 1 bot and 1 group — no credit card needed.
            </Typography>
            <Button variant="contained" startIcon={<Add />} onClick={() => setAddOpen(true)} size="large">
              Add Your First Bot
            </Button>
          </Card>
        ) : filteredBots.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 6 }}>
            <Typography color="text.secondary">No bots match "{searchQuery}"</Typography>
          </Box>
        ) : (
          <Grid container spacing={2}>
            {filteredBots.map((bot) => {
              const health = bot.health_status || 'unknown';
              return (
                <Grid item xs={12} sm={6} md={4} key={bot.id}>
                  <Card>
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                        <Avatar sx={{ bgcolor: 'primary.main', mr: 1.5, width: 40, height: 40 }}>
                          <SmartToy fontSize="small" />
                        </Avatar>
                        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                          <Typography variant="subtitle1" fontWeight={600} noWrap>{bot.bot_name}</Typography>
                          <Typography variant="body2" color="text.secondary" noWrap>@{bot.bot_username}</Typography>
                        </Box>
                        <Tooltip title={`Health: ${HEALTH_LABELS[health]}`}>
                          <Chip
                            label={HEALTH_LABELS[health]}
                            color={HEALTH_COLORS[health]}
                            size="small"
                          />
                        </Tooltip>
                      </Box>
                      <Typography variant="caption" color="text.disabled">
                        {bot.group_count ?? 0} group{bot.group_count !== 1 ? 's' : ''}
                        {bot.last_active && (
                          <> · last active {new Date(bot.last_active).toLocaleDateString()}</>
                        )}
                      </Typography>
                    </CardContent>
                    <CardActions sx={{ px: 2, pb: 2, gap: 0.5, flexWrap: 'wrap' }}>
                      <Button size="small" startIcon={<Settings />} onClick={() => navigate(`/bot/${bot.id}`)}>
                        Groups
                      </Button>
                      <Button size="small" startIcon={<BarChart />} onClick={() => navigate(`/analytics/${bot.id}`)}>
                        Analytics
                      </Button>
                      <Box sx={{ flexGrow: 1 }} />
                      <Tooltip title={bot.is_active ? 'Stop bot' : 'Start bot'}>
                        <IconButton onClick={() => handleToggle(bot)} sx={{ minWidth: 40, minHeight: 40 }}>
                          <PowerSettingsNew fontSize="small" color={bot.is_active ? 'success' : 'disabled'} />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Delete bot">
                        <IconButton onClick={() => { setSelectedBot(bot); setDeleteOpen(true); }} sx={{ minWidth: 40, minHeight: 40 }}>
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
          <Card sx={{ mt: 3, background: 'linear-gradient(135deg, #1565c0 0%, #7c4dff 100%)', border: 'none' }}>
            <CardContent sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2, p: { xs: 2.5, md: 3 } }}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="subtitle1" fontWeight={700} color="white">
                  Unlock 5 bots, unlimited groups & scheduling
                </Typography>
                <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.8)' }}>
                  Pro plan — just $9/month ($0.30/day). Pay with crypto.
                </Typography>
              </Box>
              <Button
                variant="contained"
                onClick={() => navigate('/pricing')}
                endIcon={<ArrowForward />}
                sx={{ bgcolor: 'white', color: 'primary.main', fontWeight: 700, '&:hover': { bgcolor: '#f0f0f0' }, width: { xs: '100%', sm: 'auto' } }}
              >
                Upgrade to Pro
              </Button>
            </CardContent>
          </Card>
        )}

        {/* ── Invite section ── */}
        {!loading && user.id && <InviteCard userId={user.id} />}

        {/* ── Leaderboard ── */}
        {!loading && <LeaderboardCard />}

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
      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)}>
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
