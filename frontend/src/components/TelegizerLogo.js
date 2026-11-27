import React from 'react';
import { Box } from '@mui/material';

const SIZE_MAP = {
  xs: { mark: 16, fontSize: '0.875rem', gap: 0.75 },
  sm: { mark: 20, fontSize: '1rem',     gap: 1 },
  md: { mark: 22, fontSize: '1.125rem', gap: 1 },
  lg: { mark: 30, fontSize: '1.5rem',   gap: 1.25 },
  xl: { mark: 44, fontSize: '2.125rem', gap: 1.5 },
};

export const LOGO_BLUE = '#4a9ff5';

/** The Telegizer mark: a flat paper plane leaving two motion lines. One colour, no tile. */
export function TelegizerMark({ size = 20, color = LOGO_BLUE, title }) {
  return (
    <Box
      component="svg"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : 'true'}
      sx={{ display: 'block', flexShrink: 0 }}
    >
      <path d="M21.2 2.8 4.6 9.6l6.1 2.3 2.4 6.3 8.1-15.4Z" fill={color} />
      <path d="m21.2 2.8-10.5 9.1" stroke="#0f1012" strokeOpacity="0.45" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M2.5 15.5h4M4.5 19h3.5" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
    </Box>
  );
}

/**
 * Telegizer brand logo.
 * variant="full" → mark + "telegizer" wordmark (default)
 * variant="icon" → mark only
 * size: "xs" | "sm" | "md" | "lg" | "xl"
 */
export default function TelegizerLogo({ variant = 'full', size = 'md', sx = {} }) {
  const { mark, fontSize, gap } = SIZE_MAP[size] || SIZE_MAP.md;
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap, lineHeight: 1, ...sx }}>
      <TelegizerMark size={mark} title={variant === 'icon' ? 'Telegizer' : undefined} />
      {variant === 'full' && (
        <Box
          component="span"
          sx={{ fontWeight: 600, fontSize, letterSpacing: '-0.01em', lineHeight: 1, color: 'text.primary', userSelect: 'none' }}
        >
          telegizer
        </Box>
      )}
    </Box>
  );
}
