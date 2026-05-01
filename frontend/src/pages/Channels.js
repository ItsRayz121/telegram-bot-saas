import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, Grid,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  CircularProgress, Alert, Avatar, IconButton, Tooltip, Stack,
} from '@mui/material';
import {
  Campaign, Add, Refresh, Delete, Analytics, People,
  Visibility, ThumbUp, OpenInNew, CheckCircle, Warning,
  Handshake, HourglassEmpty, Cancel,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { channels as chApi, directory as dirApi } from '../services/api';

const OWNER_EMAIL = 'fazalelahi5577@gmail.com';

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
  // Temporarily hidden for future reactivation: channel tracking list & add dialog
  // const [list, setList] = useState([]);
  // const [loading, setLoading] = useState(true);
  // const [dialogOpen, setDialogOpen] = useState(false);

  const [myListings, setMyListings] = useState([]);
  const [listingsLoading, setListingsLoading] = useState(true);
  const [listDialogOpen, setListDialogOpen] = useState(false);

  // Load current user for admin check
  const [currentUser, setCurrentUser] = useState(null);
  useEffect(() => {
    const stored = localStorage.getItem('user');
    if (stored) {
      try { setCurrentUser(JSON.parse(stored)); } catch {}
    }
  }, []);
  const isAdminOrOwner = currentUser?.is_admin || currentUser?.email === OWNER_EMAIL;

  useEffect(() => {
    // Temporarily hidden for future reactivation: channel tracking fetch
    // chApi.list().then(r => setList(r.data)).catch(() => {}).finally(() => setLoading(false));

    dirApi.mine()
      .then(r => setMyListings(r.data || []))
      .catch(() => {})
      .finally(() => setListingsLoading(false));
  }, []);

  // Temporarily hidden for future reactivation
  // const handleAdded = (ch) => setList(prev => [ch, ...prev]);
  // const handleDelete = (id) => setList(prev => prev.filter(c => c.id !== id));
  // const handleRefresh = (updated) => setList(prev => prev.map(c => c.id === updated.id ? updated : c));

  const channelListings = myListings.filter(l => l.listing_type === 'channel');

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 960, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3, flexWrap: 'wrap', gap: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Campaign sx={{ fontSize: 28, color: 'primary.main' }} />
          <Box>
            <Typography variant="h5" fontWeight={700}>Channels</Typography>
            <Typography variant="caption" color="text.secondary">
              Manage your channel marketplace listings
            </Typography>
          </Box>
        </Box>
        {/* Temporarily hidden for future reactivation: Add Channel button
        <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)}>
          Add Channel
        </Button> */}
      </Box>

      {/* Temporarily hidden for future reactivation: channel analytics list & empty state
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
      )} */}

      {/* ── Admin/Owner: Listing Status Panel ─────────────────────────────── */}
      {isAdminOrOwner && !listingsLoading && channelListings.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" color="text.secondary" mb={1.5} fontWeight={600}>
            Your Channel Listings
          </Typography>
          <Stack spacing={1.5}>
            {channelListings.map(l => (
              <ListingStatusRow key={l.id} listing={l} />
            ))}
          </Stack>
        </Box>
      )}

      {/* ── Marketplace listing card ──────────────────────────────────────── */}
      <MarketplaceListingCard onList={() => setListDialogOpen(true)} />

      {/* ── DirectorySubmit inline dialog ─────────────────────────────────── */}
      <Dialog open={listDialogOpen} onClose={() => setListDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Handshake sx={{ color: 'secondary.light' }} />
          List Your Channel in Telegizer Marketplace
        </DialogTitle>
        <DialogContent dividers sx={{ p: 0 }}>
          {/* DirectorySubmit renders its own full UI — we embed it here */}
          <Box sx={{ p: 2 }}>
            <DirectorySubmitInline
              onDone={() => {
                setListDialogOpen(false);
                dirApi.mine().then(r => setMyListings(r.data || [])).catch(() => {});
                toast.success('Your channel listing was submitted!');
              }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setListDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Temporarily hidden for future reactivation: AddChannelDialog
      <AddChannelDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onAdded={handleAdded}
      /> */}
    </Box>
  );
}

