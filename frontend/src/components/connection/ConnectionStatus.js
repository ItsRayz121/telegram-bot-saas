import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Box, Button, CircularProgress, Tooltip, Typography } from '@mui/material';
import { WifiOff, SignalWifiStatusbar4Bar, CloudOff } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { subscribe, getSnapshot, tryAgain, startConnectionMonitor } from '../../services/connectionMonitor';
import OfflineArt from './OfflineArt';

const BUTTON_DELAY_MS = 8000; // let automatic recovery work first
const PILL = {
  unstable: { icon: SignalWifiStatusbar4Bar, color: '#f59e0b', tip: 'Connection is unstable.' },
  offline: { icon: WifiOff, color: '#ef4444', tip: "You're offline. Reconnecting…" },
  backend_down: { icon: CloudOff, color: '#ef4444', tip: 'Telegizer is temporarily unreachable. Your bots keep running. Reconnecting…' },
};

export default function ConnectionStatus() {
  const s = useSyncExternalStore(subscribe, getSnapshot);
  const [dismissed, setDismissed] = useState(false);
  const [showBtn, setShowBtn] = useState(false);
  const [busy, setBusy] = useState(false);
  const lastRecovered = useRef(0);

  useEffect(() => { startConnectionMonitor(); }, []);

  useEffect(() => {
    if (s.status !== 'offline') { setDismissed(false); setShowBtn(false); return undefined; }
    const t = setTimeout(() => setShowBtn(true), BUTTON_DELAY_MS);
    return () => clearTimeout(t);
  }, [s.status]);

  useEffect(() => {
    if (s.recoveredAt && s.recoveredAt !== lastRecovered.current) {
      lastRecovered.current = s.recoveredAt;
      toast.success('Back online', { toastId: 'back-online', autoClose: 3000, hideProgressBar: true });
    }
  }, [s.recoveredAt]);

  if (s.status === 'ok') return null;
  const pill = PILL[s.status];
  const Icon = pill.icon;

  const onTry = async () => { setBusy(true); await tryAgain(); setBusy(false); };

  if (s.status === 'offline' && !dismissed) {
    return (
      <Box role="alert" aria-live="polite" sx={{ position: 'fixed', inset: 0, zIndex: 10000, bgcolor: '#0a1030', background: 'radial-gradient(110% 80% at 50% 20%, #14275e 0%, #0a1030 55%, #060818 100%)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 1.5, px: 2, textAlign: 'center' }}>
        <OfflineArt />
        <Typography variant="h5" sx={{ color: '#f1f0ff', fontWeight: 700 }}>You're Offline</Typography>
        <Typography sx={{ color: '#a5a3d6', display: 'flex', alignItems: 'center', gap: 1 }}>
          Reconnecting<span aria-hidden>…</span>
        </Typography>
        <Box sx={{ minHeight: 76, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, mt: 1 }}>
          {showBtn && (
            <>
              <Button variant="contained" size="small" onClick={onTry} disabled={busy} startIcon={busy ? <CircularProgress size={14} color="inherit" /> : null}>
                Try Again
              </Button>
              <Button size="small" sx={{ color: '#8f8dc4' }} onClick={() => setDismissed(true)}>View page</Button>
            </>
          )}
        </Box>
        <Typography variant="caption" sx={{ color: '#6f6da8' }}>Your bots keep running on our servers.</Typography>
      </Box>
    );
  }

  return (
    <Tooltip title={pill.tip} placement="left">
      <Box role="status" aria-label={pill.tip} onClick={s.status === 'unstable' ? undefined : onTry} sx={{ position: 'fixed', right: 16, bottom: 16, zIndex: 9998, width: 36, height: 36, borderRadius: '50%', bgcolor: 'background.paper', border: `1px solid ${pill.color}`, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: s.status === 'unstable' ? 'default' : 'pointer', boxShadow: 3 }}>
        {s.reconnecting && s.status !== 'unstable'
          ? <CircularProgress size={22} thickness={4} sx={{ color: pill.color, position: 'absolute' }} />
          : null}
        <Icon sx={{ fontSize: 18, color: pill.color }} />
      </Box>
    </Tooltip>
  );
}
