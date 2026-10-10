import React, { useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, TextField, Typography, Alert, Chip, Stack,
} from '@mui/material';
import { groupTeam } from '../services/api';

const ROLE_TEXT = {
  manager: 'manage this group (settings, moderation, automations, forwarding, tasks)',
  viewer: 'view this group (read-only)',
};

export default function JoinGroupCodeDialog({ open, onClose, onJoined, initialCode = '' }) {
  const [code, setCode] = useState(initialCode);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const reset = () => { setCode(''); setPreview(null); setError(''); };
  const close = () => { reset(); onClose(); };

  const check = async () => {
    setBusy(true); setError('');
    try {
      const { data } = await groupTeam.preview(encodeURIComponent(code.trim()));
      setPreview(data.invite);
    } catch (e) {
      setPreview(null);
      setError(e?.response?.data?.error || 'Invalid or expired access code');
    }
    setBusy(false);
  };

  const join = async () => {
    setBusy(true); setError('');
    try {
      await groupTeam.redeem(code.trim());
      reset();
      onJoined && onJoined();
    } catch (e) {
      setError(e?.response?.data?.error || 'Could not use this access code');
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onClose={close} maxWidth="xs" fullWidth>
      <DialogTitle>Join a group with an access code</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Paste the code the owner sent you. It gives you access to the group (or the bot's groups) it was made for, nothing else.
        </Typography>
        {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
        <TextField
          autoFocus fullWidth label="Access code" value={code}
          onChange={(e) => { setCode(e.target.value); setPreview(null); setError(''); }}
          inputProps={{ style: { fontFamily: 'monospace' }, autoComplete: 'off', spellCheck: false }}
        />
        {preview && (
          <Stack spacing={0.5} sx={{ mt: 2 }}>
            <Typography variant="subtitle1" fontWeight={600}>{preview.group_title}</Typography>
            <Chip size="small" label={preview.role} sx={{ alignSelf: 'flex-start' }} />
            <Typography variant="body2" color="text.secondary">
              {preview.scope === 'bot'
                ? `You'll get access to all ${preview.group_count} group${preview.group_count === 1 ? '' : 's'} this bot manages, including ones added later. `
                : ''}
              You'll be able to {ROLE_TEXT[preview.role] || 'access this group'}.
            </Typography>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        {preview ? (
          <Button variant="contained" disabled={busy} onClick={join}>Join group</Button>
        ) : (
          <Button variant="contained" disabled={busy || code.trim().length < 8} onClick={check}>Check code</Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
