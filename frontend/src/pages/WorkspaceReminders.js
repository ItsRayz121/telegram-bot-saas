import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Button, Card, CardContent, Chip, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Alert, CircularProgress, Grid, Tabs, Tab, Tooltip,
} from '@mui/material';
import {
  AccessTime, Add, Delete, CheckCircle, RadioButtonUnchecked,
  ArrowBack, Notifications, EventAvailable,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { workspace, googleCalendar as calApi } from '../services/api';

const QUICK_TIMES = [
  { label: '30 min', minutes: 30 },
  { label: '1 hour', minutes: 60 },
  { label: '2 hours', minutes: 120 },
  { label: '4 hours', minutes: 240 },
  { label: 'Tomorrow', minutes: 24 * 60 },
  { label: '2 days', minutes: 2 * 24 * 60 },
  { label: '1 week', minutes: 7 * 24 * 60 },
];

function toLocalDatetimeInput(date) {
  const d = new Date(date);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

function ReminderCard({ reminder, onDelete, calConnected }) {
  const isPast = new Date(reminder.remind_at) < new Date();
  const remind_dt = new Date(reminder.remind_at);
  const [syncing, setSyncing] = useState(false);

  const syncCal = async () => {
    setSyncing(true);
    try {
      const { data } = await calApi.syncReminder(reminder.id);
      if (data.html_link) {
        toast.success(
          <span>Added to Google Calendar — <a href={data.html_link} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit' }}>View event</a></span>
        );
      } else {
        toast.success('Event added to Google Calendar');
      }
    } catch (e) {
      toast.error(e?.response?.data?.error || 'Failed to sync to calendar.');
    } finally {
      setSyncing(false);
    }
  };

  const timeLabel = remind_dt.toLocaleString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });

  return (
    <Card sx={{ opacity: reminder.is_delivered ? 0.65 : 1 }}>
      <CardContent sx={{ p: 2.5, display: 'flex', alignItems: 'flex-start', gap: 2 }}>
        <Box sx={{ pt: 0.25 }}>
          {reminder.is_delivered
            ? <CheckCircle sx={{ color: 'success.main', fontSize: 22 }} />
            : <RadioButtonUnchecked sx={{ color: isPast ? 'warning.main' : 'primary.main', fontSize: 22 }} />
          }
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body1" fontWeight={600} sx={{ mb: 0.5 }}>
            {reminder.reminder_text}
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
            <Chip
              icon={<AccessTime sx={{ fontSize: '0.8rem !important' }} />}
              label={timeLabel}
              size="small"
              color={reminder.is_delivered ? 'default' : isPast ? 'warning' : 'primary'}
              variant="outlined"
              sx={{ fontSize: '0.7rem' }}
            />
            {reminder.is_delivered && (
              <Chip label="Delivered" size="small" color="success" sx={{ fontSize: '0.7rem' }} />
            )}
            {reminder.telegram_group_id && (
              <Chip label="Group reminder" size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} />
            )}
          </Box>
          {reminder.original_message && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.75, display: 'block' }} noWrap>
              From: "{reminder.original_message}"
            </Typography>
          )}
        </Box>
        <Box sx={{ display: 'flex', gap: 0.5 }}>
          {calConnected && !reminder.is_delivered && (
            <Tooltip title="Add to Google Calendar">
              <IconButton size="small" color="primary" onClick={syncCal} disabled={syncing}>
                {syncing ? <CircularProgress size={14} /> : <EventAvailable fontSize="small" />}
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title="Delete">
            <IconButton size="small" onClick={() => onDelete(reminder.id)} color="error">
              <Delete fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </CardContent>
    </Card>
  );
}

