import React, { useState } from 'react';
import { Alert, Box, Button, Collapse, Link, Typography } from '@mui/material';
import { ExpandLess, ExpandMore, OpenInNew } from '@mui/icons-material';

// Replaces the retired bot-enforced slow mode. Telegram's own Slow Mode can only be switched on by a
// human admin inside Telegram (the API method is user-only), so this is a guide, not a control: nothing
// here changes any Telegizer setting.
const STEPS = [
  {
    title: 'Open the group in Telegram',
    body: 'Open the Telegram app and select the group you manage.',
  },
  {
    title: 'Open the group information',
    body: 'Tap (mobile) or click (desktop) the group name at the top of the chat, then choose Edit (the pencil icon) or Manage Group. On Telegram Desktop and Web the name opens a side panel with a pencil or "Manage" option.',
  },
  {
    title: 'Open Permissions',
    body: 'Choose Permissions (sometimes shown as "Group Permissions"). Menu names and placement differ a little between iOS, Android, Desktop and Web.',
  },
  {
    title: 'Find Slow Mode and pick an interval',
    body: 'In the Permissions screen look for the Slow Mode setting: on phones it is usually further down the list of what members can do, on Desktop it is in the same dialog. Choose how long each member must wait between messages.',
  },
  {
    title: 'Save',
    body: 'Confirm with the app\'s Done, Save or checkmark button. Telegram then shows members a countdown until they can post again.',
  },
];

export default function SlowModeGuide({ groupUsername, hasLegacySetting }) {
  const [open, setOpen] = useState(false);
  const [trouble, setTrouble] = useState(false);
  const [dev, setDev] = useState(false);
  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        <b>Slow Mode</b> makes each member wait between messages. It is a Telegram feature, so Telegram itself
        enforces it for every member (and shows them a countdown). It is switched on inside Telegram by the group
        owner or an administrator, not from Telegizer.
      </Typography>

      <Button size="small" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="slow-mode-steps"
        endIcon={open ? <ExpandLess /> : <ExpandMore />}>
        How to enable it
      </Button>
      {groupUsername && (
        <Button size="small" component="a" href={`https://t.me/${String(groupUsername).replace(/^@/, '')}`} target="_blank"
          rel="noopener noreferrer" endIcon={<OpenInNew fontSize="small" />} sx={{ ml: 1 }}>
          Open this group in Telegram
        </Button>
      )}
      <Collapse in={open} unmountOnExit>
        <Box id="slow-mode-steps" sx={{ mt: 1 }}>
          <Box component="ol" sx={{ pl: 2.5, m: 0, '& li': { mb: 1.25 } }}>
            {STEPS.map((s) => (
              <li key={s.title}>
                <Typography variant="body2" fontWeight={700} component="span">{s.title}. </Typography>
                <Typography variant="body2" color="text.secondary" component="span">{s.body}</Typography>
              </li>
            ))}
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            Telegram changes its menus from time to time; if a label differs, look for the same idea. The link above
            only opens the group; Telegram does not offer a link straight to its Permissions screen.
          </Typography>

          <Button size="small" onClick={() => setTrouble((o) => !o)} aria-expanded={trouble} sx={{ mt: 1 }}
            endIcon={trouble ? <ExpandLess /> : <ExpandMore />}>
            Can't see Permissions or Slow Mode?
          </Button>
          <Collapse in={trouble} unmountOnExit>
            <Box component="ul" sx={{ pl: 2.5, m: 0, mt: 0.5, '& li': { mb: 0.5 } }}>
              <li><Typography variant="body2" color="text.secondary">You must be the owner or an administrator who is allowed to change group permissions. Ask the owner to give you that right, or ask them to do these steps.</Typography></li>
              <li><Typography variant="body2" color="text.secondary">Slow Mode applies to groups. It is not offered for broadcast channels or one-to-one chats.</Typography></li>
              <li><Typography variant="body2" color="text.secondary">Update the Telegram app, or try Telegram Desktop or Web: older clients can hide newer settings.</Typography></li>
            </Box>
          </Collapse>
        </Box>
      </Collapse>

      <Alert severity="info" icon={false} sx={{ mt: 1.5, '& .MuiAlert-message': { width: '100%' } }}>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>Using it together with Telegizer</Typography>
        <Box component="ul" sx={{ pl: 2.25, m: 0, '& li': { mb: 0.5 } }}>
          <li><Typography variant="body2">Telegram handles the wait between messages.</Typography></li>
          <li><Typography variant="body2">Your other Telegizer moderation rules (spam, links, bad words, verification, warnings) keep doing their own jobs on the messages Telegram lets through.</Typography></li>
          <li><Typography variant="body2">Telegizer's own cooldown has been retired and stays off, so the same wait is never enforced twice.</Typography></li>
          <li><Typography variant="body2">Those other rules can still mute or restrict a member for their own reasons (for example Spam Detection mutes after repeated bursts of messages). With Slow Mode on, a member cannot send messages fast enough to trigger a burst rule, but other rules are unaffected.</Typography></li>
          <li><Typography variant="body2">Who is exempt from Slow Mode is decided by Telegram (owner and administrators). Telegizer member levels and trusted-user lists do not change it.</Typography></li>
        </Box>
        {hasLegacySetting && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            This group has an older Telegizer slow-mode setting saved. It is kept but does nothing: no messages are deleted
            and no one is restricted or notified because of it.
          </Typography>
        )}
      </Alert>

      <Box sx={{ mt: 1 }}>
        <Button size="small" onClick={() => setDev((o) => !o)} aria-expanded={dev} endIcon={dev ? <ExpandLess /> : <ExpandMore />}>
          Technical notes
        </Button>
        <Collapse in={dev} unmountOnExit>
          <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
            Telegram's Slow Mode is set with the user-only API method{' '}
            <Link href="https://core.telegram.org/method/channels.toggleSlowMode" target="_blank" rel="noopener noreferrer">channels.toggleSlowMode</Link>;
            the Bot API has no equivalent, so a bot cannot switch it on. A bot-made cooldown would have to delete messages and call{' '}
            <Link href="https://core.telegram.org/bots/api#restrictchatmember" target="_blank" rel="noopener noreferrer">restrictChatMember</Link>,
            and Telegram treats a restriction shorter than 30 seconds as permanent, which made short cooldowns unreliable.
            Official description of the feature:{' '}
            <Link href="https://telegram.org/blog/silent-messages-slow-mode" target="_blank" rel="noopener noreferrer">Telegram blog: Slow Mode</Link>.
          </Typography>
        </Collapse>
      </Box>
    </Box>
  );
}
