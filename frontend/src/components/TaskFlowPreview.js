// Live, clickable preview of how a multi-task campaign's buttons behave in the bot
// (Telegram) or on the channel post (Discord). It is a SIMULATION: nothing is sent,
// saved or verified. It re-renders from the task list the owner is editing, so every
// change (label, link, auto-verify, platform) shows immediately.
//
// The rules below mirror the real bot (backend/engagement.py task_button_label /
// task_panel_kind, backend/engagement_bot.py panel + Verify): keep them in sync.
import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Box, Button, Chip, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { RAID_GOALS, taskIsX, taskAutoOn } from './TaskXOptions';

const TRIES = 3;                      // failed checks before it is handed to the admins
const LABEL_MAX = 28;
const GOAL_LABEL = {
  follows: '🐦 Follow on X', retweets: '🔁 Repost on X', comments: '💬 Comment on X',
  quotes: '🔁 Quote on X', likes: '❤️ Like on X',
};
const PLATFORM_NAME = {
  x: 'X', twitter: 'X', telegram: 'Telegram', discord: 'Discord', youtube: 'YouTube', instagram: 'Instagram',
  tiktok: 'TikTok', facebook: 'Facebook', reddit: 'Reddit', linkedin: 'LinkedIn', medium: 'Medium',
};

/** Short button text for a task, no XP. Same rules as the backend. */
export function taskButtonLabel(t, platform = 'telegram') {
  const s = t.settings || {};
  const custom = String(s.button_label || '').trim();
  if (custom) return custom.slice(0, LABEL_MAX);
  const plat = (t.platform || '').toLowerCase();
  const goals = RAID_GOALS.map((g) => g.key).filter((k) => (s.raid_goals || {})[k] > 0 || parseInt((s.raid_goals || {})[k], 10) > 0);
  const x = t.type === 'raid' || plat === 'x' || plat === 'twitter';
  if (x && goals.length === 1) return GOAL_LABEL[goals[0]];
  if (x && goals.length) return '🐦 X task';
  const title = (t.title || '').trim();
  const low = title.toLowerCase();
  const pname = PLATFORM_NAME[plat];
  const word = low.includes('channel') ? 'channel'
    : platform === 'discord' ? (low.includes('server') ? 'server' : low.includes('group') ? 'group' : '')
      : (low.includes('community') ? 'community' : low.includes('group') ? 'group' : '');
  if (low.startsWith('join') && pname) {
    return `${plat === 'telegram' && platform === 'telegram' ? '✈️ ' : ''}Join ${pname}${word ? ` ${word}` : ''}`.slice(0, LABEL_MAX);
  }
  const verbs = [['follow', 'Follow'], ['subscribe', 'Subscribe'], ['retweet', 'Repost'], ['repost', 'Repost'], ['like', 'Like'], ['comment', 'Comment']];
  for (const [v, label] of verbs) {
    if (low.startsWith(v) && pname) return `${x ? '🐦 ' : ''}${label} on ${pname}`.slice(0, LABEL_MAX);
  }
  const cut = title.split(':')[0].split(' – ')[0].split(' - ')[0].trim() || title || 'Task';
  return cut.length <= LABEL_MAX ? cut : `${cut.slice(0, LABEL_MAX - 1).trimEnd()}…`;
}

/** "x" | "join" | null: how a member completes the task with buttons alone. */
export function taskPanelKind(t, { isPaid = true, keyReady = true } = {}) {
  if ((t.custom_fields || []).some((f) => f.field_type !== 'username')) return null;
  const goals = ((t.settings || {}).raid_goals) || {};
  const hasGoal = RAID_GOALS.some((g) => parseInt(goals[g.key], 10) > 0);
  if (taskIsX(t) && taskAutoOn(t) && hasGoal) return isPaid && keyReady ? 'x' : null;
  if (t.verification_mode === 'auto') return 'join';
  return null;
}

const STYLE = {
  telegram: { bg: '#0e1621', bubble: '#182533', text: '#e8edf5', btn: 'rgba(106,179,243,0.18)', btnText: '#6ab3f3', sub: '#7f91a4', user: '#2b5278' },
  discord: { bg: '#313338', bubble: '#2b2d31', text: '#dbdee1', btn: '#4e5058', btnText: '#fff', sub: '#949ba4', user: '#404249' },
};

function Bubble({ st, who = 'bot', children }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: who === 'user' ? 'flex-end' : 'flex-start', my: 0.75 }}>
      <Box sx={{
        maxWidth: '88%', bgcolor: who === 'user' ? st.user : st.bubble, color: st.text, px: 1.5, py: 1, fontSize: 14, lineHeight: 1.45,
        borderRadius: who === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
      }}>{children}</Box>
    </Box>
  );
}

