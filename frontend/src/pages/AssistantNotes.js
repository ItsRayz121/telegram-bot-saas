import React from 'react';
import { Box, Typography } from '@mui/material';
import { EditNote } from '@mui/icons-material';

export default function AssistantNotes() {
  return (
    <Box sx={{ p: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 400 }}>
      <EditNote sx={{ fontSize: 56, color: 'text.disabled', mb: 2 }} />
      <Typography variant="h5" fontWeight={600} gutterBottom>Notes</Typography>
      <Typography color="text.secondary" textAlign="center" maxWidth={400}>
        Capture decisions, tasks, and links from your groups — manually or via AI extraction.
        Coming in Sprint 4.
      </Typography>
    </Box>
  );
}
