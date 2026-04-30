import React from 'react';
import { Box, Typography } from '@mui/material';
import { Tune } from '@mui/icons-material';

export default function AssistantAISettings() {
  return (
    <Box sx={{ p: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 400 }}>
      <Tune sx={{ fontSize: 56, color: 'text.disabled', mb: 2 }} />
      <Typography variant="h5" fontWeight={600} gutterBottom>AI Settings</Typography>
      <Typography color="text.secondary" textAlign="center" maxWidth={400}>
        Configure the AI provider for all Assistant features. Use the platform Gemini key or bring your own.
        Coming in Sprint 2.
      </Typography>
    </Box>
  );
}
