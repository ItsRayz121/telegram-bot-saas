import React, { useState } from 'react';
import { Alert, Avatar, Box, Chip, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { MessagePreview } from './MessagePreview';

// Previews for messages whose text is fixed in the bot (not authored by the admin). The wording below is
// copied from the sending code, so when that code changes, change it here too:
//   verification : backend/official_bot.py (_send_verification_challenge) and backend/bot_features/verification.py
//   notices      : backend/official_bot.py (_automod_execute) and backend/bot_features/moderation.py (execute_automod_action)
// Nothing here triggers a verification, a rule or a notice; every control is inert.

const SAMPLE_USER = 'Alex';

export function VerificationPreview({ official, method, timeoutSeconds, maxAttempts, groupName }) {
  const timeout = Number(timeoutSeconds) > 0 ? Number(timeoutSeconds) : 300;
  const attempts = Number(maxAttempts) > 0 ? Number(maxAttempts) : 3;
  const group = groupName || 'Your group';
  const math = method === 'math';
  const buttons = math ? [[{ text: '19' }, { text: '14' }], [{ text: '22' }, { text: '17' }]] : [[{ text: '✅ I am human — Click to verify' }]];
  let text; let props;
  if (official) {
    // Official bot: the button challenge is plain text; the math challenge is Markdown.
    text = math
      ? `🔢 Welcome ${SAMPLE_USER}!\n\nSolve to verify: *7 + 12 = ?*\nYou have ${timeout}s.`
      : `👋 Welcome ${SAMPLE_USER}!\n\nClick the button below to verify you're human.\nYou have ${timeout} seconds.`;
    props = math ? {} : { plain: true };
  } else {
    // Custom bots: HTML.
    text = math
      ? `🔢 Welcome to <b>${group}</b>! ${SAMPLE_USER}, solve this to verify:\n\n<b>7 + 12 = ?</b>\n\nYou have ${timeout} seconds. Attempts: 0/${attempts}`
      : `👋 Welcome to <b>${group}</b>, ${SAMPLE_USER}!\n\nPlease click the button below to verify you're human.\nYou have ${timeout} seconds.`;
    props = { html: true };
  }
  return (
    <MessagePreview platform="telegram" syntax="none" kind="verification message" text={text} buttons={buttons} {...props}
      destination="Posted when a new member joins (the member is restricted until they answer)"
      notes={math ? ['The four numbers are sample answer buttons: the real ones are shuffled each time and only one is correct.'] : []} />
  );
}

export function ModerationNoticePreview({ official, rule = 'spam', muteMinutes = 10, autoDeleteSeconds, autoDelete = true }) {
  const [kind, setKind] = useState('delete');
  const label = String(rule).replace(/_/g, ' ');
  const text = {
    delete: official ? `⚠️ ${SAMPLE_USER}, your message was removed: ${label}.` : `⚠️ @alex_m: ${label} (Warning 1)`,
    mute: official ? `🔇 ${SAMPLE_USER} muted ${muteMinutes}min: ${label}.` : `🔇 @alex_m muted for ${muteMinutes}m: ${label}`,
  }[kind];
  return (
    <Box>
      <ToggleButtonGroup size="small" exclusive value={kind} onChange={(_, v) => v && setKind(v)} aria-label="Notice type" sx={{ mb: 1 }}>
        <ToggleButton value="delete" sx={{ textTransform: 'none' }}>Message removed / warned</ToggleButton>
        <ToggleButton value="mute" sx={{ textTransform: 'none' }}>Member muted</ToggleButton>
      </ToggleButtonGroup>
      <MessagePreview platform="telegram" syntax="none" plain kind="notice" text={text}
        destination={autoDelete && autoDeleteSeconds > 0 ? `Posted in the group, removed after ${autoDeleteSeconds}s` : 'Posted in the group and left in place'}
        notes={['The wording of these notices is built into the bot; it cannot be edited. The notice appears only when a rule actually fires.']} />
    </Box>
  );
}

// Telegram poll bubble. Rendered from the draft only; the options are not interactive and nothing is sent.
export function PollPreview({ form }) {
  const options = (form.options || []).map((o) => (o || '').trim());
  const filled = options.filter(Boolean);
  const problems = [];
  if ((form.question || '').length > 300) problems.push('Telegram allows at most 300 characters in a poll question.');
  if (options.some((o) => o.length > 100)) problems.push('Telegram allows at most 100 characters per option.');
  if (filled.length < 2) problems.push('A poll needs at least two non-empty options.');
  if (form.is_quiz && (form.explanation || '').length > 200) problems.push('Telegram allows at most 200 characters in a quiz explanation.');
  const quiz = !!form.is_quiz;
  const correct = Number(form.correct_option_index);
  return (
    <Box data-testid="poll-preview">
      <Stack direction="row" spacing={0.75} alignItems="center" useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
        <Chip size="small" color="warning" variant="outlined" label="Preview — not sent" />
        <Chip size="small" variant="outlined" label="Telegram" />
        <Typography variant="caption" color="text.secondary">{quiz ? 'Quiz' : 'Poll'} · {form.is_anonymous ? 'anonymous' : 'public votes'}{!quiz && form.allows_multiple ? ' · multiple answers' : ''}</Typography>
      </Stack>
      <Box sx={{ bgcolor: '#0e1621', borderRadius: 2, p: 1.5 }}>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
          <Avatar sx={{ width: 30, height: 30, bgcolor: 'primary.main', fontSize: 13 }}>T</Avatar>
          <Box sx={{ maxWidth: 440, width: '100%', bgcolor: '#182533', color: '#e8edf5', borderRadius: '14px 14px 14px 4px', px: 1.75, py: 1.25 }}>
            <Typography variant="body2" sx={{ fontWeight: 700, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{form.question || 'Your question appears here'}</Typography>
            <Typography variant="caption" sx={{ color: '#7f91a4', display: 'block', mb: 0.75 }}>
              {quiz ? 'Quiz' : form.is_anonymous ? 'Anonymous poll' : 'Poll'}{!quiz && form.allows_multiple ? ' · select one or more' : ''}
            </Typography>
            {(options.length ? options : ['', '']).map((o, i) => (
              <Box key={i} aria-hidden="true" sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.5 }}>
                <Box sx={{ width: 16, height: 16, flexShrink: 0, borderRadius: !quiz && form.allows_multiple ? 0.5 : '50%', border: '2px solid #6ab3f3' }} />
                <Typography variant="body2" sx={{ wordBreak: 'break-word', color: o ? 'inherit' : '#7f91a4' }}>{o || `Option ${i + 1}`}</Typography>
              </Box>
            ))}
          </Box>
        </Box>
      </Box>
      {quiz && filled.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          Correct answer (members only see it after answering): <strong>{options[correct] || `Option ${correct + 1}`}</strong>
          {form.explanation ? <> · Explanation shown after answering: “{form.explanation}”</> : null}
        </Typography>
      )}
      {problems.map((p) => <Alert key={p} severity="warning" sx={{ mt: 1, py: 0 }}>{p}</Alert>)}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
        Options are not clickable here and no votes are cast. The final look can differ slightly between apps and devices.
      </Typography>
    </Box>
  );
}
