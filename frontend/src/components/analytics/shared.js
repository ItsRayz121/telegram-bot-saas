import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import {
  Alert, Avatar, Box, Button, Card, CardContent, Chip, CircularProgress, Skeleton,
  Typography,
} from '@mui/material';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { insights } from '../../services/api';

/**
 * Column widths for the analytics tables. Percentages of the table so every column and the
 * rightmost action stay visible at desktop widths without sideways scrolling; below `minWidth`
 * the container scrolls instead of squeezing (phones use cards, so this is only a safety net).
 */
export function TableCols({ widths }) {
  return (
    <colgroup>
      {widths.map((w, i) => <col key={i} style={{ width: w }} />)}
    </colgroup>
  );
}

export const fixedTableSx = {
  tableLayout: 'fixed',
  width: '100%',
  '& td, & th': { px: 1.25, py: 1.1, verticalAlign: 'middle' },
  '& th': { whiteSpace: 'nowrap', fontWeight: 700 },
  '& td': { overflowWrap: 'anywhere' },
};

/** Where "View profile" goes: the existing member profile (CRM drawer) of this group. */
export function memberProfilePath({ isOfficial, botId, groupId, userId }) {
  if (userId == null || userId === '') return null;
  const base = isOfficial ? `/groups/${groupId}/crm` : `/bot/${botId}/group/${groupId}/crm`;
  return `${base}?member=${encodeURIComponent(userId)}`;
}

export function memberLabel(m) {
  if (!m) return 'Unknown member';
  return m.name || m.first_name || (m.username ? `@${m.username}` : null) || (m.user_id ? `User ${m.user_id}` : 'Unknown member');
}

/** Loads one insight and exposes loading / error / reload. Re-fetches when params change. */
export function useInsight(botId, groupId, kind, params, enabled = true) {
  const [state, setState] = useState({ data: null, loading: enabled, error: null });
  const key = JSON.stringify(params || {});
  const seq = useRef(0);
  const load = useCallback(() => {
    if (!enabled) return Promise.resolve();
    const my = ++seq.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    return insights.get(botId, groupId, kind, params)
      .then((r) => { if (my === seq.current) setState({ data: r.data, loading: false, error: null }); })
      .catch((e) => {
        if (my === seq.current) {
          setState((s) => ({ data: s.data, loading: false, error: e?.response?.data?.error || 'Could not load this view' }));
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [botId, groupId, kind, key, enabled]);
  useEffect(() => { load(); }, [load]);
  return { ...state, reload: load };
}

export function InsightError({ message, onRetry }) {
  return (
    <Alert severity="error" sx={{ mb: 2 }}
      action={onRetry ? <Button color="inherit" size="small" onClick={onRetry}>Retry</Button> : null}>
      {message}
    </Alert>
  );
}

/** One summary metric. value === null/undefined renders an em dash (unknown), 0 renders 0. */
export function StatTile({ label, value, hint, onClick, selected, loading, tone }) {
  const unknown = value === null || value === undefined;
  const clickable = typeof onClick === 'function';
  return (
    <Card
      variant="outlined"
      sx={{
        height: '100%',
        borderColor: selected ? 'primary.main' : 'divider',
        bgcolor: selected ? 'action.selected' : 'background.paper',
      }}
    >
      <Box
        component={clickable ? 'button' : 'div'}
        type={clickable ? 'button' : undefined}
        onClick={onClick}
        aria-pressed={clickable ? !!selected : undefined}
        sx={{
          all: 'unset', boxSizing: 'border-box', display: 'block', width: '100%', height: '100%',
          cursor: clickable ? 'pointer' : 'default', p: 1.75,
          '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: -2, borderRadius: 1 },
          '&:hover': clickable ? { bgcolor: 'action.hover' } : undefined,
        }}
      >
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.3 }}>
          {label}
        </Typography>
        {loading ? (
          <Skeleton width={56} height={36} />
        ) : (
          <Typography variant="h5" fontWeight={700} sx={{ mt: 0.25, color: unknown ? 'text.disabled' : tone || 'text.primary' }}>
            {unknown ? '—' : Number(value).toLocaleString()}
          </Typography>
        )}
        {hint && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25, lineHeight: 1.3 }}>
            {hint}
          </Typography>
        )}
      </Box>
    </Card>
  );
}

export function StatGrid({ children, min = 150, columns, gap = 1.5 }) {
  // `columns` (a responsive sx value) pins an exact column count, e.g. four equal KPI cards.
  return (
    <Box sx={{ display: 'grid', gap, mb: 2, gridTemplateColumns: columns || `repeat(auto-fit, minmax(${min}px, 1fr))` }}>
      {children}
    </Box>
  );
}

export function Panel({ title, subtitle, action, children, sx }) {
  return (
    <Card variant="outlined" sx={{ mb: 2, ...sx }}>
      <CardContent sx={{ '&:last-child': { pb: 2 } }}>
        {(title || action) && (
          <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1, mb: 1.5, flexWrap: 'wrap' }}>
            <Box sx={{ minWidth: 0 }}>
              {title && <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>}
              {subtitle && <Typography variant="caption" color="text.secondary">{subtitle}</Typography>}
            </Box>
            {action}
          </Box>
        )}
        {children}
      </CardContent>
    </Card>
  );
}

