import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Chip, IconButton, CircularProgress,
  Alert, Stack, Tooltip, Select, MenuItem, FormControl, InputLabel, Button,
} from '@mui/material';
import {
  VideoCall, Close, OpenInNew, Refresh, CalendarMonth,
} from '@mui/icons-material';
import { assistant as assistantApi, telegramGroups as tgApi } from '../services/api';
import { toast } from 'react-toastify';

const PLATFORM_META = {
  zoom:        { label: 'Zoom',        color: '#2D8CFF' },
  meet:        { label: 'Google Meet', color: '#34A853' },
  teams:       { label: 'Teams',       color: '#6264A7' },
  calendly:    { label: 'Calendly',    color: '#006BFF' },
  webex:       { label: 'Webex',       color: '#00BEF0' },
  gotomeeting: { label: 'GoTo',        color: '#F56600' },
  other:       { label: 'Meeting',     color: '#9E9E9E' },
};

export default function AssistantMeetingLinks() {
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [groups, setGroups] = useState([]);
  const [filterGroup, setFilterGroup] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterGroup) params.group_id = filterGroup;
      const { data } = await assistantApi.getMeetingLinks(params);
      setLinks(data.links || []);
    } catch {
      toast.error('Failed to load meeting links.');
    } finally {
      setLoading(false);
    }
  }, [filterGroup]);

  useEffect(() => {
    tgApi.getGroups().then(r => setGroups(r.data?.groups || [])).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const dismiss = async (id) => {
    try {
      await assistantApi.dismissMeetingLink(id);
      setLinks(prev => prev.filter(l => l.id !== id));
    } catch {
      toast.error('Could not dismiss link.');
    }
  };

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 760, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <VideoCall sx={{ fontSize: 26, color: 'primary.main' }} />
        <Typography variant="h5" fontWeight={700}>Meeting Links</Typography>
      </Box>
      <Typography color="text.secondary" fontSize="0.88rem" mb={2.5}>
        Video call and scheduling links captured automatically from your groups.
      </Typography>

      <Box sx={{ display: 'flex', gap: 1.5, mb: 2.5, flexWrap: 'wrap', alignItems: 'center' }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel>All Groups</InputLabel>
          <Select value={filterGroup} label="All Groups" onChange={e => setFilterGroup(e.target.value)}>
            <MenuItem value="">All Groups</MenuItem>
            {groups.map(g => (
              <MenuItem key={g.telegram_group_id} value={g.telegram_group_id}>{g.name || g.telegram_group_id}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <Button size="small" startIcon={<Refresh fontSize="small" />} onClick={load} disabled={loading}>
          Refresh
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={28} /></Box>
      ) : links.length === 0 ? (
        <Card sx={{ textAlign: 'center', py: 6 }}>
          <CalendarMonth sx={{ fontSize: 44, color: 'text.disabled', mb: 1.5 }} />
          <Typography fontWeight={600} mb={0.5}>No meeting links yet</Typography>
          <Typography color="text.secondary" fontSize="0.85rem">
            When a Zoom, Meet, Teams, or Calendly link is shared in a group, it appears here automatically.
          </Typography>
        </Card>
      ) : (
        <Stack spacing={1.5}>
          {links.map(link => {
            const meta = PLATFORM_META[link.platform] || PLATFORM_META.other;
            return (
              <Card key={link.id} variant="outlined">
                <CardContent sx={{ py: '12px !important', px: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5, flexWrap: 'wrap' }}>
                        <Chip
                          label={meta.label}
                          size="small"
                          sx={{ bgcolor: meta.color, color: '#fff', fontSize: '0.68rem', height: 20 }}
                        />
                        {link.group_title && (
                          <Typography fontSize="0.75rem" color="text.secondary">{link.group_title}</Typography>
                        )}
                        <Typography fontSize="0.72rem" color="text.disabled" sx={{ ml: 'auto' }}>
                          {new Date(link.captured_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </Typography>
                      </Box>
                      <Typography
                        fontSize="0.82rem"
                        color="primary.main"
                        noWrap
                        sx={{ cursor: 'pointer', '&:hover': { textDecoration: 'underline' } }}
                        onClick={() => window.open(link.url, '_blank', 'noopener')}
                      >
                        {link.url}
                      </Typography>
                      {link.context_text && (
                        <Typography fontSize="0.75rem" color="text.secondary" mt={0.5} noWrap>
                          "{link.context_text}"
                        </Typography>
                      )}
                      {link.posted_by_username && (
                        <Typography fontSize="0.72rem" color="text.disabled" mt={0.25}>
                          @{link.posted_by_username}
                        </Typography>
                      )}
                    </Box>
                    <Box sx={{ display: 'flex', gap: 0.5, flexShrink: 0 }}>
                      <Tooltip title="Open link">
                        <IconButton size="small" onClick={() => window.open(link.url, '_blank', 'noopener')}>
                          <OpenInNew fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Dismiss">
                        <IconButton size="small" color="default" onClick={() => dismiss(link.id)}>
                          <Close fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            );
          })}
        </Stack>
      )}
    </Box>
  );
}
