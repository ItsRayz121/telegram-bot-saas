import React, { useState, useEffect } from 'react';
import {
  FormControl, InputLabel, Select, MenuItem, TextField,
  Box, Typography, CircularProgress, Tooltip, IconButton,
} from '@mui/material';
import { Refresh } from '@mui/icons-material';
import { settings as settingsApi } from '../services/api';

/**
 * Compact forum topic selector.
 *
 * Props:
 *   botId        – 'official' | integer bot ID
 *   groupId      – group ID string
 *   value        – current topic ID (number | null)
 *   onChange     – (topicId: number | null) => void
 *   label        – input label (default "Forum Topic")
 *   helperText   – shown below the selector
 */

function parseTopicInput(val) {
  if (!val || !val.trim()) return null;
  // Extract from Telegram topic links: t.me/c/CHATID/THREAD_ID or any URL ending in /NUMBER
  const match = val.match(/\/(\d+)\/?$/);
  if (match) return parseInt(match[1], 10);
  const n = parseInt(val, 10);
  return isNaN(n) ? null : n;
}

export default function ForumTopicSelector({ botId, groupId, value, onChange, label = 'Forum Topic', helperText }) {
  const [topics, setTopics] = useState(null); // null = not yet loaded
  const [loading, setLoading] = useState(false);
  const [manualMode, setManualMode] = useState(false);
  const [manualValue, setManualValue] = useState('');

  const load = async () => {
    if (!botId || !groupId) return;
    setLoading(true);
    try {
      const res = await settingsApi.getForumTopics(botId, groupId);
      setTopics(res.data.topics || []);
    } catch {
      setTopics([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [botId, groupId]); // eslint-disable-line

  // If a value is set but not found in discovered topics → show as manual/saved
  const valueInTopics = topics && value
    ? topics.some(t => String(t.thread_id) === String(value))
    : false;
  const hasSavedUnknown = value && topics !== null && !valueInTopics;

  // Select value: '' = main chat, 'manual' = manual entry, number string = topic
  const selectValue = manualMode
    ? 'manual'
    : value
      ? (valueInTopics ? String(value) : 'manual')
      : '';

  const handleSelectChange = (e) => {
    const v = e.target.value;
    if (v === '') {
      setManualMode(false);
      onChange(null);
    } else if (v === 'manual') {
      setManualMode(true);
      setManualValue(value ? String(value) : '');
    } else {
      setManualMode(false);
      onChange(parseInt(v, 10));
    }
  };

  const handleManualChange = (e) => {
    const raw = e.target.value;
    setManualValue(raw);
    // Only fire onChange when we have a confident parse — never call onChange(null) mid-type,
    // because incomplete URLs (e.g. "https://t.me") would wipe a previously saved ID.
    const parsed = parseTopicInput(raw);
    if (parsed !== null && parsed !== value) onChange(parsed);
  };

  const handleManualBlur = () => {
    // On blur, always commit the final parsed value (including null to clear)
    const parsed = parseTopicInput(manualValue);
    onChange(parsed);
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <FormControl size="small" fullWidth>
          <InputLabel>{label}</InputLabel>
          <Select value={selectValue} label={label} onChange={handleSelectChange}>
            <MenuItem value="">Main group chat</MenuItem>

            {loading && (
              <MenuItem disabled>
                <CircularProgress size={14} sx={{ mr: 1 }} /> Detecting topics…
              </MenuItem>
            )}

            {!loading && topics && topics.length === 0 && (
              <MenuItem disabled sx={{ fontStyle: 'italic', fontSize: '0.82rem' }}>
                No topics detected yet
              </MenuItem>
            )}

            {!loading && topics && topics.map(t => (
              <MenuItem key={t.thread_id} value={String(t.thread_id)}>
                {t.is_closed ? '🔒 ' : ''}{t.name}
                <Typography variant="caption" color="text.secondary" sx={{ ml: 0.75 }}>
                  #{t.thread_id}
                </Typography>
              </MenuItem>
            ))}

            {hasSavedUnknown && !manualMode && (
              <MenuItem value="manual">
                Saved topic ID: {value}
              </MenuItem>
            )}

            <MenuItem value="manual" sx={{ fontStyle: 'italic', fontSize: '0.82rem', color: 'text.secondary' }}>
              Enter topic ID or link…
            </MenuItem>
          </Select>
        </FormControl>

        <Tooltip title="Refresh topic list">
          <IconButton size="small" onClick={load} disabled={loading}>
            <Refresh fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {manualMode && (
        <TextField
          size="small"
          fullWidth
          type="text"
          label="Topic ID or link"
          placeholder="e.g. 12345 or https://t.me/c/123/456"
          value={manualValue}
          onChange={handleManualChange}
          onBlur={handleManualBlur}
          sx={{ mt: 1 }}
          helperText="Enter a topic ID or paste a Telegram topic link — ID will be extracted automatically."
        />
      )}

      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
        {helperText || 'Paste a topic link or enter a topic ID. Leave blank for the main group chat.'}
      </Typography>
    </Box>
  );
}
