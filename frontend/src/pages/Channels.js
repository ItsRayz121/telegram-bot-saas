import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, Grid,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  CircularProgress, Alert, Avatar, IconButton, Tooltip, Stack,
} from '@mui/material';
import {
  Campaign, Add, Refresh, Delete, Analytics, People,
  Visibility, ThumbUp, OpenInNew, CheckCircle, Warning,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { channels as chApi } from '../services/api';

function StatusChip({ status }) {
  const map = {
    active: { color: 'success', label: 'Active' },
    no_admin: { color: 'warning', label: 'Bot not admin' },
    pending: { color: 'default', label: 'Pending' },
    error: { color: 'error', label: 'Error' },
  };
  const { color, label } = map[status] || map.pending;
  return <Chip label={label} color={color} size="small" sx={{ height: 20, fontSize: '0.65rem' }} />;
}

function ChannelCard({ channel, onDelete, onRefresh, onClick }) {
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async (e) => {
    e.stopPropagation();
    setRefreshing(true);
    try {
      const res = await chApi.refresh(channel.id);
      onRefresh(res.data);
      toast.success('Stats refreshed');
    } catch {
      toast.error('Refresh failed');
    } finally {
      setRefreshing(false);
    }
  };

  const handleDelete = async (e) => {
    e.stopPropagation();
    if (!window.confirm(`Remove "${channel.title}" from tracking?`)) return;
    try {
      await chApi.delete(channel.id);
      onDelete(channel.id);
      toast.success('Channel removed');
    } catch {
      toast.error('Delete failed');
    }
  };

  return (
    <Card sx={{ cursor: 'pointer', '&:hover': { borderColor: 'primary.main' } }} onClick={onClick}>
      <CardContent sx={{ p: 2.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5, mb: 2 }}>
          <Avatar sx={{ bgcolor: 'primary.main', width: 42, height: 42, fontSize: '1.1rem' }}>
            {channel.title[0]?.toUpperCase()}
          </Avatar>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <Typography fontWeight={700} noWrap>{channel.title}</Typography>
              <StatusChip status={channel.bot_status} />
            </Box>
            {channel.username && (
              <Typography variant="caption" color="text.secondary">@{channel.username}</Typography>
            )}
          </Box>
          <Box sx={{ display: 'flex', gap: 0.5 }}>
            <Tooltip title="Refresh stats">
              <IconButton size="small" onClick={handleRefresh} disabled={refreshing}>
                {refreshing ? <CircularProgress size={16} /> : <Refresh fontSize="small" />}
              </IconButton>
            </Tooltip>
            <Tooltip title="Remove">
              <IconButton size="small" onClick={handleDelete} color="error">
                <Delete fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        <Grid container spacing={1.5}>
          {[
            { icon: <People sx={{ fontSize: 15 }} />, label: 'Members', value: (channel.member_count || 0).toLocaleString() },
            { icon: <Visibility sx={{ fontSize: 15 }} />, label: 'Avg Views', value: Math.round(channel.avg_views || 0).toLocaleString() },
            { icon: <ThumbUp sx={{ fontSize: 15 }} />, label: 'Engagement', value: `${(channel.engagement_rate || 0).toFixed(2)}%` },
            { icon: <Analytics sx={{ fontSize: 15 }} />, label: 'Posts tracked', value: channel.post_count || 0 },
          ].map(s => (
            <Grid item xs={6} key={s.label}>
              <Box sx={{ bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 1.5, p: 1, textAlign: 'center' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5, color: 'text.secondary', mb: 0.25 }}>
                  {s.icon}
                  <Typography variant="caption" color="text.secondary">{s.label}</Typography>
                </Box>
                <Typography variant="body2" fontWeight={700}>{s.value}</Typography>
              </Box>
            </Grid>
          ))}
        </Grid>

        {channel.tcs_score != null && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1.5, pt: 1.5, borderTop: '1px solid rgba(255,255,255,0.07)' }}>
            <Typography variant="caption" color="text.secondary">TCS Score:</Typography>
            <Chip
              label={`${channel.tcs_score}/100 · ${channel.tcs_grade}`}
              size="small"
              color={channel.tcs_score >= 65 ? 'success' : channel.tcs_score >= 40 ? 'warning' : 'error'}
              sx={{ height: 18, fontSize: '0.63rem', fontWeight: 700 }}
            />
          </Box>
        )}
        {channel.bot_status === 'no_admin' && (
          <Alert severity="warning" icon={<Warning fontSize="small" />} sx={{ mt: 1.5, fontSize: '0.72rem', py: 0.5 }}>
            Add the bot as admin in your channel to capture posts automatically.
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

function AddChannelDialog({ open, onClose, onAdded }) {
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleAdd = async () => {
    if (!value.trim()) return;
    setLoading(true);
    setError('');
    try {
      const res = await chApi.add({ channel_id: value.trim() });
      onAdded(res.data);
      toast.success('Channel added!');
      onClose();
      setValue('');
    } catch (e) {
      setError(e.response?.data?.error || 'Could not add channel');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Channel</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Enter your channel's @username or link. The bot must be an admin in the channel
          to capture post analytics automatically.
        </Typography>
        <TextField
          fullWidth
          label="Channel @username or link"
          placeholder="@mychannel or https://t.me/mychannel"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleAdd()}
          autoFocus
        />
        {error && <Alert severity="error" sx={{ mt: 1.5 }}>{error}</Alert>}
        <Alert severity="info" icon={false} sx={{ mt: 2, fontSize: '0.75rem' }}>
          <strong>To enable live analytics:</strong> Add the Telegizer bot as an admin
          to your channel. It will then capture every post with views, reactions, and forwards.
        </Alert>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleAdd} disabled={loading || !value.trim()}>
          {loading ? <CircularProgress size={20} /> : 'Add Channel'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function Channels() {
  const navigate = useNavigate();
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => {
    chApi.list()
      .then(r => setList(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleAdded = (ch) => setList(prev => [ch, ...prev]);
  const handleDelete = (id) => setList(prev => prev.filter(c => c.id !== id));
  const handleRefresh = (updated) => setList(prev => prev.map(c => c.id === updated.id ? updated : c));

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 960, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3, flexWrap: 'wrap', gap: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Campaign sx={{ fontSize: 28, color: 'primary.main' }} />
          <Box>
            <Typography variant="h5" fontWeight={700}>Channels</Typography>
            <Typography variant="caption" color="text.secondary">
              Track analytics for your Telegram channels
            </Typography>
          </Box>
        </Box>
        <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)}>
          Add Channel
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ py: 6, textAlign: 'center' }}><CircularProgress /></Box>
      ) : list.length === 0 ? (
        <Card sx={{ textAlign: 'center', py: 6 }}>
          <CardContent>
            <Campaign sx={{ fontSize: 56, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" fontWeight={700} gutterBottom>No channels yet</Typography>
            <Typography variant="body2" color="text.secondary" mb={3} maxWidth={400} mx="auto">
              Add your Telegram channel to track views, reactions, member growth,
              and engagement rate for every post.
            </Typography>
            <Stack direction="row" spacing={1.5} justifyContent="center" flexWrap="wrap">
              <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)}>
                Add your first channel
              </Button>
              <Button variant="outlined" startIcon={<OpenInNew />}
                href="https://t.me/BotFather" target="_blank">
                Open BotFather
              </Button>
            </Stack>
            <Alert severity="info" icon={<CheckCircle fontSize="small" />}
              sx={{ mt: 3, textAlign: 'left', maxWidth: 480, mx: 'auto', fontSize: '0.75rem' }}>
              Tip: Make the bot an admin in your channel to automatically capture every post's analytics.
            </Alert>
          </CardContent>
        </Card>
      ) : (
        <Grid container spacing={2}>
          {list.map(ch => (
            <Grid item xs={12} sm={6} key={ch.id}>
              <ChannelCard
                channel={ch}
                onDelete={handleDelete}
                onRefresh={handleRefresh}
                onClick={() => navigate(`/channels/${ch.id}`)}
              />
            </Grid>
          ))}
        </Grid>
      )}

      <AddChannelDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onAdded={handleAdded}
      />
    </Box>
  );
}
