import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton,
  Chip, Alert, Tooltip, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, FormControl, InputLabel, Select, MenuItem,
} from '@mui/material';
import { Add, Delete, ContentCopy, Link, Person, TrendingUp } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { invites } from '../services/api';

const TIME_FILTERS = [
  { value: '1d', label: 'Last 1 Day' },
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
  { value: 'all', label: 'All Time' },
];

export default function InviteLinks({ botId, groupId }) {
  const [links, setLinks] = useState([]);
  const [open, setOpen] = useState(false);
  const [timeFilter, setTimeFilter] = useState('all');
  const [form, setForm] = useState({ name: '', max_uses: '', expire_date: '' });

  const load = async () => {
    try {
      const res = await invites.list(botId, groupId, { time_filter: timeFilter });
      setLinks(res.data.invite_links || []);
    } catch { }
  };

  useEffect(() => { load(); }, [botId, groupId, timeFilter]);

  const handleCreate = async () => {
    if (!form.name.trim()) { toast.error('Name is required'); return; }
    try {
      await invites.create(botId, groupId, {
        name: form.name,
        max_uses: form.max_uses ? parseInt(form.max_uses) : null,
        expire_date: form.expire_date || null,
      });
      toast.success('Invite link created');
      setOpen(false);
      setForm({ name: '', max_uses: '', expire_date: '' });
      load();
    } catch (e) { toast.error(e.response?.data?.error || 'Failed to create invite link'); }
  };

  const handleRevoke = async (id) => {
    try {
      await invites.delete(botId, groupId, id);
      setLinks(prev => prev.map(l => l.id === id ? { ...l, is_active: false } : l));
      toast.success('Invite link revoked');
    } catch { toast.error('Failed to revoke'); }
  };

  const copyLink = (url) => {
    if (!url) { toast.error('Link not yet generated — bot may be offline'); return; }
    navigator.clipboard.writeText(url);
    toast.success('Copied to clipboard!');
  };

  const activeLinks = links.filter(l => l.is_active);
  const revokedLinks = links.filter(l => !l.is_active);

  const currentPeriodLabel = TIME_FILTERS.find(f => f.value === timeFilter)?.label || 'All Time';

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="h6" fontWeight={600}>Invite Links</Typography>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Time Period</InputLabel>
            <Select
              value={timeFilter}
              label="Time Period"
              onChange={e => setTimeFilter(e.target.value)}
            >
              {TIME_FILTERS.map(f => (
                <MenuItem key={f.value} value={f.value}>{f.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button variant="contained" startIcon={<Add />} onClick={() => setOpen(true)}>
            Create Link
          </Button>
        </Box>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        Create named invite links to track where new members come from. Join events are tracked automatically when the bot is online.
        Also use <strong>/invitelink [name]</strong> in the group.
      </Alert>

      {/* Summary stats */}
      {links.length > 0 && (
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={6} sm={3}>
            <Card variant="outlined">
              <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                <Typography variant="caption" color="text.secondary">Total Links</Typography>
                <Typography variant="h5" fontWeight={700}>{links.length}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={6} sm={3}>
            <Card variant="outlined">
              <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                <Typography variant="caption" color="text.secondary">Active</Typography>
                <Typography variant="h5" fontWeight={700} color="success.main">{activeLinks.length}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={6} sm={3}>
            <Card variant="outlined">
              <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                <Typography variant="caption" color="text.secondary">Total Tracked Joins</Typography>
                <Typography variant="h5" fontWeight={700}>
                  {links.reduce((s, l) => s + (l.joins_total || 0), 0)}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={6} sm={3}>
            <Card variant="outlined">
              <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                <Typography variant="caption" color="text.secondary">{currentPeriodLabel}</Typography>
                <Typography variant="h5" fontWeight={700} color="primary.main">
                  {links.reduce((s, l) => s + (l.featured_joins || 0), 0)}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Main table */}
      {links.length === 0 ? (
        <Card>
          <CardContent>
            <Typography color="text.secondary" align="center">No invite links yet. Create one to start tracking.</Typography>
          </CardContent>
        </Card>
      ) : (
        <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ '& th': { fontWeight: 700, whiteSpace: 'nowrap' } }}>
                <TableCell>Name</TableCell>
                <TableCell>Created By</TableCell>
                <TableCell>Link</TableCell>
                <TableCell align="right">Total Joins</TableCell>
                <TableCell align="right">1 Day</TableCell>
                <TableCell align="right">7 Days</TableCell>
                <TableCell align="right">30 Days</TableCell>
                <TableCell>Expires</TableCell>
                <TableCell>Status</TableCell>
                <TableCell></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {links.map(link => (
                <TableRow key={link.id} hover sx={{ opacity: link.is_active ? 1 : 0.55 }}>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <Link fontSize="small" color="primary" />
                      <Typography variant="body2" fontWeight={500}>{link.name}</Typography>
                    </Box>
                  </TableCell>
                  <TableCell>
                    {link.created_by_username || link.created_by_telegram_id ? (
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Person fontSize="small" color="action" />
                        <Typography variant="body2" color="text.secondary" sx={{ fontSize: 11 }}>
                          {link.created_by_username ? `@${link.created_by_username}` : `ID: ${link.created_by_telegram_id}`}
                        </Typography>
                      </Box>
                    ) : (
                      <Typography variant="body2" color="text.disabled">—</Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    {link.telegram_invite_link ? (
                      <Tooltip title={link.telegram_invite_link}>
                        <Button size="small" startIcon={<ContentCopy />} onClick={() => copyLink(link.telegram_invite_link)}
                          sx={{ textTransform: 'none', fontSize: 11 }}>
                          Copy
                        </Button>
                      </Tooltip>
                    ) : (
                      <Typography variant="body2" color="text.secondary">Generating…</Typography>
                    )}
                  </TableCell>
                  <TableCell align="right">
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 0.5 }}>
                      <TrendingUp fontSize="small" color="success" />
                      <Typography variant="body2" fontWeight={500}>
                        {link.joins_total ?? link.uses_count ?? 0}
                        {link.max_uses ? ` / ${link.max_uses}` : ''}
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2">{link.joins_1d ?? '—'}</Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2">{link.joins_7d ?? '—'}</Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2">{link.joins_30d ?? '—'}</Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
                      {link.expire_date ? new Date(link.expire_date).toLocaleDateString() : '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={link.is_active ? 'Active' : 'Revoked'}
                      size="small"
                      color={link.is_active ? 'success' : 'default'}
                    />
                  </TableCell>
                  <TableCell>
                    {link.is_active && (
                      <IconButton size="small" color="error" onClick={() => handleRevoke(link.id)}>
                        <Delete fontSize="small" />
                      </IconButton>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {revokedLinks.length > 0 && (
        <Typography variant="caption" color="text.secondary">
          {revokedLinks.length} revoked link{revokedLinks.length > 1 ? 's' : ''} shown above (greyed out).
        </Typography>
      )}

      {/* Platform limitation note */}
      <Alert severity="warning" sx={{ mt: 2 }}>
        <strong>Platform note:</strong> Join tracking requires the bot to have <strong>administrator rights</strong> with "Add Members" permission to receive ChatMember events. If the bot lacks this permission, join counts will not update automatically.
      </Alert>

      {/* Create dialog */}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Create Invite Link</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12}>
              <TextField fullWidth label="Link Name (e.g. Twitter Campaign)" value={form.name}
                onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth type="number" label="Max Uses (leave blank for unlimited)"
                value={form.max_uses} onChange={e => setForm(p => ({ ...p, max_uses: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth type="datetime-local" label="Expire Date (optional)"
                InputLabelProps={{ shrink: true }} value={form.expire_date}
                onChange={e => setForm(p => ({ ...p, expire_date: e.target.value }))} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreate}>Create</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
