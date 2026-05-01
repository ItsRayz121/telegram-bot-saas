import React, { useMemo, useEffect } from 'react';
import { Box } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { useNavigate, useLocation } from 'react-router-dom';
import { TelegramProvider, useTelegram } from '../contexts/TelegramContext';

// Auto-wire Telegram BackButton: show when navigated past the mini-app root
function BackButtonManager() {
  const { tg } = useTelegram();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isRoot = pathname === '/mini-app' || pathname === '/mini-app/';

  useEffect(() => {
    const btn = tg?.BackButton;
    if (!btn) return;
    if (isRoot) {
      btn.hide();
    } else {
      const handler = () => navigate(-1);
      btn.show();
      btn.onClick(handler);
      return () => {
        btn.offClick(handler);
        btn.hide();
      };
    }
  }, [tg, isRoot, navigate]);

  return null;
}

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
      typography: {
        fontFamily: "'Inter', -apple-system, sans-serif",
        h4: { fontSize: '1.25rem', '@media (min-width:600px)': { fontSize: '1.65rem' } },
        h5: { fontSize: '1.05rem', '@media (min-width:600px)': { fontSize: '1.25rem' } },
        h6: { fontSize: '0.95rem', '@media (min-width:600px)': { fontSize: '1.1rem' } },
        subtitle1: { fontSize: '0.875rem', '@media (min-width:600px)': { fontSize: '1rem' } },
        body1: { fontSize: '0.9rem' },
        body2: { fontSize: '0.8rem' },
      },
      components: {
        MuiButton: {
          styleOverrides: {
            root: {
              textTransform: 'none',
              borderRadius: 10,
              // Tappable but not oversized inside Telegram WebView
              minHeight: 40,
              fontSize: '0.875rem',
            },
          },
        },
        MuiCard: { styleOverrides: { root: { borderRadius: 14, border: '1px solid rgba(255,255,255,0.07)' } } },
        MuiCardContent: {
          styleOverrides: {
            root: {
              padding: '12px',
              '&:last-child': { paddingBottom: '12px' },
              '@media (min-width:600px)': { padding: '16px', '&:last-child': { paddingBottom: '16px' } },
            },
          },
        },
      },
    });
  }, [tgTheme]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BackButtonManager />
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
