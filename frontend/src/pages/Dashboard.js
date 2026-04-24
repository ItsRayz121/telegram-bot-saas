import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  CardActions, Grid, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, IconButton, Chip, CircularProgress, Tooltip, Menu, MenuItem,
  Avatar, LinearProgress, Alert,
} from '@mui/material';
import {
  Add, Delete, Settings, BarChart, SmartToy, AccountCircle,
  PowerSettingsNew, Upgrade, CheckCircle,
} from '@mui/icons-material';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { bots, auth, billing } from '../services/api';

const MAX_BOTS = { free: 1, pro: 5, enterprise: 50 };

function safeParseUser() {
  try {
    return JSON.parse(localStorage.getItem('user') || '{}');
  } catch {
    return {};
  }
}

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
    } catch { /* ignore — subscription chip just won't show expiry */ }
  }, []);

  useEffect(() => {
    refreshUser();
    fetchBots();
    fetchSubscription();
  }, [refreshUser, fetchBots, fetchSubscription]);

  // Show payment success banner when returning from checkout
  useEffect(() => {
    if (searchParams.get('payment') === 'success') {
      toast.success('Payment received! Your plan will be upgraded within a few minutes.');
    }
  }, [searchParams]);

  const tier = user.subscription_tier || 'free';
  const maxBots = MAX_BOTS[tier] ?? 1;
  const botCount = botList.length;
  const atLimit = botCount >= maxBots;

  const handleAddBot = async () => {
    if (!newToken.trim()) return;
    if (atLimit) {
      toast.error(`You've reached the ${maxBots} bot limit on your ${tier} plan. Upgrade to add more.`);
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
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <SmartToy sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="h6" fontWeight={700} sx={{ flexGrow: 1 }}>
            BotForge
          </Typography>
          <Chip
            label={tier.toUpperCase()}
            color={tierColor}
            size="small"
            sx={{ mr: 1 }}
          />
          {tier === 'free' && (
            <Button
              size="small"
              startIcon={<Upgrade />}
              onClick={() => navigate('/pricing')}
              sx={{ mr: 1 }}
            >
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
            {tier !== 'enterprise' && (
              <MenuItem onClick={() => { setAnchorEl(null); navigate('/pricing'); }}>
                Upgrade Plan
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
        {/* Subscription expiry warning */}
        {subscription?.is_expired && (
          <Alert severity="warning" sx={{ mb: 2 }} action={
            <Button size="small" color="warning" onClick={() => navigate('/pricing')}>Renew</Button>
          }>
            Your {tier} subscription has expired. Renew to restore access to paid features.
          </Alert>
        )}

        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Box>
            <Typography variant="h5" fontWeight={600}>My Bots</Typography>
            <Typography variant="caption" color="text.secondary">
              {botCount} / {maxBots} bots used
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

        {/* Bot limit progress */}
        <Box sx={{ mb: 3 }}>
          <LinearProgress
            variant="determinate"
            value={(botCount / maxBots) * 100}
            color={atLimit ? 'error' : botCount / maxBots >= 0.8 ? 'warning' : 'primary'}
            sx={{ height: 4, borderRadius: 2 }}
          />
          {atLimit && tier !== 'enterprise' && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.75 }}>
              <Typography variant="caption" color="error.main">
                Bot limit reached.
              </Typography>
              <Button size="small" variant="text" color="primary" sx={{ p: 0, minWidth: 0, fontSize: 12 }} onClick={() => navigate('/pricing')}>
                Upgrade to add more →
              </Button>
            </Box>
          )}
        </Box>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}>
            <CircularProgress />
          </Box>
        ) : botList.length === 0 ? (
          <Card sx={{ textAlign: 'center', py: 8 }}>
            <SmartToy sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" mb={1}>No bots yet</Typography>
            <Typography variant="body2" color="text.disabled" mb={1}>
              Add your first Telegram bot to get started
            </Typography>
            <Typography variant="caption" color="text.disabled" display="block" mb={3}>
              Get a bot token from @BotFather on Telegram, then paste it below.
            </Typography>
            <Button variant="contained" startIcon={<Add />} onClick={() => setAddOpen(true)}>
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
                        <Typography variant="subtitle1" fontWeight={600} noWrap>
                          {bot.bot_name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" noWrap>
                          @{bot.bot_username}
                        </Typography>
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

        {/* Quick start guide for new users */}
        {!loading && botList.length === 0 && (
          <Card sx={{ mt: 3, p: 1 }}>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={600} mb={2}>Quick Start Guide</Typography>
              {[
                { done: false, text: 'Create a bot via @BotFather on Telegram' },
                { done: false, text: 'Copy the bot token and add it here' },
                { done: false, text: 'Add your bot as admin to your Telegram group' },
                { done: false, text: 'The group will appear automatically in your dashboard' },
                { done: false, text: 'Open Group Settings to configure AutoMod, scheduling, and more' },
              ].map((step, i) => (
                <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                  <CheckCircle fontSize="small" color={step.done ? 'success' : 'disabled'} />
                  <Typography variant="body2" color={step.done ? 'text.primary' : 'text.secondary'}>
                    {step.text}
                  </Typography>
                </Box>
              ))}
            </CardContent>
          </Card>
        )}
      </Box>

      {/* Add Bot Dialog */}
      <Dialog open={addOpen} onClose={() => { setAddOpen(false); setNewToken(''); }} maxWidth="sm" fullWidth>
        <DialogTitle>Add Telegram Bot</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            1. Open Telegram and message <strong>@BotFather</strong><br />
            2. Send <code>/newbot</code> and follow the steps<br />
            3. Copy the token it gives you and paste below
          </Typography>
          <TextField
            fullWidth
            label="Bot Token"
            value={newToken}
            onChange={(e) => setNewToken(e.target.value)}
            placeholder="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
            helperText="The token from @BotFather (e.g. 123456:ABC-DEF...)"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setAddOpen(false); setNewToken(''); }}>Cancel</Button>
          <Button variant="contained" onClick={handleAddBot} disabled={adding || !newToken.trim()}>
            {adding ? <CircularProgress size={20} color="inherit" /> : 'Add Bot'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Bot Dialog */}
      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)}>
        <DialogTitle>Delete Bot</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>{selectedBot?.bot_name}</strong>? This will remove all
            associated groups, members, and settings. This action cannot be undone.
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
