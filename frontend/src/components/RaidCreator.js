import React, { useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, TextField, Grid, Typography, Box, IconButton,
  Switch, FormControlLabel, CircularProgress, Divider,
} from '@mui/material';
import { Add, Remove } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { settings } from '../services/api';

const DEFAULT_GOALS = { repost: 0, like: 0, reply: 0, bookmark: 0 };

export default function RaidCreator({ open, onClose, botId, groupId }) {
  const [form, setForm] = useState({
    tweet_url: '',
    goals: { ...DEFAULT_GOALS },
    duration_hours: 24,
    xp_reward: 100,
    pin_message: true,
    reminders_enabled: true,
  });
  const [loading, setLoading] = useState(false);

  const handleGoalChange = (key, delta) => {
    setForm((prev) => ({
      ...prev,
      goals: { ...prev.goals, [key]: Math.max(0, (prev.goals[key] || 0) + delta) },
    }));
  };

  const handleChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async () => {
    if (!form.tweet_url.trim()) {
      toast.error('Tweet URL is required');
      return;
    }
    const hasGoal = Object.values(form.goals).some((v) => v > 0);
    if (!hasGoal) {
      toast.error('Set at least one raid goal');
      return;
    }
    setLoading(true);
    try {
      await settings.createRaid(botId, groupId, form);
      toast.success('Raid created! Members will be notified.');
      onClose();
      setForm({
        tweet_url: '',
        goals: { ...DEFAULT_GOALS },
        duration_hours: 24,
        xp_reward: 100,
        pin_message: true,
        reminders_enabled: true,
      });
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to create raid');
    } finally {
      setLoading(false);
    }
  };

  const GoalRow = ({ label, field }) => (
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', py: 0.5 }}>
      <Typography variant="body2">{label}</Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <IconButton size="small" onClick={() => handleGoalChange(field, -1)}>
          <Remove fontSize="small" />
        </IconButton>
        <Typography variant="body1" sx={{ minWidth: 32, textAlign: 'center' }}>
          {form.goals[field]}
        </Typography>
        <IconButton size="small" onClick={() => handleGoalChange(field, 1)}>
          <Add fontSize="small" />
        </IconButton>
      </Box>
    </Box>
  );

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Create Twitter/X Raid</DialogTitle>
      <DialogContent>
        <TextField
          fullWidth
          label="Tweet URL"
          value={form.tweet_url}
          onChange={(e) => handleChange('tweet_url', e.target.value)}
          placeholder="https://twitter.com/user/status/..."
          sx={{ mt: 1, mb: 3 }}
        />

        <Typography variant="subtitle2" fontWeight={600} mb={1}>
          Raid Goals
        </Typography>
        <GoalRow label="Reposts" field="repost" />
        <GoalRow label="Likes" field="like" />
        <GoalRow label="Replies" field="reply" />
        <GoalRow label="Bookmarks" field="bookmark" />

        <Divider sx={{ my: 2 }} />

        <Grid container spacing={2}>
          <Grid item xs={6}>
            <TextField
              fullWidth
              type="number"
              label="Duration (hours)"
              value={form.duration_hours}
              onChange={(e) => handleChange('duration_hours', parseInt(e.target.value) || 24)}
              inputProps={{ min: 1, max: 168 }}
            />
          </Grid>
          <Grid item xs={6}>
            <TextField
              fullWidth
              type="number"
              label="XP Reward"
              value={form.xp_reward}
              onChange={(e) => handleChange('xp_reward', parseInt(e.target.value) || 0)}
              inputProps={{ min: 0 }}
            />
          </Grid>
          <Grid item xs={6}>
            <FormControlLabel
              control={
                <Switch
                  checked={form.pin_message}
                  onChange={(e) => handleChange('pin_message', e.target.checked)}
                />
              }
              label="Pin raid message"
            />
          </Grid>
          <Grid item xs={6}>
            <FormControlLabel
              control={
                <Switch
                  checked={form.reminders_enabled}
                  onChange={(e) => handleChange('reminders_enabled', e.target.checked)}
                />
              }
              label="Send reminders"
            />
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={loading}>
          {loading ? <CircularProgress size={20} color="inherit" /> : 'Launch Raid'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