function CreateDialog({ open, onClose, onCreated }) {
  const [text, setText] = useState('');
  const [remindAt, setRemindAt] = useState('');
  const [saving, setSaving] = useState(false);

  const setQuickTime = (minutes) => {
    const d = new Date(Date.now() + minutes * 60000);
    setRemindAt(toLocalDatetimeInput(d));
  };

  const handleSave = async () => {
    if (!text.trim() || !remindAt) return;
    setSaving(true);
    try {
      const isoDate = new Date(remindAt).toISOString();
      const res = await workspace.createReminder({ reminder_text: text.trim(), remind_at: isoDate });
      onCreated(res.data.reminder);
      toast.success('Reminder saved! I\'ll DM you on Telegram.');
      setText('');
      setRemindAt('');
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to save reminder');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>New Reminder</DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <Alert severity="info" sx={{ mb: 2.5, fontSize: '0.82rem' }}>
          Delivered via Telegram DM. You must have your Telegram connected at{' '}
          <strong>/settings</strong> for delivery to work.
        </Alert>
        <TextField
          label="What to remind you about"
          multiline
          rows={2}
          fullWidth
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Follow up with Alice about the proposal"
          inputProps={{ maxLength: 500 }}
          sx={{ mb: 2.5 }}
          autoFocus
        />
        <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
          Quick times
        </Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
          {QUICK_TIMES.map((qt) => (
            <Chip
              key={qt.label}
              label={qt.label}
              size="small"
              clickable
              variant="outlined"
              onClick={() => setQuickTime(qt.minutes)}
            />
          ))}
        </Box>
        <TextField
          label="Remind at"
          type="datetime-local"
          fullWidth
          value={remindAt}
          onChange={(e) => setRemindAt(e.target.value)}
          InputLabelProps={{ shrink: true }}
          inputProps={{ min: toLocalDatetimeInput(new Date()) }}
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={!text.trim() || !remindAt || saving}
          startIcon={saving ? <CircularProgress size={16} /> : null}
        >
          Save Reminder
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function WorkspaceReminders() {
  const navigate = useNavigate();
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(0); // 0=upcoming, 1=delivered
  const [dialogOpen, setDialogOpen] = useState(false);
  const [calConnected, setCalConnected] = useState(false);

  useEffect(() => {
    calApi.status().then(r => setCalConnected(r.data?.connected || false)).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await workspace.listReminders({ delivered: tab === 1 ? 'true' : 'false' });
      setReminders(res.data.reminders || []);
    } catch {
      toast.error('Failed to load reminders');
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (id) => {
    try {
      await workspace.deleteReminder(id);
      setReminders((r) => r.filter((x) => x.id !== id));
      toast.success('Reminder deleted');
    } catch {
      toast.error('Failed to delete reminder');
    }
  };

  const handleCreated = (reminder) => {
    if (tab === 0) setReminders((r) => [reminder, ...r]);
  };

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 760, mx: 'auto' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
        <IconButton size="small" onClick={() => navigate('/workspace')} sx={{ mr: 0.5 }}>
          <ArrowBack fontSize="small" />
        </IconButton>
        <Notifications sx={{ color: 'primary.main' }} />
        <Typography variant="h5" fontWeight={700}>Reminders</Typography>
      </Box>
      <Typography color="text.secondary" sx={{ mb: 3, ml: 5 }}>
        Save anything you need to follow up on. The bot DMs you on Telegram at the right time.
      </Typography>

      <Alert severity="info" sx={{ mb: 3, fontSize: '0.83rem' }}>
        <strong>Auto-detection:</strong> The bot watches for phrases like "remind me to…" in your groups
        and creates reminders automatically. Or use <code>/remind 2h text</code> in any linked group.
      </Alert>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ minHeight: 36 }}>
          <Tab label="Upcoming" sx={{ minHeight: 36, py: 0 }} />
          <Tab label="Delivered" sx={{ minHeight: 36, py: 0 }} />
        </Tabs>
        <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)} size="small">
          New Reminder
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : reminders.length === 0 ? (
        <Card sx={{ textAlign: 'center', py: 6 }}>
          <CardContent>
            <AccessTime sx={{ fontSize: 48, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              {tab === 0 ? 'No upcoming reminders' : 'No delivered reminders'}
            </Typography>
            {tab === 0 && (
              <Button variant="outlined" startIcon={<Add />} onClick={() => setDialogOpen(true)} sx={{ mt: 1 }}>
                Create your first reminder
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <Grid container spacing={1.5}>
          {reminders.map((r) => (
            <Grid item xs={12} key={r.id}>
              <ReminderCard reminder={r} onDelete={handleDelete} calConnected={calConnected} />
            </Grid>
          ))}
        </Grid>
      )}

      <CreateDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={handleCreated}
      />
    </Box>
  );
}
