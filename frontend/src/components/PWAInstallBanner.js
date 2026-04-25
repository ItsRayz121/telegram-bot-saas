import React, { useState, useEffect } from 'react';
import { Box, Button, Typography, IconButton } from '@mui/material';
import { Close, IosShare } from '@mui/icons-material';

export default function PWAInstallBanner() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [showAndroid, setShowAndroid] = useState(false);
  const [showIOS, setShowIOS] = useState(false);
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem('pwa_banner_dismissed') === '1'
  );

  useEffect(() => {
    if (dismissed) return;

    const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
    const isInStandalone = window.navigator.standalone === true || window.matchMedia('(display-mode: standalone)').matches;

    if (isIOS && !isInStandalone) {
      const t = setTimeout(() => setShowIOS(true), 3000);
      return () => clearTimeout(t);
    }

    const handler = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setShowAndroid(true);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, [dismissed]);

  const handleInstall = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    setDeferredPrompt(null);
    setShowAndroid(false);
    if (outcome === 'accepted') {
      localStorage.setItem('pwa_banner_dismissed', '1');
      setDismissed(true);
    }
  };

  const handleDismiss = () => {
    setShowAndroid(false);
    setShowIOS(false);
    localStorage.setItem('pwa_banner_dismissed', '1');
    setDismissed(true);
  };

  if (!showAndroid && !showIOS) return null;

  const bannerSx = {
    position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 1400,
    bgcolor: '#161b22', borderTop: '1px solid #30363d',
    p: 2, display: { md: 'none' },
    boxShadow: '0 -4px 24px rgba(0,0,0,0.4)',
  };

  if (showAndroid) {
    return (
      <Box sx={bannerSx}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Box
            component="img"
            src="/icons/telegizer-icon.png"
            alt="Telegizer"
            sx={{ width: 36, height: 36, objectFit: 'contain', flexShrink: 0, borderRadius: 1.5 }}
          />
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography variant="body2" fontWeight={700}>Install Telegizer</Typography>
            <Typography variant="caption" color="text.secondary">
              Add to your home screen for fast access
            </Typography>
          </Box>
          <Button size="small" variant="contained" onClick={handleInstall} sx={{ flexShrink: 0 }}>
            Install
          </Button>
          <IconButton size="small" onClick={handleDismiss} sx={{ flexShrink: 0 }}>
            <Close fontSize="small" />
          </IconButton>
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={bannerSx}>
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
        <IosShare color="primary" sx={{ flexShrink: 0, mt: 0.25 }} />
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography variant="body2" fontWeight={700}>Add to Home Screen</Typography>
          <Typography variant="caption" color="text.secondary">
            Tap <strong>Share</strong> (
            <IosShare sx={{ fontSize: 12, verticalAlign: 'middle' }} />
            ) then <strong>"Add to Home Screen"</strong>
          </Typography>
        </Box>
        <IconButton size="small" onClick={handleDismiss} sx={{ flexShrink: 0 }}>
          <Close fontSize="small" />
        </IconButton>
      </Box>
    </Box>
  );
}
