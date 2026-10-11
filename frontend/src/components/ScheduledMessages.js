import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Switch, FormControlLabel, Dialog, DialogTitle, DialogContent,
  DialogActions, IconButton, Chip, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, Paper, Tooltip, CircularProgress,
} from '@mui/material';
import { Add, Delete, Edit, Schedule, Repeat, AccessTime, Save } from '@mui/icons-material';
import { Alert } from '@mui/material';
import { toast } from 'react-toastify';
import { settings } from '../services/api';
import TimezoneSelect, { formatInTimezone } from './TimezoneSelect';
import { MessagePreview, PreviewPanel } from './preview/MessagePreview';

// UTC instant -> the 'YYYY-MM-DDTHH:mm' wall time in `tz`, the format a datetime-local input expects.
function utcToLocalInput(iso, tz) {
  if (!iso) return '';
  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    }).formatToParts(new Date(iso)).reduce((a, p) => ({ ...a, [p.type]: p.value }), {});
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  } catch {
    return '';
  }
}

// 'YYYY-MM-DDTHH:mm' typed as wall time in `tz` -> the UTC instant (ISO), or null. Mirrors the server's conversion.
function wallToUtcIso(wall, tz) {
  if (!wall) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(wall);
  if (!m) return null;
  const guess = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  try {
    const offsetAt = (t) => {
      const p = new Intl.DateTimeFormat('en-CA', { timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
        .formatToParts(new Date(t)).reduce((a, x) => ({ ...a, [x.type]: x.value }), {});
      return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) - t;
    };
    let t = guess - offsetAt(guess);
    t = guess - offsetAt(t);
    return new Date(t).toISOString();
  } catch { return null; }
}

export default function ScheduledMessages({ botId, groupId, defaultTimezone }) {
  const [messages, setMessages] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);   // the saved schedule being edited (null = creating)
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);   // false until the first list response: no "empty" flash while loading

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
      // Custom-bot groups answer { scheduled_messages: [...] }; official groups answer a bare list.
      setMessages(Array.isArray(res.data) ? res.data : (res.data.scheduled_messages || []));
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to load scheduled messages');
    } finally { setLoaded(true); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [botId, groupId]);

  // Keep default timezone in sync if the group setting changes
  useEffect(() => {
    setForm(prev => (editing ? prev : { ...prev, timezone: defaultTimezone || browserTz }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultTimezone]);

  const payloadFrom = (f) => ({
    title: f.title,
    message_text: f.message_text,
    timezone: f.timezone,
    stop_date: f.stop_date || null,   // on edit this is dropped unless changed (see handleSaveEdit)
    repeat_interval: f.repeat_interval ? parseInt(f.repeat_interval, 10) : null,
    auto_delete_after: f.auto_delete_after ? parseInt(f.auto_delete_after, 10) : null,
    pin_message: f.pin_message,
    link_preview_enabled: f.link_preview_enabled,
  });

  const closeDialog = () => { setOpen(false); setEditing(null); setForm(emptyForm); };

  const handleCreate = async () => {
    if (!form.title || !form.message_text || !form.send_at) {
      toast.error('Title, message and send time are required');
      return;
    }
    try {
      await settings.createScheduledMessage(botId, groupId, {
        ...payloadFrom(form),
        send_at: form.send_at,          // raw local datetime — backend converts with timezone
      });
      toast.success('Scheduled message created');
      closeDialog();
      load();
    } catch (e) { toast.error(e.response?.data?.error || 'Failed to create'); }
  };

  const openEdit = (m) => {
    const tz = m.timezone || 'UTC';
    const f = {
      title: m.title || '',
      message_text: m.message_text || '',
      send_at: utcToLocalInput(m.send_at, tz),
      timezone: tz,
      repeat_interval: m.repeat_interval ? String(m.repeat_interval) : '',
      stop_date: utcToLocalInput(m.stop_date, tz),
      pin_message: !!m.pin_message,
      auto_delete_after: m.auto_delete_after ? String(m.auto_delete_after) : '',
      link_preview_enabled: m.link_preview_enabled !== false,
    };
    setEditing({ ...m, initial: f });
    setForm(f);
    setOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!form.title.trim() || !form.message_text.trim() || !form.send_at) {
      toast.error('Title, message and send time are required');
      return;
    }
    // Only send the time when the person changed it (or its timezone): otherwise a
    // text-only edit would re-submit a rounded time and could be rejected as "in the past".
    const timeChanged = form.send_at !== editing.initial.send_at || form.timezone !== editing.initial.timezone;
    const body = payloadFrom(form);
    if (timeChanged) body.send_at = form.send_at;
    // Same rule for the stop date: an untouched stop date is not re-converted, so nothing shifts.
    if (form.stop_date === editing.initial.stop_date && form.timezone === editing.initial.timezone) delete body.stop_date;
    setSaving(true);
    try {
      await settings.updateScheduledMessage(botId, groupId, editing.id, body);
      toast.success('Scheduled message updated');
      closeDialog();
      load();
    } catch (e) {
      // Dialog stays open with the person's edits; the saved schedule is untouched.
      toast.error(e.response?.data?.error || 'Failed to save changes');
      if (e.response?.data?.code === 'ALREADY_SENT') load();
    } finally { setSaving(false); }
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
        <Button variant="contained" startIcon={<Add />} onClick={() => { setEditing(null); setForm(emptyForm); setOpen(true); }}>Schedule Message</Button>
      </Box>

      {!loaded ? (
        <Card><CardContent sx={{ display: 'flex', justifyContent: 'center' }}><CircularProgress size={22} aria-label="Loading scheduled messages" /></CardContent></Card>
      ) : messages.length === 0 ? (
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
                    {m.tz_review && (
                      <Tooltip title="Saved before timezone handling was corrected. The stored time is unchanged; open Edit to check it reads right.">
                        <Chip label="Check time" size="small" variant="outlined" color="warning" sx={{ ml: 0.5 }} />
                      </Tooltip>
                    )}
                  </TableCell>
                  <TableCell>
                    <Tooltip title={m.is_sent ? 'Already sent — can no longer be edited' : 'Edit scheduled message'}>
                      <span>
                        <IconButton size="small" aria-label="Edit scheduled message" disabled={!!m.is_sent}
                          onClick={() => openEdit(m)}><Edit fontSize="small" /></IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title="Delete scheduled message">
                      <IconButton size="small" color="error" aria-label="Delete scheduled message" onClick={() => handleDelete(m.id)}><Delete fontSize="small" /></IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog open={open} onClose={saving ? undefined : closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{editing ? 'Edit scheduled message' : 'Schedule a Message'}</DialogTitle>
        <DialogContent>
          {editing?.tz_review && (
            <Alert severity="warning" sx={{ mt: 0.5, mb: 1 }}>
              This schedule was saved before timezone handling was corrected, so the time you typed may have been stored as UTC
              instead of {editing.timezone}. Its stored send time ({formatInTimezone(editing.send_at, 'UTC')} UTC) is unchanged and
              is what will be used. If the time shown below is not what you meant, change the date and time and save.
            </Alert>
          )}
          {editing && (
            <Alert severity="info" sx={{ mt: 0.5 }}>
              {editing.repeat_interval
                ? 'Changes apply to future sends only. Messages already sent stay as they were.'
                : 'This message has not been sent yet. Saving updates it in place and does not send it now.'}
              {' '}A new send time must be in the future.
            </Alert>
          )}
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12}>
              <TextField fullWidth label="Title" value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth multiline rows={4} label="Message Text (Markdown supported)" value={form.message_text} onChange={e => setForm(p => ({ ...p, message_text: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              {/* Preview only: renders this draft locally. The scheduler posts the text as-is (Telegram Markdown). */}
              <PreviewPanel>
                <MessagePreview platform="telegram" syntax="none" kind="scheduled message" text={form.message_text}
                  buttons={editing?.buttons || undefined} linkPreview={form.link_preview_enabled}
                  media={editing?.media_url ? { kind: 'Media', label: editing.media_url.split('/').pop() } : undefined}
                  destination="Posted to the group at the scheduled time" notes={form.pin_message ? ['This message will also be pinned when it is posted.'] : []} />
              </PreviewPanel>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth type="datetime-local" label="Send At" InputLabelProps={{ shrink: true }}
                value={form.send_at} onChange={e => setForm(p => ({ ...p, send_at: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              {(() => {
                const changed = !editing || form.send_at !== editing.initial.send_at || form.timezone !== editing.initial.timezone;
                const iso = changed ? wallToUtcIso(form.send_at, form.timezone) : editing.send_at;
                if (!iso) return <Typography variant="caption" color="text.secondary">Pick a date and time to see when it will be sent.</Typography>;
                return (
                  <Typography variant="caption" color="text.secondary" data-testid="next-send">
                    Next send: <strong>{formatInTimezone(iso, form.timezone)} ({form.timezone})</strong> = {formatInTimezone(iso, 'UTC')} UTC
                    {form.repeat_interval ? `, then every ${form.repeat_interval} minutes` : ' (once)'}
                    {editing && !changed ? ' · unchanged' : ''}
                  </Typography>
                );
              })()}
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
          <Button onClick={closeDialog} disabled={saving}>Cancel</Button>
          {editing ? (
            <Button variant="contained" startIcon={<Save />} onClick={handleSaveEdit} disabled={saving}>
              {saving ? 'Saving…' : 'Save changes'}
            </Button>
          ) : (
            <Button variant="contained" startIcon={<Schedule />} onClick={handleCreate}>Schedule</Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
}
