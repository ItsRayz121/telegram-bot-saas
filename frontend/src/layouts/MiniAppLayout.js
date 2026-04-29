import React, { useMemo } from 'react';
import { Box } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { TelegramProvider, useTelegram } from '../contexts/TelegramContext';

// Inner component so it can read tgTheme from context
function ThemedContent({ children }) {
  const { tgTheme } = useTelegram();

  const theme = useMemo(() => {
    // Use Telegram's colors when available, fall back to app defaults
    const primary = tgTheme?.buttonColor || '#2563EB';
    const bg = tgTheme?.bgColor || '#0f172a';
    const paper = tgTheme?.secondaryBgColor || '#1e293b';
    const text = tgTheme?.textColor || '#f1f5f9';
    const hint = tgTheme?.hintColor || '#94a3b8';

    return createTheme({
      palette: {
        mode: 'dark',
        primary: { main: primary },
        secondary: { main: '#7C3AED' },
        background: { default: bg, paper },
        text: { primary: text, secondary: hint },
        divider: 'rgba(255,255,255,0.08)',
      },
      typography: { fontFamily: "'Inter', -apple-system, sans-serif" },
      components: {
        MuiButton: { styleOverrides: { root: { textTransform: 'none', borderRadius: 10 } } },
        MuiCard: { styleOverrides: { root: { borderRadius: 14, border: '1px solid rgba(255,255,255,0.07)' } } },
      },
    });
  }, [tgTheme]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box
        sx={{
          minHeight: '100vh',
          bgcolor: 'background.default',
          pb: 'calc(env(safe-area-inset-bottom, 0px) + 64px)', // space for bottom nav
          pt: 'env(safe-area-inset-top, 0px)',
        }}
      >
        {children}
      </Box>
    </ThemeProvider>
  );
}

export default function MiniAppLayout({ children }) {
  return (
    <TelegramProvider>
      <ThemedContent>{children}</ThemedContent>
    </TelegramProvider>
  );
}
