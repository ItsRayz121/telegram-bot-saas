import React from 'react';
import { Box, Typography } from '@mui/material';
import { Summarize } from '@mui/icons-material';

export default function AssistantDigests() {
  return (
    <Box sx={{ p: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 400 }}>
      <Summarize sx={{ fontSize: 56, color: 'text.disabled', mb: 2 }} />
      <Typography variant="h5" fontWeight={600} gutterBottom>Digests</Typography>
      <Typography color="text.secondary" textAlign="center" maxWidth={400}>
        AI-powered daily summaries of your group activity, delivered to your DM or group topic.
        Coming in Sprint 3.
      </Typography>
    </Box>
  );
}
