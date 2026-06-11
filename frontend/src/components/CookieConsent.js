import React, { useState, useEffect } from 'react';
import { Box, Button, Typography, Stack, Link } from '@mui/material';
import { initPostHog, initGA } from '../index';

const STORAGE_KEY = 'telegizer_cookie_consent';

function bootIfPreviouslyAccepted() {
  if (localStorage.getItem(STORAGE_KEY) === 'accepted') {
    initPostHog();
    initGA();
  }
}
bootIfPreviouslyAccepted();

export default function CookieConsent() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      setVisible(true);
    }
  }, []);

  const accept = () => {
    localStorage.setItem(STORAGE_KEY, 'accepted');
    setVisible(false);
    initPostHog();
    initGA();
  };

  const decline = () => {
    localStorage.setItem(STORAGE_KEY, 'declined');
    setVisible(false);
    if (window.__posthog_initialized && window.posthog) {
      window.posthog.opt_out_capturing();
    }
  };

  if (!visible) return null;

  return (
    <Box
      role="dialog"
      aria-live="polite"
      aria-label="Cookie consent"
      sx={{
        position: 'fixed',
        bottom: { xs: 0, sm: 16 },
        left: { xs: 0, sm: 16 },
        right: { xs: 0, sm: 'auto' },
        maxWidth: { sm: 440 },
        zIndex: 9999,
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: { xs: 0, sm: 2 },
        p: 2.5,
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }}
    >
      <Typography variant="body2" fontWeight={600} mb={0.75}>
        Analytics cookies
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={2} lineHeight={1.6}>
        We use Google Analytics and PostHog (anonymised usage) to improve the product.
        No data is sold or shared with advertisers.{' '}
        <Link href="/privacy" color="primary.light" underline="hover">
          Privacy Policy
        </Link>
      </Typography>
      <Stack direction="row" spacing={1}>
        <Button size="small" variant="contained" onClick={accept} sx={{ flexShrink: 0 }}>
          Accept
        </Button>
        <Button size="small" variant="text" color="inherit" onClick={decline} sx={{ color: 'text.secondary' }}>
          Decline
        </Button>
      </Stack>
    </Box>
  );
}