function Btn({ st, platform, children, onClick, kind = 'normal', title, disabled }) {
  const discordColor = kind === 'verify' ? '#248046' : kind === 'link' ? '#4e5058' : '#5865f2';
  return (
    <Box component="button" type="button" onClick={onClick} disabled={disabled} title={title}
      sx={{
        font: 'inherit', fontSize: 13, border: 0, cursor: disabled ? 'default' : 'pointer', borderRadius: platform === 'discord' ? 1 : 1.5,
        px: 1.25, py: 0.7, flex: 1, textAlign: 'center', opacity: disabled ? 0.5 : 1,
        bgcolor: platform === 'discord' ? discordColor : st.btn, color: platform === 'discord' ? '#fff' : st.btnText,
        '&:hover': { filter: disabled ? 'none' : 'brightness(1.15)' },
      }}>
      {children}
    </Box>
  );
}

export default function TaskFlowPreview({ tasks = [], platform = 'telegram', isPaid = true, xStatus, title = 'Your campaign' }) {
  const st = STYLE[platform] || STYLE.telegram;
  const keyReady = xStatus === undefined || xStatus === 'live';
  const list = useMemo(() => (tasks || []).filter((t) => (t.title || '').trim()), [tasks]);
  const [outcome, setOutcome] = useState('pass');        // pass | wait | cannot
  const [sel, setSel] = useState(null);                   // task index the member opened
  const [log, setLog] = useState([]);                     // bubbles after the picker
  const [done, setDone] = useState({});                   // index -> true
  const [tries, setTries] = useState({});

  const reset = () => { setSel(null); setLog([]); setDone({}); setTries({}); };
  // an edit that removes the open task, or reorders enough to matter, restarts the demo
  useEffect(() => { if (sel !== null && !list[sel]) reset(); }, [list, sel]);

  if (!list.length) {
    return <Alert severity="info" icon={false}>Add a task with a title to see how its button will work.</Alert>;
  }

  const open = (i) => {
    if (done[i]) { setLog((l) => [...l, { who: 'bot', text: 'Already verified ✅' }]); return; }
    const t = list[i];
    const kind = taskPanelKind(t, { isPaid, keyReady });
    setSel(i);
    setLog([{ who: 'user', text: taskButtonLabel(t, platform) }, { who: 'panel', i, kind }]);
  };

  const verify = (i, kind) => {
    const t = list[i];
    const xp = parseInt(t.reward_xp, 10) || 0;
    const add = (...m) => setLog((l) => [...l, ...m]);
    if (kind === 'join' && outcome === 'cannot') {
      add({ who: 'bot', text: "I can't check this one automatically right now, so it was sent to the admins for review." });
      return;
    }
    if (outcome === 'pass') {
      setDone((d) => ({ ...d, [i]: true }));
      add({ who: 'bot', text: `✅ Verified!${xp ? ` +${xp} XP added.` : ''} Thanks for taking part.` });
      return;
    }
    if (kind === 'join') {
      add({ who: 'popup', text: "You don't appear to be a member yet. Join first, then tap Verify." });
      return;
    }
    const n = (tries[i] || 0) + 1;
    if (n >= TRIES) {
      setTries((x) => ({ ...x, [i]: 0 }));
      add({ who: 'bot', text: "🕓 I couldn't confirm it yet, so it was sent to the admins. It is also re-checked automatically for the next 30 minutes." });
      return;
    }
    setTries((x) => ({ ...x, [i]: n }));
    add({ who: 'bot', text: `⏳ Not detected yet (${n}/${TRIES}). Do it on X, wait about 30 seconds, then tap Verify again.` });
  };

  const panel = (m, idx) => {
    const t = list[m.i];
    const url = (t.task_url || '').trim();
    if (m.kind === 'x' || m.kind === 'join') {
      const x = m.kind === 'x';
      return (
        <Box key={idx}>
          <Bubble st={st}>
            <strong>{t.title}</strong>{'\n'}
            {x ? '1️⃣ Tap Open on X and do it.' : '1️⃣ Tap Join.'}{'\n'}
            {x ? '2️⃣ Come back and tap Verify. It is checked automatically.' : '2️⃣ Come back and tap Verify.'}
            {x && <>{'\n'}👤 Checking @yourhandle</>}
          </Bubble>
          <Stack spacing={0.5} sx={{ mb: 0.5, maxWidth: '88%' }}>
            {url.startsWith('http') && (
              <Box sx={{ display: 'flex' }}><Btn st={st} platform={platform} kind="link" title={`Opens ${url}`}>{x ? '🐦 Open on X ↗' : '✈️ Join ↗'}</Btn></Box>
            )}
            {!url.startsWith('http') && (
              <Typography variant="caption" sx={{ color: '#ffb74d' }}>
                {x ? 'Add the task link (the tweet or profile) so the Open button appears.' : 'Add the public t.me link so the Join button appears and that chat is checked.'}
              </Typography>
            )}
            <Box sx={{ display: 'flex', gap: 0.5 }}>
              <Btn st={st} platform={platform} kind="verify" onClick={() => verify(m.i, m.kind)}>✅ Verify</Btn>
              {x && <Btn st={st} platform={platform} title="Changes the saved X username">✏️ Change X username</Btn>}
            </Box>
          </Stack>
        </Box>
      );
    }
    // typed / uploaded proof: the normal proof flow
    const fields = t.custom_fields || [];
    const prompts = fields.length ? fields : [{ label: t.verification_mode === 'link' ? 'Proof link' : 'Proof screenshot', field_type: t.verification_mode === 'link' ? 'url' : 'screenshot' }];
    return (
      <Box key={idx}>
        <Bubble st={st}><strong>{t.title}</strong>{'\n'}Let's collect your submission. {prompts.length} step(s).</Bubble>
        {prompts.map((f, k) => (
          <Bubble st={st} key={k}>
            <strong>{f.label || 'Your answer'}</strong>{'\n'}
            {f.field_type === 'screenshot' ? '📷 Please upload a screenshot (photo).' : f.field_type === 'url' ? '🔗 Please submit the link.' : 'Please type your answer.'}
          </Bubble>
        ))}
        <Typography variant="caption" sx={{ color: st.sub, display: 'block', mb: 0.5 }}>
          This task needs typed or uploaded proof, so it uses the normal chat flow and goes to review.
          {taskIsX(t) && taskAutoOn(t) && !keyReady ? ' Auto-verify on X is on, but no working Twitter API key was found.' : ''}
          {taskIsX(t) && taskAutoOn(t) && !isPaid ? ' Auto-verify on X needs a Pro plan.' : ''}
        </Typography>
      </Box>
    );
  };

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
        <Typography variant="body2" color="text.secondary">If the check…</Typography>
        <ToggleButtonGroup size="small" exclusive value={outcome} onChange={(_, v) => v && setOutcome(v)} aria-label="Simulated check result">
          <ToggleButton value="pass" sx={{ textTransform: 'none' }}>✅ passes</ToggleButton>
          <ToggleButton value="wait" sx={{ textTransform: 'none' }}>⏳ finds nothing yet</ToggleButton>
          <ToggleButton value="cannot" sx={{ textTransform: 'none' }}>🤖 bot can't see the chat</ToggleButton>
        </ToggleButtonGroup>
        <Button size="small" onClick={reset}>Start over</Button>
      </Stack>
      <Box sx={{ bgcolor: st.bg, borderRadius: 2, p: 1.5, maxHeight: 460, overflowY: 'auto' }} aria-label={`${platform} button preview`}>
        {platform === 'discord' && (
          <Typography variant="caption" sx={{ color: st.sub, display: 'block' }}>
            Each task is a button on the channel post. Your private panel is only visible to you.
          </Typography>
        )}
        <Bubble st={st}>
          🚀 <strong>{title}</strong>{'\n'}Choose a task to complete:
        </Bubble>
        <Box sx={{ display: 'grid', gap: 0.5, mb: 1, maxWidth: '88%' }}>
          {list.map((t, i) => (
            <Box key={i} sx={{ display: 'flex' }}>
              <Btn st={st} platform={platform} kind="normal" onClick={() => open(i)} title="Tap to try this task">
                {done[i] ? '✅ ' : ''}{taskButtonLabel(t, platform)}
              </Btn>
            </Box>
          ))}
        </Box>
        {log.map((m, idx) => {
          if (m.who === 'panel') return panel(m, idx);
          if (m.who === 'popup') {
            return (
              <Box key={idx} sx={{ my: 0.75, mx: 'auto', maxWidth: '80%', textAlign: 'center', bgcolor: '#000', color: '#fff', opacity: 0.85, borderRadius: 2, px: 1.5, py: 1, fontSize: 13 }}>
                {m.text}
              </Box>
            );
          }
          return <Bubble st={st} who={m.who} key={idx}>{m.text}</Bubble>;
        })}
      </Box>
      <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
        {list.map((t, i) => {
          const k = taskPanelKind(t, { isPaid, keyReady });
          return (
            <Chip key={i} size="small" variant="outlined" color={k ? 'success' : 'default'}
              label={`${taskButtonLabel(t, platform)}: ${k === 'x' ? 'automatic (X)' : k === 'join' ? 'automatic (join check)' : 'typed proof, reviewed'}`} />
          );
        })}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
        Simulation only: nothing is sent or checked. It updates as you edit the tasks.
      </Typography>
    </Box>
  );
}