export function EmptyNote({ children }) {
  return (
    <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
      {children}
    </Typography>
  );
}

export function Loading({ label = 'Loading…' }) {
  return (
    <Box role="status" sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, py: 4 }}>
      <CircularProgress size={20} /> <Typography variant="body2" color="text.secondary">{label}</Typography>
    </Box>
  );
}

/** Avatar + name that both open the member's profile. Falls back to plain text if there is no stable id. */
export function MemberLink({ member, profile, size = 28, secondary, strong }) {
  const label = memberLabel(member);
  const initial = (label.replace(/^@/, '')[0] || '?').toUpperCase();
  const inner = (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1, minWidth: 0, maxWidth: '100%' }}>
      <Avatar sx={{ width: size, height: size, fontSize: size * 0.45, bgcolor: 'primary.dark', color: 'primary.contrastText' }}>
        {initial}
      </Avatar>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2" fontWeight={strong ? 700 : 600} noWrap>{label}</Typography>
        {secondary && <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>{secondary}</Typography>}
      </Box>
    </Box>
  );
  if (!profile) return inner;
  return (
    <Box
      component={RouterLink}
      to={profile}
      aria-label={`Open profile of ${label}`}
      sx={{
        color: 'inherit', textDecoration: 'none', minWidth: 0, maxWidth: '100%', display: 'inline-flex', borderRadius: 1,
        '&:hover .MuiTypography-body2': { textDecoration: 'underline' },
        '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: 2 },
      }}
    >
      {inner}
    </Box>
  );
}

export function ProfileButton({ to, label = 'View profile', size = 'small' }) {
  if (!to) return null;
  return (
    <Button component={RouterLink} to={to} size={size} variant="outlined" sx={{ whiteSpace: 'nowrap' }}>
      {label}
    </Button>
  );
}

export function PeriodChips({ value, options, onChange, ariaLabel = 'Time period' }) {
  return (
    <Box role="group" aria-label={ariaLabel} sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
      {options.map(({ key, label }) => (
        <Chip
          key={key} label={label} size="small" clickable
          aria-pressed={value === key}
          variant={value === key ? 'filled' : 'outlined'}
          color={value === key ? 'primary' : 'default'}
          onClick={() => onChange(key)}
        />
      ))}
    </Box>
  );
}

/** Small area/line chart used by every overview. series: [{date, ...}], keys: [{key, label, color}] */
export function TrendChart({ series, keys, height = 180, emptyText = 'No activity recorded in this period.' }) {
  const total = (series || []).reduce((n, p) => n + keys.reduce((m, k) => m + (p[k.key] || 0), 0), 0);
  if (!series || series.length === 0 || total === 0) return <EmptyNote>{emptyText}</EmptyNote>;
  return (
    <Box sx={{ width: '100%', height }} role="img" aria-label={`Trend chart: ${keys.map((k) => k.label).join(', ')}`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={series} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(143,163,188,0.18)" vertical={false} />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#8fa3bc' }} tickFormatter={(d) => d.slice(5)} minTickGap={24} />
          <YAxis tick={{ fontSize: 11, fill: '#8fa3bc' }} allowDecimals={false} />
          <Tooltip contentStyle={{ background: '#0f1e35', border: '1px solid #274060', borderRadius: 8, fontSize: 12 }} />
          {keys.map((k) => (
            <Area key={k.key} type="monotone" dataKey={k.key} name={k.label} stroke={k.color} fill={k.color}
              fillOpacity={0.16} strokeWidth={2} dot={false} isAnimationActive={false} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </Box>
  );
}

/** Horizontal share bars (label, count) - used for reason / rule / category breakdowns. */
export function BreakdownBars({ rows, onPick, activeLabel, color = 'primary.main' }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (!rows.length) return <EmptyNote>Nothing to break down yet.</EmptyNote>;
  return (
    <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0, display: 'grid', gap: 1 }}>
      {rows.map((r) => {
        const clickable = typeof onPick === 'function';
        return (
          <Box component="li" key={r.label}>
            <Box
              component={clickable ? 'button' : 'div'} type={clickable ? 'button' : undefined}
              onClick={clickable ? () => onPick(r.label) : undefined}
              sx={{ all: 'unset', display: 'block', width: '100%', cursor: clickable ? 'pointer' : 'default', borderRadius: 1,
                '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: 2 } }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                <Typography variant="body2" noWrap sx={{ fontWeight: activeLabel === r.label ? 700 : 400 }}>{r.label}</Typography>
                <Typography variant="body2" fontWeight={700}>{r.count.toLocaleString()}</Typography>
              </Box>
              <Box sx={{ height: 6, borderRadius: 3, bgcolor: 'action.hover', overflow: 'hidden', mt: 0.5 }}>
                <Box sx={{ height: '100%', width: `${(r.count / max) * 100}%`, bgcolor: color, borderRadius: 3 }} />
              </Box>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

export const fmtDateTime = (ts, tz) => {
  if (!ts) return '—';
  const d = new Date(/(Z|[+-]\d\d:?\d\d)$/.test(ts) ? ts : `${ts}Z`);   // server timestamps are UTC
  try {
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: tz || undefined });
  } catch {
    return d.toLocaleString();
  }
};
