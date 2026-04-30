import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Select, MenuItem,
  FormControl, InputLabel, ToggleButton, ToggleButtonGroup, Chip,
  CircularProgress, Alert, Dialog, DialogTitle, DialogContent,
  DialogActions, Divider, TextField, Switch, FormControlLabel,
  IconButton, Tooltip,
} from '@mui/material';
import {
  Send, History, Circle, Summarize, AddCircleOutline,
} from '@mui/icons-material';
import { digests } from '../services/api';
import { useNavigate } from 'react-router-dom';

const FREQUENCIES = [
  { value: 'daily',   label: 'Daily'   },
  { value: 'weekly',  label: 'Weekly'  },
  { value: 'monthly', label: 'Monthly' },
];

function relativeTime(isoStr) {
  if (!isoStr) return null;
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 2) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return 'Yesterday';
  return `${days} days ago`;
}

function StatusDot({ status }) {
  const color = status === 'active' ? 'success.main' : status === 'pending' ? 'warning.main' : 'text.disabled';
  return <Circle sx={{ fontSize: 10, color, mr: 0.5 }} />;
}

function HistoryDialog({ groupTitle, groupId, open, onClose }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !groupId) return;
    setLoading(true);
    digests.getHistory(groupId)
      .then(({ data }) => setRows(data.history || []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [open, groupId]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Digest History — {groupTitle}</DialogTitle>
      <DialogContent dividers sx={{ p: 0 }}>
        {loading ? (
          <Box sx={{ p: 3, display: 'flex', justifyContent: 'center' }}>
            <CircularProgress size={28} />
          </Box>
        ) : rows.length === 0 ? (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography color="text.secondary" fontSize="0.88rem">No digests sent yet.</Typography>
          </Box>
        ) : (
          rows.map((row, i) => (
            <Box key={row.id} sx={{ px: 2.5, py: 1.75, borderBottom: i < rows.length - 1 ? '1px solid' : 'none', borderColor: 'divider' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                <Typography fontSize="0.78rem" color="text.disabled">
                  {new Date(row.sent_at).toLocaleString()}
                </Typography>
                {row.provider && (
                  <Chip label={row.provider} size="small" sx={{ fontSize: '0.68rem', height: 18 }} />
                )}
              </Box>
              <Typography fontSize="0.84rem" color="text.secondary" sx={{ whiteSpace: 'pre-wrap' }}>
                {row.content_preview || '(no preview)'}
              </Typography>
            </Box>
          ))
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} size="small">Close</Button>
      </DialogActions>
    </Dialog>
  );
}

function GroupDigestCard({ group, onSaved }) {
  const digest = group.digest || {};
  const [enabled, setEnabled] = useState(digest.enabled ?? false);
  const [frequency, setFrequency] = useState(digest.frequency || 'daily');
  const [scheduleTime, setScheduleTime] = useState(digest.schedule_time || '09:00');
  const [delivery, setDelivery] = useState(digest.delivery || 'dm');
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [sendMsg, setSendMsg] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);

  const dirty = (
    enabled !== (digest.enabled ?? false) ||
    frequency !== (digest.frequency || 'daily') ||
    scheduleTime !== (digest.schedule_time || '09:00') ||
    delivery !== (digest.delivery || 'dm')
  );

  const handleSave = async () => {
    setSaving(true);
    setSaveError('');
    try {
      await digests.update(group.group_id, { enabled, frequency, schedule_time: scheduleTime, delivery });
      onSaved();
    } catch (e) {
      setSaveError(e?.response?.data?.error || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleSendNow = async () => {
    setSending(true);
    setSendMsg('');
    try {
      await digests.sendNow(group.group_id);
      setSendMsg('Digest sent!');
      onSaved();
    } catch (e) {
      setSendMsg(e?.response?.data?.error || 'Failed to send');
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          {/* Header */}
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <StatusDot status={group.bot_status} />
              <Typography fontWeight={600} fontSize="0.95rem">{group.group_title}</Typography>
            </Box>
            <FormControlLabel
              control={
                <Switch
                  checked={enabled}
                  onChange={e => setEnabled(e.target.checked)}
                  size="small"
                />
              }
              label={<Typography fontSize="0.8rem">{enabled ? 'Enabled' : 'Disabled'}</Typography>}
              labelPlacement="start"
            />
          </Box>

          <Divider sx={{ mb: 2 }} />

          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 1.5 }}>
            {/* Frequency */}
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Schedule</InputLabel>
              <Select
                value={frequency}
                label="Schedule"
                onChange={e => setFrequency(e.target.value)}
                disabled={!enabled}
              >
                {FREQUENCIES.map(f => (
                  <MenuItem key={f.value} value={f.value}>{f.label}</MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Time */}
            <TextField
              label="At"
              type="time"
              size="small"
              value={scheduleTime}
              onChange={e => setScheduleTime(e.target.value)}
              disabled={!enabled}
              InputLabelProps={{ shrink: true }}
              sx={{ width: 130 }}
            />

            {/* Delivery */}
            <Box>
              <Typography fontSize="0.72rem" color="text.secondary" mb={0.25}>Delivery</Typography>
              <ToggleButtonGroup
                value={delivery}
                exclusive
                onChange={(_, v) => v && setDelivery(v)}
                size="small"
                disabled={!enabled}
              >
                <ToggleButton value="dm" sx={{ fontSize: '0.75rem', py: 0.5 }}>My DM</ToggleButton>
                <ToggleButton value="group" sx={{ fontSize: '0.75rem', py: 0.5 }}>Group</ToggleButton>
              </ToggleButtonGroup>
            </Box>
          </Box>

          {/* Last sent */}
          {group.last_sent ? (
            <Typography fontSize="0.78rem" color="text.secondary" mb={1.5}>
              Last sent: {relativeTime(group.last_sent.sent_at)}
              {group.last_sent.provider && (
                <Typography component="span" fontSize="0.78rem" color="text.disabled"> · {group.last_sent.provider}</Typography>
              )}
            </Typography>
          ) : (
            <Typography fontSize="0.78rem" color="text.disabled" mb={1.5}>Never sent</Typography>
          )}

          {saveError && <Alert severity="error" sx={{ mb: 1, fontSize: '0.8rem' }}>{saveError}</Alert>}
          {sendMsg && (
            <Alert severity={sendMsg === 'Digest sent!' ? 'success' : 'error'} sx={{ mb: 1, fontSize: '0.8rem' }}>
              {sendMsg}
            </Alert>
          )}

          {/* Actions */}
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {dirty && (
              <Button
                variant="contained"
                size="small"
                onClick={handleSave}
                disabled={saving}
                startIcon={saving ? <CircularProgress size={14} /> : null}
              >
                Save
              </Button>
            )}
            <Button
              variant="outlined"
              size="small"
              startIcon={sending ? <CircularProgress size={14} /> : <Send />}
              onClick={handleSendNow}
              disabled={sending}
            >
              Send Now
            </Button>
            <Button
              variant="text"
              size="small"
              startIcon={<History />}
              onClick={() => setHistoryOpen(true)}
            >
              History
            </Button>
          </Box>
        </CardContent>
      </Card>

      <HistoryDialog
        groupTitle={group.group_title}
        groupId={group.group_id}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
      />
    </>
  );
}

export default function AssistantDigests() {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await digests.getAll();
      setGroups(data.groups || []);
    } catch {
      setError('Failed to load digests.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <Box sx={{ p: 3, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
        <CircularProgress size={32} />
      </Box>
    );
  }

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 760, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Typography variant="h5" fontWeight={700}>Digests</Typography>
      </Box>
      <Typography color="text.secondary" fontSize="0.9rem" mb={3}>
        AI-powered summaries of your group activity, delivered to your DM or group.
      </Typography>

      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      {groups.length === 0 ? (
        <Card variant="outlined">
          <CardContent sx={{ textAlign: 'center', py: 5 }}>
            <Summarize sx={{ fontSize: 48, color: 'text.disabled', mb: 1.5 }} />
            <Typography fontWeight={600} mb={0.5}>No groups connected yet</Typography>
            <Typography color="text.secondary" fontSize="0.88rem" mb={2.5}>
              Add the bot to a Telegram group to start generating AI digests.
            </Typography>
            <Button
              variant="contained"
              size="small"
              startIcon={<AddCircleOutline />}
              onClick={() => navigate('/groups')}
            >
              Connect a Group
            </Button>
          </CardContent>
        </Card>
      ) : (
        groups.map(g => (
          <GroupDigestCard key={g.group_id} group={g} onSaved={load} />
        ))
      )}
    </Box>
  );
}
