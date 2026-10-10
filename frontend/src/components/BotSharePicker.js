import React, { useEffect, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Typography, List, ListItemButton,
  ListItemText, CircularProgress, Alert, Chip,
} from '@mui/material';
import { groupTeam } from '../services/api';

// Lets an owner pick which bot to share in one step (all of its groups, now and later).
export default function BotSharePicker({ open, onClose, onPick }) {
  const [loading, setLoading] = useState(true);
  const [bots, setBots] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setLoading(true); setError('');
    groupTeam.bots()
      .then((r) => setBots(r.data.bots || []))
      .catch((e) => setError(e?.response?.data?.error || 'Could not load your bots.'))
      .finally(() => setLoading(false));
  }, [open]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Share a whole bot</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Pick a bot to give someone access to every group it manages, including groups you add later.
          To share just one group, use that group's Team button instead.
        </Typography>
        {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}</Alert>}
        {loading ? <CircularProgress size={22} /> : (
          <List dense>
            {bots.map((b) => (
              <ListItemButton key={b.key} onClick={() => onPick(b)}>
                <ListItemText
                  primary={b.label}
                  secondary={`${b.group_count} group${b.group_count === 1 ? '' : 's'}${b.people ? ` · ${b.people} shared` : ''}`} />
                <Chip size="small" label={b.kind === 'official' ? 'Official' : 'Custom'} />
              </ListItemButton>
            ))}
            {bots.length === 0 && <Typography variant="body2" color="text.secondary">No bots yet.</Typography>}
          </List>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  );
}
