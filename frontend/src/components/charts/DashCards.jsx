import React from 'react';
import { Avatar, Box, LinearProgress, Typography } from '@mui/material';
import { EmojiEvents } from '@mui/icons-material';

/** Shared dashboard building blocks (KPI card, panel, ranked share row) used by the
 *  Telegram and Discord invite dashboards so both look and behave the same. */
export const dashCard = {
  border: 1, borderColor: 'divider', borderRadius: 2.5, p: 2, minWidth: 0,
  bgcolor: 'background.paper',
};

export function Kpi({ icon, tone, label, value, hint }) {
  return (
    <Box sx={{
      ...dashCard, display: 'flex', gap: 1.5, alignItems: 'center',
    }}>
      <Box sx={{ width: 40, height: 40, borderRadius: 2, display: 'grid', placeItems: 'center', color: tone, bgcolor: 'action.hover', flexShrink: 0, '& svg': { fontSize: 20 } }}>{icon}</Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" noWrap display="block">{label}</Typography>
        <Typography sx={{ fontSize: 28, fontWeight: 600, lineHeight: 1.1, fontVariantNumeric: 'tabular-nums' }}>{value}</Typography>
        {hint && <Typography variant="caption" color="text.secondary" noWrap display="block">{hint}</Typography>}
      </Box>
    </Box>
  );
}

export function DashPanel({ title, action, children }) {
  return (
    <Box sx={{ ...dashCard, display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, mb: 1.5, flexWrap: 'wrap' }}>
        <Typography fontWeight={600}>{title}</Typography>{action}
      </Box>
      {children}
    </Box>
  );
}

export const initial = (n) => String(n || '?').trim().charAt(0).toUpperCase();
export const pct = (a, b) => (b > 0 ? `${((a / b) * 100).toFixed(1)}%` : '0%');

/** One ranked row: #n, avatar initial, name, "N joins · share%", proportional bar. */
export function ShareRow({ index, name, count, total, noun = 'join', sub }) {
  return (
    <Box sx={{ display: 'flex', gap: 1.25, alignItems: 'center', py: 1, borderTop: index ? 1 : 0, borderColor: 'divider' }}>
      <Box sx={{ width: 38, display: 'flex', alignItems: 'center', gap: 0.25, color: index === 0 ? '#FAA61A' : 'text.secondary' }}>
        {index === 0 && <EmojiEvents sx={{ fontSize: 16 }} />}<Typography variant="body2" fontWeight={600}>#{index + 1}</Typography>
      </Box>
      <Avatar sx={{ width: 30, height: 30, fontSize: 13, bgcolor: 'primary.main' }}>{initial(name)}</Avatar>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="body2" noWrap>{name}</Typography>
            {sub && <Typography variant="caption" color="text.secondary" noWrap display="block">{sub}</Typography>}
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
            {Number(count || 0).toLocaleString()} {count === 1 ? noun : `${noun}s`} · {pct(count, total)}
          </Typography>
        </Box>
        <LinearProgress variant="determinate" value={total ? Math.min(100, (count / total) * 100) : 0}
          sx={{ mt: 0.5, height: 6, borderRadius: 3, bgcolor: 'action.hover', '& .MuiLinearProgress-bar': { borderRadius: 3, background: 'linear-gradient(90deg,#5865F2,#4fb3a5)' } }} />
      </Box>
    </Box>
  );
}
