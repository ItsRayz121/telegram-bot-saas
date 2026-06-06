import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, CircularProgress, Typography, Button, Paper } from '@mui/material';
import { ErrorOutline } from '@mui/icons-material';
import { useTelegram } from '../contexts/TelegramContext';

// Snapshot of the live Telegram/browser state — used to diagnose why auth didn't start.
function collectDiagnostics() {
  const tg = (typeof window !== 'undefined' && window.Telegram && window.Telegram.WebApp) || null;
  const u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
  return {
    isTelegramFlag: typeof window !== 'undefined' ? !!window.__IS_TELEGRAM__ : false,
    hasTelegramObj: typeof window !== 'undefined' ? !!window.Telegram : false,
    hasWebApp: !!tg,
    initDataLen: tg && tg.initData ? tg.initData.length : 0,
    user: u ? `${u.id} ${u.first_name || ''}`.trim() : '(none)',
    platform: tg ? tg.platform : '(n/a)',
    version: tg ? tg.version : '(n/a)',
    hash: typeof window !== 'undefined' ? (window.location.hash || '(empty)') : '',
    href: typeof window !== 'undefined' ? window.location.href : '',
    ua: typeof navigator !== 'undefined' ? navigator.userAgent : '',
    apiUrl: process.env.REACT_APP_API_URL || '(same-origin)',
  };
}

function LoadingScreen() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 2 }}>
      <CircularProgress size={36} />
      <Typography color="text.secondary" variant="body2">Opening Telegizer…</Typography>
    </Box>
  );
}

// Shows the failure reason + live Telegram state so we can see what the device provides.
function DiagnosticScreen({ title, message, authError }) {
  const d = collectDiagnostics();
  const rows = [
    ['__IS_TELEGRAM__', String(d.isTelegramFlag)],
    ['window.Telegram', String(d.hasTelegramObj)],
    ['WebApp object', String(d.hasWebApp)],
    ['initData length', String(d.initDataLen)],
    ['Telegram user', d.user],
    ['platform', d.platform],
    ['version', d.version],
    ['API URL', d.apiUrl],
    ['auth error', authError || '(none)'],
    ['hash', d.hash],
    ['UA', d.ua],
  ];
  return (
    <Box sx={{ p: 2.5, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-start', minHeight: '100vh', gap: 2 }}>
      <ErrorOutline sx={{ fontSize: 48, color: 'warning.main', mt: 2 }} />
      <Typography variant="h6" fontWeight={700} textAlign="center">{title}</Typography>
      <Typography variant="body2" color="text.secondary" textAlign="center">{message}</Typography>
      <Paper variant="outlined" sx={{ p: 1.5, width: '100%', maxWidth: 480, bgcolor: 'rgba(0,0,0,0.3)' }}>
        <Typography variant="caption" fontWeight={700} color="text.secondary">Diagnostics (screenshot this)</Typography>
        <Box component="dl" sx={{ m: 0, mt: 1, display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 1.5, rowGap: 0.5 }}>
          {rows.map(([k, v]) => (
            <React.Fragment key={k}>
              <Typography component="dt" variant="caption" sx={{ color: 'text.secondary', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{k}</Typography>
              <Typography component="dd" variant="caption" sx={{ m: 0, fontFamily: 'monospace', wordBreak: 'break-all' }}>{v}</Typography>
            </React.Fragment>
          ))}
        </Box>
      </Paper>
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', justifyContent: 'center' }}>
        <Button variant="contained" onClick={() => window.location.reload()}>Retry</Button>
        <Button variant="outlined" onClick={() => window.location.replace('/')}>Open website</Button>
      </Box>
    </Box>
  );
}

// Resolve the post-auth destination from Telegram's start_param (set via ?startapp=…).
// Custom bots deep-link here through the official bot to get Telegram auth, then we route
// the user to the right page. Supported: "grp_<botId>_<groupId>" → that group's settings.
function resolveStartDestination() {
  try {
    const tg = window.Telegram && window.Telegram.WebApp;
    const sp = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || '';
    const m = /^grp_(\d+)_(\d+)$/.exec(sp);
    if (m) return `/bot/${m[1]}/group/${m[2]}`;
  } catch { /* fall through to default */ }
  return '/dashboard';
}

export default function MiniApp() {
  const { status, authError } = useTelegram();
  const navigate = useNavigate();

  useEffect(() => {
    if (status === 'ok') {
      navigate(resolveStartDestination(), { replace: true });
    }
    if (status === 'no_init_data') {
      // initData missing but WebApp object exists — if a prior session exists, use it.
      const token = localStorage.getItem('token');
      if (token) navigate(resolveStartDestination(), { replace: true });
    }
  }, [status, navigate]);

  // NOTE: temporary diagnostics. Previously no_webapp silently redirected to '/',
  // which hid the failure reason. Show the live Telegram state instead.
  if (status === 'error') {
    return <DiagnosticScreen title="Authentication failed" message="Telegram session reached the server but was rejected." authError={authError} />;
  }
  if (status === 'no_webapp') {
    return <DiagnosticScreen title="Not detected as Telegram" message="window.Telegram.WebApp was never provided by the client." authError={authError} />;
  }
  if (status === 'no_init_data') {
    const hasToken = !!localStorage.getItem('token');
    if (!hasToken) return <DiagnosticScreen title="No Telegram session data" message="The WebApp object exists, but initData was empty." authError={authError} />;
    return <LoadingScreen />;
  }

  return <LoadingScreen />;
}
