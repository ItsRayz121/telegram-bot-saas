/**
 * Per-group settings modal.
 *
 * Sections:
 *   • Display & Category
 *   • Extraction Toggles (tasks / reminders / decisions / meetings)
 *   • Behaviour (status, active mode, silence window)
 *   • Danger Zone (delete data, disconnect)
 */
import React, { useState, useEffect } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, IconButton, Typography, Box, TextField, Divider,
  FormControl, InputLabel, Select, MenuItem, FormControlLabel,
  Switch, CircularProgress, Alert,
} from '@mui/material';
import { Close } from '@mui/icons-material';
import { hub } from '../../services/api';

const CATEGORIES = ['work', 'family', 'project', 'community', 'other'];
const HOURS = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);

export default function GroupSettingsOverlay({ open, group, onClose, onUpdated, onDisconnected }) {
  const [displayName, setDisplayName] = useState('');
  const [category, setCategory] = useState('work');
  const [extractTasks, setExtractTasks] = useState(true);
  const [extractReminders, setExtractReminders] = useState(true);
  const [extractDecisions, setExtractDecisions] = useState(true);
  const [extractMeetings, setExtractMeetings] = useState(true);
  const [status, setStatus] = useState('active');
  const [silenceStart, setSilenceStart] = useState('');
  const [silenceEnd, setSilenceEnd] = useState('');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [dangerLoading, setDangerLoading] = useState(false);

  // Populate fields when group changes
  useEffect(() => {
    if (!group) return;
    setDisplayName(group.display_name || group.group_name || '');
    setCategory(group.category || 'work');
    setExtractTasks(group.extract_tasks !== false);
    setExtractReminders(group.extract_reminders !== false);
    setExtractDecisions(group.extract_decisions !== false);
    setExtractMeetings(group.extract_meetings !== false);
    setStatus(group.is_active ? 'active' : 'paused');
    setSilenceStart(group.silence_window_start || '');
    setSilenceEnd(group.silence_window_end || '');
    setError(null);
    setConfirmDisconnect(false);
    setConfirmDelete(false);
  }, [group]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        display_name: displayName.trim() || null,
        category,
        extract_tasks: extractTasks,
        extract_reminders: extractReminders,
        extract_decisions: extractDecisions,
        extract_meetings: extractMeetings,
        is_active: status === 'active',
        silence_window_start: silenceStart || null,
        silence_window_end: silenceEnd || null,
      };
      const r = await hub.updateGroupSettings(group.id, payload);
      if (onUpdated) onUpdated(r.data.group);
      onClose();
    } catch (e) {
      setError(e?.response?.data?.error || 'Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteData = async () => {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    setDangerLoading(true);
    setError(null);
    try {
      await hub.deleteGroupData(group.id);
      setConfirmDelete(false);
      if (onUpdated) onUpdated(group);
      onClose();
    } catch (e) {
      setError(e?.response?.data?.error || 'Failed to delete data.');
    } finally {
      setDangerLoading(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirmDisconnect) { setConfirmDisconnect(true); return; }
    setDangerLoading(true);
    setError(null);
    try {
      await hub.disconnectGroup(group.id);
      if (onDisconnected) onDisconnected(group.id);
      onClose();
    } catch (e) {
      setError(e?.response?.data?.error || 'Failed to disconnect group.');
    } finally {
      setDangerLoading(false);
    }
  };

  if (!group) return null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>
        Group Settings
        <IconButton onClick={onClose} size="small" sx={{ position: 'absolute', right: 8, top: 8 }}>
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent dividers sx={{ pb: 2 }}>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {/* Display & Category */}
        <SectionLabel>Display & Category</SectionLabel>
        <TextField
          label="Display Name"
          size="small"
          fullWidth
          sx={{ mb: 1.5 }}
          value={displayName}
          onChange={e => setDisplayName(e.target.value)}
          inputProps={{ maxLength: 80 }}
          placeholder={group.group_name || ''}
        />
        <FormControl size="small" fullWidth sx={{ mb: 2 }}>
          <InputLabel>Category</InputLabel>
          <Select value={category} label="Category" onChange={e => setCategory(e.target.value)}>
            {CATEGORIES.map(c => (
              <MenuItem key={c} value={c} sx={{ textTransform: 'capitalize' }}>{c}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Divider sx={{ mb: 2 }} />

        {/* Extraction Toggles */}
        <SectionLabel>What to extract</SectionLabel>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, mb: 2 }}>
          <ToggleRow label="Tasks & action items" checked={extractTasks} onChange={setExtractTasks} />
          <ToggleRow label="Reminders & deadlines" checked={extractReminders} onChange={setExtractReminders} />
          <ToggleRow label="Decisions" checked={extractDecisions} onChange={setExtractDecisions} />
          <ToggleRow label="Meetings" checked={extractMeetings} onChange={setExtractMeetings} />
        </Box>

        <Divider sx={{ mb: 2 }} />

        {/* Behaviour */}
        <SectionLabel>Behaviour</SectionLabel>
        <FormControl size="small" fullWidth sx={{ mb: 1.5 }}>
          <InputLabel>Status</InputLabel>
          <Select value={status} label="Status" onChange={e => setStatus(e.target.value)}>
            <MenuItem value="active">Active</MenuItem>
            <MenuItem value="paused">Paused</MenuItem>
          </Select>
        </FormControl>

        <Typography variant="body2" fontWeight={500} mb={0.5}>Silence Window</Typography>
        <Typography variant="caption" color="text.secondary" display="block" mb={1}>
          No extractions between these hours (leave blank to disable)
        </Typography>
        <Box sx={{ display: 'flex', gap: 1.5, mb: 2 }}>
          <FormControl size="small" sx={{ flex: 1 }}>
            <InputLabel>From</InputLabel>
            <Select value={silenceStart} label="From" onChange={e => setSilenceStart(e.target.value)}>
              <MenuItem value=""><em>None</em></MenuItem>
              {HOURS.map(h => <MenuItem key={h} value={h}>{h}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ flex: 1 }}>
            <InputLabel>To</InputLabel>
            <Select value={silenceEnd} label="To" onChange={e => setSilenceEnd(e.target.value)}>
              <MenuItem value=""><em>None</em></MenuItem>
              {HOURS.map(h => <MenuItem key={h} value={h}>{h}</MenuItem>)}
            </Select>
          </FormControl>
        </Box>

        <Divider sx={{ mb: 2 }} />

        {/* Danger Zone */}
        <SectionLabel color="error.main">Danger Zone</SectionLabel>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button
            variant="outlined"
            size="small"
            color="warning"
            disabled={dangerLoading}
            onClick={handleDeleteData}
          >
            {dangerLoading && confirmDelete ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}
            {confirmDelete ? 'Confirm — delete data?' : 'Delete data from this group'}
          </Button>
          <Button
            variant="outlined"
            size="small"
            color="error"
            disabled={dangerLoading}
            onClick={handleDisconnect}
          >
            {dangerLoading && confirmDisconnect ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}
            {confirmDisconnect ? 'Confirm — disconnect?' : 'Disconnect group'}
          </Button>
        </Box>
        {(confirmDelete || confirmDisconnect) && (
          <Typography variant="caption" color="error" display="block" mt={0.75}>
            Click again to confirm. This cannot be undone.
          </Typography>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} size="small" color="inherit">Cancel</Button>
        <Button onClick={handleSave} variant="contained" size="small" disabled={saving}>
          {saving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function SectionLabel({ children, color = 'text.secondary' }) {
  return (
    <Typography
      variant="caption"
      fontWeight={700}
      color={color}
      sx={{ display: 'block', mb: 1, textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: '0.68rem' }}
    >
      {children}
    </Typography>
  );
}

function ToggleRow({ label, checked, onChange }) {
  return (
    <FormControlLabel
      control={<Switch checked={checked} onChange={e => onChange(e.target.checked)} size="small" />}
      label={<Typography variant="body2">{label}</Typography>}
      sx={{ m: 0 }}
    />
  );
}
