import React from 'react';
import { TextField } from '@mui/material';

export const MAX_INVITE_XP = 1000;

// What the settings page stores for whatever was typed: a whole number from 0 to 1000, and 0 (= off) for blank or junk.
export function clampInviteXp(raw) {
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(MAX_INVITE_XP, n));
}

// "XP per invite" for the Telegram invite-links tab. Members get their own link with /myinvite; every new person who joins
// with it earns that member this much XP. 0 is off. Saved with the rest of the page's settings (invites.xp_per_invite).
export default function InviteRewardField({ value, onChange }) {
  return (
    <TextField
      fullWidth
      type="number"
      label="XP per invite"
      value={value ?? 0}
      inputProps={{ min: 0, max: MAX_INVITE_XP, step: 1 }}
      onChange={(e) => onChange(clampInviteXp(e.target.value))}
      helperText={'XP a member earns for each new person who joins with their personal link (members get it by sending /myinvite). '
        + '0 turns it off. Each person is rewarded once, no XP for inviting yourself, and the XP & Levels system must be on.'}
    />
  );
}
