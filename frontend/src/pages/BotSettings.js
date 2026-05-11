import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  CardActionArea, Grid, Chip, CircularProgress, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material';
import { ArrowBack, BarChart, Group, Settings, LinkOff } from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { bots } from '../services/api';

export default function BotSettings() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [bot, setBot] = useState(null);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);

  // Disconnect confirmation state
  const [disconnectTarget, setDisconnectTarget] = useState(null); // group object | null
  const [disconnecting, setDisconnecting] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [botRes, groupsRes] = await Promise.all([
        bots.get(id),
        bots.getGroups(id),
      ]);
      setBot(botRes.data.bot);
      setGroups(groupsRes.data.groups);
    } catch {
      toast.error('Failed to load bot data');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDisconnect = async () => {
    if (!disconnectTarget) return;
    setDisconnecting(true);
    try {
      await bots.disconnectGroup(id, disconnectTarget.id);
      toast.success(`"${disconnectTarget.group_name || 'Group'}" disconnected from ${bot?.bot_name || 'bot'}`);
      setDisconnectTarget(null);
      setGroups(prev => prev.filter(g => g.id !== disconnectTarget.id));
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to disconnect group');
    } finally {
      setDisconnecting(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate('/dashboard')} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          <Typography variant="h6" fontWeight={600} sx={{ flexGrow: 1 }}>
            {bot?.bot_name}
          </Typography>
          <Chip
            label={bot?.is_active ? 'Active' : 'Stopped'}
            color={bot?.is_active ? 'success' : 'default'}
            size="small"
          />
        </Toolbar>
      </AppBar>

      <Box sx={{ maxWidth: 1200, mx: 'auto', p: { xs: 2, md: 3 } }}>
        <Typography variant="h6" fontWeight={600} mb={2}>
          Groups ({groups.length})
        </Typography>

        {groups.length === 0 ? (
          <Card sx={{ textAlign: 'center', py: 8 }}>
            <Group sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" mb={1}>
              No groups yet
            </Typography>
            <Typography variant="body2" color="text.disabled">
              Add your bot to a Telegram group to manage it here.
            </Typography>
          </Card>
        ) : (
          <Grid container spacing={2}>
            {groups.map((group) => (
              <Grid item xs={12} sm={6} md={4} key={group.id}>
                <Card>
                  <CardActionArea onClick={() => navigate(`/bot/${id}/group/${group.id}`)}>
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 1 }}>
                        <Box
                          sx={{
                            width: 44, height: 44, borderRadius: 2,
                            bgcolor: 'primary.main', display: 'flex',
                            alignItems: 'center', justifyContent: 'center', mr: 1.5, flexShrink: 0,
                          }}
                        >
                          <Group />
                        </Box>
                        <Box>
                          <Typography variant="subtitle1" fontWeight={600}>
                            {group.group_name || 'Unknown Group'}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {group.member_count ?? 0} members
                          </Typography>
                        </Box>
                      </Box>

                      {/* Actions — three equal-width buttons in a single row */}
                      <Box sx={{ display: 'flex', gap: 1, mt: 0.5 }}>
                        <Button
                          size="small"
                          variant="contained"
                          startIcon={<Settings sx={{ fontSize: '0.95rem !important' }} />}
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/bot/${id}/group/${group.id}`);
                          }}
                          sx={{
                            flex: 1,
                            fontSize: '0.72rem',
                            fontWeight: 600,
                            letterSpacing: 0.2,
                            textTransform: 'none',
                            py: 0.75,
                            borderRadius: 1.5,
                            boxShadow: 'none',
                            '&:hover': { boxShadow: '0 2px 8px rgba(33,150,243,0.25)', transform: 'translateY(-1px)' },
                            transition: 'transform 0.15s, box-shadow 0.15s',
                          }}
                        >
                          Settings
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          startIcon={<BarChart sx={{ fontSize: '0.95rem !important' }} />}
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/bot/${id}/group/${group.id}/analytics`);
                          }}
                          sx={{
                            flex: 1,
                            fontSize: '0.72rem',
                            fontWeight: 600,
                            letterSpacing: 0.2,
                            textTransform: 'none',
                            py: 0.75,
                            borderRadius: 1.5,
                            '&:hover': { bgcolor: 'primary.main', color: '#fff', borderColor: 'primary.main', transform: 'translateY(-1px)' },
                            transition: 'transform 0.15s, background-color 0.15s, color 0.15s',
                          }}
                        >
                          Analytics
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          color="error"
                          startIcon={<LinkOff sx={{ fontSize: '0.95rem !important' }} />}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDisconnectTarget(group);
                          }}
                          sx={{
                            flex: 1,
                            fontSize: '0.72rem',
                            fontWeight: 600,
                            letterSpacing: 0.2,
                            textTransform: 'none',
                            py: 0.75,
                            borderRadius: 1.5,
                            '&:hover': { bgcolor: 'error.main', color: '#fff', borderColor: 'error.main', transform: 'translateY(-1px)' },
                            transition: 'transform 0.15s, background-color 0.15s, color 0.15s',
                          }}
                        >
                          Disconnect
                        </Button>
                      </Box>
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Box>

      {/* Disconnect confirmation dialog */}
      <Dialog
        open={!!disconnectTarget}
        onClose={() => !disconnecting && setDisconnectTarget(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Disconnect Group?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Disconnect <strong>{disconnectTarget?.group_name || 'this group'}</strong> from{' '}
            <strong>{bot?.bot_name || 'this bot'}</strong>?
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            The Telegram group will not be deleted. The bot will stop managing it from
            Telegizer, but it remains in the group on Telegram until you manually remove it.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDisconnectTarget(null)} disabled={disconnecting}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleDisconnect}
            disabled={disconnecting}
            startIcon={disconnecting ? <CircularProgress size={14} /> : <LinkOff />}
          >
            {disconnecting ? 'Disconnecting…' : 'Disconnect'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
