import React from 'react';
import { Box, Tooltip, Typography } from '@mui/material';

/**
 * Shared per-day bar chart used by every dashboard (Telegram official/custom bots,
 * Discord/Guildizer, campaigns). Every bar carries its exact value above it, so the
 * numbers are readable without hovering. Values come straight from `series`; nothing
 * is computed or invented here.
 *
 * series:  [{ [dateKey]: 'YYYY-MM-DD', ...numbers }]
 * keys:    [{ key, label, color }]   one entry = plain bars, several = grouped bars
 * compact: smaller chart for summary strips (value labels stay)
 */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function shortDay(day) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(day || ''));
  return m ? `${MONTHS[Number(m[2]) - 1] || m[2]} ${Number(m[3])}` : String(day || '');
}

const LABEL_H = 16;

function fmtVal(v) {
  if (v >= 100000) return `${Math.round(v / 1000)}k`;
  if (v >= 10000) return `${(v / 1000).toFixed(1)}k`;
  return String(v);
}

export default function DailyBars({ series, keys, dateKey = 'date', height = 132, compact = false, ariaLabel }) {
  const rows = (series || []).map((d) => ({
    day: d[dateKey],
    vals: keys.map((k) => Number(d[k.key]) || 0),
  }));
  if (rows.length === 0) return null;

  const n = keys.length;
  const max = Math.max(1, ...rows.flatMap((r) => r.vals));
  const colMin = (n > 1 ? 14 + n * 20 : rows.length > 14 ? 30 : 36) + (compact ? -6 : 0);
  const tickEvery = rows.length > 21 ? 3 : rows.length > 10 ? 2 : 1;
  const plotH = height - LABEL_H - 4;
  const fmt = (v) => v.toLocaleString();
  const fs = compact ? 10 : 11;

  return (
    <Box
      role="img"
      aria-label={ariaLabel || keys.map((k) => k.label).join(', ') + ' per day'}
      sx={{
        overflowX: 'auto', overflowY: 'hidden', pb: 0.5, width: '100%',
        '@keyframes dbGrow': { from: { transform: 'scaleY(0)' }, to: { transform: 'scaleY(1)' } },
        '@keyframes dbFade': { from: { opacity: 0 }, to: { opacity: 1 } },
      }}
    >
      {n > 1 && (
        <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', mb: 0.75 }}>
          {keys.map((k) => (
            <Box key={k.key} sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
              <Box sx={{ width: 8, height: 8, borderRadius: '2px', bgcolor: k.color }} />
              <Typography variant="caption" color="text.secondary">{k.label}</Typography>
            </Box>
          ))}
        </Box>
      )}
      <Box sx={{
        display: 'grid',
        gridTemplateColumns: `repeat(${rows.length}, minmax(${colMin}px, 1fr))`,
        columnGap: '4px',
        minWidth: rows.length * (colMin + 4),
      }}>
        {rows.map((r, i) => (
          <Tooltip
            key={`b-${r.day}-${i}`}
            arrow
            enterTouchDelay={0}
            leaveTouchDelay={2500}
            title={(
              <span>
                <strong>{shortDay(r.day)}</strong>
                {keys.map((k, ki) => (<React.Fragment key={k.key}><br />{fmt(r.vals[ki])} {k.label}</React.Fragment>))}
              </span>
            )}
          >
            <Box sx={{
              display: 'flex', alignItems: 'flex-end', justifyContent: 'center', gap: '2px',
              height, cursor: 'default', '&:hover .db-bar': { filter: 'brightness(1.2)' },
            }}>
              {r.vals.map((v, ki) => {
                const barH = v === 0 ? 2 : Math.max(4, (v / max) * plotH);
                return (
                  <Box key={keys[ki].key} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', flex: 1, minWidth: 0, maxWidth: 36 }}>
                    <Typography component="span" sx={{
                      height: LABEL_H, lineHeight: `${LABEL_H}px`, fontSize: fs, fontWeight: v === 0 ? 500 : 700,
                      fontVariantNumeric: 'tabular-nums', color: v === 0 ? 'text.disabled' : 'text.primary',
                      whiteSpace: 'nowrap', opacity: 0, animation: `dbFade .4s ease ${120 + i * 25}ms forwards`,
                      '@media (prefers-reduced-motion: reduce)': { animation: 'none', opacity: 1 },
                    }}>{fmtVal(v)}</Typography>
                    <Box className="db-bar" sx={{
                      width: n > 1 ? '80%' : '70%', maxWidth: 28, height: barH, bgcolor: keys[ki].color,
                      opacity: v === 0 ? 0.3 : 0.95, borderRadius: '4px 4px 0 0', transformOrigin: 'bottom',
                      transition: 'filter .15s', animation: `dbGrow .5s cubic-bezier(.2,.8,.2,1) ${i * 25}ms both`,
                      '@media (prefers-reduced-motion: reduce)': { animation: 'none' },
                    }} />
                  </Box>
                );
              })}
            </Box>
          </Tooltip>
        ))}
        {rows.map((r, i) => (
          <Typography key={`t-${r.day}-${i}`} variant="caption" color="text.disabled" sx={{
            textAlign: 'center', fontSize: 10, mt: 0.5, whiteSpace: 'nowrap', borderTop: '1px solid', borderColor: 'divider', pt: 0.5,
          }}>
            {i % tickEvery === 0 || i === rows.length - 1 ? shortDay(r.day) : ' '}
          </Typography>
        ))}
      </Box>
    </Box>
  );
}
