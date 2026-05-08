import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Paper, Chip, Divider, IconButton, Collapse,
  Stack, Tooltip,
} from '@mui/material';
import { BugReport, Close, ContentCopy } from '@mui/icons-material';
import { APP_VERSION, BUILD_TIME, API_BASE_URL } from '../version';

function _user() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

function Row({ label, value, mono = false }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(String(value)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };
  return (
    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ py: 0.4 }}>
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 130 }}>{label}</Typography>
      <Stack direction="row" alignItems="center" spacing={0.5}>
        <Typography
          variant="caption"
          fontFamily={mono ? 'monospace' : undefined}
          color="text.primary"
          sx={{ wordBreak: 'break-all', textAlign: 'right' }}
        >
          {String(value)}
        </Typography>
        <Tooltip title={copied ? 'Copied!' : 'Copy'}>
          <IconButton size="small" onClick={copy} sx={{ p: 0.25, opacity: 0.5 }}>
            <ContentCopy sx={{ fontSize: 11 }} />
          </IconButton>
        </Tooltip>
      </Stack>
    </Stack>
  );
}

export default function DebugPanel() {
  const [open, setOpen] = useState(false);
  const [swVersion, setSwVersion] = useState('checking…');
  const user = _user();

  // Show only when ?debug=1 is in the URL, or always in dev
  const shouldShow = process.env.NODE_ENV === 'development'
    || new URLSearchParams(window.location.search).get('debug') === '1';

  useEffect(() => {
    if (!open) return;
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.getRegistration().then((reg) => {
        setSwVersion(reg ? (reg.active?.scriptURL || 'registered (no URL)') : 'not registered');
      });
    } else {
      setSwVersion('not supported');
    }
  }, [open]);

  if (!shouldShow) return null;

  const isTelegram = !!(window?.Telegram?.WebApp?.initData);
  const tgVersion  = window?.Telegram?.WebApp?.version || 'n/a';
  const tgPlatform = window?.Telegram?.WebApp?.platform || 'n/a';

  return (
    <Box
      sx={{
        position: 'fixed', bottom: 16, right: 16, zIndex: 9999,
        display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1,
      }}
    >
      <Collapse in={open} unmountOnExit>
        <Paper
          elevation={8}
          sx={{
            p: 2, width: 320, maxHeight: '70vh', overflowY: 'auto',
            bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider',
            borderRadius: 2,
          }}
        >
          <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1}>
            <Typography variant="subtitle2" fontWeight={700}>Debug Info</Typography>
            <IconButton size="small" onClick={() => setOpen(false)}><Close fontSize="small" /></IconButton>
          </Stack>
          <Divider sx={{ mb: 1 }} />

          <Typography variant="caption" color="primary.main" fontWeight={600} display="block" mb={0.5}>Build</Typography>
          <Row label="App version"  value={APP_VERSION} />
          <Row label="Build time"   value={BUILD_TIME} mono />
          <Row label="Environment"  value={process.env.NODE_ENV} />

          <Divider sx={{ my: 1 }} />
          <Typography variant="caption" color="primary.main" fontWeight={600} display="block" mb={0.5}>Network</Typography>
          <Row label="API base URL" value={API_BASE_URL} mono />
          <Row label="Current host" value={window.location.hostname} mono />
          <Row label="Full URL"     value={window.location.href} mono />

          <Divider sx={{ my: 1 }} />
          <Typography variant="caption" color="primary.main" fontWeight={600} display="block" mb={0.5}>Telegram</Typography>
          <Row label="TMA detected" value={isTelegram ? 'YES ✓' : 'no'} />
          <Row label="WebApp version" value={tgVersion} />
          <Row label="Platform"     value={tgPlatform} />
          <Row label="Init data"    value={isTelegram ? 'present' : 'absent'} />

          <Divider sx={{ my: 1 }} />
          <Typography variant="caption" color="primary.main" fontWeight={600} display="block" mb={0.5}>User</Typography>
          <Row label="Plan"         value={user.subscription_tier || 'unknown'} />
          <Row label="User ID"      value={user.id || 'not logged in'} />

          <Divider sx={{ my: 1 }} />
          <Typography variant="caption" color="primary.main" fontWeight={600} display="block" mb={0.5}>Service Worker</Typography>
          <Row label="SW URL" value={swVersion} mono />
        </Paper>
      </Collapse>

      <Tooltip title="Debug panel">
        <Chip
          icon={<BugReport sx={{ fontSize: 16 }} />}
          label={open ? 'close' : 'debug'}
          size="small"
          onClick={() => setOpen((v) => !v)}
          sx={{
            cursor: 'pointer', opacity: 0.7,
            bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider',
            '&:hover': { opacity: 1 },
          }}
        />
      </Tooltip>
    </Box>
  );
}
