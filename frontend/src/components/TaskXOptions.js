// Per-task X (Twitter) options for multi-task campaigns, shared by the Telegram and
// Discord campaign editors so both behave identically: targets for each action and
// an "Auto-verify on X" switch (Pro), stored in the task's `settings`.
import React from 'react';
import { Box, Chip, Grid, Switch, TextField, Tooltip, Typography } from '@mui/material';
import { InfoOutlined } from '@mui/icons-material';

/** A small (i) icon with a short explanation. Keyboard-focusable; the text is also its accessible name. */
export function HelpTip({ text }) {
  return (
    <Tooltip title={text} arrow enterTouchDelay={0} leaveTouchDelay={6000}>
      <Box component="span" tabIndex={0} role="img" aria-label={text}
        sx={{ display: 'inline-flex', verticalAlign: 'middle', color: 'text.secondary', cursor: 'help' }}>
        <InfoOutlined sx={{ fontSize: 16 }} />
      </Box>
    </Tooltip>
  );
}

export const X_HELP = 'Needs a Twitter API key and a Pro or Enterprise plan (each check uses X API credits). '
  + 'Likes cannot be read from X, so they stay honor-based. If a check is unsure, it waits for your review.';

export const RAID_GOALS = [
  { key: 'likes', label: 'Likes' },
  { key: 'retweets', label: 'Retweets' },
  { key: 'comments', label: 'Comments' },
  { key: 'quotes', label: 'Quote tweets' },
  { key: 'follows', label: 'Follows' },
];

// A task can be checked on X when it's a Twitter raid or an X social task.
export const taskIsX = (t) => t.type === 'raid'
  || (t.type === 'social_task' && ['x', 'twitter'].includes((t.platform || '').toLowerCase()));

export const taskAutoOn = (t) => !!(t.settings || {}).auto_verify_x;

// The proof field added when auto-verify is switched on, so the bot knows whose X
// account to check. Telegram remembers the handle, so it can be left empty there.
const handleField = (remembered) => ({
  label: 'Your X @username',
  field_type: 'username',
  required: !remembered,
  example: remembered ? 'Leave empty to use the handle you saved before' : '@yourname',
});

// Smart defaults when a task's type / platform changes, so the common case is
// automatic: an X task starts with auto-verify ON (Pro) and its handle field, and a
// join-your-own-community task (Telegram / Discord platform) starts on automatic
// membership verification. Only fills in what is still at its untouched default.
export function smartTaskDefaults(next, { isPaid, rememberedHandle = false, joinPlatform }) {
  const patch = {};
  if (taskIsX(next) && isPaid && !('auto_verify_x' in (next.settings || {}))) {
    patch.settings = { ...(next.settings || {}), auto_verify_x: true };
    const fields = next.custom_fields || [];
    if (!fields.some((f) => f.field_type === 'username')) {
      patch.custom_fields = [...fields, handleField(rememberedHandle)];
    }
  }
  if (joinPlatform && (next.platform || '') === joinPlatform && next.verification_mode === 'manual') {
    patch.verification_mode = 'auto';
  }
  return patch;
}

// What we send as a task's settings: only X-capable tasks carry the X options.
export function taskSettingsPayload(t, isPaid) {
  const s = { ...(t.settings || {}) };
  if (!String(s.button_label || '').trim()) delete s.button_label;
  if (!taskIsX(t)) { delete s.raid_goals; delete s.auto_verify_x; return s; }
  s.raid_goals = RAID_GOALS.reduce((acc, g) => {
    const n = parseInt((s.raid_goals || {})[g.key], 10);
    if (n > 0) acc[g.key] = n;
    return acc;
  }, {});
  if (!(isPaid && s.auto_verify_x)) delete s.auto_verify_x;
  return s;
}

// "Targets: 5 Retweets, 3 Comments · Auto-verify on X" for a locked task, or ''.
export function lockedXSummary(t) {
  const s = t.settings || {};
  const parts = RAID_GOALS.filter((g) => (s.raid_goals || {})[g.key]).map((g) => `${s.raid_goals[g.key]} ${g.label}`);
  const bits = [];
  if (parts.length) bits.push(`Targets: ${parts.join(', ')}`);
  if (s.auto_verify_x) bits.push('Auto-verify on X');
  return bits.join(' · ');
}

export default function TaskXOptions({ task, onPatch, isPaid, rememberedHandle = false }) {
  const s = task.settings || {};
  const goals = s.raid_goals || {};
  const setSettings = (next) => onPatch({ settings: { ...s, ...next } });
  const toggleAuto = (on) => {
    const patch = { settings: { ...s, auto_verify_x: on } };
    const fields = task.custom_fields || [];
    if (on && !fields.some((f) => f.field_type === 'username')) {
      patch.custom_fields = [...fields, handleField(rememberedHandle)];
    }
    onPatch(patch);
  };
  return (
    <Box sx={{ border: '1px dashed', borderColor: 'divider', borderRadius: 1, p: 1.25 }}>
      <Typography variant="caption" color="text.secondary">
        Targets (optional): how many of each action you want. Leave a box empty to skip it.
      </Typography>
      <Grid container spacing={1} sx={{ mt: 0.25 }}>
        {RAID_GOALS.map((g) => (
          <Grid item xs={6} key={g.key}>
            <TextField fullWidth size="small" type="number" label={g.label}
              value={goals[g.key] || ''} inputProps={{ min: 0 }}
              onChange={(e) => setSettings({ raid_goals: { ...goals, [g.key]: e.target.value } })} />
          </Grid>
        ))}
      </Grid>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mt: 1 }}>
        <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
          Auto-verify on X <Chip size="small" label="Pro" color={isPaid ? 'default' : 'warning'} variant="outlined" />
          <HelpTip text={X_HELP} />
        </Typography>
        <Tooltip title={isPaid ? '' : 'Upgrade to Pro or Enterprise to use automatic X verification'}>
          <span>
            <Switch checked={isPaid && taskAutoOn(task)} disabled={!isPaid}
              onChange={(e) => toggleAuto(e.target.checked)} />
          </span>
        </Tooltip>
      </Box>
      {isPaid && taskAutoOn(task) && !Object.values(goals).some((n) => parseInt(n, 10) > 0) && (
        <Typography variant="caption" color="warning.main" display="block" sx={{ mt: 0.5 }}>
          Set at least one target above (for example Follows: 1) or there is nothing to check automatically.
          {task.type === 'raid' || (task.task_url || '').includes('/status/')
            ? '' : " For a Follow task, paste the account's profile link (https://x.com/Name) as the task link."}
        </Typography>
      )}
      {!isPaid && (
        <Typography variant="caption" color="text.secondary" display="block">
          Free plan: this task goes to manual review. Upgrade to verify it automatically.
        </Typography>
      )}
    </Box>
  );
}
