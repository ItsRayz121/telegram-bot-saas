import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton,
  Chip, Alert, Tooltip, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper,
} from '@mui/material';
import { Add, Delete, ContentCopy, Link } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { invites } from '../services/api';

export default function InviteLinks({ botId, groupId }) {
  const [links, setLinks] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', max_uses: '', expire_date: '' });

  const load = async () => {
    try {
      const res = await invites.list(botId, groupId);
      setLinks(res.data.invite_links || []);
    } catch { }
  };

  useEffect(() => { load(); }, [botId, groupId]);

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

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight={600}>Invite Links</Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => setOpen(true)}>Create Link</Button>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        Create named invite links to track where new members come from. Each link is generated via the Telegram Bot API and tracked in the dashboard.
        Also use <strong>/invitelink [name]</strong> in the group.
      </Alert>

      {links.length === 0 ? (
        <Card><CardContent><Typography color="text.secondary" align="center">No invite links yet.</Typography></CardContent></Card>
      ) : (
        <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Link</TableCell>
                <TableCell>Uses</TableCell>
                <TableCell>Expires</TableCell>
                <TableCell>Status</TableCell>
                <TableCell></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {links.map(link => (
                <TableRow key={link.id} hover>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <Link fontSize="small" color="primary" />
                      <Typography variant="body2" fontWeight={500}>{link.name}</Typography>
                    </Box>
                  </TableCell>
                  <TableCell>
                    {link.telegram_invite_link ? (
                      <Tooltip title="Copy link">
                        <Button size="small" startIcon={<ContentCopy />} onClick={() => copyLink(link.telegram_invite_link)} sx={{ textTransform: 'none', fontSize: 11 }}>
                          Copy
                        </Button>
                      </Tooltip>
                    ) : (
                      <Typography variant="body2" color="text.secondary">Generating...</Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {link.uses_count}{link.max_uses ? ` / ${link.max_uses}` : ''}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {link.expire_date ? new Date(link.expire_date).toLocaleDateString() : '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip label={link.is_active ? 'Active' : 'Revoked'} size="small" color={link.is_active ? 'success' : 'default'} />
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
