import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Switch, FormControlLabel, Dialog, DialogTitle, DialogContent,
  DialogActions, IconButton, Chip, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, Paper, Tooltip,
} from '@mui/material';
import { Add, Delete, Schedule, Repeat, AccessTime } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { settings } from '../services/api';
import TimezoneSelect, { formatInTimezone } from './TimezoneSelect';

export default function ScheduledMessages({ botId, groupId, defaultTimezone }) {
  const [messages, setMessages] = useState([]);
  const [open, setOpen] = useState(false);

  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  const initialTz = defaultTimezone || browserTz;

  const emptyForm = {
    title: '', message_text: '', send_at: '', timezone: initialTz,
    repeat_interval: '', stop_date: '', pin_message: false,
    auto_delete_after: '', link_preview_enabled: true,
  };
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    try {
      const res = await settings.getScheduledMessages(botId, groupId);
      setMessages(res.data.scheduled_messages || []);
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to load scheduled messages');
    }
  };

  useEffect(() => { load(); }, [botId, groupId]);

  // Keep default timezone in sync if the group setting changes
  useEffect(() => {
    setForm(prev => ({ ...prev, timezone: defaultTimezone || browserTz }));
  }, [defaultTimezone]);

  const handleCreate = async () => {
    if (!form.title || !form.message_text || !form.send_at) {
      toast.error('Title, message and send time are required');
      return;
    }
    try {
      await settings.createScheduledMessage(botId, groupId, {
        title: form.title,
        message_text: form.message_text,
        send_at: form.send_at,          // raw local datetime — backend converts with timezone
        timezone: form.timezone,
        stop_date: form.stop_date || null,
        repeat_interval: form.repeat_interval ? parseInt(form.repeat_interval) : null,
        auto_delete_after: form.auto_delete_after ? parseInt(form.auto_delete_after) : null,
        pin_message: form.pin_message,
        link_preview_enabled: form.link_preview_enabled,
      });
      toast.success('Scheduled message created');
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (e) { toast.error(e.response?.data?.error || 'Failed to create'); }
  };

  const handleDelete = async (id) => {
    try {
      await settings.deleteScheduledMessage(botId, groupId, id);
      toast.success('Deleted');
      setMessages(prev => prev.filter(m => m.id !== id));
    } catch { toast.error('Failed to delete'); }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight={600}>Scheduled Messages</Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => setOpen(true)}>Schedule Message</Button>
      </Box>

      {messages.length === 0 ? (
        <Card><CardContent><Typography color="text.secondary" align="center">No scheduled messages yet.</Typography></CardContent></Card>
      ) : (
        <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Title</TableCell>
                <TableCell>Send At</TableCell>
                <TableCell>Repeat</TableCell>
                <TableCell>Status</TableCell>
                <TableCell></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {messages.map(m => (
                <TableRow key={m.id} hover>
                  <TableCell><Typography variant="body2" fontWeight={500}>{m.title}</Typography></TableCell>
                  <TableCell>
                    <Tooltip title={`UTC: ${m.send_at}`}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <AccessTime sx={{ fontSize: 14, color: 'text.secondary' }} />
                        <Typography variant="body2">
                          {formatInTimezone(m.send_at, m.timezone)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
                          ({m.timezone})
                        </Typography>
                      </Box>
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    {m.repeat_interval ? (
                      <Chip icon={<Repeat />} label={`Every ${m.repeat_interval}m`} size="small" color="primary" variant="outlined" />
                    ) : <Typography variant="body2" color="text.secondary">Once</Typography>}
                  </TableCell>
                  <TableCell>
                    <Chip label={m.is_sent ? 'Sent' : 'Pending'} size="small" color={m.is_sent ? 'success' : 'warning'} />
                  </TableCell>
                  <TableCell>
                    <IconButton size="small" color="error" onClick={() => handleDelete(m.id)}><Delete fontSize="small" /></IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Schedule a Message</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12}>
              <TextField fullWidth label="Title" value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth multiline rows={4} label="Message Text (Markdown supported)" value={form.message_text} onChange={e => setForm(p => ({ ...p, message_text: e.target.value }))} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth type="datetime-local" label="Send At" InputLabelProps={{ shrink: true }}
                value={form.send_at} onChange={e => setForm(p => ({ ...p, send_at: e.target.value }))} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TimezoneSelect
                value={form.timezone}
                onChange={tz => setForm(p => ({ ...p, timezone: tz }))}
                label="Timezone"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth type="number" label="Repeat Every (minutes, 0=once)"
                value={form.repeat_interval} onChange={e => setForm(p => ({ ...p, repeat_interval: e.target.value }))} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth type="datetime-local" label="Stop Repeating At" InputLabelProps={{ shrink: true }}
                value={form.stop_date} onChange={e => setForm(p => ({ ...p, stop_date: e.target.value }))} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth type="number" label="Auto-delete after (seconds, 0=never)"
                value={form.auto_delete_after} onChange={e => setForm(p => ({ ...p, auto_delete_after: e.target.value }))} />
            </Grid>
            <Grid item xs={6}>
              <FormControlLabel control={<Switch checked={form.pin_message} onChange={e => setForm(p => ({ ...p, pin_message: e.target.checked }))} />} label="Pin message" />
            </Grid>
            <Grid item xs={6}>
              <FormControlLabel control={<Switch checked={form.link_preview_enabled} onChange={e => setForm(p => ({ ...p, link_preview_enabled: e.target.checked }))} />} label="Link preview" />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" startIcon={<Schedule />} onClick={handleCreate}>Schedule</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
