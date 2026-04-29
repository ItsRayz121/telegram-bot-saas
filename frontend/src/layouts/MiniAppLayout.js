import React from 'react';
import { Box } from '@mui/material';
import { TelegramProvider } from '../contexts/TelegramContext';

export default function MiniAppLayout({ children }) {
  return (
    <TelegramProvider>
      <Box
        sx={{
          minHeight: '100vh',
          bgcolor: 'background.default',
          // Respect Telegram's safe area insets on iOS
          pb: 'env(safe-area-inset-bottom, 16px)',
          pt: 'env(safe-area-inset-top, 0px)',
        }}
      >
        {children}
      </Box>
    </TelegramProvider>
  );
}
