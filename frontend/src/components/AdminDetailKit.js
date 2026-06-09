// Shared presentational helpers for the admin detail pages (user + group).
// Kept separate from AdminPanel.js so the routed pages can reuse the exact same
// look without bloating the already-large panel file.
import React from 'react';
import { Box, Typography, Chip } from '@mui/material';

export function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function fmtDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function fmtRelative(iso) {
  if (!iso) return 'never';
  const diff = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(diff)) return 'never';
  const s = Math.floor(diff / 1000);
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function usd(val) {
  return `$${(val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function Field({ label, value, mono }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="body2" sx={mono ? { fontFamily: 'monospace', wordBreak: 'break-all' } : undefined}>
        {value === null || value === undefined || value === '' ? '—' : value}
      </Typography>
    </Box>
  );
}

export function SectionTitle({ children, sx }) {
  return (
    <Typography variant="caption" color="text.secondary" fontWeight={700} textTransform="uppercase"
      letterSpacing={0.8} display="block" mb={1} mt={2} sx={sx}>
      {children}
    </Typography>
  );
}

const STATUS_COLORS = {
  active: 'success', approved: 'success', ok: 'success', pending: 'warning',
  warning: 'warning', error: 'error', disabled: 'error', rejected: 'error',
  banned: 'error', suspicious: 'warning', unknown: 'default', info: 'info', critical: 'error',
};

export function StatusChip({ label }) {
  return <Chip label={label} size="small" color={STATUS_COLORS[label] || 'default'} />;
}
