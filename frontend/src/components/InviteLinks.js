import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton,
  Chip, Alert, Tooltip, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Menu, MenuItem, ListItemIcon, ListItemText,
  ToggleButton, ToggleButtonGroup, Collapse, useMediaQuery,
} from '@mui/material';
import {
  Add, Delete, ContentCopy, MoreVert, KeyboardArrowDown, KeyboardArrowUp,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { invites } from '../services/api';

const TIME_FILTERS = [
  { value: '1d', label: 'Last 1 Day', short: '1d' },
  { value: '7d', label: 'Last 7 Days', short: '7d' },
  { value: '30d', label: 'Last 30 Days', short: '30d' },
  { value: 'all', label: 'All Time', short: 'All' },
];

// One-line name with a full-name reveal only when it is long enough to be cut off.
// Ordinary names stay on one line; no break-all wrapping.
function LinkName({ name, creator }) {
  const long = (name || '').length > 28;
  const text = (
    <Typography variant="body2" fontWeight={600} noWrap tabIndex={long ? 0 : undefined}
      aria-label={long ? name : undefined}>
      {name}
    </Typography>
  );
  return (
    <Box sx={{ minWidth: 0 }}>
      {long ? <Tooltip title={name} enterTouchDelay={0}>{text}</Tooltip> : text}
      <Typography variant="caption" color="text.secondary" noWrap display="block">
        {creator || 'Creator unknown'}
      </Typography>
    </Box>
  );
}

function creatorLabel(link) {
  if (link.created_by_username) return `@${link.created_by_username}`;
  if (link.created_by_telegram_id) return `ID: ${link.created_by_telegram_id}`;
  return '';
}

export default function InviteLinks({ botId, groupId }) {
  const [links, setLinks] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const [timeFilter, setTimeFilter] = useState('all');
  const [form, setForm] = useState({ name: '', max_uses: '', expire_date: '' });
  const [menu, setMenu] = useState({ anchor: null, link: null });
  const [expanded, setExpanded] = useState({});
  const compact = useMediaQuery('(max-width:899.95px)');

  const load = async () => {
    try {
      const res = await invites.list(botId, groupId, { time_filter: timeFilter });
      setLinks(res.data.invite_links || []);
    } catch { toast.error('Failed to load invite links'); }
    finally { setLoaded(true); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const closeMenu = () => setMenu({ anchor: null, link: null });

  const activeLinks = links.filter(l => l.is_active);
  const revokedLinks = links.filter(l => !l.is_active);

  const currentPeriod = TIME_FILTERS.find(f => f.value === timeFilter) || TIME_FILTERS[3];
  const currentPeriodLabel = currentPeriod.label;
  const currentPeriodShort = currentPeriod.short;
  // Selected-period joins ("All" = lifetime). The underlying counts are unchanged.
  const periodJoins = (l) => (timeFilter === 'all' ? (l.joins_total ?? l.uses_count ?? 0) : (l.featured_joins ?? '—'));
  const totalJoins = (l) => `${l.joins_total ?? l.uses_count ?? 0}${l.max_uses ? ` / ${l.max_uses}` : ''}`;
  const expiresText = (l) => (l.expire_date ? new Date(l.expire_date).toLocaleDateString() : '—');
  const statusChip = (l) => (
    <Chip label={l.is_active ? 'Active' : 'Revoked'} size="small" color={l.is_active ? 'success' : 'default'} />
  );

  return (
    <Box sx={{ width: '100%' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="h6" fontWeight={600}>Invite Links</Typography>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <ToggleButtonGroup size="small" exclusive value={timeFilter} aria-label="Joins period"
            onChange={(_, v) => v && setTimeFilter(v)}>
            {TIME_FILTERS.map(f => (
              <ToggleButton key={f.value} value={f.value} aria-label={f.label} sx={{ textTransform: 'none', px: 1.5 }}>
                {f.short}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
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

      {/* Main table (desktop) / stacked cards (narrow screens) */}
      {links.length === 0 ? (
        <Card>
          <CardContent>
            <Typography color="text.secondary" align="center">
              {loaded ? 'No invite links yet. Create one to start tracking.' : 'Loading invite links…'}
            </Typography>
          </CardContent>
        </Card>
      ) : compact ? (
        <Box sx={{ display: 'grid', gap: 1.25, mb: 2 }}>
          {links.map(link => (
            <Card key={link.id} variant="outlined" sx={{ opacity: link.is_active ? 1 : 0.6 }}>
              <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <LinkName name={link.name} creator={creatorLabel(link)} />
                  </Box>
                  {statusChip(link)}
                  <IconButton size="small" aria-label={`Actions for ${link.name}`} aria-haspopup="menu"
                    onClick={(e) => setMenu({ anchor: e.currentTarget, link })}>
                    <MoreVert fontSize="small" />
                  </IconButton>
                </Box>
                <Box sx={{ display: 'flex', gap: 3, mt: 1, flexWrap: 'wrap' }}>
                  <Box>
                    <Typography variant="caption" color="text.secondary" display="block">Joins ({currentPeriodShort})</Typography>
                    <Typography variant="body2" fontWeight={600}>{periodJoins(link)}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary" display="block">Total joins</Typography>
                    <Typography variant="body2" fontWeight={600}>{totalJoins(link)}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary" display="block">Expires</Typography>
                    <Typography variant="body2" fontWeight={600}>{expiresText(link)}</Typography>
                  </Box>
                </Box>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
                  1d: {link.joins_1d ?? '—'} · 7d: {link.joins_7d ?? '—'} · 30d: {link.joins_30d ?? '—'}
                </Typography>
              </CardContent>
            </Card>
          ))}
        </Box>
      ) : (
        <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2, width: '100%' }}>
          <Table size="small" sx={{ width: '100%' }}>
            <TableHead>
              <TableRow sx={{ '& th': { fontWeight: 700, whiteSpace: 'nowrap' } }}>
                <TableCell padding="checkbox" />
                <TableCell sx={{ minWidth: 240, width: '34%' }}>Link name</TableCell>
                <TableCell align="right">Joins ({currentPeriodShort})</TableCell>
                <TableCell align="right">Total joins</TableCell>
                <TableCell>Expires</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right" sx={{ width: 56 }}>
                  <Box component="span" sx={{ position: 'absolute', left: -9999 }}>Actions</Box>
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {links.map(link => (
                <React.Fragment key={link.id}>
                  <TableRow hover sx={{ opacity: link.is_active ? 1 : 0.6, '& > td': { borderBottom: expanded[link.id] ? 0 : undefined } }}>
                    <TableCell padding="checkbox">
                      <IconButton size="small" aria-expanded={!!expanded[link.id]}
                        aria-label={`${expanded[link.id] ? 'Hide' : 'Show'} join periods for ${link.name}`}
                        onClick={() => setExpanded(p => ({ ...p, [link.id]: !p[link.id] }))}>
                        {expanded[link.id] ? <KeyboardArrowUp fontSize="small" /> : <KeyboardArrowDown fontSize="small" />}
                      </IconButton>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 300 }}>
                      <LinkName name={link.name} creator={creatorLabel(link)} />
                    </TableCell>
                    <TableCell align="right"><Typography variant="body2" fontWeight={600}>{periodJoins(link)}</Typography></TableCell>
                    <TableCell align="right"><Typography variant="body2">{totalJoins(link)}</Typography></TableCell>
                    <TableCell><Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>{expiresText(link)}</Typography></TableCell>
                    <TableCell>{statusChip(link)}</TableCell>
                    <TableCell align="right">
                      <IconButton size="small" aria-label={`Actions for ${link.name}`} aria-haspopup="menu"
                        onClick={(e) => setMenu({ anchor: e.currentTarget, link })}>
                        <MoreVert fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={7} sx={{ py: 0, borderBottom: expanded[link.id] ? undefined : 0 }}>
                      <Collapse in={!!expanded[link.id]} unmountOnExit>
                        <Box sx={{ display: 'flex', gap: 4, py: 1.25, pl: 5, flexWrap: 'wrap' }}>
                          <Typography variant="body2" color="text.secondary">Last 1 day: <b>{link.joins_1d ?? '—'}</b></Typography>
                          <Typography variant="body2" color="text.secondary">Last 7 days: <b>{link.joins_7d ?? '—'}</b></Typography>
                          <Typography variant="body2" color="text.secondary">Last 30 days: <b>{link.joins_30d ?? '—'}</b></Typography>
                          {link.max_uses ? <Typography variant="body2" color="text.secondary">Max uses: <b>{link.max_uses}</b></Typography> : null}
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Menu anchorEl={menu.anchor} open={Boolean(menu.anchor)} onClose={closeMenu}>
        <MenuItem disabled={!menu.link?.telegram_invite_link}
          onClick={() => { copyLink(menu.link?.telegram_invite_link); closeMenu(); }}>
          <ListItemIcon><ContentCopy fontSize="small" /></ListItemIcon>
          <ListItemText>{menu.link && !menu.link.telegram_invite_link ? 'Link generating…' : 'Copy link'}</ListItemText>
        </MenuItem>
        {menu.link?.is_active && (
          <MenuItem onClick={() => { handleRevoke(menu.link.id); closeMenu(); }}>
            <ListItemIcon><Delete fontSize="small" color="error" /></ListItemIcon>
            <ListItemText>Revoke link</ListItemText>
          </MenuItem>
        )}
      </Menu>

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