// ── Marketplace listing card ──────────────────────────────────────────────────
function MarketplaceListingCard({ onList }) {
  return (
    <Card
      sx={{
        mt: 4,
        border: '1px dashed',
        borderColor: 'rgba(124,58,237,0.4)',
        bgcolor: 'rgba(124,58,237,0.04)',
        position: 'relative',
        overflow: 'visible',
      }}
    >
      {/* Coming Soon badge — Temporarily hidden for future reactivation when marketplace goes live
      <Chip label="Coming Soon" size="small" sx={{ position: 'absolute', top: -10, right: 16,
        bgcolor: 'rgba(124,58,237,0.85)', color: '#fff', fontWeight: 700, fontSize: '0.68rem',
        letterSpacing: '0.05em', height: 20 }} /> */}

      <CardContent sx={{ p: 2.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
          <Box
            sx={{
              width: 48, height: 48, borderRadius: '50%',
              bgcolor: 'rgba(124,58,237,0.15)', border: '1px solid rgba(124,58,237,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}
          >
            <Handshake sx={{ fontSize: 24, color: 'secondary.light' }} />
          </Box>

          <Box sx={{ flex: 1, minWidth: 200 }}>
            <Typography fontWeight={700} fontSize="1rem" mb={0.5}>
              List Your Channel in Telegizer Marketplace
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={1.5}>
              Future collaborations, sponsorships, and partnership opportunities.
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap">
              {['Sponsorships', 'Collaborations', 'Partnerships'].map(tag => (
                <Chip key={tag} label={tag} size="small" variant="outlined"
                  sx={{ height: 20, fontSize: '0.65rem', borderColor: 'rgba(124,58,237,0.3)', color: 'secondary.light' }} />
              ))}
            </Stack>
          </Box>

          <Button
            variant="outlined"
            startIcon={<Handshake />}
            onClick={onList}
            sx={{
              borderColor: 'rgba(124,58,237,0.5)',
              color: 'secondary.light',
              whiteSpace: 'nowrap',
              '&:hover': { borderColor: 'secondary.light', bgcolor: 'rgba(124,58,237,0.1)' },
            }}
          >
            List My Channel
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Listing status badge helper ───────────────────────────────────────────────
const STATUS_MAP = {
  pending:  { label: 'Pending Review', color: 'warning',  icon: <HourglassEmpty sx={{ fontSize: 14 }} /> },
  approved: { label: 'Approved',       color: 'success',  icon: <CheckCircle sx={{ fontSize: 14 }} /> },
  rejected: { label: 'Rejected',       color: 'error',    icon: <Cancel sx={{ fontSize: 14 }} /> },
};

function ListingStatusRow({ listing }) {
  const s = STATUS_MAP[listing.status] || STATUS_MAP.pending;
  return (
    <Card variant="outlined" sx={{ p: 0 }}>
      <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          <Campaign sx={{ color: 'secondary.light', fontSize: 18, flexShrink: 0 }} />
          <Typography variant="body2" fontWeight={600} sx={{ flex: 1 }}>
            {listing.title}
          </Typography>
          <Chip
            icon={s.icon}
            label={s.label}
            color={s.color}
            size="small"
            sx={{ height: 22, fontSize: '0.68rem', fontWeight: 700 }}
          />
        </Box>
        {listing.status === 'rejected' && listing.rejection_reason && (
          <Typography variant="caption" color="error.light" sx={{ mt: 0.5, display: 'block', pl: 4 }}>
            Reason: {listing.rejection_reason}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

// ── Inline DirectorySubmit for modal embedding ────────────────────────────────
// Reuses existing dirApi.create — no new backend logic.
function DirectorySubmitInline({ onDone }) {
  const navigate = useNavigate();
  const [channels, setChannels] = useState([]);
  const [myListings, setMyListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [form, setForm] = useState({
    channel_id: '', title: '', description: '', category: '',
    language: 'English', country: 'Global', telegram_link: '',
  });

  const CATEGORIES = [
    'Technology & Dev', 'Crypto & Web3', 'News & Politics',
    'Business & Finance', 'Education & Learning', 'Entertainment',
    'Gaming', 'Health & Wellness', 'Sports', 'Art & Design', 'Other',
  ];

  useEffect(() => {
    Promise.all([chApi.list(), dirApi.mine()])
      .then(([chRes, mineRes]) => {
        setChannels(chRes.data || []);
        setMyListings(mineRes.data || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const set = (field, val) => setForm(prev => ({ ...prev, [field]: val }));

  const handleChannelSelect = (id) => {
    set('channel_id', id);
    const ch = channels.find(c => c.id === id);
    if (ch) {
      set('title', ch.title);
      if (ch.username) set('telegram_link', `https://t.me/${ch.username}`);
    }
  };

  const isAlreadyListed = (id) =>
    myListings.some(l => String(l.channel_id) === String(id));

  const handleSubmit = async () => {
    if (!form.channel_id) { toast.error('Select a channel'); return; }
    if (!form.category)   { toast.error('Select a category'); return; }
    if (!form.telegram_link) { toast.error('Enter a Telegram link'); return; }
    setSubmitting(true);
    try {
      await dirApi.create({ ...form, listing_type: 'channel' });
      setDone(true);
    } catch (e) {
      toast.error(e.response?.data?.error || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <Box sx={{ py: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  if (done) return (
    <Box sx={{ py: 4, textAlign: 'center' }}>
      <CheckCircle sx={{ fontSize: 56, color: 'success.main', mb: 1.5 }} />
      <Typography variant="h6" fontWeight={700} gutterBottom>Listing submitted!</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Your channel is under review. You'll see the status update here.
      </Typography>
      <Button variant="contained" onClick={onDone}>Done</Button>
    </Box>
  );

  return (
    <Stack spacing={2.5}>
      {channels.length === 0 ? (
        <Alert severity="info">
          You don't have any channels tracked yet.{' '}
          <Button size="small" onClick={() => navigate('/channels')}>Add a channel first</Button>
        </Alert>
      ) : (
        <TextField
          select
          fullWidth
          label="Select your channel"
          value={form.channel_id}
          onChange={e => handleChannelSelect(e.target.value)}
          SelectProps={{ native: false }}
        >
          {channels.map(ch => (
            <option key={ch.id} value={ch.id} disabled={isAlreadyListed(ch.id)} style={{ padding: 8 }}>
              {ch.title}{isAlreadyListed(ch.id) ? ' (Already listed)' : ''}
            </option>
          ))}
        </TextField>
      )}

      <TextField fullWidth label="Title" value={form.title} onChange={e => set('title', e.target.value)} />
      <TextField fullWidth multiline rows={3} label="Description (optional)"
        value={form.description} onChange={e => set('description', e.target.value)} />

      <TextField select fullWidth label="Category" value={form.category}
        onChange={e => set('category', e.target.value)} SelectProps={{ native: false }}>
        {CATEGORIES.map(c => <option key={c} value={c} style={{ padding: 8 }}>{c}</option>)}
      </TextField>

      <TextField fullWidth label="Telegram join link" placeholder="https://t.me/mychannel"
        value={form.telegram_link} onChange={e => set('telegram_link', e.target.value)} />

      <Button variant="contained" size="large" startIcon={<Handshake />}
        onClick={handleSubmit} disabled={submitting || channels.length === 0}>
        {submitting ? <CircularProgress size={20} /> : 'Submit Listing'}
      </Button>
    </Stack>
  );
}
