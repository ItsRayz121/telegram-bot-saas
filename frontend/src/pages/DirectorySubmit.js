import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField,
  Select, MenuItem, FormControl, InputLabel, CircularProgress,
  Alert, ToggleButton, ToggleButtonGroup, Divider, Chip, Stack,
} from '@mui/material';
import { Campaign, Groups, Explore, CheckCircle } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { directory as dirApi, channels as chApi } from '../services/api';
import api from '../services/api';

const CATEGORIES = [
  "Technology & Dev", "Crypto & Web3", "News & Politics",
  "Business & Finance", "Education & Learning", "Entertainment",
  "Gaming", "Health & Wellness", "Sports", "Art & Design", "Other",
];

const LANGUAGES = [
  "English", "Arabic", "Spanish", "Portuguese", "Russian",
  "Hindi", "Indonesian", "Turkish", "French", "German", "Other",
];

export default function DirectorySubmit() {
  const navigate = useNavigate();
  const [type, setType] = useState('channel');
  const [channels, setChannels] = useState([]);
  const [groups, setGroups] = useState([]);
  const [myListings, setMyListings] = useState([]);
  const [loadingData, setLoadingData] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const [form, setForm] = useState({
    channel_id: '',
    telegram_group_id: '',
    title: '',
    description: '',
    category: '',
    language: 'English',
    country: 'Global',
    telegram_link: '',
  });

  useEffect(() => {
    Promise.all([
      chApi.list(),
      api.get('/api/groups'),
      dirApi.mine(),
    ]).then(([chRes, grpRes, mineRes]) => {
      setChannels(chRes.data || []);
      setGroups(grpRes.data || []);
      setMyListings(mineRes.data || []);
    }).catch(() => {}).finally(() => setLoadingData(false));
  }, []);

  const set = (field, val) => setForm(prev => ({ ...prev, [field]: val }));

  // Auto-fill title when channel/group selected
  const handleChannelSelect = (id) => {
    set('channel_id', id);
    const ch = channels.find(c => c.id === id);
    if (ch) {
      set('title', ch.title);
      if (ch.username) set('telegram_link', `https://t.me/${ch.username}`);
    }
  };

  const handleGroupSelect = (id) => {
    set('telegram_group_id', id);
    const grp = groups.find(g => g.telegram_group_id === id);
    if (grp) set('title', grp.name || '');
  };

  const isAlreadyListed = (id, field) =>
    myListings.some(l => String(l[field]) === String(id));

  const handleSubmit = async () => {
    if (!form.category) { toast.error('Select a category'); return; }
    if (!form.telegram_link) { toast.error('Enter a Telegram join link'); return; }
    if (type === 'channel' && !form.channel_id) { toast.error('Select a channel'); return; }
    if (type === 'group' && !form.telegram_group_id) { toast.error('Select a group'); return; }

    setSubmitting(true);
    try {
      await dirApi.create({ ...form, listing_type: type });
      setDone(true);
      toast.success('Listed successfully!');
    } catch (e) {
      toast.error(e.response?.data?.error || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (loadingData) return <Box sx={{ py: 8, textAlign: 'center' }}><CircularProgress /></Box>;

  if (done) return (
    <Box sx={{ p: 4, maxWidth: 520, mx: 'auto', textAlign: 'center' }}>
      <CheckCircle sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
      <Typography variant="h5" fontWeight={700} gutterBottom>You're listed!</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Your community is now visible in the directory. It may take a few minutes to appear.
      </Typography>
      <Stack direction="row" spacing={1.5} justifyContent="center">
        <Button variant="contained" onClick={() => navigate('/directory')}>View Directory</Button>
        <Button variant="outlined" onClick={() => { setDone(false); setForm({ channel_id: '', telegram_group_id: '', title: '', description: '', category: '', language: 'English', country: 'Global', telegram_link: '' }); }}>
          List Another
        </Button>
      </Stack>
    </Box>
  );

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 680, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <Explore sx={{ fontSize: 28, color: 'primary.main' }} />
        <Box>
          <Typography variant="h5" fontWeight={700}>List Your Community</Typography>
          <Typography variant="caption" color="text.secondary">
            Get discovered by thousands of users and potential partners
          </Typography>
        </Box>
      </Box>

      <Card>
        <CardContent sx={{ p: 3 }}>
          {/* Type toggle */}
          <Typography variant="subtitle2" fontWeight={700} mb={1.5}>Community type</Typography>
          <ToggleButtonGroup
            value={type} exclusive size="small" sx={{ mb: 3 }}
            onChange={(_, v) => v && setType(v)}
          >
            <ToggleButton value="channel" sx={{ gap: 1 }}>
              <Campaign fontSize="small" /> Channel
            </ToggleButton>
            <ToggleButton value="group" sx={{ gap: 1 }}>
              <Groups fontSize="small" /> Group
            </ToggleButton>
          </ToggleButtonGroup>

          {/* Source selector */}
          {type === 'channel' ? (
            channels.length === 0 ? (
              <Alert severity="info" sx={{ mb: 3 }}>
                You don't have any channels tracked yet.{' '}
                <Button size="small" onClick={() => navigate('/channels')}>Add a channel first</Button>
              </Alert>
            ) : (
              <FormControl fullWidth sx={{ mb: 2 }}>
                <InputLabel>Select your channel</InputLabel>
                <Select value={form.channel_id} label="Select your channel"
                  onChange={e => handleChannelSelect(e.target.value)}>
                  {channels.map(ch => (
                    <MenuItem key={ch.id} value={ch.id} disabled={isAlreadyListed(ch.id, 'channel_id')}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {ch.title}
                        {isAlreadyListed(ch.id, 'channel_id') && <Chip label="Listed" size="small" sx={{ height: 16, fontSize: '0.6rem' }} />}
                        {ch.tcs_grade && <Chip label={`TCS ${ch.tcs_grade}`} color="success" size="small" sx={{ height: 16, fontSize: '0.6rem' }} />}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )
          ) : (
            groups.length === 0 ? (
              <Alert severity="info" sx={{ mb: 3 }}>
                You don't have any groups yet.{' '}
                <Button size="small" onClick={() => navigate('/groups')}>Add a group first</Button>
              </Alert>
            ) : (
              <FormControl fullWidth sx={{ mb: 2 }}>
                <InputLabel>Select your group</InputLabel>
                <Select value={form.telegram_group_id} label="Select your group"
                  onChange={e => handleGroupSelect(e.target.value)}>
                  {groups.map(g => (
                    <MenuItem key={g.telegram_group_id} value={g.telegram_group_id}
                      disabled={isAlreadyListed(g.telegram_group_id, 'telegram_group_id')}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {g.name}
                        {isAlreadyListed(g.telegram_group_id, 'telegram_group_id') && <Chip label="Listed" size="small" sx={{ height: 16, fontSize: '0.6rem' }} />}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )
          )}

          <Divider sx={{ my: 2 }} />

          {/* Listing details */}
          <Typography variant="subtitle2" fontWeight={700} mb={1.5}>Listing details</Typography>

          <TextField fullWidth label="Display title" value={form.title}
            onChange={e => set('title', e.target.value)} sx={{ mb: 2 }} />

          <TextField fullWidth multiline rows={3} label="Description"
            placeholder="What is this community about? Who should join?"
            value={form.description} onChange={e => set('description', e.target.value)} sx={{ mb: 2 }} />

          <TextField fullWidth label="Telegram invite link"
            placeholder="https://t.me/yourcommunity"
            value={form.telegram_link} onChange={e => set('telegram_link', e.target.value)} sx={{ mb: 2 }}
            helperText="Public join link — shown to everyone in the directory" />

          <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
            <FormControl sx={{ flex: 1, minWidth: 160 }}>
              <InputLabel>Category *</InputLabel>
              <Select value={form.category} label="Category *"
                onChange={e => set('category', e.target.value)}>
                {CATEGORIES.map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl sx={{ flex: 1, minWidth: 140 }}>
              <InputLabel>Language</InputLabel>
              <Select value={form.language} label="Language"
                onChange={e => set('language', e.target.value)}>
                {LANGUAGES.map(l => <MenuItem key={l} value={l}>{l}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>

          <TextField fullWidth label="Country / Region"
            placeholder="e.g. Pakistan, United States, Global"
            value={form.country} onChange={e => set('country', e.target.value)} sx={{ mb: 3 }} />

          <Alert severity="info" icon={false} sx={{ mb: 3, fontSize: '0.75rem' }}>
            Your listing will be visible publicly. TCS score (if computed) will be shown alongside your community
            to signal authenticity to potential members and partners.
          </Alert>

          <Button fullWidth variant="contained" size="large" onClick={handleSubmit}
            disabled={submitting}>
            {submitting ? <CircularProgress size={22} /> : 'Submit to Directory'}
          </Button>
        </CardContent>
      </Card>
    </Box>
  );
}
