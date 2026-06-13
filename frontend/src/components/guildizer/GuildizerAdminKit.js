// Shared presentational helpers for the Guildizer admin shell + detail pages.
// Independent copy of the Telegizer AdminDetailKit look (same design language via
// the shared theme), kept separate so Guildizer never imports Telegizer admin code.
import React from 'react';
import { Box, Typography, Chip, Card, CardContent, TableRow, TableCell } from '@mui/material';
import { PALETTE } from '../../theme';

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

// Primary KPI tile — big number, label, optional sub-text + icon, optional click.
export function StatCard({ value, label, sub, icon: Icon, color = PALETTE.blue, onClick }) {
  return (
    <Card
      variant="outlined"
      onClick={onClick}
      sx={{
        height: '100%',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease',
        ...(onClick && {
          '&:hover': { transform: 'translateY(-2px)', borderColor: color, boxShadow: `0 6px 22px ${color}22` },
        }),
      }}
    >
      <CardContent sx={{ py: 1.75, display: 'flex', alignItems: 'center', gap: 1.5 }}>
        {Icon && (
          <Box sx={{
            width: 38, height: 38, borderRadius: 1.5, flexShrink: 0,
            display: 'grid', placeItems: 'center', bgcolor: `${color}1f`, color,
          }}>
            <Icon sx={{ fontSize: 20 }} />
          </Box>
        )}
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h6" fontWeight={800} lineHeight={1.1}>{value ?? 0}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap display="block">{label}</Typography>
          {sub && <Typography variant="caption" color="text.disabled" noWrap display="block">{sub}</Typography>}
        </Box>
      </CardContent>
    </Card>
  );
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

export function EmptyRow({ colSpan, label = 'No data.' }) {
  return (
    <TableRow>
      <TableCell colSpan={colSpan} align="center" sx={{ color: 'text.disabled', py: 3 }}>
        {label}
      </TableCell>
    </TableRow>
  );
}

const STATUS_COLORS = {
  active: 'success', approved: 'success', ok: 'success', verified: 'success', pending: 'warning',
  warning: 'warning', error: 'error', disabled: 'error', rejected: 'error',
  banned: 'error', suspicious: 'warning', unknown: 'default', info: 'info', critical: 'error',
};

export function StatusChip({ label }) {
  return <Chip label={label} size="small" color={STATUS_COLORS[label] || 'default'} variant="outlined" />;
}
