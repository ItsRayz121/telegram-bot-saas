import React from 'react';
import { Box, Typography, Button, Stack } from '@mui/material';
import { SmartToy } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

export default function NotFound() {
  const navigate = useNavigate();
  const token = localStorage.getItem('token');

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        textAlign: 'center',
        p: 3,
      }}
    >
      <Box>
        <SmartToy sx={{ fontSize: 72, color: 'text.disabled', mb: 2 }} />
        <Typography variant="h2" fontWeight={800} color="text.secondary" mb={1}>
          404
        </Typography>
        <Typography variant="h5" fontWeight={600} mb={1}>
          Page not found
        </Typography>
        <Typography variant="body1" color="text.secondary" mb={4} maxWidth={360} mx="auto">
          The page you're looking for doesn't exist or has been moved.
        </Typography>
        <Stack direction="row" spacing={2} justifyContent="center">
          <Button variant="contained" onClick={() => navigate(token ? '/dashboard' : '/')}>
            {token ? 'Go to Dashboard' : 'Go Home'}
          </Button>
          <Button variant="outlined" onClick={() => navigate(-1)}>
            Go Back
          </Button>
        </Stack>
      </Box>
    </Box>
  );
}
