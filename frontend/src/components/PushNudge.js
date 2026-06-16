import React, { useState, useEffect } from 'react';
import { Box, Typography, Button, IconButton, Collapse } from '@mui/material';
import { NotificationsActive, Close } from '@mui/icons-material';
import { notifications as notificationsApi } from '../services/api';
import { enablePush, pushSupported, notificationPermission } from '../utils/push';

// Frequency policy (matches mainstream apps — soft, capped, never naggy):
//   • Only ever shown while OS permission is still "default" (untouched).
//   • After a dismiss: hidden for 14 days.
//   • Hard cap of 3 lifetime shows, then never again.
//   • Once granted/denied the native prompt, the banner self-suppresses.
const REASK_DAYS = 14;
const MAX_SHOWS = 3;

function keys(ns) {
  return { count: `pushnudge_${ns}_count`, last: `pushnudge_${ns}_last` };
}

function eligible(ns) {
  if (!pushSupported()) return false;
  if (notificationPermission() !== 'default') return false; // granted or denied → never nudge
  try {
    const k = keys(ns);
    const count = parseInt(localStorage.getItem(k.count) || '0', 10);
    if (count >= MAX_SHOWS) return false;
    const last = parseInt(localStorage.getItem(k.last) || '0', 10);
    if (count > 0 && Date.now() - last < REASK_DAYS * 86400000) return false;
    return true;
  } catch {
    return false;
  }
}

/**
 * Soft, frequency-capped prompt to enable push. Renders nothing unless the user
 * is eligible (see policy above). `api` selects which backend the subscription
 * registers with; `ns` namespaces the per-pillar frequency counters.
 */
export default function PushNudge({ api = notificationsApi, ns = 'tg', label }) {
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setShow(eligible(ns)); }, [ns]);

  const recordDismiss = () => {
    try {
      const k = keys(ns);
      const count = parseInt(localStorage.getItem(k.count) || '0', 10) + 1;
      localStorage.setItem(k.count, String(count));
      localStorage.setItem(k.last, String(Date.now()));
    } catch { /* ignore */ }
  };

  const onDismiss = () => { recordDismiss(); setShow(false); };

  const onEnable = async () => {
    setBusy(true);
    try {
      await enablePush(api);
    } catch {
      // Denied/cancelled — permission now self-suppresses future nudges.
      recordDismiss();
    } finally {
      setBusy(false);
      setShow(false);
    }
  };

  if (!show) return null;

  return (
    <Collapse in={show}>
      <Box
        sx={{
          display: 'flex', alignItems: 'center', gap: 1.5,
          p: 1.5, mb: 2, borderRadius: 2,
          border: '1px solid', borderColor: 'primary.main',
          bgcolor: 'action.hover',
        }}
      >
        <NotificationsActive color="primary" />
        <Typography variant="body2" sx={{ flex: 1 }}>
          {label || 'Turn on notifications so you never miss raids, reports and important alerts.'}
        </Typography>
        <Button size="small" variant="contained" onClick={onEnable} disabled={busy}>
          {busy ? 'Enabling…' : 'Enable'}
        </Button>
        <IconButton size="small" onClick={onDismiss} aria-label="Dismiss">
          <Close fontSize="small" />
        </IconButton>
      </Box>
    </Collapse>
  );
}
