import React from 'react';
import { Box, Typography } from '@mui/material';

const SIZE_MAP = {
  xs: { img: 20, fontSize: '0.85rem',  gap: 0.5  },
  sm: { img: 26, fontSize: '1.05rem', gap: 0.75 },
  md: { img: 34, fontSize: '1.35rem', gap: 1    },
  lg: { img: 46, fontSize: '1.8rem',  gap: 1.25 },
  xl: { img: 64, fontSize: '2.4rem',  gap: 1.5  },
};

/**
 * Telegizer brand logo component.
 *
 * variant="full"  → icon mark + "telegizer" wordmark (default)
 * variant="icon"  → icon mark only (compact nav, loading, empty states)
 *
 * size: "xs" | "sm" | "md" | "lg" | "xl"
 */
export default function TelegizerLogo({ variant = 'full', size = 'md', sx = {} }) {
  const { img, fontSize, gap } = SIZE_MAP[size] || SIZE_MAP.md;

  return (
    <Box
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap,
        lineHeight: 1,
        ...sx,
      }}
    >
      <Box
        component="img"
        src="/icons/telegizer-icon-192.png"
        alt="Telegizer"
        aria-hidden={variant === 'full' ? 'true' : 'false'}
        sx={{
          width: img,
          height: img,
          objectFit: 'contain',
          display: 'block',
          flexShrink: 0,
          // Crisp rendering on retina displays
          imageRendering: '-webkit-optimize-contrast',
        }}
      />
      {variant === 'full' && (
        <Typography
          component="span"
          aria-label="Telegizer"
          sx={{
            fontWeight: 800,
            fontSize,
            letterSpacing: '-0.035em',
            lineHeight: 1,
            background: 'linear-gradient(125deg, #2563EB 20%, #06B6D4 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            userSelect: 'none',
          }}
        >
          telegizer
        </Typography>
      )}
    </Box>
  );
}
