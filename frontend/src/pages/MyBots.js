import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Container, Typography, Button, Card, CardContent,
  Chip, CircularProgress, Alert, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, IconButton,
  Tooltip, Grid, Divider,
} from '@mui/material';
import {
  Add, SmartToy, Delete, Refresh, CheckCircle, ErrorOutline,
  OpenInNew,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { customBots } from '../services/api';

function StatusChip({ status }) {
  const map = {
    active: { label: 'Active', color: 'success' },
    inactive: { label: 'Inactive', color: 'warning' },
    error: { label: 'Error', color: 'error' },
  };
  const { label, color } = map[status] || { label: status, color: 'default' };
  return <Chip label={label} color={color} size="small" />;
}

export default function MyBots() {
  const [bots, setBots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ bot_token: '', bot_username: '' });
  const [adding, setAdding] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await customBots.list();
      setBots(res.data.bots || []);
    } catch {
      toast.error('Failed to load bots');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    if (!form.bot_token || !form.bot_username) return;
    setAdding(true);
    try {
      await customBots.add(form);
      toast.success('Custom bot connected!');
      setAddOpen(false);
      setForm({ bot_token: '', bot_username: '' });
      load();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to connect bot');
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await customBots.delete(deleteTarget.id);
      toast.success(`@${deleteTarget.bot_username} disconnected`);
      setDeleteTarget(null);
      load();
    } catch {
      toast.error('Failed to disconnect bot');
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', py: 4 }}>
      <Container maxWidth="lg">
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
          <Box>
            <Typography variant="h4" fontWeight={700}>My Bots</Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              Official shared bot + any custom bots you connect
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <IconButton onClick={load} disabled={loading}><Refresh /></IconButton>
            <Button variant="contained" startIcon={<Add />} onClick={() => setAddOpen(true)}>
              Connect Own Bot
            </Button>
          </Box>
        </Box>

        {/* Official bot card — always shown */}
        <Card sx={{ mb: 3, border: '1px solid', borderColor: 'success.dark', background: 'rgba(34,197,94,0.05)' }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <SmartToy sx={{ fontSize: 36, color: 'success.main' }} />
              <Box sx={{ flex: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="h6" fontWeight={700}>Official Telegizer Bot</Typography>
                  <Chip label="Shared" color="success" size="small" />
                </Box>
                <Typography variant="body2" color="text.secondary">
                  One shared bot serving all your groups automatically. No setup required.
                </Typography>
              </Box>
              <Button
                variant="outlined"
                size="small"
                endIcon={<OpenInNew />}
                href="https://t.me/telegizer_bot"
                target="_blank"
                rel="noreferrer"
              >
                Open Bot
              </Button>
            </Box>
          </CardContent>
        </Card>

        <Divider sx={{ mb: 3 }}>
          <Chip label="Custom Bots" size="small" />
        </Divider>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : bots.length === 0 ? (
          <Card sx={{ textAlign: 'center', py: 6 }}>
            <SmartToy sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" gutterBottom>No custom bots connected</Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              Pro/Enterprise users can connect their own bot token for white-label usage.
            </Typography>
            <Button variant="contained" startIcon={<Add />} onClick={() => setAddOpen(true)}>
              Connect Bot Token
            </Button>
          </Card>
        ) : (
          <Grid container spacing={2}>
            {bots.map((bot) => (
              <Grid item xs={12} md={6} key={bot.id}>
                <Card>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <Box>
                        <Typography variant="h6" fontWeight={600}>
                          {bot.bot_name || `@${bot.bot_username}`}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          @{bot.bot_username}
                        </Typography>
                      </Box>
                      <StatusChip status={bot.status} />
                    </Box>

                    <Divider sx={{ my: 1.5 }} />

                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" color="text.secondary">
                        {bot.linked_groups_count} group{bot.linked_groups_count !== 1 ? 's' : ''} linked
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Added {new Date(bot.created_at).toLocaleDateString()}
                      </Typography>
                    </Box>

                    <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
                      <Button
                        size="small"
                        variant="outlined"
                        href={`https://t.me/${bot.bot_username}`}
                        target="_blank"
                        rel="noreferrer"
                        endIcon={<OpenInNew />}
                        sx={{ flex: 1 }}
                      >
                        Open on Telegram
                      </Button>
                      <Tooltip title="Disconnect bot">
                        <IconButton size="small" color="error" onClick={() => setDeleteTarget(bot)}>
                          <Delete fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Container>

      {/* Add bot dialog */}
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Connect Your Own Bot</DialogTitle>
        <DialogContent sx={{ pt: '16px !important' }}>
          <Alert severity="info" sx={{ mb: 2 }}>
            Create a bot via <strong>@BotFather</strong> on Telegram, then paste the token below.
            Your token is encrypted and never exposed.
          </Alert>
          <TextField
            fullWidth
            label="Bot Token"
            value={form.bot_token}
            onChange={(e) => setForm({ ...form, bot_token: e.target.value.trim() })}
            placeholder="1234567890:AAAA..."
            type="password"
            sx={{ mb: 2 }}
          />
          <TextField
            fullWidth
            label="Bot Username"
            value={form.bot_username}
            onChange={(e) => setForm({ ...form, bot_username: e.target.value.trim().replace('@', '') })}
            placeholder="mybot"
            InputProps={{ startAdornment: <Typography color="text.secondary" mr={0.5}>@</Typography> }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleAdd}
            disabled={adding || !form.bot_token || !form.bot_username}
          >
            {adding ? <CircularProgress size={20} /> : 'Connect Bot'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Disconnect confirm */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>Disconnect Bot?</DialogTitle>
        <DialogContent>
          <Typography>
            Disconnect <strong>@{deleteTarget?.bot_username}</strong>? Groups using this bot will
            fall back to the official Telegizer bot.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDelete}>Disconnect</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
