import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  CardActions, Grid, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, IconButton, Chip, CircularProgress, Tooltip, Menu, MenuItem,
  Avatar,
} from '@mui/material';
import {
  Add, Delete, Settings, BarChart, SmartToy, AccountCircle,
  MoreVert, PowerSettingsNew, CreditCard,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { bots, auth } from '../services/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const [botList, setBotList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedBot, setSelectedBot] = useState(null);
  const [newToken, setNewToken] = useState('');
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [anchorEl, setAnchorEl] = useState(null);
  const [user, setUser] = useState(JSON.parse(localStorage.getItem('user') || '{}'));

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
    } catch {
      // silently ignore
    }
  }, []);

  useEffect(() => {
    refreshUser();
    fetchBots();
  }, [refreshUser, fetchBots]);

  const handleAddBot = async () => {
    if (!newToken.trim()) return;
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

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <SmartToy sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="h6" fontWeight={700} sx={{ flexGrow: 1 }}>
            BotForge
          </Typography>
          <Chip
            label={user.subscription_tier?.toUpperCase() || 'FREE'}
            color={user.subscription_tier === 'enterprise' ? 'secondary' : user.subscription_tier === 'pro' ? 'primary' : 'default'}
            size="small"
            sx={{ mr: 1 }}
          />
          <Button startIcon={<CreditCard />} onClick={() => navigate('/pricing')} sx={{ mr: 1 }}>
            Upgrade
          </Button>
          <IconButton onClick={(e) => setAnchorEl(e.currentTarget)}>
            <AccountCircle />
          </IconButton>
          <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
            <MenuItem disabled>
              <Typography variant="body2">{user.email}</Typography>
            </MenuItem>
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
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h5" fontWeight={600}>My Bots</Typography>
          <Button variant="contained" startIcon={<Add />} onClick={() => setAddOpen(true)}>
            Add Bot
          </Button>
        </Box>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}>
            <CircularProgress />
          </Box>
        ) : botList.length === 0 ? (
          <Card sx={{ textAlign: 'center', py: 8 }}>
            <SmartToy sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" mb={1}>
              No bots yet
            </Typography>
            <Typography variant="body2" color="text.disabled" mb={3}>
              Add your first Telegram bot to get started
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
                  </CardContent>
                  <CardActions sx={{ px: 2, pb: 2, gap: 0.5 }}>
                    <Button
                      size="small"
                      startIcon={<Settings />}
                      onClick={() => navigate(`/bot/${bot.id}`)}
                    >
                      Groups
                    </Button>
                    <Button
                      size="small"
                      startIcon={<BarChart />}
                      onClick={() => navigate(`/analytics/${bot.id}`)}
                    >
                      Analytics
                    </Button>
                    <Box sx={{ flexGrow: 1 }} />
                    <Tooltip title={bot.is_active ? 'Stop bot' : 'Start bot'}>
                      <IconButton size="small" onClick={() => handleToggle(bot)}>
                        <PowerSettingsNew fontSize="small" color={bot.is_active ? 'success' : 'disabled'} />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete bot">
                      <IconButton
                        size="small"
                        onClick={() => { setSelectedBot(bot); setDeleteOpen(true); }}
                      >
                        <Delete fontSize="small" color="error" />
                      </IconButton>
                    </Tooltip>
                  </CardActions>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Box>

      <Dialog open={addOpen} onClose={() => { setAddOpen(false); setNewToken(''); }} maxWidth="sm" fullWidth>
        <DialogTitle>Add Telegram Bot</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Create a bot via @BotFather on Telegram and paste the token below.
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
