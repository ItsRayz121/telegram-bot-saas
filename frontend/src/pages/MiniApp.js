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
    // Telegram start_param (custom-bot ?startapp deep links) OR a ?start= query
    // param (official bot in-Telegram web_app buttons point at /mini-app?start=…).
    let sp = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || '';
    if (!sp) {
      try { sp = new URLSearchParams(window.location.search).get('start') || ''; } catch {}
    }
    const m = /^grp_(\d+)_(\d+)$/.exec(sp);
    if (m) return `/bot/${m[1]}/group/${m[2]}`;
    // Engagement campaign task: ?startapp=engtask_<id> → participant task page.
    const t = /^engtask_(\d+)$/.exec(sp);
    if (t) return `/task/${t[1]}`;
    // Short codes used by bot deep links (startapp only allows [A-Za-z0-9_-]).
    const MAP = {
      dashboard: '/dashboard',
      settings: '/settings',
      mygroups: '/my-groups',
      // Target /custom-bots directly: /my-bots is a <Navigate> that drops the query
      // string, which would lose ?connect=1 before MyBots can read it.
      mybots: '/custom-bots',
      connectbot: '/custom-bots?connect=1',
      referral: '/referrals',
      tasks: '/tasks',
      workspace: '/workspace',
      automations: '/workspace/automations',
      billing: '/billing',
      echo: '/ark',
    };
    if (MAP[sp]) return MAP[sp];
  } catch { /* fall through to default */ }
  return '/dashboard';
}

export default function MiniApp() {
  const { status, authError } = useTelegram();
  const navigate = useNavigate();

  const hasStoredSession = typeof window !== 'undefined' && !!localStorage.getItem('token');

  useEffect(() => {
    if (status === 'ok') {
      navigate(resolveStartDestination(), { replace: true });
    }
    // initData missing OR rejected (e.g. the persistent Menu Button replayed a
    // stale-auth_date session) — if a prior valid session exists, use it so the
    // user still lands in the app instead of a failure screen.
    if ((status === 'no_init_data' || status === 'error') && hasStoredSession) {
      navigate(resolveStartDestination(), { replace: true });
    }
  }, [status, navigate, hasStoredSession]);

  // Rejected by the server. If a prior session exists we fall through to it
  // above; otherwise show the live Telegram state to diagnose.
  if (status === 'error') {
    if (hasStoredSession) return <LoadingScreen />;
    return <DiagnosticScreen title="Authentication failed" message="Telegram session reached the server but was rejected." authError={authError} />;
  }
  if (status === 'no_webapp') {
    return <DiagnosticScreen title="Not detected as Telegram" message="window.Telegram.WebApp was never provided by the client." authError={authError} />;
  }
  if (status === 'no_init_data') {
    if (!hasStoredSession) return <DiagnosticScreen title="No Telegram session data" message="The WebApp object exists, but initData was empty." authError={authError} />;
    return <LoadingScreen />;
  }

  return <LoadingScreen />;
}
