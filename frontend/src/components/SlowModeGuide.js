import React from 'react';
import { Box, Button, Typography } from '@mui/material';
import { OpenInNew } from '@mui/icons-material';

// Replaces the retired bot-enforced slow mode. Telegram's own Slow Mode can only be switched on by a
// human admin inside Telegram (the API method is user-only), so this is a guide, not a control: nothing
// here changes any Telegizer setting.
const STEPS = [
  ['Open your group', 'and tap its name/title at the top to open Group Info.'],
  ['Tap Edit', '(the pencil icon).'],
  ['Open Permissions', '(the lock / key icon).'],
  ['Scroll down to Slow Mode', 'and pick an interval (5s – 1h).'],
  ['Done.', 'Telegram now shows every member a per-user "write again in …" timer.'],
];

export default function SlowModeGuide({ groupUsername, hasLegacySetting }) {
  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Slow Mode is a Telegram feature: only a human group admin can switch it on, in Telegram itself.
        Telegram then enforces the wait for every member.
      </Typography>
      <Box component="ol" sx={{ pl: 2.5, m: 0, '& li': { mb: 0.75 } }}>
        {STEPS.map(([title, body]) => (
          <li key={title}>
            <Typography variant="body2" fontWeight={700} component="span">{title} </Typography>
            <Typography variant="body2" color="text.secondary" component="span">{body}</Typography>
          </li>
        ))}
      </Box>
      {groupUsername && (
        <Button size="small" component="a" href={`https://t.me/${String(groupUsername).replace(/^@/, '')}`} target="_blank"
          rel="noopener noreferrer" endIcon={<OpenInNew fontSize="small" />} sx={{ mt: 1 }}>
          Open this group in Telegram
        </Button>
      )}
      {hasLegacySetting && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          This group has an older Telegizer slow-mode setting saved. It is kept but does nothing.
        </Typography>
      )}
    </Box>
  );
}
