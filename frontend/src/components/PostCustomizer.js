import React, { useRef, useState } from 'react';
import { Alert, Box, Button, Chip, FormControlLabel, Stack, Switch, TextField, Typography } from '@mui/material';

// Edit the group / channel announcement: switch single lines off, or write the whole text.
// Shared by Telegram (Telegizer) and Discord (Guildizer). The text uses **bold**, __italic__ and
// {placeholders} that are filled in live (deadline, status, goals ...).
export const POST_HIDEABLE = [
  { key: 'reward', label: 'Reward' },
  { key: 'xp', label: 'XP' },
  { key: 'submissions', label: 'Submissions rule' },
  { key: 'proof', label: 'Proof line' },
  { key: 'deadline', label: 'Deadline' },
  { key: 'status', label: 'Status' },
];

const PLACEHOLDERS = [
  ['title', 'Campaign title'], ['description', 'Your brief'], ['tasks', 'Task list'], ['goals', 'Live goals'],
  ['reward', 'Reward text'], ['xp', 'XP'], ['submissions', 'Submissions rule'], ['proof', 'What members send'],
  ['deadline', 'Time left'], ['status', 'Active / ending / closed'], ['link', 'Task link'],
];

export default function PostCustomizer({ hide = [], template = '', onChange, fetchDefault, hideable = POST_HIDEABLE }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const ref = useRef(null);
  const custom = !!template;

  const toggle = (key, show) => {
    const next = show ? hide.filter((k) => k !== key) : [...new Set([...hide, key])];
    onChange({ post_hide: next });
  };

  const startCustom = async () => {
    setLoading(true); setError('');
    try {
      const tpl = await fetchDefault();
      onChange({ post_template: tpl || '{title}\n\n{description}' });
    } catch (e) {
      setError('Could not load the automatic text. Try again.');
    } finally { setLoading(false); }
  };

  const insert = (name) => {
    const el = ref.current;
    const tag = `{${name}}`;
    if (!el) { onChange({ post_template: `${template}${tag}` }); return; }
    const s = el.selectionStart ?? template.length;
    const e = el.selectionEnd ?? s;
    const next = template.slice(0, s) + tag + template.slice(e);
    onChange({ post_template: next });
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(s + tag.length, s + tag.length); });
  };

  return (
    <Box sx={{ mt: 2, border: '1px solid', borderColor: 'divider', borderRadius: 1, p: 1.5 }}>
      <Typography variant="subtitle2">Customize the announcement</Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        Hide lines you don't need, or write the whole text yourself. The preview updates as you go.
      </Typography>

      {!custom && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, columnGap: 2 }}>
          {hideable.map((h) => (
            <FormControlLabel key={h.key} label={`Show: ${h.label}`}
              control={<Switch size="small" checked={!hide.includes(h.key)} onChange={(e) => toggle(h.key, e.target.checked)} />} />
          ))}
        </Box>
      )}

      {!custom ? (
        <Button size="small" sx={{ mt: 1 }} onClick={startCustom} disabled={loading}>
          {loading ? 'Loading…' : 'Edit the full text'}
        </Button>
      ) : (
        <Stack spacing={1} sx={{ mt: 1 }}>
          <TextField inputRef={ref} multiline minRows={8} maxRows={18} fullWidth label="Announcement text"
            value={template} onChange={(e) => onChange({ post_template: e.target.value })}
            inputProps={{ maxLength: 3000 }}
            helperText="Use **bold**, __italic__ and the placeholders below. A line whose placeholders are all empty is left out automatically." />
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {PLACEHOLDERS.map(([k, tip]) => (
              <Chip key={k} size="small" variant="outlined" label={`{${k}}`} title={tip} onClick={() => insert(k)} />
            ))}
          </Box>
          <Alert severity="info" icon={false} sx={{ py: 0 }}>
            Deadline, status and goals keep updating on their own after the post is sent.
          </Alert>
          <Button size="small" color="inherit" sx={{ alignSelf: 'flex-start' }} onClick={() => onChange({ post_template: '' })}>
            Back to the automatic text
          </Button>
        </Stack>
      )}
      {error && <Typography variant="caption" color="error" display="block" sx={{ mt: 0.5 }}>{error}</Typography>}
    </Box>
  );
}
