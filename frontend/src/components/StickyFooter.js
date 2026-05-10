/**
 * StickyFooter — mobile action bar that docks above the bottom navigation.
 *
 * Uses `position: sticky` instead of `position: fixed` to avoid the
 * Telegram WebView / Android Chrome bug where fixed-position elements
 * inside an overflow:auto scroll container are positioned relative to
 * that container rather than the viewport (causing the bar to appear
 * mid-screen as the page scrolls).
 *
 * With sticky, the element flows normally in the document and sticks at
 * `bottom: calc(56px + safe-area)` — just above the app's bottom nav —
 * when the user scrolls past its natural position.
 *
 * Desktop: hidden (save button lives in the AppBar there).
 * Mobile: always rendered when `hidden` is false.
 */

import React from 'react';
import { Box } from '@mui/material';

// Height of the AppLayout mobile bottom navigation bar (px).
const BOTTOM_NAV_HEIGHT = 56;

export default function StickyFooter({ children, hidden = false }) {
  if (hidden) return null;

  return (
    <Box
      sx={{
        // Mobile only — desktop uses the AppBar save button
        display: { xs: 'block', md: 'none' },

        // sticky instead of fixed: works correctly in Telegram WebApp,
        // Android Chrome WebViews, and mobile PWAs where position:fixed
        // inside overflow:auto breaks containment.
        position: 'sticky',

        // Sit just above the fixed bottom navigation bar.
        // env(safe-area-inset-bottom) handles iPhone notch / home indicator.
        bottom: `calc(${BOTTOM_NAV_HEIGHT}px + env(safe-area-inset-bottom))`,

        // Full-width within its scroll container (GroupSettings outer Box
        // has no maxWidth, so this spans the viewport width).
        left: 0,
        right: 0,

        // Above settings content (1000), below MUI modals (1300)
        zIndex: 1100,

        p: 1.5,
        bgcolor: 'background.paper',
        borderTop: '1px solid',
        borderColor: 'divider',

        // Subtle slide-up entrance so the bar doesn't feel jarring
        '@keyframes slideUp': {
          from: { transform: 'translateY(8px)', opacity: 0 },
          to:   { transform: 'translateY(0)',   opacity: 1 },
        },
        animation: 'slideUp 0.18s ease-out',
      }}
    >
      {children}
    </Box>
  );
}
