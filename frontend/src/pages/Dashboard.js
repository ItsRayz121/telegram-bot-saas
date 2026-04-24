import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  CardActions, Grid, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, IconButton, Chip, CircularProgress, Tooltip, Menu, MenuItem,
  Avatar, LinearProgress, Alert, Stepper, Step, StepLabel, StepContent,
  Snackbar, Collapse,
} from '@mui/material';
import {
  Add, Delete, Settings, BarChart, SmartToy, AccountCircle,
  PowerSettingsNew, Upgrade, CheckCircle, Close, ContentCopy,
  ArrowForward, CreditCard, People,
} from '@mui/icons-material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { bots, auth, billing } from '../services/api';

const MAX_BOTS = { free: 1, pro: 5, enterprise: 50 };

function safeParseUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

// ── Onboarding Card ────────────────────────────────────────────────────────────
function OnboardingCard({ botList, onAddBot, navigate }) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem('onboarding_dismissed') === '1'
  );

  const hasBots = botList.length > 0;
  const hasGroups = botList.some((b) => (b.group_count ?? 0) > 0);

  const steps = [
    { label: 'Create your account', done: true },
    {
      label: 'Add your first bot',
      done: hasBots,
      action: !hasBots ? (
        <Button size="small" variant="contained" startIcon={<Add />} onClick={onAddBot} sx={{ mt: 1 }}>
          Add Bot
        </Button>
      ) : null,
      hint: 'Get a token from @BotFather on Telegram, then paste it here.',
    },
    {
      label: 'Add bot to your Telegram group as admin',
      done: hasGroups,
      hint: 'Open Telegram, add your bot to the group, and make it admin. The group appears here automatically.',
    },
    {
      label: 'Enable AutoMod',
      done: false,
      action: hasBots ? (
        <Button size="small" variant="outlined" onClick={() => navigate(`/bot/${botList[0]?.id}`)} sx={{ mt: 1 }}>
          Open Group Settings
        </Button>
      ) : null,
      hint: 'Go to Group Settings → AutoMod to enable spam detection and link filtering.',
    },
    {
      label: 'Schedule your first message',
      done: false,
      action: hasBots ? (
        <Button size="small" variant="outlined" onClick={() => navigate(`/bot/${botList[0]?.id}`)} sx={{ mt: 1 }}>
          Open Scheduler
        </Button>
      ) : null,
      hint: 'Set up a daily or weekly post so your group always has fresh content.',
    },
  ];

  const completedCount = steps.filter((s) => s.done).length;
  const activeStep = steps.findIndex((s) => !s.done);
  const allDone = completedCount === steps.length;

  if (dismissed && !allDone) return null;
  if (allDone) return null;

  const remaining = steps.length - completedCount;

  return (
    <Card sx={{ mb: 3, border: '1px solid', borderColor: 'primary.main', bgcolor: 'rgba(33,150,243,0.04)' }}>
      <CardContent sx={{ pb: 1 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Box>
            <Typography variant="subtitle1" fontWeight={700}>
              Getting Started
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {remaining} step{remaining !== 1 ? 's' : ''} away from full automation
            </Typography>
          </Box>
          <IconButton size="small" onClick={() => { setDismissed(true); localStorage.setItem('onboarding_dismissed', '1'); }}>
            <Close fontSize="small" />
          </IconButton>
        </Box>

        <LinearProgress
          variant="determinate"
          value={(completedCount / steps.length) * 100}
          sx={{ mt: 1.5, mb: 2, height: 6, borderRadius: 3 }}
        />

        <Stepper activeStep={activeStep} orientation="vertical" sx={{ '& .MuiStepLabel-label': { fontSize: '0.875rem' } }}>
          {steps.map((step, idx) => (
            <Step key={step.label} completed={step.done} expanded={idx === activeStep}>
              <StepLabel
                StepIconProps={{
                  icon: step.done ? <CheckCircle color="success" /> : undefined,
                }}
              >
                <Typography variant="body2" fontWeight={step.done ? 400 : 600} color={step.done ? 'text.disabled' : 'text.primary'}>
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
      </CardContent>
    </Card>
  );
}

// ── Invite Card ────────────────────────────────────────────────────────────────
function InviteCard({ userId }) {
  const [copied, setCopied] = useState(false);
  const inviteLink = `${window.location.origin}/register?ref=${userId}`;

  const handleCopy = () => {
    navigator.clipboard.writeText(inviteLink).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Card sx={{ mt: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <People color="primary" />
          <Typography variant="subtitle1" fontWeight={700}>Invite Friends</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Share BotForge with other community admins. Referral rewards coming soon — invite early and get credited automatically.
        </Typography>
        <Box
          sx={{
            display: 'flex', alignItems: 'center', gap: 1,
            p: 1.5, bgcolor: 'background.default', borderRadius: 2,
            border: '1px solid', borderColor: 'divider',
            overflowX: 'auto',
          }}
        >
          <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
            {inviteLink}
          </Typography>
          <IconButton size="small" onClick={handleCopy} color={copied ? 'success' : 'default'}>
            {copied ? <CheckCircle fontSize="small" /> : <ContentCopy fontSize="small" />}
          </IconButton>
        </Box>
        {copied && (
          <Typography variant="caption" color="success.main" mt={0.5} display="block">
            Link copied!
          </Typography>
        )}
      </CardContent>
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
  }, [refreshUser, fetchBots, fetchSubscription]);

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

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const tierColor = tier === 'enterprise' ? 'secondary' : tier === 'pro' ? 'primary' : 'default';

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* ── AppBar ── */}
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <SmartToy sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="h6" fontWeight={700} sx={{ flexGrow: 1 }}>
            BotForge
          </Typography>
          <Chip label={tier.toUpperCase()} color={tierColor} size="small" sx={{ mr: 1 }} />
          {tier === 'free' && (
            <Button size="small" startIcon={<Upgrade />} onClick={() => navigate('/pricing')} sx={{ mr: 1 }}>
              Upgrade
            </Button>
          )}
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
            <MenuItem onClick={() => { setAnchorEl(null); navigate('/billing'); }}>
              <CreditCard fontSize="small" sx={{ mr: 1 }} /> Billing
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

      <Box sx={{ maxWidth: 1200, mx: 'auto', p: 3 }}>

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
          <OnboardingCard botList={botList} onAddBot={() => setAddOpen(true)} navigate={navigate} />
        )}

        {/* ── Header row ── */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Box>
            <Typography variant="h5" fontWeight={700}>My Bots</Typography>
            <Typography variant="caption" color="text.secondary">
              {botCount} / {maxBots} bots · {tier} plan
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setAddOpen(true)}
            disabled={atLimit}
          >
            Add Bot
          </Button>
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
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}>
            <CircularProgress />
          </Box>
        ) : botList.length === 0 ? (
          <Card sx={{ textAlign: 'center', py: 8, px: 3 }}>
            <SmartToy sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
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
        ) : (
          <Grid container spacing={2}>
            {botList.map((bot) => (
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
                      <Chip
                        label={bot.is_active ? 'Active' : 'Stopped'}
                        color={bot.is_active ? 'success' : 'default'}
                        size="small"
                      />
                    </Box>
                    <Typography variant="caption" color="text.disabled">
                      {bot.group_count ?? 0} group{bot.group_count !== 1 ? 's' : ''}
                    </Typography>
                  </CardContent>
                  <CardActions sx={{ px: 2, pb: 2, gap: 0.5 }}>
                    <Button size="small" startIcon={<Settings />} onClick={() => navigate(`/bot/${bot.id}`)}>
                      Groups
                    </Button>
                    <Button size="small" startIcon={<BarChart />} onClick={() => navigate(`/analytics/${bot.id}`)}>
                      Analytics
                    </Button>
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
            ))}
          </Grid>
        )}

        {/* ── Upgrade CTA for free users with bots ── */}
        {!loading && tier === 'free' && botList.length > 0 && (
          <Card sx={{ mt: 3, background: 'linear-gradient(135deg, #1565c0 0%, #7c4dff 100%)', border: 'none' }}>
            <CardContent sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2, p: 3 }}>
              <Box>
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
                sx={{ bgcolor: 'white', color: 'primary.main', fontWeight: 700, '&:hover': { bgcolor: '#f0f0f0' } }}
              >
                Upgrade to Pro
              </Button>
            </CardContent>
          </Card>
        )}

        {/* ── Invite section ── */}
        {!loading && user.id && <InviteCard userId={user.id} />}

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
